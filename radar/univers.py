"""Univers élargi (environ 500 valeurs) et appartenance historique, contre le biais du survivant.

- Base : les valeurs de config.yaml (américaines et européennes), toujours suivies, seules utilisées pour
  reconnaître les entreprises dans la presse (noms vérifiés à la main).
- S&P 500 : composition actuelle et changements depuis la page Wikipedia de l'indice, rafraîchis chaque
  semaine et conservés dans data/univers.json (le dépôt garde la dernière version connue si la page est
  inaccessible).
- Appartenance historique : une valeur ne compte, pour l'entraînement, l'évaluation et les moyennes, qu'aux
  dates où elle faisait partie de l'indice. Les valeurs sorties de l'indice depuis 2016 et encore cotées
  sont ajoutées sur leur période d'appartenance : le passé n'est plus vu uniquement à travers les gagnants
  d'aujourd'hui. Les valeurs européennes de la base restent considérées comme membres sur toute la période
  (biais résiduel, signalé).
"""
import datetime as dt
import io
import json
import pathlib

import numpy as np
import pandas as pd

WIKI = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = {"User-Agent": "radar-bourse/0.3 (projet personnel de veille ; https://github.com/maurice2sv-dot/radar-bourse)"}
DEBUT_SORTIES = "2016-01-01"
DIAG = ""
REFRESH_JOURS = 7

GICS = {"Information Technology": "tech", "Communication Services": "telecom", "Consumer Discretionary": "conso",
        "Consumer Staples": "distribution", "Health Care": "sante", "Financials": "finance", "Industrials": "industrie",
        "Energy": "energie", "Materials": "materiaux", "Utilities": "services_publics", "Real Estate": "immobilier"}
YAHOO = {"Technology": "tech", "Communication Services": "telecom", "Consumer Cyclical": "conso",
         "Consumer Defensive": "distribution", "Healthcare": "sante", "Financial Services": "finance",
         "Industrials": "industrie", "Energy": "energie", "Basic Materials": "materiaux", "Utilities": "services_publics",
         "Real Estate": "immobilier"}


def yahoo_ticker(t):
    return str(t).strip().upper().replace(".", "-")


def _sector(gics, sub=""):
    sub = (sub or "").lower()
    if "automobile manufacturers" in sub:
        return "auto"
    if "aerospace" in sub and "defense" in sub:
        return "defense"
    return GICS.get(gics)


def _date(x):
    d = pd.to_datetime(str(x).split("(")[0].strip(), errors="coerce")
    return None if pd.isna(d) else d.strftime("%Y-%m-%d")


def _flat(t):
    if isinstance(t.columns, pd.MultiIndex):
        t = t.copy()
        t.columns = ["_".join(dict.fromkeys(str(x) for x in c if not str(x).startswith("Unnamed"))) for c in t.columns]
    return t


def _find(cols, *keys):
    return next((c for c in cols if all(k in str(c).lower() for k in keys)), None)


def parse_wikipedia(html):
    """Renvoie (membres actuels, changements). Lève une exception explicite si la page n'a pas la forme attendue.
    Tolérant aux variations de présentation (noms de colonnes, en-têtes sur deux lignes)."""
    tables = [_flat(t) for t in pd.read_html(io.StringIO(html))]
    cur = next((t for t in tables if (_find(t.columns, "symbol") or _find(t.columns, "ticker"))
                and _find(t.columns, "sector") and len(t) >= 400), None)
    if cur is None:
        apercu = " | ".join(",".join(str(c)[:15] for c in list(t.columns)[:4]) for t in tables[:3])
        raise ValueError(f"table des membres introuvable ({len(tables)} tables : {apercu})")
    sym = _find(cur.columns, "symbol") or _find(cur.columns, "ticker")
    nom = _find(cur.columns, "security") or _find(cur.columns, "company") or sym
    gs = _find(cur.columns, "sector")
    sub = _find(cur.columns, "sub")
    add = _find(cur.columns, "date", "add")
    membres = [{"ticker": yahoo_ticker(d[sym]), "name": str(d[nom]), "sector": _sector(str(d[gs]).strip(), d[sub] if sub else ""),
                "depuis": _date(d[add]) if add else None} for _, d in cur.iterrows()]
    changements = []
    global DIAG
    DIAG = " | ".join(",".join(str(c)[:18] for c in list(t.columns)[:6]) for t in tables[1:4])
    chg = next((t for t in tables if t is not cur and (_find(t.columns, "removed") or _find(t.columns, "added"))), None)
    if chg is not None:
        cd = _find(chg.columns, "date") or chg.columns[0]
        at = _find(chg.columns, "added", "ticker") or _find(chg.columns, "added", "symbol")
        rt = _find(chg.columns, "removed", "ticker") or _find(chg.columns, "removed", "symbol")
        rs = _find(chg.columns, "removed", "secur") or _find(chg.columns, "removed", "compan")
        if not (at and rt) and chg.shape[1] >= 5:
            # en-tête sur deux lignes lu comme une seule : ordre standard date, ajout (symbole, nom), retrait (symbole, nom)
            cd, at, _, rt, rs = list(chg.columns[:5])
        if at and rt:
            for _, r in chg.iterrows():
                d = _date(r[cd])
                if not d:
                    continue  # ligne d'en-tête répétée ou date illisible
                ok = lambda v: isinstance(v, str) and v.strip() and v.strip().lower() not in ("ticker", "symbol")
                a = yahoo_ticker(r[at]) if ok(r[at]) else None
                x = yahoo_ticker(r[rt]) if ok(r[rt]) else None
                changements.append({"date": d, "ajout": a, "retrait": x,
                                    "nom_retrait": str(r[rs]) if x and rs else None})
    if len(membres) < 400:
        raise ValueError(f"composition inattendue ({len(membres)} valeurs)")
    return membres, changements


