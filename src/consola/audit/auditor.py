"""
Audit subsystem records every consola session and command

Inspired by basecamp's audits1984 but without its review capabilities.
"""

from __future__ import annotations

import getpass
import os
from contextlib import AbstractContextManager
from typing import Any

from consola.audit.models import ConsolaCommand, ConsolaSession, get_audit_engine
from consola.session import BridgedSession, SessionBridge

__all__ = ["Auditor", "AuditReviewer"]


def _current_user() -> str:
    return os.environ.get("CONSOLA_USER") or getpass.getuser()


class Auditor:
    """
    Records a single console session and all commands executed within it

    Example:

        with Auditor() as auditor:
            auditor.record("User.all()")
    """

    def __init__(self, audit_db_url: str = "sqlite:///consola_audit.db") -> None:
        self._engine = get_audit_engine(audit_db_url)
        self._bridge = SessionBridge(self._engine)
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


class AuditReviewer:
    """
    CLI-level audit review interface
    """

    def __init__(self, audit_db_url: str = "sqlite:///consola_audit.db") -> None:
        self._engine = get_audit_engine(audit_db_url)
        self._bridge = SessionBridge(self._engine)

    def _db(self):
        return self._bridge()

    def list_sessions(self, pending_only: bool = False, limit: int = 50) -> list[ConsolaSession]:
        with self._db() as db:
            from sqlalchemy import select

            stmt = select(ConsolaSession).order_by(ConsolaSession.started_at.desc()).limit(limit)
            if pending_only:
                stmt = stmt.where(ConsolaSession.reviewed.is_(False))

            return list(db.scalars(stmt).all())

    def get_session(self, session_id: int) -> ConsolaSession | None:
        with self._db() as db:
            return db.get(ConsolaSession, session_id)

    def approve(self, session_id: int, notes: str = "") -> bool:
        with self._db() as db:
            s = db.get(ConsolaSession, session_id)
            if s is None:
                return False
            s.approve(notes)
            db.commit()
            return True

    def flag(self, session_id: int, notes: str = "") -> bool:
        with self._db() as db:
            s = db.get(ConsolaSession, session_id)
            if s is None:
                return False
            s.flag(notes)
            db.commit()
            return True

    def pending_count(self) -> int:
        with self._db() as db:
            from sqlalchemy import func, select

            return (
                db.scalar(select(func.count()).select_from(ConsolaSession).where(ConsolaSession.reviewed.is_(False)))
                or 0
            )
