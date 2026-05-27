from flask import request
from app.extensions import db
from app.models.audit_log import AuditLog


def log_audit(target_user_id, action, changed_by, changes=None, old_value=None, new_value=None):
    log = AuditLog(
        user_id=target_user_id,
        action=action,
        changed_by=changed_by,
        changes=changes,
        old_value=old_value,
        new_value=new_value,
        ip_address=request.remote_addr or request.headers.get('X-Forwarded-For', '') or ''
    )
    db.session.add(log)
    return log