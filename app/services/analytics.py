from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import func, select
from app.extensions import db
from app.models.event import Event
from app.models.registration import Registration
from app.models.attendance import Attendance


@dataclass(frozen=True)
class EventAnalytic:
    event_id: int
    title: str
    date: str
    category: str
    total_registrations: int
    total_present: int
    total_absent: int
    attendance_rate: float   # 0.0 – 100.0


@dataclass(frozen=True)
class CategoryStat:
    category: str
    count: int


def get_event_analytics() -> Sequence[EventAnalytic]:
    """Return per-event analytics ordered by event date descending."""
    events = db.session.scalars(
        select(Event).order_by(Event.date.desc())
    ).all()

    results: list[EventAnalytic] = []
    for event in events:
        total_reg = db.session.scalar(
            select(func.count(Registration.id)).where(
                Registration.event_id == event.id
            )
        ) or 0

        total_present = db.session.scalar(
            select(func.count(Attendance.id)).where(
                Attendance.event_id == event.id,
                Attendance.status == "present",
            )
        ) or 0

        total_absent = db.session.scalar(
            select(func.count(Attendance.id)).where(
                Attendance.event_id == event.id,
                Attendance.status == "absent",
            )
        ) or 0

        rate = round(total_present / total_reg * 100, 1) if total_reg else 0.0

        results.append(EventAnalytic(
            event_id=event.id,
            title=event.title,
            date=event.date.strftime("%d %b %Y"),
            category=event.category or "Uncategorised",
            total_registrations=total_reg,
            total_present=total_present,
            total_absent=total_absent,
            attendance_rate=rate,
        ))

    return results


def get_category_stats() -> Sequence[CategoryStat]:
    """Return registration counts grouped by event category."""
    rows = db.session.execute(
        select(
            Event.category,
            func.count(Registration.id).label("cnt"),
        )
        .outerjoin(Registration, Registration.event_id == Event.id)
        .group_by(Event.category)
        .order_by(func.count(Registration.id).desc())
    ).all()

    return [
        CategoryStat(
            category=row.category or "Uncategorised",
            count=row.cnt,
        )
        for row in rows
    ]

