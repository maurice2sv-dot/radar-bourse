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


class _Rep:
    def __init__(self, text="", js=None, code=200):
        self.text, self._js, self.status_code = text, js, code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._js


def _base_cours(tmp_path, d):
    import sqlite3
    con = sqlite3.connect(tmp_path / "t.db")
    con.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL, volume REAL)")
    con.executemany("INSERT INTO prices VALUES (?,?,?,0)", [("AAA", d, 100.0), ("BBB", d, 50.0)])
    return con


def test_controle_croise_secours_nasdaq(tmp_path, monkeypatch):
    import requests
    d = "2026-11-20"
    con = _base_cours(tmp_path, d)

    def get(url, **kw):
        if "stooq" in url:
            return _Rep(text="Get your apikey")  # Stooq exige une clé : réponse sans cours
        t = url.split("/quote/")[1].split("/")[0]
        close = {"AAA": "$100.50", "BBB": "$58.00"}[t]
        return _Rep(js={"data": {"tradesTable": {"rows": [{"date": "11/20/2026", "close": close}]}}})
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(collect, "_open_day", lambda: "9999-12-31")
    cfg = {"watchlist": {"AAA": {}, "BBB": {}, "CCC.PA": {}}}
    log, errs = collect.cross_check(cfg, con)
    assert log["controle_croise"].startswith("Nasdaq : 2 valeurs comparées, 1 écart")
    assert len(errs) == 1 and "BBB +16%" in errs[0] and "Nasdaq" in errs[0]


def test_controle_croise_absent_signale(tmp_path, monkeypatch):
    import requests
    con = _base_cours(tmp_path, "2026-11-20")
    monkeypatch.setattr(requests, "get", lambda url, **kw: _Rep(code=403))
    log, errs = collect.cross_check({"watchlist": {"AAA": {}, "BBB": {}}}, con)
    assert errs and errs[0].startswith("contrôle croisé des cours indisponible (Stooq : RuntimeError HTTP 403")
    assert "Nasdaq" in errs[0]
