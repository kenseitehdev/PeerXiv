"""PeerXiv backend/frontend server entry point."""

from peerxiv import create_app
from peerxiv.extensions import socketio

app = create_app()


def main() -> None:
    socketio.run(
        app,
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        use_reloader=app.config["DEBUG"],
    )


if __name__ == "__main__":
    main()
