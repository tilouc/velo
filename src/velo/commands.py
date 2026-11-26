"""Une fonction par commande : elle relie les modules entre eux.

Chaque commande suit le même trajet :
réglages (config) -> données (gbfs / storage) -> calculs (states / history / query)
-> affichage (display). Elle renvoie le code de sortie (0 = tout va bien).
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
    """Règle de priorité : l'option de la commande, sinon la valeur de config.yaml
    (qui contient déjà la valeur par défaut du code si le réglage était absent)."""
    return configured if option is None else option


def check_minimum(value: int, minimum: int, option: str) -> int:
    """Refuse une option inférieure au minimum autorisé."""
    if value < minimum:
        raise VeloError(f"{option} doit valoir au moins {minimum} secondes.")
    return value


def warn_if_static_files_old(config: Config) -> None:
    """Avertit si les fichiers qui changent rarement sont absents ou trop vieux."""
    date = gbfs.static_files_date(config.network_folder)
    if date is None:
        display.print_warning("fichiers du réseau absents. Lancez : velo refresh")
    elif datetime.now().astimezone() - date > timedelta(days=config.max_age_days):
        days = (datetime.now().astimezone() - date).days
        display.print_warning(
            f"les informations sur les stations datent de {days} jours. Lancez : velo refresh"
        )


# --- velo init ------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Crée la configuration et les dossiers, puis teste la connexion."""
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


# --- velo refresh ----------------------------------------------------------------


def cmd_refresh(args: argparse.Namespace, config: Config) -> int:
    """Retélécharge les trois fichiers qui changent rarement."""
    gbfs.download_static_files(config.gbfs_url, config.network_folder)
    count = len(gbfs.load_stations(config.network_folder))
    moment = datetime.now().astimezone()
    log.info("Fichiers du réseau mis à jour (%d stations)", count)
    display.console.print(
        f"{config.network_name} - mise à jour du {display.format_moment(moment)} : {count} stations"
    )
    return 0


# --- velo status ------------------------------------------------------------------


def cmd_status(args: argparse.Namespace, config: Config) -> int:
    """Résumé de l'état du réseau en temps réel."""
    warn_if_static_files_old(config)
    snapshot = gbfs.fetch_snapshot(config.gbfs_url)
    summary = states.summarize(snapshot)
    display.console.print(display.render_status(config.network_name, snapshot.last_updated, summary))
    return 0


# --- velo station ------------------------------------------------------------------


def cmd_station(args: argparse.Namespace, config: Config) -> int:
    """Lister, chercher ou consulter une station."""
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


# --- velo favorites -----------------------------------------------------------------


def cmd_favorites(args: argparse.Namespace, config: Config) -> int:
    """Afficher, ajouter ou retirer des favoris."""
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


# --- velo alerts ---------------------------------------------------------------------


def cmd_alerts(args: argparse.Namespace, config: Config) -> int:
    """Liste des stations hors service, vides ou presque, pleines ou presque."""
    low_bikes = pick(args.low_bikes, config.low_bikes)
    low_docks = pick(args.low_docks, config.low_docks)
    stations = gbfs.load_stations(config.network_folder)
    warn_if_static_files_old(config)
    snapshot = gbfs.fetch_snapshot(config.gbfs_url)
    alerts = states.compute_alerts(snapshot, stations, low_bikes, low_docks)
    display.console.print(
        f"[bold]{config.network_name} - alertes du {display.format_moment(snapshot.last_updated)}[/]"
    )
    display.console.print(display.render_alerts(alerts))
    return 0


# --- velo dashboard -------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace, config: Config) -> int:
    """Tableau de bord mis à jour automatiquement (Ctrl+C pour quitter)."""
    refresh = check_minimum(pick(args.refresh, config.dashboard_refresh),
                            MIN_DASHBOARD_REFRESH, "--refresh")
    low_bikes = pick(args.low_bikes, config.low_bikes)
    low_docks = pick(args.low_docks, config.low_docks)
    stations = gbfs.load_stations(config.network_folder)

    current: Snapshot = gbfs.fetch_snapshot(config.gbfs_url)  # sans données, rien à afficher
    previous: Snapshot | None = None
    error: str | None = None

    def screen(seconds_left: int) -> Group:
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
        with Live(screen(refresh), console=display.console, auto_refresh=False,
                  redirect_stderr=True, screen=False) as live:
            while True:
                for seconds_left in range(refresh, 0, -1):
                    live.update(screen(seconds_left), refresh=True)
                    time.sleep(1)
                try:
                    new = gbfs.fetch_snapshot(config.gbfs_url)
                except NetworkError as exc:
                    log.warning("Tableau de bord : %s", exc)
                    error = str(exc)
                else:
                    if new.last_updated != current.last_updated:
                        previous, current = current, new
                    error = None
    except KeyboardInterrupt:
        display.console.print("Tableau de bord fermé.")
    return 0


# --- velo collect ----------------------------------------------------------------------

_DURATION = re.compile(r"^(?:(?P<h>\d+)h)?(?:(?P<m>\d+)(?:m|min)?)?(?:(?P<s>\d+)s)?$")


def parse_duration(text: str) -> timedelta:
    """"3h", "90m", "1h30", "45s" -> timedelta."""
    match = _DURATION.match(text.strip().lower())
    if not text.strip() or not match or not any(match.groupdict().values()):
        raise VeloError(f"Durée invalide : « {text} » (exemples : 3h, 90m, 1h30, 45s).")
    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    duration = timedelta(hours=parts["h"], minutes=parts["m"], seconds=parts["s"])
    if duration.total_seconds() <= 0:
        raise VeloError("La durée doit être positive.")
    return duration


def parse_until(text: str) -> datetime:
    """"2026-11-20 10:00" -> datetime local, qui doit être dans le futur."""
    try:
        moment = datetime.strptime(text.strip(), "%Y-%m-%d %H:%M").astimezone()
    except ValueError as exc:
        raise VeloError(f"Date invalide : « {text} » (format : \"AAAA-MM-JJ HH:MM\").") from exc
    if moment <= datetime.now().astimezone():
        raise VeloError(f"La date de fin {text} est déjà passée.")
    return moment


def cmd_collect(args: argparse.Namespace, config: Config) -> int:
    """Enregistre l'état de toutes les stations à intervalle régulier."""
    interval = check_minimum(pick(args.interval, config.interval_seconds),
                             MIN_INTERVAL_SECONDS, "--interval")
    end: datetime | None = None
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
                if args.once:
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
                wait = min(wait, remaining)
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


# --- velo history ----------------------------------------------------------------------


def _all_periods(config: Config, interval: int) -> tuple[list[storage.Record], list[history.Period]]:
    records = storage.read_history(config.history_folder)
    return records, history.find_periods([r.timestamp for r in records], interval)


def cmd_history(args: argparse.Namespace, config: Config) -> int:
    """Affiche les périodes et relevés enregistrés."""
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


# --- velo query ------------------------------------------------------------------------


def cmd_query(args: argparse.Namespace, config: Config) -> int:
    """Analyse l'historique enregistré."""
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
            stations = {}  # sans les noms, on affiche seulement les identifiants
    if result.interrupted:
        display.print_warning("la sélection comporte des interruptions.")
    display.console.print(display.render_query(result, args.metric, args.by, stations))
    return 0
