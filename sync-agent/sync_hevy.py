import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone
 
HEVY_BASE_URL = "https://api.hevyapp.com"
TEMPLATES_CACHE_PATH = Path("/app/.hevy_cache/exercise_templates.json")
 
 
def get_headers():
    api_key = os.getenv("HEVY_API_KEY")
    if not api_key:
        raise RuntimeError("HEVY_API_KEY manquant dans l'environnement.")
    return {"api-key": api_key}
 
 
def load_exercise_templates_cache():
    """Charge le cache local des exercise_templates (groupe musculaire, etc.)."""
    if TEMPLATES_CACHE_PATH.exists():
        with open(TEMPLATES_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}
 
 
def save_exercise_templates_cache(cache):
    TEMPLATES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATES_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
 
 
def fetch_exercise_template(template_id, cache, headers):
    """Récupère un template d'exercice (avec cache local pour limiter les appels API)."""
    if template_id in cache:
        return cache[template_id]
 
    resp = requests.get(
        f"{HEVY_BASE_URL}/v1/exercise_templates/{template_id}",
        headers=headers,
        timeout=15,
    )
    if resp.status_code != 200:
        return None
 
    template = resp.json()
    cache[template_id] = template
    return template
 
 
def format_duration_hms(seconds):
    if not seconds or seconds < 0:
        return "0min"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}s" if secs else f"{minutes}min"
 
 
def parse_iso_datetime(dt_str):
    # Hevy renvoie des dates ISO 8601, ex: "2026-08-10T18:32:00Z"
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
 
 
def build_markdown(workout, cache, headers):
    workout_id = workout["id"]
    title = workout.get("title", "Séance musculation")
    start_dt = parse_iso_datetime(workout["start_time"])
    end_dt = parse_iso_datetime(workout["end_time"])
    date_str = start_dt.strftime("%Y-%m-%d")
    duration_seconds = (end_dt - start_dt).total_seconds()
 
    total_volume_kg = 0.0
    total_sets = 0
    muscle_groups_touched = set()
    exercises_md = []
 
    for exercise in workout.get("exercises", []):
        ex_title = exercise.get("title", "Exercice inconnu")
        template_id = exercise.get("exercise_template_id")
        template = fetch_exercise_template(template_id, cache, headers) if template_id else None
        muscle_group = None
        if template:
            muscle_group = template.get("primary_muscle_group") or template.get("muscle_group")
            if muscle_group:
                muscle_groups_touched.add(muscle_group)
 
        sets = exercise.get("sets", [])
        set_lines = []
        for s in sets:
            total_sets += 1
            set_type = s.get("set_type", "normal")
            weight = s.get("weight_kg")
            reps = s.get("reps")
            distance = s.get("distance_meters")
            duration = s.get("duration_seconds")
 
            if weight is not None and reps is not None:
                total_volume_kg += weight * reps
                tag = "" if set_type == "normal" else f" ({set_type})"
                set_lines.append(f"{reps} reps @ {weight}kg{tag}")
            elif reps is not None:
                set_lines.append(f"{reps} reps")
            elif distance is not None and duration is not None:
                set_lines.append(f"{distance}m en {format_duration_hms(duration)}")
            elif duration is not None:
                set_lines.append(format_duration_hms(duration))
 
        muscle_tag = f" _{muscle_group}_" if muscle_group else ""
        exercises_md.append(f"### {ex_title}{muscle_tag}\n" + "\n".join(f"- {line}" for line in set_lines))
 
    exercises_block = "\n\n".join(exercises_md)
    muscle_groups_str = ", ".join(sorted(muscle_groups_touched)) if muscle_groups_touched else "N/A"
 
    note_content = f"""---
date: {date_str}
type: musculation
id_hevy: {workout_id}
titre: "{title}"
duree_minutes: {int(duration_seconds / 60)}
volume_total_kg: {int(total_volume_kg)}
nb_series: {total_sets}
groupes_musculaires: "{muscle_groups_str}"
---
# 🏋️ Musculation : {title}
 
## 📊 Résumé
- **Date :** {date_str}
- **Durée :** {format_duration_hms(duration_seconds)}
- **Volume total :** {int(total_volume_kg)} kg
- **Nombre de séries :** {total_sets}
- **Groupes musculaires :** {muscle_groups_str}
 
## 💪 Détail des exercices
 
{exercises_block}
"""
    return note_content, workout_id, date_str
 
 
def main():
    output_dir = Path("/app/vault/Entrainements")
    output_dir.mkdir(parents=True, exist_ok=True)
 
    headers = get_headers()
    cache = load_exercise_templates_cache()
 
    print("Connexion à Hevy API...")
    resp = requests.get(
        f"{HEVY_BASE_URL}/v1/workouts",
        headers=headers,
        params={"page": 1, "pageSize": 1},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
 
    workouts = data.get("workouts", [])
    if not workouts:
        print("Aucun entraînement trouvé.")
        return
 
    workout = workouts[0]
    note_content, workout_id, date_str = build_markdown(workout, cache, headers)
 
    md_filename = output_dir / f"Muscu_{date_str}_{workout_id}.md"
 
    if md_filename.exists():
        print(f"✓ Note déjà existante, rien à faire ({md_filename.name}).")
    else:
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(note_content)
        print(f"✓ Note Markdown générée : {md_filename.name}")
 
    save_exercise_templates_cache(cache)
 
 
if __name__ == "__main__":
    main()
