"""
Pretty SQL logging for SQL Statements in Consola
"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from consola.types import AnyEngine

__all__ = ["attach_logging", "detach_logging"]

_console = Console(highlight=False)
_timings: dict[int, float] = {}


def _before(
    conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any
) -> None:  # noqa: ARG001
    _timings[id(cursor)] = time.perf_counter()


def _after(
    conn: Any, cursor: Any, statement: Any, parameters: Any, context: Any, executemany: Any
) -> None:  # noqa: ARG001
    elapsed = (time.perf_counter() - _timings.pop(id(cursor), time.perf_counter())) * 1000
    header = Text("  SQL ", style="bold cyan")
    header.append(f"({elapsed:.1f}ms)", style="dim")

    _console.print(header)
    _console.print(Syntax(statement.strip(), "sql", theme="monokai", word_wrap=True, padding=(0, 2)))

    if parameters:
        p = Text("  Params  ", style="bold magenta")
        p.append(repr(parameters), style="dim")
        _console.print(p)

    _console.print()


def _sync_engine(engine: AnyEngine) -> Engine:
    if isinstance(engine, AsyncEngine):
        return engine.sync_engine

    return engine


def attach_logging(engine: AnyEngine) -> None:
    """
    Setup event listeners for query logging
    """

    e = _sync_engine(engine)

    if not event.contains(e, "before_cursor_execute", _before):
        event.listen(e, "before_cursor_execute", _before)

    if not event.contains(e, "after_cursor_execute", _after):
        event.listen(e, "after_cursor_execute", _after)


def detach_logging(engine: AnyEngine) -> None:
    """
    Remove event listeners for query logging
    """

    e = _sync_engine(engine)

    for hook, name in [(_before, "before_cursor_execute"), (_after, "after_cursor_execute")]:
        if event.contains(e, name, hook):
            event.remove(e, name, hook)
