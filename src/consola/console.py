"""
Consola REPL

Runs in auto-transaction mode by default (--no-transaction to disable).

REPL commands (Rails-like style):
  :reload   — re-discover engine + models in-place
  :models   — list discovered models
  :begin    — start an explicit transaction block
  :commit   — commit the explicit transaction block
  :rollback — rollback the explicit transaction block

Model help:
  User --help   (or any model name + --help)

Every operation returns the populated model instance(s), just like Rails console.

Auto-rollback on failure for every atomic operation
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from typing import Any

from rich.console import Console as RichConsole
from rich.panel import Panel

from consola.audit import Auditor
from consola.completions import setup_completions
from consola.discovery import ModelRegistry, discover_engines, discover_models
from consola.errors import pretty_print_error, translate_error
from consola.logging import attach_logging, detach_logging
from consola.proxy import ModelProxy
from consola.session import BridgedSession, SessionBridge, is_async, tables_exist
from consola.types import AnyEngine

rich = RichConsole()

BANNER = "[bold cyan]Consola[/bold cyan]  " "[dim]:help · :models · :exit  or  <Model> --help[/dim]"

_REPL_COMMANDS = {
    ":reload",
    ":models",
    ":begin",
    ":commit",
    ":rollback",
    ":exit",
    ":help",
}


def _engine_label(engine: AnyEngine) -> str:
    if is_async(engine):
        return engine.url.render_as_string(hide_password=True)  # type: ignore[attr-defined]

    url = engine.sync_engine.url.render_as_string(hide_password=True)  # type: ignore[union-attr,attr-defined]
    return str(url)


def _print_banner(registry: ModelRegistry, engine: AnyEngine, auto_tx: bool) -> None:
    kind = "[yellow]async[/yellow]" if is_async(engine) else "[green]sync[/green]"
    tx = "[cyan]auto-transaction[/cyan]" if auto_tx else "[dim]no-transaction[/dim]"
    rich.print(
        Panel(
            f"{BANNER}\n[dim]{_engine_label(engine)}  ({kind}, {tx})[/dim]",
            border_style="cyan",
            expand=False,
            padding=(0, 1),
        )
    )
    rich.print()


_INTERNAL_TABLES: frozenset[str] = frozenset({"consola_sessions", "consola_commands"})


def _validate_tables(registry: ModelRegistry, engine: AnyEngine) -> None:
    table_map = {
        getattr(cls, "__tablename__", None): name
        for name, cls in registry.all().items()
        if getattr(cls, "__tablename__", None) and getattr(cls, "__tablename__", None) not in _INTERNAL_TABLES
    }
    if not table_map:
        return

    table_name_keys: filter[Any] = filter(lambda x: x is not None, table_map.keys())  # type: ignore[arbitrary-type]
    table_names: list[str] = list(table_name_keys)
    existence = tables_exist(engine, table_names)
    missing = [tbl for tbl, ok in existence.items() if not ok]
    if not missing:
        return
    rich.print("[bold yellow]⚠  Missing tables (run migrations then :reload):[/bold yellow]")
    for tbl in missing:
        rich.print(f"   [red]✗[/red]  {table_map[tbl]} → [dim]{tbl}[/dim]")
    rich.print()


def _preprocess(source: str) -> str | None:
    """
    Transform bare REPL commands and `Model --help` into real Python calls.

    Returns:
      str | None: Transformed source to execute, or None to run as-is.
    """

    stripped = source.strip()

    if stripped in _REPL_COMMANDS:
        return f'__consola_cmd__("{stripped[1:]}")'

    parts = stripped.split()
    if len(parts) == 2 and parts[1] == "--help":
        return f'__consola_cmd__("model_help", "{parts[0]}")'

    return None


def _open_session(bridge: SessionBridge, state: dict[str, Any]) -> BridgedSession:
    ctx = bridge()
    session = ctx.__enter__()
    state["_session_ctx"] = ctx
    return session


def _close_session(state: dict[str, Any]) -> None:
    try:
        ctx = state.get("_session_ctx")
        if ctx:
            ctx.__exit__(None, None, None)
    except Exception:
        return


def _build_namespace(
    registry: ModelRegistry,
    bridge: SessionBridge,
    engine: AnyEngine,
    state: dict[str, Any],
    auto_tx: bool,
) -> dict[str, Any]:
    session = _open_session(bridge, state)

    ns: dict[str, Any] = {}

    def _inject_proxies(ses: BridgedSession) -> None:
        for name, cls in registry.all().items():
            ns[name] = ModelProxy(cls, ses, auto_tx=auto_tx)

    _inject_proxies(session)

    ns["session"] = session
    ns["db"] = session
    ns["engine"] = engine

    def __consola_cmd__(cmd: str, arg: str = "") -> None:  # noqa: N802
        nonlocal session

        cmd = cmd.strip().lower()

        if cmd == "reload":
            _close_session(state)
            discover_models(
                search_paths=state.get("search_paths"),
                bases=state.get("bases"),
                registry=registry,
            )
            session = _open_session(bridge, state)
            _inject_proxies(session)

            ns["session"] = session
            ns["db"] = session

            frame = sys._getframe(1)
            frame.f_locals.update({k: ns[k] for k in registry.names()})
            frame.f_locals["session"] = session
            frame.f_locals["db"] = session

            setup_completions(ns, registry.names())
            _validate_tables(registry, engine)

            rich.print(f"[green]↺  Reloaded — {len(registry)} model(s)[/green]")

        elif cmd == "models":
            for n in sorted(registry.names()):
                cls = registry.all()[n]
                tbl = getattr(cls, "__tablename__", "?")
                rich.print(f"  [cyan]{n}[/cyan] [dim]({tbl})[/dim]")

        elif cmd == "begin":
            if state.get("explicit_tx"):
                rich.print("[yellow]Already in a transaction block.[/yellow]")
            else:
                state["explicit_tx"] = True
                rich.print("[cyan]Transaction opened — call :commit or :rollback[/cyan]")

        elif cmd == "commit":
            if not state.get("explicit_tx"):
                rich.print("[yellow]No open transaction block.[/yellow]")
            else:
                try:
                    session.commit()
                    state["explicit_tx"] = False
                    rich.print("[green]✓ Committed[/green]")
                except Exception as exc:
                    session.rollback()
                    state["explicit_tx"] = False
                    consola_exc = translate_error(exc)
                    pretty_print_error(consola_exc)

        elif cmd == "rollback":
            session.rollback()
            state["explicit_tx"] = False
            rich.print("[yellow]↩ Rolled back[/yellow]")

        elif cmd == "exit":
            raise SystemExit(0)

        elif cmd == "help":
            rich.print(
                """
