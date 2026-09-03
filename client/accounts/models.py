from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from werkzeug.security import check_password_hash, generate_password_hash

from peerxiv.extensions import db


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    email = db.Column(db.String(320), nullable=False, unique=True, index=True)
    display_name = db.Column(db.String(160), nullable=False, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    orcid_id = db.Column(db.String(19), unique=True, index=True)
    orcid_name = db.Column(db.String(160))
    orcid_linked_at = db.Column(db.DateTime(timezone=True), index=True)
    role = db.Column(db.String(160), nullable=False, default="Researcher")
    bio = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    zenodo_connections = db.relationship(
        "ZenodoConnection",
        back_populates="account",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self, *, private: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "display_name": self.display_name,
            "role": self.role,
            "bio": self.bio,
            "created_at": self.created_at.isoformat(),
            "orcid": (
                {
                    "id": self.orcid_id,
                    "name": self.orcid_name or self.display_name,
                    "url": f"https://orcid.org/{self.orcid_id}",
                    "verified_at": self.orcid_linked_at.isoformat()
                    if self.orcid_linked_at
                    else None,
                }
                if self.orcid_id
                else None
            ),
        }
        if private:
            result.update({"email": self.email, "active": self.active})
        return result


class ZenodoConnection(db.Model):
    """An encrypted, per-researcher Zenodo API connection.

    The API never serializes ``encrypted_token``.  A connection is scoped to
    one Zenodo environment because sandbox and production accounts are wholly
    separate.
    """

    __tablename__ = "zenodo_connections"
    __table_args__ = (
        db.UniqueConstraint("account_id", "environment", name="uq_zenodo_connection"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    account_id = db.Column(
        db.String(36),
        db.ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    environment = db.Column(db.String(24), nullable=False, index=True)
    encrypted_token = db.Column(db.Text, nullable=False)
    token_hint = db.Column(db.String(16), nullable=False)
    scopes = db.Column(db.JSON, nullable=False, default=list)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    account = db.relationship("Account", back_populates="zenodo_connections")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "connected",
            "environment": self.environment,
            "token_hint": self.token_hint,
            "scopes": self.scopes,
            "verified_at": self.verified_at.isoformat(),
        }


class RegistrationInvite(db.Model):
    __tablename__ = "registration_invites"
    __table_args__ = (
        db.CheckConstraint("max_uses > 0", name="ck_registration_invite_max_uses"),
        db.CheckConstraint("use_count >= 0", name="ck_registration_invite_use_count"),
        db.CheckConstraint(
            "use_count <= max_uses", name="ck_registration_invite_use_limit"
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    code_digest = db.Column(db.String(64), nullable=False, unique=True, index=True)
    label = db.Column(db.String(160), nullable=False, default="Alpha invitation")
    email = db.Column(db.String(320), index=True)
    max_uses = db.Column(db.Integer, nullable=False, default=1)
    use_count = db.Column(db.Integer, nullable=False, default=0)
    expires_at = db.Column(db.DateTime(timezone=True), index=True)
    revoked_at = db.Column(db.DateTime(timezone=True), index=True)
    last_used_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    def status(self, *, now: datetime | None = None) -> str:
        current = now or utc_now()
        expires_at = self._aware(self.expires_at)
        if self.revoked_at is not None:
            return "revoked"
        if expires_at is not None and expires_at <= current:
            return "expired"
        if self.use_count >= self.max_uses:
            return "used"
        return "active"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "email": self.email,
            "max_uses": self.max_uses,
            "use_count": self.use_count,
            "remaining_uses": max(self.max_uses - self.use_count, 0),
            "status": self.status(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat(),
        }


class UserFollow(db.Model):
    __tablename__ = "user_follows"
    __table_args__ = (
        db.UniqueConstraint("follower_id", "followed_id", name="uq_user_follow"),
        db.CheckConstraint("follower_id <> followed_id", name="ck_user_follow_not_self"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    follower_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    followed_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class UserInterest(db.Model):
    __tablename__ = "user_interests"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "facet", "namespace", "slug", name="uq_user_interest_tag"
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    user_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facet = db.Column(db.String(80), nullable=False, index=True)
    namespace = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(160), nullable=False, index=True)
    label = db.Column(db.String(240), nullable=False)
    weight = db.Column(db.Float, nullable=False, default=0.0)
    observations = db.Column(db.Integer, nullable=False, default=1)
    source_kinds = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Activity(db.Model):
    __tablename__ = "activities"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    actor_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verb = db.Column(db.String(80), nullable=False, index=True)
    object_type = db.Column(db.String(80), nullable=False, index=True)
    object_id = db.Column(db.String(120), nullable=False, index=True)
    summary = db.Column(db.String(500), nullable=False)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    actor = db.relationship("Account", lazy="joined")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "actor": self.actor.to_dict(),
            "verb": self.verb,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }


class Notification(db.Model):
    __tablename__ = "notifications"
    __table_args__ = (
        db.UniqueConstraint("user_id", "dedupe_key", name="uq_user_notification_dedupe"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    user_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True
    )
    kind = db.Column(db.String(80), nullable=False, index=True)
    text = db.Column(db.String(500), nullable=False)
    reason = db.Column(db.Text)
    object_type = db.Column(db.String(80))
    object_id = db.Column(db.String(120), index=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)
    dedupe_key = db.Column(db.String(320), nullable=False)
    read_at = db.Column(db.DateTime(timezone=True), index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "reason": self.reason,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "payload": self.payload,
            "read": self.read_at is not None,
            "created_at": self.created_at.isoformat(),
        }
