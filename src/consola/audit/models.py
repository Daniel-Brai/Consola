"""
Models for audit logging of console sessions and commands.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

__all__ = ["AuditBase", "ConsolaSession", "ConsolaCommand"]


class AuditBase(DeclarativeBase):
    pass


class ConsolaSession(AuditBase):
    """
    One interactive console session
    """

    __tablename__ = "consola_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(256), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commands: Mapped[list[ConsolaCommand]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="select"
    )

    def end(self) -> None:
        self.ended_at = datetime.now()

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
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    raised_exception: Mapped[bool] = mapped_column(Boolean, default=False)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[ConsolaSession] = relationship(back_populates="commands")

    def __repr__(self) -> str:
        snip = self.source[:60].replace("\n", "↵")
        return f"<ConsolaCommand id={self.id} {snip!r}>"
