"""Analyse de l'historique (velo query) : sélection, métriques, regroupement.

Les relevés des stations hors service sont exclus des calculs (une station
fermée n'est ni « vide » ni « pleine » au sens de l'usager). Les interruptions
de collecte ne sont jamais comblées : on calcule seulement sur ce qui existe.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time

from velo.errors import VeloError
from velo.history import Period, find_periods, max_gap
from velo.storage import Record

METRICS = ("avg_bikes", "avg_docks", "empty_rate", "full_rate")
GROUPS = ("station", "hour", "weekday", "day")
WEEKDAY_NAMES = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_DAY_ALIASES = {
    **{name: i for i, name in enumerate(WEEKDAY_NAMES)},
    **{name: i for i, name in enumerate(("mon", "tue", "wed", "thu", "fri", "sat", "sun"))},
    **{name: i for i, name in enumerate(
        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))},
}


class NoDataError(VeloError):
    """Aucun relevé ne correspond à la sélection demandée."""


# --- Lecture des options de sélection ----------------------------------------


def parse_day(text: str) -> date:
    """"2026-11-18" -> date. Lève VeloError si le format est faux."""
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise VeloError(f"Date invalide : « {text} » (format attendu : AAAA-MM-JJ).") from exc


def parse_moment(text: str, end_of_day: bool = False) -> datetime:
    """"2026-11-18" ou "2026-11-18 08:30" -> datetime local avec décalage horaire.

    Une date seule vaut le début du jour, ou la fin du jour si end_of_day est vrai.
    """
    text = text.strip()
    try:
        if len(text) == 10:
            moment = datetime.combine(date.fromisoformat(text), time.max if end_of_day else time.min)
        else:
            moment = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise VeloError(
            f"Date invalide : « {text} » (formats acceptés : AAAA-MM-JJ ou \"AAAA-MM-JJ HH:MM\")."
        ) from exc
    return moment.astimezone()


def parse_days(values: list[str]) -> set[int]:
    """["weekdays"] -> {0..4} ; ["weekend"] -> {5, 6} ; ["lundi", "mardi"] -> {0, 1}."""
    days: set[int] = set()
    for value in values:
        for item in value.lower().split(","):
            item = item.strip()
            if not item:
                continue
            if item == "weekdays":
                days |= {0, 1, 2, 3, 4}
            elif item == "weekend":
                days |= {5, 6}
            elif item in _DAY_ALIASES:
                days.add(_DAY_ALIASES[item])
            else:
                raise VeloError(
                    f"Jour invalide : « {item} » (weekdays, weekend, ou lundi, mardi... / mon, tue...)."
                )
    return days


def parse_hours(text: str) -> tuple[int, int]:
    """"7-9" -> (7, 9) : relevés de 7:00 inclus à 9:00 exclu."""
    try:
        start_text, end_text = text.split("-")
        start, end = int(start_text), int(end_text)
    except ValueError as exc:
        raise VeloError(f"Plage horaire invalide : « {text} » (exemple : 7-9).") from exc
    if not (0 <= start < end <= 24):
        raise VeloError(f"Plage horaire invalide : « {text} » (heures entre 0 et 24, début < fin).")
    return start, end


# --- Sélection ---------------------------------------------------------------


@dataclass
class Selection:
    """Les critères de sélection des relevés (tous facultatifs)."""

    day: date | None = None
    start: datetime | None = None
    end: datetime | None = None
    periods: list[int] = field(default_factory=list)
    days: set[int] = field(default_factory=set)
    hours: tuple[int, int] | None = None
    station: str | None = None

    def keeps(self, record: Record, periods: list[Period]) -> bool:
        """Vrai si le relevé correspond à tous les critères."""
        moment = record.timestamp
        if self.station is not None and record.station_id != self.station:
            return False
        if self.day is not None and moment.date() != self.day:
            return False
        if self.start is not None and moment < self.start:
            return False
        if self.end is not None and moment > self.end:
            return False
        if self.days and moment.weekday() not in self.days:
            return False
        if self.hours is not None and not (self.hours[0] <= moment.hour < self.hours[1]):
            return False
        if self.periods and not any(
            p.contains(moment) for p in periods if p.number in self.periods
        ):
            return False
        return True


# --- Calcul ------------------------------------------------------------------


@dataclass(frozen=True)
class ResultRow:
    """Une ligne du résultat : un groupe et la valeur de chaque métrique."""

    key: str
    values: dict[str, float]
    count: int  # nombre de lignes (station x relevé) utilisées


@dataclass
class QueryResult:
    """Le résultat complet d'une requête."""

    rows: list[ResultRow]
    snapshot_count: int
    periods_used: list[int]
    interrupted: bool


