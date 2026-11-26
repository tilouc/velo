"""Le journal de bord (le module logging).

print() affiche un message et c'est tout. logging, c'est mieux :
- chaque message a un niveau : DEBUG (détail), INFO (normal), WARNING
  (attention), ERROR (raté) ;
- un même message peut partir à deux endroits : l'écran ET un fichier velo.log ;
- on choisit ce qu'on voit à l'écran avec logging.level dans config.yaml.

Ici : l'écran montre les messages à partir du niveau choisi (INFO par défaut),
et le fichier velo.log garde TOUT, avec la date, pour comprendre après coup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler

from velo.display import error_console

LOG_FILE_NAME = "velo.log"


class _NotAlreadyShown(logging.Filter):
    """Empêche d'afficher deux fois la même erreur à l'écran.

    Quand cli.py affiche déjà « Erreur : ... », il marque le message shown=True
    pour qu'il aille seulement dans le fichier, pas une deuxième fois à l'écran.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not getattr(record, "shown", False)


def setup_console(level: str = "INFO") -> None:
    """Branche la sortie « écran » du journal."""
    root = logging.getLogger("velo")
    root.setLevel(logging.DEBUG)  # on laisse tout passer, chaque sortie filtre à son niveau
    for handler in list(root.handlers):
        root.removeHandler(handler)
    console = RichHandler(console=error_console, show_time=False, show_path=False)
    console.setLevel(level)
    console.addFilter(_NotAlreadyShown())
    root.addHandler(console)


def set_console_level(level: str) -> None:
    """Change le niveau affiché à l'écran (celui lu dans config.yaml)."""
    for handler in logging.getLogger("velo").handlers:
        if isinstance(handler, RichHandler):
            handler.setLevel(level)


def add_file(folder: Path) -> Path | None:
    """Branche la sortie « fichier » du journal : <folder>/velo.log, tous niveaux, avec la date."""
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
    """Ferme proprement le fichier de log à la fin de la commande."""
    root = logging.getLogger("velo")
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.close()
            root.removeHandler(handler)
