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
