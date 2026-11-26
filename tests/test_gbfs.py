"""Tests de gbfs.py, avec l'API simulée (fixture fake_api)."""

import json
from pathlib import Path

import pytest

from tests.conftest import GBFS_URL, load_json
from velo import gbfs
from velo.errors import NetworkError, VeloError


def test_decouverte_des_fichiers_gbfs_2(fake_api: dict) -> None:
    feeds = gbfs.discover_feeds(GBFS_URL)
    assert feeds["station_status"] == "https://test.local/station_status.json"
    assert set(feeds) == {"system_information", "station_information", "station_status",
                          "vehicle_types"}


def test_decouverte_des_fichiers_gbfs_3(fake_api: dict) -> None:
    fake_api[GBFS_URL] = {"version": "3.0", "data": {"feeds": [
        {"name": "station_status", "url": "https://test.local/station_status.json"}]}}
    assert gbfs.discover_feeds(GBFS_URL) == {
        "station_status": "https://test.local/station_status.json"}


def test_gbfs_json_invalide(fake_api: dict) -> None:
    fake_api[GBFS_URL] = {"pas": "de data"}
    with pytest.raises(NetworkError):
        gbfs.discover_feeds(GBFS_URL)


def test_releve_ignore_les_stations_invalides(fake_api: dict) -> None:
    snapshot = gbfs.fetch_snapshot(GBFS_URL)
    ids = [s.station_id for s in snapshot.stations]
    assert ids == ["1", "2", "3", "4", "5"]  # la station 99 ("beaucoup" vélos) est ignorée
    assert snapshot.last_updated.utcoffset() is not None  # heure locale avec décalage


def test_releve_sans_station_valide() -> None:
    with pytest.raises(NetworkError):
        gbfs.parse_station_status({"last_updated": 1795431600, "data": {"stations": [{}]}})


def test_telechargement_des_fichiers_statiques(fake_api: dict, tmp_path: Path) -> None:
    gbfs.download_static_files(GBFS_URL, tmp_path)
    for name in gbfs.STATIC_FEEDS:
        assert (tmp_path / f"{name}.json").exists()
    stations = gbfs.load_stations(tmp_path)
    assert stations["2"].name == "Solférino"
    assert gbfs.load_network_info(tmp_path).name == "V'Lille Test"
    assert gbfs.static_files_date(tmp_path) is not None


def test_fichier_statique_absent(tmp_path: Path) -> None:
    with pytest.raises(VeloError, match="velo refresh"):
        gbfs.load_stations(tmp_path)
    assert gbfs.static_files_date(tmp_path) is None


def test_nom_gbfs_3_traduit(tmp_path: Path) -> None:
    data = load_json("station_information.json")
    data["data"]["stations"][0]["name"] = [{"text": "Gare", "language": "fr"}]
    (tmp_path / "station_information.json").write_text(json.dumps(data), encoding="utf-8")
    assert gbfs.load_stations(tmp_path)["1"].name == "Gare"


def test_parse_time_accepte_les_deux_formats() -> None:
    a = gbfs.parse_time(1795431600)
    b = gbfs.parse_time(a.isoformat())
    assert a == b
    with pytest.raises(ValueError):
        gbfs.parse_time(True)
