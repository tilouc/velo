"""Enregistrement et lecture de l'historique au format CSV.

Un fichier par jour (AAAA-MM-JJ.csv), une ligne par station et par relevé :
timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported
Les dates sont en ISO 8601, heure locale avec décalage horaire.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from velo.models import Snapshot

log = logging.getLogger(__name__)

COLUMNS = [
    "timestamp", "station_id", "bikes", "docks",
    "is_installed", "is_renting", "is_returning", "last_reported",
]


@dataclass(frozen=True)
class Record:
    """Une ligne de l'historique : une station dans un relevé."""

    timestamp: datetime
    station_id: str
    bikes: int
    docks: int
    is_installed: bool
    is_renting: bool
    is_returning: bool

    @property
    def out_of_service(self) -> bool:
        """Même définition que states.is_out_of_service."""
        return not (self.is_installed and self.is_renting and self.is_returning)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def file_for(history_folder: Path, moment: datetime) -> Path:
    """Fichier CSV du jour d'un relevé."""
    return history_folder / f"{moment.date().isoformat()}.csv"


def append_snapshot(history_folder: Path, snapshot: Snapshot) -> Path:
    """Ajoute un relevé à la fin du fichier du jour (créé avec son en-tête si besoin)."""
    history_folder.mkdir(parents=True, exist_ok=True)
    path = file_for(history_folder, snapshot.last_updated)
    is_new = not path.exists() or path.stat().st_size == 0
    timestamp = snapshot.last_updated.isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        for s in snapshot.stations:
            writer.writerow([
                timestamp, s.station_id, s.bikes, s.docks,
                _bool(s.is_installed), _bool(s.is_renting), _bool(s.is_returning),
                s.last_reported.isoformat(timespec="seconds"),
            ])
    return path


def history_files(history_folder: Path) -> list[Path]:
    """Les fichiers CSV de l'historique, du plus ancien au plus récent."""
    if not history_folder.exists():
        return []
    return sorted(history_folder.glob("????-??-??.csv"))


def _parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in ("true", "1"):
        return True
    if lowered in ("false", "0"):
        return False
    raise ValueError(f"booléen invalide : {text!r}")


def _parse_row(row: dict[str, str]) -> Record:
    timestamp = datetime.fromisoformat(row["timestamp"])
    if timestamp.tzinfo is None:
        raise ValueError("date sans décalage horaire")
    bikes, docks = int(row["bikes"]), int(row["docks"])
    if bikes < 0 or docks < 0:
        raise ValueError("nombre négatif")
    if not row["station_id"]:
        raise ValueError("identifiant vide")
    return Record(
        timestamp=timestamp,
        station_id=row["station_id"],
        bikes=bikes,
        docks=docks,
        is_installed=_parse_bool(row["is_installed"]),
        is_renting=_parse_bool(row["is_renting"]),
        is_returning=_parse_bool(row["is_returning"]),
    )


def read_file(path: Path) -> list[Record]:
    """Lit un fichier CSV. Les lignes invalides sont ignorées et journalisées."""
    records = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            log.warning("%s ignoré : colonnes manquantes %s", path.name, sorted(missing))
            return []
        for line_number, row in enumerate(reader, start=2):
            try:
                records.append(_parse_row(row))
            except (ValueError, TypeError, KeyError) as exc:
                log.warning("%s ligne %d ignorée : %s", path.name, line_number, exc)
    return records


def read_history(history_folder: Path) -> list[Record]:
    """Lit tout l'historique, trié par date."""
    records: list[Record] = []
    for path in history_files(history_folder):
        records.extend(read_file(path))
    records.sort(key=lambda r: r.timestamp)
    return records


def last_timestamp(history_folder: Path) -> datetime | None:
    """Date du dernier relevé enregistré (pour ne pas l'enregistrer deux fois)."""
    files = history_files(history_folder)
    for path in reversed(files):
        records = read_file(path)
        if records:
            return max(r.timestamp for r in records)
    return None
