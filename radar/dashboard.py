"""Tableau de bord HTML autonome (aucune dépendance, thème clair/sombre, tableaux = vue accessible)."""
from html import escape as e

CSS = """
:root{color-scheme:light;--bg:#f4f4f2;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--mute:#7a7974;--grid:#e3e2de;
--s1:#2a78d6;--s2:#eb6834;--warn-bg:#fdf1e6;}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--mute:#98978f;--grid:#2d2d2b;--s1:#3987e5;--s2:#d95926;--warn-bg:#2a2118;}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 48px}
h1{font-size:22px;margin:0}h2{font-size:16px;margin:0 0 4px}.sub{color:var(--ink2);font-size:13px;margin:0 0 12px}
.card{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px;margin-top:16px}
.banner{background:var(--warn-bg);border:1px solid var(--s2);border-radius:10px;padding:10px 14px;margin-top:12px;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:16px}
.kpi{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:12px 14px}
.kpi b{display:block;font-size:24px;font-variant-numeric:tabular-nums}.kpi span{color:var(--ink2);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;color:var(--ink2);font-weight:500;font-size:12px;
border-bottom:1px solid var(--grid);padding:6px 8px}td{padding:8px;border-bottom:1px solid var(--grid);vertical-align:middle}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.row{display:grid;grid-template-columns:150px 1fr 90px;gap:10px;align-items:center;padding:5px 0;font-size:14px}
.track{position:relative;height:10px;background:var(--grid);border-radius:5px;overflow:hidden}
.fill{position:absolute;top:0;bottom:0;border-radius:4px}.mid{position:absolute;left:50%;top:-2px;bottom:-2px;width:2px;background:var(--surface)}
.one{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--ink2)}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;border:1px solid var(--grid);font-size:12px;color:var(--ink2)}
.pc{display:flex;align-items:center;gap:6px;min-width:96px}.pc .track{width:54px;flex:none}.pc span{font-variant-numeric:tabular-nums;width:38px;text-align:right}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.mute{color:var(--mute);font-size:12px}ul{margin:0;padding-left:18px}li{margin:6px 0}
@media (max-width:640px){.row{grid-template-columns:110px 1fr 70px}th.h,td.h{display:none}}
"""


def pct(x):
    return f"{x * 100:.0f} %"


def cbar(p):
    """Barre centrée sur 50 % : bleu = hausse, orange = baisse. Texte en couleur d'encre."""
    w = abs(p - 0.5) * 100
    if p >= 0.5:
        f = f'<div class="fill" style="left:50%;width:{w:.1f}%;background:var(--s1)"></div>'
    else:
        f = f'<div class="fill" style="right:50%;width:{w:.1f}%;background:var(--s2)"></div>'
    return f'<div class="pc" title="Probabilité de battre le marché : {pct(p)}"><div class="track">{f}<div class="mid"></div></div><span>{pct(p)}</span></div>'


def spark(v):
    lo, hi = min(v), max(v)
    pts = " ".join(f"{i * 94 / (len(v) - 1) + 1:.1f},{25 - (x - lo) / (hi - lo + 1e-9) * 22:.1f}" for i, x in enumerate(v))
    ex, ey = pts.split()[-1].split(",")
    chg = (v[-1] / v[0] - 1) * 100
    return (f'<svg width="98" height="28" role="img" aria-label="Cours sur 60 jours : {chg:+.1f} %"><title>60 jours : {chg:+.1f} %</title>'
            f'<polyline points="{pts}" fill="none" stroke="var(--s1)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{ex}" cy="{ey}" r="3.5" fill="var(--s1)" stroke="var(--surface)" stroke-width="2"/></svg>')


