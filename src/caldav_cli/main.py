"""caldav_cli - CalDAV CLI for OpenClaw.

QUICK REFERENCE (for AI agents):

  caldav_cli calendars              List all calendars
  caldav_cli events [--start DATE] [--end DATE] [--calendar NAME]
                                    List events (default: today +30 days)
  caldav_cli add SUMMARY --start DATETIME [--end DATETIME] [--desc TEXT] [--location TEXT] [--tz TIMEZONE] [--calendar NAME]
                                    Create a new event
  caldav_cli show UID               Show full details of one event
  caldav_cli update UID [--summary TEXT] [--start DT] [--end DT] [--desc TEXT] [--location TEXT] [--tz TIMEZONE]
                                    Update an event (omit fields to leave unchanged)
  caldav_cli delete UID [--yes]     Delete an event by UID
  caldav_cli config                 Show config file path and credential status
  caldav_cli setup                  Interactive wizard to write ~/.config/caldav_cli/config.env

DATE FORMAT: YYYY-MM-DD or YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM+HH:MM (e.g. 2024-06-01T14:30+08:00)
TIMEZONE: IANA name (e.g. Asia/Shanghai, Asia/Tokyo). Falls back to CALDAV_TIMEZONE env var, then system local tz.
UID: from 'events' or 'show' output — a UUID string identifying one event.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from caldav_cli import client as dav
from caldav_cli.config import (
    config_path,
    get_credentials,
    get_default_calendar_name,
    CONFIG_DIR,
    CONFIG_FILE,
)

app = typer.Typer(
    name="caldav_cli",
    help=__doc__,
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
console = Console()
err = Console(stderr=True, style="bold red")


def _get_calendar(name: str | None):
    url, username, password = get_credentials()
    c = dav.connect(url, username, password)
    principal = dav.get_principal(c)
    cal_name = name or get_default_calendar_name()
    return dav.resolve_calendar(principal, cal_name)


def _get_principal():
    url, username, password = get_credentials()
    c = dav.connect(url, username, password)
    return dav.get_principal(c)


# ── Commands ──────────────────────────────────────────────────────────────────


@app.command()
def calendars():
    """List all calendars available on the server."""
    try:
        principal = _get_principal()
        cals = dav.list_calendars(principal)
        if not cals:
            rprint("[yellow]No calendars found.[/yellow]")
            return
        table = Table(title="Calendars", show_lines=False)
        table.add_column("#", style="dim", width=4)
        table.add_column("Name", style="bold")
        table.add_column("URL", style="dim")
        for i, cal in enumerate(cals, 1):
            table.add_row(str(i), cal.name or "(unnamed)", str(cal.url))
        console.print(table)
    except Exception as e:
        err.print(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def events(
    start: Optional[str] = typer.Option(None, "--start", "-s", help="Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM). Default: today."),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End date. Default: start +30 days."),
    calendar: Optional[str] = typer.Option(None, "--calendar", "-c", help="Calendar name. Uses CALDAV_CALENDAR or first calendar if unset."),
    output: str = typer.Option("table", "--output", "-o", help="Output format: table | json"),
):
    """List events in a date range.

    Examples:

      caldav_cli events
      caldav_cli events --start 2024-06-01 --end 2024-06-30
      caldav_cli events --calendar work --output json
    """
    try:
        cal = _get_calendar(calendar)
        evts = dav.fetch_events(cal, start, end)
        if not evts:
            rprint("[yellow]No events found in the given range.[/yellow]")
            return
        if output == "json":
            rprint(json.dumps(evts, indent=2, default=str))
            return
        table = Table(title=f"Events on '{cal.name}'", show_lines=True)
        table.add_column("Start", style="cyan", min_width=18)
        table.add_column("End", style="cyan", min_width=18)
        table.add_column("Summary", style="bold")
        table.add_column("UID", style="dim", max_width=36)
        for e in evts:
            table.add_row(
                e.get("start") or "",
                e.get("end") or "",
                e.get("summary") or "(no title)",
                e.get("uid") or "",
            )
        console.print(table)
    except Exception as e:
        err.print(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def show(
    uid: str = typer.Argument(..., help="Event UID"),
    calendar: Optional[str] = typer.Option(None, "--calendar", "-c", help="Calendar name."),
    output: str = typer.Option("pretty", "--output", "-o", help="Output format: pretty | json"),
):
    """Show full details of a single event by UID."""
    try:
        cal = _get_calendar(calendar)
        evts = dav.fetch_events(cal, "2000-01-01", "2099-12-31")
        match = next((e for e in evts if e.get("uid") == uid), None)
        if not match:
            err.print(f"Event '{uid}' not found.")
            raise typer.Exit(1)
        if output == "json":
            rprint(json.dumps(match, indent=2, default=str))
            return
        for key, val in match.items():
            rprint(f"[bold]{key:>12}[/bold]: {val or ''}")
    except typer.Exit:
        raise
    except Exception as e:
        err.print(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def add(
    summary: str = typer.Argument(..., help="Event title/summary."),
    start: str = typer.Option(..., "--start", "-s", help="Start datetime (YYYY-MM-DD, YYYY-MM-DDTHH:MM, or YYYY-MM-DDTHH:MM+HH:MM)."),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="End datetime. Default: start +1 hour."),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="Event description."),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="Event location."),
    tz: Optional[str] = typer.Option(None, "--tz", help="Timezone (IANA, e.g. Asia/Shanghai). Overrides CALDAV_TIMEZONE env var and system tz."),
    calendar: Optional[str] = typer.Option(None, "--calendar", "-c", help="Calendar name."),
):
    """Create a new calendar event.

    Examples:

      caldav_cli add "Team standup" --start 2024-06-03T09:00 --end 2024-06-03T09:30
      caldav_cli add "Tokyo dinner" --start 2024-06-03T19:00 --tz Asia/Tokyo
      caldav_cli add "Birthday" --start 2024-06-15 --desc "Don't forget cake" --calendar personal
    """
    try:
        cal = _get_calendar(calendar)
        uid = dav.create_event(cal, summary, start, end, description, location, tz=tz)
        rprint(f"[green]✓ Event created.[/green] UID: [bold]{uid}[/bold]")
    except Exception as e:
        err.print(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def update(
    uid: str = typer.Argument(..., help="Event UID to update."),
    summary: Optional[str] = typer.Option(None, "--summary", help="New title."),
    start: Optional[str] = typer.Option(None, "--start", "-s", help="New start datetime."),
    end: Optional[str] = typer.Option(None, "--end", "-e", help="New end datetime."),
    description: Optional[str] = typer.Option(None, "--desc", "-d", help="New description."),
    location: Optional[str] = typer.Option(None, "--location", "-l", help="New location."),
    tz: Optional[str] = typer.Option(None, "--tz", help="Timezone (IANA, e.g. Asia/Tokyo). Applied to --start and --end if they lack explicit offset."),
    calendar: Optional[str] = typer.Option(None, "--calendar", "-c", help="Calendar name."),
):
    """Update an existing event. Only provided fields are changed.

    Examples:

      caldav_cli update <UID> --summary "New title"
      caldav_cli update <UID> --start 2024-06-03T10:00 --end 2024-06-03T11:00 --tz Asia/Tokyo
    """
    try:
        cal = _get_calendar(calendar)
        dav.update_event(cal, uid, summary, start, end, description, location, tz=tz)
        rprint(f"[green]✓ Event updated.[/green]")
    except Exception as e:
        err.print(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def delete(
    uid: str = typer.Argument(..., help="Event UID to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    calendar: Optional[str] = typer.Option(None, "--calendar", "-c", help="Calendar name."),
):
    """Delete a calendar event by UID.

    Example:

      caldav_cli delete <UID> --yes
    """
    try:
        if not yes:
            typer.confirm(f"Delete event '{uid}'?", abort=True)
        cal = _get_calendar(calendar)
        dav.delete_event(cal, uid)
        rprint(f"[green]✓ Event deleted.[/green]")
    except typer.Abort:
        rprint("[yellow]Cancelled.[/yellow]")
    except Exception as e:
        err.print(f"Error: {e}")
        raise typer.Exit(1)


@app.command()
def config():
    """Show config file path and current credential status (no secrets printed)."""
    path = config_path()
    rprint(f"Config file: [bold]{path}[/bold]")
    if path.exists():
        rprint(f"[green]✓ Config file exists.[/green]")
        # Check which keys are set without printing values
        from dotenv import dotenv_values
        keys = dotenv_values(path).keys()
        for k in ("CALDAV_URL", "CALDAV_USERNAME", "CALDAV_PASSWORD", "CALDAV_CALENDAR", "CALDAV_TIMEZONE"):
            mark = "[green]✓[/green]" if k in keys else "[dim]✗ (not set)[/dim]"
            rprint(f"  {mark} {k}")
    else:
        rprint(f"[yellow]✗ Config file not found.[/yellow] Run [bold]caldav_cli setup[/bold] to create it.")


@app.command()
def setup():
    """Interactive wizard to write ~/.config/caldav_cli/config.env."""
    rprint("[bold]caldav_cli setup[/bold]")
    rprint(f"This will write credentials to: [bold]{CONFIG_FILE}[/bold]")
    rprint("[yellow]Tip: use an app password, not your main password.[/yellow]\n")

    url = typer.prompt("CalDAV URL (e.g. https://cloud.example.com/remote.php/dav)")
    username = typer.prompt("Username")
    password = typer.prompt("Password / App password", hide_input=True)
    calendar = typer.prompt("Default calendar name (leave blank to use first)", default="")
    timezone_name = typer.prompt("Default timezone (IANA, e.g. Asia/Shanghai, leave blank to use system tz)", default="")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.chmod(0o600) if CONFIG_FILE.exists() else None

    lines = [
        f"CALDAV_URL={url}",
        f"CALDAV_USERNAME={username}",
        f"CALDAV_PASSWORD={password}",
    ]
    if calendar:
        lines.append(f"CALDAV_CALENDAR={calendar}")
    if timezone_name:
        lines.append(f"CALDAV_TIMEZONE={timezone_name}")

    CONFIG_FILE.write_text("\n".join(lines) + "\n")
    CONFIG_FILE.chmod(0o600)
    rprint(f"\n[green]✓ Config written to {CONFIG_FILE}[/green] (mode 600)")

    # Quick connection test
    rprint("\nTesting connection...")
    try:
        import os
        os.environ["CALDAV_URL"] = url
        os.environ["CALDAV_USERNAME"] = username
        os.environ["CALDAV_PASSWORD"] = password
        principal = _get_principal()
        cals = dav.list_calendars(principal)
        rprint(f"[green]✓ Connected! Found {len(cals)} calendar(s):[/green]")
        for cal in cals:
            rprint(f"  - {cal.name}")
    except Exception as e:
        rprint(f"[yellow]⚠ Connection test failed: {e}[/yellow]")
        rprint("Credentials were saved — check URL/password and try [bold]caldav_cli calendars[/bold].")


def main():
    app()


if __name__ == "__main__":
    main()
