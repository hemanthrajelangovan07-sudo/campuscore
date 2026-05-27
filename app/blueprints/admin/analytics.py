from flask import Blueprint, render_template

from app.services.analytics import get_event_analytics, get_category_stats
from app.utils.auth import roles_required

bp = Blueprint("admin_analytics", __name__, url_prefix="/admin")


@bp.route("/analytics")
@roles_required("admin", "organizer")
def analytics():
    event_analytics = get_event_analytics()
    category_stats = get_category_stats()

    cat_labels = [s.category for s in category_stats]
    cat_counts = [s.count for s in category_stats]

    event_analytics_json = [
        {
            "category": ea.category,
            "registrations": ea.total_registrations,
            "present": ea.total_present,
            "absent": ea.total_absent,
        }
        for ea in event_analytics
    ]

    return render_template(
        "admin/analytics.html",
        event_analytics=event_analytics,
        cat_labels=cat_labels,
        cat_counts=cat_counts,
        event_analytics_json=event_analytics_json,
    )
