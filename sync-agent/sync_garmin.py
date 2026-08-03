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

def format_pace(duration_seconds, distance_meters):
    if distance_meters == 0 or duration_seconds == 0:
        return "0:00"
    velocity_mins = (duration_seconds / 60) / (distance_meters / 1000)
    minutes = int(velocity_mins)
    seconds = int((velocity_mins - minutes) * 60)
    return f"{minutes}:{seconds:02d}"

def format_duration(seconds):
    if not seconds or seconds < 0: return "0s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0: return f"{hours}h {minutes}m {secs}s"
    return f"{minutes}min {secs}s"

def find_metric_index(metrics_map, keys):
    for k in keys:
        idx = metrics_map.get(k)
        if idx is not None:
            return idx
    return None

def process_activity_detailed(client, activity, output_dir):
    """
    Fetches raw telemetry for a Garmin activity, calculates 1km splits, 
    and generates a detailed Markdown summary.
    """
    activity_id = activity.get("activityId")
    name = activity.get("activityName", "Activité Garmin")
    date_str = activity.get("startTimeLocal", "").split(" ")[0] if activity.get("startTimeLocal") else "unknown_date"
    
    total_duration_summary = activity.get("duration", 0)
    total_distance_summary = activity.get("distance", 0)
    avg_hr_summary = activity.get("averageHR", 0)
    
    csv_filename = output_dir / f"Activite_{date_str}_{activity_id}_brut.csv"
    md_filename = output_dir / f"Activite_{date_str}_{activity_id}.md"
    
    raw_rows = []
    
    # 1. Fetch from Garmin if CSV doesn't exist, otherwise read from disk
    if not csv_filename.exists():
        print(f"Téléchargement des données brutes depuis Garmin : {name} ({date_str})...")
        try:
            details = client.get_activity_details(activity_id)
            raw_metrics = details.get("activityDetailMetrics", [])
            
            if raw_metrics:
                # Map metric keys to their respective indices in the metrics array
                metrics_map = {desc["key"]: desc["metricsIndex"] for desc in details.get("metricDescriptors", [])}
                
                time_idx = find_metric_index(metrics_map, ["directTimestamp", "timestamp", "time"])
                dist_idx = find_metric_index(metrics_map, ["sumDistance", "directDistance", "distance"])
                speed_idx = find_metric_index(metrics_map, ["directSpeed", "speed"])
                hr_idx = find_metric_index(metrics_map, ["directHeartRate", "heartRate"])
                alt_idx = find_metric_index(metrics_map, ["directElevation", "elevation", "altitude"])
                
                # Write to disk and store in memory simultaneously
                with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(["timestamp", "distance_m", "speed_ms", "heart_rate", "altitude_m"])
                    
                    for point in raw_metrics:
                        m = point.get("metrics", [])
                        
                        # Extract point data safely
                        t = m[time_idx] if time_idx is not None and len(m) > time_idx else 0
                        d = m[dist_idx] if dist_idx is not None and len(m) > dist_idx else 0
                        s = m[speed_idx] if speed_idx is not None and len(m) > speed_idx else 0
                        hr = m[hr_idx] if hr_idx is not None and len(m) > hr_idx else 0
                        alt = m[alt_idx] if alt_idx is not None and len(m) > alt_idx else 0
                        
                        raw_rows.append({"timestamp": t, "distance_m": d, "speed_ms": s, "heart_rate": hr, "altitude_m": alt})
                        writer.writerow([t, d, s, hr, alt])
                        
                print(f"✓ Fichier CSV généré : {csv_filename.name}")
        except Exception as e:
            print(f"Impossible de récupérer la télémétrie pour {activity_id}: {e}")
    else:
        # Load from disk if it already exists
        with open(csv_filename, "r", encoding="utf-8") as csvfile:
            raw_rows = list(csv.DictReader(csvfile))

    # 2. Parse telemetry points and compute elapsed time
    splits = []
    markdown_splits = ""
    reconstructed_total_distance = total_distance_summary
    overall_pace = format_pace(total_duration_summary, total_distance_summary)
    max_hr = 0
    avg_hr = avg_hr_summary
    
    if raw_rows:
        # Garmin sometimes uses ms epoch vs seconds epoch, detect which one it is
        first_ts_raw = float(raw_rows[0].get("timestamp") or 0.0)
        ts_is_milliseconds = first_ts_raw > 1e12
        
        parsed_points = []
        first_ts = None
        for row in raw_rows:
            ts = float(row.get("timestamp") or 0.0)
            if first_ts is None:
                first_ts = ts
            
            # Normalize elapsed time to seconds
            delta = ts - first_ts
            elapsed = delta / 1000.0 if ts_is_milliseconds else delta
            
            parsed_points.append({
                "elapsed": elapsed,
                "distance": float(row.get("distance_m") or 0.0),
                "speed": float(row.get("speed_ms") or 0.0),
                "hr": float(row.get("heart_rate") or 0.0),
            })
            
        # 3. Calculate 1km splits
        if parsed_points:
            total_distance = parsed_points[-1]["distance"]
            reconstructed_total_distance = total_distance
            overall_pace = format_pace(total_duration_summary, total_distance)
            
            valid_hrs = [p["hr"] for p in parsed_points if p["hr"] > 0]
            if valid_hrs:
                avg_hr = sum(valid_hrs) / len(valid_hrs)
                max_hr = max(valid_hrs)
            
            current_target_m = 1000.0
            start_pt = parsed_points[0]
            
            for p in parsed_points:
                # Boundary reached for the 1km split
                while p["distance"] >= current_target_m and current_target_m <= total_distance:
                    dist_delta = p["distance"] - start_pt["distance"]
                    time_delta = p["elapsed"] - start_pt["elapsed"]
                    
                    segment_hrs = [pt["hr"] for pt in parsed_points if start_pt["elapsed"] <= pt["elapsed"] <= p["elapsed"] and pt["hr"] > 0]
                    avg_hr_seg = int(sum(segment_hrs) / len(segment_hrs)) if segment_hrs else "N/A"
                    
                    splits.append({
                        "km": int(current_target_m / 1000),
                        "duration": time_delta,
                        "distance": dist_delta,
                        "pace": format_pace(time_delta, dist_delta),
                        "hr": avg_hr_seg
                    })
                    start_pt = p
                    current_target_m += 1000.0
            
            # Handle the last partial kilometer (if > 20m remainder)
            if start_pt["distance"] < total_distance:
                end_pt = parsed_points[-1]
                dist_delta = end_pt["distance"] - start_pt["distance"]
                if dist_delta > 20: 
                    time_delta = end_pt["elapsed"] - start_pt["elapsed"]
                    segment_hrs = [pt["hr"] for pt in parsed_points if start_pt["elapsed"] <= pt["elapsed"] <= end_pt["elapsed"] and pt["hr"] > 0]
                    avg_hr_seg = int(sum(segment_hrs) / len(segment_hrs)) if segment_hrs else "N/A"
                    
                    splits.append({
                        "km": f"{int(current_target_m / 1000)} (partiel)",
                        "duration": time_delta,
                        "distance": dist_delta,
                        "pace": format_pace(time_delta, dist_delta),
                        "hr": avg_hr_seg
                    })

    # 4. Generate Markdown
    if splits:
        markdown_splits = "\n## ⏱️ Temps de passage (Reconstruits du CSV)\n| Km | Temps | Allure | FC Moy |\n|---|---|---|---|\n"
        for s in splits:
            markdown_splits += f"| {s['km']} | {format_duration(s['duration'])} | **{s['pace']}** | {s['hr']} bpm |\n"
            
    csv_link = f"\n## 📁 Fichiers associés\n- Données brutes (CSV) : `{csv_filename.name}`" if csv_filename.exists() else ""
    
    note_content = f"""---
type: entrainement/garmin
date: {date_str}
id_garmin: {activity_id}
distance_km: {reconstructed_total_distance/1000:.2f}
allure_moyenne: "{overall_pace}"
---
# 🏃 {name}

## 📊 Résumé des Performances
- **Date :** {date_str}
- **Distance :** **{reconstructed_total_distance/1000:.2f} km**
- **Durée :** {format_duration(total_duration_summary)}
- **Allure moyenne :** **{overall_pace} min/km**
- **Cardio :** Moyenne {int(avg_hr) if avg_hr else 'N/A'} bpm | Max {int(max_hr) if max_hr else 'N/A'} bpm
{markdown_splits}{csv_link}
"""
    with open(md_filename, "w", encoding="utf-8") as f:
        f.write(note_content)
    print(f"✓ Markdown d'activité généré : {md_filename.name}")

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
                    process_activity_detailed(client, act, activity_dir)
            else:
                print("Aucune activité récente trouvée.")
        except Exception as e:
            print(f"Erreur lors de la récupération des activités : {e}")

        print("Garmin health metrics successfully fetched and saved.")

    except Exception as e:
        print(f"Error in Garmin client: {e}")

if __name__ == "__main__":
    fetch_and_save_metrics()
