from datetime import datetime

from app.extensions import db


class AccountDeletionRequest(db.Model):
    __tablename__ = "account_deletion_request"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    scheduled_for = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='pending')
