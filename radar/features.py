"""Construction des variables : prix, signaux d'actualité pondérés, cibles relatives au marché."""
import json

import numpy as np
import pandas as pd

from .events import CATS, SECTORS, SENSITIVE, rel_exposure

PRICE_FEATS = ["ret1", "ret5", "ret20", "rel5", "rel20", "vol20", "volratio", "dist_ma50", "rsi", "vol_rel",
               "mkt_ret5", "mkt_ret20", "sec_id"]
NEWS_FEATS = [f"n_{c}" for c in CATS] + ["news_comp", "co_sent", "co_mentions"]
CAL_FEATS = ["earn_next", "earn_since", "earn_surprise", "cb_next"]
ALL_FEATS = PRICE_FEATS + NEWS_FEATS + CAL_FEATS


def load_prices(con, wl, min_rows=120):
    p = pd.read_sql("SELECT ticker,date,close,volume FROM prices", con, parse_dates=["date"])
    p = p[p["ticker"].isin(list(wl))]
    close = p.pivot(index="date", columns="ticker", values="close").sort_index()
    volume = p.pivot(index="date", columns="ticker", values="volume").sort_index()
    keep = [t for t in close.columns if close[t].notna().sum() >= min_rows]
    dropped = [t for t in wl if t not in keep]
    # jours fériés différents selon les places : on reporte le dernier cours connu (3 jours max)
    return close[keep].ffill(limit=3), volume[keep].ffill(limit=3), dropped


def load_scores(con):
    s = pd.read_sql("SELECT id,date,source,title,cats,polarity,tickers,techs,vol FROM scores", con,
                    parse_dates=["date"])
    for c in ("cats", "tickers", "techs"):
        s[c] = s[c].map(json.loads)
    return s


def _roll3(pos, values, n, idx):
    out = np.zeros(n)
    np.add.at(out, pos, values)
    return pd.Series(out, index=idx).rolling(3, min_periods=1).sum()


def load_earnings(con):
    e = pd.read_sql("SELECT ticker,date,surprise FROM earnings", con, parse_dates=["date"])
    return e.sort_values("date")


def _cb_dates(cal):
    out = []
    for ds in (cal or {}).get("cb", {}).values():
        out += [np.datetime64(pd.Timestamp(str(d))) for d in ds]
    return np.array(sorted(out), dtype="datetime64[ns]")


def _to_next(ev, iv, cap):
    """Jours calendaires jusqu'au prochain événement (date incluse), plafonnés. Dates supposées connues d'avance."""
    if len(ev) == 0:
        return np.full(len(iv), float(cap))
    j = np.searchsorted(ev, iv, side="left")
    d = (ev[np.minimum(j, len(ev) - 1)] - iv) / np.timedelta64(1, "D")
    return np.clip(np.where(j < len(ev), d, cap), 0, cap)


def build_features(close, volume, scores, wl, horizons, wsrc=None, wcs=None, cal=None):
    wsrc, wcs = wsrc or {}, wcs or {}
    idx, n = close.index, len(close)
    iv = idx.values.astype("datetime64[ns]")
    cb_next = _to_next(_cb_dates(cal), iv, 15) / 15
    earn = (cal or {}).get("earn")
    earn_by = {t: g for t, g in earn.groupby("ticker")} if earn is not None and len(earn) else {}
    xr = rel_exposure(wl)
    has = len(scores) > 0
    if has:
        pos = np.minimum(idx.searchsorted(scores["date"].values), n - 1)
        ws = scores["source"].map(lambda s: wsrc.get(s, 1.0)).values.astype(float)
        pol = scores["polarity"].values
        sv = scores["vol"].fillna(1.0).values
        cat3 = {}
        for c in CATS:
            inten = np.array([d.get(c, 0.0) for d in scores["cats"]])
            cat3[c] = _roll3(pos, ws * inten * (pol if c in SENSITIVE else 1.0), n, idx)
    else:
        cat3 = {c: pd.Series(np.zeros(n), index=idx) for c in CATS}
    rets = close.pct_change(fill_method=None)
    mkt = rets.mean(axis=1)
    frames = []
    for t in close.columns:
        c, r1, v = close[t], rets[t], volume[t]
        sector = wl[t]["sector"]
        f = pd.DataFrame(index=idx)
        f["ret1"], f["ret5"], f["ret20"] = r1, c.pct_change(5, fill_method=None), c.pct_change(20, fill_method=None)
        f["vol20"] = r1.rolling(20).std()
        f["volratio"] = r1.rolling(5).std() / (r1.rolling(60).std() + 1e-9)
        f["dist_ma50"] = c / c.rolling(50).mean() - 1
        d = c.diff()
        up, dn = d.clip(lower=0).rolling(14).mean(), (-d.clip(upper=0)).rolling(14).mean()
        f["rsi"] = 100 - 100 / (1 + up / (dn + 1e-9))
        f["vol_rel"] = v / (v.rolling(20).mean() + 1e-9)
        f["mkt_ret5"] = mkt.rolling(5).sum()
        f["mkt_ret20"] = mkt.rolling(20).sum()
        g = earn_by.get(t)
        ev = g["date"].values.astype("datetime64[ns]") if g is not None else np.array([], dtype="datetime64[ns]")
        f["earn_next"] = _to_next(ev, iv, 30) / 30
        j = np.searchsorted(ev, iv, side="left") - 1  # dernier résultat strictement passé : surprise connue
        since = np.where(j >= 0, (iv - ev[np.maximum(j, 0)]) / np.timedelta64(1, "D"), 30) if len(ev) else np.full(n, 30.0)
        f["earn_since"] = np.clip(since, 0, 30) / 30
        sur = g["surprise"].values.astype(float) if g is not None else np.zeros(0)
        f["earn_surprise"] = np.clip(np.nan_to_num(np.where(j >= 0, sur[np.maximum(j, 0)], 0.0)), -0.5, 0.5) if len(ev) else 0.0
        f["cb_next"] = cb_next
        f["sec_id"] = SECTORS.index(sector)  # sans lui, les actualités serviraient surtout à reconnaître le secteur
        comp = 0
        for k in CATS:
            f[f"n_{k}"] = cat3[k] * xr[k][sector]
            comp = comp + wcs.get(f"{k}|{sector}", 1.0) * f[f"n_{k}"]
        f["news_comp"] = comp
        if has:
            m = np.array([t in tk for tk in scores["tickers"]])
            f["co_sent"] = _roll3(pos[m], (ws * pol)[m], n, idx)
            ment = _roll3(pos[m], sv[m], n, idx)
        else:
            f["co_sent"], ment = 0.0, pd.Series(np.zeros(n), index=idx)
        f["co_mentions"] = ment / (ment.rolling(60, min_periods=10).mean() + 0.5)
        for h in horizons:
            f[f"fwd{h}"] = c.shift(-h) / c - 1
        f["ticker"], f["sector"], f["date"] = t, sector, idx
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    g = df.groupby("date")
    for h in horizons:  # cible : rendement de la valeur moins celui du marché suivi
        df[f"x{h}"] = df[f"fwd{h}"] - g[f"fwd{h}"].transform("mean")
    df["rel5"] = df["ret5"] - g["ret5"].transform("mean")
    df["rel20"] = df["ret20"] - g["ret20"].transform("mean")
    return df
