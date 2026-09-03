import sqlite3

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
limiter = Limiter(key_func=get_remote_address)


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def initialize_extensions(app) -> None:
    db.init_app(app)
    migrate.init_app(app, db, compare_type=True)
    limiter.init_app(app)
    socketio.init_app(
        app,
        async_mode=app.config["SOCKETIO_ASYNC_MODE"],
        cors_allowed_origins=app.config["FRONTEND_ORIGINS"],
        message_queue=app.config["SOCKETIO_MESSAGE_QUEUE"],
        channel=app.config["SOCKETIO_CHANNEL"],
        manage_session=True,
    )
