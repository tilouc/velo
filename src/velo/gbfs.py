"""Le seul fichier qui parle au site de V'Lille.

GBFS, c'est le format standard dans lequel des centaines de réseaux de vélos
publient leurs données. Ça marche comme un sommaire :
1. on télécharge gbfs.json : c'est le sommaire, il donne l'adresse des autres fichiers ;
2. on télécharge le fichier dont on a besoin (par exemple station_status.json) ;
3. on vérifie son contenu et on le recopie dans les fiches de models.py.

Pourquoi tout regrouper ici ? Si demain V'Lille change son format, c'est le
seul fichier à modifier. Le reste de l'outil ne voit jamais le JSON.
Et seule l'adresse du sommaire vient de config.yaml : les autres sont lues dedans.
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

# Les trois fichiers qui changent rarement : on les garde sur le disque.
STATIC_FEEDS = ("system_information", "station_information", "vehicle_types")
TIMEOUT_SECONDS = 15  # si le site ne répond pas en 15 s, on abandonne


# --- 1. Télécharger ------------------------------------------------------------------


def fetch_json(url: str) -> dict[str, Any]:
    """Télécharge une adresse et renvoie le JSON sous forme de dictionnaire.

    Si internet est coupé, si le site plante ou si la réponse n'est pas du JSON,
    on lève une NetworkError avec un message clair (jamais de plantage brut).
    """
    log.debug("Téléchargement de %s", url)
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()  # erreur si le site répond « 404 » ou « 500 »
        data = response.json()
    except requests.RequestException as exc:
        raise NetworkError(f"Réseau injoignable ({url}) : {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise NetworkError(f"Réponse invalide (pas du JSON) : {url}") from exc
    if not isinstance(data, dict):
        raise NetworkError(f"Réponse inattendue : {url}")
    return data


def discover_feeds(gbfs_url: str) -> dict[str, str]:
    """Lit le sommaire gbfs.json et renvoie {nom du fichier: son adresse}.

    Exemple de résultat : {"station_status": "https://.../station_status.json", ...}
    Deux versions existent : en 2.x la liste est rangée par langue
    (data -> en -> feeds), en 3.0 directement (data -> feeds). On accepte les deux.
    """
    root = fetch_json(gbfs_url)
    data = root.get("data")
    if not isinstance(data, dict):
        raise NetworkError("gbfs.json invalide : champ « data » manquant.")
    feeds = data.get("feeds")
    if feeds is None:
        # Version 2.x : on prend la première langue disponible.
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
    """Donne l'adresse d'un fichier du sommaire, ou une erreur s'il n'est pas publié."""
    if name not in feeds:
        raise NetworkError(f"Le réseau ne publie pas le fichier « {name} ».")
    return feeds[name]


def download_static_files(gbfs_url: str, folder: Path) -> None:
    """Télécharge les trois fichiers qui changent rarement et les range dans `folder`."""
    feeds = discover_feeds(gbfs_url)
    folder.mkdir(parents=True, exist_ok=True)
    for name in STATIC_FEEDS:
        data = fetch_json(feed_url(feeds, name))
        if name == "station_information":
            parse_station_information(data)  # on vérifie AVANT d'écraser l'ancien fichier
        path = folder / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        log.debug("Fichier enregistré : %s", path)


def fetch_snapshot(gbfs_url: str) -> Snapshot:
    """Télécharge l'état de toutes les stations MAINTENANT, et renvoie un Snapshot."""
    feeds = discover_feeds(gbfs_url)
    return parse_station_status(fetch_json(feed_url(feeds, "station_status")))


# --- 2. Relire les fichiers déjà enregistrés sur le disque ----------------------------


def _read_static(folder: Path, name: str) -> dict[str, Any]:
    """Relit un des trois fichiers enregistrés. S'il manque : « lancez velo refresh »."""
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
    """Renvoie toutes les stations connues, rangées par numéro : {"10": StationInfo(...)}."""
    return parse_station_information(_read_static(folder, "station_information"))


def load_network_info(folder: Path) -> NetworkInfo:
    """Renvoie la carte d'identité du réseau (son nom, son fuseau horaire)."""
    return parse_system_information(_read_static(folder, "system_information"))


def static_files_date(folder: Path) -> datetime | None:
    """Renvoie la date du plus vieux des trois fichiers, ou None s'il en manque un.

    Sert à prévenir l'utilisateur : « vos infos datent de 10 jours, faites velo refresh ».
    """
    dates = []
    for name in STATIC_FEEDS:
        path = folder / f"{name}.json"
        if not path.exists():
            return None
        dates.append(datetime.fromtimestamp(path.stat().st_mtime).astimezone())
    return min(dates)


# --- 3. Vérifier le JSON et le recopier dans les fiches -------------------------------


def parse_time(value: Any) -> datetime:
    """Transforme une date GBFS en vraie date Python, à l'heure locale.

    En 2.x, une date est un nombre de secondes depuis 1970 (exemple : 1795431600).
    En 3.0, c'est un texte (exemple : "2026-11-18T08:14:00+01:00"). On gère les deux.
    """
    if isinstance(value, bool):
        raise ValueError("date invalide")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).astimezone()
    if isinstance(value, str):
        return datetime.fromisoformat(value).astimezone()
    raise ValueError("date invalide")


def _text(value: Any) -> str | None:
    """Lit un nom : texte simple en 2.x, liste de traductions en 3.0."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        text = value[0].get("text")
        return text if isinstance(text, str) else None
    return None


def _stations_list(data: dict[str, Any], fichier: str) -> list[Any]:
    """Va chercher data -> stations dans le JSON, ou lève une erreur si ce n'est pas là."""
    stations = data.get("data", {}).get("stations") if isinstance(data.get("data"), dict) else None
    if not isinstance(stations, list):
        raise NetworkError(f"{fichier} invalide : liste des stations introuvable.")
    return stations


def parse_system_information(data: dict[str, Any]) -> NetworkInfo:
    """JSON de system_information -> fiche NetworkInfo."""
    content = data.get("data")
    if not isinstance(content, dict):
        raise NetworkError("system_information invalide.")
    return NetworkInfo(
        name=_text(content.get("name")) or "Réseau inconnu",
        timezone=str(content.get("timezone", "")),
    )


def parse_station_information(data: dict[str, Any]) -> dict[str, StationInfo]:
    """JSON de station_information -> {numéro: fiche StationInfo}.

    Une station mal décrite (sans numéro ou sans nom) est sautée et notée dans le
    journal. On ne fait pas planter tout l'outil pour une seule station abîmée.
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
    """Lit un nombre de vélos ou de places : il doit être un entier positif ou nul."""
    for key in keys:
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    raise ValueError(f"champ {keys[0]} manquant ou invalide")


def _flag(raw: dict[str, Any], key: str) -> bool:
    """Lit un vrai/faux (true/false). Certains vieux réseaux écrivent 1/0 : accepté aussi."""
    value = raw.get(key)
    if isinstance(value, bool):
        return value
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"champ {key} manquant ou invalide")


def parse_station_status(data: dict[str, Any]) -> Snapshot:
    """JSON de station_status -> Snapshot (la photo de toutes les stations).

    Chaque station est vérifiée. Si une seule est abîmée (par exemple
    "beaucoup" vélos au lieu d'un nombre), on la saute et on continue.
    """
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
                    # en 3.0 le champ s'appelle num_vehicles_available
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
