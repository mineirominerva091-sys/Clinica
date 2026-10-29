from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column


db = SQLAlchemy()


class CallStatus(str, Enum):
    WAITING = "aguardando"
    CALLED = "chamado"
    FINISHED = "finalizado"
    CANCELED = "cancelado"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Call(db.Model):
    __tablename__ = "calls"
    __table_args__ = (
        CheckConstraint(
            "status IN ('aguardando', 'chamado', 'finalizado', 'cancelado')",
            name="ck_calls_status",
        ),
        Index(
            "ux_one_active_call",
            "status",
            unique=True,
            postgresql_where=text("status = 'chamado'"),
            sqlite_where=text("status = 'chamado'"),
        ),
        Index("ix_calls_waiting_order", "status", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(100), nullable=False)
    registration: Mapped[str] = mapped_column(String(40), nullable=False)
    room: Mapped[str] = mapped_column(String(60), nullable=False, default="Consultório")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=CallStatus.WAITING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    @property
    def event_token(self) -> str:
        called = self.called_at.isoformat() if self.called_at else ""
        return f"{self.id}:{called}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_name": self.patient_name,
            "registration": self.registration,
            "room": self.room,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "called_at": self.called_at.isoformat() if self.called_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "event_token": self.event_token,
        }
