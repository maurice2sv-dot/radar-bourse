import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd

from radar import db, journal, portefeuille


def test_indice_publie_en_retard_rattrape(tmp_path):
    idx = pd.bdate_range("2026-11-23", periods=5)
    close = pd.DataFrame(100.0, index=idx, columns=list("ABCDE"))
    allp = [{"ticker": t, "name": t, "p5": 0.5} for t in close]
    vrai = pd.Series([100, 101, 102, 103, 104.0], index=idx)
    for i in range(5):
        vu = vrai.iloc[:i + 1].copy()
        if 0 < i < 4:
            vu.iloc[-1] = np.nan  # dernier cours pas encore publié
        s = portefeuille.update(close.iloc[:i + 1], allp, idx[i].strftime("%Y-%m-%d"), tmp_path / "p.json",
                                macro=pd.DataFrame({"X": vu}), refs={"Indice": "X"})
    assert abs(s["refs"]["Indice"] - 0.04) < 1e-9
    assert [x["Indice"] for x in s["historique"]] == [101.0, 102.0, 103.0, 104.0]


def _base(tmp_path, jours, hit):
    con = db.connect({"db_path": "r.db", "mode": "live"}, tmp_path)
    for d in jours:
        for t in range(10):
            con.execute("INSERT INTO predictions(run_date,ticker,horizon,p_up,p_raw,kind,resolved,realized,hit) "
                        "VALUES (?,?,5,0.5,0.5,'live',1,0.0,?)", (d, f"T{t}", int(t < hit)))
    return con


def test_coefficient_neutre_sans_periodes_suffisantes(tmp_path):
    jours = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-11-18", periods=6)]
    con = _base(tmp_path, jours, 4)
    periodes = journal.independent_hits(con)
    assert len(periodes) == 2  # jours 1 et 6 : les autres se chevauchent
    k, n, hit = journal.shrink_factor(journal.live_stats(con), 5, periodes)
    assert k == 0.3 and n == 60 and abs(hit - 0.4) < 1e-9


def test_coefficient_adapte_apres_20_periodes(tmp_path):
    jours = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-05", periods=100)]
    con = _base(tmp_path, jours, 6)
    periodes = journal.independent_hits(con)
    k, _, _ = journal.shrink_factor(journal.live_stats(con), 5, periodes)
    assert len(periodes) == 20 and abs(k - 0.9) < 1e-9


def test_echeances_periode_fraiche(tmp_path):
    con = _base(tmp_path, [], 0)
    f = journal.fresh_stats(con, "2026-11-26")
    assert f["dates"] == 0 and f["premier_attendu"] == "2026-12-03" and f["complet_attendu"] == "2026-12-30"
