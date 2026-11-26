"""Les réglages de l'utilisateur (le fichier config.yaml).

Pense à un thermostat :
- la valeur d'usine, c'est la valeur par défaut écrite ici, dans le code ;
- la valeur que tu as programmée, c'est celle de config.yaml ;
- la valeur « juste pour ce soir », c'est une option tapée dans la commande.

Ce fichier s'occupe des deux premiers étages : « config.yaml, sinon défaut ».
Le troisième (l'option) est géré plus haut, dans commands.py.

Il fait trois choses :
1. lire config.yaml ;
2. compléter : un réglage absent prend sa valeur par défaut ;
3. vérifier : un réglage faux (« banane » au lieu d'un nombre) arrête tout
   avec un message qui dit QUEL réglage est faux.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from velo.errors import ConfigError

# --- Les valeurs par défaut (le « réglage d'usine ») ---------------------------

DEFAULT_NETWORK_NAME = "V'Lille"
DEFAULT_GBFS_URL = "https://media.ilevia.fr/opendata/gbfs.json"
DEFAULT_MAX_AGE_DAYS = 7
DEFAULT_INTERVAL_SECONDS = 120
DEFAULT_LOW_BIKES = 2
DEFAULT_LOW_DOCKS = 2
DEFAULT_DASHBOARD_REFRESH = 60
DEFAULT_LOG_LEVEL = "INFO"

MIN_INTERVAL_SECONDS = 60
MIN_DASHBOARD_REFRESH = 60
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def default_config_path() -> Path:
    """Où ranger config.yaml si l'utilisateur ne dit rien.

    Linux : ~/.config/velo/config.yaml
    Windows : C:\\Users\\<toi>\\AppData\\Roaming\\velo\\config.yaml
    Si la variable d'environnement VELO_CONFIG existe, on prend son chemin à la place.
    """
    if "VELO_CONFIG" in os.environ:
        return Path(os.environ["VELO_CONFIG"])
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "velo" / "config.yaml"


def default_data_folder() -> Path:
    """Où ranger les données si l'utilisateur ne dit rien.

    Linux : ~/.local/share/velo
    Windows : C:\\Users\\<toi>\\AppData\\Local\\velo
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "velo"


def slugify(name: str) -> str:
    """Transforme un nom de réseau en nom de dossier propre.

    Exemple : "V'Lille" devient "vlille" (minuscules, sans accent, sans symbole).
    """
    sans_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sans_accents.lower()) or "reseau"


# --- L'objet Config : tous les réglages, rangés et déjà vérifiés -----------------


@dataclass(frozen=True)
class Config:
    """Tous les réglages, rangés dans une seule boîte.

    Au lieu d'écrire donnees["alerts"]["low_bikes"] partout, le reste du code
    écrit config.low_bikes. frozen=True : une fois créée, la boîte ne change plus.
    """

    network_name: str
    gbfs_url: str
    data_folder: Path
    max_age_days: int
    interval_seconds: int
    low_bikes: int
    low_docks: int
    dashboard_refresh: int
    log_level: str

    @property
    def network_folder(self) -> Path:
        """Le dossier du réseau. Exemple : ~/.local/share/velo/vlille"""
        return self.data_folder / slugify(self.network_name)

    @property
    def history_folder(self) -> Path:
        """Le dossier des CSV collectés. Exemple : ~/.local/share/velo/vlille/history"""
        return self.network_folder / "history"


# --- Petits outils de lecture -------------------------------------------------------


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Renvoie une section du YAML (par exemple « alerts »), ou {} si elle n'existe pas."""
    value = data.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(
            f"Configuration invalide : la section « {name} » doit contenir des réglages."
        )
    return value


def _int(section: dict[str, Any], key: str, default: int, minimum: int, label: str) -> int:
    """Lit un réglage qui doit être un nombre entier, au moins égal à `minimum`.

    Exemples avec low_bikes : absent -> le défaut ; 5 -> 5 ; "banane" -> erreur ; -1 -> erreur.
    """
    value = section.get(key, default)
    # Piège Python : True est considéré comme un entier (True == 1). On le refuse.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Réglage {label} invalide : « {value} » n'est pas un nombre entier.")
    if value < minimum:
        raise ConfigError(f"Réglage {label} invalide : {value} (minimum {minimum}).")
    return value


def _text(section: dict[str, Any], key: str, default: str, label: str) -> str:
    """Lit un réglage qui doit être un texte non vide."""
    value = section.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Réglage {label} invalide : un texte non vide est attendu.")
    return value.strip()


# --- Lecture complète ------------------------------------------------------------


