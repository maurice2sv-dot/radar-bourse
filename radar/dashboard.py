"""Tableau de bord HTML autonome (aucune dépendance ni script, thème clair/sombre, graphes en HTML et SVG).
Ordre de lecture : climat du jour, valeurs à surveiller, ensemble du classement, contexte, preuves."""
from html import escape as e

CSS = """
:root{color-scheme:light;--bg:#edf1f4;--surface:#fff;--ink:#102338;--ink2:#47596b;--line:#d5dee6;--track:#e6ecf1;
--up:#1b6fb8;--down:#c2560f;--alt:#7556b0;--teal:#0f7f72;--calm:#bfd8d2;--tense:#f1d9a6;--stress:#eeb48c;--crash:#d98b86;--warn:#fdf0df;--head:#102338;--headink:#f3f7fa;--head2:#b4c6d6}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#0e1925;--surface:#152435;--ink:#e8eff5;--ink2:#a9bac9;--line:#2a3d51;--track:#203348;
--up:#5aa9e6;--down:#f08a4b;--alt:#b39ae6;--teal:#4cc3b2;--calm:#2f5a52;--tense:#75602b;--stress:#85492a;--crash:#7c3532;--warn:#3a2c17;--head:#1b3046;--headink:#f3f7fa;--head2:#b4c6d6}}
*{box-sizing:border-box}html{scroll-behavior:smooth;-webkit-text-size-adjust:100%}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif;font-variant-numeric:tabular-nums}
h1,h2,h3,.big{font-family:"Avenir Next","Bahnschrift","Segoe UI",system-ui,sans-serif;line-height:1.2}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
header{background:var(--head);color:var(--headink);padding:22px 0 24px}
h1{font-size:15px;font-weight:600;margin:0;color:var(--head2)}.big{font-size:30px;font-weight:700;margin:6px 0 4px}
header p{margin:0;color:var(--head2);font-size:14px}
.gauge{margin-top:18px;max-width:620px}.scale{position:relative;display:flex;height:14px;border-radius:7px}
.scale i{display:block;height:100%}.scale i:first-child{border-radius:7px 0 0 7px}.scale i:nth-child(4){border-radius:0 7px 7px 0}
.needle{position:absolute;top:-5px;width:4px;height:24px;margin-left:-2px;border-radius:2px;background:var(--headink);box-shadow:0 0 0 2px var(--head)}
.zones{display:flex;font-size:12px;color:var(--head2);margin-top:6px}.zones span{overflow:hidden;white-space:nowrap}
.alerts{list-style:none;margin:16px 0 0;padding:0}.alerts li{padding:7px 0;border-top:1px solid rgba(180,198,214,.25);font-size:14px}
nav{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;gap:20px;overflow-x:auto;white-space:nowrap}
nav a{color:var(--ink);text-decoration:none;font-size:14px;padding:11px 0}nav a:hover{text-decoration:underline}
a:focus-visible,summary:focus-visible{outline:3px solid var(--up);outline-offset:2px}
section{padding-top:30px;scroll-margin-top:36px}h2{font-size:21px;margin:0 0 4px}h3{font-size:16px;margin:0 0 6px}
.sub{color:var(--ink2);font-size:14px;margin:0 0 14px;max-width:75ch}.small{color:var(--ink2);font-size:12.5px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:14px;align-items:start}
.banner{background:var(--warn);border-radius:8px;padding:10px 14px;margin-top:14px;font-size:13.5px}
.up{color:var(--up)}.down{color:var(--down)}
.val{display:flex;flex-direction:column;gap:10px}.val .top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.val h3{margin:0;font-size:17px}.rank{text-align:right;white-space:nowrap}.rank b{font-size:26px;line-height:1}
.signal{font-weight:600;font-size:14px}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;border-top:1px solid var(--line);padding-top:10px}
.facts b{display:block;font-size:15px}.facts span{font-size:12px;color:var(--ink2)}
.spark{display:block;width:100%;height:56px}
.bar{display:grid;grid-template-columns:minmax(0,9.5em) 1fr 5.8em;gap:10px;align-items:center;padding:4px 0;font-size:14px}
.bar>span:last-child{text-align:right;font-size:13px;color:var(--ink2)}
.track{position:relative;height:10px;background:var(--track);border-radius:5px}
.track i{position:absolute;top:0;bottom:0;border-radius:3px}.track u{position:absolute;top:-3px;bottom:-3px;width:2px;margin-left:-1px;background:var(--ink2)}
.plot{display:grid;grid-template-columns:4.2em 1fr;gap:0 8px}.yax{position:relative;font-size:12px;color:var(--ink2);text-align:right}
.yax span{position:absolute;right:0;transform:translateY(-50%);white-space:nowrap}
.area{position:relative;border-left:1px solid var(--line);border-bottom:1px solid var(--line)}
.area svg{position:absolute;inset:0;width:100%;height:100%;overflow:visible}
.xax{grid-column:2;display:flex;justify-content:space-between;font-size:12px;color:var(--ink2);padding-top:4px}
.hist{display:flex;align-items:flex-end;gap:2px;height:150px;border-bottom:1px solid var(--line)}
.hist i{flex:1;border-radius:3px 3px 0 0;min-width:0}
.pins{position:relative;height:30px}.pins span{position:absolute;top:4px;width:22px;height:22px;margin-left:-11px;border-radius:50%;background:var(--ink);color:var(--surface);font-size:12px;font-weight:700;text-align:center;line-height:22px}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;margin:10px 0 0;padding:0;list-style:none;font-size:13.5px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--ink2);font-weight:600;font-size:12.5px;border-bottom:1px solid var(--line);padding:6px 8px 6px 0}
td{padding:7px 8px 7px 0;border-bottom:1px solid var(--line);vertical-align:top}.n{text-align:right;white-space:nowrap}
.list{margin:0;padding:0;list-style:none}.list li{padding:8px 0;border-bottom:1px solid var(--line);font-size:14px}
details{margin-top:14px}summary{cursor:pointer;font-weight:600;padding:12px 16px;background:var(--surface);border:1px solid var(--line);border-radius:10px}
details>div{padding-top:14px}
footer{margin-top:34px;padding:18px 0 40px;border-top:1px solid var(--line);font-size:13px;color:var(--ink2)}
@media (max-width:560px){.m{display:none}td{padding-right:5px}.big{font-size:25px}.bar{grid-template-columns:minmax(0,7.5em) 1fr 5.2em;gap:8px;font-size:13.5px}}
"""


