"""Tout ce qui s'affiche dans le terminal. Ici, on met en forme : on ne calcule rien.

Chaque fonction reçoit des résultats déjà calculés (par states.py, query.py...)
et renvoie un objet « affichable » de la bibliothèque Rich (un tableau, un texte).
Les commandes l'impriment. Le tableau de bord, lui, assemble les MÊMES objets
sur un seul écran : c'est pour ça qu'on n'écrit jamais deux fois le même affichage.

Rich, c'est une bibliothèque qui fait de jolis tableaux et des couleurs dans le
terminal. Dans un texte Rich, [bold]...[/] veut dire « en gras ».
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

console = Console()  # l'écran normal (les résultats)
error_console = Console(stderr=True)  # l'écran des erreurs et avertissements

LABEL_STYLES = {
    "hors service": "bold magenta",
    "vide": "bold red",
    "presque vide": "yellow",
    "pleine": "bold blue",
    "presque pleine": "cyan",
}


def format_moment(moment: datetime) -> str:
    """Exemple : "16/11/2026 à 12:05"."""
    return moment.strftime("%d/%m/%Y à %H:%M")


def format_short(moment: datetime) -> str:
    """Exemple : "16/11/2026 12:05"."""
    return moment.strftime("%d/%m/%Y %H:%M")


def _label(label: str) -> Text:
    """Un état ("vide", "pleine"...) avec sa couleur."""
    return Text(label, style=LABEL_STYLES.get(label, ""))


def _delta(value: int | None) -> str:
    """Une évolution entre parenthèses. Exemple : -2 -> "(-2)". Rien si 0 ou inconnue."""
    if not value:
        return ""
    return f"({value:+d})"


# --- Messages ------------------------------------------------------------------------


def print_error(message: str) -> None:
    """Affiche « Erreur : ... » en une ligne, sans le pavé technique de Python."""
    error_console.print(f"[bold red]Erreur :[/] {message}")


def print_warning(message: str) -> None:
    """Affiche « Avertissement : ... » : le résultat est là, mais à prendre avec prudence."""
    error_console.print(f"[yellow]Avertissement :[/] {message}")


# --- velo status ---------------------------------------------------------------------------


def render_status(network_name: str, moment: datetime, summary: NetworkSummary) -> Group:
    """L'écran de velo status : un titre, puis les chiffres."""
    title = Text(f"{network_name} - données du {format_moment(moment)}", style="bold")
    return Group(title, Text(""), render_summary(summary))


def render_summary(summary: NetworkSummary) -> Table:
    """Les chiffres du réseau, sans titre (le tableau de bord les réutilise)."""
    table = Table.grid(padding=(0, 3))  # grid = tableau sans bordures
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


# --- velo station ------------------------------------------------------------------------


def render_station_list(stations: list[StationInfo]) -> Table:
    """Un tableau à deux colonnes : numéro et nom."""
    table = Table(box=None, header_style="bold")
    table.add_column("ID", justify="right")
    table.add_column("Station")
    for info in stations:
        table.add_row(info.station_id, info.name)
    return table


def render_station_detail(
    info: StationInfo, status: StationStatus | None, label: str
) -> Table:
    """La fiche d'une station : nom, capacité, vélos, places, état."""
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


# --- velo favorites ----------------------------------------------------------------------


def render_favorites(rows: list[FavoriteRow]) -> Table:
    """Le tableau des favoris. Dans le tableau de bord, l'évolution s'ajoute : "3 (-2)"."""
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
    """Le message quand il n'y a aucun favori : on explique comment en ajouter."""
    return Text.from_markup(
        "Aucun favori pour l'instant.\n"
        "Trouvez l'identifiant d'une station avec [bold]velo station search <nom>[/], "
        "puis ajoutez-la avec [bold]velo favorites add <id>[/]."
    )


# --- velo alerts ---------------------------------------------------------------------------


def _alert_list(alerts: list[Alert], value: str) -> str:
    """Une liste d'alertes sur une ligne. Exemple : "43 Gare Lille Flandres (0), 61 Gambetta (1)"."""
    if value == "bikes":
        return ", ".join(f"{a.station_id} {a.name} ({a.bikes})" for a in alerts)
    if value == "docks":
        return ", ".join(
            f"{a.station_id} {a.name} ({a.docks} place{'s' if a.docks > 1 else ''})" for a in alerts
        )
    return ", ".join(f"{a.station_id} {a.name}" for a in alerts)


def render_alerts(alerts: Alerts) -> Table | Text:
    """Les alertes, une ligne par type. Sans alerte, une phrase pour le dire."""
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


# --- velo history ----------------------------------------------------------------------------


def render_history(network_name: str, periods: list[Period]) -> Group:
    """Le tableau des périodes : numéro, début, fin, durée, nombre de relevés."""
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


# --- velo query ------------------------------------------------------------------------------


def _metric_value(metric: str, value: float) -> str:
    """Un taux s'affiche en % sans virgule ("72 %"), une moyenne avec une décimale ("3.4")."""
    return f"{value:.0f} %" if metric.endswith("_rate") else f"{value:.1f}"


def _group_label(key: str, by: str | None, stations: dict[str, StationInfo]) -> str:
    """Rend le nom d'un paquet lisible : "61" -> "61 Gambetta", "0-lundi" -> "lundi"."""
    if by == "station":
        info = stations.get(key)
        return f"{key} {info.name}" if info else key
    if by == "weekday":
        return WEEKDAY_NAMES[int(key.split("-")[0])]
    return key


def render_query(
    result: QueryResult, metrics: list[str], by: str | None, stations: dict[str, StationInfo]
) -> Group:
    """Le résultat d'une requête : d'où viennent les données, puis le tableau."""
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


# --- velo dashboard --------------------------------------------------------------------------


def render_dashboard(
    network_name: str,
    moment: datetime,
    seconds_left: int,
    summary: NetworkSummary,
    favorites: list[FavoriteRow],
    alerts: Alerts,
    error: str | None,
) -> Group:
    """Un écran complet du tableau de bord, construit avec les briques ci-dessus.

    Regarde bien : render_summary, render_favorites et render_alerts sont les
    mêmes fonctions que pour velo status, velo favorites et velo alerts.
    """
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