def intervalles(membres, changements):
    """Périodes d'appartenance [début, fin) par valeur, reconstruites à rebours depuis la composition actuelle."""
    out, noms = {}, {}
    for m in membres:
        out[m["ticker"]] = [[m.get("depuis"), None]]
        noms[m["ticker"]] = m["name"]
    mot = lambda s: (str(s or "").split() or [""])[0].lower().strip(".,")
    for c in sorted(changements, key=lambda c: c["date"], reverse=True):
        x = c["retrait"]
        if x and c["date"] >= DEBUT_SORTIES:
            if x in noms and mot(noms[x]) != mot(c.get("nom_retrait")):
                pass  # symbole réattribué à une autre société : l'ancienne n'a plus de cours sous ce symbole
            else:
                per = out.setdefault(x, [])
                if not per or (per[0][0] is not None and per[0][0] >= c["date"]):
                    per.insert(0, [None, c["date"]])  # début fixé plus loin si un ajout antérieur est trouvé
        a = c["ajout"]
        if a and a in out:
            for p in out[a]:
                if p[0] is None and (p[1] is None or p[1] > c["date"]):
                    p[0] = c["date"]
                    break
    return out


def _fetch_html():
    import requests
    r = requests.get(WIKI, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def _secteurs_yahoo(tickers, budget=60):
    """Secteur des valeurs sorties de l'indice (absent de Wikipedia), demandé à Yahoo par petits lots."""
    import yfinance as yf
    out = {}
    for t in tickers[:budget]:
        try:
            info = yf.Ticker(t).get_info()
            out[t] = YAHOO.get(info.get("sector")) or ""
            out[t + "|nom"] = info.get("shortName") or ""
        except Exception:
            out[t] = None
    return out


def load(cfg, root=".", live=True, now=None):
    """Univers complet {ticker: fiche}, périodes d'appartenance et journal. Ne lève jamais."""
    root = pathlib.Path(root)
    path = root / "data" / "univers.json"
    base = {t: dict(v, base=True) for t, v in cfg["watchlist"].items()}
    log, errs = {}, []
    if not cfg.get("univers", {}).get("sp500", False):
        return base, {t: [[None, None]] for t in base}, log, errs
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    now = now or dt.datetime.now(dt.timezone.utc)
    age = (now - dt.datetime.fromisoformat(cache["maj"])).days if cache.get("maj") else 999
    if live and (age >= REFRESH_JOURS or not cache.get("changements")):
        try:
            membres, chg = parse_wikipedia(_fetch_html())
            if not chg:
                errs.append("univers S&P 500 : historique des changements illisible, appartenance limitée aux dates d'entrée"
                            f" (tables lues : {DIAG[:200]})")
            elif not any(c["retrait"] for c in chg):
                errs.append("univers S&P 500 : aucune sortie lue dans l'historique des changements")
            cache.update({"maj": now.isoformat(), "membres": membres, "changements": chg})
            log["univers"] = f"S&P 500 rafraîchi ({len(membres)} membres, {len(chg)} changements)"
        except Exception as e:
            errs.append(f"univers S&P 500 : {type(e).__name__} {str(e)[:60]} (dernière version connue conservée)")
    if not cache.get("membres"):
        return base, {t: [[None, None]] for t in base}, log, errs
    per = intervalles(cache["membres"], cache.get("changements", []))
    secteurs = cache.setdefault("secteurs_sortis", {})
    actuels = {m["ticker"]: m for m in cache["membres"]}
    sortis = [t for t in per if t not in actuels and t not in base]
    if live:
        todo = [t for t in sortis if t not in secteurs or secteurs[t] is None]
        if todo:
            try:
                secteurs.update(_secteurs_yahoo(todo))
            except Exception as e:
                errs.append(f"secteurs des valeurs sorties : {type(e).__name__}")
    try:
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass

    wl = dict(base)
    for t, m in actuels.items():
        if t in wl:
            continue
        if m["sector"]:
            wl[t] = {"name": m["name"], "sector": m["sector"], "base": False}
    noms = {c["retrait"]: c["nom_retrait"] for c in cache.get("changements", []) if c["retrait"]}
    for t in sortis:
        if secteurs.get(t):
            wl[t] = {"name": secteurs.get(t + "|nom") or noms.get(t) or t, "sector": secteurs[t], "base": False,
                     "sorti": True}
    membership = {}
    for t in wl:
        if t in per:
            membership[t] = per[t]
        else:  # base européenne (ou américaine hors indice) : membre sur toute la période
            membership[t] = [[None, None]]
    n_act = sum(1 for t in wl if is_active(membership[t]))
    log["valeurs"] = {"actives": n_act, "sorties_suivies": sum(1 for v in wl.values() if v.get("sorti")),
                      "secteur_manquant": sum(1 for t in sortis if secteurs.get(t) in (None, ""))}
    return wl, membership, log, errs


def is_active(periods):
    return any(p[1] is None for p in periods)


def mask(membership, index, columns):
    """Tableau booléen dates × valeurs : vrai si la valeur appartient à l'univers à cette date."""
    m = np.zeros((len(index), len(columns)), dtype=bool)
    iv = pd.DatetimeIndex(index)
    for j, t in enumerate(columns):
        for a, b in membership.get(t, [[None, None]]):
            ok = np.ones(len(iv), dtype=bool)
            if a:
                ok &= iv >= pd.Timestamp(a)
            if b:
                ok &= iv < pd.Timestamp(b)
            m[:, j] |= ok
    return pd.DataFrame(m, index=index, columns=columns)
