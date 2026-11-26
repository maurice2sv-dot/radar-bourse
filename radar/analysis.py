"""Tendances sectorielles, technologies à veiller, valeurs à surveiller, événements marquants."""
import numpy as np
import pandas as pd

from . import regime
from .events import CATS, TECHS

CAT_FR = {"militaire": "militaire", "securitaire": "sécuritaire", "politique": "politique", "financier": "financier",
          "meteo": "météo", "economique": "économique", "scientifique": "scientifique", "religieux": "religieux",
          "media": "médiatique"}
ASIE = {"^N225", "^HSI", "000001.SS"}  # indices asiatiques : contexte et alertes, hors modèle
EUROPE = {"^FCHI", "^GDAXI", "^STOXX50E", "^FTSE", "^SSMI"}  # indices européens : suivi, hors modèle
MIN_HIST = 30  # jours actifs exigés sur les 60 jours de référence avant de parler de hausse ou d'émergence
SEC_FR = {"tech": "Technologie", "conso": "Consommation", "auto": "Automobile", "finance": "Finance",
          "energie": "Énergie", "defense": "Défense", "aero": "Aéronautique", "luxe": "Luxe", "sante": "Santé",
          "distribution": "Grande consommation", "industrie": "Industrie", "materiaux": "Matériaux",
          "services_publics": "Services publics", "telecom": "Télécoms", "immobilier": "Immobilier"}


def _z(s):
    sd = s.std()
    return (s - s.mean()) / (sd if sd and not np.isnan(sd) else 1.0)


def marches_alertes(macro, last_date, cfg):
    """Indicateurs de marché : niveau, variation sur 1 et 20 séances, alertes de risque (Asie comprise)."""
    marches, alertes = [], []
    if macro is not None and len(macro):
        m = macro[macro.index <= last_date]
        for lab, s in cfg.get("marches", {}).items():
            if s not in m or m[s].dropna().size < 25:
                continue
            v = m[s].dropna()
            lvl, chg20 = float(v.iloc[-1]), (float(v.iloc[-1] - v.iloc[-21]) if s == "^TNX" else float(v.iloc[-1] / v.iloc[-21] - 1))
            chg1 = float(v.iloc[-1] / v.iloc[-2] - 1) if s != "^TNX" else float(v.iloc[-1] - v.iloc[-2])
            marches.append({"label": lab, "niveau": lvl, "chg20": chg20, "chg1": chg1, "points": s == "^TNX", "date": v.index[-1].strftime("%d/%m"),
                            "asie": s in ASIE})
            if s in EUROPE:  # courbe sur 60 séances pour le tableau de bord
                marches[-1].update(europe=True, serie=[round(float(x), 2) for x in v.iloc[-60:]])
            if s in ASIE:
                if abs(chg1) >= 0.03:
                    alertes.append(f"Asie, {lab} {chg1 * 100:+.1f} % sur la séance du {v.index[-1].strftime('%d/%m')}".replace(".", ",", 1))
                elif chg20 <= -0.10:
                    alertes.append(f"Asie, {lab} {chg20 * 100:+.0f} % sur 20 séances")
            elif s in ("^VIX", "^V2TX"):
                chg5 = float(v.iloc[-1] / v.iloc[-6] - 1)
                if lvl >= 25 or chg5 >= 0.30:
                    alertes.append(f"tension de marché, {lab} à {lvl:.1f} ({chg5 * 100:+.0f} % sur 5 séances)")
            elif s == "CL=F" and abs(chg20) >= 0.15:
                alertes.append(f"pétrole {chg20 * 100:+.0f} % sur 20 séances")
            elif s == "DX-Y.NYB" and abs(chg20) >= 0.04:
                alertes.append(f"dollar {chg20 * 100:+.1f} % sur 20 séances")
            elif s == "^TNX" and abs(chg20) >= 0.40:
                alertes.append(f"taux US à 10 ans {chg20:+.2f} point sur 20 séances")
    return marches, alertes


