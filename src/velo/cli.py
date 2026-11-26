"""Point d'entrée de la commande `velo`.

Ce module fait trois choses, et rien d'autre :
1. décrire les commandes et leurs options (build_parser) ;
2. lire ce que l'utilisateur a tapé et charger la configuration ;
3. aiguiller vers la bonne fonction de commands.py, et transformer toute
   erreur en message clair avec un code de sortie non nul.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from pathlib import Path

from velo import commands, display, logs
from velo.config import Config, default_config_path, load_config
from velo.errors import VeloError
from velo.query import GROUPS, METRICS

log = logging.getLogger(__name__)


def positive_int(text: str) -> int:
    """Type argparse : entier strictement positif."""
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"« {text} » n'est pas un nombre entier") from exc
    if value <= 0:
        raise argparse.ArgumentTypeError(f"{value} doit être strictement positif")
    return value


def non_negative_int(text: str) -> int:
    """Type argparse : entier positif ou nul."""
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"« {text} » n'est pas un nombre entier") from exc
    if value < 0:
        raise argparse.ArgumentTypeError(f"{value} ne peut pas être négatif")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Décrit toutes les commandes et leurs options (le « formulaire »)."""
    parser = argparse.ArgumentParser(
        prog="velo",
        description="Consulter et analyser le réseau de vélos en libre-service V'Lille.",
    )
    parser.add_argument("--config", type=Path, default=None,
                        help="chemin du fichier config.yaml (par défaut : dossier de config)")
    commands_ = parser.add_subparsers(dest="command", required=True, metavar="COMMANDE")

    # velo init
    init = commands_.add_parser("init", help="prépare l'outil (configuration, dossiers)")
    init.add_argument("--force", action="store_true", help="écrase la configuration existante")

    # velo refresh
    commands_.add_parser("refresh", help="met à jour les données qui changent rarement")

    # velo status
    commands_.add_parser("status", help="résumé de l'état du réseau en temps réel")

    # velo station list | search <texte> | show <id>
    station = commands_.add_parser("station", help="lister, chercher ou consulter une station")
    station_sub = station.add_subparsers(dest="station_command", required=True, metavar="ACTION")
    station_sub.add_parser("list", help="liste toutes les stations")
    station_search = station_sub.add_parser("search", help="cherche une station par son nom")
    station_search.add_argument("text", help="texte à chercher dans le nom")
    station_show = station_sub.add_parser("show", help="état en temps réel d'une station")
    station_show.add_argument("id", help="identifiant de la station")

    # velo favorites [add <id> | remove <id>]
    fav = commands_.add_parser("favorites", help="afficher, ajouter et retirer des favoris")
    fav_sub = fav.add_subparsers(dest="favorites_command", metavar="ACTION")
    fav_add = fav_sub.add_parser("add", help="ajoute une station aux favoris")
    fav_add.add_argument("id", help="identifiant de la station")
    fav_remove = fav_sub.add_parser("remove", help="retire une station des favoris")
    fav_remove.add_argument("id", help="identifiant de la station")

    # velo alerts
    alerts = commands_.add_parser("alerts", help="stations vides, pleines ou hors service")
    alerts.add_argument("--low-bikes", type=non_negative_int, metavar="N",
                        help="seuil « presque vide » (remplace la configuration)")
    alerts.add_argument("--low-docks", type=non_negative_int, metavar="N",
                        help="seuil « presque pleine » (remplace la configuration)")

    # velo dashboard
    dash = commands_.add_parser("dashboard", help="tableau de bord mis à jour en continu")
    dash.add_argument("--refresh", type=positive_int, metavar="SECONDES",
                      help="intervalle de mise à jour (minimum 60)")
    dash.add_argument("--low-bikes", type=non_negative_int, metavar="N")
    dash.add_argument("--low-docks", type=non_negative_int, metavar="N")

    # velo collect
    collect = commands_.add_parser("collect", help="enregistre l'état du réseau régulièrement")
    collect.add_argument("--interval", type=positive_int, metavar="SECONDES",
                         help="secondes entre deux relevés (minimum 60)")
    stop = collect.add_mutually_exclusive_group()
    stop.add_argument("--duration", metavar="DUREE", help="arrêt après une durée (ex. 3h, 90m)")
    stop.add_argument("--until", metavar='"AAAA-MM-JJ HH:MM"', help="arrêt à une date et heure")
    stop.add_argument("--once", action="store_true", help="un seul relevé, puis arrêt")

    # velo history
    hist = commands_.add_parser("history", help="périodes et relevés enregistrés")
    hist.add_argument("--from", dest="date_from", metavar="AAAA-MM-JJ")
    hist.add_argument("--to", dest="date_to", metavar="AAAA-MM-JJ")
    hist.add_argument("--interval", type=positive_int, metavar="SECONDES",
                      help="intervalle de collecte utilisé pour détecter les interruptions")

    # velo query
    q = commands_.add_parser("query", help="analyse l'historique enregistré")
    q.add_argument("--metric", nargs="+", choices=METRICS, required=True, metavar="METRIQUE",
                   help=f"une ou plusieurs métriques parmi : {', '.join(METRICS)}")
    q.add_argument("--date", metavar="AAAA-MM-JJ", help="un seul jour")
    q.add_argument("--from", dest="date_from", metavar='"AAAA-MM-JJ[ HH:MM]"')
    q.add_argument("--to", dest="date_to", metavar='"AAAA-MM-JJ[ HH:MM]"')
    q.add_argument("--period", nargs="+", type=positive_int, metavar="N",
                   help="numéros de période (voir velo history)")
    q.add_argument("--days", nargs="+", metavar="JOURS",
                   help="weekdays, weekend ou une liste de jours (lundi mardi... / mon tue...)")
    q.add_argument("--hours", metavar="DEBUT-FIN", help="plage horaire, par exemple 7-9")
    q.add_argument("--station", metavar="ID", help="une seule station")
    q.add_argument("--by", choices=GROUPS, help="regroupement des résultats")
    q.add_argument("--top", type=positive_int, metavar="N", help="n'affiche que les N premiers")
    q.add_argument("--interval", type=positive_int, metavar="SECONDES", help=argparse.SUPPRESS)

    return parser