def hbar(label, value, vmax, text, tip="", neg=False, one=None):
    w = max(0.0, min(100.0, value / vmax * 100))
    col = "var(--s2)" if neg else "var(--s1)"
    mark = f'<div class="one" style="left:{one / vmax * 100:.1f}%"></div>' if one is not None else ""
    return (f'<div class="row" title="{e(tip)}"><div>{e(label)}</div><div class="track"><div class="fill" style="left:0;width:{w:.1f}%;background:{col}"></div>{mark}</div>'
            f'<div class="mute" style="text-align:right;color:var(--ink2)">{e(text)}</div></div>')


def dbar(label, value, vmax, text, tip=""):
    w = min(50.0, abs(value) / vmax * 50)
    side = f"left:50%;width:{w:.1f}%;background:var(--s1)" if value >= 0 else f"right:50%;width:{w:.1f}%;background:var(--s2)"
    return (f'<div class="row" title="{e(tip)}"><div>{e(label)}</div><div class="track"><div class="fill" style="{side}"></div><div class="mid"></div></div>'
            f'<div class="mute" style="text-align:right;color:var(--ink2)">{e(text)}</div></div>')


def render(rep, path):
    bt, main = rep["backtest"], str(rep["main_horizon"])
    b = bt[main]
    gain = b["auc"] - bt["price_only"]["auc"]
    demo = rep["mode"] == "demo"
    jr = {(j["horizon"], j["kind"]): j for j in rep["journal"]}
    jmain = jr.get((rep["main_horizon"], "replay")) or jr.get((rep["main_horizon"], "live"))
    out = [f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>Radar bourse</title><style>{CSS}</style></head><body><main>',
           f'<h1>Radar bourse</h1><p class="sub">Situation au {e(rep["as_of"])} · {len(rep["all_p5"])} valeurs suivies · {rep["n_articles"]} signaux analysés · généré le {e(rep.get("generated_utc", ""))} UTC</p>']
    if demo:
        out.append('<div class="banner"><b>Mode démo : données synthétiques.</b> Les cours et articles sont simulés avec des effets cachés pour tester la mécanique. '
                   'Aucun chiffre ci-dessous ne décrit le marché réel.</div>')
    if rep.get("errors") or rep.get("stale_days", 0) > 4:
        msg = ([f'Cours figés depuis {rep["stale_days"]} jours.'] if rep.get("stale_days", 0) > 4 else []) + rep.get("errors", [])
        out.append('<div class="banner"><b>Anomalies de collecte :</b> ' + e(" · ".join(msg)) + '</div>')
    out.append('<div class="banner" style="background:var(--surface);border-color:var(--grid)">Outil d\'aide à la veille, pas un conseil en investissement. '
               'Les probabilités sont volontairement rapprochées de 50 % tant que le journal n\'a pas prouvé leur fiabilité.</div>')
    kp = [(f'{b["auc"]:.2f}', f'AUC backtest à {main} j (0,50 = hasard)'),
          (f'{gain:+.2f}', "AUC apporté par les actualités"),
          (pct(b["acc_conf"]), f'Précision si confiance forte (n={b["n_conf"]})'),
          (pct(jmain["hit"]) if jmain else "n/d", f'Réussite journal à {main} j (n={jmain["n"] if jmain else 0})'),
          (pct(rep["suivi"]["beat"]) if rep.get("suivi", {}).get("n") else "en cours",
           f'Valeurs signalées battant le marché à {main} j (n={rep.get("suivi", {}).get("n", 0)})'),
          (f'{rep["shrink"]:.2f}', "Coefficient de confiance (0,1 à 1)")]
    out.append('<div class="kpis">' + "".join(f'<div class="kpi"><b>{v}</b><span>{e(t)}</span></div>' for v, t in kp) + '</div>')

    # Valeurs à surveiller
    hz = rep["horizons"]
    rows = "".join(
        f'<tr><td><b>{e(w["name"])}</b><div class="mute">{e(w["ticker"])} · {e(w["sector"])}</div></td>'
        + "".join(f'<td>{cbar(w["p"][str(h)])}</td>' for h in hz)
        + f'<td class="h">{spark(w["spark"])}</td><td class="h"><span class="pill">{e(w["driver"])}</span>' + (' <span class="pill">résultats sous 5 j</span>' if w.get("earn") else "") + '</td>'
        f'<td class="n h">{w["mentions"]:.1f}×</td></tr>' for w in rep["watch"])
    out.append('<section class="card"><h2>Valeurs à surveiller</h2><p class="sub">Classées par attention : intensité des actualités, volatilité inhabituelle et conviction du modèle. '
               'Probabilité de faire mieux que la moyenne des valeurs suivies. Barre bleue = surperformance probable, orange = sous-performance.</p><div style="overflow-x:auto"><table><thead><tr><th>Valeur</th>'
               + "".join(f'<th>Surperf. à {h} j</th>' for h in hz)
               + '<th class="h">60 jours</th><th class="h">Pilote</th><th class="n h">Mentions</th></tr></thead><tbody>' + rows + '</tbody></table></div></section>')

    # Secteurs + technologies
    sv = max(abs(s["score"]) for s in rep["sectors"]) or 1
    sec = "".join(dbar(s["sector"], s["score"], sv, s["label"], f'Rendement 20 j {s["ret20"] * 100:+.1f} % · pilote : {s["driver"]}') for s in rep["sectors"])
    zv = max(max(t["z"] for t in rep["techs"]), 3)
    tec = "".join(hbar(t["tech"], max(t["z"], 0), zv, f'{t["status"]}',
                       f'{t["m7"]} mentions sur 7 j · valeurs liées : {", ".join(t["related"]) or "aucune"}') for t in rep["techs"][:8])
    out.append('<div class="grid2"><section class="card"><h2>Tendances sectorielles</h2><p class="sub">Momentum 20 j et signal d\'actualité combinés. Passez la souris pour le détail.</p>'
               + sec + '</section><section class="card"><h2>Technologies à veiller</h2><p class="sub">Mentions des 7 derniers jours contre la norme des 60 jours précédents (écart en z).' + (f' <b>En calibrage : encore {rep["calib_days"]} jours de bourse d\'articles à accumuler avant toute alerte.</b>' if rep.get("calib_days") else '') + '</p>'
               + tec + '</section></div>')

    # Catégories
    hv = max(max((h["ratio"] or 0) for h in rep["heat"]), 2)
    heat = "".join(hbar(h["cat"], h["ratio"] or 0, hv, f'×{h["ratio"]:.1f}' if h["ratio"] is not None else 'calibrage', f'{h["s7"]:.1f} d\'intensité sur 7 j', one=1.0) for h in rep["heat"])
    out.append('<section class="card"><h2>Pression par type d\'événement</h2><p class="sub">Intensité des 7 derniers jours rapportée à la normale (trait gris = 1,0 = normal).</p>' + heat + '</section>')

    # Adaptation
    ws = "".join(hbar(x["key"], x["value"], 2.5, f'{x["value"]:.2f}', f'{x["hits"]:.0f}/{x["n"]:.0f} jours justes · z = {x["z"]:+.1f}', one=1.0) for x in rep["weights_source"])
    wc = "".join(hbar(x["key"], x["value"], 2.5, f'{x["value"]:.2f}', f'{x["hits"]:.0f}/{x["n"]:.0f} jours justes · z = {x["z"]:+.1f}', one=1.0) for x in rep["weights_pairs"][:10]) \
        or '<p class="mute">Aucun couple n\'a encore passé le test. Tous les poids restent à 1,0.</p>'
    out.append('<div class="grid2"><section class="card"><h2>Fiabilité apprise des sources</h2><p class="sub">Poids 1,0 = neutre. Un poids ne bouge que si l\'écart au hasard est statistiquement significatif.</p>'
               + ws + '</section><section class="card"><h2>Couples événement × secteur validés</h2><p class="sub">' + f'{rep["n_sig"]} signaux significatifs sur {rep["n_tests"]} testés. ' + 'Au-dessus de 1,0 : le lien se vérifie. En dessous : il joue à l\'envers.</p>' + wc + '</section></div>')

    # Backtest
    trs = "".join(f'<tr><td>{h} j</td><td class="n">{bt[str(h)]["acc"] * 100:.1f} %</td><td class="n">{bt[str(h)]["base"] * 100:.1f} %</td>'
                  f'<td class="n">{bt[str(h)]["auc"]:.3f}</td><td class="n">{bt[str(h)]["brier"]:.3f}</td>'
                  f'<td class="n">{bt[str(h)]["acc_conf"] * 100:.1f} % ({bt[str(h)]["n_conf"]})</td></tr>' for h in hz)
    po = bt["price_only"]
    sc_txt = f" Sans le calendrier : AUC {bt['sans_calendrier']['auc']:.3f}." if "sans_calendrier" in bt else ""
    sc_txt += f" Sans les indicateurs de marché : AUC {bt['sans_marches']['auc']:.3f}." if "sans_marches" in bt else ""
    out.append('<section class="card"><h2>Fiabilité du modèle (backtest sans fuite)</h2><p class="sub">Entraînement sur le passé seul, test sur 5 périodes successives, écart de h jours entre les deux. '
               'Cible : battre la moyenne des valeurs suivies. Poids neutres (les poids appris utilisent des résultats futurs). Les rendements se chevauchent : lire les chiffres comme des ordres de grandeur.</p>'
               '<div style="overflow-x:auto"><table><thead><tr><th>Horizon</th><th class="n">Précision</th><th class="n">Référence (toujours la même direction)</th><th class="n">AUC</th><th class="n">Brier</th><th class="n">Précision si confiance forte (n)</th></tr></thead><tbody>'
               + trs + f'</tbody></table></div><p class="mute">Sans les actualités (prix seuls, {main} j) : AUC {po["auc"]:.3f}, précision {po["acc"] * 100:.1f} %.{sc_txt}</p></section>')

    # Événements
    ev = "".join(f'<li><b>{e(x["date"])}</b> · {e(x["source"])} · {e(x["title"])} <span class="pill">{e(", ".join(x["cats"]))}</span></li>' for x in rep["events"])
    mk = "".join(f'<tr><td>{e(x["label"])}</td><td class="n">{x["niveau"]:.2f}</td><td class="n">'
                 + (f'{x["chg20"]:+.2f} pt' if x["points"] else f'{x["chg20"] * 100:+.1f} %') + f'</td><td class="n mute">{e(x["date"])}</td></tr>'
                 for x in rep.get("marches", []))
    if mk:
        al = ('<p class="sub"><b>Alertes : ' + e(" ; ".join(rep["alertes_marche"])) + '</b></p>') if rep.get("alertes_marche") else ''
        out.append('<section class="card"><h2>Marchés</h2><p class="sub">Niveau et variation sur 20 séances. Alerte si VIX au-dessus de 25 ou en hausse de 30 % en 5 séances, pétrole ±15 %, dollar ±4 %, taux ±0,40 point.</p>'
                   + al + '<table><thead><tr><th>Indicateur</th><th class="n">Niveau</th><th class="n">20 séances</th><th class="n">Au</th></tr></thead><tbody>' + mk + '</tbody></table></section>')
    ag = "".join(f'<li><b>{e(a["date"])}</b> · {e(a["label"])}</li>' for a in rep.get("agenda", []))
    out.append('<section class="card"><h2>Agenda</h2><p class="sub">Résultats des 7 prochains jours et décisions de la Fed et de la BCE des 14 prochains jours.</p>'
               + (f'<ul>{ag}</ul>' if ag else '<p class="mute">Rien d\'inscrit pour l\'instant.</p>') + '</section>')
    out.append('<section class="card"><h2>Événements marquants</h2><p class="sub">Trois dernières séances.</p><ul>' + ev + '</ul></section>')
    out.append('</main></body></html>')
    open(path, "w", encoding="utf-8").write("".join(out))
