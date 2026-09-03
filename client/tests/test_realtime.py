from peerxiv.extensions import db, socketio
from social.models import Conversation, ConversationParticipant


def test_public_paper_room_and_private_chat_guard(socket_client):
    received = socket_client.get_received("/social")
    assert received[0]["name"] == "server.ready"

    watched = socket_client.emit(
        "paper.watch",
        {"paper_id": "px:2608.test"},
        namespace="/social",
        callback=True,
    )
    assert watched == {"ok": True, "room": "paper:px:2608.test"}

    message = socket_client.emit(
        "message.send",
        {"conversation_id": "test", "body": "hello"},
        namespace="/social",
        callback=True,
    )
    assert message == {"ok": False, "error": "authentication_required"}


def test_authenticated_conversation_message_and_size_guard(app, client):
    session_payload = client.get("/api/v1/accounts/me").get_json()
    user_id = session_payload["user"]["id"]
    with app.app_context():
        conversation = Conversation(title="Release coordination")
        db.session.add(conversation)
        db.session.flush()
        conversation_id = conversation.id
        db.session.add(
            ConversationParticipant(conversation_id=conversation_id, user_id=user_id)
        )
        db.session.commit()

    live = socketio.test_client(app, flask_test_client=client, namespace="/social")
    assert live.emit(
        "conversation.join",
        {"conversation_id": conversation_id},
        namespace="/social",
        callback=True,
    )["ok"] is True

    sent = live.emit(
        "message.send",
        {
            "conversation_id": conversation_id,
            "body": "Deployment smoke test",
            "csrf_token": session_payload["csrf_token"],
        },
        namespace="/social",
        callback=True,
    )
    assert sent["ok"] is True
    assert sent["message"]["body"] == "Deployment smoke test"

    too_long = live.emit(
        "message.send",
        {
            "conversation_id": conversation_id,
            "body": "x" * 10_001,
            "csrf_token": session_payload["csrf_token"],
        },
        namespace="/social",
        callback=True,
    )
    assert too_long == {"ok": False, "error": "message_too_long"}
    live.disconnect(namespace="/social")
