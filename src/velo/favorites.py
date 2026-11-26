"""Les stations favorites (velo favorites, add, remove).

Les favoris sont rangés dans un petit fichier, favorites.json, dans le dossier
du réseau. Il contient juste une liste de numéros, par exemple ["43", "10"].
L'énoncé demande que ce ne soit PAS dans config.yaml : config.yaml, c'est
l'utilisateur qui l'écrit à la main ; favorites.json, c'est l'outil qui le gère.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from velo.errors import VeloError
from velo.models import StationInfo

log = logging.getLogger(__name__)

MAX_FAVORITES = 10  # imposé par l'énoncé, le même pour tous les groupes
FILE_NAME = "favorites.json"


def favorites_path(network_folder: Path) -> Path:
    """L'emplacement du fichier. Exemple : ~/.local/share/velo/vlille/favorites.json"""
    return network_folder / FILE_NAME


def load_favorites(network_folder: Path) -> list[str]:
    """Lit la liste des favoris.

    Pas de fichier ? Liste vide. Fichier abîmé ? Liste vide aussi, avec un
    avertissement dans le journal, plutôt que de faire planter la commande.
    """
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
    """Écrit la liste des favoris dans le fichier."""
    network_folder.mkdir(parents=True, exist_ok=True)
    favorites_path(network_folder).write_text(json.dumps(favorites, indent=2), encoding="utf-8")


def add_favorite(
    network_folder: Path, station_id: str, stations: dict[str, StationInfo]
) -> StationInfo:
    """Ajoute une station aux favoris, et renvoie sa fiche (pour afficher son nom).

    Trois refus possibles, chacun avec un message clair : numéro inconnu,
    station déjà en favori, liste déjà pleine (10).
    """
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
    """Retire une station des favoris. Erreur claire si elle n'y était pas."""
    favorites = load_favorites(network_folder)
    if station_id not in favorites:
        raise VeloError(f"La station {station_id} n'est pas dans vos favoris.")
    favorites.remove(station_id)
    save_favorites(network_folder, favorites)
    log.debug("Favori retiré : %s", station_id)
