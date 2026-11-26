"""Les « fiches » que tout Vélo se passe de main en main.

Le site de V'Lille envoie du JSON compliqué. Le module gbfs.py le lit UNE fois
et le recopie dans ces fiches simples. Ensuite, le reste du code ne voit plus
jamais le JSON : il écrit station.bikes au lieu de
raw["data"]["stations"][3]["num_bikes_available"].

Une @dataclass, c'est une classe qui sert juste à ranger des valeurs avec un nom.
frozen=True : une fois remplie, la fiche ne change plus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NetworkInfo:
    """La carte d'identité du réseau. Exemple : nom "V'lille", fuseau "Europe/Paris"."""

    name: str
    timezone: str


@dataclass(frozen=True)
class StationInfo:
    """Ce qui ne bouge presque jamais dans une station : son numéro, son nom, sa taille.

    Exemple : StationInfo("10", "Rihour", 32)
    """

    station_id: str
    name: str
    capacity: int | None


@dataclass(frozen=True)
class StationStatus:
    """Ce qui bouge tout le temps : combien de vélos et de places, à un instant donné.

    Exemple : la station "10" a 12 vélos, 20 places libres, et fonctionne normalement.
    """

    station_id: str
    bikes: int
    docks: int
    is_installed: bool
    is_renting: bool
    is_returning: bool
    last_reported: datetime


@dataclass(frozen=True)
class Snapshot:
    """Un relevé : une photo de toutes les stations au même moment.

    last_updated = l'heure de la photo ; stations = la liste des StationStatus.
    """

    last_updated: datetime
    stations: list[StationStatus]
