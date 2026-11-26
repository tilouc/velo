# Vélo

Outil en ligne de commande pour consulter le réseau de vélos en libre-service **V'Lille** en temps réel, enregistrer son évolution et analyser cet historique. Les données viennent du flux ouvert GBFS publié par la MEL et Ilévia.

Projet final du module « Langage Interprété », ISEN Lille, 2026-2027.

## Installation

### 1. Installer uv

uv gère Python, l'environnement virtuel et les dépendances.

- **Linux / macOS** :
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Windows** (PowerShell) :
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

Fermez puis rouvrez le terminal, et vérifiez avec `uv --version`.

### 2. Récupérer le projet et installer la commande `velo`

```bash
git clone https://github.com/tilouc/projet-final-langage-interprete.git
cd projet-final-langage-interprete
uv tool install .
```

`uv tool install .` installe la commande `velo` pour tout le système : elle s'utilise ensuite depuis n'importe quel dossier. Si le terminal ne la trouve pas, lancez `uv tool update-shell` puis rouvrez-le.

### 3. Premier lancement

```bash
velo init
```

```text
Configuration créée : /home/alice/.config/velo/config.yaml
Dossier de données créé : /home/alice/.local/share/velo/vlille
Connexion à V'Lille : OK (268 stations)
```

Emplacements par défaut :

| | Linux / macOS | Windows |
|---|---|---|
| configuration | `~/.config/velo/config.yaml` | `%APPDATA%\velo\config.yaml` |
| données | `~/.local/share/velo/` | `%LOCALAPPDATA%\velo\` |

L'option globale `--config CHEMIN` (avant la commande) permet d'utiliser un autre fichier : `velo --config ./test.yaml status`.

### Pour développer

```bash
uv sync              # crée .venv avec toutes les dépendances (dont pytest et ruff)
uv run velo status   # lance la version en cours de développement
uv run pytest        # lance les tests
uv run ruff check    # vérifie le code
```

## Utilisation

| Commande | Rôle |
|---|---|
| `velo init [--force]` | crée la configuration et le dossier de données, teste la connexion |
| `velo refresh` | retélécharge les fichiers qui changent rarement (stations, réseau, types de vélos) |
| `velo status` | résumé du réseau en temps réel |
| `velo station list` | liste toutes les stations avec leur identifiant |
| `velo station search <texte>` | cherche une station par son nom |
| `velo station show <id>` | état en temps réel d'une station |
| `velo favorites` | état des stations favorites |
| `velo favorites add <id>` / `remove <id>` | ajoute ou retire un favori (10 au maximum) |
| `velo alerts [--low-bikes N] [--low-docks N]` | stations hors service, vides ou presque, pleines ou presque |
| `velo dashboard [--refresh S] [--low-bikes N] [--low-docks N]` | tableau de bord mis à jour en continu (Ctrl+C pour quitter) |
| `velo collect [--interval S] [--duration D \| --until "AAAA-MM-JJ HH:MM" \| --once]` | enregistre l'état du réseau à intervalle régulier |
| `velo history [--from AAAA-MM-JJ] [--to AAAA-MM-JJ]` | périodes et relevés enregistrés |
| `velo query --metric M [M ...] [sélection] [--by G] [--top N]` | analyse de l'historique |

`velo <commande> --help` détaille chaque commande.

### Exemples

```bash
velo status
velo station search gare
velo favorites add 43
velo alerts --low-bikes 5
velo dashboard
velo collect --duration 3h            # 3h, 90m, 1h30, 45s
velo collect --until "2026-11-20 10:00"
velo history
velo query --metric empty_rate --days weekdays --hours 7-9 --by station --top 3
velo query --metric avg_bikes avg_docks --station 43 --by hour
velo query --metric full_rate --period 1 2 --by weekday
```

### Sélection des données dans `velo query`

| Option | Rôle |
|---|---|
| `--date AAAA-MM-JJ` | un seul jour |
| `--from`, `--to` | intervalle : `AAAA-MM-JJ` ou `"AAAA-MM-JJ HH:MM"` (une date seule va de 00:00 à 23:59) |
| `--period N [N ...]` | numéros de période affichés par `velo history` |
| `--days` | `weekdays`, `weekend`, ou des jours : `lundi mardi`, `mon tue`… |
| `--hours 7-9` | de 7:00 inclus à 9:00 exclu |
| `--station ID` | une seule station |

Les options se combinent (toutes doivent être vraies). Sans option de date ni de période, la requête porte sur tout l'historique. Métriques : `avg_bikes`, `avg_docks`, `empty_rate`, `full_rate`. Regroupements (`--by`) : `station`, `hour`, `weekday`, `day`.

### Configuration

Le fichier `config.yaml` est créé par `velo init`, modifié à la main, et validé au début de chaque commande. Un réglage absent prend sa valeur par défaut ; un réglage invalide arrête la commande avec un message qui le nomme (par exemple `Réglage alerts.low_bikes invalide : « banane » n'est pas un nombre entier.`).

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

**Ordre de priorité**, toujours le même : 1) l'option de la commande (`--interval`, `--low-bikes`…), 2) sinon la valeur de `config.yaml`, 3) sinon la valeur par défaut du code.

### Données enregistrées

```text
<dossier de données>/
├── velo.log                      journal (tous les niveaux, avec la date)
└── vlille/
    ├── system_information.json
    ├── station_information.json
    ├── vehicle_types.json
    ├── favorites.json            liste des identifiants favoris
    └── history/
        ├── 2026-11-18.csv
        └── 2026-11-19.csv
```

Chaque CSV contient une ligne par station et par relevé :

