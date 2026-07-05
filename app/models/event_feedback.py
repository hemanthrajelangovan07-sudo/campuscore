from datetime import datetime

from app.extensions import db


class EventFeedback(db.Model):
    __tablename__ = "event_feedback"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    event = db.relationship('Event', backref=db.backref('feedbacks', lazy=True))
    user = db.relationship('User', backref=db.backref('feedbacks', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('event_id', 'user_id', name='one_review_per_user_per_event'),
        db.CheckConstraint('rating >= 1 AND rating <= 5', name='rating_range'),
    )
