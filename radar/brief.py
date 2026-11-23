"""Briefs courts (quotidien et hebdomadaire) en texte, prêts à insérer dans un email.

Chaque bloc suit le même schéma : les faits, « En clair » (explication pédagogique),
puis « Appréciation » (lecture qualitative du bloc). Le bilan hebdomadaire
commenté (brief_weekly.md) est joint à l'envoi du lundi matin.
"""
import json
import math
import pathlib
import statistics

HIST_FILE = "brief_hist.json"
HIST_KEEP = 30
_GRP = {"actualites": "actualités", "marches": "marchés"}


def _p(x):
    return "?" if x is None or x != x else f"{x * 100:.0f} %"


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

def _risque_txt(rep, t):
    r = (rep.get("risque") or {}).get(t)
    if not r:
        return ""
    return (f" ; profil {r['profil']} (volatilité {_n(r['vol'] * 100, 0)} % par an, bêta {_n(r['beta'], 1)}, "
            f"pire baisse sur un an {_n(r['dd'] * 100, 0)} %)")


def _bloc_profils(rep):
    pr = rep.get("profils")
    titre = "2. Par profil de risque"
    if not pr:
        return [titre, "  Indisponible lors de ce passage."]
    noms = {"prudent": "Prudent (peu agité)", "équilibré": "Équilibré", "dynamique": "Dynamique (très agité)"}
    L = [titre]
    for p in ("prudent", "équilibré", "dynamique"):
        g = pr.get(p) or {}
        if not g.get("top"):
            continue
        L.append(f"  {noms[p]}, {g['n']} valeurs, volatilité de {_n(g['vol_min'] * 100, 0)} à {_n(g['vol_max'] * 100, 0)} % par an : "
                 + " ; ".join(f"{x['name']} ({_ord(x['rang'])}, {_n(x['p5'] * 100)} %, bêta {_n(x['beta'], 1)})" for x in g["top"]))
    L.append("  En clair : les valeurs sont réparties en trois tiers selon leur agitation sur un an (volatilité : ampleur habituelle "
             "des variations, en % par an). Le bêta mesure la sensibilité au marché : 1 = suit le marché, 1,5 = amplifie ses "
             "mouvements de moitié, 0,5 = les amortit, négatif = évolue souvent à contre-courant (cas récent du pétrole). Une valeur dynamique peut gagner ou perdre beaucoup plus qu'une valeur prudente, "
             "dans les deux sens. Le risque se mesure bien ; le potentiel, beaucoup moins : le classement reste celui du modèle.")
    tops = {p: (pr.get(p) or {}).get("top") or [] for p in pr}
    meilleur = max(tops, key=lambda p: tops[p][0]["p5"] if tops[p] else 0)
    L.append(f"  Appréciation : les signaux les plus marqués se trouvent dans le profil {meilleur} ; "
             + ("c'est fréquent, les valeurs agitées produisant des écarts plus grands, sans que cela prouve un meilleur potentiel."
                if meilleur == "dynamique" else "les écarts restent faibles, aucune catégorie de risque n'est nettement favorisée."))
    return L


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
                      f"({_n(p * 100)} %, soit {_sn((p - 0.5) * 100)} pt par rapport à pile ou face) ; thème d'actualité dominant : {x['driver']}"
                      + _risque_txt(rep, x["ticker"]))

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
               + (f"({fav} favorable{'s' if fav > 1 else ''}, {len(nets) - fav} défavorable{'s' if len(nets) - fav > 1 else ''}) ; "
                  if 0 < fav < len(nets) else f"{'favorable' if fav else 'défavorable'}{'s' if len(nets) > 1 else ''} ; ")
               + 
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
    return ["3. Technologie à veiller", fait, clair, f"  Appréciation : {app}"]


