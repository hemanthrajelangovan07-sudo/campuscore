from functools import wraps
from flask import session, abort


def roles_required(*roles: str):
    """Restrict a view to users whose role is in *roles*.

    Usage::

        @app.route('/admin/analytics')
        @roles_required('admin', 'organizer')
        def admin_analytics(): ...
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            role = session.get("role")
            if role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator
