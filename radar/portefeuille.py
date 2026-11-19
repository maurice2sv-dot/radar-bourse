"""Portefeuille fictif : application mécanique et sans argent réel de règles fixées à l'avance.

Deux règles suivies côte à côte, mêmes frais et mêmes dates :
- « radar » : les 20 % de valeurs les mieux classées par le modèle (probabilité à 5 séances) ;
- « momentum » : les 20 % de valeurs qui ont le plus monté sur 12 mois hors dernier mois (règle naïve) ;
  si le modèle ne fait pas mieux que cette règle simple, sa complexité ne sert à rien.
Mécanique commune : parts égales ; tous les 5 séances, une valeur détenue reste tant qu'elle figure dans les
40 % les mieux classées (règle de maintien, qui réduit les frais), les places libres vont aux mieux classées ;
frais de 10 points de base par sens sur la part réellement échangée ; exécution au cours de clôture du signal.
Références : moyenne des valeurs de l'univers à parts égales, S&P 500 (SPY) et Stoxx Europe 600 (EXSA.DE).
Par profil de risque (tiers de volatilité, voir risque.py) : « radar_prudent », « radar_équilibré »,
« radar_dynamique », chacune jugée contre la moyenne de son profil (composition figée à chaque revue).
Les rendements sont pris en devise locale, sans conversion.
Toute modification de règle remet le compteur à zéro (supprimer data/portefeuille.json).
"""
import json
import pathlib

import numpy as np

PART = 0.20
MAINTIEN = 0.40
DUREE = 5
VERSION = 3
PROFILS = ("prudent", "équilibré", "dynamique")
STRATS = ("radar", "momentum") + tuple(f"radar_{p}" for p in PROFILS)
# règles par profil : le classement du radar appliqué à l'intérieur de chaque tiers de volatilité,
# jugé contre la moyenne de ce même tiers (une valeur prudente ne se compare pas à une valeur dynamique)


def _load(path):
    try:
        st = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        return st if st.get("version") == VERSION else None
    except Exception:
        return None


def _choix(scores, held, n):
    order = [t for t, _ in sorted(scores.items(), key=lambda x: -x[1])]
    keep = set(held) & set(order[:int(round(len(order) * MAINTIEN))])
    new = list(keep) + [t for t in order if t not in keep][:n - len(keep)]
    return {t: 1.0 / len(new) for t in new} if new else {}


def momentum_scores(close, member, run_date):
    """Tendance 12 mois hors dernier mois, pour les valeurs de l'univers à la date du signal."""
    px = close.ffill(limit=3)
    i = px.index.get_indexer([np.datetime64(run_date)])[0]
    if i < 252:
        return {}
    m = px.iloc[i - 21] / px.iloc[i - 252] - 1
    if member is not None:
        m = m[member.iloc[i].reindex(m.index).fillna(False).astype(bool)]
    return {t: float(v) for t, v in m.dropna().items()}


