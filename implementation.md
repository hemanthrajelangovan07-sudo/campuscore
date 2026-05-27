# CampusCore × Univent — Feature Parity Implementation Plan

**Source repo:** [campuscore](https://github.com/Vaishnavi-kumaresan/campuscore)  
**Reference repo:** [Univent](https://github.com/AbhishekBalija/Univent-College_Event_Management_System)  
**Stack:** Python 3.11 · Flask 3 · SQLAlchemy 2 · Flask-Migrate · Flask-SocketIO · Flask-WTF · Jinja2 · Bootstrap 5

---

## Architecture Ground Rules

Before touching any phase, understand the structural constraints:

1. **Do not write routes directly in `app.py`.** Each feature lives in its own Blueprint under `app/blueprints/`.
2. **Do not query the DB from templates or route handlers.** All DB logic goes through a `services/` module.
3. **Do not use raw SQL migrations.** Use `flask db migrate` + `flask db upgrade`.
4. **Do not emit SocketIO events from route handlers directly.** Emit from the service layer so logic is testable.
5. **All forms must carry a CSRF token** (Flask-WTF handles this automatically when `WTF_CSRF_ENABLED = True`).

### Target project structure after all four phases

```
app/
├── __init__.py              ← create_app() factory
├── extensions.py            ← db, migrate, socketio, csrf singletons
├── models/
│   ├── __init__.py
│   ├── event.py
│   ├── user.py
│   ├── registration.py
│   ├── attendance.py
│   ├── announcement.py      ← Phase 2
│   └── score.py             ← Phase 4
├── services/
│   ├── analytics.py         ← Phase 1
│   ├── announcements.py     ← Phase 2
│   ├── notifications.py     ← Phase 3
│   └── leaderboard.py       ← Phase 4
├── blueprints/
│   ├── admin/
│   │   ├── __init__.py
│   │   ├── analytics.py     ← Phase 1
│   │   ├── announcements.py ← Phase 2
│   │   └── leaderboard.py   ← Phase 4
│   └── student/
│       └── leaderboard.py   ← Phase 4
├── sockets/
│   ├── __init__.py
│   ├── announcements.py     ← Phase 2
│   └── notifications.py     ← Phase 3
└── templates/
    ├── base.html
    ├── admin/
    │   ├── analytics.html
    │   ├── announcements.html
    │   └── leaderboard.html
    └── student/
        └── leaderboard.html
```

---

## Feature Map

| Univent Feature | CampusCore Status | Implemented by |
|---|---|---|
| Create / Edit / Delete events | ✅ Exists | — |
| View participants per event | ✅ Exists | — |
| Mark attendance | ✅ Exists | — |
| Event Analytics Dashboard | ❌ Missing | Phase 1 |
| Real-time Announcements | ❌ Missing | Phase 2 |
| Real-time Notifications | ❌ Missing | Phase 3 |
| Gamified Leaderboard | ❌ Missing | Phase 4 |

> **Both Admin and Organizer roles** share identical access to Phases 1–4.  
> The `@roles_required('admin', 'organizer')` decorator (added in §0) enforces this uniformly.

---

## Phase 0 — Structural Prerequisites (do once, before any phase)

These changes are required by every phase. Run them first.

### 0.1 Install dependencies

```bash
pip install flask-migrate flask-wtf flask-socketio eventlet
```

Update `requirements.txt`:
```
Flask>=3.0
Flask-SQLAlchemy>=3.1
Flask-Migrate>=4.0
Flask-WTF>=1.2
Flask-SocketIO>=5.3
eventlet>=0.35
```

### 0.2 Create `app/extensions.py`

This file holds every Flask extension as a module-level singleton so that
`create_app()` can call `.init_app()` on them without circular imports.

```python
# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()
```

### 0.3 Update `app/__init__.py` — register extensions and blueprints

```python
# app/__init__.py
from flask import Flask
from .extensions import db, migrate, socketio, csrf


def create_app(config_object="app.config.Config") -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    # ── Extensions ────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    socketio.init_app(
        app,
        async_mode="eventlet",
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ORIGINS", "*"),
    )

    # ── Models (import so Migrate can see them) ────────────────────────────
    from app.models import event, user, registration, attendance  # noqa: F401

    # ── Blueprints registered in later phases ─────────────────────────────
    # (Each phase's OpenCode prompt registers its blueprint here)

    # ── SocketIO namespaces registered in later phases ────────────────────

    return app
```

### 0.4 Add `roles_required` decorator to `app/utils/auth.py`

The existing codebase likely has an `admin_required` decorator. Replace it
with a generalised version that accepts multiple roles so organizers and
admins get identical access.

```python
# app/utils/auth.py
from functools import wraps
from flask import session, abort


def roles_required(*roles: str):
    """Restrict a view to users whose role is in *roles*.

    Usage::

        @app.route('/admin/analytics')
        @roles_required('admin', 'organizer')
        def admin_analytics(): ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            role = session.get("role")
            if role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

### 0.5 Update `run.py`

```python
# run.py
from app import create_app
from app.extensions import socketio

app = create_app()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
```

---

## Phase 1 — Event Analytics Dashboard

### What it adds
A dedicated analytics page for admins/organizers showing per-event
registration counts, attendance rates, and a Chart.js bar chart of
registrations grouped by category. Zero raw SQL — all queries use
SQLAlchemy 2 ORM constructs.

---

### 1.1 Create `app/services/analytics.py`

```python
# app/services/analytics.py
"""
Analytics service — all DB reads for the analytics dashboard.

Keeping queries here (instead of in the route) means the same data
can be consumed by a future REST API or background job without
duplicating logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
```

---

### 1.2 Create `app/blueprints/admin/analytics.py`

```python
# app/blueprints/admin/analytics.py
from flask import Blueprint, render_template, session

from app.services.analytics import get_event_analytics, get_category_stats
from app.utils.auth import roles_required

bp = Blueprint("admin_analytics", __name__, url_prefix="/admin")


@bp.route("/analytics")
@roles_required("admin", "organizer")
def analytics():
    event_analytics = get_event_analytics()
    category_stats = get_category_stats()

    return render_template(
        "admin/analytics.html",
        event_analytics=event_analytics,
        cat_labels=[s.category for s in category_stats],
        cat_counts=[s.count for s in category_stats],
    )
```

---

### 1.3 Register the blueprint — add to `app/__init__.py` inside `create_app()`

```python
    # inside create_app(), under "Blueprints registered in later phases"
    from app.blueprints.admin.analytics import bp as analytics_bp
    app.register_blueprint(analytics_bp)
```

---

### 1.4 Create `app/templates/admin/analytics.html`

```html
{% extends 'base.html' %}

{% block title %}Event Analytics{% endblock %}

{% block content %}
<div class="container-fluid py-4">

  {# ── Page header ──────────────────────────────────────────────────── #}
  <div class="d-flex align-items-center gap-3 mb-4">
    <div class="rounded-3 p-2 bg-primary bg-opacity-10">
      <i class="fas fa-chart-bar fa-lg text-primary"></i>
    </div>
    <div>
      <h4 class="mb-0 fw-semibold">Event Analytics</h4>
      <p class="text-muted small mb-0">Registration and attendance overview across all events</p>
    </div>
  </div>

  {# ── Summary KPI cards ────────────────────────────────────────────── #}
  {% set total_events = event_analytics | length %}
  {% set total_regs   = event_analytics | sum(attribute='total_registrations') %}
  {% set total_pres   = event_analytics | sum(attribute='total_present') %}
  {% set avg_rate     = (event_analytics | sum(attribute='attendance_rate') / total_events) | round(1) if total_events else 0 %}

  <div class="row g-3 mb-4">
    {% for label, value, icon, colour in [
        ('Total Events',       total_events, 'fa-calendar-alt', 'primary'),
        ('Total Registrations',total_regs,   'fa-user-check',   'info'),
        ('Total Attendees',    total_pres,   'fa-users',        'success'),
        ('Avg Attendance Rate',avg_rate ~ '%','fa-percent',     'warning'),
    ] %}
    <div class="col-sm-6 col-xl-3">
      <div class="card border-0 shadow-sm h-100">
        <div class="card-body d-flex align-items-center gap-3">
          <div class="rounded-circle p-3 bg-{{ colour }} bg-opacity-10 flex-shrink-0">
            <i class="fas {{ icon }} fa-lg text-{{ colour }}"></i>
          </div>
          <div>
            <div class="fs-3 fw-bold">{{ value }}</div>
            <div class="text-muted small">{{ label }}</div>
          </div>
        </div>
      </div>
    </div>
    {% endfor %}
  </div>

  {# ── Category chart ───────────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm mb-4">
    <div class="card-header bg-transparent border-bottom-0 pt-3 pb-0">
      <h6 class="fw-semibold mb-0">Registrations by Category</h6>
    </div>
    <div class="card-body" style="height: 280px;">
      <canvas id="catChart"></canvas>
    </div>
  </div>

  {# ── Per-event table ──────────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm">
    <div class="card-header bg-transparent border-bottom-0 pt-3 pb-0 d-flex justify-content-between align-items-center">
      <h6 class="fw-semibold mb-0">Per-Event Breakdown</h6>
      <input type="search" id="tableSearch" class="form-control form-control-sm w-auto"
             placeholder="Search events…">
    </div>
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0" id="analyticsTable">
          <thead class="table-light">
            <tr>
              <th class="ps-3">Event</th>
              <th>Category</th>
              <th>Date</th>
              <th class="text-center">Registrations</th>
              <th class="text-center">Present</th>
              <th class="text-center">Absent</th>
              <th style="min-width: 180px;">Attendance Rate</th>
            </tr>
          </thead>
          <tbody>
            {% for a in event_analytics %}
            <tr>
              <td class="ps-3 fw-medium">{{ a.title }}</td>
              <td>
                <span class="badge text-bg-secondary fw-normal">{{ a.category }}</span>
              </td>
              <td class="text-muted small">{{ a.date }}</td>
              <td class="text-center">{{ a.total_registrations }}</td>
              <td class="text-center">
                <span class="badge text-bg-success">{{ a.total_present }}</span>
              </td>
              <td class="text-center">
                <span class="badge text-bg-danger">{{ a.total_absent }}</span>
              </td>
              <td>
                <div class="d-flex align-items-center gap-2">
                  <div class="progress flex-grow-1" style="height: 8px;" role="progressbar"
                       aria-valuenow="{{ a.attendance_rate }}" aria-valuemin="0" aria-valuemax="100">
                    <div class="progress-bar
                      {% if a.attendance_rate >= 75 %}bg-success
                      {% elif a.attendance_rate >= 50 %}bg-warning
                      {% else %}bg-danger{% endif %}"
                      style="width: {{ a.attendance_rate }}%">
                    </div>
                  </div>
                  <span class="small text-muted text-nowrap">{{ a.attendance_rate }}%</span>
                </div>
              </td>
            </tr>
            {% else %}
            <tr>
              <td colspan="7" class="text-center text-muted py-4">No events found.</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>
{% endblock %}

{% block scripts %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
(function () {
  'use strict';

  // ── Category chart ───────────────────────────────────────────────────
  const catLabels = {{ cat_labels | tojson }};
  const catCounts = {{ cat_counts | tojson }};

  const palette = [
    '#3b82f6','#10b981','#f59e0b','#ef4444',
    '#8b5cf6','#06b6d4','#ec4899','#14b8a6',
  ];

  new Chart(document.getElementById('catChart'), {
    type: 'bar',
    data: {
      labels: catLabels,
      datasets: [{
        label: 'Registrations',
        data: catCounts,
        backgroundColor: catLabels.map((_, i) => palette[i % palette.length]),
        borderRadius: 6,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.parsed.y} registrations`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { stepSize: 1 },
          grid: { color: 'rgba(0,0,0,0.05)' },
        },
        x: { grid: { display: false } },
      },
    },
  });

  // ── Live table search ────────────────────────────────────────────────
  document.getElementById('tableSearch').addEventListener('input', function () {
    const term = this.value.toLowerCase();
    document.querySelectorAll('#analyticsTable tbody tr').forEach(row => {
      row.style.display = row.textContent.toLowerCase().includes(term) ? '' : 'none';
    });
  });
})();
</script>
{% endblock %}
```

---

### 1.5 Add nav link in `templates/base.html` — admin/organizer sidebar

```html
<a href="{{ url_for('admin_analytics.analytics') }}"
   class="nav-link {{ 'active' if request.endpoint == 'admin_analytics.analytics' }}">
  <i class="fas fa-chart-bar me-2"></i>Analytics
</a>
```

---

## Phase 2 — Real-time Announcements

### What it adds
Admin/organizer broadcasts announcements stored in the DB.  
All connected clients receive a dismissible floating banner via SocketIO.  
Past announcements are shown with timestamps and delete controls.

---

### 2.1 Create `app/models/announcement.py`

```python
# app/models/announcement.py
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


class Announcement(db.Model):
    __tablename__ = "announcement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    author: Mapped["User"] = relationship("User", foreign_keys=[created_by])  # noqa: F821

    def to_socket_payload(self) -> dict:
        return {
            "id": self.id,
            "message": self.message,
            "time": self.created_at.strftime("%d %b %Y %H:%M"),
            "author": self.author.name if self.author else "System",
        }
```

---

### 2.2 Create `app/services/announcements.py`

```python
# app/services/announcements.py
"""
Announcement service — keeps all business logic and SocketIO emission
out of the route handler so the route stays thin and testable.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select

from app.extensions import db, socketio
from app.models.announcement import Announcement


def get_all_announcements() -> Sequence[Announcement]:
    return db.session.scalars(
        select(Announcement).order_by(Announcement.created_at.desc())
    ).all()


def create_announcement(message: str, author_id: int) -> Announcement:
    """Persist a new announcement and broadcast it to all connected clients."""
    announcement = Announcement(message=message, created_by=author_id)
    db.session.add(announcement)
    db.session.commit()

    # Emit after commit so the id is available
    socketio.emit("new_announcement", announcement.to_socket_payload())
    return announcement


def delete_announcement(announcement_id: int) -> None:
    announcement = db.session.get(Announcement, announcement_id)
    if announcement is None:
        raise ValueError(f"Announcement {announcement_id} not found")
    db.session.delete(announcement)
    db.session.commit()
```

---

### 2.3 Create `app/blueprints/admin/announcements.py`

```python
# app/blueprints/admin/announcements.py
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.services.announcements import (
    create_announcement,
    delete_announcement,
    get_all_announcements,
)
from app.utils.auth import roles_required

bp = Blueprint("admin_announcements", __name__, url_prefix="/admin")


@bp.route("/announcements", methods=["GET", "POST"])
@roles_required("admin", "organizer")
def announcements():
    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if not message:
            flash("Announcement message cannot be empty.", "warning")
            return redirect(url_for("admin_announcements.announcements"))

        if len(message) > 1000:
            flash("Announcement must be 1000 characters or fewer.", "warning")
            return redirect(url_for("admin_announcements.announcements"))

        create_announcement(message=message, author_id=session["user_id"])
        flash("Announcement sent to all connected users.", "success")
        return redirect(url_for("admin_announcements.announcements"))

    return render_template(
        "admin/announcements.html",
        announcements=get_all_announcements(),
    )


@bp.post("/announcements/<int:ann_id>/delete")
@roles_required("admin", "organizer")
def delete(ann_id: int):
    try:
        delete_announcement(ann_id)
        flash("Announcement deleted.", "info")
    except ValueError:
        flash("Announcement not found.", "danger")
    return redirect(url_for("admin_announcements.announcements"))
```

---

### 2.4 Register the blueprint — add to `app/__init__.py`

```python
    from app.blueprints.admin.announcements import bp as announcements_bp
    app.register_blueprint(announcements_bp)
```

### 2.5 Run the migration

```bash
flask db migrate -m "add announcement table"
flask db upgrade
```

---

### 2.6 Create `app/templates/admin/announcements.html`

```html
{% extends 'base.html' %}

{% block title %}Announcements{% endblock %}

{% block content %}
<div class="container-fluid py-4">

  <div class="d-flex align-items-center gap-3 mb-4">
    <div class="rounded-3 p-2 bg-warning bg-opacity-10">
      <i class="fas fa-bullhorn fa-lg text-warning"></i>
    </div>
    <div>
      <h4 class="mb-0 fw-semibold">Announcements</h4>
      <p class="text-muted small mb-0">Broadcast messages are pushed live to all connected students</p>
    </div>
  </div>

  {# ── Compose form ─────────────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
      <h6 class="fw-semibold mb-3">Broadcast New Announcement</h6>
      <form method="POST" action="{{ url_for('admin_announcements.announcements') }}"
            id="announceForm" novalidate>
        {{ csrf_token() }}  {# Flask-WTF global CSRF token #}
        <div class="mb-3">
          <textarea name="message" id="message" class="form-control" rows="3"
                    maxlength="1000" placeholder="Write your announcement…"
                    required></textarea>
          <div class="d-flex justify-content-between mt-1">
            <div class="invalid-feedback d-block" id="msgError" style="display:none!important"></div>
            <small class="text-muted ms-auto"><span id="charCount">0</span> / 1000</small>
          </div>
        </div>
        <button type="submit" class="btn btn-primary">
          <i class="fas fa-paper-plane me-2"></i>Send to All Students
        </button>
      </form>
    </div>
  </div>

  {# ── History ──────────────────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm">
    <div class="card-header bg-transparent border-bottom-0 pt-3 pb-0">
      <h6 class="fw-semibold mb-0">Announcement History</h6>
    </div>
    <div class="card-body">
      {% if announcements %}
        {% for ann in announcements %}
        <div class="d-flex gap-3 align-items-start border rounded-3 p-3 mb-3 bg-light bg-opacity-50">
          <div class="flex-grow-1">
            <p class="mb-1">{{ ann.message }}</p>
            <small class="text-muted">
              <i class="far fa-clock me-1"></i>{{ ann.created_at.strftime('%d %b %Y %H:%M') }}
              {% if ann.author %}
                &nbsp;·&nbsp;<i class="far fa-user me-1"></i>{{ ann.author.name }}
              {% endif %}
            </small>
          </div>
          <form method="POST"
                action="{{ url_for('admin_announcements.delete', ann_id=ann.id) }}"
                onsubmit="return confirm('Delete this announcement?')">
            {{ csrf_token() }}
            <button type="submit" class="btn btn-sm btn-outline-danger" title="Delete">
              <i class="fas fa-trash-alt"></i>
            </button>
          </form>
        </div>
        {% endfor %}
      {% else %}
        <p class="text-muted text-center py-3">No announcements yet.</p>
      {% endif %}
    </div>
  </div>

</div>
{% endblock %}

{% block scripts %}
<script>
  const textarea = document.getElementById('message');
  const counter  = document.getElementById('charCount');
  textarea.addEventListener('input', () => {
    counter.textContent = textarea.value.length;
  });
</script>
{% endblock %}
```

---

### 2.7 Add SocketIO banner to `templates/base.html` — before `</body>`

Place this block once, globally, so every page receives announcements:

```html
{# ── Global SocketIO ───────────────────────────────────────────────── #}
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"
        integrity="sha384-..." crossorigin="anonymous"></script>
<script>
(function () {
  'use strict';

  const socket = window._socket = io({ transports: ['websocket', 'polling'] });

  // ── Announcement banner ──────────────────────────────────────────────
  socket.on('new_announcement', function (data) {
    showBanner(data.message, data.time, data.author);
  });

  function showBanner(message, time, author) {
    const el = document.createElement('div');
    el.className =
      'alert alert-warning alert-dismissible fade show shadow position-fixed';
    el.style.cssText =
      'top:72px;right:20px;z-index:9999;max-width:400px;border-left:4px solid #f59e0b;';
    el.setAttribute('role', 'alert');
    el.innerHTML = `
      <div class="d-flex gap-2 align-items-start">
        <i class="fas fa-bullhorn mt-1 text-warning flex-shrink-0"></i>
        <div>
          <strong class="d-block mb-1">New Announcement</strong>
          <p class="mb-1 small">${escHtml(message)}</p>
          <span class="text-muted" style="font-size:.75rem">${escHtml(time)} · ${escHtml(author)}</span>
        </div>
      </div>
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 10_000);
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
})();
</script>
```

---

### 2.8 Add nav link in `templates/base.html` — admin/organizer sidebar

```html
<a href="{{ url_for('admin_announcements.announcements') }}"
   class="nav-link {{ 'active' if request.endpoint and 'announcement' in request.endpoint }}">
  <i class="fas fa-bullhorn me-2"></i>Announcements
</a>
```

---

## Phase 3 — Real-time Notifications

### What it adds
Students receive instant toast notifications when:
- A new event is published (broadcast to all students)
- Their own attendance is marked **present** (targeted to that user's SocketIO room)

Targeting is implemented with **SocketIO rooms** — each logged-in user joins a
private room named `user_<id>` on connect. This avoids broadcasting private
data to every client.

---

### 3.1 Create `app/sockets/notifications.py`

```python
# app/sockets/notifications.py
"""
SocketIO event handlers for the notifications namespace.

Clients join a personal room on connect so the server can target
individual users without broadcasting private data to everyone.
"""
from flask import session
from flask_socketio import join_room

from app.extensions import socketio


@socketio.on("connect")
def on_connect():
    user_id = session.get("user_id")
    if user_id:
        # Each authenticated user gets a private room: "user_<id>"
        join_room(f"user_{user_id}")
```

---

### 3.2 Register the socket handler — add to `app/__init__.py`

```python
    # inside create_app(), under "SocketIO namespaces registered in later phases"
    from app.sockets import notifications  # noqa: F401 — registers handlers via decorator
```

---

### 3.3 Create `app/services/notifications.py`

```python
# app/services/notifications.py
"""
Notification helpers used by other services.

Keeping emit calls here means route handlers and other services
never import socketio directly — only this module does.
"""
from app.extensions import socketio


def notify_new_event(title: str, date: str, venue: str) -> None:
    """Broadcast a 'new event published' notification to all connected clients."""
    socketio.emit("notification", {
        "type": "event_created",
        "title": "New Event Published",
        "body": f"{title} · {date} at {venue or 'TBD'}",
    })


def notify_attendance_marked(user_id: int, event_title: str) -> None:
    """Send an attendance confirmation only to the specific student."""
    socketio.emit("notification", {
        "type": "attendance_marked",
        "title": "Attendance Confirmed ✓",
        "body": f'You are marked Present for "{event_title}". Your certificate is ready.',
    }, to=f"user_{user_id}")
```

---

### 3.4 Integrate into existing route handlers in `app.py` (or existing blueprint)

Find the existing `create_event` route and add **after** `db.session.commit()`:

```python
from app.services.notifications import notify_new_event

# after db.session.commit():
notify_new_event(
    title=event.title,
    date=event.date.strftime("%d %b %Y"),
    venue=getattr(event, "venue", None) or "TBD",
)
```

Find the existing `manage_attendance` route and add **after** `db.session.commit()`:

```python
from app.services.notifications import notify_attendance_marked

# inside the loop after commit, only for students marked present:
for reg, student in registrations:
    if request.form.get(f"attendance_{student.id}") == "present":
        notify_attendance_marked(
            user_id=student.id,
            event_title=event.title,
        )
```

---

### 3.5 Add toast renderer to `templates/base.html` — inside the existing `<script>` block

Append inside the `(function() { ... })()` IIFE added in Phase 2:

```javascript
  // ── Personal notifications (event created, attendance marked) ────────
  socket.on('notification', function (data) {
    showToast(data.title, data.body, data.type);
  });

  function showToast(title, body, type) {
    const accent = {
      event_created:      '#3b82f6',
      attendance_marked:  '#10b981',
    }[type] || '#6b7280';

    const container = document.createElement('div');
    container.className = 'position-fixed p-3';
    container.style.cssText = 'bottom:20px;right:20px;z-index:9999;min-width:300px;';
    container.innerHTML = `
      <div class="toast show shadow" role="alert"
           style="border-left:4px solid ${accent};border-radius:10px;">
        <div class="toast-header border-0 pb-0">
          <span class="me-auto fw-semibold" style="color:${accent}">${escHtml(title)}</span>
          <button type="button" class="btn-close btn-close-sm"
                  onclick="this.closest('.position-fixed').remove()"></button>
        </div>
        <div class="toast-body pt-1 text-muted small">${escHtml(body)}</div>
      </div>`;
    document.body.appendChild(container);
    setTimeout(() => container.remove(), 7_000);
  }
```

---

## Phase 4 — Gamified Leaderboard

### What it adds
- Admin/organizer assigns points to students per event with an optional reason
- A top-3 podium + full ranked table updates in real time via SocketIO
- Students see a read-only view with their own row highlighted
- One unique constraint prevents double-awarding the same student for the same event

---

### 4.1 Create `app/models/score.py`

```python
# app/models/score.py
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

    student: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # noqa: F821
    event: Mapped["Event"] = relationship("Event", foreign_keys=[event_id])  # noqa: F821
```

---

### 4.2 Create `app/services/leaderboard.py`

```python
# app/services/leaderboard.py
"""
Leaderboard service.

All leaderboard reads and writes go through here so the SocketIO
broadcast is always consistent with what's in the database.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from app.extensions import db, socketio
from app.models.score import Score
from app.models.user import User


@dataclass(frozen=True)
class LeaderboardEntry:
    user_id: int
    name: str
    department: str
    total_points: int
    rank: int


def get_leaderboard() -> list[LeaderboardEntry]:
    rows = db.session.execute(
        select(
            User.id,
            User.name,
            User.department,
            func.coalesce(func.sum(Score.points), 0).label("total"),
        )
        .outerjoin(Score, Score.user_id == User.id)
        .where(User.role == "student")
        .group_by(User.id)
        .order_by(func.coalesce(func.sum(Score.points), 0).desc())
    ).all()

    return [
        LeaderboardEntry(
            user_id=row.id,
            name=row.name,
            department=row.department or "N/A",
            total_points=row.total,
            rank=rank,
        )
        for rank, row in enumerate(rows, start=1)
    ]


def _leaderboard_payload() -> list[dict]:
    return [
        {
            "user_id": e.user_id,
            "name": e.name,
            "department": e.department,
            "total_points": e.total_points,
            "rank": e.rank,
        }
        for e in get_leaderboard()
    ]


def upsert_score(
    user_id: int,
    event_id: int,
    points: int,
    reason: str | None,
) -> Score:
    """Insert or update a score entry, then push a live leaderboard update."""
    score = db.session.scalar(
        select(Score).where(
            Score.user_id == user_id,
            Score.event_id == event_id,
        )
    )

    if score is None:
        score = Score(
            user_id=user_id,
            event_id=event_id,
            points=points,
            reason=reason,
        )
        db.session.add(score)
    else:
        score.points = points
        score.reason = reason

    db.session.commit()

    # Push updated leaderboard to all clients
    socketio.emit("leaderboard_update", {"board": _leaderboard_payload()})
    return score
```

---

### 4.3 Create `app/blueprints/admin/leaderboard.py`

```python
# app/blueprints/admin/leaderboard.py
from flask import Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from app.extensions import db
from app.models.event import Event
from app.models.user import User
from app.services.leaderboard import get_leaderboard, upsert_score
from app.utils.auth import roles_required

bp = Blueprint("admin_leaderboard", __name__, url_prefix="/admin")


@bp.route("/leaderboard", methods=["GET", "POST"])
@roles_required("admin", "organizer")
def leaderboard():
    if request.method == "POST":
        user_id  = request.form.get("user_id",  type=int)
        event_id = request.form.get("event_id", type=int)
        points   = request.form.get("points",   type=int, default=0)
        reason   = request.form.get("reason",   "").strip() or None

        if user_id is None or event_id is None:
            flash("Invalid student or event.", "danger")
            return redirect(url_for("admin_leaderboard.leaderboard"))

        if not (0 <= points <= 10_000):
            flash("Points must be between 0 and 10,000.", "warning")
            return redirect(url_for("admin_leaderboard.leaderboard"))

        upsert_score(user_id=user_id, event_id=event_id, points=points, reason=reason)
        flash("Score updated and leaderboard refreshed.", "success")
        return redirect(url_for("admin_leaderboard.leaderboard"))

    students = db.session.scalars(
        select(User).where(User.role == "student").order_by(User.name)
    ).all()
    events = db.session.scalars(
        select(Event).order_by(Event.date.desc())
    ).all()

    return render_template(
        "admin/leaderboard.html",
        students=students,
        events=events,
        leaderboard=get_leaderboard(),
    )
```

---

### 4.4 Create `app/blueprints/student/leaderboard.py`

```python
# app/blueprints/student/leaderboard.py
from flask import Blueprint, render_template, session

from app.services.leaderboard import get_leaderboard
from app.utils.auth import roles_required

bp = Blueprint("student_leaderboard", __name__)


@bp.route("/leaderboard")
@roles_required("student")
def leaderboard():
    return render_template(
        "student/leaderboard.html",
        leaderboard=get_leaderboard(),
        current_user_id=session.get("user_id"),
    )
```

---

### 4.5 Register both blueprints — add to `app/__init__.py`

```python
    from app.blueprints.admin.leaderboard   import bp as admin_lb_bp
    from app.blueprints.student.leaderboard import bp as student_lb_bp
    app.register_blueprint(admin_lb_bp)
    app.register_blueprint(student_lb_bp)
```

### 4.6 Run the migration

```bash
flask db migrate -m "add score table"
flask db upgrade
```

---

### 4.7 Create `app/templates/admin/leaderboard.html`

```html
{% extends 'base.html' %}

{% block title %}Leaderboard Management{% endblock %}

{% block content %}
<div class="container-fluid py-4">

  <div class="d-flex align-items-center gap-3 mb-4">
    <div class="rounded-3 p-2 bg-warning bg-opacity-10">
      <i class="fas fa-trophy fa-lg text-warning"></i>
    </div>
    <div>
      <h4 class="mb-0 fw-semibold">Leaderboard Management</h4>
      <p class="text-muted small mb-0">Award points and manage student rankings</p>
    </div>
  </div>

  {# ── Top-3 podium ─────────────────────────────────────────────────── #}
  {% if leaderboard %}
  <div class="row justify-content-center g-3 mb-4">
    {% set podium = [
        (leaderboard[1] if leaderboard|length > 1 else none, '🥈', '#94a3b8', 2),
        (leaderboard[0],                                      '🥇', '#f59e0b', 1),
        (leaderboard[2] if leaderboard|length > 2 else none, '🥉', '#cd7f32', 3),
    ] %}
    {% for entry, medal, colour, pos in podium %}
    {% if entry %}
    <div class="col-auto">
      <div class="text-center p-4 rounded-3 shadow-sm text-white"
           style="background:{{ colour }};min-width:140px;">
        <div style="font-size:2.5rem">{{ medal }}</div>
        <div class="fw-bold mt-1">{{ entry.name }}</div>
        <div class="small opacity-75">{{ entry.department }}</div>
        <div class="fs-5 fw-bold mt-1">{{ entry.total_points }} pts</div>
      </div>
    </div>
    {% endif %}
    {% endfor %}
  </div>
  {% endif %}

  {# ── Award points form ────────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm mb-4">
    <div class="card-body">
      <h6 class="fw-semibold mb-3">Award Points</h6>
      <form method="POST" action="{{ url_for('admin_leaderboard.leaderboard') }}"
            class="row g-3 align-items-end" novalidate>
        {{ csrf_token() }}
        <div class="col-md-3">
          <label class="form-label small fw-medium">Student</label>
          <select name="user_id" class="form-select" required>
            <option value="" disabled selected>Select student…</option>
            {% for s in students %}
            <option value="{{ s.id }}">{{ s.name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-label small fw-medium">Event</label>
          <select name="event_id" class="form-select" required>
            <option value="" disabled selected>Select event…</option>
            {% for e in events %}
            <option value="{{ e.id }}">{{ e.title }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-2">
          <label class="form-label small fw-medium">Points</label>
          <input type="number" name="points" class="form-control"
                 min="0" max="10000" placeholder="0" required>
        </div>
        <div class="col-md-3">
          <label class="form-label small fw-medium">Reason <span class="text-muted">(optional)</span></label>
          <input type="text" name="reason" class="form-control"
                 maxlength="200" placeholder="e.g. 1st Place">
        </div>
        <div class="col-md-1">
          <button type="submit" class="btn btn-primary w-100">
            <i class="fas fa-save"></i>
          </button>
        </div>
      </form>
    </div>
  </div>

  {# ── Full rankings table ───────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm">
    <div class="card-header bg-transparent border-bottom-0 pt-3">
      <h6 class="fw-semibold mb-0">Full Rankings</h6>
    </div>
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0" id="lbTable">
          <thead class="table-light">
            <tr>
              <th class="ps-3" style="width:60px">#</th>
              <th>Student</th>
              <th>Department</th>
              <th class="text-end pe-3">Points</th>
            </tr>
          </thead>
          <tbody>
            {% for entry in leaderboard %}
            <tr>
              <td class="ps-3 text-muted">{{ entry.rank }}</td>
              <td class="fw-medium">{{ entry.name }}</td>
              <td class="text-muted small">{{ entry.department }}</td>
              <td class="text-end pe-3">
                <span class="badge text-bg-primary fs-6">{{ entry.total_points }}</span>
              </td>
            </tr>
            {% else %}
            <tr>
              <td colspan="4" class="text-center text-muted py-4">No scores recorded yet.</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>
{% endblock %}

{% block scripts %}
<script>
// Live leaderboard refresh via SocketIO (socket initialised in base.html)
window._socket.on('leaderboard_update', function (data) {
  const tbody = document.querySelector('#lbTable tbody');
  tbody.innerHTML = data.board.map(e => `
    <tr>
      <td class="ps-3 text-muted">${e.rank}</td>
      <td class="fw-medium">${escHtml(e.name)}</td>
      <td class="text-muted small">${escHtml(e.department)}</td>
      <td class="text-end pe-3">
        <span class="badge text-bg-primary fs-6">${e.total_points}</span>
      </td>
    </tr>`).join('');
});
</script>
{% endblock %}
```

---

### 4.8 Create `app/templates/student/leaderboard.html`

```html
{% extends 'base.html' %}

{% block title %}Leaderboard{% endblock %}

{% block content %}
<div class="container-fluid py-4">

  <div class="d-flex align-items-center gap-3 mb-4">
    <div class="rounded-3 p-2 bg-warning bg-opacity-10">
      <i class="fas fa-trophy fa-lg text-warning"></i>
    </div>
    <div>
      <h4 class="mb-0 fw-semibold">Student Leaderboard</h4>
      <p class="text-muted small mb-0">Rankings update live as points are awarded</p>
    </div>
  </div>

  {# ── Top-3 podium (same structure as admin view) ───────────────────── #}
  {% if leaderboard %}
  <div class="row justify-content-center g-3 mb-4">
    {% set podium = [
        (leaderboard[1] if leaderboard|length > 1 else none, '🥈', '#94a3b8'),
        (leaderboard[0],                                      '🥇', '#f59e0b'),
        (leaderboard[2] if leaderboard|length > 2 else none, '🥉', '#cd7f32'),
    ] %}
    {% for entry, medal, colour in podium %}
    {% if entry %}
    <div class="col-auto">
      <div class="text-center p-4 rounded-3 shadow-sm text-white
                  {{ 'ring ring-white' if entry.user_id == current_user_id }}"
           style="background:{{ colour }};min-width:140px;">
        <div style="font-size:2.5rem">{{ medal }}</div>
        <div class="fw-bold mt-1">
          {{ entry.name }}
          {% if entry.user_id == current_user_id %}
          <span class="badge bg-white text-dark ms-1 small">You</span>
          {% endif %}
        </div>
        <div class="small opacity-75">{{ entry.department }}</div>
        <div class="fs-5 fw-bold mt-1">{{ entry.total_points }} pts</div>
      </div>
    </div>
    {% endif %}
    {% endfor %}
  </div>
  {% endif %}

  {# ── Rankings table ────────────────────────────────────────────────── #}
  <div class="card border-0 shadow-sm">
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0" id="lbTable"
               data-current-user="{{ current_user_id }}">
          <thead class="table-light">
            <tr>
              <th class="ps-3" style="width:60px">#</th>
              <th>Student</th>
              <th>Department</th>
              <th class="text-end pe-3">Points</th>
            </tr>
          </thead>
          <tbody>
            {% for entry in leaderboard %}
            <tr {% if entry.user_id == current_user_id %}
                class="table-primary fw-semibold"{% endif %}>
              <td class="ps-3">{{ entry.rank }}</td>
              <td>
                {{ entry.name }}
                {% if entry.user_id == current_user_id %}
                <span class="badge text-bg-primary ms-1">You</span>
                {% endif %}
              </td>
              <td class="text-muted small">{{ entry.department }}</td>
              <td class="text-end pe-3">
                <span class="badge text-bg-primary fs-6">{{ entry.total_points }}</span>
              </td>
            </tr>
            {% else %}
            <tr>
              <td colspan="4" class="text-center text-muted py-4">
                No scores recorded yet — be the first!
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>
{% endblock %}

{% block scripts %}
<script>
(function () {
  'use strict';
  const currentUserId = parseInt(
    document.getElementById('lbTable').dataset.currentUser, 10
  );

  window._socket.on('leaderboard_update', function (data) {
    const tbody = document.querySelector('#lbTable tbody');
    tbody.innerHTML = data.board.map(e => {
      const isYou = e.user_id === currentUserId;
      return `
        <tr${isYou ? ' class="table-primary fw-semibold"' : ''}>
          <td class="ps-3">${e.rank}</td>
          <td>
            ${escHtml(e.name)}
            ${isYou ? '<span class="badge text-bg-primary ms-1">You</span>' : ''}
          </td>
          <td class="text-muted small">${escHtml(e.department)}</td>
          <td class="text-end pe-3">
            <span class="badge text-bg-primary fs-6">${e.total_points}</span>
          </td>
        </tr>`;
    }).join('');
  });
})();
</script>
{% endblock %}
```

---

### 4.9 Add nav links in `templates/base.html`

Admin / Organizer sidebar:
```html
<a href="{{ url_for('admin_leaderboard.leaderboard') }}"
   class="nav-link {{ 'active' if 'admin_leaderboard' in (request.endpoint or '') }}">
  <i class="fas fa-trophy me-2"></i>Leaderboard
</a>
```

Student sidebar:
```html
<a href="{{ url_for('student_leaderboard.leaderboard') }}"
   class="nav-link {{ 'active' if 'student_leaderboard' in (request.endpoint or '') }}">
  <i class="fas fa-trophy me-2"></i>Leaderboard
</a>
```

---

## OpenCode Prompts — one phase at a time

Paste each prompt verbatim into OpenCode with `@implementation.md` attached.

---

### Phase 0 prompt
```
@implementation.md

Implement Phase 0 — Structural Prerequisites.

1. Install the packages listed in §0.1 and update requirements.txt.
2. Create app/extensions.py exactly as in §0.2.
3. Replace the body of app/__init__.py (or create_app()) with the version
   in §0.3. Preserve any existing blueprint registrations already present.
4. Create app/utils/auth.py with the roles_required decorator in §0.4.
   If admin_required already exists, leave it; do not delete it. New views
   will use roles_required going forward.
5. Replace run.py with the version in §0.5.

Do not implement Phases 1–4.
```

---

### Phase 1 prompt
```
@implementation.md

Implement Phase 1 — Event Analytics Dashboard. Phase 0 is already done.

1. Create app/services/analytics.py (§1.1).
2. Create app/blueprints/admin/analytics.py (§1.2).
3. Register the analytics blueprint inside create_app() in app/__init__.py
   as shown in §1.3.
4. Create app/templates/admin/analytics.html (§1.4).
5. Add the Analytics nav link to the admin/organizer sidebar in
   templates/base.html (§1.5).

Do not modify the database schema. Do not implement Phases 2–4.
```

---

### Phase 2 prompt
```
@implementation.md

Implement Phase 2 — Real-time Announcements. Phases 0–1 are already done.

1. Create app/models/announcement.py (§2.1).
2. Create app/services/announcements.py (§2.2).
3. Create app/blueprints/admin/announcements.py (§2.3).
4. Register the announcements blueprint in create_app() (§2.4).
5. Run `flask db migrate -m "add announcement table"` then `flask db upgrade`.
6. Create app/templates/admin/announcements.html (§2.6).
7. Add the global SocketIO script block to templates/base.html before
   </body> (§2.7). If a <script src="socket.io..."> tag already exists,
   replace the entire old block with the new one from §2.7.
8. Add the Announcements nav link to the admin/organizer sidebar (§2.8).

Do not implement Phases 3–4.
```

---

### Phase 3 prompt
```
@implementation.md

Implement Phase 3 — Real-time Notifications. Phases 0–2 are already done.

1. Create app/sockets/notifications.py (§3.1).
2. Register the socket handler in create_app() (§3.2).
3. Create app/services/notifications.py (§3.3).
4. In the existing create_event route, import notify_new_event and call it
   after db.session.commit() as shown in §3.4.
5. In the existing manage_attendance route, import notify_attendance_marked
   and call it inside the attendance loop as shown in §3.4.
6. Append the showToast function and socket.on('notification') listener
   inside the existing SocketIO <script> block in templates/base.html (§3.5).
   Do not add a second <script src="socket.io..."> tag.

Do not implement Phase 4.
```

---

### Phase 4 prompt
```
@implementation.md

Implement Phase 4 — Gamified Leaderboard. Phases 0–3 are already done.

1. Create app/models/score.py (§4.1).
2. Create app/services/leaderboard.py (§4.2).
3. Create app/blueprints/admin/leaderboard.py (§4.3).
4. Create app/blueprints/student/leaderboard.py (§4.4).
5. Register both blueprints in create_app() (§4.5).
6. Run `flask db migrate -m "add score table"` then `flask db upgrade`.
7. Create app/templates/admin/leaderboard.html (§4.7).
8. Create app/templates/student/leaderboard.html (§4.8).
9. Add leaderboard nav links for admin/organizer and student sidebars
   in templates/base.html (§4.9).
```

---

## File Change Summary

| Phase | New files | Modified files |
|---|---|---|
| 0 — Prerequisites | `app/extensions.py` · `app/utils/auth.py` | `app/__init__.py` · `run.py` · `requirements.txt` |
| 1 — Analytics | `app/services/analytics.py` · `app/blueprints/admin/analytics.py` · `templates/admin/analytics.html` | `app/__init__.py` · `templates/base.html` |
| 2 — Announcements | `app/models/announcement.py` · `app/services/announcements.py` · `app/blueprints/admin/announcements.py` · `templates/admin/announcements.html` | `app/__init__.py` · `templates/base.html` · DB migration |
| 3 — Notifications | `app/sockets/notifications.py` · `app/services/notifications.py` | existing `create_event` route · existing `manage_attendance` route · `templates/base.html` |
| 4 — Leaderboard | `app/models/score.py` · `app/services/leaderboard.py` · `app/blueprints/admin/leaderboard.py` · `app/blueprints/student/leaderboard.py` · `templates/admin/leaderboard.html` · `templates/student/leaderboard.html` | `app/__init__.py` · `templates/base.html` · DB migration |
