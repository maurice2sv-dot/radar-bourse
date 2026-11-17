"""Orchestration : collecte, scoring, apprentissage, prédiction, journal, rapport."""
import datetime as dt
import json
import pathlib

import pandas as pd

from . import analysis, collect, db, events, features, gdelt, journal, model


def score_new(con, cfg):
    matchers = events.company_matchers(cfg["watchlist"])
    rows = con.execute("SELECT a.id,a.date,a.source,a.title,a.text FROM articles a "
                       "LEFT JOIN scores s ON s.id=a.id WHERE s.id IS NULL").fetchall()
    out = []
    for i, d, src, title, text in rows:
        s = events.score_article(title, text, matchers)
        out.append((i, d, src, title, json.dumps(s["cats"]), s["polarity"], json.dumps(s["tickers"]), json.dumps(s["techs"])))
    con.executemany("INSERT INTO scores(id,date,source,title,cats,polarity,tickers,techs) VALUES (?,?,?,?,?,?,?,?)", out)
    con.commit()
    return len(out)


def gdelt_to_scores(con):
    """Transforme les séries GDELT en signaux quotidiens. Volume et ton sont comparés à leur propre norme
    des 90 jours précédents. Le signal du jour J est daté J+1 : il n'est connu qu'une fois la journée finie."""
    g = pd.read_sql("SELECT kind,key,date,vol,tone FROM gdelt", con, parse_dates=["date"])
    if g.empty:
        return 0
    today = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
    rows = []
    for (kind, key), s in g.groupby(["kind", "key"]):
        s = s.sort_values("date")
        s = s[s["date"] < today]  # journée en cours incomplète
        base = s["vol"].shift(1).rolling(90, min_periods=20).mean()
        ratio = (s["vol"] / (base + 1e-9)).clip(0, 4)
        tm = s["tone"].shift(1).rolling(90, min_periods=20).median()
        ts = s["tone"].shift(1).rolling(90, min_periods=20).std()
        pol = ((s["tone"] - tm) / (2 * ts + 1e-6)).clip(-1, 1).fillna(0)
        for d, b, r, p in zip(s["date"], base, ratio, pol):
            if b != b or b <= 0:
                continue
            day = (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            cats, tk = ({key: float(r) / 2}, []) if kind == "cat" else ({}, [key])
            rows.append((f"gd-{kind}-{key}-{day}", day, "GDELT", f"GDELT {key} : volume ×{r:.1f}, ton {p:+.2f}",
                         json.dumps(cats), float(p), json.dumps(tk), "[]", float(r)))
    con.executemany("INSERT OR REPLACE INTO scores(id,date,source,title,cats,polarity,tickers,techs,vol) VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def replay(con, df, feats, cfg):
    """Rejeu point-in-time : à chaque date passée, entraîne sur le seul passé connu et journalise."""
    if con.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] > 0:
        return 0
    dates = sorted(df["date"].unique())
    n, step = cfg["replay_dates"], 5
    pts = dates[-(n * step) - 21:-21:step]
    for d in pts:
        rows = []
        for h in cfg["horizons"]:
            tk, p = model.predict_at(df, d, feats, h, iters=80)
            rows += [(t, h, float(x), float(x), "") for t, x in zip(tk, p)]
        journal.log_predictions(con, pd.Timestamp(d).strftime("%Y-%m-%d"), rows, "replay")
    return len(pts)


def run(cfg, root=".", do_replay=True):
    log, errs = {}, []
    con = db.connect(cfg, root)
    wl, hz, main = cfg["watchlist"], cfg["horizons"], cfg["main_horizon"]
    if cfg["mode"] == "demo":
        if con.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0:
            collect.demo_generate(cfg, con)
    else:  # chaque source est isolée : une panne est signalée, jamais bloquante
        st, e = collect.collect_prices_live(cfg, con)
        log["cours"], errs = st["sources"], errs + e
        try:
            log["resultats"], e = collect.collect_earnings_live(cfg, con)
            errs += e
            log["marches"], e = collect.collect_macro_live(cfg, con)
            errs += e
        except Exception as ex:
            errs.append(f"calendrier des résultats : {type(ex).__name__}")
        try:
            log["flux_ok"], ko = collect.collect_news_live(cfg, con)
            errs += ko
        except Exception as ex:
            errs.append(f"flux RSS : {type(ex).__name__}")
        try:
            log["gdelt_series"], e = gdelt.import_csv(cfg, con, root)
            errs += e
            log["gdelt_signaux"] = gdelt_to_scores(con)
        except Exception as ex:
            errs.append(f"GDELT : {type(ex).__name__} {str(ex)[:80]}")
    log["nouveaux_articles"] = score_new(con, cfg)

    close, volume, dropped = features.load_prices(con, wl)
    if close.shape[1] < 5 or len(close) < 300:
        raise RuntimeError(f"Cours insuffisants ({close.shape[1]} valeurs, {len(close)} jours) : {errs}")
    if dropped:
        errs.append("valeurs écartées faute d'historique : " + ", ".join(dropped))
    wl = {t: wl[t] for t in close.columns}
    scores = features.load_scores(con)

    # 1. Backtest honnête : poids neutres (les poids appris utilisent des rendements qui seraient « futurs »)
    cal = {"earn": features.load_earnings(con), "cb": cfg.get("calendrier", {}).get("banques_centrales", {})}
    macro = features.load_macro(con)
    df0 = features.build_features(close, volume, scores, wl, hz, cal=cal, macro=macro)
    bt = model.run_backtests(df0, hz, main)

    # 2. Journal : rejeu point-in-time puis résolution
    if do_replay:
        log["rejeu"] = replay(con, df0, features.ALL_FEATS, cfg)
    log["resolues"] = journal.resolve(con, close)
    log["signalees_resolues"] = journal.resolve_watch(con, close, h=main)

    # 3. Apprentissage : poids des sources et des couples catégorie x secteur, avec test de signification
    n_tests, n_sig = journal.learn_weights(con, close, scores, wl, h=main)
    wsrc, wcs = db.get_weights(con, "source"), db.get_weights(con, "catsec")

    # 4. Prédiction du jour avec les poids appris
    df = features.build_features(close, volume, scores, wl, hz, wsrc, wcs, cal=cal, macro=macro)
    preds, last = model.predict_latest(df, features.ALL_FEATS, hz)
    stats = journal.live_stats(con)
    k, n_res, hit = journal.shrink_factor(stats, main)
    preds["p_up"] = 0.5 + k * (preds["p_raw"] - 0.5)
    rep = analysis.analyze(df, scores, close, dict(cfg, watchlist=wl), preds, wcs, cal, macro)
    run_date = last.strftime("%Y-%m-%d")
    journal.log_watch(con, run_date, [w["ticker"] for w in rep["watch"][:3]], [w["p"][str(main)] for w in rep["watch"][:3]])
    journal.log_predictions(con, run_date, [(r.ticker, int(r.h), r.p_up, r.p_raw, rep["drivers"][r.ticker])
                                            for r in preds.itertuples()], "live")

    def w(kind, where=""):
        return [{"key": a, "value": b, "n": c, "hits": d, "z": z} for a, b, c, d, z in
                con.execute(f"SELECT key,value,n,hits,z FROM weights WHERE kind=? {where} ORDER BY ABS(z) DESC", (kind,))]

    pairs = []
    for x in w("catsec", "AND value<>1"):
        c, s = x["key"].split("|")
        pairs.append(dict(x, key=f"{analysis.CAT_FR[c]} × {analysis.SEC_FR[s]}"))
    today = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    rep.update({"mode": cfg["mode"], "backtest": bt, "main_horizon": main, "horizons": hz,
                "weights_source": w("source"), "weights_pairs": pairs, "n_tests": n_tests, "n_sig": n_sig,
                "suivi": journal.watch_stats(con), "journal": stats.to_dict("records"), "shrink": k, "n_resolved": n_res, "live_hit": hit,
                "n_articles": int(len(scores)), "n_gdelt": int((scores["source"] == "GDELT").sum()) if len(scores) else 0,
                "generated_utc": today.strftime("%Y-%m-%d %H:%M"), "stale_days": int((today.date() - last.date()).days),
                "errors": errs, "log": log})
    rep.pop("drivers")
    out = pathlib.Path(root) / "data"
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, default=float, indent=1))
    (out / "status.json").write_text(json.dumps({"genere_utc": rep["generated_utc"], "mode": cfg["mode"], "cours_au": run_date,
                                                 "jours_de_retard": rep["stale_days"], "anomalies": errs, "journal": log},
                                                ensure_ascii=False, indent=1))
    con.close()
    return rep