def num(x, d=1, signe=False):
    """Nombre à la française ; n.d. si absent."""
    if x is None or x != x:
        return "n.d."
    s = f"{x:+.{d}f}" if signe else f"{x:.{d}f}"
    return s.replace(".", ",")


def pc(x, d=1, signe=False):
    return "n.d." if x is None or x != x else num(x * 100, d, signe) + " %"


def jour(iso):
    p = str(iso)[:10].split("-")
    return f"{p[2]}/{p[1]}" if len(p) == 3 else str(iso)


def rang(r):
    return "1re" if r == 1 else f"{r}e"


def sens(x):
    return "up" if x >= 0 else "down"


def barre(label, a, b, color, texte, repere=None, tip=""):
    """Barre horizontale de a à b (en % de la piste)."""
    g, d = sorted((max(0.0, min(100.0, a)), max(0.0, min(100.0, b))))
    fill = f'<i style="left:{g:.1f}%;width:{max(d - g, 0.8):.1f}%;background:var(--{color})"></i>' if d - g > 0.05 else ""
    mark = f'<u style="left:{repere:.1f}%"></u>' if repere is not None else ""
    return f'<div class="bar" title="{e(tip)}"><span>{e(label)}</span><span class="track">{fill}{mark}</span><span>{texte}</span></div>'


def divergente(label, v, vmax, texte, tip=""):
    return barre(label, 50, 50 + v / (vmax or 1) * 50, sens(v), texte, 50, tip)


def poly(pts, color, width=2, dash=""):
    d = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    return (f'<polyline points="{d}" fill="none" stroke="var(--{color})" stroke-width="{width}" stroke-dasharray="{dash}" '
            'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>')


def points(pts, color, taille, opacite=1.0):
    """Points ronds quelle que soit la déformation du graphe (segments nuls à bout rond)."""
    d = "".join(f"M{x:.2f} {y:.2f}h0" for x, y in pts)
    return (f'<path d="{d}" stroke="var(--{color})" stroke-width="{taille}" stroke-linecap="round" fill="none" '
            f'opacity="{opacite}" vector-effect="non-scaling-stroke"/>') if d else ""


def graphe(svg, ylabels, xlabels, hauteur, alt):
    y = "".join(f'<span style="top:{pos:.1f}%">{t}</span>' for pos, t in ylabels)
    x = "".join(f"<span>{t}</span>" for t in xlabels)
    return (f'<div class="plot"><div class="yax">{y}</div><div class="area" style="height:{hauteur}px">'
            f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="{e(alt)}">{svg}</svg></div>'
            f'<div class="xax">{x}</div></div>')


def spark(v):
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    pts = [(i * 98 / (len(v) - 1) + 1, 94 - (x - lo) / (hi - lo + 1e-9) * 88) for i, x in enumerate(v)]
    chg = v[-1] / v[0] - 1
    color = "ink2"  # neutre : la couleur bleu/orange est réservée au signal du modèle
    return (f'<svg class="spark" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Cours sur 60 jours : {pc(chg, 1, True)}">'
            f'{poly(pts, color)}{points(pts[-1:], color, 7)}</svg><div class="small">Cours sur 60 jours : <b>{pc(chg, 1, True)}</b></div>')


