import json

import numpy as np
import pandas as pd

from radar import portefeuille


def _close(n=300, k=50, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=n)
    cols = [f"T{i}" for i in range(k)]
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (n, k)), 0)), index=idx, columns=cols)


def test_portefeuille_complet(tmp_path):
    close = _close()
    macro = pd.DataFrame({"SPY": np.linspace(100, 110, len(close))}, index=close.index)
    path = tmp_path / "p.json"
    rng = np.random.default_rng(3)
    s = None
    for i in range(260, 300):
        d = close.index[i].strftime("%Y-%m-%d")
        allp = [{"ticker": t, "name": t, "p5": 0.5 + rng.normal(0, 0.004)} for t in close.columns]
        s = portefeuille.update(close.iloc[:i + 1], allp, d, path, macro=macro, refs={"S&P 500": "SPY"})
        if i == 270:  # deuxième passage le même jour : aucun effet
            assert portefeuille.update(close.iloc[:i + 1], allp, d, path, macro=macro, refs={"S&P 500": "SPY"}) == s
    assert s["seances"] == 39
    assert s["strats"]["radar"]["n_lignes"] == 10 and s["strats"]["momentum"]["n_lignes"] == 10
    assert s["refs"]["S&P 500"] > 0  # l'indice fictif monte
    st = json.loads(path.read_text())
    assert all(st["strats"][k]["frais"] > 0 for k in ("radar", "momentum"))


def test_regle_de_maintien():
    sc = {f"T{i}": -i for i in range(50)}  # T0 le mieux classé
    held = {"T15": 0.1, "T30": 0.1}       # T15 dans les 40 % premiers, T30 non
    w = portefeuille._choix(sc, held, 10)
    assert "T15" in w and "T30" not in w and len(w) == 10


def test_profils(tmp_path):
    from radar import risque
    close = _close(k=60)
    rq = risque.metrics(close)
    assert len(rq) == 60 and {x["profil"] for x in rq.values()} == set(risque.PROFILS)
    allp = [{"ticker": t, "name": t, "p5": 0.5 + i * 1e-4} for i, t in enumerate(close.columns)]
    pr = risque.par_profil(rq, allp)
    assert sum(pr[p]["n"] for p in risque.PROFILS) == 60 and len(pr["prudent"]["top"]) == 3
    path = tmp_path / "p.json"
    prof = {t: x["profil"] for t, x in rq.items()}
    for i in range(280, 292):
        s = portefeuille.update(close.iloc[:i + 1], allp, close.index[i].strftime("%Y-%m-%d"), path, profils=prof)
    for p in risque.PROFILS:
        assert s["strats"][f"radar_{p}"]["n_lignes"] == 4  # 20 % de 20 valeurs
        assert s["strats"][f"radar_{p}"]["periodes"] == 2
