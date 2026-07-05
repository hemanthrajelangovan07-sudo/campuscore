import secrets
from datetime import datetime

from app.extensions import db


class Certificate(db.Model):
    __tablename__ = "certificate"

    id = db.Column(db.Integer, primary_key=True)
    verification_code = db.Column(db.String(32), unique=True, nullable=False,
                                   default=lambda: secrets.token_hex(16))
    registration_id = db.Column(db.Integer, db.ForeignKey('registration.id'), nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow)
    pdf_path = db.Column(db.String(255))
    revoked = db.Column(db.Boolean, default=False)

    registration = db.relationship('Registration', backref=db.backref('certificate', uselist=False))
