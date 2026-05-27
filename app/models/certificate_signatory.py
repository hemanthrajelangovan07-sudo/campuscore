from app.extensions import db


class CertificateSignatory(db.Model):
    __tablename__ = 'certificate_signatory'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    title = db.Column(db.String(200), nullable=False, default='Event Coordinator')
    signature_image = db.Column(db.String(500))
    ordering = db.Column(db.Integer, default=0)

    event = db.relationship('Event', backref=db.backref('signatories', lazy=True, cascade='all, delete-orphan'))