def analyze(df, scores, close, cfg, preds, wcs, cal=None, macro=None):
    wl, main = cfg["watchlist"], cfg["main_horizon"]
    last_date = df["date"].max()
    last = df[df["date"] == last_date].set_index("ticker")
    idx, n = close.index, len(close)

    # Pilotes d'actualité par valeur : catégorie dominante pondérée
    def driver(t):
        vals = {c: wcs.get(f"{c}|{last.loc[t, 'sector']}", 1.0) * last.loc[t, f"n_{c}"] for c in CATS}
        c = max(vals, key=lambda k: abs(vals[k]))
        return (CAT_FR[c], float(vals[c])) if abs(vals[c]) > 1e-9 else ("aucun signal fort", 0.0)

    # Secteurs
    sec = last.groupby("sector").agg(ret20=("ret20", "mean"), news=("news_comp", "mean"))
    sec["score"] = _z(sec["ret20"]) + _z(sec["news"])
    sectors = []
    for s, r in sec.sort_values("score", ascending=False).iterrows():
        tk = [t for t in last.index if last.loc[t, "sector"] == s]
        drv = max((driver(t) for t in tk), key=lambda x: abs(x[1]))
        sectors.append({"sector": SEC_FR.get(s, s), "ret20": float(r.ret20), "news": float(r.news),
                        "score": float(r.score), "label": "haussière" if r.score > 0.5 else "baissière" if r.score < -0.5 else "neutre",
                        "driver": drv[0]})

    # Technologies : z-score des mentions 7 j contre les 60 j précédents
    counts = pd.DataFrame(0.0, index=idx, columns=list(TECHS))
    is_g = (scores["source"].values == "GDELT") if len(scores) else np.zeros(0, bool)
    pos = np.minimum(idx.searchsorted(scores["date"].values), n - 1) if len(scores) else np.zeros(0, int)
    def active(mask):  # jours distincts avec données dans la fenêtre de référence (un vieil article isolé ne compte pas)
        a = np.unique(pos[mask])
        return int(((a >= n - 67) & (a < n - 7)).sum())

    hist_rss = active(~is_g) if len(scores) else 0
    if len(scores):
        for p, tl in zip(pos, scores["techs"]):
            for t in tl:
                counts.iloc[p, counts.columns.get_loc(t)] += 1
    base = counts.iloc[-67:-7]
    m7 = counts.tail(7).mean()
    z = (m7 - base.mean()) / np.maximum(base.std() / np.sqrt(7), 0.08)
    calib = hist_rss < MIN_HIST
    if calib:
        z = z * 0
    techs = []
    for t in z.sort_values(ascending=False).index:
        rel = [k for k, v in wl.items() if t in v.get("techs", [])]
        techs.append({"tech": t, "z": float(z[t]), "m7": int(counts.tail(7)[t].sum()), "related": rel,
                      "status": "calibrage" if calib else "émergente" if z[t] > 2.5 and counts.tail(7)[t].sum() >= 3 else "en hausse" if z[t] > 1 else "stable"})

    # Chaleur des catégories (intensité brute 7 j vs moyenne des 90 j précédents)
    heat = []
    for c in CATS:
        daily = np.zeros(n)
        inten = np.array([d.get(c, 0.0) for d in scores["cats"]]) if len(scores) else np.zeros(0)
        g = is_g & (inten > 0)
        use = g if g.any() else ~is_g  # série GDELT (avec historique) si elle existe, sinon articles RSS
        np.add.at(daily, pos[use], inten[use])
        hist = active(use) if len(scores) else 0
        s7 = daily[-7:].sum()
        ratio = None  # pas de norme tant que l'historique est trop court : aucune alerte
        if hist >= MIN_HIST:
            ratio = float(s7 / (daily[-67:-7].mean() * 7 + 0.5))
        heat.append({"cat": CAT_FR[c], "s7": float(s7), "ratio": ratio, "hist": int(max(hist, 0))})

    # Valeurs à surveiller
    p_main = preds[preds.h == main].set_index("ticker")
    tab = pd.DataFrame({
        "news": last["news_comp"].abs(), "vr": last["volratio"], "conf": (p_main["p_up"] - 0.5).abs()}).dropna()
    tab["earn"] = (last["earn_next"] <= 5 / 30).astype(float).reindex(tab.index).fillna(0)  # résultats sous 5 jours
    tab["attention"] = _z(tab["news"]) + _z(tab["vr"]) + _z(tab["conf"]) + 1.0 * tab["earn"]
    recent = close.tail(60)
    watch = []
    for t in tab.sort_values("attention", ascending=False).index[:8]:
        d, dv = driver(t)
        ps = {str(h): float(preds[(preds.ticker == t) & (preds.h == h)]["p_up"].iloc[0]) for h in cfg["horizons"]}
        watch.append({"ticker": t, "name": wl[t]["name"], "sector": SEC_FR.get(wl[t]["sector"], wl[t]["sector"]),
                      "p": ps, "driver": d, "mentions": float(last.loc[t, "co_mentions"]), "ret5": float(last.loc[t, "ret5"]),
                      "volratio": float(last.loc[t, "volratio"]), "attention": float(tab.loc[t, "attention"]),
                      "earn": bool(tab.loc[t, "earn"]),
                      "spark": [float(x) for x in (recent[t] / recent[t].iloc[0]).values]})
    allp = [{"ticker": t, "name": wl[t]["name"], "p5": float(p_main.loc[t, "p_up"])} for t in p_main.index]

    # Événements marquants (3 derniers jours de bourse)
    ev = []
    if len(scores) and len(idx) >= 3:
        cut = idx[-3]
        r = scores[(scores["date"] >= cut) & (scores["source"] != "GDELT")].copy()
        r["mag"] = r["cats"].map(lambda d: max(d.values()) if d else 0) * r["polarity"].abs().add(0.3)
        for row in r.sort_values("mag", ascending=False).head(8).itertuples():
            ev.append({"date": row.date.strftime("%d/%m"), "source": row.source, "title": row.title,
                       "cats": [CAT_FR[c] for c in row.cats], "pol": float(row.polarity)})
    # Agenda : résultats des 7 prochains jours, décisions de banques centrales des 14 prochains jours
    agenda = []
    e = (cal or {}).get("earn")
    if e is not None and len(e):
        up = e[(e["date"] > last_date) & (e["date"] <= last_date + pd.Timedelta(days=7)) & e["ticker"].isin(list(wl))]
        for r in up.sort_values("date").itertuples():
            agenda.append({"d": r.date, "date": r.date.strftime("%d/%m"), "label": f"résultats {wl[r.ticker]['name']}"})
    for name, ds in ((cal or {}).get("cb") or {}).items():
        nxt = [pd.Timestamp(str(d)) for d in ds if last_date < pd.Timestamp(str(d)) <= last_date + pd.Timedelta(days=14)]
        if nxt:
            agenda.append({"d": nxt[0], "date": nxt[0].strftime("%d/%m"), "label": f"décision {name}"})
    agenda = [{k: v for k, v in a.items() if k != "d"} for a in sorted(agenda, key=lambda a: a["d"])]
    # Indicateurs de marché : niveau, variation sur 20 séances, alertes de risque
    marches, alertes = marches_alertes(macro, last_date, cfg)
    return {"marches": marches, "alertes_marche": alertes, "regime": regime.etat(macro, last_date), "agenda": agenda, "calib_days": int(max(0, MIN_HIST - hist_rss)), "as_of": last_date.strftime("%Y-%m-%d"), "sectors": sectors, "techs": techs, "heat": heat,
            "watch": watch, "drivers": {t: driver(t)[0] for t in last.index}, "all_p5": sorted(allp, key=lambda x: -x["p5"]), "events": ev}
