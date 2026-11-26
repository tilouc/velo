"""Tests de states.py : définitions des états, résumé, alertes, favoris."""

from datetime import datetime

from tests.conftest import load_json
from velo import gbfs, states
from velo.models import Snapshot, StationStatus

NOW = datetime(2026, 11, 18, 8, 0).astimezone()


def station(sid: str, bikes: int, docks: int, ok: bool = True) -> StationStatus:
    return StationStatus(sid, bikes, docks, True, ok, ok, NOW)


def test_hors_service() -> None:
    assert states.is_out_of_service(station("1", 3, 3, ok=False))
    assert not states.is_out_of_service(station("1", 3, 3))
    assert states.is_out_of_service(StationStatus("1", 3, 3, False, True, True, NOW))


def test_etiquettes() -> None:
    assert states.state_label(station("1", 0, 10), 2, 2) == "vide"
    assert states.state_label(station("1", 2, 10), 2, 2) == "presque vide"
    assert states.state_label(station("1", 10, 0), 2, 2) == "pleine"
    assert states.state_label(station("1", 10, 1), 2, 2) == "presque pleine"
    assert states.state_label(station("1", 0, 0, ok=False), 2, 2) == "hors service"
    assert states.state_label(station("1", 5, 5), 2, 2) == ""


def test_resume_du_reseau() -> None:
    snapshot = gbfs.parse_station_status(load_json("station_status.json"))
    summary = states.summarize(snapshot)
    assert (summary.total, summary.in_service, summary.out_of_service) == (5, 4, 1)
    assert (summary.empty, summary.full) == (1, 1)
    assert (summary.bikes, summary.docks) == (22, 38)  # la station 4 (hors service) est exclue
    assert round(summary.fill_rate) == 37


def test_alertes_sans_doublon_et_seuils() -> None:
    snapshot = gbfs.parse_station_status(load_json("station_status.json"))
    stations = gbfs.parse_station_information(load_json("station_information.json"))
    alerts = states.compute_alerts(snapshot, stations, low_bikes=2, low_docks=2)
    assert [a.station_id for a in alerts.out_of_service] == ["4"]
    assert [a.station_id for a in alerts.low_bikes] == ["1", "2"]
    assert [a.station_id for a in alerts.low_docks] == ["3"]
    # avec un seuil plus haut, Vauban (8 vélos) devient « presque vide »
    alerts = states.compute_alerts(snapshot, stations, low_bikes=8, low_docks=0)
    assert "5" in [a.station_id for a in alerts.low_bikes]
    assert "4" not in [a.station_id for a in alerts.low_bikes]


def test_aucune_alerte() -> None:
    snapshot = Snapshot(NOW, [station("1", 5, 5)])
    assert states.compute_alerts(snapshot, {}, 2, 2).count == 0


def test_favoris_avec_evolution() -> None:
    before = Snapshot(NOW, [station("1", 5, 5)])
    after = Snapshot(NOW, [station("1", 3, 7)])
    rows = states.favorite_rows(["1", "42"], after, {}, 2, 2, previous=before)
    assert (rows[0].bikes, rows[0].delta_bikes, rows[0].delta_docks) == (3, -2, 2)
    assert rows[1].bikes is None and rows[1].label == "absente du relevé"
