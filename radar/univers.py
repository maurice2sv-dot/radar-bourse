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
# Changements de symbole d'une même société (ancien, nouveau). Le fichier historique liste les symboles de l'époque :
# sans ce raccord, l'historique de META avant juin 2022 (alors FB) était écarté. Un couple n'est appliqué que si le
# fichier historique le confirme (fin de l'ancien le jour exact du début du nouveau) et si l'ancien symbole n'a plus
# de cours chez Yahoo (aucun secteur trouvé) : ses périodes passent alors au nouveau symbole, qui porte l'historique.
RENOMMAGES = [("FB", "META"), ("UTX", "RTX"), ("ANTM", "ELV"), ("CBS", "VIAC"), ("VIAC", "PARA"), ("HRS", "LHX"),
              ("COG", "CTRA"), ("FI", "FISV"), ("FISV", "FI"), ("RE", "EG"), ("FLT", "CPAY"), ("PKI", "RVTY"),
              ("ABC", "COR"), ("WLTW", "WTW"), ("BLL", "BALL"), ("CDAY", "DAY"), ("SYMC", "NLOK"), ("NLOK", "GEN"),
              ("HCP", "PEAK"), ("PEAK", "DOC"), ("DWDP", "DD"), ("TMK", "GL"), ("BHGE", "BKR"), ("CTL", "LUMN"),
              ("DISCA", "WBD"), ("MYL", "VTRS"), ("JEC", "J"), ("ARNC", "HWM"), ("PARA", "PSKY"), ("GPS", "GAP"),
              ("FBHS", "FBIN"), ("KORS", "CPRI"), ("RTN", "RTX")]

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


FJA = "https://api.github.com/repos/fja05680/sp500/contents"


def historique_fja(token=None):
    """Composition historique du S&P 500 tenue dans le dépôt public fja05680/sp500 (une ligne par date de changement,
    liste complète des membres). Renvoie {symbole: [[début, fin), ...]} depuis 2016 et la dernière date couverte."""
    import re
    import requests
    h = {"Accept": "application/vnd.github+json", **UA}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.get(FJA, headers=h, timeout=30)
    r.raise_for_status()
    def quand(nom):
        m = re.search(r"\((\d{2})-(\d{2})-(\d{4})\)", nom)
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ""
    fichiers = [x for x in r.json() if x["name"].lower().endswith(".csv") and "historical components" in x["name"].lower()]
    if not fichiers:
        raise ValueError("aucun fichier de composition historique")
    f = max(fichiers, key=lambda x: quand(x["name"]))
    df = pd.read_csv(io.StringIO(requests.get(f["download_url"], headers=UA, timeout=60).text))
    dcol = next(c for c in df.columns if "date" in c.lower())
    tcol = next(c for c in df.columns if "ticker" in c.lower())
    df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
    df = df.dropna(subset=[dcol]).sort_values(dcol)
    # point de départ : la composition en vigueur au 1er janvier 2016
    avant = df[df[dcol] <= pd.Timestamp(DEBUT_SORTIES)]
    df = pd.concat([avant.tail(1), df[df[dcol] > pd.Timestamp(DEBUT_SORTIES)]])
    per, ouverts, fin = {}, {}, None
    for d, tk in zip(df[dcol], df[tcol]):
        d = d.strftime("%Y-%m-%d")
        cur = {yahoo_ticker(x) for x in str(tk).split(",") if x.strip()}
        for t in cur - set(ouverts):
            ouverts[t] = d if d > DEBUT_SORTIES else None
        for t in set(ouverts) - cur:
            per.setdefault(t, []).append([ouverts.pop(t), d])
        fin = d
    for t, a in ouverts.items():
        per.setdefault(t, []).append([a, None])
    return per, fin


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


