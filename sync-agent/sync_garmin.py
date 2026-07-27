import os
import csv
from datetime import date
from pathlib import Path
from garminconnect import Garmin

def flatten_dict(d, parent_key='', sep='_'):
    items = []
    if not isinstance(d, dict):
        return {parent_key: d}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, str(v)))
        else:
            items.append((new_key, v))
    return dict(items)

def save_to_csv(data, filename):
    if not data:
        return
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or len(data) == 0:
        return
        
    keys = set()
    for d in data:
        keys.update(d.keys())
        
    with open(filename, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(keys))
        writer.writeheader()
        writer.writerows(data)

def generate_activity_markdown(activity, output_dir):
    activity_id = activity.get("activityId")
    name = activity.get("activityName", "Activité Garmin")
    date_str = activity.get("startTimeLocal", "").split(" ")[0] if activity.get("startTimeLocal") else "unknown_date"
    distance_km = activity.get("distance", 0) / 1000.0 if activity.get("distance") else 0
    duration_min = activity.get("duration", 0) / 60.0 if activity.get("duration") else 0
    avg_hr = activity.get("averageHR", 0)
    
    avg_pace = "N/A"
    if distance_km > 0 and duration_min > 0:
        pace_dec = duration_min / distance_km
        p_min = int(pace_dec)
        p_sec = int((pace_dec - p_min) * 60)
        avg_pace = f"{p_min}:{p_sec:02d} min/km"
    
    md_content = f"""---
type: entrainement/garmin
date: {date_str}
id_garmin: {activity_id}
distance_km: {distance_km:.2f}
allure_moyenne: "{avg_pace}"
---
# 🏃 {name}

## 📊 Résumé des Performances
- **Date :** {date_str}
- **Distance :** {distance_km:.2f} km
- **Durée :** {duration_min:.1f} min
- **Allure moyenne :** {avg_pace}
- **Cardio moyen :** {int(avg_hr) if avg_hr else 'N/A'} bpm
"""
    file_path = output_dir / f"Activite_{date_str}_{activity_id}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✓ Markdown d'activité généré : {file_path.name}")

def generate_daily_stats_markdown(stats_data, sleep_data, today_str, output_dir):
    sleep_score = sleep_data.get("dailySleepDTO", {}).get("sleepScores", {}).get("overall", {}).get("value", "N/A") if sleep_data else "N/A"
    sleep_time = sleep_data.get("dailySleepDTO", {}).get("sleepTimeSeconds", 0) if sleep_data else 0
    sleep_hours = int(sleep_time // 3600)
    sleep_mins = int((sleep_time % 3600) // 60)
    
    rest_hr = stats_data.get("restingHeartRate", "N/A") if stats_data else "N/A"
    stress_avg = stats_data.get("averageStressLevel", "N/A") if stats_data else "N/A"
    
    bb_max = stats_data.get("bodyBatteryHighestValue", "N/A") if stats_data else "N/A"
    
    # Simple appreciation
    sleep_judgement = "Bonne" if isinstance(sleep_score, int) and sleep_score > 75 else "Moyenne/Mauvaise"
    stress_judgement = "Calme" if isinstance(stress_avg, int) and stress_avg < 25 else "Élevé"
    
    md_content = f"""---
type: health/daily
date: {today_str}
sleep_score: {sleep_score}
resting_hr: {rest_hr}
stress_avg: {stress_avg}
---
# 🩺 Bilan Santé Garmin - {today_str}

## 💤 Sommeil
- **Durée** : {sleep_hours}h {sleep_mins}m
- **Score** : {sleep_score} / 100 ({sleep_judgement})

## ❤️ Cœur & Stress
- **FC Repos** : {rest_hr} bpm
- **Stress Moyen** : {stress_avg} ({stress_judgement})

## 🔋 Énergie
- **Body Battery Max** : {bb_max}
"""
    file_path = output_dir / f"Garmin_Daily_{today_str}.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✓ Bilan de santé quotidien généré : {file_path.name}")

def fetch_and_save_metrics():
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        print("GARMIN_EMAIL or GARMIN_PASSWORD not set")
        return
    
    token_dir = "/app/.garminconnect"
    os.makedirs(token_dir, exist_ok=True)
    
    output_dir = Path("/app/vault/Health")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    activity_dir = Path("/app/vault/Entrainements")
    activity_dir.mkdir(parents=True, exist_ok=True)
    
    today = date.today()
    today_str = today.isoformat()
    
    print(f"Connexion à Garmin Connect pour {today_str}...")
    try:
        client = Garmin(email, password)
        client.login(token_dir)
        
        metrics = {
            "hrv": client.get_hrv_data,
            "sleep": client.get_sleep_data,
            "stress": client.get_stress_data,
            "body_battery": client.get_body_battery,
            "spo2": client.get_spo2_data,
            "daily_stats": client.get_stats
        }
        
        fetched_data = {}
        for name, func in metrics.items():
            try:
                data = func(today_str)
                fetched_data[name] = data
                if data:
                    if isinstance(data, list):
                        flat_data = [flatten_dict(item) for item in data]
                    else:
                        flat_data = flatten_dict(data)
                    save_to_csv(flat_data, output_dir / f"{name}_{today_str}.csv")
                    print(f"✓ {name} sauvé.")
            except Exception as e:
                print(f"Erreur pour {name}: {e}")

        # Generate daily stats Markdown
        generate_daily_stats_markdown(
            fetched_data.get("daily_stats"),
            fetched_data.get("sleep"),
            today_str,
            output_dir
        )
        
        # Fetch recent activities and generate Markdown
        print("Récupération des dernières activités...")
        try:
            activities = client.get_activities(0, 5) # Fetch up to 5 recent activities
            if activities:
                for act in activities:
                    generate_activity_markdown(act, activity_dir)
            else:
                print("Aucune activité récente trouvée.")
        except Exception as e:
            print(f"Erreur lors de la récupération des activités : {e}")

        print("Garmin health metrics successfully fetched and saved.")

    except Exception as e:
        print(f"Error in Garmin client: {e}")

if __name__ == "__main__":
    fetch_and_save_metrics()
