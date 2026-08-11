from flask import session
from flask_socketio import emit, join_room

from .extensions import socketio

def register_socket_handlers() -> None:
    @socketio.on("connect", namespace="/social")
    def connected(_auth=None):
        user_id = session.get("user_id")
        if user_id:
            join_room(f"user:{user_id}")
        emit(
            "server.ready",
            {"namespace": "/social", "authenticated": bool(session.get("user_id"))},
        )

    from social.sockets import register_social_socket_handlers

    register_social_socket_handlers()
