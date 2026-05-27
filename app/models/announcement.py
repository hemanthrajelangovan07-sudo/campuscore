from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

PriorityType = Literal["info", "warning", "urgent"]


class Announcement(db.Model):
    __tablename__ = "announcement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    message: Mapped[str] = mapped_column(Text, nullable=False)

    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default="info"
    )  # 'info' | 'warning' | 'urgent'

    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────
    author: Mapped["User"] = relationship(
        "User", foreign_keys=[created_by], lazy="joined"
    )

    # ── Helpers ───────────────────────────────────────────────────────
    @property
    def priority_label(self) -> str:
        return {"info": "Info", "warning": "Warning", "urgent": "Urgent"}.get(
            self.priority, "Info"
        )

    @property
    def priority_colour(self) -> str:
        """Bootstrap contextual colour for this priority."""
        return {"info": "primary", "warning": "warning", "urgent": "danger"}.get(
            self.priority, "primary"
        )

    @property
    def author_name(self) -> str:
        return self.author.name if self.author else "System"

    @property
    def author_role(self) -> str:
        return self.author.role if self.author else "system"

    def formatted_time(self) -> str:
        return self.created_at.strftime("%d %b %Y · %H:%M")

    def to_socket_payload(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "priority": self.priority,
            "priority_label": self.priority_label,
            "priority_colour": self.priority_colour,
            "author": self.author_name,
            "author_role": self.author_role,
            "time": self.formatted_time(),
        }
