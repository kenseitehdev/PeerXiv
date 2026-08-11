from datetime import UTC, datetime
from uuid import uuid4

from peerxiv.extensions import db


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    title = db.Column(db.String(240), nullable=False, default="Research conversation")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    participants = db.relationship(
        "ConversationParticipant",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="conversation",
    )
    messages = db.relationship(
        "Message",
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="conversation",
        order_by="Message.created_at",
    )

    def to_dict(self, *, viewer_id: str, include_messages: bool = False) -> dict[str, object]:
        viewer = next((item for item in self.participants if item.user_id == viewer_id), None)
        last_message = self.messages[-1] if self.messages else None
        unread_count = sum(
            1
            for message in self.messages
            if message.author_id != viewer_id
            and (viewer is None or viewer.last_read_at is None or message.created_at > viewer.last_read_at)
        )
        result: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "participants": [item.user.to_dict() for item in self.participants if item.user],
            "last_message": last_message.to_dict() if last_message else None,
            "unread_count": unread_count,
            "created_at": self.created_at.isoformat(),
        }
        if include_messages:
            result["messages"] = [message.to_dict() for message in self.messages]
        return result


class ConversationParticipant(db.Model):
    __tablename__ = "conversation_participants"
    __table_args__ = (db.UniqueConstraint("conversation_id", "user_id", name="uq_conversation_participant"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    last_read_at = db.Column(db.DateTime(timezone=True))
    joined_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    conversation = db.relationship("Conversation", back_populates="participants")
    user = db.relationship("Account", lazy="joined")


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    conversation_id = db.Column(db.String(36), db.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    conversation = db.relationship("Conversation", back_populates="messages")
    author = db.relationship("Account", lazy="joined")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "author_id": self.author_id,
            "author": self.author.to_dict() if self.author else {"id": self.author_id},
            "body": self.body,
            "created_at": self.created_at.isoformat(),
        }


class Discussion(db.Model):
    __tablename__ = "discussions"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    paper_id = db.Column(db.String(36), db.ForeignKey("papers.id", ondelete="CASCADE"), index=True)
    author_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    topic = db.Column(db.String(120), nullable=False, default="Research Practice", index=True)
    title = db.Column(db.String(500), nullable=False)
    body = db.Column(db.Text, nullable=False)
    score = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    author = db.relationship("Account", foreign_keys=[author_id], lazy="joined")
    paper = db.relationship("Paper", lazy="joined")
    comments = db.relationship(
        "Comment", cascade="all, delete-orphan", lazy="selectin", back_populates="discussion",
        order_by="Comment.created_at",
    )

    def to_dict(self, *, viewer_id: str | None = None, include_comments: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "paper": self.paper.identifier if self.paper else None,
            "author": self.author.to_dict() if self.author else {"id": self.author_id},
            "topic": self.topic,
            "title": self.title,
            "body": self.body,
            "score": self.score,
            "comment_count": len(self.comments),
            "following": any(item.user_id == viewer_id for item in self.followers) if viewer_id else False,
            "saved": any(item.user_id == viewer_id for item in self.saves) if viewer_id else False,
            "viewer_vote": next((item.value for item in self.votes if item.user_id == viewer_id), 0) if viewer_id else 0,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_comments:
            result["comments"] = [comment.to_dict() for comment in self.comments]
        return result


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    discussion_id = db.Column(db.String(36), db.ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = db.Column(db.String(36), db.ForeignKey("comments.id", ondelete="SET NULL"), index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    discussion = db.relationship("Discussion", back_populates="comments")
    author = db.relationship("Account", foreign_keys=[author_id], lazy="joined")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "discussion_id": self.discussion_id,
            "author": self.author.to_dict() if self.author else {"id": self.author_id},
            "parent_id": self.parent_id,
            "body": self.body,
            "created_at": self.created_at.isoformat(),
        }


class DiscussionFollow(db.Model):
    __tablename__ = "discussion_follows"
    __table_args__ = (db.UniqueConstraint("discussion_id", "user_id", name="uq_discussion_follow"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    discussion_id = db.Column(db.String(36), db.ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    discussion = db.relationship("Discussion", backref=db.backref("followers", cascade="all, delete-orphan", lazy="selectin"))


class DiscussionSave(db.Model):
    __tablename__ = "discussion_saves"
    __table_args__ = (db.UniqueConstraint("discussion_id", "user_id", name="uq_discussion_save"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    discussion_id = db.Column(db.String(36), db.ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    discussion = db.relationship("Discussion", backref=db.backref("saves", cascade="all, delete-orphan", lazy="selectin"))


class DiscussionVote(db.Model):
    __tablename__ = "discussion_votes"
    __table_args__ = (
        db.UniqueConstraint("discussion_id", "user_id", name="uq_discussion_vote"),
        db.CheckConstraint("value IN (-1, 1)", name="ck_discussion_vote_value"),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    discussion_id = db.Column(db.String(36), db.ForeignKey("discussions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    value = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    discussion = db.relationship("Discussion", backref=db.backref("votes", cascade="all, delete-orphan", lazy="selectin"))
