import json

import numpy as np
import pandas as pd

from radar import brief, model, portefeuille, regime


def _macro(vix_last, spy_path):
    idx = pd.bdate_range("2023-01-02", periods=len(spy_path))
    return pd.DataFrame({"^VIX": [18.0] * (len(idx) - 1) + [vix_last], "SPY": spy_path}, index=idx)


def test_regimes():
    calme = regime.etat(_macro(14, np.linspace(100, 130, 600)))
    assert calme["niveau"] == "calme" and not calme["frein"]
    stress = regime.etat(_macro(33, list(np.linspace(100, 130, 590)) + list(np.linspace(130, 112, 10))))
    assert stress["niveau"] == "stress" and stress["frein"]          # VIX 33 et 14 % sous le plus haut
    krach = regime.etat(_macro(25, list(np.linspace(100, 130, 594)) + [128, 125, 120, 116, 113, 112]))
    assert krach["niveau"] == "krach"                                  # S&P 500 -12,5 % en 5 séances
    baissier = regime.etat(_macro(22, list(np.linspace(130, 100, 600))))
    assert baissier["frein"] and "24 mois" in baissier["frein_raison"]
    assert regime.etat(None)["niveau"] is None


def test_fiabilite_par_regime():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2020-01-01", periods=120)
    rows = []
    for d in dates:
        x = rng.normal(0, 1, 40)
        rows += [{"date": d, "ticker": f"T{i}", "x5": x[i], "m5": x[i] / 100, "p": x[i] + rng.normal(0, 2)} for i in range(40)]
    r = pd.DataFrame(rows)
    vix = pd.Series(np.where(np.arange(120) < 60, 15.0, 35.0), index=dates)
    out = regime.par_regime(r, 5, pd.DataFrame({"^VIX": vix}), 10, model.evaluate)
    assert out["regimes"]["calme"]["dates"] == 60 and out["regimes"]["stress"]["dates"] == 60
    assert out["regimes"]["calme"]["ic"] > 0 and "ic" not in out["regimes"]["krach"]
    assert out["episodes"]["Covid 2020"]["dates"] > 0
    json.dumps(out)
    evl = {"regimes": out}
    assert brief._ligne_regimes(evl)[0].startswith("  Selon le climat de marché")
    assert "Historiquement, dans ce climat" in brief._hist_regime(evl, "stress")


def test_frein_neutre_en_tendance():
    sc = {f"T{i}": float(i) for i in range(50)}        # le radar préfère les numéros élevés
    mom = {f"T{i}": float(i) for i in range(50)}       # qui sont aussi les plus en tendance
    w = portefeuille._choix_neutre(sc, mom, {}, 10)
    assert len(w) == 10
    quint = sorted(int(t[1:]) // 10 for t in w)
    assert quint == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]      # deux lignes par cinquième de tendance
    assert set(portefeuille._choix(sc, {}, 10)) == {f"T{i}" for i in range(40, 50)}


def test_frein_dans_le_portefeuille(tmp_path):
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2025-01-01", periods=300)
    cols = [f"T{i}" for i in range(50)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (300, 50)), 0)), index=idx, columns=cols)
    path = tmp_path / "p.json"
    allp = [{"ticker": t, "name": t, "p5": 0.5 + i * 1e-4} for i, t in enumerate(cols)]
    for i in range(280, 292):
        s = portefeuille.update(close.iloc[:i + 1], allp, idx[i].strftime("%Y-%m-%d"), path, frein=True)
    F = s["strats"]["radar_frein"]
    assert F["n_lignes"] == 10 and F["frein"] is True
    assert set(json.loads(path.read_text())["strats"]["radar_frein"]["lignes"]) != set(json.loads(path.read_text())["strats"]["radar"]["lignes"])


def test_ajout_regle_sans_remise_a_zero(tmp_path):
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2025-01-01", periods=300)
    cols = [f"T{i}" for i in range(50)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (300, 50)), 0)), index=idx, columns=cols)
    allp = [{"ticker": t, "name": t, "p5": 0.5 + i * 1e-4} for i, t in enumerate(cols)]
    path = tmp_path / "p.json"
    for i in range(280, 283):
        portefeuille.update(close.iloc[:i + 1], allp, idx[i].strftime("%Y-%m-%d"), path)
    st = json.loads(path.read_text())
    del st["strats"]["radar_frein"]                     # état écrit avant l'ajout de la règle
    v_radar = st["strats"]["radar"]["valeur"]
    path.write_text(json.dumps(st))
    s = portefeuille.update(close.iloc[:284], allp, idx[283].strftime("%Y-%m-%d"), path)
    assert s["strats"]["radar_frein"]["n_lignes"] == 10 and s["strats"]["radar_frein"]["debut"] == idx[283].strftime("%Y-%m-%d")
    assert s["seances"] == 3 and s["strats"]["radar"]["perf"] != 0 and v_radar
    assert s["prochaine_revue"] == 2                    # le calendrier des revues n'est pas décalé


def test_effet_frein():
    rng = np.random.default_rng(4)
    dates = pd.bdate_range("2022-01-03", periods=60)
    rows = []
    for d in dates:
        p = rng.normal(0, 1, 50)
        rows += [{"date": d, "ticker": f"T{i}", "x5": 0.0, "m5": p[i] / 100, "p": p[i], "mom12_1": rng.random()} for i in range(50)]
    r = pd.DataFrame(rows)
    spy = pd.Series(np.linspace(130, 100, 700), index=pd.bdate_range("2019-06-03", periods=700))
    macro = pd.DataFrame({"SPY": spy, "^VIX": 25.0})
    out = regime.effet_frein(r[["date", "ticker", "x5", "m5", "p"]], r, 5, macro)
    assert out["periodes"] > 0 and out["radar"] > out["neutre"]   # ici le classement est parfait : le frein coûte
    assert "Frein anti-krach, effet passé" in "\n".join(brief._ligne_regimes({"regimes": {"regimes": {"calme": {"dates": 20, "ic": 0.01, "t": 1.0}}, "frein": out}}))
