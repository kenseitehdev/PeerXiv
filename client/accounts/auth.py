from __future__ import annotations

import hmac
import secrets
from functools import wraps

from flask import g, jsonify, request, session

from peerxiv.extensions import db

from .models import Account


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def establish_session(account: Account) -> str:
    csrf_token = secrets.token_urlsafe(32)
    session.clear()
    session["user_id"] = account.id
    session["csrf_token"] = csrf_token
    session.permanent = True
    return csrf_token


def current_account() -> Account | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    account = db.session.get(Account, user_id)
    if account is None or not account.active:
        session.clear()
        return None
    return account


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        account = current_account()
        if account is None:
            return jsonify(
                {"error": {"code": "authentication_required", "message": "Sign in required"}}
            ), 401
        if request.method not in SAFE_METHODS:
            expected = str(session.get("csrf_token", ""))
            supplied = request.headers.get("X-CSRF-Token", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                return jsonify(
                    {"error": {"code": "csrf_failed", "message": "Invalid CSRF token"}}
                ), 403
        g.current_account = account
        return view(*args, **kwargs)

    return wrapped
