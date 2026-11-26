"""Tout l'affichage dans le terminal (avec Rich). Aucun calcul ici.

Chaque fonction reçoit des résultats déjà calculés et renvoie un objet
« affichable » Rich. Les commandes l'impriment ; le tableau de bord assemble
les mêmes objets sur un seul écran.
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Console, Group
from rich.table import Table
from rich.text import Text

from velo.history import Period, format_duration
from velo.models import StationInfo, StationStatus
from velo.query import WEEKDAY_NAMES, QueryResult
from velo.states import Alert, Alerts, FavoriteRow, NetworkSummary

console = Console()
error_console = Console(stderr=True)

LABEL_STYLES = {
    "hors service": "bold magenta",
    "vide": "bold red",
    "presque vide": "yellow",
    "pleine": "bold blue",
    "presque pleine": "cyan",
}


def format_moment(moment: datetime) -> str:
    """16/11/2026 à 12:05"""
    return moment.strftime("%d/%m/%Y à %H:%M")


def format_short(moment: datetime) -> str:
    """16/11/2026 12:05"""
    return moment.strftime("%d/%m/%Y %H:%M")


def _label(label: str) -> Text:
    return Text(label, style=LABEL_STYLES.get(label, ""))


def _delta(value: int | None) -> str:
    if not value:
        return ""
    return f"({value:+d})"


# --- Messages ----------------------------------------------------------------


def print_error(message: str) -> None:
    """Message d'erreur clair, sans trace d'exception."""
    error_console.print(f"[bold red]Erreur :[/] {message}")


def print_warning(message: str) -> None:
    """Avertissement : le résultat est à interpréter avec prudence."""
    error_console.print(f"[yellow]Avertissement :[/] {message}")


# --- velo status ---------------------------------------------------------------


def render_status(network_name: str, moment: datetime, summary: NetworkSummary) -> Group:
    """Le résumé du réseau, avec son titre."""
    title = Text(f"{network_name} - données du {format_moment(moment)}", style="bold")
    return Group(title, Text(""), render_summary(summary))


def render_summary(summary: NetworkSummary) -> Table:
    """Les chiffres du réseau (réutilisés par le tableau de bord)."""
    table = Table.grid(padding=(0, 3))
    table.add_column(style="bold")
    table.add_column()
    table.add_column()
    table.add_row(
        "Stations",
        f"en service [bold]{summary.in_service}[/] / {summary.total}",
        f"hors service [bold]{summary.out_of_service}[/]",
    )
    table.add_row("", f"vides [bold]{summary.empty}[/]", f"pleines [bold]{summary.full}[/]")
    table.add_row(
        "Vélos",
        f"disponibles [bold]{summary.bikes}[/]",
        f"places libres [bold]{summary.docks}[/]",
    )
    table.add_row("", f"taux de remplissage [bold]{summary.fill_rate:.0f} %[/]", "")
    return table


# --- velo station --------------------------------------------------------------


def render_station_list(stations: list[StationInfo]) -> Table:
    """Liste de stations : identifiant et nom."""
    table = Table(box=None, header_style="bold")
    table.add_column("ID", justify="right")
    table.add_column("Station")
    for info in stations:
        table.add_row(info.station_id, info.name)
    return table


def render_station_detail(
    info: StationInfo, status: StationStatus | None, label: str
) -> Table:
    """Fiche détaillée d'une station."""
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold")
    table.add_column()
    table.add_row("Station", f"{info.station_id} {info.name}")
    table.add_row("Capacité", str(info.capacity) if info.capacity is not None else "inconnue")
    if status is None:
        table.add_row("État", "absente du dernier relevé")
        return table
    table.add_row("Vélos", str(status.bikes))
    table.add_row("Places libres", str(status.docks))
    table.add_row("État", _label(label or "normal"))
    table.add_row("Mise à jour", format_moment(status.last_reported))
    return table


# --- velo favorites ------------------------------------------------------------


def render_favorites(rows: list[FavoriteRow]) -> Table:
    """Tableau des favoris (avec l'évolution si elle est connue)."""
    table = Table(box=None, header_style="bold")
    table.add_column("ID", justify="right")
    table.add_column("Station")
    table.add_column("Vélos", justify="right")
    table.add_column("Places", justify="right")
    table.add_column("")
    for row in rows:
        bikes = "-" if row.bikes is None else f"{row.bikes} {_delta(row.delta_bikes)}".strip()
        docks = "-" if row.docks is None else f"{row.docks} {_delta(row.delta_docks)}".strip()
        table.add_row(row.station_id, row.name, bikes, docks, _label(row.label))
    return table


