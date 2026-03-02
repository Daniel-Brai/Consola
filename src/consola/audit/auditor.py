"""
Audit subsystem records every consola session and command

Inspired by basecamp's audits1984 but without its review capabilities.
"""

from __future__ import annotations

import getpass
import os
from contextlib import AbstractContextManager
from typing import Any

from consola.audit.models import AuditBase, ConsolaCommand, ConsolaSession
from consola.session import BridgedSession, SessionBridge
from consola.types import AnyEngine

__all__ = ["Auditor", "AuditReader"]


def _current_user() -> str:
    return os.environ.get("CONSOLA_USER") or getpass.getuser()


class Auditor:
    """
    Records a single console session and all commands executed within it

    Example:

        with Auditor() as auditor:
            auditor.record("User.all()")
    """

    def __init__(self, engine: AnyEngine) -> None:
        from consola.session import resolve_sync_engine

        engine = resolve_sync_engine(engine)
        AuditBase.metadata.create_all(engine)

        self._engine = engine
        self._bridge = SessionBridge(engine)
        self._db_cm: AbstractContextManager[BridgedSession] | None = None
        self._db: BridgedSession | None = None
        self._console_session: ConsolaSession | None = None

    def __enter__(self) -> Auditor:
        self._db_cm = self._bridge()
        self._db = self._db_cm.__enter__()
        self._console_session = ConsolaSession(username=_current_user())
        self._db.add(self._console_session)
        self._db.commit()
        return self

    def __exit__(self, *_: object) -> None:
        if self._console_session and self._db:
            self._console_session.end()
            self._db.commit()
            try:
                self._db.close()
            finally:
                if self._db_cm:
                    self._db_cm.__exit__(None, None, None)
                self._db = None
                self._db_cm = None

    def record(self, source: str, exception: Any | None = None) -> None:
        if not self._db or not self._console_session:
            return

        cmd = ConsolaCommand(
            session_id=self._console_session.id,
            source=source,
            raised_exception=exception is not None,
            exception_message=str(exception) if exception else None,
        )
        self._db.add(cmd)
        self._db.commit()

    @property
    def session_id(self) -> int | None:
        return self._console_session.id if self._console_session else None


class AuditReader:
    """
    CLI level audit read interface
    """

    def __init__(self, engine: AnyEngine) -> None:
        from consola.session import resolve_sync_engine

        sync_engine = resolve_sync_engine(engine)
        self._engine = sync_engine
        self._bridge = SessionBridge(sync_engine)

    def _db(self):
        return self._bridge()

    def list_sessions(self, limit: int = 50) -> list[tuple[ConsolaSession, int]]:
        with self._db() as db:
            from sqlalchemy import func, select

            count_sub = (
                select(ConsolaCommand.session_id, func.count().label("cmd_count"))
                .group_by(ConsolaCommand.session_id)
                .subquery()
            )
            stmt = (
                select(ConsolaSession, func.coalesce(count_sub.c.cmd_count, 0))
                .outerjoin(count_sub, ConsolaSession.id == count_sub.c.session_id)
                .order_by(ConsolaSession.started_at.desc())
                .limit(limit)
            )
            return list(db.execute(stmt).all())

    def get_session(self, session_id: int) -> ConsolaSession | None:
        with self._db() as db:
            return db.get(ConsolaSession, session_id)