def _bloc_alerte(rep):
    hs = [x for x in rep["heat"] if x["ratio"] is not None]
    h = max(hs, key=lambda x: x["ratio"]) if hs else None
    ev = rep["events"][0] if rep["events"] else None
    lignes = []
    if rep.get("alertes_marche"):
        lignes.append("  Marchés : " + " ; ".join(rep["alertes_marche"]))
    asie = [m for m in rep.get("marches", []) if m.get("asie")]
    if asie:
        lignes.append("  Asie (dernière séance close) : " + " ; ".join(f"{m['label']} {_sn(m['chg1'] * 100)} % le {m['date']}" for m in asie))
    lignes.append("  Actualité : " + (f"{h['cat']} à ×{_n(h['ratio'])} la normale" if h and h["ratio"] >= 2 else
                                       f"aucune pression inhabituelle (thème le plus actif : {h['cat']}, ×{_n(h['ratio'])} la normale)" if h else
                                       "en calibrage (historique d'actualités insuffisant)"))
    if ev:
        lignes.append(f"  Événement marquant : {ev['title']} ({ev['source']})")
    if rep.get("agenda"):
        lignes.append("  À venir : " + " ; ".join(f"{a['label']} le {a['date']}" for a in rep["agenda"][:4]))
    rg = rep.get("regime") or {}
    if rg.get("niveau"):
        lignes.append(f"  Régime de marché : {rg['niveau']} (" + " ; ".join(rg["raisons"]) + ")")
        lignes.append("  Frein anti-krach du momentum : " + (f"actif, {rg['frein_raison']}" if rg.get("frein") else "inactif"))
    vix = next((m for m in rep.get("marches", []) if m["label"] == "VIX"), None)
    clair = ("  En clair : le VIX mesure la nervosité attendue sur la bourse américaine (sous 15 : calme ; 15 à 20 : normal ; "
             "20 à 30 : tension ; au-delà de 30 : stress). La pression d'actualité compare le volume d'articles par thème à sa moyenne : "
             "×1 = habituel, ×2 ou plus = inhabituel."
             + (" Les bourses asiatiques (Tokyo, Hong Kong, Shanghai) ferment avant l'ouverture de l'Europe : une forte variation"
                " y donne souvent le ton de la séance européenne ; alerte au-delà de 3 % sur une séance ou de 10 % de baisse sur 20 séances."
                if asie else "")
             + (" Régime de marché : calme (VIX sous 20), tension (20 à 30), stress (30 ou plus, ou S&P 500 en baisse de 5 % en 5 séances), "
                "krach (40 ou plus, ou baisse de 10 % en 5 séances). Le frein anti-krach s'active après un marché baissier agité : "
                "c'est dans les rebonds qui suivent que les stratégies de tendance subissent leurs pires pertes."
                if rg.get("niveau") else ""))
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
    consigne = {"tension": " Dans ce contexte, les mouvements de court terme sont plus amples et les signaux du modèle moins lisibles.",
                "stress": " Climat de stress : mouvements amples et corrélés, les signaux de court terme sont à lire avec prudence.",
                "krach": " Climat de krach : les classements de court terme perdent l'essentiel de leur sens, l'observation prime."}
    niv = rg.get("niveau") or ("tension" if vix and vix["niveau"] >= 20 else None)
    app += consigne.get(niv, "")
    hist = _hist_regime(rep.get("eval") or {}, niv)
    if hist:
        app += " " + hist
    if rg.get("frein"):
        app += " Frein actif : la règle « radar avec frein » du portefeuille fictif ne penche plus vers les valeurs en forte tendance."
    return ["4. Alerte marchés et actualité"] + lignes + [clair, f"  Appréciation : {app}"]


def _hist_regime(evl, niv):
    """Phrase sur la fiabilité historique du classement dans le régime donné."""
    x = ((evl.get("regimes") or {}).get("regimes") or {}).get(niv) if niv else None
    if not x or "ic" not in x:
        return ""
    ic, t = x["ic"], x["t"]
    qual = ("avantage net" if t == t and t >= 2 and ic > 0 else "léger avantage, non significatif" if ic > 0 else "aucun avantage")
    return (f"Historiquement, dans ce climat ({x['dates']} dates), le classement a un IC de {_sn(ic, 3)}"
            + (f" (t = {_n(t)})" if t == t else "") + f" : {qual}.")


def _ligne_regimes(evl):
    rg = evl.get("regimes") or {}
    parts = [f"{k} {_sn(x['ic'], 3)} ({x['dates']} dates)" for k, x in (rg.get("regimes") or {}).items() if "ic" in x]
    eps = [f"{k} {_sn(x['ic'], 3)}" for k, x in (rg.get("episodes") or {}).items() if "ic" in x]
    if not parts:
        return []
    out = ["  Selon le climat de marché (IC hors échantillon) : " + " ; ".join(parts)
           + ((" ; épisodes de stress : " + " ; ".join(eps)) if eps else "")]
    fr = rg.get("frein") or {}
    if fr.get("periodes"):
        out.append(f"  Frein anti-krach, effet passé ({fr['periodes']} périodes de 5 séances où il aurait été actif) : "
                   f"radar {_sn(fr['radar'] * 100, 2)} % contre {_sn(fr['neutre'] * 100, 2)} % avec frein, par période, avant frais ; "
                   f"le frein fait mieux {fr['gagnees']} fois sur {fr['periodes']}")
    return out


