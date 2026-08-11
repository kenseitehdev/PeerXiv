from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from peerxiv.extensions import db


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class ResearchSpace(db.Model):
    __tablename__ = "research_spaces"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    owner_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind = db.Column(db.String(40), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    visibility = db.Column(db.String(24), nullable=False, default="public", index=True)
    status = db.Column(db.String(40), nullable=False, default="active")
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    owner = db.relationship("Account", lazy="joined")
    members = db.relationship(
        "SpaceMember", cascade="all, delete-orphan", lazy="selectin", back_populates="space"
    )
    paper_links = db.relationship(
        "SpacePaper", cascade="all, delete-orphan", lazy="selectin", back_populates="space"
    )
    resources = db.relationship(
        "SpaceResource", cascade="all, delete-orphan", lazy="selectin", back_populates="space"
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "visibility": self.visibility,
            "status": self.status,
            "details": self.details,
            "owner": self.owner.to_dict(),
            "members": [member.to_dict() for member in self.members],
            "papers": [link.to_dict() for link in self.paper_links],
            "resources": [resource.to_dict() for resource in self.resources],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class SpaceMember(db.Model):
    __tablename__ = "space_members"
    __table_args__ = (
        db.UniqueConstraint("space_id", "user_id", name="uq_space_member"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    space_id = db.Column(
        db.String(36), db.ForeignKey("research_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = db.Column(db.String(40), nullable=False, default="collaborator")
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    space = db.relationship("ResearchSpace", back_populates="members")
    user = db.relationship("Account", lazy="joined")

    def to_dict(self) -> dict[str, object]:
        return {"user": self.user.to_dict(), "role": self.role, "joined_at": self.joined_at.isoformat()}


class SpacePaper(db.Model):
    __tablename__ = "space_papers"
    __table_args__ = (
        db.UniqueConstraint("space_id", "paper_id", name="uq_space_paper"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    space_id = db.Column(
        db.String(36), db.ForeignKey("research_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    paper_id = db.Column(
        db.String(36), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relationship = db.Column(db.String(80), nullable=False, default="linked")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    space = db.relationship("ResearchSpace", back_populates="paper_links")
    paper = db.relationship("Paper", lazy="joined")

    def to_dict(self) -> dict[str, object]:
        return {"paper": self.paper.to_dict(), "relationship": self.relationship}


class SpaceResource(db.Model):
    __tablename__ = "space_resources"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    space_id = db.Column(
        db.String(36), db.ForeignKey("research_spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_type = db.Column(db.String(60), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    url = db.Column(db.Text)
    details = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    space = db.relationship("ResearchSpace", back_populates="resources")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "resource_type": self.resource_type,
            "title": self.title,
            "url": self.url,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
        }
