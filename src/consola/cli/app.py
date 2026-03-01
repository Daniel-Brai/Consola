"""
Consola CLI App

    consola start                               auto-discover engine
    consola start --db myapp.database:engine    explicit module and variable name
    consola start --no-transaction
    consola start --no-sql-log
    consola start --scan <dir>
    consola start --enable-audit
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from consola.cli.audit import audit_app

rich = Console()

app = typer.Typer(
    name="consola",
    help="Interactive SQL console for SQLAlchemy or SQLModel projects.",
    no_args_is_help=False,
    add_completion=False,
    rich_markup_mode="rich",
)
app.add_typer(audit_app, name="audit")


def _abort(msg: str) -> None:
    rich.print(f"[red]{msg}[/red]")
    raise typer.Exit(1)


def _load_module(dotted: str):
    if "" not in sys.path:
        sys.path.insert(0, "")
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as exc:
        _abort(f"Cannot import [bold]{dotted}[/bold]: {exc}")


def _collect_bases(mod) -> list[type]:
    from sqlalchemy.orm import DeclarativeBase, DeclarativeMeta

    try:
        from sqlmodel import SQLModel
    except ImportError:
        SQLModel = None

    bases = []
    for attr in dir(mod):
        obj = getattr(mod, attr, None)
        if not isinstance(obj, type):
            continue
        try:
            if isinstance(type(obj), DeclarativeMeta) or (
                issubclass(obj, DeclarativeBase) and obj is not DeclarativeBase
            ):
                bases.append(obj)
            elif SQLModel and issubclass(obj, SQLModel) and obj is not SQLModel:
                bases.append(obj)
        except TypeError:
            continue

    return bases


@app.command()
def start(
    db: Annotated[
        str | None,
        typer.Option(
            "--db",
            "-d",
            help=(
                "Dotted module path with a colon for the variable exposing an [cyan]db engine[/cyan]"
                "([italic]Engine[/italic] or [italic]AsyncEngine[/italic]). "
                "Omit to let Consola scan the current directory automatically. "
                "Example: [bold]--db myapp.database:engine[/bold]"
            ),
            show_default=False,
        ),
    ] = None,
    scan: Annotated[
        list[Path] | None,
        typer.Option(
            "--scan",
            "-s",
            help="Extra directories to scan for engine or model files.",
            exists=True,
            file_okay=False,
            show_default=False,
        ),
    ] = None,
    no_transaction: Annotated[
        bool,
        typer.Option(
            "--no-transaction",
            help="Disable auto-transaction mode. Writes are not committed automatically.",
        ),
    ] = False,
    no_sql_log: Annotated[
        bool,
        typer.Option(
            "--no-sql-log",
            help="Disable pretty SQL logging.",
        ),
    ] = False,
    enable_audit: Annotated[
        bool,
        typer.Option(
            "--enable-audit",
            help=(
                "Enable audit logging. Creates [cyan]consola_sessions[/cyan] and "
                "[cyan]consola_commands[/cyan] tables in the main database if they "
                "don't exist and records every session and command."
            ),
        ),
    ] = False,
) -> None:
    """
    Boot the [bold cyan]Consola[/bold cyan] interactive console

    Consola will auto-discover your engine and models by scanning the current
    directory.

    Pass [bold]--db[/bold] if you need to point at a specific module
    """

    engine = None
    bases: list[type] = []

    if db:
        if db.count(":") != 1:
            _abort(
                f"Invalid format for [bold]--db[/bold]. Expected [italic]module:variable[/italic], got [bold]{db}[/bold]."
            )

        module_path, _, var_name = db.partition(":")
        mod = _load_module(module_path)
        engine = getattr(mod, var_name, None)
        if engine is None:
            _abort(
                f"Module [bold]{db}[/bold] has no [bold]{var_name}[/bold] attribute.\n"
                f"Ensure it exposes a SQLAlchemy Engine or AsyncEngine as the variable `{var_name}`."
            )
        bases = _collect_bases(mod)

    from consola.console import start as _start

    _start(
        engine=engine,
        bases=bases or None,
        search_paths=[str(p) for p in scan] if scan else None,
        sql_logging=not no_sql_log,
        auto_transaction=not no_transaction,
        enable_audit=enable_audit,
    )