def _bloc_fiabilite(rep, main, evl):
    rs = evl.get("reserve") or {}
    fr = rep.get("fraiche") or {}
    grp = " + ".join(["prix"] + [_GRP.get(g, g) for g in evl["groupes"]])
    ic, t, net = rs.get("ic", float("nan")), rs.get("t", float("nan")), rs.get("net", float("nan"))
    if fr.get("dates"):
        l0 = (f"  Période fraîche depuis le {fr['debut']} (mesure de référence) : IC {_sn(fr['ic'], 3)}"
              + (f" (t = {_n(fr['t'])})" if fr.get("t") is not None else "") + f" sur {fr['dates']} date{'s' if fr['dates'] > 1 else ''}, "
              f"{_p(fr['justes'])} de prévisions justes")
    else:
        l0 = f"  Période fraîche depuis le {fr.get('debut', '?')} (mesure de référence) : premiers résultats après {main} séances"
    lignes = [l0,
              f"  Historique, test réservé depuis le {evl['reserve_debut']} (ne sert plus aux réglages) : IC {_sn(ic, 3)} (t = {_n(t)}) ; "
              f"les 20 % les mieux classées font {_sn(net * 100, 2)} % par {main} jours de mieux que la moyenne, frais déduits",
              f"  Variables retenues : {grp} ; coefficient de confiance {_n(rep['shrink'], 2)} ; {rep['n_resolved']} prévisions résolues"
              + (f", {_p(rep['live_hit'])} justes" if rep.get("live_hit") is not None else "")]
    lignes += _ligne_regimes(evl)
    sv = rep.get("suivi") or {}
    if sv.get("n"):
        lignes.append(f"  Valeurs signalées : {_p(sv['beat'])} ont battu le marché à {main} jours (écart moyen {_sn(sv['excess'] * 100, 2)} %, "
                      f"{sv['n']} cas sur {sv['jours']} jour{'s' if sv['jours'] > 1 else ''})")
    else:
        lignes.append("  Suivi des valeurs signalées démarré, premier bilan après 5 séances")
    clair = ("  En clair : l'IC (coefficient d'information) mesure si le classement prévu ressemble au classement réellement observé. "
             "0 = hasard ; 0,02 à 0,05 = avantage modeste mais réel, niveau courant chez les professionnels. "
             "Le t indique si ce résultat peut être dû à la chance : au-dessus de 2, c'est peu probable. "
             "La « période fraîche » ne contient que des prévisions faites avant les faits, après le dernier réglage du modèle : "
             "c'est désormais la seule mesure qui compte. Le test réservé, consulté souvent, reste affiché pour mémoire.")
    if fr.get("dates", 0) >= 20 and fr.get("t") is not None:
        app = ("avantage confirmé sur la période fraîche." if fr["t"] >= 2 and fr["ic"] > 0 else
               "pas d'avantage démontré sur la période fraîche : les signaux restent des pistes de veille.")
    elif math.isnan(t) or math.isnan(ic):
        app = "mesure indisponible, aucune conclusion possible."
    else:
        app = (f"période fraîche encore trop courte ({fr.get('dates', 0)} date{'s' if fr.get('dates', 0) > 1 else ''} sur 20 au moins) ; "
               + ("l'historique montre un avantage faible mais significatif, à confirmer." if t >= 2 and net > 0 else
                  "l'historique montre un léger avantage net de frais, mais trop incertain pour écarter le hasard (t inférieur à 2)."
                  if net > 0 else "l'historique ne montre pas d'avantage net de frais."))
    return ["5. Fiabilité du modèle"] + lignes + [clair, f"  Appréciation : {app}"]


_REF = {"moyenne": "moyenne de l'univers"}


def _perf_line(pf):
    st, rf = pf["strats"], pf["refs"]
    parts = [f"radar {_sn(st['radar']['perf'] * 100, 2)} %", f"momentum {_sn(st['momentum']['perf'] * 100, 2)} %"]
    parts += [f"{_REF.get(k, k)} {_sn(v * 100, 2)} %" for k, v in rf.items() if not k.startswith("moyenne_")]
    return " ; ".join(parts)


