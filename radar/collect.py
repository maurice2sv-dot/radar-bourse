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


def _open_day():
    """Date à écarter (séance peut-être en cours). Après 22 h UTC, New York a clôturé : rien à écarter."""
    now = dt.datetime.now(dt.timezone.utc)
    return now.strftime("%Y-%m-%d") if now.hour < 22 else "9999-12-31"


STOOQ_SUFFIX = {"PA": "fr", "AS": "nl", "DE": "de", "L": "uk"}


def _stooq_symbol(t):
    if "." in t:
        base, suf = t.rsplit(".", 1)
        return f"{base.lower()}.{STOOQ_SUFFIX.get(suf, suf.lower())}"
    return f"{t.lower()}.us"


def _prices_yfinance(tickers, years=10):
    import yfinance as yf
    data = yf.download(tickers, period=f"{years}y", auto_adjust=True, progress=False, group_by="column", threads=False)
    close, vol = data["Close"], data["Volume"]
    rows, today = [], _open_day()
    for t in tickers:
        if t not in close:
            continue
        for d, p in close[t].dropna().items():
            if d.strftime("%Y-%m-%d") >= today:
                continue  # séance en cours : cours partiel, écarté
            v = vol[t].get(d, 0)
            rows.append((t, d.strftime("%Y-%m-%d"), float(p), float(v) if v == v else 0.0))
    return rows


def _prices_stooq(tickers, years=10):
    import io
    import requests
    rows, today = [], _open_day()
    for t in tickers:
        try:
            r = requests.get(f"https://stooq.com/q/d/l/?s={_stooq_symbol(t)}&i=d", timeout=20,
                             headers={"User-Agent": "radar-bourse/0.2"})
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            if "Close" not in df:
                continue
            k = 262 * years
            for d, p, v in zip(df["Date"].tail(k), df["Close"].tail(k), df.get("Volume", pd.Series(0, index=df.index)).tail(k)):
                if str(d) < today:
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
            rows = fn(missing, cfg.get("historique_ans", 10))
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


def collect_earnings_live(cfg, con):
    """Dates et surprises de résultats (yfinance). Rafraîchit chaque passage les valeurs les plus anciennes,
    pour couvrir tout l'univers en une semaine. Ne lève jamais : renvoie un état et des anomalies."""
    tickers = list(cfg["watchlist"])
    cap = cfg.get("calendrier", {}).get("max_par_passage", 70)
    now = dt.datetime.now(dt.timezone.utc)
    seen = dict(con.execute("SELECT ticker, fetched FROM earnings_fetch").fetchall())
    lim = (now - dt.timedelta(days=6)).isoformat()
    todo = sorted([t for t in tickers if seen.get(t, "") < lim], key=lambda t: seen.get(t, ""))[:cap]
    if not todo:
        return {"rafraichies": 0}, []
    try:
        import yfinance as yf
    except Exception as e:
        return {"rafraichies": 0}, [f"calendrier des résultats : {type(e).__name__}"]
    ok, vides, ko = 0, [], []
    for t in todo:
        try:
            e = yf.Ticker(t).get_earnings_dates(limit=16)
        except Exception as ex:
            ko.append(t)
            if len(ko) >= 8 and ok == 0:
                break  # source manifestement indisponible : inutile d'insister
            continue
        rows = []
        if e is not None and len(e):
            col = lambda *names: next((e[n] for n in names if n in e), pd.Series(np.nan, index=e.index))
            est, act, sur = col("EPS Estimate"), col("Reported EPS"), col("Surprise(%)")
            for d, a, b, c in zip(e.index, est, act, sur):
                day = pd.Timestamp(d).strftime("%Y-%m-%d")
                f = lambda x: None if x is None or x != x else float(x)
                rows.append((t, day, f(a), f(b), None if f(c) is None else f(c) / 100))
        else:
            vides.append(t)
        con.executemany("INSERT OR REPLACE INTO earnings VALUES (?,?,?,?,?)", rows)
        con.execute("INSERT OR REPLACE INTO earnings_fetch VALUES (?,?,?)", (t, now.isoformat(), len(rows)))
        ok += 1
    con.commit()
    errs = []
    if ko:
        errs.append(f"calendrier des résultats : {len(ko)} valeurs en échec sur {len(todo)} (reprise au prochain passage)")
    return {"rafraichies": ok, "sans_donnees": len(vides)}, errs


