"""Modèle de classement relatif et évaluation à la manière des professionnels.

Cible : faire mieux que la moyenne de son secteur à h jours (neutralité sectorielle).
Mesures : IC (corrélation de rang entre classement prédit et classement réel, chaque jour), écart entre les 20 %
de valeurs les mieux classées et la moyenne, net de frais et de rotation.
Discipline : les groupes de variables sont choisis sur la période de développement seulement ; la période de
test réservée (config evaluation.test_reserve_debut) ne sert à aucun choix.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from .features import ALL_FEATS, CAL_FEATS, FUND_FEATS, MACRO_FEATS, NEWS_FEATS, PRICE_FEATS

GROUPS = {"actualites": NEWS_FEATS, "calendrier": CAL_FEATS, "marches": MACRO_FEATS, "fondamentaux": FUND_FEATS}
GROUP_FR = {"prix": "prix", "actualites": "actualités", "calendrier": "calendrier", "marches": "marchés",
            "fondamentaux": "fondamentaux"}


def feats_for(groups):
    return PRICE_FEATS + [f for g in groups for f in GROUPS.get(g, [])]


def _usable(tr, feats):
    """Écarte les variables sans aucune valeur (source absente) : le modèle ne sait pas les découper."""
    return [f for f in feats if tr[f].notna().any()]


def make_model(iters=120):
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=iters, min_samples_leaf=200,
                                          l2_regularization=1.0, random_state=0)


def split(d, cfg, h):
    dates = np.array(sorted(d["date"].unique()))
    debut = np.datetime64(pd.Timestamp(str(cfg["evaluation"]["test_reserve_debut"])))
    dev = dates[dates < debut]
    dev = dev[:-h] if len(dev) > h else dev  # cibles du développement connues avant le test réservé
    dev_folds = np.array_split(dev[int(len(dev) * 0.4):], 5)
    res_folds = np.array_split(dates[dates >= debut], 4)
    return dates, dev_folds, res_folds


def walk(d, feats, h, folds, dates):
    """Walk-forward : pour chaque bloc, entraînement sur le passé seul, avec un écart de h jours."""
    out = []
    for f in folds:
        if len(f) == 0:
            continue
        i0 = np.searchsorted(dates, f[0])
        tr = d[d["date"] <= dates[max(i0 - h - 1, 0)]].dropna(subset=[f"x{h}"])
        te = d[d["date"].isin(f)].dropna(subset=[f"x{h}", f"m{h}"])
        if len(tr) < 1000 or te.empty:
            continue
        fu = _usable(tr, feats)
        m = make_model().fit(tr[fu], (tr[f"x{h}"] > 0).astype(int))
        out.append(te[["date", "ticker", f"x{h}", f"m{h}"]].assign(p=m.predict_proba(te[fu])[:, 1]))
    return pd.concat(out) if out else pd.DataFrame()


def evaluate(r, h, cost_bps=10):
    if r is None or r.empty:
        return None
    x, m = f"x{h}", f"m{h}"
    ic = r.groupby("date").apply(lambda g: g["p"].rank().corr(g[x].rank())).dropna()
    icn = ic.iloc[::h]  # une date sur h : observations sans chevauchement
    t = float(icn.mean() / icn.std() * np.sqrt(len(icn))) if len(icn) > 2 and icn.std() > 0 else float("nan")
    prev, gross, net, turn = set(), [], [], []
    for d in sorted(r["date"].unique())[::h]:
        g = r[r["date"] == d]
        k = max(1, len(g) // 5)
        top = set(g.nlargest(k, "p")["ticker"])
        to = 1.0 if not prev else len(top - prev) / k
        ret = float(g[g["ticker"].isin(top)][m].mean())
        gross.append(ret)
        net.append(ret - to * 2 * cost_bps / 1e4)
        turn.append(to)
        prev = top
    ann = np.sqrt(252 / h)
    ir = lambda s: float(np.mean(s) / np.std(s) * ann) if len(s) > 2 and np.std(s) > 0 else float("nan")
    y = (r[x] > 0).astype(int)
    return {"ic": float(ic.mean()), "t": t, "n": int(len(icn)), "ic_pos": float((icn > 0).mean()),
            "auc": float(roc_auc_score(y, r["p"])) if y.nunique() > 1 else float("nan"),
            "brut": float(np.mean(gross)), "net": float(np.mean(net)), "rotation": float(np.mean(turn[1:] or [1.0])),
            "ir_brut": ir(gross), "ir_net": ir(net),
            "debut": str(pd.Timestamp(r["date"].min()).date()), "fin": str(pd.Timestamp(r["date"].max()).date())}


def select_groups(d, cfg, h):
    """Sélection pas à pas : un groupe n'est gardé que s'il améliore l'IC de développement d'au moins gain_min_ic."""
    ev_cfg = cfg["evaluation"]
    dates, dev_folds, _ = split(d, cfg, h)
    cost, gain = ev_cfg.get("cout_bps", 10), ev_cfg.get("gain_min_ic", 0.003)
    best_ev = evaluate(walk(d, PRICE_FEATS, h, dev_folds, dates), h, cost)
    trace = [dict(best_ev, groupe="prix", garde=True)]
    chosen = []
    for g, feats in GROUPS.items():
        if not any(d[f].notna().any() for f in feats):
            trace.append({"groupe": g, "garde": False, "note": "aucune donnée"})
            continue
        ev = evaluate(walk(d, feats_for(chosen + [g]), h, dev_folds, dates), h, cost)
        keep = ev is not None and best_ev is not None and ev["ic"] >= best_ev["ic"] + gain
        trace.append(dict(ev or {}, groupe=g, garde=bool(keep)))
        if keep:
            chosen.append(g)
            best_ev = ev
    return chosen, trace, best_ev


def evaluate_reserve(d, cfg, h, groups):
    dates, _, res_folds = split(d, cfg, h)
    return evaluate(walk(d, feats_for(groups), h, res_folds, dates), h, cfg["evaluation"].get("cout_bps", 10))


def predict_at(df, date, feats, h, iters=120):
    """Entraîne sur les lignes dont la cible est entièrement connue à `date`, prédit à `date`."""
    dates = np.array(sorted(df["date"].unique()))
    i = np.searchsorted(dates, date)
    tr = df[(df["date"] <= dates[max(i - h, 0)])].dropna(subset=[f"x{h}"])
    cur = df[df["date"] == date]
    fu = _usable(tr, feats)
    m = make_model(iters).fit(tr[fu], (tr[f"x{h}"] > 0).astype(int))
    return cur["ticker"].values, m.predict_proba(cur[fu])[:, 1]


def predict_latest(df, feats, horizons):
    last = df["date"].max()
    rows = []
    for h in horizons:
        tr = df.dropna(subset=[f"x{h}"])
        cur = df[df["date"] == last]
        fu = _usable(tr, feats)
        m = make_model().fit(tr[fu], (tr[f"x{h}"] > 0).astype(int))
        for t, p in zip(cur["ticker"], m.predict_proba(cur[fu])[:, 1]):
            rows.append({"ticker": t, "h": h, "p_raw": float(p)})
    return pd.DataFrame(rows), last
