"""Briefs courts (quotidien et hebdomadaire) en texte, prêts à insérer dans un email."""
import pathlib


def _p(x):
    return f"{x * 100:.0f} %"


def generate(rep, out_dir):
    demo = rep["mode"] == "demo"
    main = str(rep["main_horizon"])
    bt = rep["backtest"][main]
    gain = bt["auc"] - rep["backtest"]["price_only"]["auc"]
    tag = " (DÉMO, données synthétiques)" if demo else ""

    w = rep["watch"][:3]
    t = next((x for x in rep["techs"] if x["status"] in ("émergente", "en hausse")), None)
    hs = [x for x in rep["heat"] if x["ratio"] is not None]
    h = max(hs, key=lambda x: x["ratio"]) if hs else None
    ev = rep["events"][0] if rep["events"] else None
    alerte = (f"{h['cat']} à ×{h['ratio']:.1f} la normale" if h and h["ratio"] >= 2 else
              "aucune pression inhabituelle" if h else "en calibrage (historique d'actualités insuffisant)")
    if ev:
        alerte += f". Événement marquant : {ev['title']} ({ev['source']})"
    fiab = (f"AUC backtest {bt['auc']:.2f} (apport des actualités {gain:+.2f}), coefficient de confiance {rep['shrink']:.2f}, "
            f"{rep['n_resolved']} prévisions résolues")
    if rep.get("live_hit") is not None:
        fiab += f", {_p(rep['live_hit'])} justes"
    anomalies = ([f"cours figés depuis {rep['stale_days']} jours"] if rep.get('stale_days', 0) > 4 else []) + rep.get('errors', [])
    plus = f" (+{len(anomalies) - 3} autres, voir data/status.json)" if len(anomalies) > 3 else ""
    etat = ("ANOMALIES : " + " ; ".join(anomalies[:3]) + plus) if anomalies else "toutes les sources ont répondu"
    daily = [f"Radar bourse, cours au {rep['as_of']}, généré le {rep.get('generated_utc', '')} UTC{tag}",
             "- Valeurs à surveiller : " + " ; ".join(
                 f"{x['name']} ({_p(x['p'][main])} de chances de battre le marché à {main} j, pilote {x['driver']})" for x in w),
             "- Technologie à veiller : " + (f"{t['tech']} ({t['status']}, {t['m7']} mentions sur 7 j)" if t else
                                            f"en calibrage, encore {rep['calib_days']} jours de bourse" if rep.get("calib_days") else "aucune hausse notable"),
             f"- Alerte : {alerte}",
             f"- Fiabilité : {fiab}",
             f"- État : {etat}",
             "Veille informative, pas un conseil en investissement."]

    sec = rep["sectors"]
    jr = "; ".join(f"{j['horizon']} j ({j['kind']}) {_p(j['hit'])} sur {j['n']}" for j in rep["journal"]) or "journal vide"
    weekly = [f"Radar bourse, bilan hebdomadaire au {rep['as_of']}{tag}",
              "- Secteurs porteurs : " + ", ".join(f"{s['sector']} ({s['driver']})" for s in sec[:3]),
              "- Secteurs sous pression : " + ", ".join(f"{s['sector']} ({s['driver']})" for s in sec[-2:]),
              "- Technologies : " + ", ".join(f"{x['tech']} ({x['status']})" for x in rep["techs"][:3]),
              f"- Journal des prédictions (taux de réussite) : {jr}",
              "- Sources les plus fiables : " + ", ".join(f"{x['key']} {x['value']:.2f}" for x in rep["weights_source"][:3]),
              f"- Liens événement × secteur validés ({rep['n_sig']} significatifs sur {rep['n_tests']} testés) : "
              + (", ".join(f"{x['key']} {x['value']:.2f}" for x in rep["weights_pairs"][:4]) or "aucun pour l'instant"),
              f"- Valeur ajoutée des actualités sur les prix seuls : AUC {gain:+.2f}",
              "Veille informative, pas un conseil en investissement."]
    out = pathlib.Path(out_dir)
    (out / "brief.md").write_text("\n".join(daily) + "\n", encoding="utf-8")
    (out / "brief_weekly.md").write_text("\n".join(weekly) + "\n", encoding="utf-8")
    return daily
