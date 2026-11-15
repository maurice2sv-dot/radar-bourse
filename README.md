# Radar bourse

Outil de veille et de prévision directionnelle sur de grandes valeurs. Il croise cours et actualités (militaires, sécuritaires, politiques, financières, météo, économiques, scientifiques, religieuses, médiatiques), détecte tendances, valeurs et technologies à surveiller, et **mesure sa propre fiabilité** pour s'ajuster.

## Lancer

```
pip install -r requirements.txt
python run.py            # génère dashboard.html et data/report.json
```
Mode `demo` (défaut) : données synthétiques, pour tester la mécanique. Pour le réel, mettre `mode: live` dans `config.yaml` (cours via yfinance, actualités via flux RSS) et lancer **chaque jour** : l'apprentissage ne progresse qu'avec le temps, car les flux RSS ne donnent pas d'historique.

## Fonctionnement
1. **Collecte** : cours (yfinance, Stooq en secours), flux RSS, et GDELT pour l'historique mondial d'actualités (volume et ton quotidiens, 3 ans, par type d'événement et par entreprise).
2. **Cible relative** : le modèle prédit si une valeur fera mieux que la moyenne des valeurs suivies à 1, 5 et 20 jours. Il ne prédit pas la direction du marché.
3. **Signal d'actualité** : intensité x exposition du secteur relative au marché (a priori `EXPOSURE` dans `radar/events.py`) x poids appris.
4. **Journal** : chaque prédiction est enregistrée puis comparée au réel (`predictions`).
5. **Poids appris, avec test** : pour chaque source et chaque couple événement x secteur, on mesure si le secteur visé a surperformé comme annoncé. Une observation par jour, nombre d'observations indépendantes borné par durée / horizon, rendements centrés sur leur médiane. Un poids ne quitte 1,0 que si z >= 1,96 (sources) ou 2,58 (couples).
6. **Prudence** : probabilités rapprochées de 50 % tant que le taux de réussite réel n'est pas prouvé ; le backtest compare avec et sans actualités.

## Robustesse
- Chaque source est isolée : une panne est notée dans `data/status.json` et dans le brief, sans bloquer.
- Une base par mode (`radar_demo.db` et `radar.db`) : la démo ne contamine jamais le réel.
- GDELT : une requête toutes les 6 secondes, budget de temps borné, reprise incrémentale.
- En cas d'échec complet, le workflow écrit un brief d'échec.

## Limites connues
- Le chemin live a été testé avec un réseau simulé, pas contre les vrais services : le premier lancement réel peut demander un ajustement (format GDELT, symboles Stooq).
- Les poids appris utilisent tout l'historique : le backtest reste en poids neutres pour ne pas se flatter.
- Notation des articles RSS par mots-clés ; requêtes GDELT par mots-clés anglais.
- Pas de coûts de transaction ni d'exécution d'ordres. Ce n'est pas un conseil en investissement.

## Mode live automatique (GitHub Actions)
1. Créer un dépôt **privé** et y pousser ce dossier.
2. Le workflow `.github/workflows/radar.yml` s'exécute du lundi au vendredi vers 6h15 (heure de Paris en hiver), lance `python run.py --mode live` et enregistre `data/radar.db`, `data/brief.md`, `data/brief_weekly.md`, `dashboard.html`.
3. Le brief matinal lit `data/brief.md` (tous les jours) et `data/brief_weekly.md` (le lundi).
4. Les premiers jours, le modèle n'a pas d'historique d'actualités (les flux RSS ne remontent pas le passé) : l'apport des actualités reste nul jusqu'à accumulation de plusieurs semaines.