def render_no_favorites() -> Text:
    """Explication quand il n'y a aucun favori."""
    return Text.from_markup(
        "Aucun favori pour l'instant.\n"
        "Trouvez l'identifiant d'une station avec [bold]velo station search <nom>[/], "
        "puis ajoutez-la avec [bold]velo favorites add <id>[/]."
    )


# --- velo alerts -----------------------------------------------------------------


def _alert_list(alerts: list[Alert], value: str) -> str:
    if value == "bikes":
        return ", ".join(f"{a.station_id} {a.name} ({a.bikes})" for a in alerts)
    if value == "docks":
        return ", ".join(
            f"{a.station_id} {a.name} ({a.docks} place{'s' if a.docks > 1 else ''})" for a in alerts
        )
    return ", ".join(f"{a.station_id} {a.name}" for a in alerts)


def render_alerts(alerts: Alerts) -> Table | Text:
    """Les alertes classées par type."""
    if alerts.count == 0:
        return Text("Aucune alerte : toutes les stations fonctionnent normalement.", style="green")
    table = Table.grid(padding=(0, 3))
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    if alerts.out_of_service:
        table.add_row(f"Hors service ({len(alerts.out_of_service)})",
                      _alert_list(alerts.out_of_service, "name"))
    if alerts.low_bikes:
        table.add_row(f"Vide ou presque ({len(alerts.low_bikes)})",
                      _alert_list(alerts.low_bikes, "bikes"))
    if alerts.low_docks:
        table.add_row(f"Pleine ou presque ({len(alerts.low_docks)})",
                      _alert_list(alerts.low_docks, "docks"))
    return table


# --- velo history ------------------------------------------------------------------


def render_history(network_name: str, periods: list[Period]) -> Group:
    """La liste des périodes collectées."""
    total = sum(p.count for p in periods)
    table = Table(box=None, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Début")
    table.add_column("Fin")
    table.add_column("Durée", justify="right")
    table.add_column("Relevés", justify="right")
    for p in periods:
        table.add_row(str(p.number), format_short(p.start), format_short(p.end),
                      format_duration(p.duration), str(p.count))
    title = (f"Historique {network_name} : {len(periods)} période{'s' if len(periods) > 1 else ''}, "
             f"{total} relevé{'s' if total > 1 else ''}")
    return Group(Text(title, style="bold"), Text(""), table)


# --- velo query --------------------------------------------------------------------


def _metric_value(metric: str, value: float) -> str:
    return f"{value:.0f} %" if metric.endswith("_rate") else f"{value:.1f}"


def _group_label(key: str, by: str | None, stations: dict[str, StationInfo]) -> str:
    if by == "station":
        info = stations.get(key)
        return f"{key} {info.name}" if info else key
    if by == "weekday":
        return WEEKDAY_NAMES[int(key.split("-")[0])]
    return key


def render_query(
    result: QueryResult, metrics: list[str], by: str | None, stations: dict[str, StationInfo]
) -> Group:
    """Le résultat d'une requête sur l'historique."""
    periods = ", ".join(map(str, result.periods_used))
    header = Text(
        f"Données : période{'s' if len(result.periods_used) > 1 else ''} {periods} - "
        f"{result.snapshot_count} relevé{'s' if result.snapshot_count > 1 else ''}"
    )
    first_column = {"station": "Station", "hour": "Heure", "weekday": "Jour",
                    "day": "Date"}.get(by or "", "")
    table = Table(box=None, header_style="bold")
    table.add_column(first_column)
    for metric in metrics:
        table.add_column(metric, justify="right")
    table.add_column("Relevés", justify="right")
    for row in result.rows:
        table.add_row(_group_label(row.key, by, stations),
                      *(_metric_value(m, row.values[m]) for m in metrics), str(row.count))
    return Group(header, Text(""), table)


# --- velo dashboard ----------------------------------------------------------------


def render_dashboard(
    network_name: str,
    moment: datetime,
    seconds_left: int,
    summary: NetworkSummary,
    favorites: list[FavoriteRow],
    alerts: Alerts,
    error: str | None,
) -> Group:
    """Un écran complet du tableau de bord, assemblé avec les mêmes briques."""
    header = Text.assemble(
        (f"{network_name}", "bold"),
        f" - données du {format_moment(moment)} - prochaine mise à jour dans {seconds_left} s",
        "   (Ctrl+C pour quitter)",
    )
    parts: list = [header]
    if error:
        parts.append(Text(f"⚠ Réseau indisponible, dernières données conservées : {error}",
                          style="yellow"))
    parts += [Text(""), render_summary(summary), Text("")]
    parts.append(Text("Favoris", style="bold underline"))
    parts.append(render_favorites(favorites) if favorites else render_no_favorites())
    parts += [Text(""), Text("Alertes", style="bold underline"), render_alerts(alerts)]
    return Group(*parts)
