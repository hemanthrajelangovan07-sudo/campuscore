from datetime import datetime

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(30), default='system')
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    related_event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