# ---------------------------------------------------------------- sections

def entete(rep):
    rg = rep.get("regime") or {}
    h = [f'<header><div class="wrap"><h1>Radar bourse, cours au {jour(rep["as_of"])}</h1>']
    if rg.get("niveau"):
        h.append(f'<div class="big">Climat de marché : {e(rg["niveau"])}</div><p>{e(" ; ".join(rg.get("raisons", [])))}. '
                 'Frein anti-krach ' + ("actif" if rg.get("frein") else "inactif") + '.</p>')
        vix = rg.get("vix")
        if vix is not None and vix == vix:
            zones = [("Calme", "calm", 20), ("Tension", "tense", 10), ("Stress", "stress", 10), ("Krach", "crash", 10)]
            h.append(f'<div class="gauge" role="img" aria-label="VIX {num(vix)} sur une échelle de 0 à 50"><div class="scale">'
                     + "".join(f'<i style="width:{w * 2}%;background:var(--{c})"></i>' for _, c, w in zones)
                     + f'<span class="needle" style="left:{max(0, min(vix, 50)) * 2:.1f}%"></span></div><div class="zones">'
                     + "".join(f'<span style="width:{w * 2}%">{n}</span>' for n, _, w in zones)
                     + f'</div><p>VIX {num(vix)} : bornes à 20, 30 et 40.</p></div>')
    else:
        h.append('<div class="big">Situation du jour</div>')
    if rep.get("alertes_marche"):
        h.append('<ul class="alerts">' + "".join(f"<li>{e(a[:1].upper() + a[1:])}</li>" for a in rep["alertes_marche"]) + "</ul>")
    h.append("</div></header>")
    return "".join(h)


def valeurs(rep):
    main = str(rep["main_horizon"])
    allp = rep["all_p5"]
    n = len(allp)
    rangs = {a["ticker"]: i + 1 for i, a in enumerate(sorted(allp, key=lambda a: -a["p5"]))}
    risque = rep.get("risque") or {}
    cartes = []
    for i, w in enumerate(rep["watch"][:3], 1):
        p = w["p"][main]
        r = rangs.get(w["ticker"])
        rk = risque.get(w["ticker"]) or {}
        faits = [(pc(w.get("ret5"), 1, True), "sur 5 séances"), (e(str(rk.get("profil", "n.d."))), "profil de risque"),
                 (num(rk.get("beta")), "bêta")]
        cartes.append(
            f'<article class="panel val"><div class="top"><div><h3>{i}. {e(w["name"])}</h3><div class="small">{e(w["ticker"])}, {e(w["sector"])}</div></div>'
            + (f'<div class="rank"><b>{rang(r)}</b><div class="small">sur {n}</div></div>' if r else "") + "</div>"
            f'<div class="signal {sens(p - .5)}">{"▲ Favorable" if p >= .5 else "▼ Défavorable"} : {pc(p)} à {main} jours</div>'
            + spark(w.get("spark") or [])
            + '<div class="facts">' + "".join(f"<div><b>{v}</b><span>{t}</span></div>" for v, t in faits) + "</div>"
            f'<div class="small">Thème d\'actualité dominant : {e(w["driver"])}' + (". Résultats sous 5 jours." if w.get("earn") else "") + "</div></article>")
    hz = rep["horizons"]
    lignes = "".join(
        f'<tr><td><b>{e(w["name"])}</b><div class="small">{e(w["sector"])}, {e(w["driver"])}'
        + (", résultats sous 5 j" if w.get("earn") else "") + '</div></td>'
        + "".join(f'<td class="n {sens(w["p"][str(h)] - .5)}">{"▲" if w["p"][str(h)] >= .5 else "▼"} {pc(w["p"][str(h)])}</td>' for h in hz)
        + f'<td class="n m">{num(w.get("mentions"))}×</td></tr>' for w in rep["watch"])
    return ('<section id="valeurs"><h2>Valeurs à surveiller</h2><p class="sub">Retenues pour l\'attention qu\'elles suscitent (actualité, volumes, résultats proches), '
            'pas pour leur place en tête. Le pourcentage est la chance de faire mieux que le secteur : 50 % équivaut à pile ou face.</p>'
            '<div class="cols">' + "".join(cartes) + '</div><details><summary>Les ' + str(len(rep["watch"])) + ' valeurs suivies de près, à tous les horizons</summary>'
            '<div class="panel scroll"><table><thead><tr><th>Valeur</th>' + "".join(f'<th class="n">{h} j</th>' for h in hz)
            + '<th class="n m">Mentions</th></tr></thead><tbody>' + lignes + '</tbody></table></div></details></section>')


