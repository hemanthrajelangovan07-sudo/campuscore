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
