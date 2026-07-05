from datetime import datetime

from app.extensions import db


class SoftDeleteMixin:
    deleted_at = db.Column(db.DateTime, nullable=True)

    def soft_delete(self):
        self.deleted_at = datetime.utcnow()

    @property
    def is_deleted(self):
        return self.deleted_at is not None
