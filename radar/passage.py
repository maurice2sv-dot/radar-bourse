"""Garde des passages : décide si un passage du radar est dû, sans la base ni pandas.

Les horaires planifiés de GitHub sont indicatifs : départs retardés de 5 à 8 h, et certains jamais lancés
(lundi 23/11/2026 : ni le passage de 08h07 ni celui de 22h37). Le workflow se déclenche donc toutes les heures,
et ce module dit si le créneau en cours a déjà été traité :
- créneau « soir » : après la clôture de New York (22h UTC, marge comprise), du lundi au vendredi ;
- créneau « jour » : après la clôture de l'Asie (7h UTC), du lundi au vendredi ;
- la nuit et le week-end prolongent le dernier créneau du soir (vendredi soir jusqu'au lundi 7h).
Un créneau traité est noté dans data/passage.json : les déclenchements suivants s'arrêtent en quelques secondes.
"""
import datetime as dt
import json
import os
import pathlib
import sys

SOIR_H, JOUR_H = 22, 7


def creneau(now=None):
    """Clé du créneau en cours, par exemple « 2026-11-23/soir »."""
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    d = now.date()
    if d.weekday() < 5 and now.hour >= SOIR_H:
        return f"{d}/soir"
    if d.weekday() < 5 and now.hour >= JOUR_H:
        return f"{d}/jour"
    d -= dt.timedelta(days=1)  # nuit ou week-end : dernier soir de bourse
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return f"{d}/soir"


def fait(root):
    p = pathlib.Path(root) / "data" / "passage.json"
    try:
        return json.loads(p.read_text()).get("creneau")
    except Exception:
        return None


def noter(root, cle, now=None):
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    p = pathlib.Path(root) / "data" / "passage.json"
    p.write_text(json.dumps({"creneau": cle, "fin_utc": now.strftime("%Y-%m-%d %H:%M")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[1]
    if sys.argv[1:] == ["noter"]:
        noter(root, os.environ.get("RADAR_CRENEAU") or creneau())
        sys.exit(0)
    cle, deja = creneau(), fait(root)
    force = os.environ.get("RADAR_FORCE") == "true"
    go = force or cle != deja
    print(f"créneau {cle}, dernier traité {deja}, passage {'dû' if go else 'déjà fait'}" + (" (lancement manuel)" if force else ""))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"go={'true' if go else 'false'}\ncreneau={cle}\n")
