import datetime as dt

from radar import passage, rss


def test_creneaux():
    c = lambda s: passage.creneau(dt.datetime.fromisoformat(s))
    assert c("2026-11-23 08:30") == "2026-11-23/jour"       # lundi matin, après l'Asie
    assert c("2026-11-23 22:40") == "2026-11-23/soir"       # lundi soir, après New York
    assert c("2026-11-24 03:30") == "2026-11-23/soir"       # nuit : passage du soir retardé
    assert c("2026-11-24 06:59") == "2026-11-23/soir"
    assert c("2026-11-21 12:00") == "2026-11-20/soir"       # samedi : vendredi soir
    assert c("2026-11-23 05:00") == "2026-11-20/soir"       # lundi avant 7h : vendredi soir


def test_garde_un_passage_par_creneau(tmp_path):
    (tmp_path / "data").mkdir()
    assert passage.fait(tmp_path) is None
    passage.noter(tmp_path, "2026-11-23/soir")
    assert passage.fait(tmp_path) == "2026-11-23/soir"


XML = b"""<rss><channel>
<item><title>Percee en informatique quantique</title><description>&lt;p&gt;texte&lt;/p&gt;</description>
<link>https://ex.org/a</link><pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Sommet sur l'IA</title><link>https://ex.org/b</link><pubDate>Sun, 22 Nov 2026 09:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_archive_rss_sans_doublon(tmp_path):
    rows = rss.parse(XML, "test")
    assert [r[1] for r in rows] == ["2026-11-21", "2026-11-22"]
    assert rss.save(rows, tmp_path) == 2
    assert rss.save(rows, tmp_path) == 0  # déclenchement suivant : rien en double
    assert sorted(r[0] for r in rss.load(tmp_path)) == sorted(r[0] for r in rows)


def test_lecture_flux_config():
    import pathlib
    f = rss._feeds(pathlib.Path(__file__).resolve().parents[1] / "config.yaml")
    assert len(f) == 5 and f["bbc_world"].startswith("https://")
