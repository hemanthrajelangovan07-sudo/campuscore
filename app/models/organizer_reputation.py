from datetime import datetime

from app.extensions import db


class OrganizerReputationSnapshot(db.Model):
    __tablename__ = "organizer_reputation_snapshot"

    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    avg_event_rating = db.Column(db.Float, nullable=True)
    no_show_rate_pct = db.Column(db.Float, nullable=True)
    approval_rate_pct = db.Column(db.Float, nullable=True)
    total_events_run = db.Column(db.Integer, default=0)
    computed_at = db.Column(db.DateTime, default=datetime.utcnow)

    organizer = db.relationship('User', backref=db.backref('reputation_snapshots', lazy=True))
