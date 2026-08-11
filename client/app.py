"""Backward-compatible PeerXiv launch entry point.

Use ``python3 server.py`` for new development. Existing commands that invoke
``python3 app.py`` continue to start the same Flask-SocketIO application.
"""

from server import app, main, socketio

__all__ = ["app", "socketio"]


if __name__ == "__main__":
    main()
