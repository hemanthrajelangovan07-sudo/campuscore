from datetime import date, datetime

from app.extensions import db
from app.models.mixins import SoftDeleteMixin


class Event(db.Model, SoftDeleteMixin):
    __tablename__ = "event"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    time = db.Column(db.String(20))
    venue = db.Column(db.String(200))
    venue_id = db.Column(db.Integer, db.ForeignKey('venue.id'), nullable=True)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    category = db.Column(db.String(50), default='General')
    max_participants = db.Column(db.Integer, default=100)
    registration_deadline = db.Column(db.Date, nullable=True)
    image_url = db.Column(db.String(500))
    pdf_file = db.Column(db.String(255), default=None)
    tags = db.Column(db.Text, default='')
    organizer_name = db.Column(db.String(100))
    status = db.Column(db.String(20), default='upcoming')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Approval workflow
    approval_status = db.Column(db.String(20), default='approved')
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    revision_count = db.Column(db.Integer, default=0)
    previous_rejection_reason = db.Column(db.Text, nullable=True)

    registrations = db.relationship('Registration', backref='event', lazy=True)
    attendances = db.relationship('Attendance', backref='event', lazy=True)

    submitted_by_user = db.relationship('User', foreign_keys=[submitted_by])
    reviewed_by_user = db.relationship('User', foreign_keys=[reviewed_by])

    @property
    def computed_status(self):
        today = date.today()
        if self.status == 'cancelled':
            return 'cancelled'
        if self.status == 'draft':
            return 'draft'
        if self.date < today:
            return 'completed'
        if self.date == today:
            return 'active'
        return 'upcoming'
