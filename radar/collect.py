"""Collecte : mode démo (données synthétiques avec effets cachés) et mode live."""
import email.utils
import re
import datetime as dt

import numpy as np
import pandas as pd

from .events import EXPOSURE, SENSITIVE, SECTORS, article_id

# (titre, ton) : le ton du gabarit correspond au ton mesuré par le lexique.
TEMPLATES = {
    "militaire": [("Offensive militaire : frappes de missiles et attaque à la frontière", -1),
                  ("Cessez-le-feu signé, accord de paix après la guerre", 1),
                  ("L'OTAN annonce un déploiement de troupes en exercice", 0)],
    "securitaire": [("Cyberattaque massive : un ransomware paralyse des hôpitaux, la menace s'étend", -1),
                    ("Succès d'une opération contre l'espionnage : sécurité des infrastructures renforcée, soutien des alliés", 1),
                    ("Sabotage présumé : alerte sécurité sur des câbles sous-marins", 0)],
    "politique": [("Sanction et droits de douane : tension entre le gouvernement et ses partenaires", -1),
                  ("Accord au parlement : vote d'une réforme et relance du budget", 1),
                  ("Sommet diplomatique : le président reçoit les dirigeants", 0)],
    "financier": [("La banque centrale maintient ses taux d'intérêt, crise de liquidité et baisse des marchés", -1),
                  ("Les résultats trimestriels dépassent les attentes : bénéfice en hausse et dividende relevé", 1),
                  ("Annonce d'un rachat d'actions et d'une acquisition", 0)],
    "meteo": [("Ouragan et inondation : dégâts importants, canicule prévue", -1),
              ("Tempête sur la côte, vigilance météo", 0),
              ("Sécheresse persistante : alerte climat sur les récoltes", -1)],
    "economique": [("Récession : le PIB recule, le chômage grimpe, la dette s'aggrave", -1),
                   ("Croissance solide : reprise de l'emploi et hausse de la consommation", 1),
                   ("Inflation stable, le pétrole oscille", 0)],
    "scientifique": [("Percée scientifique : une découverte majeure en laboratoire, succès de l'essai clinique", 1),
                     ("Nouvelle étude et brevet déposé pour un prototype innovant", 0),
                     ("Échec du lancement : la recherche spatiale subit un revers", -1)],
    "religieux": [("Tensions autour d'un lieu de culte : le pape appelle au calme, l'église et la mosquée en alerte", -1),
                  ("Pèlerinage et ramadan : grande affluence religieuse", 0),
                  ("Accord interreligieux : le vatican salue la paix", 1)],
    "media": [("Scandale et polémique : enquête ouverte, démission réclamée", -1),
              ("Rumeur virale : fuite d'un document et procès annoncé", 0),
              ("Grève et licenciements annoncés dans le secteur", -1)],
}
COMPANY_TPL = [("{c} : scandale et enquête, l'action chute", -1),
               ("{c} publie des résultats record, bénéfice en hausse", 1),
               ("{c} : rappel de produits et amende annoncée", -1),
               ("{c} signe un accord majeur, investissement en croissance", 1)]
# Effet réel caché (démo) : certaines catégories n'ont aucun effet, l'outil doit le découvrir.
TRUE_COEF = {"militaire": 1.0, "securitaire": 0.6, "politique": 0.5, "financier": 1.0, "meteo": 0.3,
             "economique": 0.8, "scientifique": 0.7, "religieux": 0.0, "media": 0.2}
TECH_PHRASE = {"ia": "l'intelligence artificielle", "semi-conducteurs": "les semi-conducteurs",
               "quantique": "l'informatique quantique", "hydrogene": "l'hydrogène", "batteries": "les batteries",
               "drones": "les drones", "cyber": "la cybersécurité", "spatial": "le secteur spatial",
               "robotique": "la robotique", "biotech": "la biotech", "cloud": "le cloud", "nucleaire": "le nucléaire"}


