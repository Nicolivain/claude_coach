import csv
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Chemin où tu déposes le CSV exporté manuellement depuis l'app Hevy
# (Profil > Paramètres > Export & Import Data > Export Workouts)
# Astuce : configure Syncthing / Nextcloud / un dossier partagé pour que
# le fichier atterrisse ici automatiquement depuis ton téléphone.
CSV_IMPORT_PATH = Path("/app/vault/hevy_imports/hevy_export.csv")
OUTPUT_DIR = Path("/app/vault/Entrainements")

LBS_TO_KG = 0.453592
MILES_TO_KM = 1.60934


FR_MONTHS = {
    "janv.": "01", "févr.": "02", "mars": "03", "avr.": "04",
    "mai": "05", "juin": "06", "juil.": "07", "août": "08",
    "sept.": "09", "oct.": "10", "nov.": "11", "déc.": "12",
}


def parse_hevy_datetime(value):
    """Gère les formats FR et EN rencontrés dans les exports Hevy."""
    value = value.strip()

    # Format FR : "25 juil. 2026, 10:32"
    match = re.match(r"(\d{1,2}) (\S+) (\d{4}), (\d{2}):(\d{2})", value)
    if match:
        day, month_fr, year, hour, minute = match.groups()
        month_num = FR_MONTHS.get(month_fr.lower())
        if month_num:
            return datetime(int(year), int(month_num), int(day), int(hour), int(minute))

    formats = [
        "%d %b %Y, %H:%M",   # ex: "22 Dec 2025, 08:00"
        "%Y-%m-%d %H:%M:%S", # ex: "2024-01-15 10:00:00"
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Format de date non reconnu : {value}")


def slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def format_duration_hms(seconds):
    if not seconds or seconds < 0:
        return "0min"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}min {secs}s" if secs else f"{minutes}min"


def detect_units(fieldnames):
    """Détecte si le CSV utilise kg/km ou lbs/miles."""
    weight_field = "weight_kg" if "weight_kg" in fieldnames else "weight_lbs"
    distance_field = "distance_km" if "distance_km" in fieldnames else "distance_miles"
    return weight_field, distance_field


def to_kg(value, weight_field):
    if not value:
        return None
    value = float(value)
    return value if weight_field == "weight_kg" else value * LBS_TO_KG


def load_workouts_from_csv(csv_path):
    """Regroupe les lignes du CSV par séance (title + start_time + end_time)."""
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        weight_field, distance_field = detect_units(reader.fieldnames)

        workouts = defaultdict(lambda: {"exercises": defaultdict(list)})
        for row in reader:
            key = (row["title"], row["start_time"], row["end_time"])
            w = workouts[key]
            w["title"] = row["title"]
            w["start_time"] = row["start_time"]
            w["end_time"] = row["end_time"]
            w["exercises"][row["exercise_title"]].append({
                "set_type": row.get("set_type") or "normal",
                "weight_kg": to_kg(row.get(weight_field), weight_field),
                "reps": int(row["reps"]) if row.get("reps") else None,
                "duration_seconds": float(row["duration_seconds"]) if row.get("duration_seconds") else None,
                "rpe": row.get("rpe") or None,
            })
        return workouts


def build_markdown(workout):
    start_dt = parse_hevy_datetime(workout["start_time"])
    end_dt = parse_hevy_datetime(workout["end_time"])
    date_str = start_dt.strftime("%Y-%m-%d")
    duration_seconds = (end_dt - start_dt).total_seconds()
    title = workout["title"] or "Séance musculation"

    total_volume_kg = 0.0
    total_sets = 0
    exercises_md = []

    for exercise_title, sets in workout["exercises"].items():
        set_lines = []
        for s in sets:
            total_sets += 1
            if s["weight_kg"] is not None and s["reps"] is not None:
                total_volume_kg += s["weight_kg"] * s["reps"]
                tag = "" if s["set_type"] == "normal" else f" ({s['set_type']})"
                rpe_tag = f" @RPE {s['rpe']}" if s["rpe"] else ""
                set_lines.append(f"{s['reps']} reps @ {s['weight_kg']:.1f}kg{tag}{rpe_tag}")
            elif s["reps"] is not None:
                set_lines.append(f"{s['reps']} reps")
            elif s["duration_seconds"] is not None:
                set_lines.append(format_duration_hms(s["duration_seconds"]))
        exercises_md.append(f"### {exercise_title}\n" + "\n".join(f"- {line}" for line in set_lines))

    exercises_block = "\n\n".join(exercises_md)
    workout_slug = f"{date_str}_{slugify(title)}_{start_dt.strftime('%H%M')}"

    note_content = f"""---
date: {date_str}
type: musculation
titre: "{title}"
duree_minutes: {int(duration_seconds / 60)}
volume_total_kg: {int(total_volume_kg)}
nb_series: {total_sets}
---
# 🏋️ Musculation : {title}

## 📊 Résumé
- **Date :** {date_str}
- **Durée :** {format_duration_hms(duration_seconds)}
- **Volume total :** {int(total_volume_kg)} kg
- **Nombre de séries :** {total_sets}

## 💪 Détail des exercices

{exercises_block}
"""
    return note_content, workout_slug


def main():
    if not CSV_IMPORT_PATH.exists():
        print(f"❌ Aucun fichier trouvé à {CSV_IMPORT_PATH}. Dépose ton export Hevy à cet emplacement.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Lecture de {CSV_IMPORT_PATH.name}...")
    workouts = load_workouts_from_csv(CSV_IMPORT_PATH)

    created, skipped = 0, 0
    for workout in workouts.values():
        note_content, workout_slug = build_markdown(workout)
        md_filename = OUTPUT_DIR / f"Muscu_{workout_slug}.md"

        if md_filename.exists():
            skipped += 1
            continue

        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(note_content)
        created += 1
        print(f"✓ Note créée : {md_filename.name}")

    print(f"\nTerminé : {created} nouvelle(s) note(s), {skipped} déjà existante(s) ignorée(s).")


if __name__ == "__main__":
    main()