def classement(rep):
    allp = rep["all_p5"]
    p = [a["p5"] for a in allp]
    ecart = max([abs(x - .5) for x in p] + [.001])
    nb = 30
    comptes = [0] * nb
    for x in p:
        comptes[min(nb - 1, int((x - (.5 - ecart)) / (2 * ecart) * nb))] += 1
    top = max(comptes) or 1
    barres = "".join(f'<i style="height:{c / top * 100:.1f}%;background:var(--{"up" if i >= nb // 2 else "down"})" title="{c} valeurs"></i>'
                     for i, c in enumerate(comptes))
    par = {a["ticker"]: a for a in allp}
    marques, noms, places = "", "", []
    for i, w in enumerate(rep["watch"][:3], 1):
        if w["ticker"] not in par:
            continue
        x = (par[w["ticker"]]["p5"] - (.5 - ecart)) / (2 * ecart) * 100
        x = max(3.0, min(97.0, x))
        dec = sum(1 for y in places if abs(y - x) < 7)
        places.append(x)
        marques += f'<span style="left:{min(97.0, x + dec * 7) if x < 80 else x - dec * 7:.1f}%">{i}</span>'
        noms += f"<li><b>{i}.</b> {e(w['name'])}</li>"
    h = (f'<section id="classement"><h2>Où se situent ces valeurs</h2><p class="sub">Répartition des {len(p)} valeurs selon leur chance de faire mieux que leur secteur. '
         f'Les écarts restent faibles : au plus {num(ecart * 100)} point autour de 50 %.</p><div class="cols"><div class="panel"><h3>Ensemble du classement</h3>'
         f'<div class="hist" role="img" aria-label="Histogramme des probabilités">{barres}</div><div class="pins">{marques}</div>'
         f'<div class="xax"><span>{pc(.5 - ecart)}</span><span>50 %</span><span>{pc(.5 + ecart)}</span></div><ul class="legend">{noms}</ul></div>')
    rq = rep.get("risque") or {}
    pts = [(rq[a["ticker"]]["vol"], a["p5"], a["ticker"]) for a in allp if a["ticker"] in rq and rq[a["ticker"]].get("vol") is not None]
    if pts:
        vmax = 1.0

        def xy(v, q):
            return min(v, vmax) / vmax * 100, 50 - (q - .5) / ecart * 47
        svg = '<line x1="0" x2="100" y1="50" y2="50" stroke="var(--ink2)" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>'
        svg += points([xy(v, q) for v, q, _ in pts if q >= .5], "up", 5, .5) + points([xy(v, q) for v, q, _ in pts if q < .5], "down", 5, .5)
        suivies = {w["ticker"] for w in rep["watch"][:3]}
        svg += points([xy(v, q) for v, q, t in pts if t in suivies], "ink", 11)
        h += ('<div class="panel"><h3>Signal et agitation</h3>'
              + graphe(svg, [(3, pc(.5 + ecart)), (50, "50 %"), (97, pc(.5 - ecart))], ["0 %", "volatilité annuelle", "100 % et plus"], 200,
                       "Nuage de points : volatilité en abscisse, probabilité en ordonnée")
              + '<p class="small">Un point par valeur ; les points foncés sont les 3 valeurs à surveiller. Plus un point est à droite, plus le cours est agité.</p></div>')
    h += "</div>"
    profils = rep.get("profils") or {}
    if profils:
        blocs = ""
        for nom, x in profils.items():
            blocs += (f'<div class="panel"><h3>Profil {e(nom)}</h3><div class="small">{x["n"]} valeurs, volatilité de {pc(x["vol_min"], 0)} à {pc(x["vol_max"], 0)}</div>'
                      '<ul class="list">' + "".join(
                          f'<li><b>{e(t["name"])}</b><div class="small">{rang(t["rang"])}, {pc(t["p5"])}, bêta {num(t.get("beta"))}</div></li>'
                          for t in x.get("top", [])) + "</ul></div>")
        h += '<h3 style="margin-top:20px">Les mieux classées par profil de risque</h3><div class="cols">' + blocs + "</div>"
    return h + "</section>"