def demo_generate(cfg, con):
    rng = np.random.default_rng(cfg["demo"]["seed"])
    wl = cfg["watchlist"]
    tickers = list(wl)
    n = int(cfg["demo"]["years"] * 252)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    sect = {t: wl[t]["sector"] for t in tickers}
    sectors = sorted(set(sect.values()))
    sources = cfg["demo"]["sources"]
    amp = cfg["demo"]["shock"]
    shock = {s: np.zeros(n) for s in sectors}
    tshock = {t: np.zeros(n) for t in tickers}
    cats = list(TEMPLATES)
    techs = list(TECH_PHRASE)
    arts = []
    for i, d in enumerate(dates):
        recent = i >= n - 8
        for j in range(rng.poisson(3)):
            src = list(sources)[rng.integers(len(sources))]
            real = rng.random() < sources[src]
            if rng.random() < 0.25:
                t = tickers[rng.integers(len(tickers))]
                tpl, pol = COMPANY_TPL[rng.integers(len(COMPANY_TPL))]
                title = tpl.format(c=wl[t]["name"])
                if real:
                    tshock[t][i + 1:i + 4] += pol * 0.010 * amp / 0.008 / 3
                body = ""
            else:
                cat = cats[rng.integers(len(cats))]
                title, pol = TEMPLATES[cat][rng.integers(3)]
                if real:
                    for s in sectors:
                        eff = TRUE_COEF[cat] * EXPOSURE[cat].get(s, 0) * (pol if cat in SENSITIVE else 1)
                        shock[s][i + 1:i + 4] += amp * eff / 3
                body = ""
                if rng.random() < (0.35 if recent else 0.2):
                    tech = (["quantique", "drones"][rng.integers(2)] if recent and rng.random() < 0.5
                            else techs[rng.integers(len(techs))])
                    body = f"Les analystes suivent de près {TECH_PHRASE[tech]}."
            day = d.strftime("%Y-%m-%d")
            arts.append((article_id(src, title, f"{day}-{j}"), day, src, title, body, f"demo://{i}-{j}"))
    con.executemany("INSERT OR REPLACE INTO articles VALUES (?,?,?,?,?,?)", arts)
    mkt = rng.normal(0.0003, 0.008, n)
    secf = {s: rng.normal(0, 0.006, n) + shock[s] for s in sectors}
    rows = []
    for t in tickers:
        r = mkt + secf[sect[t]] + tshock[t] + rng.normal(0, 0.011, n)
        price = rng.uniform(50, 400) * np.cumprod(1 + r)
        vol = rng.lognormal(15, 0.3, n)
        rows += [(t, d.strftime("%Y-%m-%d"), float(p), float(v)) for d, p, v in zip(dates, price, vol)]
    con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?)", rows)
    con.commit()


STOOQ_SUFFIX = {"PA": "fr", "AS": "nl", "DE": "de", "L": "uk"}


def _stooq_symbol(t):
    if "." in t:
        base, suf = t.rsplit(".", 1)
        return f"{base.lower()}.{STOOQ_SUFFIX.get(suf, suf.lower())}"
    return f"{t.lower()}.us"


def _prices_yfinance(tickers):
    import yfinance as yf
    data = yf.download(tickers, period="3y", auto_adjust=True, progress=False, group_by="column", threads=False)
    close, vol = data["Close"], data["Volume"]
    rows = []
    for t in tickers:
        if t not in close:
            continue
        for d, p in close[t].dropna().items():
            v = vol[t].get(d, 0)
            rows.append((t, d.strftime("%Y-%m-%d"), float(p), float(v) if v == v else 0.0))
    return rows


def _prices_stooq(tickers):
    import io
    import requests
    rows = []
    for t in tickers:
        try:
            r = requests.get(f"https://stooq.com/q/d/l/?s={_stooq_symbol(t)}&i=d", timeout=20,
                             headers={"User-Agent": "radar-bourse/0.2"})
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            if "Close" not in df:
                continue
            for d, p, v in zip(df["Date"].tail(800), df["Close"].tail(800), df.get("Volume", pd.Series(0, index=df.index)).tail(800)):
                rows.append((t, str(d), float(p), float(v) if v == v else 0.0))
        except Exception:
            continue
    return rows


def collect_prices_live(cfg, con):
    """yfinance, puis Stooq en secours pour les valeurs manquantes. Ne lève jamais : renvoie un état."""
    tickers = list(cfg["watchlist"])
    errs, got, src = [], set(), []
    for name, fn in (("yfinance", _prices_yfinance), ("stooq", _prices_stooq)):
        missing = [t for t in tickers if t not in got]
        if not missing:
            break
        try:
            rows = fn(missing)
        except Exception as e:
            errs.append(f"cours {name} : {type(e).__name__} {str(e)[:80]}")
            continue
        if rows:
            con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?)", rows)
            con.commit()
            new = {r[0] for r in rows}
            got |= new
            src.append(f"{name} ({len(new)})")
    missing = [t for t in tickers if t not in got]
    if missing:
        errs.append("cours non mis à jour : " + ", ".join(missing))
    return {"sources": src, "manquants": missing}, errs


