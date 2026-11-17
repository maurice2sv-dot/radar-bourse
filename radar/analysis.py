"""Tendances sectorielles, technologies à veiller, valeurs à surveiller, événements marquants."""
import numpy as np
import pandas as pd

from .events import CATS, TECHS

CAT_FR = {"militaire": "militaire", "securitaire": "sécuritaire", "politique": "politique", "financier": "financier",
          "meteo": "météo", "economique": "économique", "scientifique": "scientifique", "religieux": "religieux",
          "media": "médiatique"}
MIN_HIST = 30  # jours actifs exigés sur les 60 jours de référence avant de parler de hausse ou d'émergence
SEC_FR = {"tech": "Technologie", "conso": "Consommation", "auto": "Automobile", "finance": "Finance",
          "energie": "Énergie", "defense": "Défense", "aero": "Aéronautique", "luxe": "Luxe", "sante": "Santé"}


def _z(s):
    sd = s.std()
    return (s - s.mean()) / (sd if sd and not np.isnan(sd) else 1.0)


def analyze(df, scores, close, cfg, preds, wcs):
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
    tab["attention"] = _z(tab["news"]) + _z(tab["vr"]) + _z(tab["conf"])
    recent = close.tail(60)
    watch = []
    for t in tab.sort_values("attention", ascending=False).index[:8]:
        d, dv = driver(t)
        ps = {str(h): float(preds[(preds.ticker == t) & (preds.h == h)]["p_up"].iloc[0]) for h in cfg["horizons"]}
        watch.append({"ticker": t, "name": wl[t]["name"], "sector": SEC_FR.get(wl[t]["sector"], wl[t]["sector"]),
                      "p": ps, "driver": d, "mentions": float(last.loc[t, "co_mentions"]), "ret5": float(last.loc[t, "ret5"]),
                      "volratio": float(last.loc[t, "volratio"]), "attention": float(tab.loc[t, "attention"]),
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
    return {"calib_days": int(max(0, MIN_HIST - hist_rss)), "as_of": last_date.strftime("%Y-%m-%d"), "sectors": sectors, "techs": techs, "heat": heat,
            "watch": watch, "drivers": {t: driver(t)[0] for t in last.index}, "all_p5": sorted(allp, key=lambda x: -x["p5"]), "events": ev}