def _bloc_portefeuille(rep):
    pf = rep.get("portefeuille")
    titre = "6. Portefeuille fictif (sans argent réel)"
    if not pf or "strats" not in pf:
        return [titre, "  Indisponible lors de ce passage.", "  Appréciation : aucune mesure possible aujourd'hui."]
    R, M = pf["strats"]["radar"], pf["strats"]["momentum"]
    moy = pf["refs"].get("moyenne", 0.0)
    ecart = (R["perf"] - moy) * 100
    ecart_m = (R["perf"] - M["perf"]) * 100
    lignes = [f"  Règle : {pf['regle']}",
              f"  Depuis le {pf['debut']} ({pf['seances']} séance{'s' if pf['seances'] > 1 else ''}) : {_perf_line(pf)}",
              f"  Radar : pire baisse {_n(R['pire_baisse'] * 100, 2)} %, frais payés {_n(R['frais'] * 100, 2)} % ; "
              f"{R['n_lignes']} lignes, dont {', '.join(R['lignes'])} ; prochaine revue dans {pf['prochaine_revue']} séance"
              f"{'s' if pf['prochaine_revue'] > 1 else ''}"]
    F = pf["strats"].get("radar_frein")
    if F and F.get("n_lignes"):
        lignes.append(f"  Radar avec frein anti-krach (depuis le {F['debut']}) : {_sn(F['perf'] * 100, 2)} % ; frein "
                      + ("actif à la dernière revue, portefeuille neutre en tendance" if F.get("frein") else "inactif, identique au radar"))
    pp = [(p, pf["strats"].get(f"radar_{p}")) for p in ("prudent", "équilibré", "dynamique")]
    if all(x for _, x in pp):
        lignes.append("  Par profil, radar contre moyenne du profil : " + " ; ".join(
            f"{p} {_sn(x['perf'] * 100, 2)} % contre {_sn(x['ref'] * 100, 2)} %" for p, x in pp))
    clair = ("  En clair : deux règles sont appliquées sans argent réel, avec les mêmes frais. « Radar » suit le classement du modèle ; "
             "« momentum » achète simplement ce qui a le plus monté sur 12 mois. Si le radar ne fait pas mieux que cette règle "
             "naïve, sa complexité ne sert à rien. Les indices réels (S&P 500, Stoxx 600) montrent ce qu'aurait rapporté un simple "
             "fonds indiciel. Par profil, la même règle est appliquée dans chaque tiers de risque et jugée contre la "
             "moyenne de ce tiers. « Radar avec frein » répartit ses lignes entre les cinq tranches de tendance quand le frein est actif, "
             "pour mesurer si ce garde-fou évite les pertes des rebonds. Il faut plusieurs mois pour conclure.")
    if pf["seances"] == 0:
        app = "portefeuilles constitués lors de ce passage ; premiers résultats dès la prochaine séance."
    elif pf["seances"] < 60:
        app = (f"tendance provisoire : le radar est {'en avance' if ecart > 0 else 'en retard'} de {_n(abs(ecart), 2)} pt sur la moyenne "
               f"et {'en avance' if ecart_m > 0 else 'en retard'} de {_n(abs(ecart_m), 2)} pt sur le momentum ; trop tôt pour conclure "
               f"({pf['seances']} séance{'s' if pf['seances'] > 1 else ''} sur au moins 60).")
    elif ecart > 0 and ecart_m > 0:
        app = (f"le radar devance la moyenne et le momentum ({R['gagnees']} périodes gagnées sur {R['periodes']}) ; "
               "résultat encourageant, à confirmer dans la durée.")
    else:
        app = ("le radar ne bat pas " + ("la moyenne" if ecart <= 0 else "la règle naïve du momentum")
               + f" ({R['gagnees']} périodes gagnées sur {R['periodes']}) : pas d'intérêt démontré à suivre ses signaux.")
    return [titre] + lignes + [clair, f"  Appréciation : {app}"]