def collect_news_live(cfg, con):
    import requests
    import xml.etree.ElementTree as ET
    ok, ko = 0, []
    for name, url in cfg["feeds"].items():
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "radar-bourse/0.2"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:  # une source en panne ne bloque pas le pipeline
            ko.append(f"flux {name} : {type(e).__name__}")
            continue
        rows = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "").strip()
            link = it.findtext("link") or ""
            try:
                day = email.utils.parsedate_to_datetime(it.findtext("pubDate")).date().isoformat()
            except Exception:
                day = dt.date.today().isoformat()
            if title:
                rows.append((article_id(name, title, day), day, name, title, desc, link))
        con.executemany("INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?)", rows)
        ok += 1
    con.commit()
    return ok, ko


# ---------------------------------------------------------------- GDELT (historique mondial d'actualités)
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_CATS = {
    "militaire": '(war OR missile OR airstrike OR invasion OR ceasefire OR "military offensive")',
    "securitaire": '(terrorism OR cyberattack OR ransomware OR espionage OR sabotage OR hostage)',
    "politique": '(election OR sanctions OR tariffs OR parliament OR referendum OR "government reform")',
    "financier": '("interest rates" OR "central bank" OR earnings OR dividend OR "bond yields" OR buyback)',
    "meteo": '(hurricane OR drought OR heatwave OR flood OR wildfire OR earthquake)',
    "economique": '(inflation OR recession OR unemployment OR "economic growth" OR "supply chain" OR "oil prices")',
    "scientifique": '("scientific breakthrough" OR "clinical trial" OR patent OR "research study" OR discovery OR prototype)',
    "religieux": '(church OR vatican OR mosque OR religious OR pilgrimage OR synagogue)',
    "media": '(scandal OR lawsuit OR boycott OR layoffs OR strike OR resignation)',
}


def parse_gdelt_timeline(js):
    """{'timeline':[{'series':..,'data':[{'date':'20240101T000000Z','value':1.2},..]}]} -> {date: valeur}"""
    out = {}
    for serie in (js or {}).get("timeline", [])[:1]:
        for pt in serie.get("data", []):
            d = str(pt.get("date", ""))[:8]
            if len(d) == 8 and d.isdigit():
                out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(pt.get("value", 0) or 0)
    return out


def _gdelt_get(query, mode, start, end, pause):
    import time
    import requests
    params = {"query": query, "mode": mode, "format": "json",
              "startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    for attempt in range(3):
        time.sleep(pause)  # limite officielle : une requête toutes les 5 secondes
        r = requests.get(GDELT_URL, params=params, timeout=60, headers={"User-Agent": "radar-bourse/0.2"})
        if r.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return parse_gdelt_timeline(r.json())
    raise RuntimeError("limite de débit GDELT")


def collect_gdelt(cfg, con):
    """Séries quotidiennes volume + ton, par catégorie et par entreprise. 3 ans au premier passage,
    puis mise à jour incrémentale. Budget de temps borné ; reprend là où il s'est arrêté."""
    import time
    g = cfg.get("gdelt", {})
    if not g.get("enabled", True):
        return 0, []
    pause, budget = g.get("pause", 6), g.get("budget_s", 900)
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    keys = [("cat", c, q) for c, q in GDELT_CATS.items()]
    for t, v in cfg["watchlist"].items():
        keys.append(("ticker", t, v.get("gdelt") or f'"{v["name"]}"'))
    last = dict(con.execute("SELECT kind||'|'||key, MAX(date) FROM gdelt GROUP BY kind,key").fetchall())
    keys.sort(key=lambda k: last.get(f"{k[0]}|{k[1]}", ""))  # les séries les plus en retard d'abord
    t0, done, errs = time.time(), 0, []
    for kind, key, query in keys:
        if time.time() - t0 > budget:
            errs.append(f"GDELT : budget de temps atteint, {len(keys) - done} séries reportées")
            break
        l = last.get(f"{kind}|{key}")
        start = (dt.datetime.fromisoformat(l) - dt.timedelta(days=3)) if l else now - dt.timedelta(days=int(g.get("years", 3) * 365))
        try:
            vol = _gdelt_get(query, "timelinevol", start, now, pause)
            tone = _gdelt_get(query, "timelinetone", start, now, pause)
        except Exception as e:
            errs.append(f"GDELT {key} : {type(e).__name__}")
            if len(errs) >= 4 and done == 0:
                errs.append("GDELT : abandon (source injoignable)")
                break
            continue
        con.executemany("INSERT OR REPLACE INTO gdelt VALUES (?,?,?,?,?)",
                        [(kind, key, d, v, tone.get(d)) for d, v in vol.items()])
        con.commit()
        done += 1
    return done, errs
