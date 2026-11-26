"""Une fonction par commande. C'est le chef d'orchestre : il ne fait rien lui-même,
il demande aux autres fichiers, dans l'ordre.

Toutes les commandes suivent le même trajet :
  1. les réglages      -> config.py
  2. les données       -> gbfs.py (internet) ou storage.py (historique)
  3. les calculs       -> states.py, search.py, history.py, query.py
  4. l'affichage       -> display.py

Chaque fonction renvoie un code de sortie : 0 = tout s'est bien passé.
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Group
from rich.live import Live

from velo import display, favorites, gbfs, history, query, search, states, storage
from velo.config import (
    MIN_DASHBOARD_REFRESH,
    MIN_INTERVAL_SECONDS,
    Config,
    default_config_path,
    load_config,
    write_default_config,
)
from velo.errors import NetworkError, VeloError
from velo.models import Snapshot

log = logging.getLogger(__name__)


def pick(option: int | None, configured: int) -> int:
    """La règle de priorité, en une ligne : l'option tapée gagne, sinon config.yaml.

    Exemple : velo alerts --low-bikes 5 -> option = 5 -> on prend 5.
              velo alerts               -> option = None -> on prend config.low_bikes.
    (config.low_bikes contient déjà la valeur par défaut si config.yaml ne disait rien.)
    """
    return configured if option is None else option


def check_minimum(value: int, minimum: int, option: str) -> int:
    """Refuse une option trop petite. Exemple : --interval 10 alors que le minimum est 60."""
    if value < minimum:
        raise VeloError(f"{option} doit valoir au moins {minimum} secondes.")
    return value


def warn_if_static_files_old(config: Config) -> None:
    """Prévient si les infos sur les stations manquent ou datent de plus de max_age_days jours."""
    date = gbfs.static_files_date(config.network_folder)
    if date is None:
        display.print_warning("fichiers du réseau absents. Lancez : velo refresh")
    elif datetime.now().astimezone() - date > timedelta(days=config.max_age_days):
        days = (datetime.now().astimezone() - date).days
        display.print_warning(
            f"les informations sur les stations datent de {days} jours. Lancez : velo refresh"
        )


# --- velo init ------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Prépare tout au premier lancement : la config, les dossiers, puis un test de connexion.

    Si internet ne marche pas, la config et les dossiers sont quand même créés :
    on affiche juste un avertissement.
    """
    config_path: Path = args.config or default_config_path()
    if config_path.exists() and not args.force:
        display.console.print(
            f"Configuration déjà présente : {config_path} (non écrasée, utilisez --force)"
        )
    else:
        write_default_config(config_path)
        display.console.print(f"Configuration créée : {config_path}")
        log.debug("Configuration créée : %s", config_path)

    config = load_config(config_path)
    config.history_folder.mkdir(parents=True, exist_ok=True)
    display.console.print(f"Dossier de données créé : {config.network_folder}")

    try:
        gbfs.download_static_files(config.gbfs_url, config.network_folder)
        count = len(gbfs.load_stations(config.network_folder))
    except VeloError as exc:
        log.warning("Connexion impossible pendant init : %s", exc)
        display.print_warning(
            f"connexion à {config.network_name} impossible ({exc}). "
            "La configuration est prête : relancez plus tard velo refresh."
        )
        return 0
    display.console.print(f"Connexion à {config.network_name} : OK ({count} stations)")
    return 0


# --- velo refresh ----------------------------------------------------------------------


def cmd_refresh(args: argparse.Namespace, config: Config) -> int:
    """Retélécharge les trois fichiers qui changent rarement (stations, réseau, types de vélos)."""
    gbfs.download_static_files(config.gbfs_url, config.network_folder)
    count = len(gbfs.load_stations(config.network_folder))
    moment = datetime.now().astimezone()
    log.info("Fichiers du réseau mis à jour (%d stations)", count)
    display.console.print(
        f"{config.network_name} - mise à jour du {display.format_moment(moment)} : {count} stations"
    )
    return 0


# --- velo status ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace, config: Config) -> int:
    """Le résumé du réseau, en direct : télécharger -> compter -> afficher."""
    warn_if_static_files_old(config)
    snapshot = gbfs.fetch_snapshot(config.gbfs_url)  # 2. les données
    summary = states.summarize(snapshot)  # 3. le calcul
    display.console.print(  # 4. l'affichage
        display.render_status(config.network_name, snapshot.last_updated, summary)
    )
    return 0