def _bloc_etat(rep):
    anomalies = ([f"cours figés depuis {rep['stale_days']} jours"] if rep.get("stale_days", 0) > 4 else []) + rep.get("errors", [])
    plus = f" (+{len(anomalies) - 3} autres, voir data/status.json)" if len(anomalies) > 3 else ""
    fait = ("  ANOMALIES : " + " ; ".join(anomalies[:3]) + plus) if anomalies else "  Toutes les sources ont répondu"
    mineures = ("faute d'historique", "contrôle croisé", "secteurs des valeurs sorties")
    graves = [a for a in anomalies if not any(m in a for m in mineures)]
    app = ("données incomplètes, les blocs ci-dessus sont à lire avec réserve." if graves
           else "écarts mineurs (valeurs récentes ou contrôles annexes), sans effet notable sur le brief." if anomalies
           else "collecte complète, le brief repose sur des données à jour.")
    return ["7. État de la collecte", fait, f"  Appréciation : {app}"]


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
          "  En clair : VIX = nervosité ; taux 10 ans = coût de l'argent à long terme ; pétrole, or, dollar = thermomètres de l'économie mondiale ; "
          "Nikkei, Hang Seng, Shanghai = santé des bourses asiatiques."]
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
          f"  Règle de maintien (garder tant que dans les 50 % premières) : net de frais {_sn(rs.get('net_maintien', float('nan')) * 100, 2)} % par {main} j, "
          f"rotation {_p(rs.get('rotation_maintien', float('nan')))} contre {_p(rs.get('rotation', float('nan')))} sans maintien",
          f"  Liens événement × secteur validés : {rep['n_sig']} significatifs sur {rep['n_tests']} testés",
          "  En clair : une famille de variables n'est gardée que si elle améliore réellement la prévision. "
          "Le ratio d'information rapporte le gain à sa régularité : au-dessus de 0,5, le résultat est plutôt régulier."]
    irn = rs.get("ir_net", float("nan"))
    L.append("  Appréciation : " + (("modèle sobre (seuls les prix sont retenus), " if not evl["groupes"] else "") + "résultat régulier hors échantillon ; "
                                    if not math.isnan(irn) and irn >= 0.5 else "résultat hors échantillon encore irrégulier ; ")
             + ("aucun lien actualité × secteur n'est encore prouvé." if not rep["n_sig"] else f"{rep['n_sig']} liens actualité × secteur confirmés."))
    L.append("")
    pf = rep.get("portefeuille")
    L.append("F. Portefeuille fictif")
    if pf and "strats" in pf:
        R, M = pf["strats"]["radar"], pf["strats"]["momentum"]
        for nom, S in (("Radar", R), ("Momentum", M)):
            if S.get("semaine"):
                sm = S["semaine"]
                L.append(f"  {nom} sur 5 séances : {_sn(sm['pf'] * 100, 2)} %, moyenne de l'univers {_sn(sm['moy'] * 100, 2)} %")
        L.append(f"  Depuis le {pf['debut']} : {_perf_line(pf)}")
        pp = [(p, pf["strats"].get(f"radar_{p}")) for p in ("prudent", "équilibré", "dynamique")]
        if all(x for _, x in pp):
            L.append("  Par profil (radar contre moyenne du profil, périodes gagnées) : " + " ; ".join(
                f"{p} {_sn(x['perf'] * 100, 2)} % contre {_sn(x['ref'] * 100, 2)} %, {x['gagnees']} sur {x['periodes']}" for p, x in pp))
        L.append(f"  Périodes de 5 séances gagnées contre la moyenne : radar {R['gagnees']} sur {R['periodes']}, "
                 f"momentum {M['gagnees']} sur {M['periodes']} ; frais payés : radar {_n(R['frais'] * 100, 2)} %, "
                 f"momentum {_n(M['frais'] * 100, 2)} %")
        L.append("  En clair : une période est « gagnée » quand la règle fait mieux que la moyenne entre deux revues. "
                 "Une règle sans valeur en gagne environ une sur deux.")
        n = R["periodes"]
        L.append("  Appréciation : " + ("historique encore trop court, aucune conclusion possible." if n < 4 else
                                        "le radar gagne nettement plus souvent qu'à pile ou face et devance le momentum."
                                        if R["gagnees"] / n >= 0.6 and R["perf"] > M["perf"] else
                                        "résultats proches du hasard ou inférieurs au momentum : la règle n'a pas encore fait ses preuves."))
    else:
        L.append("  Indisponible lors de ce passage.")
    L.append("")
    return L


def generate(rep, out_dir):
    out = pathlib.Path(out_dir)
    demo = rep["mode"] == "demo"
    main = str(rep["main_horizon"])
    evl = rep["eval"]
    tag = " (DÉMO, données synthétiques)" if demo else ""
    hist = _save_hist(out, _load_hist(out), rep)

    daily = [f"Radar bourse, cours au {rep['as_of']}, généré le {rep.get('generated_utc', '')} UTC{tag}", ""]
    for bloc in (_bloc_valeurs(rep, main, hist), _bloc_profils(rep), _bloc_techno(rep), _bloc_alerte(rep),
                 _bloc_fiabilite(rep, main, evl), _bloc_portefeuille(rep), _bloc_etat(rep)):
        daily += bloc + [""]
    weekly = _hebdo(rep, main, evl, hist, tag)
    daily.append("Veille informative, pas un conseil en investissement.")
    weekly.append("Veille informative, pas un conseil en investissement.")

    (out / "brief.md").write_text("\n".join(daily) + "\n", encoding="utf-8")
    (out / "brief_weekly.md").write_text("\n".join(weekly) + "\n", encoding="utf-8")
    return daily