def europe(rep):
    idx = [m for m in rep.get("marches") or [] if m.get("europe")]
    val = rep.get("europe") or []
    if not idx and not val:
        return ""
    h = ['<section id="europe"><h2>Europe</h2><p class="sub">Grands indices et valeurs européennes suivies. Cours de clôture, en devise locale.</p>']
    if idx:
        h.append('<div class="cols">' + "".join(
            f'<div class="panel"><h3>{e(m["label"])}</h3><div class="small">{num(m["niveau"], 0)} au {e(m["date"])}. '
            f'1 séance <b class="{sens(m["chg1"])}">{pc(m["chg1"], 1, True)}</b>, 20 séances <b class="{sens(m["chg20"])}">{pc(m["chg20"], 1, True)}</b></div>'
            + spark(m.get("serie") or []) + "</div>" for m in idx) + "</div>")
    if val:
        n = len(rep["all_p5"])

        def var(x):
            return f'<td class="n {"" if x is None else sens(x)}">{pc(x, 1, True)}</td>'

        def table(lignes):
            return ('<div class="scroll"><table><thead><tr><th>Valeur</th><th class="n">Rang</th><th class="n">5 s.</th><th class="n">20 s.</th></tr></thead><tbody>'
                    + "".join(f'<tr><td>{e(x["name"])}</td><td class="n">{rang(x["rang"])}</td>{var(x.get("ret5"))}{var(x.get("ret20"))}</tr>' for x in lignes)
                    + "</tbody></table></div>")
        connues = sorted((x for x in val if x.get("ret20") is not None), key=lambda x: -x["ret20"])
        blocs = [("Mieux classées par le radar", val[:8]), ("Plus fortes sur 20 séances", connues[:8]), ("Plus faibles sur 20 séances", connues[::-1][:8])]
        h.append(f'<p class="small">Rang sur l\'ensemble des {n} valeurs. 5 s. et 20 s. : variation sur 5 et 20 séances.</p><div class="cols">'
                 + "".join(f'<div class="panel"><h3>{t}</h3>{table(v)}</div>' for t, v in blocs if v) + "</div>"
                 + f'<details><summary>Les {len(val)} valeurs européennes suivies</summary><div class="panel">{table(val)}</div></details>')
    return "".join(h) + "</section>"


def marches(rep):
    mk = [m for m in rep.get("marches") or [] if not m.get("europe")]
    h = ['<section id="marches"><h2>Marchés et actualité</h2><div class="cols">']
    if mk:
        vm = max([abs(x["chg20"]) for x in mk if not x["points"]] + [.01])
        corps = ""
        for x in mk:
            if x["points"]:
                corps += barre(x["label"], 50, 50, "up", num(x["chg20"], 2, True) + " pt", 50, "Variation en points")
            else:
                corps += barre(x["label"], 50, 50 + x["chg20"] / vm * 50, "ink2", pc(x["chg20"], 1, True), 50, f'Niveau {num(x["niveau"], 2)} au {x["date"]}')
        table = "".join(f'<tr><td>{e(x["label"])}</td><td class="n">{num(x["niveau"], 2)}</td><td class="n">'
                        + (num(x.get("chg1"), 2, True) + " pt" if x["points"] else pc(x.get("chg1"), 1, True)) + f'</td><td class="n">{e(x["date"])}</td></tr>' for x in mk)
        h.append('<div class="panel"><h3>Variation sur 20 séances</h3>' + corps
                 + '<p class="small">Alerte si VIX au-dessus de 25 ou en hausse de 30 % en 5 séances, pétrole ±15 %, dollar ±4 %, taux ±0,40 point, indice asiatique ±3 % sur une séance ou -10 % sur 20 séances.</p>'
                 '<div class="scroll"><table><thead><tr><th>Indicateur</th><th class="n">Niveau</th><th class="n">1 séance</th><th class="n">Au</th></tr></thead><tbody>'
                 + table + "</tbody></table></div></div>")
    heat = rep.get("heat") or []
    if heat:
        hv = max([x["ratio"] or 0 for x in heat] + [2])
        h.append('<div class="panel"><h3>Pression de l\'actualité</h3><p class="small">7 derniers jours rapportés à la normale (trait = ×1, habituel).</p>'
                 + "".join(barre(x["cat"], 0, (x["ratio"] or 0) / hv * 100, "up", "×" + num(x["ratio"]) if x["ratio"] is not None else "calibrage",
                                 100 / hv, f'Intensité sur 7 jours : {num(x["s7"])}') for x in heat) + "</div>")
    ag = "".join(f'<li><b>{e(a["date"])}</b> {e(a["label"])}</li>' for a in rep.get("agenda", []))
    ev = "".join(f'<li>{e(x["title"])}<div class="small">{e(x["date"])}, {e(x["source"])}, {e(", ".join(x["cats"]))}</div></li>' for x in rep.get("events", []))
    h.append('</div><div class="cols" style="margin-top:14px"><div class="panel"><h3>Agenda</h3><p class="small">Résultats sous 7 jours, décisions Fed et BCE sous 14 jours.</p>'
             + (f'<ul class="list">{ag}</ul>' if ag else "<p>Rien d'inscrit pour l'instant.</p>") + "</div>"
             '<div class="panel"><h3>Événements marquants</h3><p class="small">Trois dernières séances.</p>'
             + (f'<ul class="list">{ev}</ul>' if ev else "<p>Aucun événement retenu.</p>") + "</div></div></section>")
    return "".join(h)


