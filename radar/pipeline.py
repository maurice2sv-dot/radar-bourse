"""Orchestration : collecte, scoring, apprentissage, prédiction, journal, rapport."""
import datetime as dt
import json
import pathlib

import pandas as pd

from . import analysis, collect, db, events, features, gdelt, gdelt_events, journal, model, portefeuille, univers


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


def evaluation(con, d, cfg, h):
    """Sélection des groupes de variables (hebdomadaire, période de développement seulement),
    puis mesure sur la période de test réservée avec les groupes retenus."""
    debut = str(cfg["evaluation"]["test_reserve_debut"])
    sel = db.meta_get(con, "selection")
    today = dt.date.today()
    # couverture de chaque groupe (valeurs ayant des données) : une source qui arrive relance la sélection
    cov = {g: int(d.loc[d[f].notna().any(axis=1), "ticker"].nunique()) for g, f in model.GROUPS.items()}
    grown = sel is not None and any(n > 1.2 * sel.get("couverture", {}).get(g, 0) + 1 for g, n in cov.items())
    stale = (sel is None or sel.get("reserve_debut") != debut or sel.get("version") != 3 or grown
             or (today - dt.date.fromisoformat(sel["date"])).days >= cfg["evaluation"].get("reselection_jours", 7))
    if stale:
        groups, trace, dev = model.select_groups(d, cfg, h)
        sel = {"version": 3, "date": today.isoformat(), "reserve_debut": debut, "groupes": groups, "trace": trace, "dev": dev,
               "couverture": cov}
        db.meta_set(con, "selection", sel)
    res = sel.get("reserve_cache") if not stale else None
    if res is None or sel.get("reserve_groupes") != sel["groupes"]:
        # recalcul hebdomadaire seulement : le test réservé ne sert plus aux réglages (voir période fraîche)
        res = model.evaluate_reserve(d, cfg, h, sel["groupes"])
        sel.update(reserve_cache=res, reserve_groupes=sel["groupes"])
        db.meta_set(con, "selection", sel)
    opened = db.meta_get(con, "reserve_ouverte")
    if opened is None or opened.get("debut") != debut:
        opened = {"debut": debut, "le": today.isoformat()}
        db.meta_set(con, "reserve_ouverte", opened)
    out = dict(sel, reserve=res, reserve_ouverte_le=opened["le"], recalcule=stale)
    out.pop("reserve_cache", None)
    return out


