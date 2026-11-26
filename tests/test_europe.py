import pathlib

import numpy as np
import pandas as pd
import yaml

from radar import europe, events

CFG = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1] / "config.yaml").read_text())


def test_resume_europe():
    idx = pd.bdate_range("2026-01-01", periods=30)
    close = pd.DataFrame({"MC.PA": np.linspace(100, 130, 30), "AAPL": 100.0, "ASML": 100.0}, index=idx)
    allp = [{"ticker": t, "name": t, "p5": p} for t, p in (("AAPL", 0.51), ("MC.PA", 0.50), ("ASML", 0.49))]
    r = europe.resume(close, allp)
    assert [(x["ticker"], x["rang"]) for x in r] == [("MC.PA", 2), ("ASML", 3)]
    assert r[0]["ret20"] > 0 and not europe.est_europeenne("BRK-B")


def test_noms_ambigus():
    wl = CFG["watchlist"]
    assert all(v["sector"] in events.SECTORS for v in wl.values())
    m = events.company_matchers(wl)
    trouve = lambda s: {t for t, rx in m.items() if rx.search(s)}
    assert not trouve("La roche s'effondre ; Charles Leclerc signe chez Ferrari ; an ongoing talk") & {"ROG.SW", "RACE.MI", "INGA.AS"}
    assert {"ROG.SW", "UBSG.SW", "BP.L"} <= trouve("Le groupe Roche, UBS et le groupe BP publient leurs résultats")
