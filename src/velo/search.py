"""Recherche de stations par leur nom, avec des expressions régulières.

Choix (expliqués dans le README) :
- la casse est ignorée : "gare" trouve "Gare Lille Flandres" ;
- les accents sont ignorés : "solferino" trouve "Solférino" ;
- la recherche est partielle : "flan" trouve "Flandres" ;
- plusieurs mots doivent tous apparaître, dans n'importe quel ordre :
  "flandres gare" trouve "Gare Lille Flandres" ;
- les caractères spéciaux tapés par l'utilisateur ("(", ".", "*"...) sont pris
  au pied de la lettre grâce à re.escape.
"""

from __future__ import annotations

import re
import unicodedata

from velo.models import StationInfo


def normalize(text: str) -> str:
    """Met en minuscules et enlève les accents : "Solférino" -> "solferino"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def build_patterns(query: str) -> list[re.Pattern[str]]:
    """Une expression régulière par mot recherché."""
    words = re.findall(r"[^\s'’\-]+", normalize(query))
    return [re.compile(re.escape(word)) for word in words]


def search_stations(stations: dict[str, StationInfo], query: str) -> list[StationInfo]:
    """Renvoie les stations dont le nom contient tous les mots de `query`."""
    patterns = build_patterns(query)
    if not patterns:
        return []
    found = [
        info
        for info in stations.values()
        if all(p.search(normalize(info.name)) for p in patterns)
    ]
    return sorted(found, key=lambda info: sort_key(info.station_id))


def sort_key(station_id: str) -> tuple[int, int | str]:
    """Trie les identifiants numériquement quand c'est possible : 2 avant 10."""
    return (0, int(station_id)) if station_id.isdigit() else (1, station_id)
