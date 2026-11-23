"""Régime de marché et frein anti-krach du momentum.

Les professionnels ne prédisent pas les krachs : ils reconnaissent le climat de marché et adaptent leur exposition.
- Régime (indicateurs connus le jour même) :
  krach    : VIX d'au moins 40, ou S&P 500 en baisse d'au moins 10 % sur 5 séances ;
  stress   : VIX d'au moins 30, ou S&P 500 en baisse d'au moins 5 % sur 5 séances ;
  tension  : VIX d'au moins 20 ;
  calme    : sinon.
- Frein anti-krach du momentum (d'après Daniel et Moskowitz, 2016, « Momentum crashes ») : les stratégies qui suivent
  la tendance subissent leurs pires pertes lors des rebonds qui suivent un marché baissier agité. Le frein est actif
  si le S&P 500 a baissé sur 24 mois, ou si le VIX est d'au moins 30 avec un S&P 500 à plus de 10 % sous son plus haut
  d'un an. Frein actif : le portefeuille fictif « radar avec frein » neutralise la tendance (voir portefeuille.py).
"""
import numpy as np
import pandas as pd

NIVEAUX = ("calme", "tension", "stress", "krach")
VIX, SPY = "^VIX", "SPY"


def niveau_vix(v):
    """Régime selon le seul VIX (sert au classement historique des dates)."""
    if v != v:
        return None
    return "krach" if v >= 40 else "stress" if v >= 30 else "tension" if v >= 20 else "calme"


def etat(macro, date=None):
    """Régime du jour et état du frein, à partir du VIX et du S&P 500 (SPY) connus à `date`. Ne lève jamais."""
    out = {"niveau": None, "raisons": [], "frein": False, "frein_raison": ""}
    try:
        if macro is None or not len(macro):
            return out
        m = macro if date is None else macro[macro.index <= pd.Timestamp(date)]
        vix = m[VIX].dropna() if VIX in m else pd.Series(dtype=float)
        spy = m[SPY].dropna() if SPY in m else pd.Series(dtype=float)
        v = float(vix.iloc[-1]) if len(vix) else float("nan")
        r5 = float(spy.iloc[-1] / spy.iloc[-6] - 1) if len(spy) > 6 else float("nan")
        dd = float(spy.iloc[-1] / spy.tail(252).max() - 1) if len(spy) > 20 else float("nan")
        r24 = float(spy.iloc[-1] / spy.iloc[-505] - 1) if len(spy) > 505 else float("nan")
        out.update(vix=v, spy5=r5, spy_dd=dd, spy24=r24)
        if v != v and r5 != r5:
            return out
        niv = niveau_vix(v) or "calme"
        if r5 == r5:
            if r5 <= -0.10:
                niv = "krach"
            elif r5 <= -0.05 and NIVEAUX.index(niv) < 2:
                niv = "stress"
        out["niveau"] = niv
        if v == v:
            out["raisons"].append(f"VIX {v:.1f}".replace(".", ","))
        if r5 == r5:
            out["raisons"].append(f"S&P 500 {r5 * 100:+.1f} % sur 5 séances".replace(".", ","))
        if dd == dd and dd <= -0.05:
            out["raisons"].append(f"{-dd * 100:.0f} % sous son plus haut d'un an")
        if r24 == r24 and r24 < 0:
            out.update(frein=True, frein_raison=f"S&P 500 en baisse sur 24 mois ({r24 * 100:+.0f} %)")
        elif v == v and v >= 30 and dd == dd and dd <= -0.10:
            out.update(frein=True, frein_raison=f"VIX {v:.0f} et S&P 500 à {-dd * 100:.0f} % sous son plus haut d'un an")
    except Exception:
        pass
    return out


def dates_par_regime(dates, macro):
    """Régime VIX de chaque date (VIX connu le jour du signal ; dernier cours connu reporté sur 5 jours au plus)."""
    if macro is None or VIX not in macro:
        return pd.Series(index=pd.DatetimeIndex(dates), dtype=object)
    v = macro[VIX].dropna()
    v = v.reindex(v.index.union(pd.DatetimeIndex(dates))).ffill(limit=5).reindex(pd.DatetimeIndex(dates))
    return v.map(niveau_vix)