# --- velo station ----------------------------------------------------------------------------


def cmd_station(args: argparse.Namespace, config: Config) -> int:
    """Trois actions : list (toutes les stations), search (chercher), show (une station en direct)."""
    stations = gbfs.load_stations(config.network_folder)
    warn_if_static_files_old(config)

    if args.station_command == "list":
        ordered = sorted(stations.values(), key=lambda s: search.sort_key(s.station_id))
        display.console.print(display.render_station_list(ordered))
        return 0

    if args.station_command == "search":
        found = search.search_stations(stations, args.text)
        if not found:
            raise VeloError(f"Aucune station ne correspond à « {args.text} ».")
        display.console.print(display.render_station_list(found))
        return 0

    # velo station show <id>
    if args.id not in stations:
        raise VeloError(f"Station {args.id} inconnue. Cherchez-la avec : velo station search")
    snapshot = gbfs.fetch_snapshot(config.gbfs_url)
    status = states.status_by_id(snapshot).get(args.id)
    label = states.state_label(status, config.low_bikes, config.low_docks) if status else ""
    display.console.print(display.render_station_detail(stations[args.id], status, label))
    return 0


# --- velo favorites ---------------------------------------------------------------------------


def cmd_favorites(args: argparse.Namespace, config: Config) -> int:
    """Sans action : affiche l'état des favoris. Avec add / remove : modifie la liste."""
    folder = config.network_folder
    if args.favorites_command == "add":
        info = favorites.add_favorite(folder, args.id, gbfs.load_stations(folder))
        display.console.print(f"Favori ajouté : {info.station_id} {info.name}")
        return 0
    if args.favorites_command == "remove":
        favorites.remove_favorite(folder, args.id)
        display.console.print(f"Favori retiré : {args.id}")
        return 0

    ids = favorites.load_favorites(folder)
    if not ids:
        display.console.print(display.render_no_favorites())
        return 0
    stations = gbfs.load_stations(folder)
    snapshot = gbfs.fetch_snapshot(config.gbfs_url)
    rows = states.favorite_rows(ids, snapshot, stations, config.low_bikes, config.low_docks)
    display.console.print(display.render_favorites(rows))
    return 0


# --- velo alerts -------------------------------------------------------------------------------


def cmd_alerts(args: argparse.Namespace, config: Config) -> int:
    """Les stations à problème. Les seuils viennent de l'option, sinon de config.yaml."""
    low_bikes = pick(args.low_bikes, config.low_bikes)
    low_docks = pick(args.low_docks, config.low_docks)
    stations = gbfs.load_stations(config.network_folder)
    warn_if_static_files_old(config)
    snapshot = gbfs.fetch_snapshot(config.gbfs_url)
    alerts = states.compute_alerts(snapshot, stations, low_bikes, low_docks)
    moment = display.format_moment(snapshot.last_updated)
    display.console.print(f"[bold]{config.network_name} - alertes du {moment}[/]")
    display.console.print(display.render_alerts(alerts))
    return 0