def tendances(rep):
    h = ['<section id="tendances"><h2>Secteurs et technologies</h2><div class="cols">']
    sec = rep.get("sectors") or []
    if sec:
        sv = max(abs(s["score"]) for s in sec) or 1
        h.append('<div class="panel"><h3>Tendance par secteur</h3><p class="small">Dynamique sur 20 jours et signal d\'actualité combinés.</p>'
                 + "".join(divergente(s["sector"], s["score"], sv, e(s["label"]), f'Rendement 20 j {pc(s["ret20"], 1, True)}, pilote : {s["driver"]}') for s in sec) + "</div>")
    techs = (rep.get("techs") or [])[:8]
    if techs:
        calib = rep.get("calib_days")
        mv = max([t["m7"] for t in techs] + [1])
        zv = max([t["z"] for t in techs] + [3])
        corps = "".join(
            barre(t["tech"], 0, t["m7"] / mv * 100, "teal", f'{t["m7"]} mention{"s" if t["m7"] > 1 else ""}') if calib else
            barre(t["tech"], 0, max(t["z"], 0) / zv * 100, "teal", e(t["status"]), tip=f'{t["m7"]} mentions sur 7 jours') for t in techs)
        note = (f"En calibrage : encore {calib} jours de bourse avant toute alerte. Les barres montrent le volume brut des mentions sur 7 jours." if calib
                else "Mentions sur 7 jours comparées à la norme des 60 jours précédents (écart en z).")
        h.append(f'<div class="panel"><h3>Technologies à veiller</h3><p class="small">{note}</p>{corps}</div>')
    return "".join(h) + "</div></section>"


def portefeuille(rep):
    pf = rep.get("portefeuille")
    if not pf:
        return ""
    series = [("Radar", "radar", None, "up", ""), ("Momentum", "momentum", None, "down", ""),
              ("Moyenne des valeurs", None, "moyenne", "ink2", "5 4"), ("S&P 500", None, "S&P 500", "alt", ""),
              ("Stoxx 600", None, "Stoxx 600", "teal", "")]
    hist = pf.get("historique") or []
    courbes, legende = [], ""
    for nom, strat, ref, color, dash in series:
        cle = strat or ref
        perf = (pf["strats"].get(strat) or {}).get("perf") if strat else pf["refs"].get(ref)
        if perf is None:
            continue
        legende += f'<li><i style="background:var(--{color})"></i>{nom} <b>{pc(perf, 2, True)}</b></li>'
        v = [0.0] + [x[cle] / 100 - 1 for x in hist if cle in x]
        if len(v) > 1:
            courbes.append((v, color, dash, 3.5 if strat == "radar" else 2))
    g = ""
    if courbes:
        lim = max([abs(x) for v, *_ in courbes for x in v] + [.005]) * 1.1

        def xy(v):
            return [(i * 100 / (len(v) - 1), 50 - x / lim * 50) for i, x in enumerate(v)]
        svg = '<line x1="0" x2="100" y1="50" y2="50" stroke="var(--line)" vector-effect="non-scaling-stroke"/>'
        svg += "".join(poly(xy(v), c, w, d) + points(xy(v)[-1:], c, 8) for v, c, d, w in reversed(courbes))
        g = graphe(svg, [(0, pc(lim, 1, True)), (50, "0 %"), (100, pc(-lim, 1, True))], [jour(pf["debut"]), jour(rep["as_of"])], 220,
                   "Évolution du portefeuille fictif et des références")
    prof = ""
    for p in ("prudent", "équilibré", "dynamique"):
        a, b = (pf["strats"].get(f"radar_{p}") or {}).get("perf"), pf["refs"].get(f"moyenne_{p}")
        if a is not None and b is not None:
            prof += f'<tr><td>{p}</td><td class="n">{pc(a, 2, True)}</td><td class="n">{pc(b, 2, True)}</td><td class="n {sens(a - b)}">{num((a - b) * 100, 2, True)} pt</td></tr>'
    r = pf["strats"].get("radar") or {}
    return ('<section id="portefeuille"><h2>Portefeuille fictif</h2><p class="sub">Aucun argent réel. ' + e(pf["regle"][:1].upper() + pf["regle"][1:]) + '. '
            f'{pf["seances"]} séances depuis le {jour(pf["debut"])}, prochaine revue dans {pf["prochaine_revue"]} séances. Plusieurs mois sont nécessaires pour conclure.</p>'
            f'<div class="cols"><div class="panel">{g}<ul class="legend">{legende}</ul></div><div class="panel"><h3>Par profil de risque</h3><div class="scroll"><table><thead><tr><th>Profil</th>'
            '<th class="n">Radar</th><th class="n">Moyenne</th><th class="n">Écart</th></tr></thead><tbody>' + prof + '</tbody></table></div>'
            f'<p class="small">Radar : {r.get("n_lignes", 0)} lignes, pire baisse {pc(r.get("pire_baisse"), 2)}, frais payés {pc(r.get("frais"), 2)}. '
            f'Principales lignes : {e(", ".join(r.get("lignes", [])))}.</p></div></div></section>')


