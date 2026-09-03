from flask import g, jsonify, request
from sqlalchemy import select

from accounts.auth import current_account, require_auth
from accounts.models import Account
from accounts.services import (
    create_notification,
    notify_followers,
    persist_match_notifications,
    record_activity,
    record_interests,
)
from discovery.notifications import classify_and_match_notifications
from discovery.schemas import NotificationClassificationInput
from papers.models import Paper
from peerxiv.extensions import db, limiter, socketio

from . import blueprint
from .models import (
    Comment,
    Conversation,
    ConversationParticipant,
    Discussion,
    DiscussionFollow,
    DiscussionSave,
    DiscussionVote,
    Message,
    utc_now,
)
from .schemas import (
    CommentCreate,
    ConversationCreate,
    DiscussionCreate,
    MessageCreate,
    ToggleInput,
    VoteInput,
)


def _discussion_or_404(discussion_id: str):
    discussion = db.session.get(Discussion, discussion_id)
    if discussion is None:
        return None, (jsonify({"error": {"code": "discussion_not_found"}}), 404)
    return discussion, None


def _conversation_for_viewer(conversation_id: str):
    membership = db.session.scalar(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == g.current_account.id,
        )
    )
    if membership is None:
        return None, None, (
            jsonify({"error": {"code": "conversation_not_found", "message": "Conversation not found"}}),
            404,
        )
    return membership.conversation, membership, None


def _classification_for_activity(*, kind: str, source_id: str, title: str, text: str, user_id: str):
    result = classify_and_match_notifications(
        NotificationClassificationInput(
            source_kind="discussion" if kind == "discussion" else "comment",
            source_id=source_id,
            title=title,
            text=text,
            exclude_authors=[g.current_account.display_name],
        )
    )
    metadata = result["source_classification"]["metadata"]
    record_interests(user_id, metadata["tags"], source_kind=kind)
    persist_match_notifications(user_id, result["notifications"])
    return result


@blueprint.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "module": "social",
            "realtime_namespace": "/social",
            "events": [
                "discussion.created",
                "discussion.comment.created",
                "paper.watch",
                "conversation.join",
                "message.send",
            ],
        }
    )


@blueprint.get("/conversations")
@require_auth
def conversations_index():
    conversations = list(db.session.scalars(
        select(Conversation)
        .join(ConversationParticipant)
        .where(ConversationParticipant.user_id == g.current_account.id)
        .order_by(Conversation.created_at.desc())
        .limit(100)
    ).unique())
    conversations.sort(
        key=lambda conversation: (
            conversation.messages[-1].created_at
            if conversation.messages
            else conversation.created_at
        ),
        reverse=True,
    )
    return jsonify(
        {"results": [conversation.to_dict(viewer_id=g.current_account.id) for conversation in conversations]}
    )


@blueprint.post("/conversations")
@require_auth
@limiter.limit("20 per hour")
def create_conversation():
    payload = ConversationCreate.model_validate(request.get_json(silent=True) or {})
    recipient = db.session.scalar(
        select(Account).where(Account.email == payload.recipient_email, Account.active.is_(True))
    )
    if recipient is None:
        return jsonify(
            {"error": {"code": "recipient_not_found", "message": "No active account uses that email"}}
        ), 404
    if recipient.id == g.current_account.id:
        return jsonify(
            {"error": {"code": "self_conversation", "message": "Choose another researcher"}}
        ), 400

    conversation = Conversation(title=payload.title or "Research conversation")
    db.session.add(conversation)
    db.session.flush()
    db.session.add_all(
        [
            ConversationParticipant(conversation_id=conversation.id, user_id=g.current_account.id),
            ConversationParticipant(conversation_id=conversation.id, user_id=recipient.id),
        ]
    )
    message = Message(
        conversation_id=conversation.id,
        author_id=g.current_account.id,
        body=payload.body,
    )
    db.session.add(message)
    db.session.flush()
    create_notification(
        recipient.id,
        actor_id=g.current_account.id,
        kind="new-message",
        text=f"{g.current_account.display_name} sent you a message",
        object_type="conversation",
        object_id=conversation.id,
        dedupe_key=f"message:{message.id}:{recipient.id}",
    )
    db.session.commit()
    for user_id in (g.current_account.id, recipient.id):
        socketio.emit(
            "conversation.created",
            conversation.to_dict(viewer_id=user_id, include_messages=True),
            room=f"user:{user_id}",
            namespace="/social",
        )
    output = conversation.to_dict(viewer_id=g.current_account.id, include_messages=True)
    return jsonify(output), 201


@blueprint.get("/conversations/<conversation_id>/messages")
@require_auth
def conversation_messages(conversation_id: str):
    conversation, _membership, error = _conversation_for_viewer(conversation_id)
    if error:
        return error
    return jsonify(
        {
            "conversation": conversation.to_dict(viewer_id=g.current_account.id),
            "results": [message.to_dict() for message in conversation.messages[-200:]],
        }
    )


