from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Score(db.Model):
    __tablename__ = "score"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_score_user_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))
    awarded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    event: Mapped["Event"] = relationship("Event", foreign_keys=[event_id])
