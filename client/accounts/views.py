import hmac
import secrets

from flask import current_app, g, jsonify, redirect, request, session, url_for
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from peerxiv.extensions import db
from peerxiv.extensions import limiter
from peerxiv.credentials import encrypt_credential

from . import blueprint
from .auth import current_account, establish_session, require_auth
from .invitations import consume_invitation
from .models import Account, Notification, UserFollow, ZenodoConnection, utc_now
from .orcid import OrcidExchangeError, authorization_url, exchange_code
from .schemas import LoginInput, ProfileInput, RegisterInput, ZenodoTokenInput
from .services import activity_feed, create_notification, recommended_people, record_activity
from .zenodo import ZenodoApiError, ZenodoClient


def _session_payload(account: Account, csrf_token: str) -> dict[str, object]:
    connection = _zenodo_connection(account)
    user = account.to_dict(private=True)
    user["zenodo"] = connection.to_dict() if connection else None
    return {
        "authenticated": True,
        "user": user,
        "csrf_token": csrf_token,
    }


def _zenodo_connection(account: Account) -> ZenodoConnection | None:
    return db.session.scalar(
        select(ZenodoConnection).where(
            ZenodoConnection.account_id == account.id,
            ZenodoConnection.environment == current_app.config["ZENODO_ENVIRONMENT"],
        )
    )


def _zenodo_client(token: str):
    factory = current_app.config.get("ZENODO_CLIENT_FACTORY") or ZenodoClient
    return factory(
        base_url=current_app.config["ZENODO_BASE_URL"],
        token=token,
        timeout=current_app.config["ZENODO_TIMEOUT"],
    )


def _orcid_return(status: str, *, reason: str | None = None):
    values = {"orcid": status}
    if reason:
        values["reason"] = reason[:120]
    return redirect(f"{url_for('server.frontend', **values)}#profile")


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
        bootstrap_match = bool(expected) and hmac.compare_digest(expected, supplied)
        generated_match = False
        if supplied and not bootstrap_match:
            generated_match = consume_invitation(supplied, email=payload.email)
        if not bootstrap_match and not generated_match:
            return jsonify(
                {
                    "error": {
                        "code": "invite_required",
                        "message": "A valid alpha invitation code is required",
                    }
                }
            ), 403
    if db.session.scalar(select(Account).where(Account.email == payload.email)) is not None:
        # Undo a generated invitation reservation when the email already exists.
        db.session.rollback()
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


@blueprint.get("/orcid/start")
@limiter.limit("20 per hour")
def start_orcid():
    if not current_app.config["ORCID_ENABLED"]:
        return jsonify(
            {
                "error": {
                    "code": "orcid_not_configured",
                    "message": "ORCID authentication is not configured on this PeerXiv instance",
                }
            }
        ), 503
    account = current_account()
    default_mode = "link" if account is not None else "login"
    mode = request.args.get("mode", default_mode).strip().casefold()
    if mode not in {"link", "login"}:
        return jsonify({"error": {"code": "invalid_orcid_mode"}}), 400
    if mode == "link" and account is None:
        return jsonify(
            {"error": {"code": "authentication_required", "message": "Sign in before linking ORCID"}}
        ), 401
    state = secrets.token_urlsafe(32)
    session["orcid_oauth"] = {"state": state, "mode": mode}
    redirect_uri = current_app.config["ORCID_REDIRECT_URI"] or url_for(
        "accounts.orcid_callback", _external=True
    )
    return jsonify(
        {
            "authorization_url": authorization_url(
                authorize_url=current_app.config["ORCID_AUTHORIZE_URL"],
                client_id=current_app.config["ORCID_CLIENT_ID"],
                redirect_uri=redirect_uri,
                state=state,
            ),
            "mode": mode,
        }
    )


@blueprint.get("/orcid/callback")
@limiter.limit("30 per hour")
def orcid_callback():
    oauth_state = session.pop("orcid_oauth", None) or {}
    expected_state = str(oauth_state.get("state") or "")
    supplied_state = str(request.args.get("state") or "")
    if not expected_state or not supplied_state or not hmac.compare_digest(expected_state, supplied_state):
        return _orcid_return("error", reason="state")
    if request.args.get("error"):
        return _orcid_return("cancelled")
    code = str(request.args.get("code") or "")
    if not code:
        return _orcid_return("error", reason="missing-code")

    redirect_uri = current_app.config["ORCID_REDIRECT_URI"] or url_for(
        "accounts.orcid_callback", _external=True
    )
    exchanger = current_app.config.get("ORCID_TOKEN_EXCHANGER") or exchange_code
    try:
        identity = exchanger(
            token_url=current_app.config["ORCID_TOKEN_URL"],
            client_id=current_app.config["ORCID_CLIENT_ID"],
            client_secret=current_app.config["ORCID_CLIENT_SECRET"],
            redirect_uri=redirect_uri,
            code=code,
            timeout=current_app.config["ORCID_TIMEOUT"],
        )
    except OrcidExchangeError:
        current_app.logger.warning("ORCID token exchange failed", exc_info=True)
        return _orcid_return("error", reason="exchange")

    linked_account = db.session.scalar(
        select(Account).where(Account.orcid_id == identity.identifier)
    )
    mode = str(oauth_state.get("mode") or "login")
    if mode == "login":
        if linked_account is None or not linked_account.active:
            return _orcid_return("unlinked")
        establish_session(linked_account)
        return _orcid_return("signed-in")

    account = current_account()
    if account is None:
        return _orcid_return("error", reason="session")
    if linked_account is not None and linked_account.id != account.id:
        return _orcid_return("conflict")
    account.orcid_id = identity.identifier
    account.orcid_name = identity.name
    account.orcid_linked_at = utc_now()
    record_activity(
        account.id,
        verb="verified",
        object_type="orcid",
        object_id=identity.identifier,
        summary=f"{account.display_name} verified an ORCID iD",
    )
    db.session.commit()
    return _orcid_return("linked")


