from app.extensions import db


class NotificationPreference(db.Model):
    __tablename__ = "notification_preference"

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    event_reminders = db.Column(db.Boolean, default=True)
    registration_confirmations = db.Column(db.Boolean, default=True)
    waitlist_updates = db.Column(db.Boolean, default=True)
    certificate_ready = db.Column(db.Boolean, default=True)
    marketing_new_events = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref=db.backref('notification_prefs', uselist=False))
