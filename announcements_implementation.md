# Announcements — Full Implementation (All Dashboards)

**Feature scope:** Admin · Organizer · Student  
**Stack:** Flask 3 · SQLAlchemy 2 · Flask-SocketIO · Flask-WTF · Bootstrap 5 · Font Awesome 6  
**UI theme:** Matches CampusCore — dark navy sidebar `#1e2d4d`, white content canvas, accent `#4f6ef7`

---

## What each role gets

| Capability | Admin | Organizer | Student |
|---|:---:|:---:|:---:|
| Compose & broadcast announcement | ✅ | ✅ | ❌ |
| Set priority (Info / Warning / Urgent) | ✅ | ✅ | ❌ |
| View full announcement history | ✅ | ✅ | ✅ |
| Delete any announcement | ✅ | ❌ | ❌ |
| Delete own announcement | ❌ | ✅ | ❌ |
| Live floating banner on new broadcast | ✅ | ✅ | ✅ |
| Unread badge on nav link | ✅ | ✅ | ✅ |

---

## File Map

```
app/
├── models/announcement.py          ← DB model (§1)
├── services/announcements.py       ← all business logic (§2)
├── blueprints/
│   ├── admin/announcements.py      ← admin + organizer routes (§3)
│   └── student/announcements.py   ← student read-only route (§4)
└── templates/
    ├── admin/announcements.html    ← admin/organizer UI (§5)
    ├── student/announcements.html  ← student UI (§6)
    └── base.html                   ← global banner + badge (§7)
```

---

## §1 — Model: `app/models/announcement.py`

```python
# app/models/announcement.py
"""
Announcement model.

priority values:  'info' | 'warning' | 'urgent'
author_role values mirror User.role: 'admin' | 'organizer'
"""
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
    author: Mapped["User"] = relationship(  # noqa: F821
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
```

**Migration:**
```bash
flask db migrate -m "add announcement table with priority"
flask db upgrade
```

---

## §2 — Service: `app/services/announcements.py`

```python
# app/services/announcements.py
"""
All announcement business logic lives here.

Routes stay thin — they validate HTTP input and delegate here.
SocketIO emission happens inside this module so it is never
scattered across route handlers.
"""
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
      - admin  → can delete anything
      - organizer → can only delete their own
    """
    ann = db.session.get(Announcement, ann_id)
    if ann is None:
        raise ValueError("Announcement not found.")

    if requestor_role == "organizer" and ann.created_by != requestor_id:
        raise PermissionError("Organizers can only delete their own announcements.")

    db.session.delete(ann)
    db.session.commit()
```

---

## §3 — Blueprint: `app/blueprints/admin/announcements.py`

Shared by both **Admin** and **Organizer** roles — the template adapts the UI
per role (delete buttons, priority selector visibility).

```python
# app/blueprints/admin/announcements.py
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from app.services.announcements import (
    create_announcement,
    delete_announcement,
    get_all_announcements,
    mark_all_read,
)
from app.utils.auth import roles_required

bp = Blueprint("admin_announcements", __name__, url_prefix="/admin")


@bp.route("/announcements", methods=["GET", "POST"])
@roles_required("admin", "organizer")
def announcements():
    if request.method == "POST":
        message  = request.form.get("message", "")
        priority = request.form.get("priority", "info")

        try:
            create_announcement(
                message=message,
                priority=priority,
                author_id=session["user_id"],
            )
            flash("Announcement broadcast to all connected users.", "success")
        except ValueError as exc:
            flash(str(exc), "danger")

        return redirect(url_for("admin_announcements.announcements"))

    # Mark all read when opening the page — reset badge counter
    session["ann_last_seen"] = mark_all_read()

    return render_template(
        "admin/announcements.html",
        announcements=get_all_announcements(),
        current_role=session.get("role"),
        current_user_id=session.get("user_id"),
    )


@bp.post("/announcements/<int:ann_id>/delete")
@roles_required("admin", "organizer")
def delete(ann_id: int):
    try:
        delete_announcement(
            ann_id=ann_id,
            requestor_id=session["user_id"],
            requestor_role=session.get("role", ""),
        )
        flash("Announcement deleted.", "info")
    except (ValueError, PermissionError) as exc:
        flash(str(exc), "danger")

    return redirect(url_for("admin_announcements.announcements"))
```

---

## §4 — Blueprint: `app/blueprints/student/announcements.py`

