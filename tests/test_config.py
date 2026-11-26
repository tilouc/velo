"""Tests de config.py : défauts, validation, messages qui nomment le réglage."""

from pathlib import Path

import pytest

from velo.config import (
    DEFAULT_GBFS_URL,
    DEFAULT_LOW_BIKES,
    load_config,
    parse_config,
    slugify,
    write_default_config,
)
from velo.errors import ConfigError


def test_fichier_vide_donne_les_valeurs_par_defaut() -> None:
    config = parse_config(None)
    assert config.gbfs_url == DEFAULT_GBFS_URL
    assert config.low_bikes == DEFAULT_LOW_BIKES
    assert config.interval_seconds == 120


def test_valeur_du_fichier_remplace_le_defaut() -> None:
    config = parse_config({"alerts": {"low_bikes": 5}})
    assert config.low_bikes == 5
    assert config.low_docks == 2  # absent du fichier : défaut


@pytest.mark.parametrize(
    ("data", "reglage"),
    [
        ({"alerts": {"low_bikes": "banane"}}, "alerts.low_bikes"),
        ({"alerts": {"low_docks": -1}}, "alerts.low_docks"),
        ({"collect": {"interval_seconds": 30}}, "collect.interval_seconds"),
        ({"dashboard": {"refresh_seconds": True}}, "dashboard.refresh_seconds"),
        ({"network": {"gbfs_url": "ftp://x"}}, "network.gbfs_url"),
        ({"logging": {"level": "BAVARD"}}, "logging.level"),
    ],
)
def test_valeur_invalide_nomme_le_reglage(data: dict, reglage: str) -> None:
    with pytest.raises(ConfigError, match=reglage.replace(".", r"\.")):
        parse_config(data)


def test_section_qui_n_est_pas_un_dictionnaire() -> None:
    with pytest.raises(ConfigError, match="alerts"):
        parse_config({"alerts": 3})


def test_fichier_absent(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="velo init"):
        load_config(tmp_path / "absent.yaml")


def test_yaml_mal_forme(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("alerts: [pas fermé", encoding="utf-8")
    with pytest.raises(ConfigError, match="mal formé"):
        load_config(path)


def test_fichier_par_defaut_relisible(tmp_path: Path) -> None:
    path = tmp_path / "sous" / "config.yaml"
    write_default_config(path, data_folder=tmp_path / "données")
    config = load_config(path)
    assert config.network_name == "V'Lille"
    assert config.data_folder == tmp_path / "données"
    assert config.network_folder == tmp_path / "données" / "vlille"


def test_slugify() -> None:
    assert slugify("V'Lille") == "vlille"
    assert slugify("Vélib' Métropole") == "velibmetropole"
