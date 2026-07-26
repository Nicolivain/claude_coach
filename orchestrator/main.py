import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta

import requests
import websocket
from flask import Flask, jsonify
from google import genai
from google.genai import types
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ---------- Configuration ----------

VAULT_DIR = Path("/app/vault")
TRAINING_DIR = VAULT_DIR / "Entrainements"
STATE_DIR = Path("/app/state")
STATE_DIR.mkdir(parents=True, exist_ok=True)

CONVERSATION_HISTORY_PATH = STATE_DIR / "conversation_history.json"

SIGNAL_API_URL = os.environ["SIGNAL_API_URL"]          # ex: http://signal-api:8080
MY_PHONE_NUMBER = os.environ["MY_PHONE_NUMBER"]        # ex: +33612345678
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
RECENT_HISTORY_DAYS = int(os.environ.get("RECENT_HISTORY_DAYS", "7"))
MAX_HISTORY_TURNS = int(os.environ.get("MAX_HISTORY_TURNS", "20"))

# Client() lit automatiquement la variable d'environnement GEMINI_API_KEY
client = genai.Client()

# Charge le prompt système depuis un fichier externe pour facilité de modification
SYSTEM_PROMPT_FILE = Path("system_prompt.txt")

try:
    SYSTEM_PROMPT = SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
except FileNotFoundError:
    print(f"⚠️ Fichier {SYSTEM_PROMPT_FILE} non trouvé, utilisation du prompt par défaut")
    SYSTEM_PROMPT = """Tu es un coach sportif assistant pour la course à pied.
    Objectif : aider à préparer un semi-marathon.
    Sois concis et donne des conseils pratiques.
    """


# ---------- Signal : envoi ----------

RECENTLY_SENT_MESSAGES = set()


def send_signal_message(text):
    if text:
        RECENTLY_SENT_MESSAGES.add(text.strip())
        if len(RECENTLY_SENT_MESSAGES) > 100:
            RECENTLY_SENT_MESSAGES.clear()
    payload = {
        "message": text,
        "number": MY_PHONE_NUMBER,
        "recipients": [MY_PHONE_NUMBER],  # envoi vers "Note à moi-même"
    }
    resp = requests.post(f"{SIGNAL_API_URL}/v2/send", json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------- Contexte Obsidian ----------

def load_recent_notes(days=RECENT_HISTORY_DAYS):
    cutoff = datetime.now() - timedelta(days=days)
    notes = []
    for md_file in sorted(VAULT_DIR.rglob("*.md")):
        try:
            mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
        except OSError:
            continue
        if mtime >= cutoff:
            notes.append(md_file.read_text(encoding="utf-8"))
    return notes


def load_all_notes_context():
    return [md_file.read_text(encoding="utf-8") for md_file in sorted(VAULT_DIR.rglob("*.md"))]


# ---------- Appel Gemini ----------

def ask_gemini(user_message, context_notes, conversation_history=None):
    """
    conversation_history : liste de dicts {"role": "user"|"model", "content": "..."}
    (on garde ce format simple en local, et on le convertit ici au format attendu par le SDK)
    """
    context_block = "\n\n---\n\n".join(context_notes) if context_notes else "(aucune note disponible)"

    contents = []
    for turn in (conversation_history or []):
        contents.append(types.Content(
            role=turn["role"],
            parts=[types.Part.from_text(text=turn["content"])],
        ))

    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=(
            f"Contexte (notes d'entraînement) :\n\n{context_block}\n\n"
            f"---\n\nMessage : {user_message}"
        ))],
    ))

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return response.text


# ---------- Flux proactif : nouvelle séance détectée ----------

class NewWorkoutHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        # Laisse le temps au fichier d'être complètement écrit avant lecture
        time.sleep(2)
        try:
            handle_new_workout(Path(event.src_path))
        except Exception as e:
            print(f"❌ Erreur traitement {event.src_path} : {e}")


def handle_new_workout(md_path):
    print(f"📄 Nouvelle séance détectée : {md_path.name}")
    new_note = md_path.read_text(encoding="utf-8")
    recent_notes = [n for n in load_recent_notes() if n != new_note]

    prompt = (
        f"Nouvelle séance à analyser :\n\n{new_note}\n\n"
        "Analyse-la à la lumière des 7 derniers jours d'entraînement et donne un débrief court."
    )
    analysis = ask_gemini(prompt, recent_notes)
    send_signal_message(f"🏃 Débrief ({md_path.stem}) :\n\n{analysis}")
    print(f"✓ Débrief envoyé pour {md_path.name}")


