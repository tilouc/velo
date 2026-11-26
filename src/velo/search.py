"""Chercher une station par son nom (velo station search).

Le but : que l'utilisateur trouve sa station même en tapant n'importe comment.
- les majuscules ne comptent pas : "gare" trouve "Gare Lille Flandres" ;
- les accents ne comptent pas : "solferino" trouve "Solférino" ;
- un bout de mot suffit : "flan" trouve "Flandres" ;
- avec plusieurs mots, chacun doit être présent, dans n'importe quel ordre :
  "flandres gare" trouve "Gare Lille Flandres" ;
- les symboles tapés ("(", ".", "*"...) sont cherchés tels quels, au lieu
  d'être compris comme des commandes d'expression régulière (grâce à re.escape).

Une expression régulière (le module re), c'est un « motif » qu'on cherche dans
un texte. Ici, le motif est simplement chaque mot tapé.
"""

from __future__ import annotations

import re
import unicodedata

from velo.models import StationInfo


def normalize(text: str) -> str:
    """Met en minuscules et enlève les accents. Exemple : "Solférino" -> "solferino"."""
    decomposed = unicodedata.normalize("NFKD", text)  # "é" devient "e" + l'accent à part
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def build_patterns(query: str) -> list[re.Pattern[str]]:
    """Un motif par mot tapé. Espaces, tirets et apostrophes séparent les mots.

    Exemple : "porte-de-douai" -> trois motifs : "porte", "de", "douai".
    """
    words = re.findall(r"[^\s'’\-]+", normalize(query))
    return [re.compile(re.escape(word)) for word in words]


def search_stations(stations: dict[str, StationInfo], query: str) -> list[StationInfo]:
    """Renvoie les stations dont le nom contient TOUS les mots tapés, triées par numéro."""
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
    """Trie les numéros comme des nombres, pas comme du texte.

    En texte, "10" passe avant "2" (on compare "1" et "2"). En nombre, 2 passe avant 10.
    """
    return (0, int(station_id)) if station_id.isdigit() else (1, station_id)
