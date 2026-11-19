"""Profil de risque de chaque valeur, mesuré sur ses cours (le risque se prévoit mieux que le rendement).

- volatilité : écart-type des variations quotidiennes sur un an, annualisé ;
- bêta : sensibilité aux mouvements de la moyenne des valeurs de l'univers (1 = suit le marché) ;
- pire baisse : plus forte chute depuis un sommet sur un an ;
- profil : tiers de l'univers du jour selon la volatilité (prudent, équilibré, dynamique).
Il s'agit d'un profil de valeur, pas d'un profil d'investisseur.
"""
import numpy as np
import pandas as pd

PROFILS = ("prudent", "équilibré", "dynamique")
FENETRE = 252


def metrics(close, member=None, min_obs=120):
    px = close.ffill(limit=3).tail(FENETRE + 1)
    r = px.pct_change(fill_method=None).iloc[1:]
    if member is not None:
        mm = member.reindex(index=r.index, columns=r.columns).fillna(False).astype(bool)
        mkt = r.where(mm).mean(axis=1)
        actifs = [t for t in r.columns if bool(member.iloc[-1].get(t, False))]
    else:
        mkt, actifs = r.mean(axis=1), list(r.columns)
    out = {}
    vm = mkt.var()
    for t in actifs:
        s = r[t]
        ok = s.notna() & mkt.notna()
        if ok.sum() < min_obs:
            continue
        p = px[t].dropna()
        out[t] = {"vol": float(s[ok].std() * np.sqrt(252)),
                  "beta": float(np.cov(s[ok], mkt[ok])[0, 1] / vm) if vm > 0 else float("nan"),
                  "dd": float((p / p.cummax() - 1).min())}
    if not out:
        return {}
    v = pd.Series({t: x["vol"] for t, x in out.items()})
    q1, q2 = v.quantile(1 / 3), v.quantile(2 / 3)
    for t, x in out.items():
        x["profil"] = PROFILS[0] if x["vol"] <= q1 else PROFILS[1] if x["vol"] <= q2 else PROFILS[2]
    return out


def par_profil(risque, all_p5, k=3):
    """Valeurs les mieux classées dans chaque profil, avec leur rang dans l'univers entier."""
    rang = {x["ticker"]: i + 1 for i, x in enumerate(sorted(all_p5, key=lambda x: -x["p5"]))}
    out = {}
    for p in PROFILS:
        membres = [x for x in all_p5 if risque.get(x["ticker"], {}).get("profil") == p]
        vols = [risque[x["ticker"]]["vol"] for x in membres]
        top = sorted(membres, key=lambda x: -x["p5"])[:k]
        out[p] = {"n": len(membres),
                  "vol_min": float(min(vols)) if vols else None, "vol_max": float(max(vols)) if vols else None,
                  "top": [{"ticker": x["ticker"], "name": x["name"], "p5": x["p5"], "rang": rang[x["ticker"]],
                           "vol": risque[x["ticker"]]["vol"], "beta": risque[x["ticker"]]["beta"]} for x in top]}
    return out