# --- velo dashboard -----------------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace, config: Config) -> int:
    """Un écran qui se met à jour tout seul. Ctrl+C pour quitter.

    Le principe : une boucle sans fin. Chaque seconde, on redessine l'écran avec
    le compte à rebours. Quand il arrive à 0, on retélécharge les données.
    Si internet coupe, on garde les dernières données et on affiche un avertissement.
    """
    refresh = check_minimum(pick(args.refresh, config.dashboard_refresh),
                            MIN_DASHBOARD_REFRESH, "--refresh")
    low_bikes = pick(args.low_bikes, config.low_bikes)
    low_docks = pick(args.low_docks, config.low_docks)
    stations = gbfs.load_stations(config.network_folder)

    current: Snapshot = gbfs.fetch_snapshot(config.gbfs_url)  # sans premières données, rien à montrer
    previous: Snapshot | None = None  # le relevé d'avant, pour calculer l'évolution des favoris
    error: str | None = None

    def screen(seconds_left: int) -> Group:
        """Construit l'écran avec les mêmes calculs que status, favorites et alerts."""
        ids = favorites.load_favorites(config.network_folder)
        return display.render_dashboard(
            config.network_name,
            current.last_updated,
            seconds_left,
            states.summarize(current),
            states.favorite_rows(ids, current, stations, low_bikes, low_docks, previous),
            states.compute_alerts(current, stations, low_bikes, low_docks),
            error,
        )

    try:
        # Live = un écran que Rich redessine sur place, au lieu d'écrire en dessous.
        with Live(screen(refresh), console=display.console, auto_refresh=False,
                  redirect_stderr=True, screen=False) as live:
            while True:
                for seconds_left in range(refresh, 0, -1):  # 60, 59, ..., 1
                    live.update(screen(seconds_left), refresh=True)
                    time.sleep(1)
                try:
                    new = gbfs.fetch_snapshot(config.gbfs_url)
                except NetworkError as exc:
                    log.warning("Tableau de bord : %s", exc)
                    error = str(exc)  # on garde les anciennes données, on prévient
                else:
                    if new.last_updated != current.last_updated:
                        previous, current = current, new
                    error = None
    except KeyboardInterrupt:  # Ctrl+C lève KeyboardInterrupt : on sort proprement
        display.console.print("Tableau de bord fermé.")
    return 0


# --- velo collect --------------------------------------------------------------------------------

# Accepte "3h", "90m", "90min", "1h30", "45s", "2h30m"...
_DURATION = re.compile(r"^(?:(?P<h>\d+)h)?(?:(?P<m>\d+)(?:m|min)?)?(?:(?P<s>\d+)s)?$")


def parse_duration(text: str) -> timedelta:
    """Transforme une durée tapée en vraie durée. Exemples : "3h", "90m", "1h30", "45s"."""
    match = _DURATION.match(text.strip().lower())
    if not text.strip() or not match or not any(match.groupdict().values()):
        raise VeloError(f"Durée invalide : « {text} » (exemples : 3h, 90m, 1h30, 45s).")
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    duration = timedelta(hours=parts["h"], minutes=parts["m"], seconds=parts["s"])
    if duration.total_seconds() <= 0:
        raise VeloError("La durée doit être positive.")
    return duration


def parse_until(text: str) -> datetime:
    """"2026-11-20 10:00" -> un moment précis. Il doit être dans le futur."""
    try:
        moment = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M").astimezone()
    except ValueError as exc:
        raise VeloError(f"Date invalide : « {text} » (format : \"AAAA-MM-JJ HH:MM\").") from exc
    if moment <= datetime.now().astimezone():
        raise VeloError(f"La date de fin {text} est déjà passée.")
    return moment


def cmd_collect(args: argparse.Namespace, config: Config) -> int:
    """Prend une photo du réseau toutes les X secondes et l'écrit dans l'historique.

    La boucle, en clair :
      1. télécharger l'état des stations ;
      2. si c'est la même photo que la dernière (même last_updated), ne rien écrire ;
         sinon, l'ajouter au CSV du jour ;
      3. s'il est l'heure d'arrêter (--duration, --until, --once), sortir ;
      4. sinon, attendre l'intervalle, puis recommencer.
    Une coupure internet ne stoppe pas la collecte : on note l'erreur et on réessaie.
    À la fin, même après Ctrl+C, on affiche un bilan (le bloc finally s'exécute toujours).
    """
    interval = check_minimum(pick(args.interval, config.interval_seconds),
                             MIN_INTERVAL_SECONDS, "--interval")
    end: datetime | None = None  # None = pas d'heure de fin, on tourne jusqu'à Ctrl+C
    if args.duration:
        end = datetime.now().astimezone() + parse_duration(args.duration)
    elif args.until:
        end = parse_until(args.until)

    folder = config.history_folder
    previous = storage.last_timestamp(folder)
    count, first, last = 0, None, None

    if not args.once:
        stop = f"jusqu'au {display.format_moment(end)}" if end else "jusqu'à Ctrl+C"
        display.console.print(f"Collecte {config.network_name} toutes les {interval} s, {stop}.")
    try:
        while True:
            try:
                snapshot = gbfs.fetch_snapshot(config.gbfs_url)
            except NetworkError as exc:
                if args.once:  # avec --once, pas de deuxième chance : c'est une erreur
                    raise
                log.error("%s - nouvel essai dans %d s", exc, interval)
            else:
                if previous is not None and snapshot.last_updated == previous:
                    log.info("Relevé de %s identique au précédent : non enregistré",
                             snapshot.last_updated.strftime("%H:%M:%S"))
                else:
                    path = storage.append_snapshot(folder, snapshot)
                    previous = last = snapshot.last_updated
                    first = first or snapshot.last_updated
                    count += 1
                    log.info("Relevé %d enregistré (%s, %d stations) dans %s", count,
                             snapshot.last_updated.strftime("%H:%M:%S"),
                             len(snapshot.stations), path.name)
            if args.once:
                break
            wait = float(interval)
            if end is not None:
                remaining = (end - datetime.now().astimezone()).total_seconds()
                if remaining <= 0:
                    break
                wait = min(wait, remaining)  # ne pas attendre au-delà de l'heure de fin
            time.sleep(wait)
            if end is not None and datetime.now().astimezone() >= end:
                break
    except KeyboardInterrupt:
        display.console.print("\nCollecte interrompue.")
    finally:
        if first and last:
            display.console.print(
                f"Bilan : {count} relevé{'s' if count > 1 else ''}, "
                f"du {display.format_short(first)} au {display.format_short(last)}."
            )
        else:
            display.console.print("Bilan : aucun relevé enregistré.")
    return 0


