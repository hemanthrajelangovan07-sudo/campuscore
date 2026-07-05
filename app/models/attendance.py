from datetime import datetime

from app.extensions import db


class Attendance(db.Model):
    __tablename__ = "attendance"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey('registration.id'), unique=True, nullable=True)
    status = db.Column(db.String(20), default='absent')
    method = db.Column(db.String(20), default='manual')
    checked_in_at = db.Column(db.DateTime, nullable=True)
    checked_in_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'event_id'),)