```python
# app/blueprints/student/announcements.py
from flask import Blueprint, render_template, session

from app.services.announcements import get_all_announcements, mark_all_read
from app.utils.auth import roles_required

bp = Blueprint("student_announcements", __name__, url_prefix="/student")


@bp.route("/announcements")
@roles_required("student")
def announcements():
    session["ann_last_seen"] = mark_all_read()
    return render_template(
        "student/announcements.html",
        announcements=get_all_announcements(),
    )
```

**Register both blueprints in `app/__init__.py`:**
```python
from app.blueprints.admin.announcements   import bp as admin_ann_bp
from app.blueprints.student.announcements import bp as student_ann_bp
app.register_blueprint(admin_ann_bp)
app.register_blueprint(student_ann_bp)
```

---

## §5 — Template: `app/templates/admin/announcements.html`

This single template serves both Admin and Organizer.  
It uses `current_role` to conditionally show/hide controls.

```html
{% extends 'base.html' %}
{% block title %}Announcements{% endblock %}

{% block head_extra %}
<style>
  /* ── Page-level custom tokens ────────────────────────────────────── */
  :root {
    --ann-radius : 14px;
    --ann-gap    : 1.25rem;
  }

  /* ── Compose card ────────────────────────────────────────────────── */
  .compose-card {
    background : #fff;
    border     : 1px solid #e8ecf4;
    border-radius : var(--ann-radius);
    box-shadow : 0 2px 12px rgba(30,45,77,.07);
  }

  .compose-card textarea {
    resize        : vertical;
    min-height    : 96px;
    border-radius : 10px;
    border        : 1.5px solid #dde3ef;
    font-size     : .95rem;
    transition    : border-color .2s;
  }
  .compose-card textarea:focus {
    border-color : #4f6ef7;
    box-shadow   : 0 0 0 3px rgba(79,110,247,.12);
  }

  /* ── Priority pill selector ──────────────────────────────────────── */
  .priority-group { display: flex; gap: .5rem; flex-wrap: wrap; }

  .priority-group input[type="radio"] { display: none; }

  .priority-pill {
    display       : flex;
    align-items   : center;
    gap           : .4rem;
    padding       : .35rem .9rem;
    border-radius : 20px;
    font-size     : .82rem;
    font-weight   : 600;
    cursor        : pointer;
    border        : 1.5px solid transparent;
    transition    : all .15s;
    user-select   : none;
  }

  /* Info */
  input#p-info:checked ~ label[for="p-info"],
  label[for="p-info"]:hover {
    background: #eff2ff; color: #4f6ef7; border-color: #4f6ef7;
  }
  label[for="p-info"] { background: #f4f6fb; color: #6b7a9a; border-color: #dde3ef; }

  /* Warning */
  input#p-warning:checked ~ label[for="p-warning"],
  label[for="p-warning"]:hover {
    background: #fff8ec; color: #d97706; border-color: #f59e0b;
  }
  label[for="p-warning"] { background: #f4f6fb; color: #6b7a9a; border-color: #dde3ef; }

  /* Urgent */
  input#p-urgent:checked ~ label[for="p-urgent"],
  label[for="p-urgent"]:hover {
    background: #fff0f0; color: #dc2626; border-color: #ef4444;
  }
  label[for="p-urgent"] { background: #f4f6fb; color: #6b7a9a; border-color: #dde3ef; }

  /* ── Send button ─────────────────────────────────────────────────── */
  .btn-broadcast {
    background    : linear-gradient(135deg,#4f6ef7,#6a89ff);
    color         : #fff;
    border        : none;
    border-radius : 10px;
    padding       : .55rem 1.4rem;
    font-weight   : 600;
    font-size     : .9rem;
    letter-spacing: .01em;
    transition    : opacity .2s, transform .15s;
  }
  .btn-broadcast:hover  { opacity:.9; transform: translateY(-1px); color:#fff; }
  .btn-broadcast:active { transform: translateY(0); }

  /* ── History section ─────────────────────────────────────────────── */
  .history-card {
    background    : #fff;
    border        : 1px solid #e8ecf4;
    border-radius : var(--ann-radius);
    box-shadow    : 0 2px 12px rgba(30,45,77,.07);
  }

  .ann-item {
    display        : flex;
    gap            : 1rem;
    align-items    : flex-start;
    padding        : 1rem 1.25rem;
    border-bottom  : 1px solid #f0f3fa;
    transition     : background .15s;
  }
  .ann-item:last-child  { border-bottom: none; }
  .ann-item:hover       { background: #f8f9fd; }

  /* Left accent stripe */
  .ann-stripe {
    width         : 4px;
    border-radius : 4px;
    flex-shrink   : 0;
    align-self    : stretch;
    min-height    : 36px;
  }
  .stripe-info    { background: #4f6ef7; }
  .stripe-warning { background: #f59e0b; }
  .stripe-urgent  { background: #ef4444; }

  /* Priority badge inside the item */
  .priority-badge {
    font-size   : .72rem;
    font-weight : 700;
    padding     : .18rem .55rem;
    border-radius : 20px;
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .badge-info    { background:#eff2ff; color:#4f6ef7; }
  .badge-warning { background:#fff8ec; color:#d97706; }
  .badge-urgent  { background:#fff0f0; color:#dc2626; }

  .ann-message {
    font-size  : .95rem;
    color      : #1e2d4d;
    font-weight: 500;
    line-height: 1.5;
    margin     : 0;
  }

  .ann-meta {
    font-size : .78rem;
    color     : #8a96ae;
    display   : flex;
    flex-wrap : wrap;
    gap       : .6rem;
    margin-top: .3rem;
    align-items: center;
  }
  .ann-meta i { font-size: .7rem; }

  /* Delete button */
  .btn-del {
    border        : 1.5px solid #fecaca;
    color         : #ef4444;
    background    : transparent;
    border-radius : 8px;
    padding       : .3rem .55rem;
    font-size     : .8rem;
    transition    : all .15s;
    flex-shrink   : 0;
    margin-top    : .1rem;
  }
  .btn-del:hover { background:#fff0f0; border-color:#ef4444; color:#dc2626; }

  /* ── Empty state ─────────────────────────────────────────────────── */
  .empty-state {
    text-align : center;
    padding    : 3.5rem 2rem;
    color      : #8a96ae;
  }
  .empty-state i { font-size: 2.8rem; margin-bottom: 1rem; opacity:.35; }

  /* ── Char counter colour ─────────────────────────────────────────── */
  .char-ok   { color: #8a96ae; }
  .char-warn { color: #d97706; }
  .char-over { color: #ef4444; font-weight: 600; }

  /* ── Page header icon ────────────────────────────────────────────── */
  .page-icon {
    width         : 44px;
    height        : 44px;
    border-radius : 12px;
    background    : linear-gradient(135deg,#4f6ef7,#6a89ff);
    display       : flex;
    align-items   : center;
    justify-content: center;
    color         : #fff;
    font-size     : 1.1rem;
    flex-shrink   : 0;
  }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid py-4 px-4" style="max-width:900px;">

  {# ── Flash messages ───────────────────────────────────────────────── #}
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% for category, msg in messages %}
  <div class="alert alert-{{ 'success' if category == 'success' else 'danger' if category == 'danger' else 'info' }}
              alert-dismissible fade show mb-3 rounded-3 border-0 shadow-sm"
       role="alert">
    <i class="fas fa-{{ 'check-circle' if category == 'success' else 'exclamation-circle' }} me-2"></i>
    {{ msg }}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% endfor %}
  {% endwith %}

  {# ── Page header ──────────────────────────────────────────────────── #}
  <div class="d-flex align-items-center gap-3 mb-4">
    <div class="page-icon">
      <i class="fas fa-bullhorn"></i>
    </div>
    <div>
      <h4 class="mb-0 fw-bold" style="color:#1e2d4d;">Announcements</h4>
      <p class="mb-0 small" style="color:#8a96ae;">
        {% if current_role in ('admin', 'organizer') %}
          Broadcast messages are pushed live to all connected users
        {% else %}
          Live announcements from your institution
        {% endif %}
      </p>
    </div>
    <div class="ms-auto">
      <span class="badge rounded-pill" style="background:#eff2ff;color:#4f6ef7;font-size:.82rem;padding:.4rem .8rem;">
        {{ announcements|length }} total
      </span>
    </div>
  </div>

  {# ── Compose card (admin + organizer only) ────────────────────────── #}
  {% if current_role in ('admin', 'organizer') %}
  <div class="compose-card p-4 mb-4">
    <h6 class="fw-bold mb-3" style="color:#1e2d4d;">
      <i class="fas fa-pen-to-square me-2" style="color:#4f6ef7;"></i>Broadcast New Announcement
    </h6>

    <form method="POST"
          action="{{ url_for('admin_announcements.announcements') }}"
          id="composeForm" novalidate>
      {{ csrf_token() }}

      {# Message textarea #}
      <div class="mb-3">
        <textarea name="message" id="messageArea" class="form-control"
                  rows="3" maxlength="1000"
                  placeholder="Write your announcement here…"
                  required></textarea>
        <div class="d-flex justify-content-between mt-1 px-1">
          <span class="small char-ok" id="charCount">0 / 1000</span>
        </div>
      </div>

      {# Priority selector #}
      <div class="mb-4">
        <label class="form-label small fw-semibold mb-2" style="color:#4a5568;">
          Priority level
        </label>
        <div class="priority-group">
          {# Hidden radios before labels so CSS :checked sibling selector works #}
          <input type="radio" name="priority" id="p-info"    value="info"    checked>
          <input type="radio" name="priority" id="p-warning" value="warning">
          <input type="radio" name="priority" id="p-urgent"  value="urgent">

          <label class="priority-pill" for="p-info">
            <i class="fas fa-circle-info"></i> Info
          </label>
          <label class="priority-pill" for="p-warning">
            <i class="fas fa-triangle-exclamation"></i> Warning
          </label>
          <label class="priority-pill" for="p-urgent">
            <i class="fas fa-circle-exclamation"></i> Urgent
          </label>
        </div>
      </div>

      <div class="d-flex align-items-center gap-3">
        <button type="submit" class="btn btn-broadcast">
          <i class="fas fa-paper-plane me-2"></i>Send to All Students
        </button>
        <button type="button" class="btn btn-link text-muted p-0 small"
                onclick="document.getElementById('messageArea').value='';
                         document.getElementById('charCount').textContent='0 / 1000';">
          Clear
        </button>
      </div>
    </form>
  </div>
  {% endif %}

  {# ── History card ─────────────────────────────────────────────────── #}
  <div class="history-card">
    <div class="d-flex align-items-center justify-content-between px-4 pt-3 pb-2">
      <h6 class="fw-bold mb-0" style="color:#1e2d4d;">
        <i class="fas fa-clock-rotate-left me-2" style="color:#8a96ae;font-size:.9rem;"></i>
        Announcement History
      </h6>
      {% if announcements %}
      <span class="small" style="color:#8a96ae;">
        Latest first
      </span>
      {% endif %}
    </div>

    <div id="annList">
    {% if announcements %}
      {% for ann in announcements %}
      <div class="ann-item" data-id="{{ ann.id }}">

        {# Coloured left stripe #}
        <div class="ann-stripe stripe-{{ ann.priority }}"></div>

        {# Content #}
        <div class="flex-grow-1 min-w-0">
          <div class="d-flex align-items-center gap-2 mb-1">
            <span class="priority-badge badge-{{ ann.priority }}">
              {{ ann.priority_label }}
            </span>
          </div>
          <p class="ann-message">{{ ann.message }}</p>
          <div class="ann-meta">
            <span><i class="far fa-clock me-1"></i>{{ ann.formatted_time() }}</span>
            <span><i class="far fa-user me-1"></i>{{ ann.author_name }}</span>
            <span class="text-capitalize">
              <i class="fas fa-shield-halved me-1"></i>{{ ann.author_role }}
            </span>
          </div>
        </div>

        {# Delete button — admin sees all, organizer sees own only #}
        {% if current_role == 'admin'
              or (current_role == 'organizer' and ann.created_by == current_user_id) %}
        <form method="POST"
              action="{{ url_for('admin_announcements.delete', ann_id=ann.id) }}"
              onsubmit="return confirm('Delete this announcement?');">
          {{ csrf_token() }}
          <button type="submit" class="btn-del" title="Delete announcement">
            <i class="fas fa-trash-alt"></i>
          </button>
        </form>
        {% endif %}

      </div>
      {% endfor %}
    {% else %}
      <div class="empty-state">
        <i class="fas fa-bullhorn d-block"></i>
        <p class="mb-1 fw-medium" style="color:#4a5568;">No announcements yet</p>
        <p class="small mb-0">
          {% if current_role in ('admin','organizer') %}
            Compose your first announcement above.
          {% else %}
            Check back soon for updates from your institution.
          {% endif %}
        </p>
      </div>
    {% endif %}
    </div>

  </div>{# /history-card #}

</div>
{% endblock %}

{% block scripts %}
<script>
(function () {
  'use strict';

  // ── Character counter ────────────────────────────────────────────────
  const area    = document.getElementById('messageArea');
  const counter = document.getElementById('charCount');

  if (area && counter) {
    area.addEventListener('input', function () {
      const n = area.value.length;
      counter.textContent = n + ' / 1000';
      counter.className = 'small ' + (n > 950 ? 'char-over' : n > 800 ? 'char-warn' : 'char-ok');
    });
  }

  // ── Live incoming announcements — prepend to history ─────────────────
  if (window._socket) {
    window._socket.on('new_announcement', function (data) {
      prependAnnouncement(data);
    });
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  const stripeMap  = { info:'stripe-info', warning:'stripe-warning', urgent:'stripe-urgent' };
  const badgeMap   = { info:'badge-info',  warning:'badge-warning',  urgent:'badge-urgent'  };

  function prependAnnouncement(data) {
    const list = document.getElementById('annList');
    if (!list) return;

    // Remove empty state if present
    const empty = list.querySelector('.empty-state');
    if (empty) empty.closest('.ann-item, div')?.remove();

    const item = document.createElement('div');
    item.className = 'ann-item';
    item.style.animation = 'slideIn .3s ease';
    item.innerHTML = `
      <div class="ann-stripe ${escHtml(stripeMap[data.priority] || 'stripe-info')}"></div>
      <div class="flex-grow-1 min-w-0">
        <div class="d-flex align-items-center gap-2 mb-1">
          <span class="priority-badge ${escHtml(badgeMap[data.priority] || 'badge-info')}">
            ${escHtml(data.priority_label)}
          </span>
        </div>
        <p class="ann-message">${escHtml(data.message)}</p>
        <div class="ann-meta">
          <span><i class="far fa-clock me-1"></i>${escHtml(data.time)}</span>
          <span><i class="far fa-user me-1"></i>${escHtml(data.author)}</span>
          <span class="text-capitalize"><i class="fas fa-shield-halved me-1"></i>${escHtml(data.author_role)}</span>
        </div>
      </div>`;

    list.insertBefore(item, list.firstChild);
  }
})();
</script>
<style>
@keyframes slideIn {
  from { opacity:0; transform:translateY(-8px); }
  to   { opacity:1; transform:translateY(0); }
}
</style>
{% endblock %}
```

