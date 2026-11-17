"""Lexiques, matrice d'exposition sectorielle et notation des articles.

La matrice EXPOSURE est un a priori (hypothèse métier). Le journal mesure ensuite
si chaque catégorie et chaque source tiennent leurs promesses (voir journal.py).
"""
import hashlib
import re

SECTORS = ["tech", "conso", "auto", "finance", "energie", "defense", "aero", "luxe", "sante",
           "distribution", "industrie", "materiaux", "services_publics", "telecom"]


def _U(base, **kw):
    d = {s: base for s in SECTORS}
    d.update(kw)
    return d


# Effet attendu d'un événement de la catégorie sur chaque secteur (signe et force).
EXPOSURE = {
    "militaire":    _U(0, defense=1.0, aero=0.5, energie=0.4, luxe=-0.3, tech=-0.1, conso=-0.1, finance=-0.1),
    "securitaire":  _U(0, defense=0.8, tech=0.2, luxe=-0.2, aero=-0.1),
    "politique":    _U(0.3, defense=0.1, energie=0.2),
    "financier":    _U(0.2, finance=0.6, tech=0.4, auto=0.3),
    "meteo":        _U(0, energie=0.5, conso=-0.2, auto=-0.1, aero=-0.2, luxe=-0.1),
    "economique":   _U(0.5, finance=0.7, luxe=0.6, auto=0.6),
    "scientifique": _U(0, tech=0.7, sante=0.7, aero=0.3, auto=0.3, energie=0.2),
    "religieux":    _U(0, luxe=-0.2, aero=-0.2, defense=0.2, conso=-0.1),
    "media":        _U(0.2),
}
# Catégories où le ton (positif/négatif) inverse l'effet. Les autres ne dépendent que de l'intensité.
SENSITIVE = {"politique", "financier", "economique", "scientifique", "media"}

KEYWORDS = {
    "militaire": r"guerre|\bwar\b|missile|frappes?\b|offensive|troupes|\barmy\b|armée|military|militaire|invasion|cessez-le-feu|ceasefire|\botan\b|\bnato\b|bombard|\bnavy\b|porte-avions",
    "securitaire": r"attentat|terroris|terror|cyber-?attaque|cyber-?attack|ransomware|sécurité|security|espionnage|espionage|sabotage|menace|threat|otage|hostage|piratage|\bhack",
    "politique": r"élection|election|gouvernement|government|parlement|parliament|sénat|senate|président|president|sanction|droits de douane|tariff|réforme|reform|budget|\bvotes?\b|coalition|référendum|traité|treaty|diplomat|sommet|summit",
    "financier": r"taux d'intérêt|interest rate|\bfed\b|\bbce\b|\becb\b|banque centrale|central bank|obligataire|\bbond\b|rendement|\byield|crédit|liquidité|liquidity|dividende|dividend|rachat d'actions|buyback|résultats|earnings|bénéfice|\bprofit|\bipo\b|acquisition",
    "meteo": r"ouragan|hurricane|tempête|\bstorm|sécheresse|drought|canicule|heat ?wave|inondation|\bflood|incendie|wildfire|cyclone|tornade|séisme|earthquake|\bgel\b|\bfrost|neige|\bsnow|el niño|la niña|météo|climat",
    "economique": r"inflation|récession|recession|croissance|\bgrowth|\bpib\b|\bgdp\b|chômage|unemployment|emploi|\bjobs\b|consommation|pénurie|shortage|supply chain|chaîne d'approvisionnement|export|déficit|\bdette|\bdebt|pétrole|\boil\b|\bgaz\b|\bgas\b|matières premières|commodit",
    "scientifique": r"découverte|discovery|percée|breakthrough|recherche|research|\bétude|\bstudy|essai clinique|clinical trial|brevet|patent|prototype|innovation|laboratoire|\bnasa\b|\besa\b|\bcern\b|vaccin|lancement|\blaunch|nobel",
    "religieux": r"église|church|vatican|\bpape\b|\bpope\b|mosquée|mosque|islam|musulman|muslim|juif|jewish|synagogue|religio|ramadan|pèlerinage|pilgrimage|clergé|chrétien|christian|hindou|hindu",
    "media": r"scandale|scandal|enquête|investigation|polémique|controvers|boycott|rappel de produits|\brecall|\bviral|\bfuite|\bleak|procès|lawsuit|\bamende|\bfine\b|démission|resign|licenci|layoff|grève|\bstrike|rumeur|rumor",
}
CATS = list(KEYWORDS)

