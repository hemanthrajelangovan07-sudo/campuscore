from app.extensions import db


class Venue(db.Model):
    __tablename__ = "venue"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=0)
    location = db.Column(db.String(200))

    events = db.relationship('Event', backref='venue_ref', lazy=True)

    def __repr__(self):
        return f"<Venue {self.name}>"
