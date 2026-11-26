"""Découpage de l'historique en périodes.

Une période est une suite de relevés sans interruption : deux relevés
consécutifs sont dans la même période si leur écart est inférieur à
3 fois l'intervalle de collecte (choix justifié dans le README).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

GAP_FACTOR = 3


@dataclass(frozen=True)
class Period:
    """Une période de collecte sans interruption."""

    number: int
    start: datetime
    end: datetime
    count: int  # nombre de relevés

    @property
    def duration(self) -> timedelta:
        """Durée entre le premier et le dernier relevé."""
        return self.end - self.start

    def contains(self, moment: datetime) -> bool:
        """Vrai si le relevé `moment` appartient à cette période."""
        return self.start <= moment <= self.end


def max_gap(interval_seconds: int) -> timedelta:
    """Écart maximal entre deux relevés d'une même période."""
    return timedelta(seconds=GAP_FACTOR * interval_seconds)


def find_periods(timestamps: list[datetime], interval_seconds: int) -> list[Period]:
    """Regroupe des dates de relevés en périodes numérotées de la plus ancienne à la plus récente."""
    moments = sorted(set(timestamps))
    if not moments:
        return []
    gap = max_gap(interval_seconds)
    groups: list[list[datetime]] = [[moments[0]]]
    for previous, current in zip(moments, moments[1:], strict=False):
        if current - previous < gap:
            groups[-1].append(current)
        else:
            groups.append([current])
    return [
        Period(number=i, start=g[0], end=g[-1], count=len(g))
        for i, g in enumerate(groups, start=1)
    ]


def format_duration(delta: timedelta) -> str:
    """Affiche une durée comme dans l'énoncé : "3 h 00"."""
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60:02d}"
