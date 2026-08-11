from datetime import UTC, datetime
from uuid import uuid4

from peerxiv.extensions import db


class Journal(db.Model):
    __tablename__ = "journals"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    name = db.Column(db.String(300), nullable=False, unique=True, index=True)
    issn = db.Column(db.String(32), unique=True)
    homepage_url = db.Column(db.Text)
    open_access = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class PublicationLink(db.Model):
    __tablename__ = "publication_links"
    __table_args__ = (db.UniqueConstraint("paper_version_id", "doi", name="uq_version_publication_doi"),)

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    paper_version_id = db.Column(db.String(36), db.ForeignKey("paper_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    journal_id = db.Column(db.String(36), db.ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False, index=True)
    doi = db.Column(db.String(255), nullable=False, index=True)
    status = db.Column(db.String(40), nullable=False, default="linked")
    verified_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
