"""Briefs courts (quotidien et hebdomadaire) en texte, prêts à insérer dans un email.

Chaque bloc suit le même schéma : les faits, « En clair » (explication pédagogique),
puis « Appréciation » (lecture qualitative du bloc). Le jeudi matin, le brief
quotidien se termine par le bilan hebdomadaire commenté.
"""
import datetime as dt
import json
import math
import pathlib
import statistics

HIST_FILE = "brief_hist.json"
HIST_KEEP = 30
_GRP = {"actualites": "actualités", "marches": "marchés"}


def _p(x):
    return f"{x * 100:.0f} %"


def _n(x, d=1):
    """Nombre à la française (virgule décimale)."""
    return f"{x:.{d}f}".replace(".", ",")


def _sn(x, d=1):
    return ("+" if x >= 0 else "") + _n(x, d)


def _ord(k):
    return "1re" if k == 1 else f"{k}e"


# ---------- historique des classements (pour montrer les évolutions) ----------

def _load_hist(out):
    try:
        return json.loads((out / HIST_FILE).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_hist(out, hist, rep):
    snap = {"p5": {x["ticker"]: round(x["p5"], 5) for x in rep.get("all_p5", [])}}
    vix = next((m for m in rep.get("marches", []) if m["label"] == "VIX"), None)
    if vix:
        snap["vix"] = round(vix["niveau"], 2)
    hist[rep["as_of"]] = snap
    hist = {k: hist[k] for k in sorted(hist)[-HIST_KEEP:]}
    try:
        (out / HIST_FILE).write_text(json.dumps(hist, ensure_ascii=False, indent=0), encoding="utf-8")
    except Exception:
        pass
    return hist


def _ranks(p5):
    order = sorted(p5, key=lambda t: -p5[t])
    return {t: i + 1 for i, t in enumerate(order)}


def _prev(hist, as_of, days_back=1):
    """Instantané de la séance précédente (days_back=1) ou d'environ une semaine avant (5)."""
    keys = [k for k in sorted(hist) if k < as_of]
    if not keys:
        return None, None
    k = keys[-days_back] if len(keys) >= days_back else keys[0]
    return k, hist[k]


# ---------- blocs ----------

def _bloc_valeurs(rep, main, hist):
    allp = rep.get("all_p5") or []
    p5 = {x["ticker"]: x["p5"] for x in allp}
    n = len(p5)
    ranks = _ranks(p5) if p5 else {}
    mu = statistics.mean(p5.values()) if p5 else 0.5
    sd = statistics.pstdev(p5.values()) if len(p5) > 1 else 0.0
    _, prev = _prev(hist, rep["as_of"])
    prev_ranks = _ranks(prev["p5"]) if prev and prev.get("p5") else {}

    lignes, forces = [], []
    for x in rep["watch"][:3]:
        p = x["p"][main]
        z = (p - mu) / sd if sd > 0 else 0.0
        force = "net" if abs(z) >= 2 else "modéré" if abs(z) >= 1 else "faible"
        sens = "favorable" if p > 0.5 else "défavorable" if p < 0.5 else "neutre"
        forces.append((force, sens))
        r = ranks.get(x["ticker"])
        rang = f"{_ord(r)} sur {n}" if r else "rang inconnu"
        ev = ""
        if r and x["ticker"] in prev_ranks:
            d = prev_ranks[x["ticker"]] - r
            ev = (f", hier {_ord(prev_ranks[x['ticker']])}" + (" (stable)" if d == 0 else f" ({'gagne' if d > 0 else 'perd'} {abs(d)} place{'s' if abs(d) > 1 else ''})"))
        lignes.append(f"  {x['name']} ({x['sector']}) : {rang}{ev} ; signal {force}, {sens} "
                      f"({_n(p * 100)} %, soit {_sn((p - 0.5) * 100)} pt par rapport à pile ou face) ; thème d'actualité dominant : {x['driver']}")

    ecart_max = max((abs(x["p5"] - 0.5) for x in allp), default=0) * 100
    clair = (f"  En clair : chaque jour, les {n} valeurs suivies sont classées selon leur chance de faire mieux que leur secteur "
             f"sur {main} séances. 50 % équivaut à pile ou face. Les écarts restent toujours petits (aujourd'hui {_n(ecart_max)} pt au plus), "
             f"c'est donc le rang et la force du signal qui comptent, pas le pourcentage brut. Signal « net » : la valeur se détache "
             f"nettement des autres (haut ou bas du classement) ; « faible » : elle reste dans le peloton. "
             f"Ces trois valeurs sont retenues pour l'attention qu'elles suscitent (actualité, volumes, résultats proches), "
             f"pas parce qu'elles sont en tête : un signal défavorable invite plutôt à la prudence.")
    nets = [f for f in forces if f[0] == "net"]
    if not forces:
        app = "aucune valeur signalée."
    elif nets:
        fav = sum(1 for f in nets if f[1] == "favorable")
        app = (f"{len(nets)} signa{'ux' if len(nets) > 1 else 'l'} net{'s' if len(nets) > 1 else ''} "
               f"({fav} favorable{'s' if fav > 1 else ''}, {len(nets) - fav} défavorable{'s' if len(nets) - fav > 1 else ''}) ; "
               f"pistes de veille à recouper avec l'actualité, l'avantage statistique restant mince valeur par valeur.")
    else:
        app = "signaux faibles à modérés, aucune valeur ne se détache vraiment : journée sans conviction particulière."
    return ["1. Valeurs à surveiller"] + lignes + [clair, f"  Appréciation : {app}"]


def _bloc_techno(rep):
    t = next((x for x in rep["techs"] if x["status"] in ("émergente", "en hausse")), None)
    if t:
        fait = f"  {t['tech']} ({t['status']}, {t['m7']} mentions sur 7 jours)"
        app = f"thème qui monte dans l'actualité ; valeurs liées : {', '.join(t.get('related', [])[:5]) or 'non précisées'}."
    elif rep.get("calib_days"):
        fait = f"  En calibrage, encore {rep['calib_days']} jours de bourse"
        app = "pas encore exploitable, l'historique est trop court pour distinguer une vraie montée d'un bruit passager."
    else:
        fait = "  Aucune hausse notable"
        app = "aucune technologie ne gagne anormalement en visibilité cette semaine."
    clair = ("  En clair : le radar compte les mentions de chaque technologie (IA, semi-conducteurs, quantique...) dans la presse "
             "et compare les 7 derniers jours à l'habitude. Une hausse inhabituelle précède parfois un intérêt des investisseurs.")
    return ["2. Technologie à veiller", fait, clair, f"  Appréciation : {app}"]


def _bloc_alerte(rep):
    hs = [x for x in rep["heat"] if x["ratio"] is not None]
    h = max(hs, key=lambda x: x["ratio"]) if hs else None
    ev = rep["events"][0] if rep["events"] else None
    lignes = []
    if rep.get("alertes_marche"):
        lignes.append("  Marchés : " + " ; ".join(rep["alertes_marche"]))
    lignes.append("  Actualité : " + (f"{h['cat']} à ×{_n(h['ratio'])} la normale" if h and h["ratio"] >= 2 else
                                       f"aucune pression inhabituelle (thème le plus actif : {h['cat']}, ×{_n(h['ratio'])} la normale)" if h else
                                       "en calibrage (historique d'actualités insuffisant)"))
    if ev:
        lignes.append(f"  Événement marquant : {ev['title']} ({ev['source']})")
    if rep.get("agenda"):
        lignes.append("  À venir : " + " ; ".join(f"{a['label']} le {a['date']}" for a in rep["agenda"][:4]))
    vix = next((m for m in rep.get("marches", []) if m["label"] == "VIX"), None)
    clair = ("  En clair : le VIX mesure la nervosité attendue sur la bourse américaine (sous 15 : calme ; 15 à 20 : normal ; "
             "20 à 30 : tension ; au-delà de 30 : stress). La pression d'actualité compare le volume d'articles par thème à sa moyenne : "
             "×1 = habituel, ×2 ou plus = inhabituel.")
    tension = []
    if vix:
        v = vix["niveau"]
        tension.append("climat de marché " + ("calme" if v < 15 else "normal" if v < 20 else "tendu" if v < 30 else "en stress")
                       + f" (VIX {_n(v)})")
    if h:
        tension.append("actualité " + ("chargée" if h["ratio"] >= 2 else "dans la norme"))
    if rep.get("agenda"):
        tension.append(f"{len(rep['agenda'])} rendez-vous de résultats proche{'s' if len(rep['agenda']) > 1 else ''}")
    app = (", ".join(tension) + ".") if tension else "rien de notable."
    if vix and vix["niveau"] >= 20:
        app += " Dans ce contexte, les mouvements de court terme sont plus amples et les signaux du modèle moins lisibles."
    return ["3. Alerte marchés et actualité"] + lignes + [clair, f"  Appréciation : {app}"]


def _bloc_fiabilite(rep, main, evl):
    rs = evl.get("reserve") or {}
    grp = " + ".join(["prix"] + [_GRP.get(g, g) for g in evl["groupes"]])
    ic, t, net = rs.get("ic", float("nan")), rs.get("t", float("nan")), rs.get("net", float("nan"))
    lignes = [f"  Test réservé depuis le {evl['reserve_debut']} : IC {_sn(ic, 3)} (t = {_n(t)}) ; "
              f"les 20 % de valeurs les mieux classées font {_sn(net * 100, 2)} % par {main} jours de mieux que la moyenne, frais déduits",
              f"  Variables retenues : {grp} ; coefficient de confiance {_n(rep['shrink'], 2)} ; {rep['n_resolved']} prévisions résolues"
              + (f", {_p(rep['live_hit'])} justes" if rep.get("live_hit") is not None else "")]
    sv = rep.get("suivi") or {}
    if sv.get("n"):
        lignes.append(f"  Valeurs signalées : {_p(sv['beat'])} ont battu le marché à {main} jours (écart moyen {_sn(sv['excess'] * 100, 2)} %, "
                      f"{sv['n']} cas sur {sv['jours']} jour{'s' if sv['jours'] > 1 else ''})")
    else:
        lignes.append("  Suivi des valeurs signalées démarré, premier bilan après 5 séances")
    clair = ("  En clair : l'IC (coefficient d'information) mesure si le classement prévu ressemble au classement réellement observé. "
             "0 = hasard ; 0,02 à 0,05 = avantage modeste mais réel, niveau courant chez les professionnels. "
             "Le t indique si ce résultat peut être dû à la chance : au-dessus de 2, c'est peu probable. "
             "Le « test réservé » porte sur une période que le modèle n'a jamais vue pendant sa construction, c'est donc la mesure honnête. "
             "Un taux de prévisions justes proche de 50 % est normal : l'avantage se joue sur un grand nombre de valeurs, pas sur chacune.")
    if math.isnan(t) or math.isnan(ic):
        app = "mesure indisponible, aucune conclusion possible."
    elif t >= 2 and net > 0:
        app = ("avantage statistique faible mais solide sur l'ensemble du classement, rentable après frais. "
               "Utile pour orienter la veille sur un panier de valeurs ; insuffisant pour décider valeur par valeur.")
    elif t >= 2:
        app = "le classement capte quelque chose, mais l'avantage disparaît une fois les frais déduits : intérêt surtout informatif."
    else:
        app = "pas de preuve que le modèle fasse mieux que le hasard sur la période récente : prudence sur les signaux."
    return ["4. Fiabilité du modèle"] + lignes + [clair, f"  Appréciation : {app}"]


def _bloc_etat(rep):
    anomalies = ([f"cours figés depuis {rep['stale_days']} jours"] if rep.get("stale_days", 0) > 4 else []) + rep.get("errors", [])
    plus = f" (+{len(anomalies) - 3} autres, voir data/status.json)" if len(anomalies) > 3 else ""
    fait = ("  ANOMALIES : " + " ; ".join(anomalies[:3]) + plus) if anomalies else "  Toutes les sources ont répondu"
    app = ("données incomplètes, les blocs ci-dessus sont à lire avec réserve." if anomalies
           else "collecte complète, le brief repose sur des données à jour.")
    return ["5. État de la collecte", fait, f"  Appréciation : {app}"]


# ---------- bilan hebdomadaire commenté ----------

def _hebdo(rep, main, evl, hist, tag):
    sec = rep["sectors"]
    rs = evl.get("reserve") or {}
    L = [f"BILAN DE LA SEMAINE au {rep['as_of']}{tag}", ""]

    # Secteurs
    L += ["A. Secteurs",
          "  Porteurs : " + ", ".join(f"{s['sector']} ({s['driver']})" for s in sec[:3]),
          "  Sous pression : " + ", ".join(f"{s['sector']} ({s['driver']})" for s in sec[-2:]),
          "  En clair : le score de chaque secteur combine sa performance sur 20 séances et la tonalité de l'actualité qui le concerne ; "
          "entre parenthèses, le thème d'actualité qui pèse le plus.",
          "  Appréciation : " + (f"écart marqué entre {sec[0]['sector']} (en tête) et {sec[-1]['sector']} (en queue), "
                                 f"le thème « {sec[0]['driver']} » structure la semaine." if sec else "données sectorielles indisponibles."), ""]

    # Évolution des classements sur la semaine
    k, old = _prev(hist, rep["as_of"], 5)
    p5 = {x["ticker"]: x["p5"] for x in rep.get("all_p5", [])}
    names = {x["ticker"]: x["name"] for x in rep.get("all_p5", [])}
    L.append("B. Mouvements du classement sur la semaine")
    if old and old.get("p5") and p5:
        r_now, r_old = _ranks(p5), _ranks(old["p5"])
        mv = sorted(((r_old[t] - r_now[t], t) for t in r_now if t in r_old), reverse=True)
        L.append(f"  Comparaison avec le {k}. Plus fortes progressions : "
                 + ", ".join(f"{names.get(t, t)} ({_ord(r_old[t])} → {_ord(r_now[t])})" for d, t in mv[:3] if d > 0))
        L.append("  Plus forts reculs : " + ", ".join(f"{names.get(t, t)} ({_ord(r_old[t])} → {_ord(r_now[t])})" for d, t in mv[::-1][:3] if d < 0))
        stab = sum(1 for d, _ in mv if abs(d) <= 10) / max(len(mv), 1)
        L.append(f"  Appréciation : {_p(stab)} des valeurs ont bougé de 10 places ou moins ; "
                 + ("classement stable, les signaux de la semaine se confirment." if stab >= 0.6 else
                    "classement très mouvant, les signaux de court terme sont à prendre avec recul."))
    else:
        L.append("  Historique en cours de constitution : les comparaisons d'une semaine sur l'autre apparaîtront dès que 5 séances seront enregistrées.")
    L.append("")

    # Journal
    jr = rep["journal"]
    L += ["C. Journal des prédictions",
          "  Taux de réussite : " + ("; ".join(f"{j['horizon']} j ({'en direct' if j['kind'] == 'live' else 'rejeu'}) {_p(j['hit'])} sur {j['n']}" for j in jr) or "journal vide"),
          "  En clair : part des prévisions dont le sens s'est révélé juste. « En direct » = prévisions faites avant les faits ; "
          "« rejeu » = prévisions recalculées sur le passé récent pour enrichir l'échantillon."]
    best = max(jr, key=lambda j: j["hit"]) if jr else None
    L.append("  Appréciation : " + (f"meilleur résultat à {best['horizon']} j ({_p(best['hit'])}) ; "
                                    + ("au-dessus de 50 %, le modèle reste un peu meilleur que le hasard sur cet horizon."
                                       if best["hit"] > 0.52 else "aucun horizon ne se détache nettement du hasard cette semaine.")
                                    if best else "pas encore de résultats."))
    L.append("")

    # Marchés
    m = rep.get("marches", [])
    L += ["D. Marchés sur 20 séances",
          "  " + (", ".join(f"{x['label']} {_n(x['niveau'], 2)} ({_sn(x['chg20'], 2)} pt)" if x["points"] else
                             f"{x['label']} {_n(x['niveau'], 2)} ({_sn(x['chg20'] * 100)} %)" for x in m) or "indisponibles"),
          "  En clair : VIX = nervosité ; taux 10 ans = coût de l'argent à long terme ; pétrole, or, dollar = thermomètres de l'économie mondiale."]
    vix = next((x for x in m if x["label"] == "VIX"), None)
    _, old_v = _prev(hist, rep["as_of"], 5)
    tend = ""
    if vix and old_v and old_v.get("vix"):
        dv = vix["niveau"] - old_v["vix"]
        tend = f" Sur la semaine, le VIX {'monte' if dv > 0.5 else 'baisse' if dv < -0.5 else 'est stable'} ({_sn(dv)} pt)."
    L.append("  Appréciation : " + (("contexte tendu, " if vix and vix["niveau"] >= 20 else "contexte serein, ") if vix else "")
             + "les mouvements de plus de 10 % sur 20 séances signalent les marchés à surveiller." + tend)
    L.append("")

    # Fiabilité
    L += ["E. Fiabilité et construction du modèle",
          "  Variables testées (IC en développement) : " + ", ".join(
              f"{_GRP.get(x['groupe'], x['groupe'])} {_sn(x['ic'], 3)}{'' if x['garde'] else ' (écartée)'}" if x.get("ic") is not None else f"{_GRP.get(x['groupe'], x['groupe'])} (aucune donnée)"
              for x in evl["trace"]),
          f"  Test réservé : IC {_sn(rs.get('ic', float('nan')), 3)}, t = {_n(rs.get('t', float('nan')))}, "
          f"net de frais {_sn(rs.get('net', float('nan')) * 100, 2)} % par {main} j, ratio d'information net {_n(rs.get('ir_net', float('nan')), 2)}",
          f"  Liens événement × secteur validés : {rep['n_sig']} significatifs sur {rep['n_tests']} testés",
          "  En clair : une famille de variables n'est gardée que si elle améliore réellement la prévision. "
          "Le ratio d'information rapporte le gain à sa régularité : au-dessus de 0,5, le résultat est plutôt régulier."]
    irn = rs.get("ir_net", float("nan"))
    L.append("  Appréciation : " + (("modèle sobre (seuls les prix sont retenus), " if not evl["groupes"] else "") + "résultat régulier hors échantillon ; "
                                    if not math.isnan(irn) and irn >= 0.5 else "résultat hors échantillon encore irrégulier ; ")
             + ("aucun lien actualité × secteur n'est encore prouvé." if not rep["n_sig"] else f"{rep['n_sig']} liens actualité × secteur confirmés."))
    L.append("")
    return L


def _is_thursday_morning(rep):
    """Vrai pour le brief de l'envoi du jeudi matin : cours du mercredi, généré avant jeudi midi UTC."""
    try:
        asof = dt.date.fromisoformat(rep["as_of"])
        gen = dt.datetime.strptime(rep.get("generated_utc", ""), "%Y-%m-%d %H:%M")
    except Exception:
        return False
    return asof.weekday() == 2 and not (gen.weekday() == 3 and gen.hour >= 12) and gen.date() <= asof + dt.timedelta(days=1)


def generate(rep, out_dir):
    out = pathlib.Path(out_dir)
    demo = rep["mode"] == "demo"
    main = str(rep["main_horizon"])
    evl = rep["eval"]
    tag = " (DÉMO, données synthétiques)" if demo else ""
    hist = _save_hist(out, _load_hist(out), rep)

    daily = [f"Radar bourse, cours au {rep['as_of']}, généré le {rep.get('generated_utc', '')} UTC{tag}", ""]
    for bloc in (_bloc_valeurs(rep, main, hist), _bloc_techno(rep), _bloc_alerte(rep),
                 _bloc_fiabilite(rep, main, evl), _bloc_etat(rep)):
        daily += bloc + [""]
    weekly = _hebdo(rep, main, evl, hist, tag)
    if _is_thursday_morning(rep):
        daily += weekly
    daily.append("Veille informative, pas un conseil en investissement.")
    weekly.append("Veille informative, pas un conseil en investissement.")

    (out / "brief.md").write_text("\n".join(daily) + "\n", encoding="utf-8")
    (out / "brief_weekly.md").write_text("\n".join(weekly) + "\n", encoding="utf-8")
    return daily
