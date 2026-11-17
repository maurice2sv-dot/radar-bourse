"""Modèle de surperformance (valeur contre marché suivi) en panel, backtest walk-forward sans fuite."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score

from .features import ALL_FEATS, NEWS_FEATS, PRICE_FEATS


def make_model(iters=120):
    return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=iters, min_samples_leaf=80,
                                          l2_regularization=1.0, random_state=0)


def _metrics(r):
    y, p = r["y"].values, r["p"].values
    acc = float(((p > 0.5) == (y == 1)).mean())
    conf = r[(r.p > 0.6) | (r.p < 0.4)]
    return {"n": int(len(r)), "acc": acc, "base": float(max(y.mean(), 1 - y.mean())),
            "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else float("nan"),
            "brier": float(brier_score_loss(y, p)),
            "acc_conf": float(((conf.p > 0.5) == (conf.y == 1)).mean()) if len(conf) else float("nan"),
            "n_conf": int(len(conf))}


def backtest(df, feats, h, n_folds=5, start_frac=0.4):
    d = df.dropna(subset=feats[:1] + [f"x{h}", "ret20"]).sort_values("date")
    dates = np.array(sorted(d["date"].unique()))
    folds = np.array_split(dates[int(len(dates) * start_frac):], n_folds)
    out = []
    for fd in folds:
        i0 = np.searchsorted(dates, fd[0])
        train_end = dates[max(i0 - h - 1, 0)]  # écart de h jours : aucune fuite de la cible
        tr = d[d["date"] <= train_end]
        te = d[(d["date"] >= fd[0]) & (d["date"] <= fd[-1])]
        m = make_model().fit(tr[feats], (tr[f"x{h}"] > 0).astype(int))
        out.append(pd.DataFrame({"p": m.predict_proba(te[feats])[:, 1],
                                 "y": (te[f"x{h}"] > 0).astype(int).values}))
    return _metrics(pd.concat(out))


def run_backtests(df, horizons, main):
    res = {str(h): backtest(df, ALL_FEATS, h) for h in horizons}
    res["price_only"] = backtest(df, PRICE_FEATS, main)  # test de valeur ajoutée des actualités
    res["sans_calendrier"] = backtest(df, PRICE_FEATS + NEWS_FEATS, main)  # valeur ajoutée du calendrier
    return res


def predict_at(df, date, feats, h, iters=120):
    """Entraîne sur les lignes dont la cible est entièrement connue à `date`, prédit à `date`."""
    dates = np.array(sorted(df["date"].unique()))
    i = np.searchsorted(dates, date)
    tr = df[(df["date"] <= dates[max(i - h, 0)])].dropna(subset=[f"x{h}"])
    cur = df[df["date"] == date]
    m = make_model(iters).fit(tr[feats], (tr[f"x{h}"] > 0).astype(int))
    return cur["ticker"].values, m.predict_proba(cur[feats])[:, 1]


def predict_latest(df, feats, horizons):
    last = df["date"].max()
    rows = []
    for h in horizons:
        tr = df.dropna(subset=[f"x{h}"])
        cur = df[df["date"] == last]
        m = make_model().fit(tr[feats], (tr[f"x{h}"] > 0).astype(int))
        for t, p in zip(cur["ticker"], m.predict_proba(cur[feats])[:, 1]):
            rows.append({"ticker": t, "h": h, "p_raw": float(p)})
    return pd.DataFrame(rows), last
