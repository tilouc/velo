"""Tests du stockage CSV, des périodes et des requêtes."""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from tests.conftest import DATA
from velo import history, query, storage
from velo.models import Snapshot, StationStatus

BASE = datetime(2026, 11, 18, 8, 0).astimezone()


def snap(moment: datetime, bikes: int = 3) -> Snapshot:
    return Snapshot(moment, [StationStatus("1", bikes, 10 - bikes, True, True, True, moment),
                             StationStatus("2", 0, 10, True, True, True, moment)])


def test_ecriture_puis_lecture(tmp_path: Path) -> None:
    storage.append_snapshot(tmp_path, snap(BASE))
    storage.append_snapshot(tmp_path, snap(BASE + timedelta(minutes=2)))
    files = storage.history_files(tmp_path)
    assert [f.name for f in files] == [f"{BASE.date().isoformat()}.csv"]
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(storage.COLUMNS)  # un seul en-tête
    assert len(lines) == 1 + 4
    records = storage.read_history(tmp_path)
    assert records[0].timestamp == BASE
    assert storage.last_timestamp(tmp_path) == BASE + timedelta(minutes=2)


def test_releve_apres_minuit_dans_le_fichier_du_jour_suivant(tmp_path: Path) -> None:
    late = datetime(2026, 11, 18, 23, 59).astimezone()
    storage.append_snapshot(tmp_path, snap(late))
    storage.append_snapshot(tmp_path, snap(late + timedelta(minutes=2)))
    assert [f.name for f in storage.history_files(tmp_path)] == ["2026-11-18.csv", "2026-11-19.csv"]


def test_ligne_invalide_ignoree(tmp_path: Path) -> None:
    shutil.copy(DATA / "history_sample.csv", tmp_path / "2026-11-18.csv")
    records = storage.read_history(tmp_path)
    assert len(records) == 6  # la ligne invalide est sautée, sans plantage
    assert records[-1].out_of_service


def test_periodes() -> None:
    moments = [BASE + timedelta(minutes=2 * i) for i in range(5)]           # 08:00 -> 08:08
    moments += [BASE + timedelta(hours=3, minutes=2 * i) for i in range(3)]  # 11:00 -> 11:04
    periods = history.find_periods(moments, interval_seconds=120)
    assert [(p.number, p.count) for p in periods] == [(1, 5), (2, 3)]
    assert history.format_duration(periods[0].duration) == "0 h 08"


def test_ecart_juste_sous_le_seuil_reste_dans_la_periode() -> None:
    moments = [BASE, BASE + timedelta(seconds=359)]  # seuil = 3 x 120 s = 360 s
    assert len(history.find_periods(moments, 120)) == 1
    assert len(history.find_periods([BASE, BASE + timedelta(seconds=360)], 120)) == 2


def records_two_periods() -> list[storage.Record]:
    out = []
    for i in range(3):
        m = BASE + timedelta(minutes=2 * i)
        out.append(storage.Record(m, "1", 0 if i == 0 else 4, 6, True, True, True))
        out.append(storage.Record(m, "2", 0, 10, True, True, True))
    m = BASE + timedelta(days=1)
    out.append(storage.Record(m, "1", 2, 8, True, True, True))
    out.append(storage.Record(m, "2", 5, 5, False, False, False))  # hors service : exclu
    return out


def test_requete_par_station_avec_top() -> None:
    result = query.run_query(records_two_periods(), query.Selection(),
                             ["empty_rate", "avg_bikes"], 120, by="station", top=1)
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.key == "2" and row.values["empty_rate"] == 100 and row.count == 3
    assert result.periods_used == [1, 2] and result.interrupted
    assert result.snapshot_count == 4


def test_requete_sur_une_periode() -> None:
    result = query.run_query(records_two_periods(), query.Selection(periods=[1]),
                             ["avg_bikes"], 120, by="station")
    rows = {r.key: r for r in result.rows}
    assert rows["1"].values["avg_bikes"] == pytest.approx(8 / 3)
    assert not result.interrupted


def test_requete_sans_donnees() -> None:
    with pytest.raises(query.NoDataError):
        query.run_query(records_two_periods(), query.Selection(hours=(20, 22)),
                        ["avg_bikes"], 120)
    with pytest.raises(query.NoDataError, match="inconnue"):
        query.run_query(records_two_periods(), query.Selection(periods=[9]), ["avg_bikes"], 120)


def test_lecture_des_options() -> None:
    assert query.parse_days(["weekdays"]) == {0, 1, 2, 3, 4}
    assert query.parse_days(["samedi", "sun"]) == {5, 6}
    assert query.parse_hours("7-9") == (7, 9)
    with pytest.raises(query.VeloError):
        query.parse_hours("9-7")
    with pytest.raises(query.VeloError):
        query.parse_days(["funday"])
    assert query.parse_moment("2026-11-18", end_of_day=True).hour == 23