def start_file_watcher():
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(NewWorkoutHandler(), str(TRAINING_DIR), recursive=True)
    observer.start()
    print(f"👀 Surveillance de {TRAINING_DIR} activée.")
    return observer


# ---------- Flux interactif : messages Signal entrants (websocket, mode json-rpc) ----------

def load_conversation_history():
    if CONVERSATION_HISTORY_PATH.exists():
        return json.loads(CONVERSATION_HISTORY_PATH.read_text(encoding="utf-8"))
    return []


def save_conversation_history(history):
    trimmed = history[-MAX_HISTORY_TURNS:]
    CONVERSATION_HISTORY_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def handle_incoming_signal_message(text):
    print(f"💬 Message Signal reçu : {text}")
    history = load_conversation_history()
    all_notes = load_all_notes_context()

    answer = ask_gemini(text, all_notes, conversation_history=history)

    history.append({"role": "user", "content": text})
    history.append({"role": "model", "content": answer})
    save_conversation_history(history)

    send_signal_message(answer)
    print("✓ Réponse envoyée sur Signal.")


def on_ws_message(ws, message):
    print(f"📩 WS RAW: {message}")
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return

    envelope = data.get("envelope", {})
    text = None

    # Récupération de l'expéditeur principal
    source_number = envelope.get("sourceNumber") or envelope.get("source")

    # 1. Message direct entrant (ex: tapé depuis un autre appareil lié)
    data_message = envelope.get("dataMessage")
    if data_message and isinstance(data_message, dict):
        # On ignore les groupes, et on vérifie que le message vient de TOI
        if source_number == MY_PHONE_NUMBER and not data_message.get("groupInfo"):
            text = data_message.get("message")

    # 2. Message synchronisé (tapé depuis ton téléphone principal)
    sync_message = envelope.get("syncMessage")
    if not text and sync_message and isinstance(sync_message, dict):
        sent_message = sync_message.get("sentMessage")
        if sent_message and isinstance(sent_message, dict):
            # On vérifie que le destinataire est bien TOI (Note à moi-même)
            destination = sent_message.get("destination") or sent_message.get("destinationNumber")
            if destination == MY_PHONE_NUMBER and not sent_message.get("groupInfo"):
                text = sent_message.get("message")

    if not text:
        return

    clean_text = text.strip()
    if clean_text in RECENTLY_SENT_MESSAGES:
        # Ignore les messages générés/envoyés par le bot lui-même
        RECENTLY_SENT_MESSAGES.discard(clean_text)
        return

    try:
        handle_incoming_signal_message(text)
    except Exception as e:
        print(f"❌ Erreur traitement message Signal : {e}")


def on_ws_error(ws, error):
    print(f"⚠️ Erreur websocket Signal : {error}")


def on_ws_close(ws, close_status_code, close_msg):
    print("🔌 Websocket Signal fermée, reconnexion dans 5s...")
    time.sleep(5)
    start_signal_websocket()


def start_signal_websocket():
    ws_url = SIGNAL_API_URL.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_url}/v1/receive/{MY_PHONE_NUMBER}"

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_ws_message,
        on_error=on_ws_error,
        on_close=on_ws_close,
    )
    thread = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 30}, daemon=True)
    thread.start()
    print(f"🔌 Connexion websocket établie vers {ws_url}")
    return ws


# ---------- Petit serveur Flask (healthcheck / debug manuel) ----------

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/debrief/latest", methods=["POST"])
def trigger_latest_debrief():
    """Endpoint manuel de secours pour forcer un débrief sans passer par le watcher."""
    files = sorted(TRAINING_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return jsonify({"error": "aucune note trouvée"}), 404
    handle_new_workout(files[0])
    return jsonify({"status": "débrief envoyé", "file": files[0].name})


def run_flask():
    app.run(host="0.0.0.0", port=5000)


# ---------- Main ----------

def main():
    print("🚀 Démarrage du coach-orchestrator...")
    start_file_watcher()
    start_signal_websocket()
    run_flask()  # bloquant, garde le process principal en vie


if __name__ == "__main__":
    main()