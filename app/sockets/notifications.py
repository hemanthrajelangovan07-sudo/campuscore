from flask import session
from flask_socketio import join_room

from app.extensions import socketio


@socketio.on("connect")
def on_connect():
    user_id = session.get("user_id")
    if user_id:
        join_room(f"user_{user_id}")
