"""Suivi des valeurs européennes : liste classée et évolution récente. Affichage seulement, aucun effet sur le modèle."""
import numpy as np

# suffixes Yahoo des places européennes suivies
PLACES = {"PA", "DE", "AS", "BR", "MC", "MI", "HE", "ST", "CO", "L", "SW"}
COTEES_AUX_ETATS_UNIS = {"ASML"}  # sociétés européennes suivies par leur cotation américaine


def est_europeenne(t):
    return t in COTEES_AUX_ETATS_UNIS or ("." in t and t.rsplit(".", 1)[1] in PLACES)


def resume(close, all_p5):
    """Valeurs européennes classées, avec leur rang d'ensemble et leur variation sur 5 et 20 séances."""
    out = []
    for r, a in enumerate(sorted(all_p5, key=lambda a: -a["p5"]), 1):
        t = a["ticker"]
        if not est_europeenne(t) or t not in close:
            continue
        v = close[t].dropna()

        def var(n):
            x = float(v.iloc[-1] / v.iloc[-1 - n] - 1) if len(v) > n else np.nan
            return None if x != x else round(x, 4)
        out.append({"ticker": t, "name": a["name"], "rang": r, "p5": a["p5"], "ret5": var(5), "ret20": var(20)})
    return out
