"""Tests de la recherche de stations et des favoris."""

from pathlib import Path

import pytest

from tests.conftest import load_json
from velo import favorites, gbfs, search
from velo.errors import VeloError
from velo.models import StationInfo

STATIONS = gbfs.parse_station_information(load_json("station_information.json"))


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("gare", ["1", "10"]),            # casse ignorée, tri numérique (1 avant 10)
        ("solferino", ["2"]),             # accents ignorés
        ("flan", ["1"]),                  # recherche partielle
        ("flandres gare", ["1"]),         # mots dans n'importe quel ordre
        ("porte-de-douai", ["4"]),        # tirets traités comme des espaces
        ("(", []),                        # caractère spécial pris au pied de la lettre
        ("zzz", []),
    ],
)
def test_recherche(texte: str, attendu: list[str]) -> None:
    assert [s.station_id for s in search.search_stations(STATIONS, texte)] == attendu


def test_ajout_retrait_favoris(tmp_path: Path) -> None:
    assert favorites.load_favorites(tmp_path) == []
    favorites.add_favorite(tmp_path, "2", STATIONS)
    assert favorites.load_favorites(tmp_path) == ["2"]
    with pytest.raises(VeloError, match="déjà"):
        favorites.add_favorite(tmp_path, "2", STATIONS)
    with pytest.raises(VeloError, match="inconnue"):
        favorites.add_favorite(tmp_path, "999", STATIONS)
    favorites.remove_favorite(tmp_path, "2")
    with pytest.raises(VeloError, match="pas dans vos favoris"):
        favorites.remove_favorite(tmp_path, "2")


def test_maximum_de_favoris(tmp_path: Path) -> None:
    many = {str(i): StationInfo(str(i), f"S{i}", 10) for i in range(11)}
    for i in range(favorites.MAX_FAVORITES):
        favorites.add_favorite(tmp_path, str(i), many)
    with pytest.raises(VeloError, match="maximum"):
        favorites.add_favorite(tmp_path, "10", many)


def test_fichier_favoris_corrompu(tmp_path: Path) -> None:
    favorites.favorites_path(tmp_path).write_text("{pas du json", encoding="utf-8")
    assert favorites.load_favorites(tmp_path) == []
