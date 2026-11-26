"""Tests de bout en bout : on appelle main() comme si on tapait la commande."""

from pathlib import Path

import pytest

from tests.conftest import GBFS_URL
from velo import cli, commands
from velo.config import load_config


def velo(config_path: Path, *args: str) -> int:
    return cli.main(["--config", str(config_path), *args])


def test_parser_sans_commande() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])


def test_init_puis_status(fake_api: dict, config_path: Path, capsys) -> None:
    assert velo(config_path, "init") == 0
    out = capsys.readouterr().out
    assert "non écrasée" in out and "OK (6 stations)" in out
    assert velo(config_path, "status") == 0
    out = capsys.readouterr().out
    assert "en service 4 / 5" in out and "taux de remplissage 37 %" in out


def test_init_cree_la_config(fake_api: dict, tmp_path: Path, monkeypatch, capsys) -> None:
    path = tmp_path / "neuve" / "config.yaml"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert cli.main(["--config", str(path), "init"]) == 0
    assert path.exists()
    assert "Configuration créée" in capsys.readouterr().out


def test_init_sans_reseau_avertit_mais_cree_tout(fake_api: dict, config_path: Path, capsys) -> None:
    fake_api.clear()
    assert velo(config_path, "init") == 0
    assert "Avertissement" in capsys.readouterr().err
    assert load_config(config_path).history_folder.exists()


def test_erreur_sans_config(tmp_path: Path, capsys) -> None:
    assert velo(tmp_path / "absente.yaml", "status") == 1
    err = capsys.readouterr().err
    assert "velo init" in err and "Traceback" not in err


def test_erreur_reseau(fake_api: dict, config_path: Path, capsys) -> None:
    fake_api.pop(GBFS_URL)
    assert velo(config_path, "status") == 1
    assert "injoignable" in capsys.readouterr().err


def test_station_et_favoris(fake_api: dict, config_path: Path, capsys) -> None:
    velo(config_path, "refresh")
    assert velo(config_path, "station", "search", "gare") == 0
    out = capsys.readouterr().out
    assert "Gare Lille Flandres" in out and "Gare Lille Europe" in out
    assert velo(config_path, "station", "show", "3") == 0
    assert "pleine" in capsys.readouterr().out

    assert velo(config_path, "favorites") == 0
    assert "Aucun favori" in capsys.readouterr().out
    assert velo(config_path, "favorites", "add", "1") == 0
    assert velo(config_path, "favorites", "add", "1") == 1  # déjà en favori
    capsys.readouterr()
    assert velo(config_path, "favorites") == 0
    assert "vide" in capsys.readouterr().out
    assert velo(config_path, "favorites", "remove", "404") == 1


def test_alertes_option_remplace_la_config(fake_api: dict, config_path: Path, capsys) -> None:
    velo(config_path, "refresh")
    capsys.readouterr()
    assert velo(config_path, "alerts") == 0
    assert "Vauban" not in capsys.readouterr().out
    assert velo(config_path, "alerts", "--low-bikes", "8") == 0
    assert "Vauban" in capsys.readouterr().out


def test_collect_history_query(fake_api: dict, config_path: Path, monkeypatch, capsys) -> None:
    velo(config_path, "refresh")
    assert velo(config_path, "collect", "--once") == 0
    assert velo(config_path, "collect", "--once") == 0  # même last_updated : pas de doublon
    out = capsys.readouterr().out
    assert "Bilan : 1 relevé" in out and "aucun relevé" in out

    assert velo(config_path, "history") == 0
    assert "1 période, 1 relevé" in capsys.readouterr().out

    assert velo(config_path, "query", "--metric", "empty_rate", "--by", "station", "--top", "1") == 0
    out = capsys.readouterr().out
    assert "1 Gare Lille Flandres" in out and "100 %" in out


def test_query_sans_donnees_affiche_les_periodes(fake_api: dict, config_path: Path, capsys) -> None:
    velo(config_path, "collect", "--once")
    capsys.readouterr()
    assert velo(config_path, "query", "--metric", "avg_bikes", "--date", "2000-01-01") == 1
    captured = capsys.readouterr()
    assert "Aucune donnée" in captured.err and "Périodes disponibles" in captured.out


def test_collect_avec_duree_et_erreur_reseau(fake_api: dict, config_path: Path, monkeypatch,
                                             capsys) -> None:
    calls = []

    def fake_sleep(seconds: float) -> None:
        calls.append(seconds)
        fake_api.clear()  # après le premier relevé, le réseau tombe
        raise KeyboardInterrupt  # simule Ctrl+C pour terminer le test

    monkeypatch.setattr(commands.time, "sleep", fake_sleep)
    assert velo(config_path, "collect", "--interval", "60", "--duration", "1h") == 0
    out = capsys.readouterr().out
    assert calls == [60.0] and "interrompue" in out and "Bilan : 1 relevé" in out


def test_options_invalides(config_path: Path, fake_api: dict, capsys) -> None:
    assert velo(config_path, "collect", "--interval", "10", "--once") == 1
    assert "au moins 60" in capsys.readouterr().err
    assert velo(config_path, "collect", "--duration", "trois heures") == 1
    with pytest.raises(SystemExit):
        velo(config_path, "alerts", "--low-bikes", "-1")


def test_duree() -> None:
    assert commands.parse_duration("3h").total_seconds() == 3 * 3600
    assert commands.parse_duration("1h30").total_seconds() == 5400
    assert commands.parse_duration("90m").total_seconds() == 5400


def test_dashboard_conserve_les_donnees_si_le_reseau_tombe(fake_api: dict, config_path: Path,
                                                         monkeypatch, capsys) -> None:
    velo(config_path, "refresh")
    velo(config_path, "favorites", "add", "5")
    ticks = []

    def fake_sleep(seconds: float) -> None:
        ticks.append(seconds)
        if len(ticks) == 60:
            fake_api.clear()  # le réseau tombe juste avant la mise à jour
        if len(ticks) == 62:
            raise KeyboardInterrupt

    monkeypatch.setattr(commands.time, "sleep", fake_sleep)
    assert velo(config_path, "dashboard") == 0
    out = capsys.readouterr().out
    assert "Vauban" in out and "Réseau indisponible" in out and "fermé" in out


def test_dashboard_refresh_minimum(fake_api: dict, config_path: Path, capsys) -> None:
    velo(config_path, "refresh")
    assert velo(config_path, "dashboard", "--refresh", "10") == 1
    assert "au moins 60" in capsys.readouterr().err
