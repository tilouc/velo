"""Découper l'historique en périodes (velo history).

Une période, c'est une suite de relevés sans trou. Exemple : tu lances la
collecte de 7h à 10h lundi, puis de 7h à 10h mardi -> deux périodes.

Comment on repère un trou ? On regarde l'écart entre deux relevés qui se
suivent. S'il est plus petit que 3 fois l'intervalle de collecte, c'est la
même période. Sinon, c'est une nouvelle période.
Avec l'intervalle par défaut de 120 s, le seuil vaut 3 x 120 = 360 s (6 minutes).

Pourquoi 3 et pas 1 ? Avec 1, un seul relevé raté (internet qui saute 10 s)
couperait la période en deux. Avec 3, on tolère deux relevés ratés. Au-delà,
c'est que la collecte a vraiment été arrêtée.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

GAP_FACTOR = 3


@dataclass(frozen=True)
class Period:
    """Une période : son numéro, son début, sa fin, et combien de relevés elle contient."""

    number: int
    start: datetime
    end: datetime
    count: int

    @property
    def duration(self) -> timedelta:
        """Le temps entre le premier et le dernier relevé."""
        return self.end - self.start

    def contains(self, moment: datetime) -> bool:
        """Vrai si ce moment tombe dans la période."""
        return self.start <= moment <= self.end


def max_gap(interval_seconds: int) -> timedelta:
    """L'écart maximal entre deux relevés d'une même période (3 x l'intervalle)."""
    return timedelta(seconds=GAP_FACTOR * interval_seconds)


def find_periods(timestamps: list[datetime], interval_seconds: int) -> list[Period]:
    """Range des heures de relevés en périodes, numérotées de la plus vieille à la plus récente.

    Exemple avec un seuil de 6 min : 8:00, 8:02, 8:04, puis 11:00, 11:02
    -> période 1 (8:00 à 8:04, 3 relevés) et période 2 (11:00 à 11:02, 2 relevés).
    """
    moments = sorted(set(timestamps))  # set() enlève les doublons (une ligne par station)
    if not moments:
        return []
    gap = max_gap(interval_seconds)
    groups: list[list[datetime]] = [[moments[0]]]
    # zip(moments, moments[1:]) donne les paires qui se suivent : (8:00, 8:02), (8:02, 8:04)...
    for previous, current in zip(moments, moments[1:], strict=False):
        if current - previous < gap:
            groups[-1].append(current)  # petit écart : même période
        else:
            groups.append([current])  # gros trou : nouvelle période
    return [
        Period(number=i, start=g[0], end=g[-1], count=len(g))
        for i, g in enumerate(groups, start=1)
    ]


def format_duration(delta: timedelta) -> str:
    """Écrit une durée comme dans l'énoncé. Exemple : 3 heures -> "3 h 00"."""
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60} h {minutes % 60:02d}"
