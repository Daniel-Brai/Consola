"""
Session abstraction layer for Consola

It provides a uniform API over SQLAlchemy sessions.

When an AsyncEngine is supplied the underlying sync_engine is used,
so the REPL never has to deal with event loop or thread issues.
"""

from __future__ import annotations

import contextlib
import weakref
from collections.abc import Generator
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session, sessionmaker

from consola.types import AnyEngine

__all__ = [
    "BridgedSession",
    "SessionBridge",
    "is_async",
    "tables_exist",
    "resolve_sync_engine",
]


_ASYNC_TO_SYNC_DRIVER: dict[str, str] = {
    "asyncpg": "psycopg",
    "aiosqlite": "",
    "asyncmy": "pymysql",
    "aiomysql": "pymysql",
}

_sync_engine_cache: weakref.WeakValueDictionary[AsyncEngine, Engine] = weakref.WeakValueDictionary()


def resolve_sync_engine(engine: AnyEngine) -> Engine:
    """
    Create or retrieve a cached synchronous Engine corresponding to the given engine

    For an AsyncEngine the async DBAPI driver (asyncpg, aiosqlite, …) is
    replaced with its synchronous counterpart so that SQLAlchemy can open
    connections without needing an event loop or greenlet context.
    """

    if not isinstance(engine, AsyncEngine):
        return engine

    cached = _sync_engine_cache.get(engine)
    if cached is not None:
        return cached

    url = engine.url
    drivername = url.drivername

    if "+" in drivername:
        dialect, async_driver = drivername.split("+", 1)
        sync_driver = _ASYNC_TO_SYNC_DRIVER.get(async_driver, async_driver)
        new_drivername = f"{dialect}+{sync_driver}" if sync_driver else dialect
    else:
        new_drivername = drivername

    sync_url = url.set(drivername=new_drivername)
    sync_engine = create_engine(sync_url, pool_pre_ping=True)
    _sync_engine_cache[engine] = sync_engine

    return sync_engine


def tables_exist(engine: AnyEngine, table_names: list[str]) -> dict[str, bool]:
    """
    Check if the given tables exist in the database

    Returns:
        dict[str, bool]: Mapping of table name to existence (True if exists, False if not)
    """

    if not table_names:
        return {}

    def _check_sync(conn: Connection) -> dict[str, bool]:
        from sqlalchemy import inspect as sa_inspect

        insp = sa_inspect(conn)
        existing = set(insp.get_table_names())
        return {t: t in existing for t in table_names}

    with resolve_sync_engine(engine).connect() as conn:
        return _check_sync(conn)


def is_async(engine: AnyEngine) -> bool:
    """
    Check if the given engine is asynchronous
    """
    return isinstance(engine, AsyncEngine)


@runtime_checkable
class BridgedSession(Protocol):
    """
    Protocol for the session bridge, providing a uniform API over Session
    """

    def execute(self, stmt: Any, params: Any = None) -> Any: ...
    def scalar(self, stmt: Any) -> Any: ...
    def scalars(self, stmt: Any) -> Any: ...
    def get(self, cls: type, pk: Any) -> Any: ...
    def add(self, obj: Any) -> None: ...
    def delete(self, obj: Any) -> None: ...
    def flush(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def refresh(self, obj: Any) -> None: ...
    def close(self) -> None: ...


class SessionBridge:
    """
    Uniform sync session API over any engine (sync or async).

    When an AsyncEngine is passed its underlying sync_engine is used directly,
    which avoids all event-loop / asyncpg thread-affinity problems.

    Example:

        bridge = SessionBridge(engine)
        with bridge() as ses:
            rows = ses.scalars(select(User)).all()
    """

    def __init__(self, engine: AnyEngine) -> None:
        self._engine = engine
        self._async = isinstance(engine, AsyncEngine)
        sync_engine = resolve_sync_engine(engine)
        self._factory: sessionmaker = sessionmaker(bind=sync_engine, expire_on_commit=False)

    @contextlib.contextmanager
    def __call__(self) -> Generator[BridgedSession, None, None]:
        with self._factory() as raw:
            yield _SyncBridgedSession(raw)


class _SyncBridgedSession:
    """
    Synchronous session bridge that directly wraps a SQLAlchemy Session, providing the same API as the async bridge
    """

    def __init__(self, raw: Session) -> None:
        self._s = raw

    def execute(self, stmt: Any, params: Any = None) -> Any:
        return self._s.execute(stmt, params or {})

    def scalar(self, stmt: Any) -> Any:
        return self._s.scalar(stmt)

    def scalars(self, stmt: Any) -> Any:
        return self._s.scalars(stmt)

    def get(self, cls: type, pk: Any) -> Any:
        return self._s.get(cls, pk)

    def add(self, obj: Any) -> None:
        self._s.add(obj)

    def delete(self, obj: Any) -> None:
        self._s.delete(obj)

    def flush(self) -> None:
        self._s.flush()

    def commit(self) -> None:
        self._s.commit()

    def rollback(self) -> None:
        self._s.rollback()

    def refresh(self, obj: Any) -> None:
        self._s.refresh(obj)

    def close(self) -> None:
        self._s.close()