def run(cfg, root=".", do_replay=True):
    log, errs = {}, []
    con = db.connect(cfg, root)
    hz, main = cfg["horizons"], cfg["main_horizon"]
    live = cfg["mode"] == "live"
    if live:  # univers élargi et appartenance historique (contre le biais du survivant)
        wl_full, membership, ulog, uerrs = univers.load(cfg, root, live=True)
        log.update(ulog)
        errs += uerrs
    else:
        wl_full, membership = cfg["watchlist"], {t: [[None, None]] for t in cfg["watchlist"]}
    actives = {t: v for t, v in wl_full.items() if univers.is_active(membership.get(t, [[None, None]]))}
    if cfg["mode"] == "demo":
        if con.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 0:
            collect.demo_generate(cfg, con)
    else:  # chaque source est isolée : une panne est signalée, jamais bloquante
        st, e = collect.collect_prices_live(dict(cfg, watchlist=wl_full), con)
        log["cours"], errs = st["sources"], errs + e
        try:
            cc, e = collect.cross_check(dict(cfg, watchlist=actives), con)
            log.update(cc)
            errs += e
        except Exception as ex:
            log["controle_croise"] = f"indisponible ({type(ex).__name__})"
        try:
            log["resultats"], e = collect.collect_earnings_live(dict(cfg, watchlist=actives), con)
            errs += e
            log["marches"], e = collect.collect_macro_live(cfg, con)
            errs += e
            log["fondamentaux"], e = collect.collect_fundamentals_live(dict(cfg, watchlist=wl_full), con)
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
            log["gdelt_evenements"], e = gdelt_events.collect(cfg, con)  # après l'import : prime sur les anciennes séries
            errs += e
            log["gdelt_signaux"] = gdelt_to_scores(con)
        except Exception as ex:
            errs.append(f"GDELT : {type(ex).__name__} {str(ex)[:80]}")
    log["nouveaux_articles"] = score_new(con, cfg)

    close, volume, dropped = features.load_prices(con, wl_full)
    if close.shape[1] < 5 or len(close) < 300:
        raise RuntimeError(f"Cours insuffisants ({close.shape[1]} valeurs, {len(close)} jours) : {errs}")
    dropped = [t for t in dropped if t in actives]
    if dropped:
        errs.append(f"valeurs actives écartées faute d'historique ({len(dropped)}) : " + ", ".join(dropped[:15])
                    + (" ..." if len(dropped) > 15 else ""))
    wl = {t: wl_full[t] for t in close.columns}
    member = univers.mask(membership, close.index, close.columns)
    close_m = close.where(member)
    sus = collect.suspicious_moves(close, member)
    if sus:
        errs.append("cours suspects (plus de 40 % en une séance, à vérifier) : " + ", ".join(sus[:8]))
    log["univers_du_jour"] = int(member.iloc[-1].sum())
    scores = features.load_scores(con)

    # 1. Évaluation honnête : poids neutres (les poids appris utilisent des rendements qui seraient « futurs »)
    cal = {"earn": features.load_earnings(con), "cb": cfg.get("calendrier", {}).get("banques_centrales", {})}
    macro = features.load_macro(con)
    fund = features.load_fundamentals(con)
    df0 = features.build_features(close, volume, scores, wl, hz, cal=cal, macro=macro, fund=fund, member=member)
    ev = evaluation(con, df0.dropna(subset=["ret20"]), cfg, main)

    # 2. Journal : rejeu point-in-time puis résolution
    if do_replay:
        log["rejeu"] = replay(con, df0, features.ALL_FEATS, cfg)
    log["resolues"] = journal.resolve(con, close_m, wl)
    log["signalees_resolues"] = journal.resolve_watch(con, close_m, h=main)

    # 3. Apprentissage : poids des sources et des couples catégorie x secteur, avec test de signification
    n_tests, n_sig = journal.learn_weights(con, close_m, scores, wl, h=main)
    wsrc, wcs = db.get_weights(con, "source"), db.get_weights(con, "catsec")

    # 4. Prédiction du jour avec les poids appris
    df = features.build_features(close, volume, scores, wl, hz, wsrc, wcs, cal=cal, macro=macro, fund=fund, member=member)
    preds, last = model.predict_latest(df.dropna(subset=["ret20"]), model.feats_for(ev["groupes"]), hz)
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
    rep.update({"mode": cfg["mode"], "eval": ev, "main_horizon": main, "horizons": hz,
                "weights_source": w("source"), "weights_pairs": pairs, "n_tests": n_tests, "n_sig": n_sig,
                "suivi": journal.watch_stats(con),
                "fraiche": journal.fresh_stats(con, cfg["evaluation"].get("periode_fraiche_debut", run_date), main), "cout_bps": cfg["evaluation"].get("cout_bps", 10), "gain_min_ic": cfg["evaluation"].get("gain_min_ic", 0.003), "journal": stats.to_dict("records"), "shrink": k, "n_resolved": n_res, "live_hit": hit,
                "n_articles": int(len(scores)), "n_gdelt": int((scores["source"] == "GDELT").sum()) if len(scores) else 0,
                "generated_utc": today.strftime("%Y-%m-%d %H:%M"), "stale_days": int((today.date() - last.date()).days),
                "errors": errs, "log": log})
    rep.pop("drivers")
    out = pathlib.Path(root) / "data"
    try:  # portefeuille fictif : règle appliquée sans argent réel, état conservé dans data/
        nom = "portefeuille.json" if cfg["mode"] == "live" else "portefeuille_demo.json"
        rep["portefeuille"] = portefeuille.update(close, rep["all_p5"], run_date, out / nom, rep["cout_bps"],
                                                  member=member, macro=macro, refs=cfg.get("references"))
    except Exception as ex:
        errs.append(f"portefeuille fictif : {type(ex).__name__} {str(ex)[:80]}")
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, default=float, indent=1))
    (out / "status.json").write_text(json.dumps({"genere_utc": rep["generated_utc"], "mode": cfg["mode"], "cours_au": run_date,
                                                 "jours_de_retard": rep["stale_days"], "anomalies": errs, "journal": log},
                                                ensure_ascii=False, indent=1))
    con.close()
    return rep
