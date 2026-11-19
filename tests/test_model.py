"""Garde-fous de la méthode : pas de regard vers le futur, mesures justes."""
import numpy as np
import pandas as pd

from radar import model


def _panel(n_dates=400, n_t=40, seed=0, signal=0.0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    rows = []
    for d in dates:
        f = rng.normal(size=n_t)
        x = signal * f + rng.normal(size=n_t)
        for i in range(n_t):
            rows.append({"date": d, "ticker": f"T{i}", "a": f[i], "x5": x[i], "m5": x[i]})
    return pd.DataFrame(rows), np.array(sorted(dates))


def test_walk_entraine_sur_le_seul_passe(monkeypatch):
    d, dates = _panel()
    vus = []
    real = model.make_model

    class Espion:
        def __init__(self):
            self.m = real(20)

        def fit(self, X, y):
            vus.append(X.index)
            return self.m.fit(X, y)

        def predict_proba(self, X):
            return self.m.predict_proba(X)

    monkeypatch.setattr(model, "make_model", lambda iters=120: Espion())
    folds = np.array_split(dates[200:], 4)
    model.walk(d, ["a"], 5, folds, dates)
    for idx, f in zip(vus, folds):
        dernier = d.loc[idx, "date"].max()
        i0 = np.searchsorted(dates, f[0])
        assert dernier <= dates[i0 - 6], "l'entraînement voit des cibles non encore connues"


def test_evaluate_ic_parfait_et_hasard():
    d, _ = _panel(n_dates=60, signal=0)
    parfait = d.assign(p=d["x5"])
    r = model.evaluate(parfait, 5, cost_bps=0)
    assert r["ic"] > 0.99 and r["net"] > 0
    hasard = d.assign(p=np.random.default_rng(1).normal(size=len(d)))
    assert abs(model.evaluate(hasard, 5)["ic"]) < 0.05


def test_frais_et_maintien():
    d, _ = _panel(n_dates=60, signal=0)
    r0 = model.evaluate(d.assign(p=d["x5"]), 5, cost_bps=0)
    r1 = model.evaluate(d.assign(p=d["x5"]), 5, cost_bps=50)
    assert r1["net"] < r0["net"]
    stable = d.assign(p=d["ticker"].str[1:].astype(int))  # classement immobile : aucune rotation après le départ
    r = model.evaluate(stable, 5)
    assert r["rotation"] == 0 and r["rotation_maintien"] == 0
