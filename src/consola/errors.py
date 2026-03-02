"""
Pretty error rendering for the Consola REPL.

IT catches both Consola specific exceptions and raw SQLAlchemy errors,
formats them with Rich so the REPL output stays readable.

Usage:

    from consola.errors import pretty_print_error, translate_sa_error

    try:
        ...
    except Exception as exc:
        raise translate_error(exc, params=kwargs) from exc
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from consola.exceptions import ConsolaError, ConsolaLookupError, ConsolaParamsError, ConsolaTransactionError

__all__ = [
    "pretty_print_error",
    "translate_error",
]


rich = Console(stderr=True)


def _sa_exceptions() -> dict[str, type[Exception]]:
    try:
        import sqlalchemy.exc as sa_exc  # noqa: PLC0415

        return {
            "NoResultFound": sa_exc.NoResultFound,
            "MultipleResultsFound": sa_exc.MultipleResultsFound,
            "InvalidRequestError": sa_exc.InvalidRequestError,
            "DataError": sa_exc.DataError,
            "IntegrityError": sa_exc.IntegrityError,
            "OperationalError": sa_exc.OperationalError,
            "ProgrammingError": sa_exc.ProgrammingError,
            "CompileError": sa_exc.CompileError,
            "ArgumentError": sa_exc.ArgumentError,
            "TimeoutError": sa_exc.TimeoutError,
            "DBAPIError": sa_exc.DBAPIError,
        }
    except ImportError:
        return {}


def translate_error(
    exc: Any,
    *,
    params: dict[str, Any] | None = None,
) -> ConsolaError:
    """
    Convert a raw SQLAlchemy (or DBAPI) exception or any exception into the appropriate ConsolaError subclass,
    preserving the original as __cause__.
    """

    sa = _sa_exceptions()
    msg = _extract_message(exc)

    if isinstance(exc, ConsolaError):
        return exc

    if isinstance(exc, (sa.get("NoResultFound", ()), LookupError)):
        return ConsolaLookupError(msg)

    if isinstance(
        exc,
        (
            sa.get("DataError", ()),
            sa.get("ProgrammingError", ()),
            sa.get("CompileError", ()),
            sa.get("ArgumentError", ()),
            sa.get("InvalidRequestError", ()),
        ),
    ):
        return ConsolaParamsError(msg, params or {})

    if isinstance(
        exc,
        (
            sa.get("IntegrityError", ()),
            sa.get("OperationalError", ()),
            sa.get("TimeoutError", ()),
            sa.get("DBAPIError", ()),
        ),
    ):
        return ConsolaTransactionError(msg)

    return ConsolaError(msg)


def _extract_message(exc: Any) -> str:
    orig = getattr(exc, "orig", None)
    if orig is not None:
        return str(orig)

    return str(exc).split("\n")[0]


def _stack(items: list[Any]) -> Any:
    from rich.console import Group  # noqa: PLC0415

    return Group(*items)


def _resolve_style(exc: Exception) -> tuple[str, str, str]:
    for cls, style in _STYLES.items():
        if isinstance(exc, cls):
            return style

    return ("red", type(exc).__name__, "bold red")


_STYLES: dict[type, tuple[str, str, str]] = {
    ConsolaLookupError: ("yellow", "Not Found", "bold yellow"),
    ConsolaParamsError: ("red", "Invalid Params", "bold red"),
    ConsolaTransactionError: ("red", "Transaction Error", "bold red"),
    ConsolaError: ("red", "Consola Error", "bold red"),
}


def pretty_print_error(exc: Exception) -> None:
    """
    Render a Consola exception to stderr with Rich
    """

    border, label, label_style = _resolve_style(exc)

    lines: list[Any] = []

    header = Text()
    header.append(f"  {label}  ", style=label_style)
    header.append(_extract_message(exc), style="white")
    lines.append(header)

    if isinstance(exc, ConsolaParamsError) and exc.params:
        lines.append("")
        t = Table(show_header=False, box=None, padding=(0, 2))
        t.add_column("key", style="dim cyan")
        t.add_column("value", style="dim")
        for k, v in exc.params.items():
            t.add_row(str(k), repr(v))
        lines.append(t)

    if isinstance(exc, ConsolaTransactionError):
        lines.append(Text("  ↩ Transaction has been rolled back.", style="dim yellow"))
        lines.append(
            Text(
                "  Hint: run <Model>.columns to see valid column names.",
                style="dim cyan",
            )
        )

    cause = exc.__cause__ or exc.__context__
    if cause and not isinstance(cause, ConsolaError):
        lines.append("")
        cause_text = Text()
        cause_text.append("  Caused by  ", style="dim")
        cause_text.append(type(cause).__name__, style="bold dim")
        cause_text.append(f": {_extract_message(cause)}", style="dim")
        lines.append(cause_text)

    rich.print()
    rich.print(
        Panel(
            _stack(lines),
            border_style=border,
            expand=False,
            padding=(0, 1),
        )
    )
    rich.print()
