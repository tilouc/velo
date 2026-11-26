# Vélo

**Vélo**, c'est un petit programme qu'on lance dans le terminal pour savoir où il y a des vélos **V'Lille** à Lille, en ce moment même. Il sait aussi noter l'état du réseau pendant des heures, puis répondre à des questions du genre : « quelle station est le plus souvent vide le matin ? ».

D'où viennent les données ? La Métropole de Lille (MEL) et Ilévia les publient gratuitement sur internet, dans un format standard qui s'appelle **GBFS**. Vélo va les lire, les range, et te les affiche proprement.

> Projet final du module « Langage Interprété », ISEN Lille, 2026-2027.

---

## Installer Vélo

### Étape 1 : installer uv

**uv**, c'est l'outil qui s'occupe de tout le côté technique pour toi : il installe la bonne version de Python et les bibliothèques dont Vélo a besoin.

- **Linux / macOS** :
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows** (dans PowerShell) :
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Ferme le terminal, rouvre-le, et tape `uv --version`. Si un numéro s'affiche, c'est bon.

### Étape 2 : récupérer Vélo et installer la commande `velo`

```bash
git clone https://github.com/tilouc/projet-final-langage-interprete.git
cd projet-final-langage-interprete
uv tool install .
```

La dernière ligne installe la commande `velo` sur ton ordinateur. Ensuite, tu peux la taper depuis n'importe quel dossier, comme `ls` ou `cd`.

Si le terminal répond « commande introuvable », tape `uv tool update-shell`, puis ferme et rouvre le terminal.

### Étape 3 : le premier lancement

```bash
velo init
```

```text
Configuration créée : /home/alice/.config/velo/config.yaml
Dossier de données créé : /home/alice/.local/share/velo/vlille
Connexion à V'Lille : OK (268 stations)
```

`velo init` fait trois choses : il crée le fichier de réglages, il crée le dossier où ranger les données, et il vérifie qu'il arrive à joindre V'Lille.

Où sont rangés ces fichiers ?

