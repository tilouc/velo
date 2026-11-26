"""Les calculs sur les stations. Ici, on calcule : on n'affiche rien, on ne télécharge rien.

D'abord, les définitions (on les justifie dans le README) :
- hors service : la station n'est pas installée, OU on ne peut pas y prendre
  de vélo, OU on ne peut pas en rendre. Bref, l'usager ne peut pas compter dessus ;
- vide : 0 vélo. Presque vide : vélos <= seuil (low_bikes, 2 par défaut) ;
- pleine : 0 place libre. Presque pleine : places <= seuil (low_docks, 2 par défaut).

Règle importante : une station hors service n'est JAMAIS comptée comme vide ou
pleine. Elle est déjà signalée comme hors service, inutile de la compter deux fois.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from velo.models import Snapshot, StationInfo, StationStatus


def is_out_of_service(status: StationStatus) -> bool:
    """Vrai si la station ne marche pas normalement.

    Il faut les trois à la fois (installée ET on peut prendre ET on peut rendre)
    pour qu'elle soit en service. S'il en manque un seul, elle est hors service.
    """
    return not (status.is_installed and status.is_renting and status.is_returning)


def is_low_bikes(status: StationStatus, low_bikes: int) -> bool:
    """Vrai si la station marche ET a peu de vélos. Exemple avec un seuil de 2 : 0, 1 ou 2 vélos."""
    return not is_out_of_service(status) and status.bikes <= low_bikes


def is_low_docks(status: StationStatus, low_docks: int) -> bool:
    """Vrai si la station marche ET a peu de places libres."""
    return not is_out_of_service(status) and status.docks <= low_docks


def state_label(status: StationStatus, low_bikes: int, low_docks: int) -> str:
    """Un mot qui résume l'état d'une station : "vide", "pleine"… ou "" si tout va bien.

    L'ordre des tests compte : on regarde d'abord le plus grave (hors service).
    """
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


# --- Le résumé du réseau (velo status) ------------------------------------------------


@dataclass(frozen=True)
class NetworkSummary:
    """Les chiffres que velo status affiche (le tableau de bord aussi)."""

    total: int
    in_service: int
    out_of_service: int
    empty: int
    full: int
    bikes: int
    docks: int

    @property
    def fill_rate(self) -> float:
        """Le taux de remplissage, en %.

        Exemple : 30 vélos et 70 places libres -> 30 / (30 + 70) = 30 %.
        """
        capacity = self.bikes + self.docks
        return 100 * self.bikes / capacity if capacity else 0.0


def summarize(snapshot: Snapshot) -> NetworkSummary:
    """Compte tout ce qu'il y a dans un relevé.

    Les vélos d'une station hors service ne sont pas comptés : personne ne peut
    les prendre, donc ils ne sont pas vraiment « disponibles ».
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


# --- Les alertes (velo alerts) -----------------------------------------------------------


@dataclass(frozen=True)
class Alert:
    """Une station à signaler, avec ce qu'il faut pour l'afficher."""

    station_id: str
    name: str
    bikes: int
    docks: int


@dataclass
class Alerts:
    """Trois listes d'alertes : hors service, presque vides, presque pleines."""

    out_of_service: list[Alert] = field(default_factory=list)
    low_bikes: list[Alert] = field(default_factory=list)
    low_docks: list[Alert] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Le nombre total d'alertes (0 = tout va bien)."""
        return len(self.out_of_service) + len(self.low_bikes) + len(self.low_docks)


def station_name(stations: dict[str, StationInfo], station_id: str) -> str:
    """Le nom d'une station à partir de son numéro. Inconnue ? On le dit au lieu de planter."""
    info = stations.get(station_id)
    return info.name if info else f"(station {station_id} inconnue)"


def compute_alerts(
    snapshot: Snapshot, stations: dict[str, StationInfo], low_bikes: int, low_docks: int
) -> Alerts:
    """Range chaque station à problème dans la bonne liste.

    Tri : les plus vides en premier (0 vélo avant 1 vélo), puis par nom.
    """
    alerts = Alerts()
    for status in snapshot.stations:
        alert = Alert(
            status.station_id, station_name(stations, status.station_id), status.bikes, status.docks
        )
        if is_out_of_service(status):
            alerts.out_of_service.append(alert)
            continue  # déjà signalée : on ne la met pas aussi dans « vide » ou « pleine »
        if status.bikes <= low_bikes:
            alerts.low_bikes.append(alert)
        if status.docks <= low_docks:
            alerts.low_docks.append(alert)
    alerts.out_of_service.sort(key=lambda a: a.name)
    alerts.low_bikes.sort(key=lambda a: (a.bikes, a.name))
    alerts.low_docks.sort(key=lambda a: (a.docks, a.name))
    return alerts


def status_by_id(snapshot: Snapshot) -> dict[str, StationStatus]:
    """Range les stations d'un relevé par numéro, pour retrouver la "10" d'un coup."""
    return {s.station_id: s for s in snapshot.stations}


# --- Les favoris (velo favorites et tableau de bord) ---------------------------------------


@dataclass(frozen=True)
class FavoriteRow:
    """Une ligne du tableau des favoris.

    bikes / docks valent None si la station n'est pas dans le relevé.
    delta_bikes / delta_docks : ce qui a changé depuis le relevé d'avant
    (exemple : -2 = deux vélos sont partis). Utilisé par le tableau de bord.
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
    """Prépare une ligne par favori. Si on donne le relevé d'avant, calcule aussi l'évolution."""
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
