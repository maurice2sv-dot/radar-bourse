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

## Évaluation (à la manière des professionnels)
- Cible : faire mieux que la moyenne de son secteur à 5 jours ; 10 ans de cours.
- Mesures : IC (corrélation de rang quotidienne entre classement prédit et réel), écart des 20 % les mieux classées contre la moyenne, avant et après frais (`evaluation.cout_bps`), rotation, ratio d'information.
- Les groupes de variables (actualités, calendrier, marchés, fondamentaux) ne sont gardés que s'ils améliorent l'IC sur la période de développement. Sélection refaite chaque semaine.
- Période de test réservée (`evaluation.test_reserve_debut`) : ne sert à aucun choix. Ne pas déplacer cette date.
- Fondamentaux : comptes officiels SEC (EDGAR) des valeurs américaines, utilisés à partir du lendemain de leur dépôt, première publication seulement.
- Biais connu : univers des grandes valeurs d'aujourd'hui (biais du survivant), qui flatte le passé.
- Régime de marché (`radar/regime.py`) : calme, tension, stress ou krach selon le VIX et la baisse du S&P 500 sur 5 séances, affiché dans l'alerte marchés avec une consigne de lecture.
- Fiabilité selon le climat : chaque semaine, IC et écart net des prévisions hors échantillon classés par régime VIX et sur les épisodes de stress (fin 2018, Covid 2020, rebond 2020, baisse 2022). Analyse descriptive, elle ne sert à aucun réglage.
- Frein anti-krach du momentum (Daniel et Moskowitz, 2016) : actif si le S&P 500 a baissé sur 24 mois, ou si le VIX dépasse 30 avec un S&P 500 à plus de 10 % sous son plus haut d'un an. Il ne modifie pas le radar : la règle fictive « radar avec frein » le suit à part (sélection répartie entre les cinq tranches de tendance), et son effet passé est mesuré chaque semaine.
- Bourses asiatiques (Nikkei 225, Hang Seng, Shanghai) : contexte et alertes seulement (±3 % sur une séance, -10 % sur 20 séances), hors modèle tant qu'un test n'a pas montré qu'elles améliorent la prévision.

## Robustesse
- La base `radar.db` n'est plus dans l'historique Git : elle vit dans la release GitHub « base » (copie du soir, plus une sauvegarde chaque vendredi). Le passage s'arrête s'il ne peut pas la récupérer, pour ne jamais repartir d'un journal vide.
- Chaque source est isolée : une panne est notée dans `data/status.json` et dans le brief, sans bloquer.
- Une base par mode (`radar_demo.db` et `radar.db`) : la démo ne contamine jamais le réel.
- GDELT : fichiers d'export d'événements (`radar/gdelt_events.py`), téléchargés directement chaque soir, sans limite de débit : part des mentions et ton par catégorie (militaire, sécuritaire, politique, protestations, religieux). Fichier quotidien 1.0, ou à défaut les 96 fichiers de 15 minutes de GDELT 2.0. Historique reconstitué à rebours dans un budget de 15 minutes par soir. L'ancienne collecte par l'interface de recherche est arrêtée ; ses 4 séries sont conservées.
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

## Portefeuille fictif

`radar/portefeuille.py` applique chaque jour, sans argent réel, deux règles fixées à l'avance et comparées avec les mêmes frais : « radar » (les 20 % de valeurs les mieux classées par le modèle) et « momentum » (les 20 % qui ont le plus monté sur 12 mois hors dernier mois). Revue toutes les 5 séances ; une valeur détenue reste tant qu'elle figure dans les 50 % premières (règle de maintien, qui réduit les frais ; 40 % jusqu'au 23/11/2026, compteur remis à zéro à ce changement) ; frais de 10 pb par sens. Références : moyenne de l'univers, S&P 500 (SPY) et Stoxx Europe 600 (EXSA.DE). L'état est dans `data/portefeuille.json` (à supprimer pour remettre le compteur à zéro si une règle change).

## Univers et biais du survivant

`radar/univers.py` élargit l'univers à environ 550 valeurs : composition du S&P 500 lue chaque semaine sur Wikipedia (copie dans `data/univers.json`), plus les valeurs de `config.yaml`. Une valeur ne compte qu'aux dates où elle appartenait à l'indice ; les valeurs sorties depuis 2016 et encore cotées sont gardées sur leur période d'appartenance. Changements de symbole d'une même société (FB devenu META, UTX devenu RTX, etc., liste `RENOMMAGES` dans `radar/univers.py`) : l'historique de l'ancien symbole est rattaché au nouveau, seulement si le fichier historique confirme la date. Biais résiduels : sociétés radiées sans cours disponibles chez Yahoo (rachats, faillites), valeurs européennes considérées comme membres sur toute la période. La part des membres historiques couverts par des cours est mesurée chaque passage (`couverture_indice` dans `data/status.json`).

## Suivi européen

Indices CAC 40, DAX, Euro Stoxx 50, FTSE 100 et SMI (contexte seulement, hors modèle) et valeurs européennes (`radar/europe.py`), affichés dans le tableau de bord et le brief. Le 26/11/2026, 19 grandes valeurs ont rejoint l'univers (les 15 de l'Euro Stoxx 50 qui manquaient, Roche, UBS, BP, GSK) : le portefeuille fictif et la période fraîche repartent de cette date. Ces valeurs, choisies aujourd'hui, sont considérées comme membres sur tout le passé (biais du survivant).

## Mesure honnête : la période fraîche

Le test réservé (depuis le 17/11/2025) a été consulté chaque jour ; il reste affiché pour mémoire et n'est plus recalculé qu'une fois par semaine. La mesure de référence est la période fraîche (`evaluation.periode_fraiche_debut`, 26/11/2026) : prévisions faites en direct après le dernier réglage. Ne pas régler le modèle en regardant ces résultats. Le brief et le tableau de bord indiquent le nombre de dates acquises sur 20 et les échéances estimées.

Coefficient de confiance (rapprochement des probabilités vers 50 %) : fixé à 0,30 tant que moins de 20 périodes indépendantes en direct sont résolues (une date compte pour une observation, fenêtres de 5 jours ouvrés sans chevauchement). Il ne change pas le classement. Les indices de référence du portefeuille fictif sont recalculés à chaque passage depuis la date de départ.

## Tests et contrôles

`python -m pytest -q tests` (lancé avant chaque passage) : absence de regard vers le futur, calcul de l'IC et des frais, règle de maintien, portefeuille, univers, brief. Contrôles de données à chaque passage : variations de plus de 40 % en une séance, contrôle croisé de 15 clôtures avec Stooq (clé facultative dans le secret `STOOQ_APIKEY`) ou, à défaut, nasdaq.com pour les valeurs américaines ; si aucune source ne répond, l'absence de contrôle figure dans les anomalies du brief ; valeurs non mises à jour.

## Charge GitHub Actions

Dépôt public : minutes illimitées sur les machines standard (4 processeurs, 16 Go). Essai hors ligne sur 690 valeurs avec resélection complète des variables (cas le plus lourd) : 4 min 30 de calcul sur 2 processeurs, 4,3 Go de mémoire. Collectes : les valeurs déjà en base ne téléchargent que 3 mois de cours ; historique complet uniquement pour les nouvelles valeurs (300 par passage) ; résultats 120 valeurs et comptes SEC 80 valeurs par passage. Durée attendue : 25 à 35 minutes pour le premier passage élargi, 10 à 20 minutes ensuite, pour une limite fixée à 75 minutes.
