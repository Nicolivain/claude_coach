import os
from garminconnect import Garmin

print("Connexion à Garmin Connect...")
try:
    # On initialise le client avec les variables d'environnement de Docker
    client = Garmin(os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD"))
    client.login()
    print("✓ Connexion réussie !")

    # On récupère les 3 dernières activités
    activities = client.get_activities(0, 3)
    
    if activities:
        for act in activities:
            if act["activityType"]["typeKey"] == "running":
                print(f"\nDernière course trouvée : {act['activityName']}")
                print(f"Distance : {act['distance']/1000:.2f} km")
                print(f"Durée : {act['duration']/60:.2f} min")
                break
    else:
        print("Aucune activité trouvée.")

except Exception as e:
    print(f"Erreur de connexion : {e}")