def _secteurs_yahoo(tickers, budget=120):
    """Secteur des valeurs sorties de l'indice (absent de Wikipedia), demandé à Yahoo par petits lots."""
    import yfinance as yf
    out = {}
    for t in tickers[:budget]:
        try:
            info = yf.Ticker(t).get_info()
            out[t] = YAHOO.get(info.get("sector")) or ""
            out[t + "|nom"] = info.get("shortName") or ""
        except Exception:
            out[t] = ""  # radiée ou inconnue de Yahoo : pas de nouvel essai (aucun cours ne serait disponible)
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
    if live and age >= REFRESH_JOURS:
        try:
            membres, chg = parse_wikipedia(_fetch_html())
            if chg and not any(c["retrait"] for c in chg):
                errs.append("univers S&P 500 : aucune sortie lue dans l'historique des changements")
            cache.update({"maj": now.isoformat(), "membres": membres, "changements": chg})
            log["univers"] = f"S&P 500 rafraîchi ({len(membres)} membres, {len(chg)} changements)"
        except Exception as e:
            errs.append(f"univers S&P 500 : {type(e).__name__} {str(e)[:60]} (dernière version connue conservée)")
    if not cache.get("membres"):
        return base, {t: [[None, None]] for t in base}, log, errs
    if live and not cache.get("changements") and (age >= REFRESH_JOURS or "historique" not in cache):
        try:
            import os
            h, fin = historique_fja(os.environ.get("GH_TOKEN"))
            cache["historique"] = {"source": "fja05680/sp500", "jusqu_au": fin, "periodes": h}
            log["historique"] = f"composition historique fja05680/sp500 jusqu'au {fin} ({len(h)} valeurs)"
        except Exception as e:
            errs.append(f"composition historique (fja05680/sp500) : {type(e).__name__} {str(e)[:60]}")
    per = intervalles(cache["membres"], cache.get("changements", []))
    hist = (cache.get("historique") or {}).get("periodes") or {}
    if not cache.get("changements") and hist:
        actuels_t = {m["ticker"]: m for m in cache["membres"]}
        per = {}
        for t, ps in hist.items():
            ps = [list(p) for p in ps]
            if t in actuels_t and ps[-1][1] is not None and ps[-1][1] >= (cache["historique"]["jusqu_au"] or ""):
                ps[-1][1] = None  # toujours membre aujourd'hui
            elif t in actuels_t and ps[-1][1] is not None:
                ps.append([actuels_t[t].get("depuis"), None])  # sorti puis revenu après la date du fichier
            per[t] = ps
        for t, m in actuels_t.items():
            per.setdefault(t, [[m.get("depuis"), None]])  # entrées postérieures au fichier
        per = {t: ps for t, ps in per.items() if t in actuels_t or any(p[1] is None or p[1] > DEBUT_SORTIES for p in ps)}
    secteurs = cache.setdefault("secteurs_sortis", {})
    actuels = {m["ticker"]: m for m in cache["membres"]}
    per, faits = raccorder(per, {t for t in per if t not in base and secteurs.get(t) == ""}, actuels)
    if faits:
        log["changements_de_symbole"] = len(faits)
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


def raccorder(per, sans_cours, actuels=()):
    """Applique RENOMMAGES : renvoie (périodes raccordées, liste des couples appliqués)."""
    per = {t: [list(p) for p in ps] for t, ps in per.items()}
    faits = []
    def bascule(o, n):
        return next((p[1] for p in per.get(o, []) if p[1] and any(q[0] == p[1] for q in per.get(n, []))), None)
    couples = sorted(((bascule(o, n), o, n) for o, n in RENOMMAGES), key=lambda x: x[0] or "")
    for d, o, n in couples:
        if not d or o not in per or n not in per or o in actuels or o not in sans_cours:  # n absent : aller-retour déjà raccordé
            continue
        ps = sorted(per.pop(o) + per[n], key=lambda p: p[0] or "")
        fus = [ps[0]]
        for a, b in ps[1:]:
            if fus[-1][1] is not None and (a or "") <= fus[-1][1]:  # périodes jointives : une seule
                fus[-1][1] = None if b is None else max(fus[-1][1], b)
            else:
                fus.append([a, b])
        per[n] = fus
        faits.append(f"{o}>{n}")
    return per, faits


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


def couverture(root, close):
    """Biais du survivant résiduel, mesuré : pour chaque année, part moyenne des membres historiques du S&P 500
    (fichier fja05680/sp500) qui ont un cours en base ce jour-là. Les sociétés radiées sans cours disponibles chez
    Yahoo (rachats, faillites) manquent : elles ne peuvent entrer ni dans l'entraînement ni dans l'évaluation."""
    cache = json.loads((pathlib.Path(root) / "data" / "univers.json").read_text(encoding="utf-8"))
    per = (cache.get("historique") or {}).get("periodes") or {}
    if not per:
        return {}
    per, _ = raccorder(per, set(per) - set(close.columns))
    idx = close.index
    cols = list(per)
    m = mask(per, idx, cols)
    px = close.reindex(columns=cols).notna().to_numpy()
    n_m = m.to_numpy().sum(axis=1)
    n_ok = (m.to_numpy() & px).sum(axis=1)
    s = pd.Series(np.where(n_m > 0, n_ok / np.maximum(n_m, 1), np.nan), index=idx)
    s = s[s.index >= pd.Timestamp(DEBUT_SORTIES)]
    return {str(y): round(float(v), 3) for y, v in s.groupby(s.index.year).mean().items()}
