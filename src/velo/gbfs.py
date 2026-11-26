"""Le SEUL module qui connaît le format GBFS.

Il télécharge les fichiers JSON du réseau, vérifie qu'ils sont utilisables et
les transforme en objets de models.py. Si un jour le format change, c'est le
seul fichier à modifier.

Seule l'URL de gbfs.json vient de la configuration : les adresses des autres
fichiers sont découvertes à partir de lui.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from velo.errors import NetworkError, VeloError
from velo.models import NetworkInfo, Snapshot, StationInfo, StationStatus

log = logging.getLogger(__name__)

# Les trois fichiers « qui changent rarement », enregistrés dans le dossier du réseau.
STATIC_FEEDS = ("system_information", "station_information", "vehicle_types")
TIMEOUT_SECONDS = 15


# --- Téléchargement -----------------------------------------------------------


def fetch_json(url: str) -> dict[str, Any]:
    """Télécharge un fichier JSON. Lève NetworkError en cas de problème."""
    log.debug("Téléchargement de %s", url)
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise NetworkError(f"Réseau injoignable ({url}) : {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise NetworkError(f"Réponse invalide (pas du JSON) : {url}") from exc
    if not isinstance(data, dict):
        raise NetworkError(f"Réponse inattendue : {url}")
    return data


def discover_feeds(gbfs_url: str) -> dict[str, str]:
    """Lit gbfs.json et renvoie {nom du fichier: adresse}.

    GBFS 2.x range la liste par langue (data -> fr -> feeds), GBFS 3.0 directement
    (data -> feeds) : on accepte les deux.
    """
    root = fetch_json(gbfs_url)
    data = root.get("data")
    if not isinstance(data, dict):
        raise NetworkError("gbfs.json invalide : champ « data » manquant.")
    feeds = data.get("feeds")
    if feeds is None:
        # GBFS 2.x : on prend la première langue disponible.
        languages = [value for value in data.values() if isinstance(value, dict)]
        feeds = languages[0].get("feeds") if languages else None
    if not isinstance(feeds, list):
        raise NetworkError("gbfs.json invalide : liste des fichiers introuvable.")
    result = {}
    for feed in feeds:
        if isinstance(feed, dict) and isinstance(feed.get("name"), str) and feed.get("url"):
            result[feed["name"]] = str(feed["url"])
    return result


def feed_url(feeds: dict[str, str], name: str) -> str:
    """Renvoie l'adresse d'un fichier, ou lève NetworkError s'il n'est pas publié."""
    if name not in feeds:
        raise NetworkError(f"Le réseau ne publie pas le fichier « {name} ».")
    return feeds[name]


def download_static_files(gbfs_url: str, folder: Path) -> None:
    """Télécharge les trois fichiers qui changent rarement et les enregistre dans `folder`."""
    feeds = discover_feeds(gbfs_url)
    folder.mkdir(parents=True, exist_ok=True)
    for name in STATIC_FEEDS:
        data = fetch_json(feed_url(feeds, name))
        if name == "station_information":
            parse_station_information(data)  # vérifie avant d'écraser l'ancien fichier
        path = folder / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.debug("Fichier enregistré : %s", path)


def fetch_snapshot(gbfs_url: str) -> Snapshot:
    """Télécharge l'état actuel de toutes les stations (station_status)."""
    feeds = discover_feeds(gbfs_url)
    return parse_station_status(fetch_json(feed_url(feeds, "station_status")))


# --- Lecture des fichiers enregistrés ----------------------------------------


def _read_static(folder: Path, name: str) -> dict[str, Any]:
    path = folder / f"{name}.json"
    if not path.exists():
        raise VeloError(f"Fichier {name}.json absent. Lancez : velo refresh")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VeloError(f"Fichier {path} illisible. Lancez : velo refresh") from exc
    if not isinstance(data, dict):
        raise VeloError(f"Fichier {path} invalide. Lancez : velo refresh")
    return data


def load_stations(folder: Path) -> dict[str, StationInfo]:
    """Lit station_information.json enregistré : {station_id: StationInfo}."""
    return parse_station_information(_read_static(folder, "station_information"))


def load_network_info(folder: Path) -> NetworkInfo:
    """Lit system_information.json enregistré."""
    return parse_system_information(_read_static(folder, "system_information"))


