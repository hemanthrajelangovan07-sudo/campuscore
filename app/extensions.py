from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()
