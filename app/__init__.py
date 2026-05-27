import os

from flask import Flask
from .extensions import db, migrate, socketio, csrf


def create_app(config_object="app.config.Config") -> Flask:
    app = Flask(__name__, instance_relative_config=False,
                template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))
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
    from app.models import (  # noqa: F401
        event, user, registration, attendance, announcement, score,
        notification, user_setting, system_setting,
    )

    # ── Blueprints ────────────────────────────────────────────────────────
    from app.blueprints.admin.analytics import bp as analytics_bp
    app.register_blueprint(analytics_bp)
    from app.blueprints.admin.announcements import bp as announcements_bp
    app.register_blueprint(announcements_bp)
    from app.blueprints.student.announcements import bp as student_ann_bp
    app.register_blueprint(student_ann_bp)

    # ── SocketIO handlers ─────────────────────────────────────────────────
    from app.sockets import notifications  # noqa: F401

    return app
