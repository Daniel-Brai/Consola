"""
Session abstraction layer for Consola

It provides a uniform API over both synchronous and asynchronous SQLAlchemy sessions,
allowing the REPL to interact with the database without needing to worry about async/await or which type of session is being used.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import Any, Protocol, runtime_checkable

import anyio
import anyio.from_thread
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from consola.types import AnyEngine

__all__ = [
    "BridgedSession",
    "SessionBridge",
    "is_async",
    "tables_exist",
]


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

    if isinstance(engine, Engine):
        with engine.connect() as conn:
            return _check_sync(conn)
    else:

        async def _async() -> dict[str, bool]:
            async with engine.connect() as conn:
                return await conn.run_sync(_check_sync)

        return anyio.run(_async)


def is_async(engine: AnyEngine) -> bool:
    """
    Check if the given engine is asynchronous
    """
    return isinstance(engine, AsyncEngine)


@runtime_checkable
class BridgedSession(Protocol):
    """
    Protocol for the session bridge, providing a uniform API over both Session and AsyncSession
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
    Uniform sync-like session API over both Session and AsyncSession

    It internally bridges async sessions so the REPL never needs to await anything and can always call the same API.

    Example:

        bridge = SessionBridge(engine)
        with bridge() as ses:
            rows = ses.exec("SELECT 1")
    """

    def __init__(self, engine: AnyEngine) -> None:
        self._engine = engine
        self._async = isinstance(engine, AsyncEngine)
        self._factory: sessionmaker | async_sessionmaker

        if self._async:
            if not isinstance(engine, AsyncEngine):
                raise TypeError("Expected AsyncEngine for async SessionBridge")

            self._factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        else:
            if not isinstance(engine, Engine):
                raise TypeError("Expected Engine for sync SessionBridge")

            self._factory = sessionmaker(bind=engine, expire_on_commit=False)

    @contextlib.contextmanager
    def __call__(self) -> Generator[BridgedSession, None, None]:

        if self._async:
            if not isinstance(self._factory, async_sessionmaker):
                raise TypeError("SessionBridge factory is not an async_sessionmaker as expected")

            yield _AsyncBridgedSession(self._factory)
        else:
            if not isinstance(self._factory, sessionmaker):
                raise TypeError("SessionBridge factory is not a sessionmaker as expected")

            with self._factory() as raw:
                yield _SyncBridgedSession(raw)


class _SyncBridgedSession(BridgedSession):
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


class _AsyncBridgedSession(BridgedSession):
    """
    Asynchronous session bridge that runs all operations in the background thread, allowing the REPL to use a synchronous API
    """

    def __init__(self, factory: async_sessionmaker) -> None:
        self._factory = factory
        self._raw: AsyncSession = factory()

    def _run(self, coro: Any) -> Any:
        return anyio.from_thread.run(lambda: coro)

    def execute(self, stmt: Any, params: Any = None) -> Any:
        return self._run(self._raw.execute(stmt, params or {}))

    def scalar(self, stmt: Any) -> Any:
        return self._run(self._raw.scalar(stmt))

    def scalars(self, stmt: Any) -> Any:
        result = self._run(self._raw.scalars(stmt))
        return result

    def get(self, cls: type, pk: Any) -> Any:
        return self._run(self._raw.get(cls, pk))

    def add(self, obj: Any) -> None:
        self._raw.add(obj)

    def delete(self, obj: Any) -> None:
        self._run(self._raw.delete(obj))

    def flush(self) -> None:
        self._run(self._raw.flush())

    def commit(self) -> None:
        self._run(self._raw.commit())

    def rollback(self) -> None:
        self._run(self._raw.rollback())

    def close(self) -> None:
        self._run(self._raw.close())

    def refresh(self, obj: Any) -> None:
        self._run(self._raw.refresh(obj))

    @property
    def raw(self) -> AsyncSession:
        return self._raw