@blueprint.delete("/orcid")
@require_auth
def unlink_orcid():
    account = g.current_account
    if account.orcid_id is None:
        return "", 204
    identifier = account.orcid_id
    account.orcid_id = None
    account.orcid_name = None
    account.orcid_linked_at = None
    record_activity(
        account.id,
        verb="unlinked",
        object_type="orcid",
        object_id=identifier,
        summary=f"{account.display_name} unlinked an ORCID iD",
    )
    db.session.commit()
    return "", 204


@blueprint.get("/zenodo")
@require_auth
def zenodo_status():
    connection = _zenodo_connection(g.current_account)
    return jsonify(
        {
            "enabled": current_app.config["ZENODO_ENABLED"],
            "environment": current_app.config["ZENODO_ENVIRONMENT"],
            "connection": connection.to_dict() if connection else None,
        }
    )


@blueprint.post("/zenodo")
@require_auth
@limiter.limit("5 per hour")
def connect_zenodo():
    if not current_app.config["ZENODO_ENABLED"]:
        return jsonify(
            {
                "error": {
                    "code": "zenodo_not_configured",
                    "message": "Encrypted provider credentials are not configured",
                }
            }
        ), 503
    payload = ZenodoTokenInput.model_validate(request.get_json(silent=True) or {})
    try:
        _zenodo_client(payload.token).verify()
    except ZenodoApiError as error:
        current_app.logger.info("Zenodo token verification failed with status %s", error.status)
        status = 400 if error.status in {401, 403} else 502
        return jsonify(
            {
                "error": {
                    "code": "zenodo_token_invalid" if status == 400 else "zenodo_unavailable",
                    "message": (
                        "Zenodo rejected this token. Confirm it has deposit:write and "
                        "deposit:actions scopes."
                        if status == 400
                        else "Zenodo could not verify the connection"
                    ),
                }
            }
        ), status

    connection = _zenodo_connection(g.current_account)
    if connection is None:
        connection = ZenodoConnection(
            account_id=g.current_account.id,
            environment=current_app.config["ZENODO_ENVIRONMENT"],
        )
        db.session.add(connection)
    connection.encrypted_token = encrypt_credential(
        payload.token, current_app.config["CREDENTIAL_ENCRYPTION_KEY"]
    )
    connection.token_hint = f"…{payload.token[-4:]}"
    connection.scopes = ["deposit:write", "deposit:actions"]
    connection.verified_at = utc_now()
    record_activity(
        g.current_account.id,
        verb="connected",
        object_type="zenodo",
        object_id=current_app.config["ZENODO_ENVIRONMENT"],
        summary=(
            f"{g.current_account.display_name} connected Zenodo "
            f"{current_app.config['ZENODO_ENVIRONMENT']}"
        ),
    )
    db.session.commit()
    return jsonify(connection.to_dict())


@blueprint.delete("/zenodo")
@require_auth
def disconnect_zenodo():
    connection = _zenodo_connection(g.current_account)
    if connection is None:
        return "", 204
    environment = connection.environment
    db.session.delete(connection)
    record_activity(
        g.current_account.id,
        verb="disconnected",
        object_type="zenodo",
        object_id=environment,
        summary=f"{g.current_account.display_name} disconnected Zenodo {environment}",
    )
    db.session.commit()
    return "", 204


@blueprint.get("/people/search")
@require_auth
def search_people():
    query = " ".join(str(request.args.get("q") or "").split())[:160]
    if len(query) < 2:
        return jsonify({"results": []})
    limit = min(max(request.args.get("limit", 8, type=int), 1), 20)
    escaped = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    conditions = [
        func.lower(Account.display_name).like(pattern, escape="\\"),
        func.lower(Account.role).like(pattern, escape="\\"),
        func.lower(func.coalesce(Account.orcid_id, "")).like(pattern, escape="\\"),
    ]
    if "@" in query:
        conditions.append(func.lower(Account.email).like(pattern, escape="\\"))
    statement = (
        select(Account)
        .where(
            Account.active.is_(True),
            Account.id != g.current_account.id,
            or_(*conditions),
        )
        .order_by(func.lower(Account.display_name), Account.id)
        .limit(limit)
    )
    results = []
    for account in db.session.scalars(statement):
        item = account.to_dict()
        item["email_match"] = account.email if query.casefold() == account.email.casefold() else None
        results.append(item)
    return jsonify({"results": results})


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
