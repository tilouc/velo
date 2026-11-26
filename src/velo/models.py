"""Les objets manipulés par Vélo.

Le reste de l'outil ne touche jamais au JSON du GBFS : il travaille avec ces
objets simples, créés par le module gbfs.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NetworkInfo:
    """Informations générales sur un réseau (system_information)."""

    name: str
    timezone: str


@dataclass(frozen=True)
class StationInfo:
    """Ce qui change rarement dans une station (station_information)."""

    station_id: str
    name: str
    capacity: int | None


@dataclass(frozen=True)
class StationStatus:
    """L'état d'une station à un instant donné (station_status)."""

    station_id: str
    bikes: int
    docks: int
    is_installed: bool
    is_renting: bool
    is_returning: bool
    last_reported: datetime


@dataclass(frozen=True)
class Snapshot:
    """Un relevé : l'état de toutes les stations d'un réseau à un instant donné."""

    last_updated: datetime
    stations: list[StationStatus]