# --- velo history -----------------------------------------------------------------------------


def _all_periods(config: Config, interval: int) -> tuple[list[storage.Record], list[history.Period]]:
    """Relit tout l'historique et le découpe en périodes."""
    records = storage.read_history(config.history_folder)
    return records, history.find_periods([r.timestamp for r in records], interval)


def cmd_history(args: argparse.Namespace, config: Config) -> int:
    """Affiche les périodes collectées. --from / --to filtrent l'affichage.

    On découpe TOUT l'historique d'abord, puis on filtre : ainsi la période 2 garde
    toujours le numéro 2, ici comme dans velo query --period 2.
    """
    interval = pick(args.interval, config.interval_seconds)
    _, periods = _all_periods(config, interval)
    start = query.parse_moment(args.date_from) if args.date_from else None
    end = query.parse_moment(args.date_to, end_of_day=True) if args.date_to else None
    shown = [p for p in periods
             if (start is None or p.end >= start) and (end is None or p.start <= end)]
    if not shown:
        display.console.print(
            "Aucun historique" + (" sur ces dates" if periods else "")
            + ". Lancez une collecte avec : velo collect"
        )
        return 0
    display.console.print(display.render_history(config.network_name, shown))
    return 0


# --- velo query ---------------------------------------------------------------------------------


def cmd_query(args: argparse.Namespace, config: Config) -> int:
    """Analyse l'historique : on transforme les options en filtres, puis query.py calcule.

    S'il n'y a aucune donnée pour ces filtres, on le dit et on montre les périodes
    disponibles, pour que l'utilisateur sache quoi demander.
    """
    interval = pick(args.interval, config.interval_seconds)
    selection = query.Selection(
        day=query.parse_day(args.date) if args.date else None,
        start=query.parse_moment(args.date_from) if args.date_from else None,
        end=query.parse_moment(args.date_to, end_of_day=True) if args.date_to else None,
        periods=args.period or [],
        days=query.parse_days(args.days) if args.days else set(),
        hours=query.parse_hours(args.hours) if args.hours else None,
        station=args.station,
    )
    records, periods = _all_periods(config, interval)
    if not records:
        raise VeloError("Aucun historique enregistré. Lancez une collecte avec : velo collect")
    try:
        result = query.run_query(records, selection, args.metric, interval, args.by, args.top)
    except query.NoDataError as exc:
        display.print_error(str(exc))
        display.console.print("Périodes disponibles :")
        display.console.print(display.render_history(config.network_name, periods))
        return 1

    stations = {}
    if args.by == "station":
        try:
            stations = gbfs.load_stations(config.network_folder)
        except VeloError:
            stations = {}  # sans les noms, on affiche seulement les numéros
    if result.interrupted:
        display.print_warning("la sélection comporte des interruptions.")
    display.console.print(display.render_query(result, args.metric, args.by, stations))
    return 0
