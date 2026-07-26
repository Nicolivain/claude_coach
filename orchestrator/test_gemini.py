"""
Test isolé de l'API Gemini, sans dépendance à Signal, Docker ou Obsidian.
Usage :
    pip install --break-system-packages google-genai
    export GEMINI_API_KEY="ta-cle-ici"
    python3 test_gemini.py
"""
import os
from google import genai
from google.genai import types
 
def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("❌ La variable d'environnement GEMINI_API_KEY n'est pas définie.")
        print("   Lance : export GEMINI_API_KEY=\"ta-cle-ici\"")
        return
 
    model_name = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    client = genai.Client()  # lit GEMINI_API_KEY automatiquement
 
    print(f"Envoi d'une requête de test à Gemini (modèle : {model_name})...")
    response = client.models.generate_content(
        model=model_name,
        contents="Réponds en une phrase : est-ce que tu reçois bien ce message ?",
        config=types.GenerateContentConfig(
            system_instruction="Tu es un assistant de test, réponds de façon très brève.",
        ),
    )
 
    print("\n✓ Réponse reçue :")
    print(response.text)
 
 
if __name__ == "__main__":
    main()
