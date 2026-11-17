"""GDELT, plan B : fichiers d'export d'événements (téléchargement direct, sans limite de débit).

Chaque événement est codé selon la nomenclature CAMEO (code racine 01 à 20). Pour chaque jour et chaque catégorie :
- vol  = part des mentions de presse consacrées aux événements de la catégorie (en %), ce qui neutralise
         la croissance du volume total de GDELT ;
- tone = ton moyen des articles, pondéré par les mentions.
Source : fichier quotidien GDELT 1.0 ; s'il manque, les 96 fichiers de 15 minutes de GDELT 2.0 du même jour.
Les colonnes utilisées ont la même position dans les deux formats.
"""
import datetime as dt
import io
import time
import zipfile

import numpy as np
import pandas as pd

V1 = "http://data.gdeltproject.org/events/{d}.export.CSV.zip"
V2 = "http://data.gdeltproject.org/gdeltv2/{d}{hm}00.export.CSV.zip"
# codes racines CAMEO : 03-06 coopération, 10-12 exigence, désaccord, rejet, 13 menace, 14 protestation,
# 15 démonstration de force, 16 réduction des relations (dont sanctions), 17 coercition, 18 agression, 19 combat,
# 20 violence de masse
CAT_ROOTS = {
    "militaire": {"15", "18", "19", "20"},
    "securitaire": {"13", "17"},
    "politique": {"03", "04", "05", "06", "10", "11", "12", "16"},
    "media": {"14"},
}
COLS = {10: "rel1", 20: "rel2", 25: "root", 28: "code", 31: "mentions", 34: "tone"}


def day_stats(frames):
    df = pd.concat(frames, ignore_index=True)
    df = df[df["root"] == "1"]
    m = pd.to_numeric(df["mentions"], errors="coerce").fillna(0.0)
    tone = pd.to_numeric(df["tone"], errors="coerce")
    tot = float(m.sum())
    if tot <= 0:
        return {}, 0
    code = df["code"].astype(str).str.zfill(2).str[:2]
    masks = {c: code.isin(r) for c, r in CAT_ROOTS.items()}
    masks["religieux"] = df["rel1"].notna() | df["rel2"].notna()  # au moins un acteur religieux
    out = {}
    for c, k in masks.items():
        w = m[k]
        if w.sum() > 0:
            t = tone[k]
            ok = t.notna()
            out[c] = (100 * float(w.sum()) / tot, float(np.average(t[ok], weights=w[ok])) if w[ok].sum() > 0 else None)
    return out, int(len(df))


def _read(content):
    zf = zipfile.ZipFile(io.BytesIO(content))
    df = pd.read_csv(zf.open(zf.namelist()[0]), sep="\t", header=None, usecols=list(COLS), dtype=str,
                     quoting=3, on_bad_lines="skip", encoding_errors="replace")
    return df.rename(columns=COLS)


def fetch_day(day, session):
    d = day.strftime("%Y%m%d")
    r = session.get(V1.format(d=d), timeout=120)
    if r.status_code == 200:
        return [_read(r.content)], "v1"
    frames = []
    for h in range(24):
        for mi in (0, 15, 30, 45):
            r = session.get(V2.format(d=d, hm=f"{h:02d}{mi:02d}"), timeout=60)
            if r.status_code == 200:
                frames.append(_read(r.content))
    return (frames, "v2") if len(frames) >= 80 else ([], f"incomplet ({len(frames)}/96)")


def collect(cfg, con):
    """Jours récents d'abord, puis historique à rebours jusqu'à `annees`, dans un budget de temps. Ne lève jamais."""
    import requests
    g = cfg.get("gdelt_events", {})
    if not g.get("enabled", True):
        return {}, []
    con.execute("CREATE TABLE IF NOT EXISTS ev_days(date TEXT PRIMARY KEY, n INTEGER, source TEXT)")
    done = {r[0] for r in con.execute("SELECT date FROM ev_days WHERE n > 0 OR source='absent'")}
    # les anciennes séries (interface de recherche) des mêmes catégories ont une autre échelle : on les retire
    keys = list(CAT_ROOTS) + ["religieux"]
    q = ",".join("?" * len(keys))
    con.execute(f"DELETE FROM gdelt WHERE kind='cat' AND key IN ({q}) AND date NOT IN (SELECT date FROM ev_days WHERE n > 0)", keys)
    for k in keys:  # signaux dérivés : recalculés à chaque passage par gdelt_to_scores
        con.execute("DELETE FROM scores WHERE id LIKE ?", (f"gd-cat-{k}-%",))
    today = dt.datetime.now(dt.timezone.utc).date()
    days = [today - dt.timedelta(days=k) for k in range(1, int(g.get("annees", 3) * 365) + 1)]
    todo = [d for d in days if d.isoformat() not in done]
    s = requests.Session()
    s.headers["User-Agent"] = "radar-bourse/0.4"
    t0, ok, errs, sources = time.time(), 0, [], {}
    for day in todo:
        if time.time() - t0 > g.get("budget_s", 900):
            break
        try:
            frames, src = fetch_day(day, s)
        except Exception as e:
            errs.append(f"{day} : {type(e).__name__}")
            if len(errs) >= 3 and ok == 0:
                break  # source injoignable : inutile d'insister
            continue
        if not frames:
            if (today - day).days > 3:  # au-delà de 3 jours, le fichier ne viendra plus
                con.execute("INSERT OR REPLACE INTO ev_days VALUES (?,?,?)", (day.isoformat(), 0, "absent"))
            continue
        stats, n = day_stats(frames)
        con.executemany("INSERT OR REPLACE INTO gdelt VALUES (?,?,?,?,?)",
                        [("cat", c, day.isoformat(), v, t) for c, (v, t) in stats.items()])
        con.execute("INSERT OR REPLACE INTO ev_days VALUES (?,?,?)", (day.isoformat(), n, src))
        con.commit()
        ok += 1
        sources[src] = sources.get(src, 0) + 1
    have = con.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM ev_days WHERE n > 0").fetchone()
    yesterday = (today - dt.timedelta(days=1)).isoformat()
    out = {"jours_acquis": ok, "sources": sources, "historique": {"jours": have[0], "du": have[1], "au": have[2]}}
    msgs = []
    if errs:
        msgs.append(f"GDELT événements : {len(errs)} échecs ({errs[0]})")
    if have[2] is None or have[2] < (today - dt.timedelta(days=3)).isoformat():
        msgs.append(f"GDELT événements : dernier jour disponible {have[2] or 'aucun'}")
    return out, msgs
