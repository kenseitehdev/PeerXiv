import hmac

from flask import session
from flask_socketio import emit, join_room
from sqlalchemy import select

from accounts.services import create_notification
from peerxiv.extensions import db, socketio

from .models import ConversationParticipant, Discussion, Message
from .schemas import MessageCreate


def register_social_socket_handlers() -> None:
    @socketio.on("paper.watch", namespace="/social")
    def watch_paper(payload):
        paper_id = str((payload or {}).get("paper_id", "")).strip()
        if not paper_id:
            return {"ok": False, "error": "paper_id_required"}
        room = f"paper:{paper_id}"
        join_room(room)
        return {"ok": True, "room": room}

    @socketio.on("discussion.watch", namespace="/social")
    def watch_discussion(payload):
        discussion_id = str((payload or {}).get("discussion_id", "")).strip()
        if not discussion_id or db.session.get(Discussion, discussion_id) is None:
            return {"ok": False, "error": "discussion_not_found"}
        room = f"discussion:{discussion_id}"
        join_room(room)
        return {"ok": True, "room": room}

    @socketio.on("conversation.join", namespace="/social")
    def join_conversation(payload):
        user_id = session.get("user_id")
        if not user_id:
            return {"ok": False, "error": "authentication_required"}
        conversation_id = str((payload or {}).get("conversation_id", "")).strip()
        if not conversation_id:
            return {"ok": False, "error": "conversation_id_required"}
        membership = db.session.scalar(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        if membership is None:
            return {"ok": False, "error": "conversation_forbidden"}
        room = f"conversation:{conversation_id}"
        join_room(room)
        return {"ok": True, "room": room}

    @socketio.on("message.send", namespace="/social")
    def send_message(payload):
        user_id = session.get("user_id")
        if not user_id:
            return {"ok": False, "error": "authentication_required"}
        supplied = str((payload or {}).get("csrf_token", ""))
        if not supplied or not hmac.compare_digest(str(session.get("csrf_token", "")), supplied):
            return {"ok": False, "error": "csrf_failed"}
        conversation_id = str((payload or {}).get("conversation_id", "")).strip()
        raw_body = (payload or {}).get("body", "")
        if not conversation_id or not str(raw_body).strip():
            return {"ok": False, "error": "conversation_and_body_required"}
        if len(str(raw_body)) > 10_000:
            return {"ok": False, "error": "message_too_long"}
        try:
            body = MessageCreate.model_validate({"body": raw_body}).body
        except ValueError:
            return {"ok": False, "error": "invalid_message"}
        membership = db.session.scalar(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id,
                ConversationParticipant.user_id == user_id,
            )
        )
        if membership is None:
            return {"ok": False, "error": "conversation_forbidden"}
        message = Message(conversation_id=conversation_id, author_id=user_id, body=body)
        db.session.add(message)
        db.session.flush()
        participants = db.session.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation_id
            )
        )
        for participant in participants:
            if participant.user_id == user_id:
                continue
            create_notification(
                participant.user_id,
                actor_id=user_id,
                kind="new-message",
                text="You received a new research message",
                object_type="conversation",
                object_id=conversation_id,
                dedupe_key=f"message:{message.id}:{participant.user_id}",
            )
        db.session.commit()
        output = message.to_dict()
        emit("message.created", output, room=f"conversation:{conversation_id}")
        return {"ok": True, "message": output}
