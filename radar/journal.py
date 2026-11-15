"""Journal des prédictions et auto-adaptation (poids des sources et des couples catégorie x secteur)."""
import numpy as np
import pandas as pd

from .events import SENSITIVE, SECTORS, rel_exposure

ZMIN = {"source": 1.96, "catsec": 2.58}  # seuil plus strict pour les couples : 81 tests simultanés


def log_predictions(con, run_date, rows, kind):
    con.executemany(
        "INSERT OR REPLACE INTO predictions(run_date,ticker,horizon,p_up,p_raw,driver,kind) VALUES (?,?,?,?,?,?,?)",
        [(run_date, t, h, p, pr, drv, kind) for t, h, p, pr, drv in rows])
    con.commit()


def resolve(con, close):
    """Compare les prédictions échues au réel : rendement de la valeur moins celui du marché suivi."""
    idx = close.index
    upd, mkt = [], {}
    for run_date, t, h, p in con.execute("SELECT run_date,ticker,horizon,p_up FROM predictions WHERE resolved=0").fetchall():
        pos = idx.searchsorted(pd.Timestamp(run_date), side="right") - 1
        if pos < 0 or pos + h >= len(idx) or t not in close:
            continue
        if (pos, h) not in mkt:
            mkt[(pos, h)] = float((close.iloc[pos + h] / close.iloc[pos] - 1).mean())
        r = float(close[t].iloc[pos + h] / close[t].iloc[pos] - 1) - mkt[(pos, h)]
        if r != r:
            continue
        upd.append((r, int((p > 0.5) == (r > 0)), run_date, t, h))
    con.executemany("UPDATE predictions SET resolved=1, realized=?, hit=? WHERE run_date=? AND ticker=? AND horizon=?", upd)
    con.commit()
    return len(upd)


def live_stats(con):
    q = """SELECT horizon, kind, COUNT(*) n, AVG(hit) hit,
           AVG((p_up-(realized>0))*(p_up-(realized>0))) brier
           FROM predictions WHERE resolved=1 GROUP BY horizon, kind"""
    return pd.read_sql(q, con)


def shrink_factor(stats, main):
    """Plus le modèle a fait ses preuves en conditions réelles, moins on rétrécit ses probabilités vers 50 %."""
    s = stats[(stats.horizon == main)]
    n = int(s.n.sum())
    if n < 30:
        return 0.3, n, None
    hit = float((s.hit * s.n).sum() / n)
    return float(np.clip(0.3 + (hit - 0.5) * 6, 0.1, 1.0)), n, hit


def learn_weights(con, close, scores, wl, h=5):
    """Recalcule tous les poids depuis l'historique complet.
    Pour chaque article échu : le secteur (ou la valeur) visé a-t-il surperformé le marché dans le sens prévu ?
    Une observation par jour et par clé. Le nombre d'observations indépendantes est borné par durée / h
    (les fenêtres de h jours se chevauchent). Un poids ne quitte 1,0 que si le test est significatif."""
    if scores.empty:
        return 0, 0
    idx, n = close.index, len(close)
    fwd = close.shift(-h) / close - 1
    mkt = fwd.mean(axis=1)
    xr = rel_exposure(wl)
    sec_x = {}
    for s in SECTORS:
        cols = [t for t in close.columns if wl[t]["sector"] == s]
        if cols:
            sec_x[s] = (fwd[cols].mean(axis=1) - mkt).values
    tk_x = {t: (fwd[t] - mkt).values for t in close.columns}
    # centrage sur la médiane : un secteur qui monte tout le temps ne valide pas à tort chaque événement
    sec_x = {k: v - np.nanmedian(v) for k, v in sec_x.items()}
    tk_x = {k: v - np.nanmedian(v) for k, v in tk_x.items()}
    obs = {}  # (kind, key) -> {jour: [somme des succès, nombre]}

    def add(kind, key, pos, hit):
        a = obs.setdefault((kind, key), {}).setdefault(pos, [0, 0])
        a[0] += hit
        a[1] += 1

    pos_all = np.minimum(idx.searchsorted(scores["date"].values), n - 1)
    for row, pos in zip(scores.itertuples(), pos_all):
        if pos >= n - h:
            continue  # pas encore échu
        vals = {c: i * (row.polarity if c in SENSITIVE else 1.0) for c, i in row.cats.items()}
        eff = {}
        for s, x in sec_x.items():
            real = x[pos]
            if real != real:
                continue
            tot = 0.0
            for c, v in vals.items():
                e = v * xr[c][s]
                tot += e
                if abs(xr[c][s]) >= 0.1 and abs(v) > 1e-9:
                    add("catsec", f"{c}|{s}", pos, int(np.sign(e) * real > 0))
            eff[s] = tot
        for s in sorted(eff, key=lambda k: -abs(eff[k]))[:2]:
            if abs(eff[s]) >= 0.1:
                add("source", row.source, pos, int(np.sign(eff[s]) * sec_x[s][pos] > 0))
        if abs(row.polarity) > 1e-9:
            for t in row.tickers:
                real = tk_x.get(t, [np.nan] * n)[pos]
                if real == real:
                    add("source", row.source, pos, int(np.sign(row.polarity) * real > 0))
    out, sig = [], 0
    for (kind, key), days in obs.items():
        N = len(days)
        H = sum(a / b for a, b in days.values())
        span = max(days) - min(days) + 1
        neff = min(N, max(1.0, span / h))
        rate = H / N
        z = (rate - 0.5) * 2 * np.sqrt(neff)
        ok = N >= 30 and abs(z) >= ZMIN[kind]
        sig += bool(ok and kind == "catsec")
        val = float(np.clip(1 + ((H + 5) / (N + 10) - 0.5) * 8, 0.2, 2.5)) if ok else 1.0
        out.append((kind, key, val, N, H, float(z)))
    con.execute("DELETE FROM weights")
    con.executemany("INSERT INTO weights VALUES (?,?,?,?,?,?)", out)
    con.commit()
    return sum(1 for o in out if o[0] == "catsec"), int(sig)
