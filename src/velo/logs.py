"""Configuration du module logging : messages de suivi vers la console et vers un fichier."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

from velo.display import error_console

LOG_FILE_NAME = "velo.log"


class _NotAlreadyShown(logging.Filter):
    """Évite d'afficher deux fois une erreur déjà montrée à l'utilisateur par la CLI."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "shown", False)


def setup_console(level: str = "INFO") -> None:
    """Active les messages de suivi dans le terminal (sur la sortie d'erreur)."""
    root = logging.getLogger("velo")
    root.setLevel(logging.DEBUG)  # chaque handler filtre ensuite selon son propre niveau
    for handler in list(root.handlers):
        root.removeHandler(handler)
    console = RichHandler(console=error_console, show_time=False, show_path=False)
    console.setLevel(level)
    console.addFilter(_NotAlreadyShown())
    root.addHandler(console)


def set_console_level(level: str) -> None:
    """Change le niveau des messages affichés dans le terminal."""
    for handler in logging.getLogger("velo").handlers:
        if isinstance(handler, RichHandler):
            handler.setLevel(level)


def add_file(folder: Path) -> Path | None:
    """Ajoute le fichier de log <folder>/velo.log (tous les niveaux, avec la date)."""
    path = folder / LOG_FILE_NAME
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
    except OSError as exc:
        logging.getLogger(__name__).warning("Fichier de log impossible à créer (%s) : %s", path, exc)
        return None
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s : %(message)s"))
    logging.getLogger("velo").addHandler(handler)
    return path


def close_files() -> None:
    """Ferme les fichiers de log (utile dans les tests)."""
    root = logging.getLogger("velo")
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root.removeHandler(handler)