[bold cyan]Consola commands[/bold cyan]

  [cyan]:models[/cyan]            List all discovered model proxies
  [cyan]:reload[/cyan]            Re-discover engine + models and rebind session in-place
  [cyan]:begin[/cyan]             Open an explicit transaction block
  [cyan]:commit[/cyan]            Commit the open transaction block (auto-rollback on failure)
  [cyan]:rollback[/cyan]          Rollback the open transaction block
  [cyan]:exit[/cyan]              Close the REPL
  [cyan]:help[/cyan]              Show this message
  [cyan]<Model> --help[/cyan]     Show columns, types and available methods for a model e.g. [bold]User --help[/bold]
"""
            )

        elif cmd == "model_help":
            proxy = ns.get(arg)
            if proxy is None:
                rich.print(f"[red]Unknown model: {arg}[/red]")
                return

            rich.print(
                f"""
[bold]Commands[/bold]
  {arg}.find(pk)
  {arg}.find_or_raise(pk)
  {arg}.find_by(**kwargs)          → single record or None
  {arg}.where(**kwargs)            → list
  {arg}.all() / .first() / .last()
  {arg}.first_by(**kwargs) / .last_by(**kwargs)
  {arg}.count(**kwargs)
  {arg}.exists(**kwargs)
  {arg}.create(**kwargs)
  {arg}.update(pk, where={{...}}, **values)
  {arg}.update_by(pk, **values)
  {arg}.update_all(where={{...}}, **values)
  {arg}.destroy(pk)
  {arg}.destroy_by(**kwargs)
  {arg}.destroy_all(**kwargs)
  {arg}.columns / .table_name
