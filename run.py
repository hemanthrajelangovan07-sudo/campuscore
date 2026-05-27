#!/usr/bin/env python3
"""
CampusCore – Sathyabama Institute of Science and Technology
Event Management System

Run this file to start the application.
"""
from app_legacy import app, socketio, init_db

if __name__ == '__main__':
    print("=" * 55)
    print("  CampusCore — SIST Event Management Portal")
    print("=" * 55)
    init_db()
    print("\n  🚀  Starting server at http://localhost:5000")
    print("  Press CTRL+C to stop\n")
    socketio.run(app, debug=True, port=5000, host='0.0.0.0', allow_unsafe_werkzeug=True)