| | Linux / macOS | Windows |
|---|---|---|
| les réglages | `~/.config/velo/config.yaml` | `%APPDATA%\velo\config.yaml` |
| les données | `~/.local/share/velo/` | `%LOCALAPPDATA%\velo\` |

Pour utiliser un autre fichier de réglages, ajoute `--config` **avant** la commande : `velo --config ./test.yaml status`.

### Pour travailler sur le code

```bash
uv sync              # installe tout ce qu'il faut dans un dossier .venv
uv run velo status   # lance la version que tu es en train de modifier
uv run pytest        # lance les tests
uv run ruff check    # vérifie que le code est propre
```

---

## Utiliser Vélo

### Toutes les commandes

| Commande | À quoi elle sert |
|---|---|
| `velo init [--force]` | prépare tout au premier lancement |
| `velo refresh` | remet à jour la liste des stations (elle change rarement) |
| `velo status` | le résumé du réseau, en direct |
| `velo station list` | la liste de toutes les stations, avec leur numéro |
| `velo station search <texte>` | chercher une station par son nom |
| `velo station show <id>` | l'état d'une station, en direct |
| `velo favorites` | l'état de tes stations favorites |
| `velo favorites add <id>` / `remove <id>` | ajouter ou retirer un favori (10 au maximum) |
| `velo alerts [--low-bikes N] [--low-docks N]` | les stations fermées, (presque) vides ou (presque) pleines |
| `velo dashboard [--refresh S] [--low-bikes N] [--low-docks N]` | un écran qui se met à jour tout seul (Ctrl+C pour quitter) |
| `velo collect [--interval S] [--duration D \| --until "AAAA-MM-JJ HH:MM" \| --once]` | noter l'état du réseau à intervalle régulier |
| `velo history [--from AAAA-MM-JJ] [--to AAAA-MM-JJ]` | voir ce qui a été noté |
| `velo query --metric M [M ...] [filtres] [--by G] [--top N]` | analyser ce qui a été noté |

Perdu ? `velo <commande> --help` explique chaque commande en détail.

### Quelques exemples

```bash
velo status                                # combien de vélos, maintenant ?
velo station search gare                   # quel est le numéro de ma station ?
velo favorites add 43                      # garder la station 43 sous la main
velo alerts --low-bikes 5                  # « presque vide » = 5 vélos ou moins, juste pour cette fois
velo dashboard                             # un écran qui se met à jour tout seul
velo collect --duration 3h                 # noter le réseau pendant 3 h (aussi : 90m, 1h30, 45s)
velo collect --until "2026-11-20 10:00"    # noter jusqu'à une date précise
velo history                               # qu'est-ce que j'ai noté ?
velo query --metric empty_rate --days weekdays --hours 7-9 --by station --top 3
```

La dernière ligne se lit comme une phrase : « donne-moi le **taux de vide**, en **semaine**, de **7 h à 9 h**, **station par station**, et garde les **3 pires** ».

### Analyser l'historique avec `velo query`

Une requête se fait en trois temps : **trier** les relevés, les **grouper**, puis **calculer**.

**1. Trier : quels relevés garder ?**

| Option | Ce qu'elle garde |
|---|---|
| `--date AAAA-MM-JJ` | un seul jour |
| `--from`, `--to` | entre deux dates : `AAAA-MM-JJ` ou `"AAAA-MM-JJ HH:MM"` (une date seule veut dire toute la journée) |
| `--period N [N ...]` | une ou plusieurs périodes, avec le numéro affiché par `velo history` |
| `--days` | `weekdays` (lundi à vendredi), `weekend`, ou des jours : `lundi mardi`, `mon tue`… |
| `--hours 7-9` | de 7 h 00 à 9 h 00 (7 h et 8 h, donc ; 9 h n'est pas compris) |
| `--station ID` | une seule station |

On peut combiner les options : un relevé est gardé s'il passe **tous** les filtres. Sans option de date ni de période, on prend tout l'historique.

**2. Grouper (`--by`) :** `station`, `hour` (par heure), `weekday` (par jour de la semaine) ou `day` (par date).

**3. Calculer (`--metric`) :**

| Métrique | Ce qu'elle mesure | Exemple |
|---|---|---|
| `avg_bikes` | le nombre moyen de vélos | 0, 2 et 4 vélos → 2,0 |
| `avg_docks` | le nombre moyen de places libres | |
| `empty_rate` | le % de fois où la station était vide | vide 1 relevé sur 4 → 25 % |
| `full_rate` | le % de fois où la station était pleine | |

`--top N` garde seulement les N premiers résultats.

### Les réglages : `config.yaml`

`velo init` crée ce fichier. Tu peux le modifier à la main avec n'importe quel éditeur de texte.

```yaml
network:
  name: V'Lille
  gbfs_url: https://media.ilevia.fr/opendata/gbfs.json
data:
  folder: /home/alice/.local/share/velo
refresh:
  max_age_days: 7          # au-delà : avertissement
collect:
  interval_seconds: 120    # minimum 60
alerts:
  low_bikes: 2             # 2 vélos ou moins : presque vide
  low_docks: 2             # 2 places ou moins : presque pleine
dashboard:
  refresh_seconds: 60      # minimum 60
logging:
  level: INFO              # DEBUG, INFO, WARNING ou ERROR
```

Vélo relit ce fichier à chaque commande et le vérifie :
- un réglage **absent** prend sa valeur par défaut ;
- un réglage **faux** arrête la commande avec un message qui dit lequel. Exemple : `Réglage alerts.low_bikes invalide : « banane » n'est pas un nombre entier.`

**Qui gagne si deux valeurs se contredisent ?** Pense à un thermostat :
1. l'**option tapée** dans la commande (`--low-bikes 5`) gagne : c'est « juste pour cette fois » ;
2. sinon, la valeur de **config.yaml** : c'est ton réglage habituel ;
3. sinon, la **valeur par défaut** écrite dans le code : c'est le réglage d'usine.

### Où sont rangées les données ?