# Expositions des secteurs ajoutés avec l'univers élargi (a priori, corrigé ensuite par les poids appris)
for _c, _kw in {
    "militaire": dict(industrie=0.1, materiaux=0.2, distribution=-0.1),
    "securitaire": dict(telecom=0.1, services_publics=-0.1),
    "financier": dict(services_publics=0.4, telecom=0.2),
    "meteo": dict(services_publics=0.4, distribution=-0.1, materiaux=0.1, industrie=-0.1),
    "economique": dict(industrie=0.7, materiaux=0.7, distribution=0.2, services_publics=0.2, telecom=0.2),
    "scientifique": dict(industrie=0.2, materiaux=0.2),
}.items():
    EXPOSURE[_c].update(_kw)

TECHS = {
    "ia": r"\bia\b|intelligence artificielle|\bai\b|artificial intelligence|\bllm",
    "semi-conducteurs": r"semi-?conducteur|semiconductor|\bpuces?\b|\bchips?\b|\bgpu",
    "quantique": r"quantique|quantum",
    "hydrogene": r"hydrog[eè]ne|hydrogen",
    "batteries": r"batteri|battery|lithium|solid-state",
    "drones": r"\bdrones?\b",
    "cyber": r"cyber",
    "spatial": r"spatial|satellite|space launch|fus[ée]e|rocket",
    "robotique": r"robot",
    "biotech": r"biotech|glp-1|thérapie génique|gene therapy|crispr",
    "cloud": r"\bcloud\b|data ?center",
    "nucleaire": r"nucléaire|nuclear|fusion nucl",
}

POS = r"hausse|record|croissance|accord|bénéfice|\bbenefit|percée|breakthrough|succès|\bsuccess|rebond|relance|approuv|\bapprov|surperform|\bbeat\b|\bsurge|\bgrowth|\bdeals?\b|upgrade|\brally|cessez-le-feu|ceasefire|\bpaix\b|\bpeace|soutien|\bsupport|investissement|\binvestment|dividende|dividend|reprise|recovery|\bgains?\b|améliore|\bimprov|signé|\bsigned|victoire"
NEG = r"baisse|chute|crise|crisis|guerre|\bwar\b|attaque|attack|sanction|récession|recession|faillite|bankrupt|scandale|scandal|enquête|investigation|rappel de|\brecall|grève|\bstrike|effondr|collapse|plunge|\bfall|\bdrop|\bdefault|ouragan|hurricane|sécheresse|drought|canicule|inondation|\bflood|tension|menace|\bthreat|missile|downgrade|\bperte|\bloss|licenci|layoff|\bamende|\bfine\b|pénurie|shortage|échec|\bfail|démission|incendie|séisme|attentat"

_CAT_RE = {c: re.compile(p, re.I) for c, p in KEYWORDS.items()}
_TECH_RE = {c: re.compile(p, re.I) for c, p in TECHS.items()}
_POS, _NEG = re.compile(POS, re.I), re.compile(NEG, re.I)


def company_matchers(wl):
    out = {}
    for t, v in wl.items():
        names = v.get("match") or [v["name"]] + list(v.get("aliases", []))
        flags = 0 if v.get("case") else re.I  # sigles ambigus (UPS, Intel, AXA...) : casse exacte
        out[t] = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in names) + r")(?!\w)", flags)
    return out


def score_article(title, text, matchers):
    s = f"{title}. {text or ''}"
    cats = {}
    for c, rx in _CAT_RE.items():
        hits = len({m.lower() for m in rx.findall(s)})
        if hits:
            cats[c] = min(1.0, 0.5 * hits)
    p, n = len(_POS.findall(s)), len(_NEG.findall(s))
    return {
        "cats": cats,
        "polarity": (p - n) / (p + n + 1),
        "tickers": [t for t, rx in matchers.items() if rx.search(s)],
        "techs": [k for k, rx in _TECH_RE.items() if rx.search(s)],
    }


def article_id(source, title, date):
    return hashlib.sha1(f"{source}|{title}|{date}".encode()).hexdigest()[:16]


def rel_exposure(wl):
    """Exposition relative au marché suivi : ce qui compte pour prédire une surperformance."""
    secs = [v["sector"] for v in wl.values()]
    out = {}
    for c, e in EXPOSURE.items():
        m = sum(e.get(s, 0) for s in secs) / len(secs)
        out[c] = {s: e.get(s, 0) - m for s in SECTORS}
    return out