---

## §6 — Template: `app/templates/student/announcements.html`

Read-only view for students — no compose form, no delete controls.  
Includes a live prepend via SocketIO.

```html
{% extends 'base.html' %}
{% block title %}Announcements{% endblock %}

{% block head_extra %}
{# Reuse the same CSS variables from the admin template via a shared partial,
   or paste the <style> block from §5 here. Below is the student-only
   additions / overrides only. #}
<style>
  /* Copy the full <style> block from §5 here */

  /* Student-only: add a subtle "NEW" flash badge for fresh items */
  .ann-item.is-new .ann-message::after {
    content       : ' NEW';
    font-size     : .65rem;
    font-weight   : 700;
    color         : #4f6ef7;
    letter-spacing: .06em;
    margin-left   : .4rem;
    vertical-align: middle;
  }
</style>
{% endblock %}

{% block content %}
<div class="container-fluid py-4 px-4" style="max-width:900px;">

  {# ── Page header ──────────────────────────────────────────────────── #}
  <div class="d-flex align-items-center gap-3 mb-4">
    <div class="page-icon">
      <i class="fas fa-bullhorn"></i>
    </div>
    <div>
      <h4 class="mb-0 fw-bold" style="color:#1e2d4d;">Announcements</h4>
      <p class="mb-0 small" style="color:#8a96ae;">
        Live updates from your institution
      </p>
    </div>
    <div class="ms-auto">
      <span class="badge rounded-pill"
            style="background:#eff2ff;color:#4f6ef7;font-size:.82rem;padding:.4rem .8rem;">
        {{ announcements|length }} total
      </span>
    </div>
  </div>

  {# ── Filter tabs ──────────────────────────────────────────────────── #}
  <div class="d-flex gap-2 mb-4 flex-wrap" id="filterBar">
    <button class="filter-btn active" data-filter="all">All</button>
    <button class="filter-btn" data-filter="info">
      <span class="dot" style="background:#4f6ef7"></span> Info
    </button>
    <button class="filter-btn" data-filter="warning">
      <span class="dot" style="background:#f59e0b"></span> Warning
    </button>
    <button class="filter-btn" data-filter="urgent">
      <span class="dot" style="background:#ef4444"></span> Urgent
    </button>
  </div>

  {# ── Announcement list ────────────────────────────────────────────── #}
  <div class="history-card">
    <div id="annList">
    {% if announcements %}
      {% for ann in announcements %}
      <div class="ann-item" data-priority="{{ ann.priority }}">
        <div class="ann-stripe stripe-{{ ann.priority }}"></div>
        <div class="flex-grow-1 min-w-0">
          <div class="d-flex align-items-center gap-2 mb-1">
            <span class="priority-badge badge-{{ ann.priority }}">
              {{ ann.priority_label }}
            </span>
          </div>
          <p class="ann-message">{{ ann.message }}</p>
          <div class="ann-meta">
            <span><i class="far fa-clock me-1"></i>{{ ann.formatted_time() }}</span>
            <span><i class="far fa-user me-1"></i>{{ ann.author_name }}</span>
            <span class="text-capitalize">
              <i class="fas fa-shield-halved me-1"></i>{{ ann.author_role }}
            </span>
          </div>
        </div>
      </div>
      {% endfor %}
    {% else %}
      <div class="empty-state">
        <i class="fas fa-bullhorn d-block"></i>
        <p class="mb-1 fw-medium" style="color:#4a5568;">No announcements yet</p>
        <p class="small mb-0">Check back soon for updates.</p>
      </div>
    {% endif %}
    </div>
  </div>

</div>
{% endblock %}

{% block scripts %}
<style>
  /* Filter button strip */
  .filter-btn {
    padding       : .35rem .9rem;
    border-radius : 20px;
    border        : 1.5px solid #dde3ef;
    background    : #fff;
    color         : #4a5568;
    font-size     : .83rem;
    font-weight   : 600;
    cursor        : pointer;
    transition    : all .15s;
    display       : flex;
    align-items   : center;
    gap           : .4rem;
  }
  .filter-btn .dot {
    width: 8px; height: 8px; border-radius: 50%; display:inline-block;
  }
  .filter-btn:hover  { border-color:#4f6ef7; color:#4f6ef7; }
  .filter-btn.active {
    background: #4f6ef7; color:#fff; border-color:#4f6ef7;
  }
  @keyframes slideIn {
    from { opacity:0; transform:translateY(-8px); }
    to   { opacity:1; transform:translateY(0); }
  }
</style>

<script>
(function () {
  'use strict';

  // ── Priority filter ──────────────────────────────────────────────────
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');

      const filter = this.dataset.filter;
      document.querySelectorAll('#annList .ann-item').forEach(row => {
        const match = filter === 'all' || row.dataset.priority === filter;
        row.style.display = match ? '' : 'none';
      });
    });
  });

  // ── Live incoming ────────────────────────────────────────────────────
  function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')
                    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  const stripeMap = { info:'stripe-info', warning:'stripe-warning', urgent:'stripe-urgent' };
  const badgeMap  = { info:'badge-info',  warning:'badge-warning',  urgent:'badge-urgent'  };

  if (window._socket) {
    window._socket.on('new_announcement', function (data) {
      const list = document.getElementById('annList');
      const empty = list.querySelector('.empty-state');
      if (empty) empty.closest('div')?.remove();

      const item = document.createElement('div');
      item.className = 'ann-item is-new';
      item.dataset.priority = data.priority;
      item.style.animation = 'slideIn .3s ease';
      item.innerHTML = `
        <div class="ann-stripe ${escHtml(stripeMap[data.priority] || 'stripe-info')}"></div>
        <div class="flex-grow-1 min-w-0">
          <div class="d-flex align-items-center gap-2 mb-1">
            <span class="priority-badge ${escHtml(badgeMap[data.priority] || 'badge-info')}">
              ${escHtml(data.priority_label)}
            </span>
          </div>
          <p class="ann-message">${escHtml(data.message)}</p>
          <div class="ann-meta">
            <span><i class="far fa-clock me-1"></i>${escHtml(data.time)}</span>
            <span><i class="far fa-user me-1"></i>${escHtml(data.author)}</span>
            <span class="text-capitalize">
              <i class="fas fa-shield-halved me-1"></i>${escHtml(data.author_role)}
            </span>
          </div>
        </div>`;
      list.insertBefore(item, list.firstChild);
    });
  }
})();
</script>
{% endblock %}
```