def static_files_date(folder: Path) -> datetime | None:
    """Date du plus ancien des trois fichiers enregistrés (None s'il en manque un)."""
    dates = []
    for name in STATIC_FEEDS:
        path = folder / f"{name}.json"
        if not path.exists():
            return None
        dates.append(datetime.fromtimestamp(path.stat().st_mtime).astimezone())
    return min(dates)


# --- Conversion JSON -> objets (avec validation) ------------------------------


def parse_time(value: Any) -> datetime:
    """Convertit une date GBFS en datetime local avec décalage horaire.

    GBFS 2.x : nombre de secondes depuis 1970 ; GBFS 3.0 : texte ISO 8601.
    """
    if isinstance(value, bool):
        raise ValueError("date invalide")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone()
    if isinstance(value, str):
        return datetime.fromisoformat(value).astimezone()
    raise ValueError("date invalide")


def _text(value: Any) -> str | None:
    """Un nom GBFS : texte simple (2.x) ou liste de traductions (3.0)."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        text = value[0].get("text")
        return text if isinstance(text, str) else None
    return None


def _stations_list(data: dict[str, Any], fichier: str) -> list[Any]:
    stations = data.get("data", {}).get("stations") if isinstance(data.get("data"), dict) else None
    if not isinstance(stations, list):
        raise NetworkError(f"{fichier} invalide : liste des stations introuvable.")
    return stations


def parse_system_information(data: dict[str, Any]) -> NetworkInfo:
    """Transforme system_information en NetworkInfo."""
    content = data.get("data")
    if not isinstance(content, dict):
        raise NetworkError("system_information invalide.")
    return NetworkInfo(
        name=_text(content.get("name")) or "Réseau inconnu",
        timezone=str(content.get("timezone", "")),
    )


def parse_station_information(data: dict[str, Any]) -> dict[str, StationInfo]:
    """Transforme station_information en {station_id: StationInfo}.

    Une station mal décrite est ignorée (et journalisée), sans arrêter l'outil.
    """
    result: dict[str, StationInfo] = {}
    for raw in _stations_list(data, "station_information"):
        if not isinstance(raw, dict) or raw.get("station_id") is None:
            log.warning("Station ignorée (identifiant manquant) dans station_information")
            continue
        station_id = str(raw["station_id"])
        name = _text(raw.get("name"))
        if not name:
            log.warning("Station %s ignorée (nom manquant)", station_id)
            continue
        capacity = raw.get("capacity")
        result[station_id] = StationInfo(
            station_id=station_id,
            name=name.strip(),
            capacity=capacity if isinstance(capacity, int) and not isinstance(capacity, bool)
            else None,
        )
    if not result:
        raise NetworkError("station_information ne contient aucune station valide.")
    return result


def _count(raw: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    raise ValueError(f"champ {keys[0]} manquant ou invalide")


def _flag(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key)
    if isinstance(value, bool):
        return value
    if value in (0, 1):  # certains réseaux GBFS 1.x écrivent 0/1
        return bool(value)
    raise ValueError(f"champ {key} manquant ou invalide")


def parse_station_status(data: dict[str, Any]) -> Snapshot:
    """Transforme station_status en Snapshot. Les stations invalides sont ignorées."""
    try:
        last_updated = parse_time(data.get("last_updated"))
    except (ValueError, OSError) as exc:
        raise NetworkError("station_status invalide : date « last_updated » manquante.") from exc

    stations = []
    for raw in _stations_list(data, "station_status"):
        try:
            if not isinstance(raw, dict) or raw.get("station_id") is None:
                raise ValueError("identifiant manquant")
            stations.append(
                StationStatus(
                    station_id=str(raw["station_id"]),
                    bikes=_count(raw, "num_bikes_available", "num_vehicles_available"),
                    docks=_count(raw, "num_docks_available"),
                    is_installed=_flag(raw, "is_installed"),
                    is_renting=_flag(raw, "is_renting"),
                    is_returning=_flag(raw, "is_returning"),
                    last_reported=parse_time(raw.get("last_reported", data.get("last_updated"))),
                )
            )
        except (ValueError, OSError) as exc:
            ident = raw.get("station_id") if isinstance(raw, dict) else "?"
            log.warning("Station %s ignorée dans station_status : %s", ident, exc)
    if not stations:
        raise NetworkError("station_status ne contient aucune station valide.")
    return Snapshot(last_updated=last_updated, stations=stations)