@blueprint.post("/conversations/<conversation_id>/messages")
@require_auth
@limiter.limit("120 per minute")
def create_conversation_message(conversation_id: str):
    conversation, _membership, error = _conversation_for_viewer(conversation_id)
    if error:
        return error
    payload = MessageCreate.model_validate(request.get_json(silent=True) or {})
    message = Message(
        conversation_id=conversation.id,
        author_id=g.current_account.id,
        body=payload.body,
    )
    db.session.add(message)
    db.session.flush()
    for participant in conversation.participants:
        if participant.user_id == g.current_account.id:
            continue
        create_notification(
            participant.user_id,
            actor_id=g.current_account.id,
            kind="new-message",
            text=f"{g.current_account.display_name} sent you a message",
            object_type="conversation",
            object_id=conversation.id,
            dedupe_key=f"message:{message.id}:{participant.user_id}",
        )
    db.session.commit()
    output = message.to_dict()
    socketio.emit("message.created", output, room=f"conversation:{conversation.id}", namespace="/social")
    return jsonify(output), 201


@blueprint.post("/conversations/<conversation_id>/read")
@require_auth
def mark_conversation_read(conversation_id: str):
    _conversation, membership, error = _conversation_for_viewer(conversation_id)
    if error:
        return error
    membership.last_read_at = utc_now()
    db.session.commit()
    return jsonify({"read": True, "read_at": membership.last_read_at.isoformat()})


@blueprint.get("/discussions")
def discussions_index():
    account = current_account()
    viewer_id = account.id if account else None
    statement = select(Discussion)
    paper_identifier = request.args.get("paper")
    if paper_identifier:
        statement = statement.join(Paper).where(Paper.identifier == paper_identifier)
    filter_name = request.args.get("filter", "active")
    if filter_name == "following" and viewer_id:
        statement = statement.join(DiscussionFollow).where(DiscussionFollow.user_id == viewer_id)
    elif filter_name == "saved" and viewer_id:
        statement = statement.join(DiscussionSave).where(DiscussionSave.user_id == viewer_id)
    ordering = Discussion.created_at.desc() if filter_name == "new" else Discussion.score.desc()
    results = db.session.scalars(statement.order_by(ordering).limit(100)).unique()
    return jsonify({"results": [item.to_dict(viewer_id=viewer_id) for item in results]})


@blueprint.post("/discussions")
@require_auth
def create_discussion():
    payload = DiscussionCreate.model_validate(request.get_json(silent=True) or {})
    paper = None
    if payload.paper_identifier:
        paper = db.session.scalar(select(Paper).where(Paper.identifier == payload.paper_identifier))
        if paper is None:
            return jsonify({"error": {"code": "paper_not_found"}}), 404
    discussion = Discussion(
        paper=paper,
        author_id=g.current_account.id,
        topic=payload.topic.strip(),
        title=payload.title.strip(),
        body=payload.body.strip(),
        score=1,
    )
    db.session.add(discussion)
    db.session.flush()
    db.session.add(DiscussionFollow(discussion=discussion, user_id=g.current_account.id))
    result = _classification_for_activity(
        kind="discussion",
        source_id=discussion.id,
        title=discussion.title,
        text=discussion.body,
        user_id=g.current_account.id,
    )
    record_activity(
        g.current_account.id,
        verb="started",
        object_type="discussion",
        object_id=discussion.id,
        summary=f"{g.current_account.display_name} started {discussion.title}",
        payload={"paper": paper.identifier if paper else None, "topic": discussion.topic},
    )
    notify_followers(
        g.current_account.id,
        kind="followed-researcher-discussion",
        text=f"{g.current_account.display_name} started a discussion: {discussion.title}",
        dedupe_suffix=f"discussion:{discussion.id}",
        object_type="discussion",
        object_id=discussion.id,
    )
    if paper and paper.owner_id and paper.owner_id != g.current_account.id:
        create_notification(
            paper.owner_id,
            actor_id=g.current_account.id,
            kind="paper-discussion",
            text=f"{g.current_account.display_name} started a discussion on {paper.title}",
            object_type="discussion",
            object_id=discussion.id,
            payload={"paper": paper.identifier},
            dedupe_key=f"paper-discussion:{discussion.id}",
        )
    db.session.commit()
    payload_out = discussion.to_dict(viewer_id=g.current_account.id, include_comments=True)
    payload_out["classification"] = result["source_classification"]
    payload_out["notifications"] = result["notifications"]
    socketio.emit("discussion.created", payload_out, namespace="/social")
    if paper:
        socketio.emit("discussion.created", payload_out, room=f"paper:{paper.identifier}", namespace="/social")
    return jsonify(payload_out), 201