def fiabilite(rep):
    main = rep["main_horizon"]
    evl = rep["eval"]
    rs = evl.get("reserve") or {}
    fr = rep.get("fraiche") or {}
    su = rep.get("suivi") or {}
    h = ['<section id="fiabilite"><h2>Peut-on s\'y fier ?</h2><p class="sub">IC : ressemblance entre le classement prévu et le classement observé. '
         '0 = hasard ; 0,02 à 0,05 = avantage modeste. Un t inférieur à 2 laisse le hasard comme explication possible.</p>']
    requis = fr.get("requis", 20)
    suite = ""
    if fr.get("dates", 0) < requis:
        if not fr.get("dates") and fr.get("premier_attendu"):
            suite += f", premier résultat après la séance du {jour(fr['premier_attendu'])}"
        if fr.get("complet_attendu"):
            suite += f", {requis} dates vers le {jour(fr['complet_attendu'])}"
    recalcul = (f", calculé le {jour(evl['date'])}, prochain à partir du {jour(evl['prochain_recalcul'])}"
                if evl.get("date") and evl.get("prochain_recalcul") else "")
    attente = (f", fixe tant que moins de {rep['shrink_requis']} périodes en direct ({rep['shrink_periodes']})"
               if rep.get("shrink_requis") and rep.get("shrink_periodes", 0) < rep["shrink_requis"] else "")
    faits = [(num(fr.get("ic"), 3, True) if fr.get("ic") is not None else "en cours",
              f'IC sur la période fraîche, mesure de référence ({fr.get("dates", 0)} date{"s" if fr.get("dates", 0) > 1 else ""} sur {requis} depuis le {jour(fr.get("debut", ""))}{suite})'),
             (num(rs.get("ic"), 3, True), f'IC historique en test réservé (t = {num(rs.get("t"))}){recalcul}'),
             (pc(rs.get("net"), 2, True), f"20 % les mieux classées contre la moyenne, par {main} jours, après frais"),
             (pc(su.get("beat"), 0) if su.get("n") else "en cours", f'Valeurs signalées battant le marché à {main} jours ({su.get("n", 0)} cas)'),
             (num(rep.get("shrink"), 2), f"Coefficient de confiance (0,1 à 1){attente}")]
    h.append('<div class="cols">' + "".join(f'<div class="panel"><div class="big">{v}</div><div class="small">{e(t)}</div></div>' for v, t in faits) + "</div>")
    rg = evl.get("regimes") or {}
    groupes = [("Selon le climat de marché", rg.get("regimes") or {}), ("Pendant les épisodes de stress", rg.get("episodes") or {})]
    if any(g for _, g in groupes):
        vm = max([abs(x["ic"]) for _, g in groupes for x in g.values() if "ic" in x] + [.01])
        h.append('<div class="cols" style="margin-top:14px">')
        for titre, g in groupes:
            if g:
                h.append(f'<div class="panel"><h3>{titre}</h3><p class="small">IC hors échantillon. Le t et le résultat net figurent dans les mesures détaillées.</p>'
                         + "".join(divergente(k, x["ic"], vm, num(x["ic"], 3, True), f'{x["dates"]} dates, t = {num(x.get("t"))}, net {pc(x.get("net"), 2, True)}')
                                   if "ic" in x else barre(k, 0, 0, "up", "trop court") for k, x in g.items()) + "</div>")
        h.append("</div>")
    return "".join(h) + "</section>"


