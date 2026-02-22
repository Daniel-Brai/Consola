"""
Models for audit logging of console sessions and commands.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from consola.types import AnyEngine

__all__ = ["AuditBase", "ConsolaSession", "ConsolaCommand", "get_audit_engine"]

_audit_engine: AnyEngine | None = None  # noqa: F821


def get_audit_engine(url: str = "sqlite:///consola_audit.db"):
    global _audit_engine
    if _audit_engine is None:
        from sqlalchemy import create_engine

        _audit_engine = create_engine(url, echo=False)
        AuditBase.metadata.create_all(_audit_engine)
    return _audit_engine


class AuditBase(DeclarativeBase):
    pass


class ConsolaSession(AuditBase):
    """
    One interactive console session
    """

    __tablename__ = "consola_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=datetime.now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    commands: Mapped[list[ConsolaCommand]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )

    def end(self) -> None:
        self.ended_at = datetime.now()

    def approve(self, notes: str = "") -> None:
        self.reviewed = True
        self.approved = True
        self.reviewer_notes = notes

    def flag(self, notes: str = "") -> None:
        self.reviewed = True
        self.approved = False
        self.reviewer_notes = notes

    def duration_seconds(self) -> float | None:
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None

    def __repr__(self) -> str:
        return (
            f"<ConsolaSession id={self.id} user={self.username!r} "
            f"started={self.started_at.isoformat() if self.started_at else '?'}>"
        )


class ConsolaCommand(AuditBase):
    """
    One line of Python executed inside a session
    """

    __tablename__ = "consola_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("consola_sessions.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default_factory=datetime.now)
    raised_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[ConsolaSession] = relationship(back_populates="commands")

    def __repr__(self) -> str:
        snip = self.source[:60].replace("\n", "↵")
        return f"<ConsolaCommand id={self.id} {snip!r}>"
