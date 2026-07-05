from datetime import datetime

from app.extensions import db
from app.models.mixins import SoftDeleteMixin


class Registration(db.Model, SoftDeleteMixin):
    __tablename__ = "registration"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    status = db.Column(db.String(20), default='confirmed')
    waitlist_position = db.Column(db.Integer, nullable=True)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

    attendance = db.relationship('Attendance', backref='registration', uselist=False, lazy=True)

    __table_args__ = (db.UniqueConstraint('user_id', 'event_id'),)
