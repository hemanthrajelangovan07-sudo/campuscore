from datetime import datetime

from app.extensions import db


class UserSetting(db.Model):
    __tablename__ = "user_setting"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    email_notifications = db.Column(db.Boolean, default=True)
    theme = db.Column(db.String(20), default='light')
    language = db.Column(db.String(20), default='english')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