# Aiguillage : nom de la commande -> fonction à appeler.
HANDLERS: dict[str, Callable[[argparse.Namespace, Config], int]] = {
    "refresh": commands.cmd_refresh,
    "status": commands.cmd_status,
    "station": commands.cmd_station,
    "favorites": commands.cmd_favorites,
    "alerts": commands.cmd_alerts,
    "dashboard": commands.cmd_dashboard,
    "collect": commands.cmd_collect,
    "history": commands.cmd_history,
    "query": commands.cmd_query,
}


def run(args: argparse.Namespace) -> int:
    """Charge la configuration puis lance la commande demandée."""
    if args.command == "init":
        return commands.cmd_init(args)
    config = load_config(args.config or default_config_path())
    logs.set_console_level(config.log_level)
    logs.add_file(config.data_folder)
    log.debug("Commande : %s", vars(args))
    return HANDLERS[args.command](args, config)


def main(argv: list[str] | None = None) -> int:
    """Fonction appelée par la commande `velo` (voir [project.scripts] dans pyproject.toml)."""
    args = build_parser().parse_args(argv)
    logs.setup_console()
    try:
        return run(args)
    except VeloError as exc:
        log.error("%s", exc, extra={"shown": True})  # dans le fichier de log seulement
        display.print_error(str(exc))
        return 1
    except KeyboardInterrupt:
        display.print_error("interrompu.")
        return 130
    except Exception as exc:  # filet de sécurité : jamais de trace brute à l'écran
        log.debug("Erreur inattendue", exc_info=True)
        log.error("Erreur inattendue : %r", exc, extra={"shown": True})
        display.print_error(f"erreur inattendue ({exc.__class__.__name__}). Détails dans velo.log.")
        return 1
    finally:
        logs.close_files()