```text
<dossier de données>/
├── velo.log                      le journal de bord (tout ce qui s'est passé, avec l'heure)
└── vlille/
    ├── system_information.json   la carte d'identité du réseau
    ├── station_information.json  la liste des stations (nom, numéro, taille)
    ├── vehicle_types.json        les types de vélos
    ├── favorites.json            tes favoris : juste une liste de numéros
    └── history/                  ce que velo collect a noté, un fichier par jour
        ├── 2026-11-18.csv
        └── 2026-11-19.csv
```

Un fichier CSV, c'est un tableau écrit en texte : une ligne par station et par relevé, les colonnes séparées par des virgules.

```text
timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported
2026-11-18T08:14:00+01:00,42,3,17,true,true,true,2026-11-18T08:13:41+01:00
```

Cette ligne veut dire : « le 18 novembre à 8 h 14, la station 42 avait 3 vélos et 17 places libres, et elle marchait normalement ». Les dates sont écrites au format ISO 8601, avec le décalage horaire (`+01:00` en hiver à Lille), pour que n'importe qui puisse relire nos fichiers sans se tromper d'heure.

---

## Nos choix, et pourquoi

### Quand dit-on qu'une station est « vide », « pleine » ou « hors service » ?

| État | Notre règle | Pourquoi |
|---|---|---|
| **hors service** | il manque **au moins une** de ces trois choses : la station est installée (`is_installed`), on peut y prendre un vélo (`is_renting`), on peut y rendre un vélo (`is_returning`) | si tu ne peux pas prendre **et** rendre un vélo, tu ne peux pas compter sur la station |
| **vide** | 0 vélo | |
| **presque vide** | vélos ≤ `alerts.low_bikes` (2 par défaut) | |
| **pleine** | 0 place libre | |
| **presque pleine** | places libres ≤ `alerts.low_docks` (2 par défaut) | |

Une station hors service n'est **jamais** comptée aussi comme vide ou pleine : elle est déjà signalée, inutile de la compter deux fois. Et dans `velo status`, ses vélos ne comptent pas comme « disponibles » : personne ne peut les prendre.

Le taux de remplissage, c'est `vélos ÷ (vélos + places libres)`. Exemple : 30 vélos et 70 places libres → 30 %.

### Comment marche la recherche de stations ?

On veut que tu trouves ta station même en tapant n'importe comment :

