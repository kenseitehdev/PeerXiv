from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import or_, update

from peerxiv.extensions import db

from .models import RegistrationInvite, utc_now


def invitation_digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_invitation(
    *,
    label: str,
    email: str | None,
    max_uses: int,
    expires_at: datetime | None,
) -> tuple[RegistrationInvite, str]:
    code = f"pxi_{secrets.token_urlsafe(24)}"
    invitation = RegistrationInvite(
        code_digest=invitation_digest(code),
        label=label,
        email=email,
        max_uses=max_uses,
        expires_at=expires_at,
    )
    db.session.add(invitation)
    db.session.commit()
    return invitation, code


def consume_invitation(code: str, *, email: str, now: datetime | None = None) -> bool:
    current = now or utc_now()
    invitation_id = db.session.scalar(
        update(RegistrationInvite)
        .where(
            RegistrationInvite.code_digest == invitation_digest(code),
            RegistrationInvite.revoked_at.is_(None),
            or_(
                RegistrationInvite.expires_at.is_(None),
                RegistrationInvite.expires_at > current,
            ),
            RegistrationInvite.use_count < RegistrationInvite.max_uses,
            or_(RegistrationInvite.email.is_(None), RegistrationInvite.email == email),
        )
        .values(
            use_count=RegistrationInvite.use_count + 1,
            last_used_at=current,
        )
        .returning(RegistrationInvite.id)
    )
    return invitation_id is not None
