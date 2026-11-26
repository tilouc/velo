"""Calculs sur l'état des stations : aucun affichage, aucun téléchargement.

Définitions (justifiées dans le README) :
- hors service : la station n'est pas installée, OU elle ne permet pas de
  prendre un vélo, OU elle ne permet pas d'en rendre un ;
- vide : 0 vélo ; presque vide : vélos <= seuil low_bikes ;
- pleine : 0 place libre ; presque pleine : places libres <= seuil low_docks.
Une station hors service n'est jamais comptée comme vide ou pleine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from velo.models import Snapshot, StationInfo, StationStatus


def is_out_of_service(status: StationStatus) -> bool:
    """Vrai si la station ne peut pas servir normalement."""
    return not (status.is_installed and status.is_renting and status.is_returning)


def is_low_bikes(status: StationStatus, low_bikes: int) -> bool:
    """Vrai si la station en service est vide ou presque vide."""
    return not is_out_of_service(status) and status.bikes <= low_bikes


def is_low_docks(status: StationStatus, low_docks: int) -> bool:
    """Vrai si la station en service est pleine ou presque pleine."""
    return not is_out_of_service(status) and status.docks <= low_docks


def state_label(status: StationStatus, low_bikes: int, low_docks: int) -> str:
    """Un mot qui résume l'état d'une station, ou "" si tout va bien."""
    if is_out_of_service(status):
        return "hors service"
    if status.bikes == 0:
        return "vide"
    if status.docks == 0:
        return "pleine"
    if status.bikes <= low_bikes:
        return "presque vide"
    if status.docks <= low_docks:
        return "presque pleine"
    return ""


# --- Résumé du réseau (velo status) ------------------------------------------


@dataclass(frozen=True)
class NetworkSummary:
    """Les chiffres affichés par velo status (et par le tableau de bord)."""

    total: int
    in_service: int
    out_of_service: int
    empty: int
    full: int
    bikes: int
    docks: int

    @property
    def fill_rate(self) -> float:
        """Taux de remplissage du réseau : vélos / (vélos + places libres), en %."""
        capacity = self.bikes + self.docks
        return 100 * self.bikes / capacity if capacity else 0.0


def summarize(snapshot: Snapshot) -> NetworkSummary:
    """Calcule le résumé du réseau à partir d'un relevé.

    Les vélos et places des stations hors service ne sont pas comptés : on ne
    peut pas s'en servir.
    """
    active = [s for s in snapshot.stations if not is_out_of_service(s)]
    return NetworkSummary(
        total=len(snapshot.stations),
        in_service=len(active),
        out_of_service=len(snapshot.stations) - len(active),
        empty=sum(1 for s in active if s.bikes == 0),
        full=sum(1 for s in active if s.docks == 0),
        bikes=sum(s.bikes for s in active),
        docks=sum(s.docks for s in active),
    )


# --- Alertes (velo alerts) ----------------------------------------------------


@dataclass(frozen=True)
class Alert:
    """Une station à signaler."""

    station_id: str
    name: str
    bikes: int
    docks: int


@dataclass
class Alerts:
    """Les alertes classées par type."""

    out_of_service: list[Alert] = field(default_factory=list)
    low_bikes: list[Alert] = field(default_factory=list)
    low_docks: list[Alert] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Nombre total d'alertes."""
        return len(self.out_of_service) + len(self.low_bikes) + len(self.low_docks)


def station_name(stations: dict[str, StationInfo], station_id: str) -> str:
    """Nom d'une station, ou un nom de remplacement si elle est inconnue."""
    info = stations.get(station_id)
    return info.name if info else f"(station {station_id} inconnue)"


def compute_alerts(
    snapshot: Snapshot, stations: dict[str, StationInfo], low_bikes: int, low_docks: int
) -> Alerts:
    """Range les stations à problème en trois listes, triées par nombre puis par nom."""
    alerts = Alerts()
    for status in snapshot.stations:
        alert = Alert(
            status.station_id, station_name(stations, status.station_id), status.bikes, status.docks
        )
        if is_out_of_service(status):
            alerts.out_of_service.append(alert)
            continue  # pas signalée une seconde fois comme vide ou pleine
        if status.bikes <= low_bikes:
            alerts.low_bikes.append(alert)
        if status.docks <= low_docks:
            alerts.low_docks.append(alert)
    alerts.out_of_service.sort(key=lambda a: a.name)
    alerts.low_bikes.sort(key=lambda a: (a.bikes, a.name))
    alerts.low_docks.sort(key=lambda a: (a.docks, a.name))
    return alerts


def status_by_id(snapshot: Snapshot) -> dict[str, StationStatus]:
    """Accès rapide à l'état d'une station par son identifiant."""
    return {s.station_id: s for s in snapshot.stations}


# --- Favoris (velo favorites et tableau de bord) ------------------------------


@dataclass(frozen=True)
class FavoriteRow:
    """Une ligne du tableau des favoris.

    bikes/docks valent None si la station n'apparaît pas dans le relevé.
    delta_bikes/delta_docks : évolution depuis le relevé précédent (tableau de bord).
    """

    station_id: str
    name: str
    bikes: int | None
    docks: int | None
    label: str
    delta_bikes: int | None = None
    delta_docks: int | None = None


def favorite_rows(
    favorite_ids: list[str],
    snapshot: Snapshot,
    stations: dict[str, StationInfo],
    low_bikes: int,
    low_docks: int,
    previous: Snapshot | None = None,
) -> list[FavoriteRow]:
    """Construit les lignes des favoris, avec l'évolution si un relevé précédent est donné."""
    current = status_by_id(snapshot)
    before = status_by_id(previous) if previous else {}
    rows = []
    for station_id in favorite_ids:
        status = current.get(station_id)
        name = station_name(stations, station_id)
        if status is None:
            rows.append(FavoriteRow(station_id, name, None, None, "absente du relevé"))
            continue
        old = before.get(station_id)
        rows.append(
            FavoriteRow(
                station_id=station_id,
                name=name,
                bikes=status.bikes,
                docks=status.docks,
                label=state_label(status, low_bikes, low_docks),
                delta_bikes=status.bikes - old.bikes if old else None,
                delta_docks=status.docks - old.docks if old else None,
            )
        )
    return rows