def compute_metric(metric: str, records: list[Record]) -> float:
    """Calcule une métrique sur une liste de relevés (non vide). Les taux sont en %."""
    n = len(records)
    if metric == "avg_bikes":
        return sum(r.bikes for r in records) / n
    if metric == "avg_docks":
        return sum(r.docks for r in records) / n
    if metric == "empty_rate":
        return 100 * sum(1 for r in records if r.bikes == 0) / n
    if metric == "full_rate":
        return 100 * sum(1 for r in records if r.docks == 0) / n
    raise VeloError(f"Métrique inconnue : {metric}")


def group_key(record: Record, by: str | None) -> str:
    """Le nom du groupe d'un relevé selon --by."""
    if by == "station":
        return record.station_id
    if by == "hour":
        return f"{record.timestamp.hour:02d}h"
    if by == "weekday":
        return f"{record.timestamp.weekday()}-{WEEKDAY_NAMES[record.timestamp.weekday()]}"
    if by == "day":
        return record.timestamp.date().isoformat()
    return "réseau"


def run_query(
    records: list[Record],
    selection: Selection,
    metrics: list[str],
    interval_seconds: int,
    by: str | None = None,
    top: int | None = None,
) -> QueryResult:
    """Exécute une requête sur l'historique."""
    periods = find_periods([r.timestamp for r in records], interval_seconds)
    known = {p.number for p in periods}
    unknown = [n for n in selection.periods if n not in known]
    if unknown:
        raise NoDataError(f"Période(s) inconnue(s) : {', '.join(map(str, unknown))}.")

    selected = [r for r in records if selection.keeps(r, periods)]
    usable = [r for r in selected if not r.out_of_service]
    if not usable:
        raise NoDataError("Aucune donnée sur la sélection demandée.")

    moments = sorted({r.timestamp for r in usable})
    used = [p.number for p in periods if any(p.contains(m) for m in moments)]

    groups: dict[str, list[Record]] = defaultdict(list)
    for record in usable:
        groups[group_key(record, by)].append(record)

    rows = [
        ResultRow(key, {m: compute_metric(m, recs) for m in metrics}, len(recs))
        for key, recs in groups.items()
    ]
    if by in ("station", None) or top is not None:
        rows.sort(key=lambda row: (-row.values[metrics[0]], row.key))
    else:
        rows.sort(key=lambda row: row.key)
    if top is not None:
        rows = rows[:top]

    return QueryResult(
        rows=rows,
        snapshot_count=len(moments),
        periods_used=used,
        interrupted=len(used) > 1 or _window_not_covered(selection, moments, interval_seconds),
    )


def _window_not_covered(selection: Selection, moments: list[datetime], interval: int) -> bool:
    """Vrai si la fenêtre de dates demandée commence avant ou finit après les relevés."""
    start, end = selection.start, selection.end
    if selection.day is not None:
        start = datetime.combine(selection.day, time.min).astimezone()
        end = datetime.combine(selection.day, time.max).astimezone()
    gap = max_gap(interval)
    if start is not None and moments[0] - start > gap:
        return True
    if end is not None:
        end = min(end, datetime.now().astimezone())
        if end - moments[-1] > gap:
            return True
    return False
