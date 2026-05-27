from datetime import datetime

from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    changes = db.Column(db.Text)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='audit_logs')
    changed_by_user = db.relationship('User', foreign_keys=[changed_by])