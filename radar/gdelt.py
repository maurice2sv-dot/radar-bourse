"""GDELT : collecte horaire légère vers des fichiers CSV, import dans la base au passage du soir.

GDELT limite à une requête toutes les 5 secondes par adresse, et les serveurs GitHub partagent leurs adresses :
un passage unique ne peut pas tout collecter. On prend donc quelques séries par heure, les plus en retard
d'abord, et on s'arrête au premier refus. Chaque série vit dans data/gdelt/<type>__<clé>.csv (date, vol, tone).
"""
import csv
import datetime as dt
import json
import pathlib
import time

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
CATS = {
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


class RateLimited(Exception):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def series(cfg):
    out = [("cat", c, q) for c, q in CATS.items()]
    for t, v in cfg["watchlist"].items():
        out.append(("ticker", t, v.get("gdelt") or f'"{v["name"]}"'))
    return out


def path(root, kind, key):
    p = pathlib.Path(root) / "data" / "gdelt"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{kind}__{key}.csv"


def read(p):
    if not p.exists():
        return {}
    with p.open(newline="") as f:
        return {r["date"]: (float(r["vol"]), float(r["tone"]) if r["tone"] else None) for r in csv.DictReader(f)}


def write(p, data):
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "vol", "tone"])
        for d in sorted(data):
            v, t = data[d]
            w.writerow([d, f"{v:.6g}", "" if t is None else f"{t:.4f}"])
    tmp.replace(p)


def parse(js):
    """{'timeline':[{'data':[{'date':'20240101T000000Z','value':1.2},..]}]} -> {date: valeur}"""
    out = {}
    for serie in (js or {}).get("timeline", [])[:1]:
        for pt in serie.get("data", []):
            d = str(pt.get("date", ""))[:8]
            if len(d) == 8 and d.isdigit():
                out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = float(pt.get("value", 0) or 0)
    return out


def fetch(query, mode, start, end, pause):
    import requests
    params = {"query": query, "mode": mode, "format": "json",
              "startdatetime": start.strftime("%Y%m%d000000"), "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    for attempt in range(2):
        time.sleep(pause)
        r = requests.get(URL, params=params, timeout=60, headers={"User-Agent": "radar-bourse/0.3"})
        msg = f"HTTP {r.status_code} {r.text[:60].strip()!r}"
        if r.status_code == 429:
            if attempt == 0:
                time.sleep(30)
                continue
            raise RateLimited(msg)
        r.raise_for_status()
        try:
            return parse(r.json())
        except ValueError:
            raise RuntimeError(msg)  # GDELT répond en texte quand il refuse la forme d'une requête
    raise RateLimited(msg)


def _last(root, kind, key):
    d = read(path(root, kind, key))
    return max(d) if d else ""


def collect_hourly(cfg, root):
    g = cfg.get("gdelt", {})
    keys = series(cfg)
    now = _now()
    today = now.strftime("%Y-%m-%d")
    if not g.get("enabled", True):
        return {"desactive": True}
    last = {(k, c): _last(root, k, c) for k, c, _ in keys}
    rot = now.toordinal() * 24 + now.hour  # ordre tournant entre séries également en retard
    order = sorted(range(len(keys)), key=lambda i: (last[keys[i][:2]], (i + rot) % len(keys)))
    todo = [keys[i] for i in order if last[keys[i][:2]] < today]  # une série par jour suffit
    t0, got, refus = time.time(), [], []
    for kind, key, q in todo[:g.get("per_run", 3)]:
        if time.time() - t0 > g.get("budget_s", 360):
            break
        l = last[(kind, key)]
        start = (dt.datetime.fromisoformat(l) - dt.timedelta(days=3)) if l else now - dt.timedelta(days=int(g.get("years", 3) * 365))
        try:
            vol = fetch(q, "timelinevol", start, now, g.get("pause", 10))
            tone = fetch(q, "timelinetone", start, now, g.get("pause", 10))
        except RateLimited as e:
            refus.append(f"{key} : {e}")
            break  # inutile d'insister, la limite se durcit si on force
        except Exception as e:
            refus.append(f"{key} : {str(e)[:90] or type(e).__name__}")
            continue
        if not vol:
            refus.append(f"{key} : réponse vide")
            continue
        p = path(root, kind, key)
        data = read(p)
        for d, v in vol.items():
            data[d] = (v, tone.get(d))
        write(p, data)
        got.append(key)
    lim = (now - dt.timedelta(days=2)).strftime("%Y-%m-%d")
    etat = {"utc": now.strftime("%Y-%m-%d %H:%M"), "acquises": got, "refus": refus,
            "a_jour": sum(_last(root, k, c) >= lim for k, c, _ in keys), "total": len(keys),
            "restant_aujourdhui": max(0, len(todo) - len(got))}
    (path(root, "x", "x").parent / "_etat.json").write_text(json.dumps(etat, ensure_ascii=False, indent=1))
    return etat


def import_csv(cfg, con, root):
    """Charge les CSV dans la base et signale les séries en retard."""
    keys = series(cfg)
    lim = (_now() - dt.timedelta(days=2)).strftime("%Y-%m-%d")
    rows, n, fresh = [], 0, 0
    for kind, key, _ in keys:
        d = read(path(root, kind, key))
        if d:
            n += 1
            fresh += max(d) >= lim
            rows += [(kind, key, day, v, t) for day, (v, t) in d.items()]
    con.executemany("INSERT OR REPLACE INTO gdelt VALUES (?,?,?,?,?)", rows)
    con.commit()
    errs = []
    if fresh < len(keys):
        ep = path(root, "x", "x").parent / "_etat.json"
        e = json.loads(ep.read_text()) if ep.exists() else {}
        errs.append(f"GDELT : {fresh} séries à jour sur {len(keys)} ({n} avec historique), collecte horaire en cours"
                    + (f", dernier refus {e['utc']} : {e['refus'][0]}" if e.get("refus") else ""))
    return n, errs