def parse_config(data: Any) -> Config:
    """Transforme le contenu du YAML (un dictionnaire) en objet Config.

    Chaque réglage passe par _int ou _text : absent -> défaut, faux -> ConfigError.
    """
    if data is None:  # fichier vide : tout prend sa valeur par défaut
        data = {}
    if not isinstance(data, dict):
        raise ConfigError("Configuration invalide : le fichier doit contenir des sections.")

    network = _section(data, "network")
    data_section = _section(data, "data")
    refresh = _section(data, "refresh")
    collect = _section(data, "collect")
    alerts = _section(data, "alerts")
    dashboard = _section(data, "dashboard")
    logging_section = _section(data, "logging")

    gbfs_url = _text(network, "gbfs_url", DEFAULT_GBFS_URL, "network.gbfs_url")
    if not gbfs_url.startswith(("http://", "https://")):
        raise ConfigError("Réglage network.gbfs_url invalide : une adresse http(s) est attendue.")

    folder = _text(data_section, "folder", str(default_data_folder()), "data.folder")

    level = _text(logging_section, "level", DEFAULT_LOG_LEVEL, "logging.level").upper()
    if level not in LOG_LEVELS:
        raise ConfigError(
            f"Réglage logging.level invalide : « {level} » (choix : {', '.join(LOG_LEVELS)})."
        )

    return Config(
        network_name=_text(network, "name", DEFAULT_NETWORK_NAME, "network.name"),
        gbfs_url=gbfs_url,
        data_folder=Path(folder).expanduser(),
        max_age_days=_int(refresh, "max_age_days", DEFAULT_MAX_AGE_DAYS, 1, "refresh.max_age_days"),
        interval_seconds=_int(
            collect, "interval_seconds", DEFAULT_INTERVAL_SECONDS, MIN_INTERVAL_SECONDS,
            "collect.interval_seconds",
        ),
        low_bikes=_int(alerts, "low_bikes", DEFAULT_LOW_BIKES, 0, "alerts.low_bikes"),
        low_docks=_int(alerts, "low_docks", DEFAULT_LOW_DOCKS, 0, "alerts.low_docks"),
        dashboard_refresh=_int(
            dashboard, "refresh_seconds", DEFAULT_DASHBOARD_REFRESH, MIN_DASHBOARD_REFRESH,
            "dashboard.refresh_seconds",
        ),
        log_level=level,
    )


def load_config(path: Path) -> Config:
    """Ouvre config.yaml, le lit, le vérifie, et renvoie un Config.

    Fichier absent -> « lancez d'abord velo init ». YAML mal écrit -> message clair.
    """
    if not path.exists():
        raise ConfigError(f"Configuration introuvable ({path}). Lancez d'abord : velo init")
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)  # le texte YAML devient un dictionnaire Python
    except yaml.YAMLError as exc:
        raise ConfigError(f"Configuration illisible ({path}) : le YAML est mal formé.") from exc
    except OSError as exc:
        raise ConfigError(f"Impossible de lire la configuration ({path}) : {exc}") from exc
    return parse_config(data)


# --- Création du fichier (velo init) ----------------------------------------------

CONFIG_TEMPLATE = """\
network:
  name: {name}
  gbfs_url: {url}

data:
  folder: {folder}

refresh:
  max_age_days: {max_age}          # au-delà : avertissement

collect:
  interval_seconds: {interval}       # minimum 60

alerts:
  low_bikes: {low_bikes}                 # {low_bikes} vélos ou moins : presque vide
  low_docks: {low_docks}                 # {low_docks} places ou moins : presque pleine

dashboard:
  refresh_seconds: {refresh}         # minimum 60

logging:
  level: {level}
"""


def write_default_config(path: Path, data_folder: Path | None = None) -> None:
    """Écrit un config.yaml rempli avec les valeurs par défaut (écrase l'ancien s'il existe)."""
    folder = data_folder or default_data_folder()
    content = CONFIG_TEMPLATE.format(
        name=_yaml_scalar(DEFAULT_NETWORK_NAME),
        url=DEFAULT_GBFS_URL,
        folder=_yaml_scalar(str(folder)),
        max_age=DEFAULT_MAX_AGE_DAYS,
        interval=DEFAULT_INTERVAL_SECONDS,
        low_bikes=DEFAULT_LOW_BIKES,
        low_docks=DEFAULT_LOW_DOCKS,
        refresh=DEFAULT_DASHBOARD_REFRESH,
        level=DEFAULT_LOG_LEVEL,
    )
    path.parent.mkdir(parents=True, exist_ok=True)  # crée ~/.config/velo/ s'il n'existe pas
    path.write_text(content, encoding="utf-8")


def _yaml_scalar(value: str) -> str:
    """Écrit un texte au format YAML, en ajoutant des guillemets si besoin.

    Exemple : l'apostrophe de V'Lille oblige à écrire "V'Lille" entre guillemets.
    """
    dumped = yaml.safe_dump(value, allow_unicode=True)
    return dumped.strip().removesuffix("...").strip()
