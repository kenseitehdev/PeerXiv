import hmac

from flask import current_app, g, jsonify, request, session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from peerxiv.extensions import db
from peerxiv.extensions import limiter

from . import blueprint
from .auth import current_account, establish_session, require_auth
from .models import Account, Notification, UserFollow, utc_now
from .schemas import LoginInput, ProfileInput, RegisterInput
from .services import activity_feed, create_notification, recommended_people, record_activity


def _session_payload(account: Account, csrf_token: str) -> dict[str, object]:
    return {
        "authenticated": True,
        "user": account.to_dict(private=True),
        "csrf_token": csrf_token,
    }


@blueprint.post("/register")
@limiter.limit("5 per minute; 20 per hour")
def register():
    payload = RegisterInput.model_validate(request.get_json(silent=True) or {})
    registration_mode = current_app.config["REGISTRATION_MODE"]
    if registration_mode == "disabled":
        return jsonify(
            {"error": {"code": "registration_disabled", "message": "Registration is closed"}}
        ), 403
    if registration_mode == "invite":
        expected = str(current_app.config["ALPHA_INVITE_CODE"])
        supplied = str(payload.invite_code or "")
        if not expected or not hmac.compare_digest(expected, supplied):
            return jsonify(
                {
                    "error": {
                        "code": "invite_required",
                        "message": "A valid alpha invitation code is required",
                    }
                }
            ), 403
    if db.session.scalar(select(Account).where(Account.email == payload.email)) is not None:
        return jsonify(
            {"error": {"code": "email_exists", "message": "An account already uses this email"}}
        ), 409
    account = Account(
        email=payload.email,
        display_name=payload.display_name.strip(),
        role=payload.role.strip(),
        bio=payload.bio.strip(),
    )
    account.set_password(payload.password)
    db.session.add(account)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return jsonify(
            {"error": {"code": "email_exists", "message": "An account already uses this email"}}
        ), 409
    record_activity(
        account.id,
        verb="joined",
        object_type="account",
        object_id=account.id,
        summary=f"{account.display_name} joined PeerXiv",
    )
    db.session.commit()
    csrf_token = establish_session(account)
    return jsonify(_session_payload(account, csrf_token)), 201


@blueprint.post("/login")
@limiter.limit("10 per minute; 50 per hour")
def login():
    payload = LoginInput.model_validate(request.get_json(silent=True) or {})
    account = db.session.scalar(select(Account).where(Account.email == payload.email))
    if account is None or not account.active or not account.check_password(payload.password):
        return jsonify(
            {"error": {"code": "invalid_credentials", "message": "Invalid email or password"}}
        ), 401
    csrf_token = establish_session(account)
    return jsonify(_session_payload(account, csrf_token))


@blueprint.post("/logout")
@require_auth
def logout():
    session.clear()
    return "", 204


@blueprint.get("/me")
def me():
    account = current_account()
    if account is None:
        return jsonify({"authenticated": False, "user": None, "csrf_token": None})
    return jsonify(_session_payload(account, str(session["csrf_token"])))


@blueprint.patch("/me")
@require_auth
def update_me():
    payload = ProfileInput.model_validate(request.get_json(silent=True) or {})
    account = g.current_account
    account.display_name = payload.display_name.strip()
    account.role = payload.role.strip()
    account.bio = payload.bio.strip()
    db.session.commit()
    return jsonify(account.to_dict(private=True))


@blueprint.get("/people/recommendations")
@require_auth
def recommendations():
    limit = min(max(request.args.get("limit", 12, type=int), 1), 50)
    return jsonify({"results": recommended_people(g.current_account.id, limit=limit)})


@blueprint.post("/people/<user_id>/follow")
@require_auth
def follow(user_id: str):
    actor = g.current_account
    target = db.session.get(Account, user_id)
    if target is None or not target.active:
        return jsonify({"error": {"code": "account_not_found", "message": "Account not found"}}), 404
    if target.id == actor.id:
        return jsonify({"error": {"code": "self_follow", "message": "You cannot follow yourself"}}), 400
    relationship = db.session.scalar(
        select(UserFollow).where(
            UserFollow.follower_id == actor.id, UserFollow.followed_id == target.id
        )
    )
    desired = (request.get_json(silent=True) or {}).get("following")
    following = relationship is not None if desired is None else bool(desired)
    if desired is None:
        following = relationship is None
    if following and relationship is None:
        db.session.add(UserFollow(follower_id=actor.id, followed_id=target.id))
        create_notification(
            target.id,
            actor_id=actor.id,
            kind="new-follower",
            text=f"{actor.display_name} followed your research",
            object_type="account",
            object_id=actor.id,
            dedupe_key=f"followed:{actor.id}",
        )
        record_activity(
            actor.id,
            verb="followed",
            object_type="account",
            object_id=target.id,
            summary=f"{actor.display_name} followed {target.display_name}",
        )
    elif not following and relationship is not None:
        db.session.delete(relationship)
    db.session.commit()
    return jsonify({"user_id": target.id, "following": following})


@blueprint.get("/notifications")
@require_auth
def notifications():
    unread_only = request.args.get("unread", "false").casefold() == "true"
    statement = select(Notification).where(Notification.user_id == g.current_account.id)
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    results = db.session.scalars(statement.order_by(Notification.created_at.desc()).limit(100))
    return jsonify({"results": [item.to_dict() for item in results]})


@blueprint.post("/notifications/<notification_id>/read")
@require_auth
def read_notification(notification_id: str):
    notification = db.session.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == g.current_account.id,
        )
    )
    if notification is None:
        return jsonify({"error": {"code": "notification_not_found"}}), 404
    notification.read_at = utc_now()
    db.session.commit()
    return jsonify(notification.to_dict())


@blueprint.post("/notifications/read-all")
@require_auth
def read_all_notifications():
    notifications = db.session.scalars(
        select(Notification).where(
            Notification.user_id == g.current_account.id,
            Notification.read_at.is_(None),
        )
    ).all()
    now = utc_now()
    for notification in notifications:
        notification.read_at = now
    db.session.commit()
    return jsonify({"updated": len(notifications)})


@blueprint.get("/activity")
@require_auth
def activities():
    limit = min(max(request.args.get("limit", 50, type=int), 1), 100)
    return jsonify(
        {"results": [item.to_dict() for item in activity_feed(g.current_account.id, limit=limit)]}
    )
