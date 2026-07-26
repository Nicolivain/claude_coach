import os
import urllib.request
import json

# Récupération automatique de tes variables d'environnement
signal_api_url = os.getenv("SIGNAL_API_URL")
my_number = os.getenv("MY_PHONE_NUMBER")

if not signal_api_url or not my_number:
    print("❌ Erreur : SIGNAL_API_URL ou MY_PHONE_NUMBER n'est pas défini dans l'environnement.")
    exit(1)

# Préparation de la requête
url = f"{signal_api_url}/v2/send"
payload = {
    "message": "🚀 Test réussi : le coach-orchestrator communique parfaitement avec Signal !",
    "number": my_number,
    "recipients": [my_number]
}

data = json.dumps(payload).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})

print(f"Envoi du message depuis le conteneur à {my_number}...")

try:
    with urllib.request.urlopen(req) as response:
        print(f"✅ Succès ! Statut HTTP : {response.status}")
except urllib.error.HTTPError as e:
    print(f"❌ Erreur HTTP : {e.code} - {e.read().decode('utf-8')}")
except Exception as e:
    print(f"❌ Erreur de connexion : {e}")