EPISODES = {  # épisodes de stress de l'historique (dates des signaux)
    "fin 2018": ("2018-10-01", "2018-12-31"),
    "Covid 2020": ("2020-02-19", "2020-04-30"),
    "rebond 2020": ("2020-03-24", "2020-06-30"),
    "baisse 2022": ("2022-01-03", "2022-10-14"),
}


def plis(dates, debut=0.15, n=10):
    """Blocs de dates pour l'analyse par régime : depuis 15 % de l'historique (le début sert d'apprentissage),
    pour couvrir aussi les krachs anciens (fin 2018, Covid 2020). Analyse descriptive : elle ne sert à aucun réglage."""
    dates = np.array(sorted(dates))
    return np.array_split(dates[int(len(dates) * debut):], n)


def par_regime(r, h, macro, cout_bps, evaluate):
    """IC et écart net du modèle selon le régime VIX et sur les épisodes de stress (prévisions hors échantillon).
    t : moyenne des IC quotidiens rapportée à leur dispersion, sur un nombre d'observations divisé par h
    (les cibles à h jours se chevauchent)."""
    if r is None or r.empty:
        return {}
    x = f"x{h}"
    ic = r.groupby("date").apply(lambda g: g["p"].rank().corr(g[x].rank())).dropna()
    reg = dates_par_regime(ic.index, macro)
    out = {"regimes": {}, "episodes": {}}

    def res(ds):
        s = ic[ic.index.isin(ds)]
        if len(s) < 2 * h:
            return {"dates": int(len(s))}
        ev = evaluate(r[r["date"].isin(s.index)], h, cout_bps) or {}
        n_eff = len(s) / h
        t = float(s.mean() / s.std() * np.sqrt(n_eff)) if s.std() > 0 else float("nan")
        return {"dates": int(len(s)), "ic": float(s.mean()), "t": t, "ic_pos": float((s > 0).mean()), "net": ev.get("net", float("nan"))}

    for niv in NIVEAUX:
        out["regimes"][niv] = res(reg[reg == niv].index)
    for nom, (a, b) in EPISODES.items():
        out["episodes"][nom] = res(ic.index[(ic.index >= pd.Timestamp(a)) & (ic.index <= pd.Timestamp(b))])
    return out


def frein_historique(macro):
    """Dates où le frein aurait été actif (mêmes règles que etat, calculées pour chaque jour)."""
    if macro is None or SPY not in macro or VIX not in macro:
        return pd.DatetimeIndex([])
    spy = macro[SPY].dropna()
    vix = macro[VIX].reindex(spy.index).ffill(limit=5)
    dd = spy / spy.rolling(252, min_periods=20).max() - 1
    r24 = spy / spy.shift(504) - 1
    on = (r24 < 0) | ((vix >= 30) & (dd <= -0.10))
    return on[on].index


def effet_frein(r, d, h, macro):
    """Sur les dates où le frein aurait été actif : écart à la moyenne (avant frais) des 20 % les mieux classées
    par le radar, contre la même sélection répartie entre les cinq tranches de tendance (règle « radar avec frein »)."""
    act = frein_historique(macro)
    if r is None or r.empty or not len(act):
        return {"periodes": 0}
    x = r.merge(d[["date", "ticker", "mom12_1"]], on=["date", "ticker"], how="left")
    x = x[x["date"].isin(act)].dropna(subset=["mom12_1"])
    radar, neutre = [], []
    for dt_ in sorted(x["date"].unique())[::h]:
        g = x[x["date"] == dt_]
        k = max(1, len(g) // 5)
        radar.append(float(g.nlargest(k, "p")[f"m{h}"].mean()))
        q = (g["mom12_1"].rank(pct=True) * 5).clip(upper=4.999).astype(int)
        neutre.append(float(pd.concat([gg.nlargest(max(1, k // 5), "p") for _, gg in g.groupby(q)])[f"m{h}"].mean()))
    if not radar:
        return {"periodes": 0}
    return {"periodes": len(radar), "radar": float(np.mean(radar)), "neutre": float(np.mean(neutre)),
            "gagnees": int(sum(n > r_ for n, r_ in zip(neutre, radar)))}
