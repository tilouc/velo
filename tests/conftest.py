"""Outils partagés par les tests.

Aucun test ne touche à internet : la fonction gbfs.fetch_json est remplacée
par une fausse version qui lit les petits fichiers JSON de tests/data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from velo import gbfs

DATA = Path(__file__).parent / "data"
GBFS_URL = "https://test.local/gbfs.json"


def load_json(name: str) -> dict:
    """Lit un fichier JSON de tests/data/."""
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@pytest.fixture
def fake_api(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict]:
    """Simule l'API : {adresse: contenu JSON}. Un test peut modifier ce dictionnaire."""
    responses = {
        GBFS_URL: load_json("gbfs.json"),
        **{
            f"https://test.local/{name}.json": load_json(f"{name}.json")
            for name in ("system_information", "station_information", "station_status",
                         "vehicle_types")
        },
    }

    def fake_fetch(url: str) -> dict:
        if url not in responses:
            raise gbfs.NetworkError(f"Réseau injoignable ({url})")
        return responses[url]

    monkeypatch.setattr(gbfs, "fetch_json", fake_fetch)
    return responses


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Un config.yaml qui pointe vers un dossier de données temporaire et la fausse API."""
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""network:
  name: "V'Lille"
  gbfs_url: {GBFS_URL}
data:
  folder: {(tmp_path / "data").as_posix()}
collect:
  interval_seconds: 120
""",
        encoding="utf-8",
    )
    return path