def update(close, all_p5, run_date, path, cout_bps=10, member=None, macro=None, refs=None, profils=None):
    """profils : {ticker: 'prudent' | 'équilibré' | 'dynamique'} à la date du signal."""
    path = pathlib.Path(path)
    st = _load(path)
    px = close.ffill(limit=3)
    cm = px.where(member.reindex(index=px.index, columns=px.columns).fillna(False).astype(bool)) if member is not None else px
    keys = [d.strftime("%Y-%m-%d") for d in px.index]
    pos = {d: i for i, d in enumerate(keys)}
    refs = refs or {}
    mac = macro.reindex(columns=list(refs.values())).ffill(limit=5) if macro is not None and len(macro) else None
    if st is None:
        st = {"version": VERSION, "debut": run_date, "derniere_date": run_date,
              "regle": (f"{int(PART * 100)} % les mieux classées, parts égales, revues toutes les {DUREE} séances, "
                        f"maintien tant qu'elles restent dans les {int(MAINTIEN * 100)} % premières, frais {cout_bps} pb par sens"),
              "strats": {s: {"valeur": 100.0, "lignes": {}, "frais": 0.0, "periodes": [], "periode_debut": None}
                         for s in STRATS},
              "refs": {"moyenne": 100.0, **{k: 100.0 for k in refs}, **{f"moyenne_{p}": 100.0 for p in PROFILS}},
              "groupes": {},
              "seances_depuis": 0, "historique": []}

    # 1. Faire vivre les positions et les références sur les séances écoulées
    jours = [d for d in keys if st["derniere_date"] < d <= run_date]
    prev = st["derniere_date"]
    for d in jours:
        if prev not in pos:
            prev = d
            continue
        r = (px.iloc[pos[d]] / px.iloc[pos[prev]] - 1).replace([np.inf, -np.inf], np.nan)
        rm = (cm.iloc[pos[d]] / cm.iloc[pos[prev]] - 1).replace([np.inf, -np.inf], np.nan)
        st["refs"]["moyenne"] *= 1 + float(np.nanmean(rm.values)) if rm.notna().any() else 1
        for p, grp in st.get("groupes", {}).items():
            g = r.reindex(grp).dropna()
            if len(g):
                st["refs"][f"moyenne_{p}"] *= 1 + float(g.mean())
        if mac is not None:
            for k, sym in refs.items():
                try:
                    a, b = mac.asof(np.datetime64(prev))[sym], mac.asof(np.datetime64(d))[sym]
                    if a == a and b == b and a > 0:
                        st["refs"][k] *= b / a
                except Exception:
                    pass
        tenu = False
        for s in STRATS:
            S = st["strats"][s]
            w = S["lignes"]
            if not w:
                continue
            tenu = True
            rr = {t: (0.0 if t not in r.index or r[t] != r[t] else float(r[t])) for t in w}
            rp = sum(x * rr[t] for t, x in w.items())
            S["lignes"] = {t: x * (1 + rr[t]) / (1 + rp) for t, x in w.items()}
            S["valeur"] *= 1 + rp
        if tenu:
            st["seances_depuis"] += 1
        st["historique"].append({"date": d, **{s: round(st["strats"][s]["valeur"], 4) for s in STRATS},
                                 **{k: round(v, 4) for k, v in st["refs"].items()}})
        prev = d
    st["derniere_date"] = max(st["derniere_date"], run_date)

    # 2. Revue des lignes (premier passage, puis toutes les DUREE séances)
    vide = not any(st["strats"][s]["lignes"] for s in STRATS)
    if (vide or st["seances_depuis"] >= DUREE) and all_p5:
        p5 = {x["ticker"]: x["p5"] for x in all_p5}
        scores = {"radar": p5, "momentum": momentum_scores(close, member, run_date)}
        if profils:
            st["groupes"] = {p: sorted(t for t in p5 if profils.get(t) == p) for p in PROFILS}
            for p in PROFILS:
                scores[f"radar_{p}"] = {t: p5[t] for t in st["groupes"][p]}
        for s in STRATS:
            S, sc = st["strats"][s], scores.get(s) or {}
            if not sc:
                continue
            ref = f"moyenne_{s[6:]}" if s.startswith("radar_") else "moyenne"
            n = max(1, round(len(sc if s.startswith("radar_") else all_p5) * PART))
            if S["periode_debut"]:
                S["periodes"].append({"debut": S["periode_debut"]["date"], "fin": run_date,
                                      "pf": S["valeur"] / S["periode_debut"]["valeur"] - 1,
                                      "moy": st["refs"][ref] / S["periode_debut"]["moyenne"] - 1})
            cible = _choix(sc, S["lignes"], n)
            tk = set(cible) | set(S["lignes"])
            rot = sum(abs(cible.get(t, 0.0) - S["lignes"].get(t, 0.0)) for t in tk)
            S["valeur"] *= 1 - rot * cout_bps / 1e4
            S["frais"] += rot * cout_bps / 1e4
            S["lignes"] = cible
            S["rotation"] = round(rot / 2, 3)
            S["periode_debut"] = {"date": run_date, "valeur": S["valeur"], "moyenne": st["refs"][ref]}
        st["seances_depuis"] = 0
        st["noms"] = {x["ticker"]: x["name"] for x in all_p5}
    st["historique"] = st["historique"][-400:]
    path.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return resume(st)


def resume(st):
    h = st["historique"]
    noms = st.get("noms", {})
    out = {"debut": st["debut"], "seances": len(h), "regle": st["regle"],
           "prochaine_revue": max(0, DUREE - st["seances_depuis"]),
           "refs": {k: v / 100 - 1 for k, v in st["refs"].items()}, "strats": {}}
    for s in STRATS:
        S = st["strats"][s]
        vals = np.array([100.0] + [x[s] for x in h])
        per = S["periodes"]
        ref = f"moyenne_{s[6:]}" if s.startswith("radar_") else "moyenne"
        sem = None
        if len(h) >= 6 and s in h[-6] and ref in h[-6]:
            sem = {"pf": h[-1][s] / h[-6][s] - 1, "moy": h[-1][ref] / h[-6][ref] - 1}
        out["strats"][s] = {"perf": S["valeur"] / 100 - 1, "pire_baisse": float((vals / np.maximum.accumulate(vals) - 1).min()),
                            "frais": S["frais"], "n_lignes": len(S["lignes"]), "rotation": S.get("rotation"),
                            "lignes": [noms.get(t, t) for t, _ in sorted(S["lignes"].items(), key=lambda x: -x[1])[:5]],
                            "periodes": len(per), "gagnees": sum(1 for p in per if p["pf"] > p["moy"]), "semaine": sem,
                            "ref": st["refs"].get(ref, 100.0) / 100 - 1}
    return out
