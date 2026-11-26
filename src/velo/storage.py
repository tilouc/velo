"""L'historique : écrire les relevés dans des fichiers CSV, puis les relire.

Pourquoi ? V'Lille ne donne que l'état d'AUJOURD'HUI, MAINTENANT. Pour savoir
si une station est souvent vide le matin, il faut noter soi-même son état,
encore et encore, et garder ces notes. C'est le rôle de velo collect.

Un CSV, c'est un tableau écrit en texte : une ligne par station et par relevé,
les colonnes séparées par des virgules. Un fichier par jour (2026-11-18.csv) :

timestamp,station_id,bikes,docks,is_installed,is_renting,is_returning,last_reported
2026-11-18T08:14:00+01:00,42,3,17,true,true,true,2026-11-18T08:13:41+01:00

Les dates sont au format ISO 8601 avec le décalage horaire (+01:00 en hiver à
Lille). L'énoncé l'impose pour que n'importe quel groupe puisse lire nos fichiers.
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
    """Une ligne du CSV relue : une station, à l'heure d'un relevé."""

    timestamp: datetime
    station_id: str
    bikes: int
    docks: int
    is_installed: bool
    is_renting: bool
    is_returning: bool

    @property
    def out_of_service(self) -> bool:
        """Même définition que dans states.py : il manque une des trois conditions."""
        return not (self.is_installed and self.is_renting and self.is_returning)


def _bool(value: bool) -> str:
    """True -> "true", False -> "false" (le format demandé dans le CSV)."""
    return "true" if value else "false"


def file_for(history_folder: Path, moment: datetime) -> Path:
    """Le fichier du jour d'un relevé. Exemple : relevé du 18/11 -> history/2026-11-18.csv"""
    return history_folder / f"{moment.date().isoformat()}.csv"


def append_snapshot(history_folder: Path, snapshot: Snapshot) -> Path:
    """Ajoute un relevé à la FIN du fichier du jour.

    "a" = append = ajouter à la fin, sans effacer ce qui existe. Si le fichier
    n'existe pas encore, on écrit d'abord la ligne des titres de colonnes.
    Un relevé pris après minuit va tout seul dans le fichier du lendemain,
    puisque le nom du fichier vient de la date du relevé.
    """
    history_folder.mkdir(parents=True, exist_ok=True)
    path = file_for(history_folder, snapshot.last_updated)
    is_new = not path.exists() or path.stat().st_size == 0
    timestamp = snapshot.last_updated.isoformat(timespec="seconds")
    # newline="" : demandé par l'énoncé, évite des lignes vides en trop sous Windows
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
    """Tous les fichiers de l'historique, du plus vieux au plus récent."""
    if not history_folder.exists():
        return []
    return sorted(history_folder.glob("????-??-??.csv"))  # ? = un caractère quelconque


def _parse_bool(text: str) -> bool:
    """"true" -> True, "false" -> False. Autre chose -> erreur."""
    lowered = text.strip().lower()
    if lowered in ("true", "1"):
        return True
    if lowered in ("false", "0"):
        return False
    raise ValueError(f"booléen invalide : {text!r}")


def _parse_row(row: dict[str, str]) -> Record:
    """Transforme une ligne de texte du CSV en Record, en vérifiant chaque colonne."""
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
    """Relit un fichier CSV.

    Une ligne abîmée est sautée et notée dans le journal (avec son numéro de
    ligne). Une seule mauvaise ligne ne doit pas rendre tout l'historique illisible.
    """
    records = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)  # chaque ligne devient {"timestamp": "...", "bikes": "3", ...}
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
    """Relit TOUT l'historique, trié du plus vieux au plus récent."""
    records: list[Record] = []
    for path in history_files(history_folder):
        records.extend(read_file(path))
    records.sort(key=lambda r: r.timestamp)
    return records


def last_timestamp(history_folder: Path) -> datetime | None:
    """L'heure du dernier relevé enregistré (ou None s'il n'y en a aucun).

    Sert à ne pas enregistrer deux fois la même photo du réseau.
    """
    files = history_files(history_folder)
    for path in reversed(files):
        records = read_file(path)
        if records:
            return max(r.timestamp for r in records)
    return None
