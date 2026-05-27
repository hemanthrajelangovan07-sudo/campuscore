from __future__ import annotations

from typing import Sequence

from sqlalchemy import select

from app.extensions import db, socketio
from app.models.announcement import Announcement

# Valid priority values — reject anything else at the service boundary
VALID_PRIORITIES = frozenset({"info", "warning", "urgent"})


# ── Reads ──────────────────────────────────────────────────────────────────


def get_all_announcements() -> Sequence[Announcement]:
    """All announcements newest-first (used by admin / organizer views)."""
    return db.session.scalars(
        select(Announcement).order_by(Announcement.created_at.desc())
    ).all()


def get_unread_count(last_seen_id: int | None) -> int:
    """
    Count announcements newer than last_seen_id.
    Used to render the unread badge on the nav link.
    Stored in the user's session as `session['ann_last_seen']`.
    """
    if last_seen_id is None:
        return db.session.scalar(
            select(db.func.count(Announcement.id))
        ) or 0

    return db.session.scalar(
        select(db.func.count(Announcement.id)).where(
            Announcement.id > last_seen_id
        )
    ) or 0


def mark_all_read() -> int:
    """Return the id of the latest announcement (to store in session)."""
    latest = db.session.scalar(
        select(Announcement.id).order_by(Announcement.id.desc()).limit(1)
    )
    return latest or 0


# ── Writes ─────────────────────────────────────────────────────────────────


def create_announcement(
    message: str,
    priority: str,
    author_id: int,
) -> Announcement:
    """
    Persist a new announcement and broadcast it live to all connected clients.

    Raises ValueError on invalid input so the route can flash a user-friendly
    message without catching generic exceptions.
    """
    message = message.strip()
    if not message:
        raise ValueError("Announcement message cannot be empty.")
    if len(message) > 1000:
        raise ValueError("Announcement must be 1000 characters or fewer.")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority!r}.")

    ann = Announcement(message=message, priority=priority, created_by=author_id)
    db.session.add(ann)
    db.session.commit()

    # Broadcast to all connected clients after successful commit
    socketio.emit("new_announcement", ann.to_socket_payload())
    return ann


def delete_announcement(ann_id: int, requestor_id: int, requestor_role: str) -> None:
    """
    Delete an announcement.

    Permission rules enforced here (not in the route) so they stay consistent
    regardless of how the endpoint is called:
      - admin  -> can delete anything
      - organizer -> can only delete their own
    """
    ann = db.session.get(Announcement, ann_id)
    if ann is None:
        raise ValueError("Announcement not found.")

    if requestor_role == "organizer" and ann.created_by != requestor_id:
        raise PermissionError("Organizers can only delete their own announcements.")

    db.session.delete(ann)
    db.session.commit()
