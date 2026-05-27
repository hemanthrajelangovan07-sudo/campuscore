from datetime import datetime

from app.extensions import db


class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    role = db.Column(db.String(20), default='student')
    reg_number = db.Column(db.String(50))
    department = db.Column(db.String(100))
    college = db.Column(db.String(200), default='Sathyabama Institute of Science and Technology')
    phone = db.Column(db.String(15))
    year_of_study = db.Column(db.Integer)
    github_url = db.Column(db.String(255))
    linkedin_url = db.Column(db.String(255))
    profile_photo_url = db.Column(db.String(255))
    participant_id = db.Column(db.String(20), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    force_password_reset = db.Column(db.Boolean, default=False)
    reset_token = db.Column(db.String(128), nullable=True)
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    profile_image = db.Column(db.String(500))
    last_login = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    registrations = db.relationship('Registration', backref='user', lazy=True)
    attendances = db.relationship('Attendance', backref='user', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

    def get_unread_notifications(self):
        from app.models.notification import Notification
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()