@blueprint.get("/discussions/<discussion_id>")
def discussion_detail(discussion_id: str):
    discussion, error = _discussion_or_404(discussion_id)
    if error:
        return error
    account = current_account()
    return jsonify(
        discussion.to_dict(
            viewer_id=account.id if account else None,
            include_comments=True,
        )
    )


@blueprint.post("/discussions/<discussion_id>/comments")
@require_auth
def create_comment(discussion_id: str):
    discussion, error = _discussion_or_404(discussion_id)
    if error:
        return error
    payload = CommentCreate.model_validate(request.get_json(silent=True) or {})
    if payload.parent_id:
        parent = db.session.scalar(
            select(Comment).where(
                Comment.id == payload.parent_id,
                Comment.discussion_id == discussion.id,
            )
        )
        if parent is None:
            return jsonify({"error": {"code": "parent_comment_not_found"}}), 404
    comment = Comment(
        discussion=discussion,
        author_id=g.current_account.id,
        parent_id=payload.parent_id,
        body=payload.body.strip(),
    )
    db.session.add(comment)
    db.session.flush()
    result = _classification_for_activity(
        kind="comment",
        source_id=comment.id,
        title=f"Reply to {discussion.title}",
        text=comment.body,
        user_id=g.current_account.id,
    )
    record_activity(
        g.current_account.id,
        verb="replied",
        object_type="discussion",
        object_id=discussion.id,
        summary=f"{g.current_account.display_name} replied to {discussion.title}",
        payload={"comment_id": comment.id},
    )
    if discussion.author_id != g.current_account.id:
        create_notification(
            discussion.author_id,
            actor_id=g.current_account.id,
            kind="discussion-reply",
            text=f"{g.current_account.display_name} replied to {discussion.title}",
            object_type="discussion",
            object_id=discussion.id,
            payload={"comment_id": comment.id},
            dedupe_key=f"discussion-reply:{comment.id}:{discussion.author_id}",
        )
    for follower in discussion.followers:
        if follower.user_id in {g.current_account.id, discussion.author_id}:
            continue
        create_notification(
            follower.user_id,
            actor_id=g.current_account.id,
            kind="followed-discussion-reply",
            text=f"New reply in {discussion.title}",
            object_type="discussion",
            object_id=discussion.id,
            payload={"comment_id": comment.id},
            dedupe_key=f"followed-discussion-reply:{comment.id}:{follower.user_id}",
        )
    db.session.commit()
    output = comment.to_dict()
    output["classification"] = result["source_classification"]
    output["notifications"] = result["notifications"]
    socketio.emit(
        "discussion.comment.created",
        output,
        room=f"discussion:{discussion.id}",
        namespace="/social",
    )
    return jsonify(output), 201


def _toggle_relationship(model, discussion: Discussion, enabled: bool | None):
    existing = db.session.scalar(
        select(model).where(
            model.discussion_id == discussion.id,
            model.user_id == g.current_account.id,
        )
    )
    desired = existing is None if enabled is None else enabled
    if desired and existing is None:
        db.session.add(model(discussion=discussion, user_id=g.current_account.id))
    elif not desired and existing is not None:
        db.session.delete(existing)
    db.session.commit()
    return desired


@blueprint.post("/discussions/<discussion_id>/follow")
@require_auth
def follow_discussion(discussion_id: str):
    discussion, error = _discussion_or_404(discussion_id)
    if error:
        return error
    payload = ToggleInput.model_validate(request.get_json(silent=True) or {})
    return jsonify({"following": _toggle_relationship(DiscussionFollow, discussion, payload.enabled)})


@blueprint.post("/discussions/<discussion_id>/save")
@require_auth
def save_discussion(discussion_id: str):
    discussion, error = _discussion_or_404(discussion_id)
    if error:
        return error
    payload = ToggleInput.model_validate(request.get_json(silent=True) or {})
    return jsonify({"saved": _toggle_relationship(DiscussionSave, discussion, payload.enabled)})


@blueprint.post("/discussions/<discussion_id>/vote")
@require_auth
def vote_discussion(discussion_id: str):
    discussion, error = _discussion_or_404(discussion_id)
    if error:
        return error
    payload = VoteInput.model_validate(request.get_json(silent=True) or {})
    existing = db.session.scalar(
        select(DiscussionVote).where(
            DiscussionVote.discussion_id == discussion.id,
            DiscussionVote.user_id == g.current_account.id,
        )
    )
    previous = existing.value if existing else 0
    if payload.value == 0:
        if existing:
            db.session.delete(existing)
    elif existing:
        existing.value = payload.value
    else:
        db.session.add(
            DiscussionVote(
                discussion=discussion,
                user_id=g.current_account.id,
                value=payload.value,
            )
        )
    discussion.score += payload.value - previous
    db.session.commit()
    return jsonify({"score": discussion.score, "viewer_vote": payload.value})
