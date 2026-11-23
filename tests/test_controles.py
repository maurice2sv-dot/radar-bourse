import json
import pathlib

import numpy as np
import pandas as pd

from radar import brief, collect


def test_cours_suspects():
    idx = pd.bdate_range("2026-01-01", periods=10)
    c = pd.DataFrame({"A": np.linspace(100, 101, 10), "B": [100] * 9 + [160.0]}, index=idx)
    out = collect.suspicious_moves(c)
    assert len(out) == 1 and out[0].startswith("B +60")


def test_brief_se_genere(tmp_path):
    rep = json.loads((pathlib.Path(__file__).resolve().parents[1] / "data" / "report.json").read_text())
    daily = brief.generate(rep, tmp_path)
    txt = "\n".join(daily)
    assert "1. Valeurs à surveiller" in txt and "Appréciation" in txt and "—" not in txt
    assert (tmp_path / "brief_weekly.md").exists()


def test_indices_asiatiques():
    from radar import analysis
    idx = pd.bdate_range("2026-01-01", periods=30)
    nk = [100.0] * 29 + [95.0]                     # Nikkei -5 % sur la dernière séance
    hs = list(np.linspace(100, 85, 30))            # Hang Seng -15 % sur 20 séances, séance calme
    sh = [100.0] * 30                              # Shanghai stable
    macro = pd.DataFrame({"^N225": nk, "^HSI": hs, "000001.SS": sh}, index=idx)
    cfg = {"marches": {"Nikkei 225": "^N225", "Hang Seng": "^HSI", "Shanghai": "000001.SS"}}
    marches, alertes = analysis.marches_alertes(macro, idx[-1], cfg)
    assert [m["label"] for m in marches if m["asie"]] == ["Nikkei 225", "Hang Seng", "Shanghai"]
    assert any(a.startswith("Asie, Nikkei 225 -5,0 %") for a in alertes)
    assert any(a.startswith("Asie, Hang Seng") and "20 séances" in a for a in alertes)
    assert not any("Shanghai" in a for a in alertes)
    rep = {"marches": marches, "alertes_marche": alertes, "events": [], "heat": [], "agenda": []}
    txt = "\n".join(brief._bloc_alerte(rep))
    assert "Asie (dernière séance close) : Nikkei 225 -5,0 %" in txt and "—" not in txt
