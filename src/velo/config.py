"""Lecture, validation et création du fichier config.yaml.

Ce module s'occupe de deux étages de la règle de priorité :
« valeur du fichier config.yaml, sinon valeur par défaut du code ».
Le troisième étage (l'option tapée dans la commande) est géré par la CLI.
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

# --- Valeurs par défaut (le « réglage d'usine ») -----------------------------

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
    """Renvoie l'emplacement par défaut de config.yaml selon le système.

    La variable d'environnement VELO_CONFIG permet de le changer (utile pour les tests).
    """
    if "VELO_CONFIG" in os.environ:
        return Path(os.environ["VELO_CONFIG"])
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "velo" / "config.yaml"


def default_data_folder() -> Path:
    """Renvoie le dossier de données par défaut selon le système."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "velo"


def slugify(name: str) -> str:
    """Transforme un nom de réseau en nom de dossier : "V'Lille" -> "vlille"."""
    sans_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sans_accents.lower()) or "reseau"


# --- L'objet configuration ---------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Tous les réglages de Vélo, déjà validés."""

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
        """Dossier du réseau : <dossier de données>/<nom du réseau>/."""
        return self.data_folder / slugify(self.network_name)

    @property
    def history_folder(self) -> Path:
        """Dossier des CSV collectés : <dossier du réseau>/history/."""
        return self.network_folder / "history"


# --- Lecture et validation ---------------------------------------------------


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    """Renvoie la section `name` du YAML (un dictionnaire), ou {} si elle est absente."""
    value = data.get(name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Configuration invalide : la section « {name} » doit contenir des réglages.")
    return value


def _int(section: dict[str, Any], key: str, default: int, minimum: int, label: str) -> int:
    """Lit un réglage entier, vérifie son type et sa valeur minimale."""
    value = section.get(key, default)
    # bool est un sous-type de int en Python (True == 1) : on le refuse explicitement.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"Réglage {label} invalide : « {value} » n'est pas un nombre entier.")
    if value < minimum:
        raise ConfigError(f"Réglage {label} invalide : {value} (minimum {minimum}).")
    return value


def _text(section: dict[str, Any], key: str, default: str, label: str) -> str:
    """Lit un réglage texte non vide."""
    value = section.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Réglage {label} invalide : un texte non vide est attendu.")
    return value.strip()


def parse_config(data: Any) -> Config:
    """Construit un Config à partir du contenu YAML déjà lu (un dictionnaire).

    Chaque réglage absent prend sa valeur par défaut ; chaque réglage invalide
    lève une ConfigError qui nomme le réglage concerné.
    """
    if data is None:
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
    """Lit et valide config.yaml. Lève ConfigError si le fichier est absent ou invalide."""
    if not path.exists():
        raise ConfigError(f"Configuration introuvable ({path}). Lancez d'abord : velo init")
    try:
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Configuration illisible ({path}) : le YAML est mal formé.") from exc
    except OSError as exc:
        raise ConfigError(f"Impossible de lire la configuration ({path}) : {exc}") from exc
    return parse_config(data)


# --- Création du fichier par défaut (velo init) ------------------------------

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
    """Écrit un config.yaml avec les valeurs par défaut (écrase le fichier s'il existe)."""
    folder = data_folder or default_data_folder()
    content = CONFIG_TEMPLATE.format(
        # yaml.safe_dump sur une valeur seule gère les guillemets (l'apostrophe de V'Lille...).
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _yaml_scalar(value: str) -> str:
    """Écrit une valeur texte au format YAML, avec guillemets si nécessaire."""
    return yaml.safe_dump(value, allow_unicode=True, default_style=None).strip().removesuffix("...").strip()