def collect_macro_live(cfg, con):
    """Indicateurs de marché (VIX, taux, pétrole, dollar, or). Ne lève jamais."""
    syms = cfg.get("marches", {})
    if not syms:
        return 0, []
    try:
        import yfinance as yf
        data = yf.download(list(syms.values()), period=f"{cfg.get('historique_ans', 10)}y", auto_adjust=True, progress=False, group_by="column", threads=False)
        close = data["Close"]
    except Exception as e:
        return 0, [f"indicateurs de marché : {type(e).__name__}"]
    today, rows, missing = _open_day(), [], []
    for lab, s in syms.items():
        if s not in close or close[s].dropna().empty:
            missing.append(lab)
            continue
        rows += [(s, d.strftime("%Y-%m-%d"), float(v)) for d, v in close[s].dropna().items() if d.strftime("%Y-%m-%d") < today]
    con.executemany("INSERT OR REPLACE INTO macro VALUES (?,?,?)", rows)
    con.commit()
    return len(syms) - len(missing), ([f"indicateurs indisponibles : {', '.join(missing)}"] if missing else [])


# ---------------------------------------------------------------- Lot 5 : fondamentaux SEC (EDGAR, données datées)
SEC_CONCEPTS = {
    "us-gaap": ["NetIncomeLoss", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "StockholdersEquity", "Liabilities", "Assets"],
    "dei": ["EntityCommonStockSharesOutstanding"],
}


def collect_fundamentals_live(cfg, con):
    """Comptes officiels des sociétés américaines. Chaque chiffre garde sa date de dépôt : le modèle ne l'utilise
    qu'à partir du lendemain (pas de regard vers le futur). Seule la première publication de chaque période est
    gardée (les retraitements ultérieurs n'étaient pas connus à l'époque). Ne lève jamais."""
    import time
    import requests
    f = cfg.get("fondamentaux", {})
    import os
    ua = os.environ.get("SEC_CONTACT", "").strip()
    if not ua:
        return {"rafraichies": 0}, ["fondamentaux SEC : secret SEC_CONTACT absent (contact exigé par la SEC)"]
    H = {"User-Agent": ua if " " in ua else f"radar-bourse {ua}", "Accept-Encoding": "gzip, deflate"}
    us = [t for t in cfg["watchlist"] if "." not in t]
    if con.execute("SELECT COUNT(*) FROM sec_cik").fetchone()[0] == 0:
        try:
            r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=H, timeout=30)
            r.raise_for_status()
            con.executemany("INSERT OR REPLACE INTO sec_cik VALUES (?,?)",
                            [(v["ticker"].upper(), int(v["cik_str"])) for v in r.json().values()])
            con.commit()
        except Exception as e:
            return {"rafraichies": 0}, [f"fondamentaux SEC : {type(e).__name__} {str(e)[:60]}"]
    cik = dict(con.execute("SELECT ticker, cik FROM sec_cik").fetchall())
    seen = dict(con.execute("SELECT ticker, fetched FROM fund_fetch").fetchall())
    now = dt.datetime.now(dt.timezone.utc)
    lim = (now - dt.timedelta(days=7)).isoformat()
    todo = sorted([t for t in us if t in cik and seen.get(t, "") < lim], key=lambda t: seen.get(t, ""))[:f.get("max_par_passage", 25)]
    ok, ko = 0, []
    for t in todo:
        time.sleep(0.25)  # la SEC limite à 10 requêtes par seconde
        try:
            r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik[t]:010d}.json", headers=H, timeout=60)
            r.raise_for_status()
            js = r.json()
        except Exception:
            ko.append(t)
            if len(ko) >= 5 and ok == 0:
                break
            continue
        first = {}
        for tax, names in SEC_CONCEPTS.items():
            facts = js.get("facts", {}).get(tax, {})
            for c in names:
                for lst in facts.get(c, {}).get("units", {}).values():
                    for x in lst:
                        if x.get("filed") and x.get("end") and x.get("val") is not None:
                            k = (c, x.get("start"), x["end"])
                            if k not in first or x["filed"] < first[k][1]:
                                first[k] = (x.get("form", ""), x["filed"], float(x["val"]))
        con.execute("DELETE FROM fundamentals WHERE ticker=?", (t,))
        con.executemany("INSERT INTO fundamentals VALUES (?,?,?,?,?,?,?)",
                        [(t, c, s, e, fl, fo, v) for (c, s, e), (fo, fl, v) in first.items()])
        con.execute("INSERT OR REPLACE INTO fund_fetch VALUES (?,?,?)", (t, now.isoformat(), len(first)))
        ok += 1
    con.commit()
    errs = [f"fondamentaux SEC : {len(ko)} valeurs en échec sur {len(todo)}"] if ko else []
    return {"rafraichies": ok, "sans_cik": len([t for t in us if t not in cik])}, errs
