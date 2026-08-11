from datetime import UTC, datetime
from uuid import uuid4

from peerxiv.extensions import db


class DiscoveryProjection(db.Model):
    """Disposable feed/search projection, never canonical research state."""

    __tablename__ = "discovery_projections"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    paper_id = db.Column(db.String(36), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    topic = db.Column(db.String(120), nullable=False, index=True)
    searchable_text = db.Column(db.Text, nullable=False, default="")
    discussion_count = db.Column(db.Integer, nullable=False, default=0)
    citation_count = db.Column(db.Integer, nullable=False, default=0)
    refreshed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
