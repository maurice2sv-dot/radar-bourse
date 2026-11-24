"""Flux RSS : collecte légère et fréquente vers data/rss/<jour>.jsonl, importée dans la base à chaque passage.

Un flux RSS ne garde que ses derniers articles (quelques heures à deux jours). Un passage du radar manqué,
retardé ou le week-end faisait donc perdre définitivement les articles de la période, et le calibrage des
technologies (30 jours actifs exigés) avançait moins vite. La collecte horaire (python -m radar.rss) n'utilise
que la bibliothèque standard : elle démarre en quelques secondes, sans la base ni pandas.
"""
import datetime as dt
import email.utils
import json
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

from .events import article_id

UA = {"User-Agent": "radar-bourse/0.2"}


def parse(content, name, today=None):
    """Lignes (id, jour, source, titre, texte, lien) d'un flux RSS."""
    today = today or dt.datetime.now(dt.timezone.utc).date().isoformat()
    rows = []
    for it in ET.fromstring(content).iter("item"):
        title = (it.findtext("title") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "").strip()
        link = it.findtext("link") or ""
        try:
            day = email.utils.parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
        except Exception:
            day = today
        if title:
            rows.append((article_id(name, title, day), day, name, title, desc, link))
    return rows


def fetch(feeds, timeout=20):
    """Toutes les lignes des flux, et la liste des flux en échec. Ne lève jamais."""
    rows, ko = [], []
    for name, url in feeds.items():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                rows += parse(r.read(), name)
        except Exception as e:  # une source en panne ne bloque rien
            ko.append(f"flux {name} : {type(e).__name__}")
    return rows, ko


def save(rows, root):
    """Ajoute les articles nouveaux dans data/rss/<jour>.jsonl (un fichier par jour de publication)."""
    d = pathlib.Path(root) / "data" / "rss"
    d.mkdir(parents=True, exist_ok=True)
    by_day, n = {}, 0
    for r in rows:
        by_day.setdefault(r[1], []).append(r)
    for day, rs in by_day.items():
        p = d / f"{day}.jsonl"
        seen = {json.loads(line)["id"] for line in p.read_text().splitlines() if line.strip()} if p.exists() else set()
        new = [r for r in rs if r[0] not in seen and not seen.add(r[0])]
        if new:
            with p.open("a", encoding="utf-8") as f:
                for r in new:
                    f.write(json.dumps(dict(zip(("id", "date", "source", "title", "text", "url"), r)), ensure_ascii=False) + "\n")
            n += len(new)
    return n


def load(root):
    """Toutes les lignes conservées dans data/rss, pour import dans la base (INSERT OR IGNORE)."""
    rows = []
    for p in sorted((pathlib.Path(root) / "data" / "rss").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                a = json.loads(line)
                rows.append((a["id"], a["date"], a["source"], a["title"], a["text"], a["url"]))
    return rows


def _feeds(cfg_path):
    """Lit la section feeds de config.yaml sans PyYAML (collecte légère)."""
    feeds, inside = {}, False
    for line in pathlib.Path(cfg_path).read_text(encoding="utf-8").splitlines():
        if re.match(r"^feeds\s*:", line):
            inside = True
            continue
        if inside:
            m = re.match(r"^\s+([\w-]+)\s*:\s*(\S+)", line)
            if m:
                feeds[m.group(1)] = m.group(2)
            elif line.strip() and not line.startswith((" ", "\t", "#")):
                break
    return feeds


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parents[1]
    rows, ko = fetch(_feeds(root / "config.yaml"))
    n = save(rows, root)
    print(json.dumps({"articles_lus": len(rows), "nouveaux": n, "echecs": ko}, ensure_ascii=False))
    sys.exit(0)