```text
timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported
2026-11-18T08:14:00+01:00,42,3,17,true,true,true,2026-11-18T08:13:41+01:00
```

`timestamp` est la date du relevé (`last_updated` du flux) ; les dates sont en ISO 8601, heure locale avec le décalage horaire.

## Choix réalisés

### États d'une station

| État | Définition | Pourquoi |
|---|---|---|
| **hors service** | `is_installed`, `is_renting` **ou** `is_returning` vaut `false` | une station où l'on ne peut pas prendre **et** rendre un vélo ne rend pas le service normal ; l'usager ne peut pas compter dessus |
| **vide** | 0 vélo | |
| **presque vide** | vélos ≤ `alerts.low_bikes` (2 par défaut) | |
| **pleine** | 0 place libre | |
| **presque pleine** | places libres ≤ `alerts.low_docks` (2 par défaut) | |

Une station hors service n'est jamais comptée comme vide ou pleine (ni dans `alerts`, ni dans `status`, ni dans `query`). Dans `status`, les vélos et places des stations hors service ne sont pas comptés : ils sont inutilisables. Le taux de remplissage vaut `vélos / (vélos + places libres)`.

### Recherche de stations (expressions régulières)

- **casse ignorée** : `gare` trouve « Gare Lille Flandres » ;
- **accents ignorés** : `solferino` trouve « Solférino » (les accents sont retirés avec `unicodedata` des deux côtés avant la comparaison) ;
- **recherche partielle** : `flan` trouve « Flandres » ;
- **plusieurs mots** : chacun doit apparaître, dans n'importe quel ordre (`flandres gare`) ; les espaces, tirets et apostrophes séparent les mots ;
- **caractères spéciaux** : le texte tapé est passé dans `re.escape`, donc `(` ou `.` sont cherchés tels quels au lieu d'être interprétés comme des symboles d'expression régulière.

### Détection des périodes

Deux relevés consécutifs appartiennent à la même période si leur écart est **strictement inférieur à 3 fois l'intervalle de collecte** (360 s avec l'intervalle par défaut de 120 s). Un facteur 1 couperait une période au moindre retard du réseau ; un facteur 3 tolère jusqu'à deux relevés manqués (erreur réseau ponctuelle, ou relevé identique au précédent non enregistré) sans inventer de continuité quand la collecte a vraiment été arrêtée. Les périodes sont calculées sur tout l'historique, donc leurs numéros sont les mêmes dans `velo history` et dans `velo query --period`.

### Données manquantes dans `velo query`

Les calculs portent uniquement sur les relevés existants : rien n'est comblé ni estimé. Le nombre de relevés utilisés est toujours affiché. Un avertissement apparaît si la sélection s'étend sur plusieurs périodes, ou si la fenêtre de dates demandée commence avant ou finit après les relevés disponibles. S'il n'y a aucune donnée, la commande renvoie une erreur et affiche les périodes disponibles.

### Robustesse

- Les données reçues de l'API sont validées dans `gbfs.py` : une station mal décrite est ignorée et journalisée, sans arrêter l'outil.
- Une ligne invalide dans un CSV est ignorée et journalisée.
- Une erreur prévue (réseau, identifiant, configuration) affiche un message clair et la commande se termine avec le code 1, jamais avec une trace d'exception.
- Pendant `collect`, une erreur réseau est journalisée et la collecte réessaie au relevé suivant ; un relevé dont `last_updated` est identique au précédent n'est pas réenregistré ; un bilan s'affiche à la fin, même après Ctrl+C.
- Pendant `dashboard`, une erreur réseau conserve les dernières données affichées et le signale.

## Organisation du code

Chaque module a un seul rôle. Les données circulent toujours dans le même sens :

```text
cli.py → commands.py → config.py      (les réglages)
                     → gbfs.py        (télécharger et lire le GBFS → objets de models.py)
                     → storage.py     (lire et écrire les CSV)
                     → states.py, search.py, favorites.py, history.py, query.py   (les calculs)
                     → display.py     (l'affichage)
```

| Module | Rôle |
|---|---|
| `cli.py` | décrit les commandes avec argparse, charge la configuration, aiguille, transforme les erreurs en messages |
| `commands.py` | une fonction par commande, qui relie les autres modules |
| `config.py` | lit, valide et crée `config.yaml` |
| `gbfs.py` | **seul module qui connaît le format GBFS** : découverte des fichiers à partir de `gbfs.json`, téléchargement, validation (GBFS 2.x et 3.0) |
| `models.py` | les objets de l'outil : `StationInfo`, `StationStatus`, `Snapshot` |
| `states.py` | définitions des états, résumé du réseau, alertes, lignes des favoris |
| `search.py` | recherche de stations par expressions régulières |
| `favorites.py` | fichier des favoris |
| `storage.py` | écriture et lecture de l'historique CSV |
| `history.py` | découpage en périodes |
| `query.py` | sélection, métriques et regroupements |
| `display.py` | tout l'affichage (Rich) : aucun calcul |
| `logs.py` | journalisation vers la console et vers `velo.log` |
| `errors.py` | `VeloError` et ses variantes |

Aucune URL n'est écrite en dur dans le code, à part la valeur par défaut de `gbfs.json` utilisée pour créer la configuration : les autres adresses sont découvertes à partir de lui. Le tableau de bord réutilise exactement les fonctions de `status`, `favorites` et `alerts`.

## Tests

```bash
uv run pytest
```

Les tests utilisent de petits fichiers préparés à la main dans `tests/data/` ; les appels à l'API sont simulés (aucune connexion internet nécessaire).

## Fonctionnalités avancées

Aucune pour l'instant : le socle obligatoire est complet.
