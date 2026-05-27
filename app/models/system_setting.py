from app.extensions import db


class SystemSetting(db.Model):
    __tablename__ = "system_setting"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