def methode(rep):
    main = rep["main_horizon"]
    evl = rep["eval"]
    rs, dev = evl.get("reserve") or {}, evl.get("dev") or {}

    def row(lbl, x):
        if not x or x.get("ic") is None:
            return f'<tr><td>{e(lbl)}</td><td colspan="7">{e(x.get("note", "non mesuré") if x else "non mesuré")}</td></tr>'
        cells = [num(x["ic"], 3, True), num(x.get("t")), pc(x.get("ic_pos"), 0), pc(x.get("brut"), 2, True), pc(x.get("net"), 2, True),
                 pc(x.get("rotation"), 0), num(x.get("ir_net"), 2)]
        return f'<tr><td>{e(lbl)}</td>' + "".join(f'<td class="n">{c}</td>' for c in cells) + "</tr>"
    head = ('<div class="panel scroll"><table><thead><tr><th></th><th class="n">IC</th><th class="n">t</th><th class="n">IC &gt; 0</th><th class="n">Brut</th>'
            '<th class="n">Net</th><th class="n">Rotation</th><th class="n">IR net</th></tr></thead><tbody>')
    noms = {"actualites": "actualités", "marches": "marchés"}
    h = ['<details><summary>Mesures détaillées et méthode</summary><div>',
         f'<p class="sub">Cible : faire mieux que la moyenne du secteur à {main} jours. Brut et net : 20 % les mieux classées contre la moyenne, '
         f'avant et après frais ({e(str(rep.get("cout_bps", 10)))} points de base par sens). Variables retenues : '
         f'{e(" + ".join(["prix"] + [noms.get(g, g) for g in evl.get("groupes", [])]))}.</p>', head,
         row(f"Test réservé ({rs.get('debut', '')} à {rs.get('fin', '')})", rs), row(f"Développement ({dev.get('debut', '')} à {dev.get('fin', '')})", dev),
         "</tbody></table></div>",
         f'<p class="small">La période réservée commence le {e(str(evl.get("reserve_debut", "")))} et ne sert à aucun choix (ouverte le {e(str(evl.get("reserve_ouverte_le", "")))}). '
         "Biais connu : l'univers est composé des grandes valeurs d'aujourd'hui, ce qui avantage le passé (biais du survivant).</p>"]
    rg = evl.get("regimes") or {}
    tous = list((rg.get("regimes") or {}).items()) + list((rg.get("episodes") or {}).items())
    if tous:
        h.append('<h3>Climats et épisodes</h3><div class="panel scroll"><table><thead><tr><th></th><th class="n">Dates</th><th class="n">IC</th><th class="n">t</th><th class="n">Net</th></tr></thead><tbody>'
                 + "".join(f'<tr><td>{e(k)}</td><td class="n">{x.get("dates", 0)}</td><td class="n">{num(x.get("ic"), 3, True)}</td><td class="n">{num(x.get("t"))}</td>'
                           f'<td class="n">{pc(x.get("net"), 2, True)}</td></tr>' for k, x in tous) + "</tbody></table></div>")
    if evl.get("trace"):
        h.append(f'<h3 style="margin-top:18px">Sélection des variables</h3><p class="small">Un groupe est gardé seulement s\'il améliore l\'IC d\'au moins {num(rep.get("gain_min_ic", .003), 3)} '
                 f'sur la période de développement. Dernier choix : {e(str(evl.get("date", "")))}.</p>' + head
                 + "".join(row(("✓ " if x["garde"] else "✗ ") + ("prix" if x["groupe"] == "prix" else "+ " + noms.get(x["groupe"], x["groupe"])), x) for x in evl["trace"])
                 + "</tbody></table></div>")

    def poids(x):
        return barre(x["key"], 0, x["value"] / 2.5 * 100, "up", num(x["value"], 2), 40, f'{x["hits"]:.0f} jours justes sur {x["n"]:.0f}, z = {num(x["z"], 1, True)}')
    ws = "".join(poids(x) for x in rep.get("weights_source", []))
    wc = "".join(poids(x) for x in rep.get("weights_pairs", [])[:10]) or "<p>Aucun couple n'a encore passé le test. Tous les poids restent à 1,0.</p>"
    h.append('<div class="cols" style="margin-top:18px"><div class="panel"><h3>Fiabilité apprise des sources</h3><p class="small">Trait = 1,0, neutre. Un poids ne bouge que si l\'écart au hasard est significatif.</p>'
             + ws + '</div><div class="panel"><h3>Couples événement et secteur validés</h3>'
             f'<p class="small">{rep.get("n_sig", 0)} signaux significatifs sur {rep.get("n_tests", 0)} testés.</p>' + wc + "</div></div></div></details>")
    return "".join(h)


def render(rep, path):
    out = ['<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>Radar bourse</title><style>{CSS}</style></head><body>', entete(rep)]
    pf = portefeuille(rep)
    eu = europe(rep)
    liens = [("valeurs", "Valeurs"), ("classement", "Classement")] + ([("europe", "Europe")] if eu else []) \
        + [("marches", "Marchés"), ("tendances", "Secteurs")] \
        + ([("portefeuille", "Portefeuille")] if pf else []) + [("fiabilite", "Fiabilité")]
    out.append('<nav aria-label="Sections"><div class="wrap">' + "".join(f'<a href="#{i}">{t}</a>' for i, t in liens) + '</div></nav><main class="wrap">')
    if rep["mode"] == "demo":
        out.append('<div class="banner"><b>Mode démo : données synthétiques.</b> Les cours et articles sont simulés pour tester la mécanique. '
                   "Aucun chiffre ci-dessous ne décrit le marché réel.</div>")
    stale = rep.get("stale_days", 0) > 4
    if rep.get("errors") or stale:
        msg = ([f'Cours figés depuis {rep["stale_days"]} jours.'] if stale else []) + rep.get("errors", [])
        out.append('<div class="banner"><b>Anomalies de collecte :</b> ' + e(" ; ".join(msg)) + "</div>")
    out += [valeurs(rep), classement(rep), eu, marches(rep), tendances(rep), pf, fiabilite(rep), methode(rep)]
    out.append(f'<footer>Veille informative, pas un conseil en investissement. Les probabilités sont volontairement rapprochées de 50 % tant que le journal n\'a pas prouvé leur fiabilité. '
               f'{len(rep["all_p5"])} valeurs suivies, {rep.get("n_articles", 0)} signaux analysés, généré le {e(rep.get("generated_utc", ""))} UTC.</footer></main></body></html>')
    open(path, "w", encoding="utf-8").write("".join(out))
