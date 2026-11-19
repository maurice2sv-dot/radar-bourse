import pandas as pd

from radar import univers

HTML = """<html><body>
<table><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>Date added</th></tr>
{rows}</table>
<table><tr><th rowspan=2>Effective Date</th><th colspan=2>Added</th><th colspan=2>Removed</th><th rowspan=2>Reason</th></tr>
<tr><th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr>
<tr><td>March 1, 2024</td><td>NEW</td><td>New Co</td><td>OLD</td><td>Old Co</td><td>x</td></tr>
<tr><td>June 1, 2020</td><td>OLD</td><td>Old Co</td><td>GONE</td><td>Gone Inc</td><td>x</td></tr>
<tr><td>June 1, 2010</td><td>AAA</td><td>Aaa</td><td>ZZZ</td><td>Zzz</td><td>x</td></tr>
</table></body></html>"""


def _html():
    rows = "".join(f"<tr><td>T{i}</td><td>Co {i}</td><td>Health Care</td><td>Pharma</td><td>2001-01-01</td></tr>" for i in range(420))
    rows += "<tr><td>NEW</td><td>New Co</td><td>Consumer Discretionary</td><td>Automobile Manufacturers</td><td>2024-03-01</td></tr>"
    rows += "<tr><td>BRK.B</td><td>Berkshire</td><td>Financials</td><td>Multi</td><td>1957-03-04</td></tr>"
    return HTML.format(rows=rows)


def test_parse_et_intervalles():
    membres, chg = univers.parse_wikipedia(_html())
    tk = {m["ticker"]: m for m in membres}
    assert "BRK-B" in tk and tk["NEW"]["sector"] == "auto" and tk["T1"]["sector"] == "sante"
    per = univers.intervalles(membres, chg)
    assert per["NEW"] == [["2024-03-01", None]]
    assert per["OLD"] == [["2020-06-01", "2024-03-01"]]   # entrée en 2020, sortie en 2024
    assert per["GONE"] == [[None, "2020-06-01"]]          # sortie après 2016, entrée inconnue
    assert "ZZZ" not in per                               # sortie avant 2016 : ignorée


def test_masque():
    idx = pd.bdate_range("2020-05-28", "2024-03-05")
    m = univers.mask({"OLD": [["2020-06-01", "2024-03-01"]]}, idx, ["OLD", "EU"])
    assert not m.loc["2020-05-29", "OLD"] and m.loc["2020-06-01", "OLD"] and not m.loc["2024-03-01", "OLD"]
    assert m["EU"].all()


def test_changements_en_tete_simple():
    rows = "".join(f"<tr><td>T{i}</td><td>Co {i}</td><td>Energy</td><td>Oil</td><td>2001-01-01</td></tr>" for i in range(410))
    html = f"""<table><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th><th>Date added</th></tr>{rows}</table>
<table><tr><th>Effective Date</th><th>Added</th><th>Added</th><th>Removed</th><th>Removed</th><th>Reason</th></tr>
<tr><td></td><td>Ticker</td><td>Security</td><td>Ticker</td><td>Security</td><td></td></tr>
<tr><td>March 1, 2024</td><td>T1</td><td>Co 1</td><td>OLD</td><td>Old Co</td><td>x</td></tr></table>"""
    _, chg = univers.parse_wikipedia(html)
    assert chg == [{"date": "2024-03-01", "ajout": "T1", "retrait": "OLD", "nom_retrait": "Old Co"}]


def test_historique_fja(monkeypatch):
    import types
    csv = "date,tickers\n2015-06-01,\"AAA,BBB,CCC\"\n2017-03-01,\"AAA,BBB,DDD\"\n2020-01-02,\"AAA,DDD,BRK.B\"\n"

    class R:
        def __init__(self, js=None, text=""):
            self._js, self.text = js, text

        def raise_for_status(self):
            pass

        def json(self):
            return self._js

    def get(url, headers=None, timeout=None):
        if url == univers.FJA:
            return R([{"name": "S&P 500 Historical Components & Changes(01-17-2026).csv", "download_url": "x"},
                      {"name": "S&P 500 Historical Components & Changes(05-01-2024).csv", "download_url": "y"}])
        assert url == "x"
        return R(text=csv)

    monkeypatch.setitem(__import__("sys").modules, "requests", types.SimpleNamespace(get=get))
    per, fin = univers.historique_fja()
    assert fin == "2020-01-02"
    assert per["AAA"] == [[None, None]]
    assert per["CCC"] == [[None, "2017-03-01"]]
    assert per["BBB"] == [[None, "2020-01-02"]]
    assert per["DDD"] == [["2017-03-01", None]] and per["BRK-B"] == [["2020-01-02", None]]
