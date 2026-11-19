"""Portefeuille fictif : application mécanique et sans argent réel de la règle du radar.

Règle (fixée à l'avance, ne pas modifier en cours de route sans remettre le compteur à zéro) :
- détenir à parts égales les 20 % de valeurs les mieux classées (probabilité à 5 séances) ;
- garder les lignes 5 séances, puis renouveler la sélection ;
- frais de 10 points de base par sens (achat ou vente) sur la part réellement échangée ;
- prix d'exécution : cours de clôture du jour du signal.
Référence : toutes les valeurs suivies à parts égales (la « moyenne » que le modèle cherche à battre).
Les rendements sont pris en devise locale (dollar, euro...), sans conversion.
"""
import json
import pathlib

import numpy as np

PART = 0.20
DUREE = 5


def _load(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def update(close, all_p5, run_date, path, cout_bps=10):
    path = pathlib.Path(path)
    st = _load(path)
    px = close.ffill()
    px.index = [d.strftime("%Y-%m-%d") for d in px.index]
    if st is None:
        st = {"regle": f"{int(PART * 100)} % les mieux classées, parts égales, renouvelées toutes les {DUREE} séances, "
                       f"frais {cout_bps} pb par sens",
              "debut": run_date, "derniere_date": run_date, "valeur": 100.0, "indice": 100.0,
              "lignes": {}, "seances_depuis": 0, "historique": [], "periodes": [], "periode_debut": None,
              "frais_cumules": 0.0}

    # 1. Faire vivre les positions sur les séances écoulées depuis le dernier passage
    jours = [d for d in px.index if st["derniere_date"] < d <= run_date]
    prev = st["derniere_date"]
    for d in jours:
        if prev not in px.index:
            prev = d
            continue
        r = (px.loc[d] / px.loc[prev] - 1).replace([np.inf, -np.inf], np.nan)
        r_ind = float(r.mean(skipna=True))
        w = {t: x for t, x in st["lignes"].items() if t in r.index}
        r_pf = sum(x * (0.0 if np.isnan(r[t]) else float(r[t])) for t, x in w.items())
        if w:
            st["lignes"] = {t: x * (1 + (0.0 if np.isnan(r[t]) else float(r[t]))) / (1 + r_pf) for t, x in w.items()}
            st["valeur"] *= 1 + r_pf
            st["seances_depuis"] += 1
        st["indice"] *= 1 + r_ind
        st["historique"].append({"date": d, "valeur": round(st["valeur"], 4), "indice": round(st["indice"], 4)})
        prev = d
    st["derniere_date"] = max(st["derniere_date"], run_date)

    # 2. Renouvellement de la sélection (au premier passage, puis toutes les DUREE séances)
    if (not st["lignes"] or st["seances_depuis"] >= DUREE) and all_p5:
        if st["periode_debut"]:
            st["periodes"].append({"debut": st["periode_debut"]["date"], "fin": run_date,
                                   "pf": st["valeur"] / st["periode_debut"]["valeur"] - 1,
                                   "ind": st["indice"] / st["periode_debut"]["indice"] - 1})
        n = max(1, round(len(all_p5) * PART))
        cible = {x["ticker"]: 1.0 / n for x in sorted(all_p5, key=lambda x: -x["p5"])[:n]}
        tickers = set(cible) | set(st["lignes"])
        rotation = sum(abs(cible.get(t, 0.0) - st["lignes"].get(t, 0.0)) for t in tickers)
        frais = rotation * cout_bps / 1e4
        st["valeur"] *= 1 - frais
        st["frais_cumules"] += frais
        st["lignes"], st["seances_depuis"] = cible, 0
        st["periode_debut"] = {"date": run_date, "valeur": st["valeur"], "indice": st["indice"]}
        st["dernier_renouvellement"] = {"date": run_date, "rotation": round(rotation / 2, 3)}
        st["noms"] = {x["ticker"]: x["name"] for x in all_p5}
    st["historique"] = st["historique"][-400:]
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return resume(st)


def resume(st):
    h = st["historique"]
    vals = np.array([100.0] + [x["valeur"] for x in h])
    dd = float((vals / np.maximum.accumulate(vals) - 1).min()) if len(vals) else 0.0
    sem = None
    if len(h) >= 6:
        a, b = h[-6], h[-1]
        sem = {"pf": b["valeur"] / a["valeur"] - 1, "ind": b["indice"] / a["indice"] - 1}
    per = st["periodes"]
    noms = st.get("noms", {})
    top = sorted(st["lignes"].items(), key=lambda x: -x[1])
    return {"debut": st["debut"], "seances": len(h), "perf": st["valeur"] / 100 - 1, "indice": st["indice"] / 100 - 1,
            "pire_baisse": dd, "frais": st["frais_cumules"], "n_lignes": len(st["lignes"]),
            "lignes": [noms.get(t, t) for t, _ in top[:5]], "regle": st["regle"],
            "periodes": len(per), "periodes_gagnees": sum(1 for p in per if p["pf"] > p["ind"]),
            "semaine": sem, "prochain_renouvellement": max(0, DUREE - st["seances_depuis"]),
            "rotation": (st.get("dernier_renouvellement") or {}).get("rotation")}
