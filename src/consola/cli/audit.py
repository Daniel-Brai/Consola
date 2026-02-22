"""
Consola CLI Audit

    consola audit list
    consola audit list --pending
    consola audit review <id>
    consola audit stats
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

rich = Console()


audit_app = typer.Typer(
    help="Inspect and review recorded console sessions.",
    rich_markup_mode="rich",
)


@audit_app.command("list")
def list_audits(
    pending: Annotated[
        bool,
        typer.Option("--pending", help="Only show unreviewed sessions."),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Maximum number of sessions to show."),
    ] = 20,
    audit_db: Annotated[
        str,
        typer.Option("--audit-db", show_default=True),
    ] = "sqlite:///consola_audit.db",
) -> None:
    """
    List recorded console sessions
    """

    from consola.audit import AuditReviewer

    sessions = AuditReviewer(audit_db).list_sessions(pending_only=pending, limit=limit)

    if not sessions:
        rich.print("[dim]No sessions found.[/dim]")
        return

    t = Table(show_header=True, header_style="bold magenta", border_style="dim")
    t.add_column("ID", style="dim", width=6)
    t.add_column("User", style="cyan")
    t.add_column("Started", style="white")
    t.add_column("Duration", justify="right")
    t.add_column("Cmds", justify="right")
    t.add_column("Status")

    for s in sessions:
        dur = f"{s.duration_seconds():.0f}s" if s.duration_seconds() else "—"
        if not s.reviewed:
            status = "[yellow]pending[/yellow]"
        elif s.approved:
            status = "[green]✓ approved[/green]"
        else:
            status = "[red]⚑ flagged[/red]"
        t.add_row(
            str(s.id),
            s.username,
            s.started_at.strftime("%Y-%m-%d %H:%M") if s.started_at else "?",
            dur,
            str(len(s.commands)),
            status,
        )

    rich.print(t)


@audit_app.command("review")
def review_audit(
    session_id: Annotated[int, typer.Argument(help="ID of the session to review.")],
    audit_db: Annotated[
        str,
        typer.Option("--audit-db", show_default=True),
    ] = "sqlite:///consola_audit.db",
) -> None:
    """
    Interactively review a console session either approve or flag it.
    """

    from consola.audit import AuditReviewer

    reviewer = AuditReviewer(audit_db)
    s = reviewer.get_session(session_id)

    if s is None:
        msg = f"Session [bold]{session_id}[/bold] not found."
        rich.print(f"[red]{msg}[/red]")
        raise typer.Exit(1)
    else:
        rich.print(
            Panel(
                f"[bold]Session #{s.id}[/bold]  "
                f"user=[cyan]{s.username}[/cyan]  "
                f"started={s.started_at}  "
                f"commands={len(s.commands)}",
                border_style="cyan",
                expand=False,
            )
        )
        rich.print()

        for i, cmd in enumerate(s.commands, 1):
            icon = "[red]✗[/red]" if cmd.raised_exception else "[dim]›[/dim]"
            rich.print(f"  {icon}  [bold]{i:>3}.[/bold]  {cmd.source!r}")
            if cmd.raised_exception and cmd.exception_message:
                rich.print(f"             [red dim]{cmd.exception_message}[/red dim]")

        rich.print()
        choice = typer.prompt(
            "Decision",
            type=typer.Option(["approve", "flag", "skip"]),
            default="skip",
        )

        if choice == "approve":
            notes = typer.prompt("Notes (optional)", default="")
            reviewer.approve(session_id, notes)
            rich.print("[green]✓ Session approved.[/green]")
        elif choice == "flag":
            notes = typer.prompt("Notes", default="")
            reviewer.flag(session_id, notes)
            rich.print("[red]⚑ Session flagged.[/red]")
        else:
            rich.print("[dim]Skipped.[/dim]")


@audit_app.command("stats")
def audit_stats(
    audit_db: Annotated[
        str,
        typer.Option("--audit-db", show_default=True),
    ] = "sqlite:///consola_audit.db",
) -> None:
    """
    Show high-level audit statistics
    """

    from consola.audit import AuditReviewer

    reviewer = AuditReviewer(audit_db)
    total = len(reviewer.list_sessions(limit=999_999))
    pending = reviewer.pending_count()
    reviewed = total - pending

    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("label", style="dim")
    t.add_column("value", style="bold")
    t.add_row("Total sessions", str(total))
    t.add_row("Pending review", f"[yellow]{pending}[/yellow]")
    t.add_row("Reviewed", f"[green]{reviewed}[/green]")

    rich.print(t)
