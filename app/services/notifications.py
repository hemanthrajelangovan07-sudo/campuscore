from app.extensions import socketio


def notify_new_event(title: str, date: str, venue: str) -> None:
    socketio.emit("notification", {
        "type": "event_created",
        "title": "New Event Published",
        "body": f"{title} · {date} at {venue or 'TBD'}",
    })


def notify_attendance_marked(user_id: int, event_title: str) -> None:
    socketio.emit("notification", {
        "type": "attendance_marked",
        "title": "Attendance Confirmed ✓",
        "body": f'You are marked Present for "{event_title}". Your certificate is ready.',
    }, room=f"user_{user_id}")
