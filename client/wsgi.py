"""Production WSGI entry point for Gunicorn."""

from peerxiv import create_app
from peerxiv.extensions import socketio

app = create_app()

__all__ = ["app", "socketio"]
