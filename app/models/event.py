from datetime import date, datetime

from app.extensions import db


class Event(db.Model):
    __tablename__ = "event"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    time = db.Column(db.String(20))
    venue = db.Column(db.String(200))
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

    registrations = db.relationship('Registration', backref='event', lazy=True)
    attendances = db.relationship('Attendance', backref='event', lazy=True)

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