---

## §7 — `templates/base.html` — global SocketIO block

Add once, before `</body>`. Handles:
1. SocketIO connection
2. Floating announcement banner (all roles)
3. Unread badge on the nav link

```html
{# ════════════════════════════════════════════════════════════════════ #}
{# Global SocketIO — placed once in base.html, before </body>          #}
{# ════════════════════════════════════════════════════════════════════ #}
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>

<style>
  /* ── Live announcement banner ─────────────────────────────────────── */
  .ann-banner {
    position      : fixed;
    top           : 76px;
    right         : 20px;
    z-index       : 9999;
    width         : 380px;
    background    : #fff;
    border-radius : 14px;
    box-shadow    : 0 8px 32px rgba(30,45,77,.18);
    border        : 1.5px solid #e8ecf4;
    overflow      : hidden;
    animation     : bannerIn .35s cubic-bezier(.34,1.56,.64,1);
  }
  .ann-banner-stripe {
    height : 4px;
    width  : 100%;
  }
  .ann-banner-body {
    padding : 1rem 1.1rem;
  }
  .ann-banner-title {
    font-size   : .8rem;
    font-weight : 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    margin-bottom : .25rem;
  }
  .ann-banner-msg {
    font-size  : .9rem;
    color      : #1e2d4d;
    font-weight: 500;
    margin     : 0 0 .35rem;
    line-height: 1.45;
  }
  .ann-banner-meta {
    font-size : .75rem;
    color     : #8a96ae;
  }
  .ann-banner-close {
    position   : absolute;
    top        : 10px;
    right      : 10px;
    background : none;
    border     : none;
    color      : #8a96ae;
    cursor     : pointer;
    font-size  : .85rem;
    padding    : 2px 5px;
    border-radius: 4px;
    line-height: 1;
  }
  .ann-banner-close:hover { color:#1e2d4d; }

  @keyframes bannerIn {
    from { opacity:0; transform:translateX(20px) scale(.96); }
    to   { opacity:1; transform:translateX(0)    scale(1); }
  }

  /* ── Nav unread badge ─────────────────────────────────────────────── */
  .nav-unread-badge {
    display       : inline-flex;
    align-items   : center;
    justify-content: center;
    min-width     : 18px;
    height        : 18px;
    border-radius : 9px;
    background    : #ef4444;
    color         : #fff;
    font-size     : .65rem;
    font-weight   : 700;
    padding       : 0 4px;
    margin-left   : auto;
    line-height   : 1;
  }
  .nav-link:has(.nav-unread-badge) { justify-content: flex-start; }
</style>

<script>
(function () {
  'use strict';

  // ── Shared XSS-safe escape ───────────────────────────────────────────
  function esc(s) {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── Colour map matching the CSS stripe/badge colours ─────────────────
  const PRIORITY_COLOUR = {
    info    : '#4f6ef7',
    warning : '#f59e0b',
    urgent  : '#ef4444',
  };

  // ── Socket connection ─────────────────────────────────────────────────
  const socket = window._socket = io({ transports: ['websocket', 'polling'] });

  // ── Unread badge counter ─────────────────────────────────────────────
  // Stored in sessionStorage so it resets on browser close.
  let unread = parseInt(sessionStorage.getItem('ann_unread') || '0', 10);

  function updateBadge(delta) {
    unread = Math.max(0, unread + delta);
    sessionStorage.setItem('ann_unread', unread);
    renderBadge();
  }

  function renderBadge() {
    document.querySelectorAll('.ann-nav-badge').forEach(el => {
      el.textContent = unread > 0 ? (unread > 99 ? '99+' : unread) : '';
      el.style.display = unread > 0 ? 'inline-flex' : 'none';
    });
  }

  // Reset badge when the user is currently on an announcements page
  if (/\/announcements/.test(window.location.pathname)) {
    unread = 0;
    sessionStorage.setItem('ann_unread', '0');
  }
  renderBadge();

  // ── New announcement event ────────────────────────────────────────────
  socket.on('new_announcement', function (data) {
    showBanner(data);
    // Only increment badge if not currently viewing announcements
    if (!/\/announcements/.test(window.location.pathname)) {
      updateBadge(+1);
    }
  });

  // ── Banner renderer ───────────────────────────────────────────────────
  let bannerQueue = [];
  let bannerShowing = false;

  function showBanner(data) {
    bannerQueue.push(data);
    if (!bannerShowing) processQueue();
  }

  function processQueue() {
    if (bannerQueue.length === 0) { bannerShowing = false; return; }
    bannerShowing = true;
    const data = bannerQueue.shift();
    renderBanner(data, processQueue);
  }

  function renderBanner(data, onDone) {
    const colour = PRIORITY_COLOUR[data.priority] || '#4f6ef7';
    const el = document.createElement('div');
    el.className = 'ann-banner';
    el.setAttribute('role', 'alert');
    el.innerHTML = `
      <div class="ann-banner-stripe" style="background:${esc(colour)}"></div>
      <div class="ann-banner-body">
        <p class="ann-banner-title" style="color:${esc(colour)}">
          <i class="fas fa-bullhorn me-1"></i>${esc(data.priority_label)} Announcement
        </p>
        <p class="ann-banner-msg">${esc(data.message)}</p>
        <span class="ann-banner-meta">
          <i class="far fa-clock me-1"></i>${esc(data.time)}
          &nbsp;·&nbsp;
          <i class="far fa-user me-1"></i>${esc(data.author)}
        </span>
      </div>
      <button class="ann-banner-close" aria-label="Dismiss">
        <i class="fas fa-xmark"></i>
      </button>`;

    document.body.appendChild(el);

    // Dismiss on close button
    el.querySelector('.ann-banner-close').addEventListener('click', () => dismiss(el, onDone));

    // Auto-dismiss after 9 s
    const timer = setTimeout(() => dismiss(el, onDone), 9000);

    function dismiss(node, cb) {
      clearTimeout(timer);
      node.style.transition = 'opacity .3s, transform .3s';
      node.style.opacity = '0';
      node.style.transform = 'translateX(20px)';
      setTimeout(() => { node.remove(); cb(); }, 300);
    }
  }

})();
</script>
```

