import os
import csv
from pathlib import Path
from garminconnect import Garmin

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
    """Cherche le premier index valide (y compris 0) parmi une liste de clés possibles."""
    for k in keys:
        idx = metrics_map.get(k)
        if idx is not None:
            return idx
    return None

def main():
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    token_dir = "/app/.garminconnect"
    os.makedirs(token_dir, exist_ok=True)
    
    output_dir = Path("/app/vault/Entrainements")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("Connexion à Garmin Connect...")
    try:
        client = Garmin(email, password)
        client.login(token_dir)
        
        activities = client.get_activities(0, 1)
        if not activities: 
            print("Aucune activité trouvée.")
            return
            
        activity = activities[0]
        activity_id = activity["activityId"]
        title = activity["activityName"]
        date_str = activity["startTimeLocal"].split(" ")[0]
        total_duration_summary = activity.get("duration", 0)
        
        csv_filename = output_dir / f"Course_{date_str}_{activity_id}_brut.csv"
        md_filename = output_dir / f"Course_{date_str}_{activity_id}.md"
        
        # 1. Téléchargement et écriture du CSV s'il n'existe pas
        if not csv_filename.exists():
            print(f"Téléchargement des données brutes depuis Garmin : {title} ({date_str})...")
            details = client.get_activity_details(activity_id)
            metrics_map = {}
            if details and "metricDescriptors" in details:
                for desc in details["metricDescriptors"]:
                    metrics_map[desc["key"]] = desc["metricsIndex"]

            # Debug : décommenter si besoin de vérifier les clés exposées par Garmin
            # print("Clés disponibles :", list(metrics_map.keys()))

            raw_metrics = details.get("activityDetailMetrics", [])
            if not raw_metrics:
                print("❌ Aucune télémétrie trouvée.")
                return

            time_idx = find_metric_index(metrics_map, ["directTimestamp", "timestamp", "time"])
            dist_idx = find_metric_index(metrics_map, ["sumDistance", "directDistance", "distance"])
            speed_idx = find_metric_index(metrics_map, ["directSpeed", "speed"])
            hr_idx = find_metric_index(metrics_map, ["directHeartRate", "heartRate"])
            alt_idx = find_metric_index(metrics_map, ["directElevation", "elevation", "altitude"])

            with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["timestamp", "distance_m", "speed_ms", "heart_rate", "altitude_m"])
                
                for point in raw_metrics:
                    m = point.get("metrics", [])
                    t = m[time_idx] if time_idx is not None and len(m) > time_idx else 0
                    d = m[dist_idx] if dist_idx is not None and len(m) > dist_idx else 0
                    s = m[speed_idx] if speed_idx is not None and len(m) > speed_idx else 0
                    hr = m[hr_idx] if hr_idx is not None and len(m) > hr_idx else 0
                    alt = m[alt_idx] if alt_idx is not None and len(m) > alt_idx else 0
                    writer.writerow([t, d, s, hr, alt])
            print(f"✓ Fichier CSV généré : {csv_filename.name}")
        else:
            print(f"✓ Utilisation du CSV existant ({csv_filename.name}).")

        # 2. Lecture du CSV et reconstruction temporelle à partir du VRAI timestamp
        raw_rows = []
        with open(csv_filename, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                raw_rows.append(row)

        if not raw_rows:
            print("❌ Erreur : CSV vide.")
            return

        # Détection auto du format du timestamp (ms epoch vs secondes epoch vs déjà relatif)
        first_ts_raw = float(raw_rows[0]["timestamp"]) if raw_rows[0]["timestamp"] else 0.0
        # Un epoch en secondes (~1.7e9 en 2024+) est bien plus petit qu'un epoch en ms (~1.7e12)
        ts_is_milliseconds = first_ts_raw > 1e12

        parsed_points = []
        first_ts = None
        for row in raw_rows:
            ts = float(row["timestamp"]) if row["timestamp"] else 0.0
            if first_ts is None:
                first_ts = ts
            delta = ts - first_ts
            elapsed = delta / 1000.0 if ts_is_milliseconds else delta

            parsed_points.append({
                "elapsed": elapsed,
                "distance": float(row["distance_m"]) if row["distance_m"] else 0.0,
                "speed": float(row["speed_ms"]) if row["speed_ms"] else 0.0,
                "hr": float(row["heart_rate"]) if row["heart_rate"] else 0.0,
            })

        # Garde-fou : vérifie que la durée totale reconstruite est cohérente avec celle de Garmin
        reconstructed_total = parsed_points[-1]["elapsed"] - parsed_points[0]["elapsed"]
        if total_duration_summary and reconstructed_total > 0:
            ecart = abs(reconstructed_total - total_duration_summary) / total_duration_summary
            if ecart > 0.05:  # plus de 5% d'écart = suspect
                print(f"⚠️  Attention : durée reconstruite ({reconstructed_total:.0f}s) vs officielle Garmin ({total_duration_summary}s) — écart de {ecart*100:.1f}%. Vérifie le format du timestamp.")

        if not parsed_points:
            print("❌ Erreur : CSV vide.")
            return

        total_distance = parsed_points[-1]["distance"]
        valid_hrs = [p["hr"] for p in parsed_points if p["hr"] > 0]
        avg_hr = sum(valid_hrs) / len(valid_hrs) if valid_hrs else 0
        max_hr = max(valid_hrs) if valid_hrs else 0
        overall_pace = format_pace(total_duration_summary, total_distance)

        # 3. Découpage propre par tranches de 1000 mètres
        splits = []
        current_target_m = 1000.0
        start_pt = parsed_points[0]
        
        for p in parsed_points:
            while p["distance"] >= current_target_m and current_target_m <= total_distance:
                end_pt = p
                dist_delta = end_pt["distance"] - start_pt["distance"]
                time_delta = end_pt["elapsed"] - start_pt["elapsed"]
                
                segment_hrs = [pt["hr"] for pt in parsed_points if start_pt["elapsed"] <= pt["elapsed"] <= end_pt["elapsed"] and pt["hr"] > 0]
                avg_hr_seg = int(sum(segment_hrs) / len(segment_hrs)) if segment_hrs else "N/A"
                
                splits.append({
                    "km": int(current_target_m / 1000),
                    "duration": time_delta,
                    "distance": dist_delta,
                    "pace": format_pace(time_delta, dist_delta),
                    "hr": avg_hr_seg
                })
                
                start_pt = end_pt
                current_target_m += 1000.0

        # Gestion du dernier kilomètre partiel (ex: les 600 derniers mètres d'un 14.6km)
        if start_pt["distance"] < total_distance:
            end_pt = parsed_points[-1]
            dist_delta = end_pt["distance"] - start_pt["distance"]
            if dist_delta > 20: # Ignorer les micro-résidus de fin
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

        markdown_splits = "| Km | Temps | Allure | FC Moy |\n|---|---|---|---|\n"
        for s in splits:
            markdown_splits += f"| {s['km']} | {format_duration(s['duration'])} | **{s['pace']}** | {s['hr']} bpm |\n"

        # 4. Écriture du Markdown Synthétique
        note_content = f"""---
type: entrainement/course
date: {date_str}
id_garmin: {activity_id}
allure_moyenne: "{overall_pace}"
distance_km: {total_distance/1000:.2f}
---
# 🏃 Course : {title}

## 📊 Résumé des Performances
- **Date :** {date_str}
- **Distance :** **{total_distance/1000:.2f} km**
- **Durée :** {format_duration(total_duration_summary)}
- **Allure moyenne :** **{overall_pace} min/km**
- **Cardio :** Moyenne {int(avg_hr)} bpm | Max {int(max_hr)} bpm

## ⏱️ Temps de passage (Reconstruits du CSV)
{markdown_splits}

## 📁 Fichiers associés
- Données brutes (CSV) : `{csv_filename.name}`
"""
        
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(note_content)
            
        print(f"✓ Markdown mis à jour avec des splits corrects : {md_filename.name}")
        
    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    main()