- **les majuscules ne comptent pas** : `gare` trouve « Gare Lille Flandres » ;
- **les accents ne comptent pas** : `solferino` trouve « Solférino ». On enlève les accents des deux côtés avant de comparer ;
- **un bout de mot suffit** : `flan` trouve « Flandres » ;
- **avec plusieurs mots, chacun doit être là**, dans n'importe quel ordre : `flandres gare` trouve « Gare Lille Flandres ». Les espaces, tirets et apostrophes séparent les mots ;
- **les symboles sont pris tels quels** : la recherche utilise des expressions régulières (des « motifs » qu'on cherche dans un texte). Dans ce langage, `(`, `.` ou `*` ont un sens spécial. On passe donc ce que tu tapes dans `re.escape`, qui les transforme en simples caractères à chercher.

### Comment découpe-t-on l'historique en périodes ?

Une **période**, c'est une suite de relevés sans trou. Exemple : tu collectes de 7 h à 10 h lundi, puis de 7 h à 10 h mardi → deux périodes.

Pour repérer un trou, on regarde l'écart entre deux relevés qui se suivent :
- s'il est **plus petit que 3 fois l'intervalle de collecte**, c'est la même période ;
- sinon, une nouvelle période commence.

Avec l'intervalle par défaut de 120 s, la limite vaut 3 × 120 = 360 s, soit 6 minutes.

**Pourquoi 3 ?** Avec 1, un seul relevé raté (internet qui saute une seconde) couperait la période en deux pour rien. Avec 3, on tolère deux relevés ratés d'affilée. Au-delà, c'est que la collecte a vraiment été arrêtée.

Les numéros de période sont calculés sur **tout** l'historique : la période 2 s'appelle donc « 2 » partout, dans `velo history` comme dans `velo query --period 2`.

### Et quand il manque des données ?

- On calcule **seulement sur ce qui a vraiment été noté**. On n'invente jamais de valeur pour boucher un trou.
- Le nombre de relevés utilisés est **toujours affiché**, pour que tu saches sur quoi repose le résultat.
- Un **avertissement** s'affiche si ta sélection contient des trous : elle s'étale sur plusieurs périodes, ou tu as demandé une journée entière alors que tu n'as collecté que 3 heures.
- S'il n'y a **aucune** donnée, la commande le dit et affiche les périodes disponibles, pour que tu saches quoi demander.

### Que se passe-t-il quand quelque chose rate ?

- Chaque donnée reçue de V'Lille est vérifiée. Si une station est mal décrite, on la saute et on le note dans le journal, sans faire planter tout l'outil.
- Si une ligne d'un fichier CSV est abîmée, on la saute aussi et on le note.
- Si un problème prévu arrive (pas d'internet, numéro inconnu, réglage faux), tu vois un message clair en une ligne, et la commande se termine avec le code 1. Jamais le gros pavé technique de Python.
- Pendant `collect`, une coupure internet n'arrête pas la collecte : on note l'erreur et on réessaie au relevé suivant. Un relevé identique au précédent n'est pas réenregistré. À la fin, même après Ctrl+C, un bilan s'affiche.
- Pendant `dashboard`, une coupure internet garde les dernières données à l'écran, avec un avertissement.

---

## Comment le code est organisé

L'idée centrale : **chaque fichier a un seul métier**, comme dans la cuisine d'un restaurant. Et les données vont toujours dans le même sens.

```text
cli.py → commands.py → config.py      les réglages
                     → gbfs.py        aller chercher les données sur internet
                     → storage.py     lire et écrire l'historique
                     → states.py, search.py, favorites.py, history.py, query.py   les calculs
                     → display.py     l'affichage
```

| Fichier | Son métier |
|---|---|
| `cli.py` | comprend ce que tu as tapé (avec argparse), charge les réglages, passe la main à la bonne commande, et transforme les erreurs en messages clairs |
| `commands.py` | une fonction par commande : le chef d'orchestre qui appelle les autres fichiers dans l'ordre |
| `config.py` | lit, vérifie et crée `config.yaml` |
| `gbfs.py` | **le seul fichier qui parle à V'Lille** : il lit le sommaire `gbfs.json`, télécharge, vérifie, et recopie tout dans des fiches simples (versions 2.x et 3.0 du format) |
| `models.py` | les fiches simples que tout le monde se passe : `StationInfo`, `StationStatus`, `Snapshot` |
| `states.py` | les règles « vide / pleine / hors service », le résumé du réseau, les alertes, les lignes des favoris |
| `search.py` | la recherche de stations par leur nom |
| `favorites.py` | le fichier des favoris |
| `storage.py` | l'historique en CSV |
| `history.py` | le découpage en périodes |
| `query.py` | trier, grouper, calculer |
| `display.py` | tout l'affichage dans le terminal (avec Rich), sans aucun calcul |
| `logs.py` | le journal de bord, à l'écran et dans `velo.log` |
| `errors.py` | les erreurs prévues (`VeloError`) |

Trois règles de l'énoncé, et comment on les respecte :
- **« Aucune URL écrite en dur »** : seule l'adresse du sommaire `gbfs.json` est dans `config.yaml`. Les adresses des autres fichiers sont lues dans ce sommaire.
- **« La lecture du GBFS est isolée dans un seul module »** : c'est `gbfs.py`. Tous les autres fichiers manipulent les fiches de `models.py`, jamais le JSON.
- **« L'affichage est séparé des calculs »** : `states.py` calcule sans rien afficher, `display.py` affiche sans rien calculer. Résultat : le tableau de bord réutilise exactement les mêmes fonctions que `status`, `favorites` et `alerts`.

---

## Les tests

```bash
uv run pytest
```

Les tests utilisent de petits fichiers préparés à la main, dans `tests/data/`. Ils ne vont jamais sur internet : la fonction qui télécharge est remplacée par une fausse version qui lit ces fichiers. Comme ça, les tests marchent partout, même sans connexion, et donnent toujours le même résultat.

## Fonctionnalités avancées

Aucune pour l'instant : le socle obligatoire est complet.
