"""Gestion des stations favorites.

Les favoris sont enregistrés dans <dossier du réseau>/favorites.json (un fichier
géré par l'outil, pas dans config.yaml) : une simple liste d'identifiants.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from velo.errors import VeloError
from velo.models import StationInfo

log = logging.getLogger(__name__)

MAX_FAVORITES = 10
FILE_NAME = "favorites.json"


def favorites_path(network_folder: Path) -> Path:
    """Emplacement du fichier des favoris."""
    return network_folder / FILE_NAME


def load_favorites(network_folder: Path) -> list[str]:
    """Lit la liste des favoris (liste vide si le fichier n'existe pas)."""
    path = favorites_path(network_folder)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("Fichier des favoris illisible (%s) : liste vide utilisée", path)
        return []
    if not isinstance(data, list):
        log.warning("Fichier des favoris invalide (%s) : liste vide utilisée", path)
        return []
    return [str(item) for item in data]


def save_favorites(network_folder: Path, favorites: list[str]) -> None:
    """Enregistre la liste des favoris."""
    network_folder.mkdir(parents=True, exist_ok=True)
    favorites_path(network_folder).write_text(json.dumps(favorites, indent=2), encoding="utf-8")


def add_favorite(
    network_folder: Path, station_id: str, stations: dict[str, StationInfo]
) -> StationInfo:
    """Ajoute une station aux favoris et la renvoie. Lève VeloError si c'est impossible."""
    if station_id not in stations:
        raise VeloError(
            f"Station {station_id} inconnue. Cherchez son identifiant avec : velo station search"
        )
    favorites = load_favorites(network_folder)
    if station_id in favorites:
        raise VeloError(f"La station {station_id} est déjà dans vos favoris.")
    if len(favorites) >= MAX_FAVORITES:
        raise VeloError(
            f"Vous avez déjà {MAX_FAVORITES} favoris (le maximum). "
            "Retirez-en un avec : velo favorites remove <id>"
        )
    favorites.append(station_id)
    save_favorites(network_folder, favorites)
    log.debug("Favori ajouté : %s", station_id)
    return stations[station_id]


def remove_favorite(network_folder: Path, station_id: str) -> None:
    """Retire une station des favoris. Lève VeloError si elle n'y est pas."""
    favorites = load_favorites(network_folder)
    if station_id not in favorites:
        raise VeloError(f"La station {station_id} n'est pas dans vos favoris.")
    favorites.remove(station_id)
    save_favorites(network_folder, favorites)
    log.debug("Favori retiré : %s", station_id)
