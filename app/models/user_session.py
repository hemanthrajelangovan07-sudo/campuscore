import secrets
from datetime import datetime

from app.extensions import db


class UserSession(db.Model):
    __tablename__ = "user_session"

    id = db.Column(db.Integer, primary_key=True)
    session_token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_agent = db.Column(db.String(255))
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_active_at = db.Column(db.DateTime, default=datetime.utcnow)
    revoked = db.Column(db.Boolean, default=False)
