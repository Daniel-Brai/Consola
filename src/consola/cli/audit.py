"""
Consola CLI Audit

    consola audit list --db myapp.database:engine
    consola audit list --db myapp.database:engine --limit 50
"""

from __future__ import annotations

import importlib
import sys
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

rich = Console()


audit_app = typer.Typer(
    help="Inspect recorded console sessions.",
    rich_markup_mode="rich",
)


def _load_engine_from_db(db: str):
    if ":" not in db:
        rich.print(
            "[red]Invalid [bold]--db[/bold] format. "
            "Expected [italic]module:variable[/italic], e.g. [bold]myapp.database:engine[/bold][/red]"
        )
        raise typer.Exit(1)

    module_path, _, var_name = db.partition(":")

    if "" not in sys.path:
        sys.path.insert(0, "")

    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        rich.print(f"[red]Cannot import [bold]{module_path}[/bold]: {exc}[/red]")
        raise typer.Exit(1) from exc

    engine = getattr(mod, var_name, None)
    if engine is None:
        rich.print(f"[red]Module [bold]{module_path}[/bold] has no attribute [bold]{var_name}[/bold].[/red]")
        raise typer.Exit(1)

    return engine


def _require_audit_tables(engine) -> None:
    from consola.session import tables_exist

    existence = tables_exist(engine, ["consola_sessions", "consola_commands"])
    if not all(existence.values()):
        rich.print(
            "[red]Audit tables not found in this database.[/red]\n"
            "[dim]Start Consola with [bold]--enable-audit[/bold] to create them automatically.[/dim]"
        )
        raise typer.Exit(1)


@audit_app.command("list")
def list_audits(
    db: Annotated[
        str,
        typer.Option(
            "--db",
            "-d",
            help=(
                "Dotted module path with a colon for the variable exposing the db engine. "
                "Example: [bold]myapp.database:engine[/bold]"
            ),
            show_default=False,
        ),
    ],
    limit: Annotated[
        int,
        typer.Option("--limit", help="Maximum number of sessions to show."),
    ] = 20,
) -> None:
    """
    List recorded console sessions
    """

    from consola.audit import AuditReader

    engine = _load_engine_from_db(db)
    _require_audit_tables(engine)

    rows = AuditReader(engine).list_sessions(limit=limit)

    if not rows:
        rich.print("[dim]No sessions found.[/dim]")
        return

    t = Table(show_header=True, header_style="bold magenta", border_style="dim")
    t.add_column("ID", style="dim", width=6)
    t.add_column("User", style="cyan")
    t.add_column("Started", style="white")
    t.add_column("Duration", justify="right")
    t.add_column("Cmds", justify="right")

    for s, cmd_count in rows:
        dur = f"{s.duration_seconds():.0f}s" if s.duration_seconds() else "—"
        t.add_row(
            str(s.id),
            s.username,
            s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "?",
            dur,
            str(cmd_count),
        )

    rich.print(t)
