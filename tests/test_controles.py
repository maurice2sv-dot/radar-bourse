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