---

## §8 — Nav links in `templates/base.html`

Replace existing (plain) Announcements nav links with the badge-aware version.

**Admin / Organizer sidebar:**
```html
<a href="{{ url_for('admin_announcements.announcements') }}"
   class="nav-link {{ 'active' if 'admin_announcements' in (request.endpoint or '') }}">
  <i class="fas fa-bullhorn me-2"></i>
  Announcements
  <span class="nav-unread-badge ann-nav-badge" style="display:none;"></span>
</a>
```

**Student sidebar:**
```html
<a href="{{ url_for('student_announcements.announcements') }}"
   class="nav-link {{ 'active' if 'student_announcements' in (request.endpoint or '') }}">
  <i class="fas fa-bullhorn me-2"></i>
  Announcements
  <span class="nav-unread-badge ann-nav-badge" style="display:none;"></span>
</a>
```

---

## §9 — OpenCode Prompt

```
@announcements_implementation.md

Implement the complete Announcements feature across all dashboards.
Follow the file map and section numbers exactly.

Steps in order:

1. Create app/models/announcement.py  (§1).
2. Create app/services/announcements.py  (§2).
3. Create app/blueprints/admin/announcements.py  (§3).
4. Create app/blueprints/student/announcements.py  (§4).
5. Register both blueprints in create_app() inside app/__init__.py  (§4, bottom).
6. Run:
       flask db migrate -m "add announcement table with priority"
       flask db upgrade
7. Create app/templates/admin/announcements.html  (§5).
   - This template is shared by both admin and organizer roles.
   - Do not create a separate organizer template.
8. Create app/templates/student/announcements.html  (§6).
   - Copy the full <style> block from §5 into this template's {% block head_extra %}.
9. In templates/base.html, before </body>:
   - Remove any existing <script src="socket.io"> tag and its accompanying <script> block.
   - Paste the complete global SocketIO block from §7 in its place.
10. In templates/base.html, replace all existing Announcements nav-link anchors
    with the badge-aware versions from §8:
    - Admin/Organizer sidebar → url_for('admin_announcements.announcements')
    - Student sidebar         → url_for('student_announcements.announcements')

Do not modify any other feature (Analytics, Leaderboard, Notifications).
Do not add a second <script src="socket.io"> tag — only one global instance.
```

---

## Summary of all files touched

| File | Action |
|---|---|
| `app/models/announcement.py` | **Create** |
| `app/services/announcements.py` | **Create** |
| `app/blueprints/admin/announcements.py` | **Create** |
| `app/blueprints/student/announcements.py` | **Create** |
| `app/templates/admin/announcements.html` | **Create** |
| `app/templates/student/announcements.html` | **Create** |
| `app/__init__.py` | **Modify** — register 2 blueprints |
| `templates/base.html` | **Modify** — SocketIO block + nav badges |
| DB migration | **Run** — `flask db migrate` + `flask db upgrade` |