"""
            )

    ns["__consola_cmd__"] = __consola_cmd__
    return ns


class _NoOpAuditor:
    """
    Audit stub used when audit logging is disabled
    """

    def __enter__(self) -> _NoOpAuditor:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def record(self, source: str, exception: Any | None = None) -> None:
        pass

    @property
    def session_id(self) -> None:
        return None


def start(
    engine: AnyEngine | None = None,
    bases: list[type] | None = None,
    search_paths: list[str] | None = None,
    sql_logging: bool = True,
    auto_transaction: bool = True,
    enable_audit: bool = False,
) -> None:
    if engine is None:
        cwd = search_paths or ["."]
        candidates = discover_engines(search_paths=cwd)

        if not candidates:
            rich.print(
                "[red]No Engine or AsyncEngine found.\n"
                "Pass one: [bold]consola start --db myapp.database:engine[/bold][/red]"
            )
            return

        if len(candidates) > 1:
            rich.print("[yellow]Multiple engines found — using first. Use --db to be explicit.[/yellow]")

        engine = candidates[0]

    if sql_logging:
        attach_logging(engine)

    effective_paths = search_paths or ["."]
    registry = discover_models(search_paths=effective_paths, bases=bases)
    bridge = SessionBridge(engine)

    state: dict[str, Any] = {
        "engine": engine,
        "search_paths": effective_paths,
        "bases": bases,
        "_session_ctx": None,
        "explicit_tx": False,
    }

    _print_banner(registry, engine, auto_transaction)
    _validate_tables(registry, engine)

    if enable_audit:
        from consola.audit.models import AuditBase
        from consola.session import resolve_sync_engine

        audit_sync_engine = resolve_sync_engine(engine)
        AuditBase.metadata.create_all(audit_sync_engine)
        audit_db_url = str(audit_sync_engine.url.render_as_string(hide_password=False))
        auditor_cm: Any = Auditor(audit_db_url)
    else:
        auditor_cm = _NoOpAuditor()

    with auditor_cm as auditor:
        ns = _build_namespace(registry, bridge, engine, state, auto_transaction)
        setup_completions(ns, registry.names())

        try:
            _start_stdlib(ns, auditor)
        finally:
            _close_session(state)

    if sql_logging:
        detach_logging(engine)


def _start_stdlib(ns: dict[str, Any], auditor: Any) -> None:
    import code

    _exc_holder: list[Any | None] = [None]

    class _Console(code.InteractiveConsole):
        def showtraceback(self) -> None:  # type: ignore[override]
            import sys

            _, exc_value, _ = sys.exc_info()
            if exc_value is not None:
                _exc_holder[0] = exc_value
                consola_exc = translate_error(exc_value)
                pretty_print_error(consola_exc)

        def showsyntaxerror(self, filename: str | None = None, **kwargs: Any) -> None:  # type: ignore[override]
            import sys

            _, exc_value, _ = sys.exc_info()
            if exc_value is not None:
                _exc_holder[0] = exc_value
                consola_exc = translate_error(exc_value)
                pretty_print_error(consola_exc)

        def runsource(self, source: str, filename: str = "<input>", symbol: str = "single") -> bool:  # type: ignore[override]
            _exc_holder[0] = None
            transformed = _preprocess(source)
            actual = transformed if transformed is not None else source
            try:
                # Only capture stdout for plain user code so we can colorize
                # print() output in green. REPL commands (transformed is not
                # None) already write via Rich directly — capturing them would
                # collect rendered ANSI bytes and then double-render them.
                if transformed is not None:
                    result = super().runsource(actual, filename, symbol)
                else:
                    output_buffer = io.StringIO()
                    with redirect_stdout(output_buffer):
                        result = super().runsource(actual, filename, symbol)

                    captured_output = output_buffer.getvalue()
                    if captured_output:
                        for line in captured_output.rstrip("\n").split("\n"):
                            rich.print(f"[green]{line}[/green]")

                return result
            finally:
                if source and source.strip():
                    auditor.record(source, exception=_exc_holder[0])

    _Console(locals=ns).interact(banner="", exitmsg="")
