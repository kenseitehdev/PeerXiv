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
    role = db.Column(db.String(160), nullable=False, default="Researcher")
    bio = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
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
        }
        if private:
            result.update({"email": self.email, "active": self.active})
        return result


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
