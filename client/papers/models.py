from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from peerxiv.extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


def new_identifier() -> str:
    now = datetime.now(UTC)
    return f"px:{now:%y%m}.{uuid4().hex[:5]}"


class Paper(db.Model):
    __tablename__ = "papers"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    owner_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id", ondelete="SET NULL"), index=True
    )
    identifier = db.Column(db.String(32), nullable=False, unique=True, index=True, default=new_identifier)
    title = db.Column(db.String(500), nullable=False)
    abstract = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(120), nullable=False, index=True)
    subfield = db.Column(db.String(120), nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    license = db.Column(db.String(64), nullable=False, default="CC BY 4.0")
    open_review = db.Column(db.Boolean, nullable=False, default=True)
    draft_authors = db.Column(db.JSON, nullable=False, default=list)
    draft_tags = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    versions = db.relationship(
        "PaperVersion",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperVersion.number",
        lazy="selectin",
    )
    owner = db.relationship("Account", lazy="joined")

    def to_dict(self) -> dict[str, object]:
        current = self.versions[-1] if self.versions else None
        return {
            "id": self.id,
            "owner": self.owner.to_dict() if self.owner else None,
            "identifier": self.identifier,
            "title": self.title,
            "abstract": self.abstract,
            "subject": self.subject,
            "subfield": self.subfield,
            "status": self.status,
            "license": self.license,
            "open_review": self.open_review,
            "authors": current.authors if current else self.draft_authors,
            "tags": current.tags if current else self.draft_tags,
            "current_version": current.number if current else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PaperVersion(db.Model):
    __tablename__ = "paper_versions"
    __table_args__ = (db.UniqueConstraint("paper_id", "number", name="uq_paper_version_number"),)

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    paper_id = db.Column(db.String(36), db.ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    abstract = db.Column(db.Text, nullable=False)
    authors = db.Column(db.JSON, nullable=False, default=list)
    tags = db.Column(db.JSON, nullable=False, default=list)
    manuscript_uri = db.Column(db.Text)
    manuscript_checksum = db.Column(db.String(128))
    change_summary = db.Column(db.Text, nullable=False, default="Initial submission")
    published_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    paper = db.relationship("Paper", back_populates="versions")
    metadata_record = db.relationship(
        "PaperMetadataRecord",
        back_populates="paper_version",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "number": self.number,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "tags": self.tags,
            "manuscript_uri": self.manuscript_uri,
            "manuscript_checksum": self.manuscript_checksum,
            "change_summary": self.change_summary,
            "published_at": self.published_at.isoformat(),
            "descriptive_metadata": self.metadata_record.to_dict() if self.metadata_record else None,
        }


class PaperMetadataRecord(db.Model):
    """Current queryable descriptive metadata projection for a paper version.

    CoU classification runs remain append-oriented.  This record is the current
    projection used by search and the UI and may be regenerated from a newer
    classifier run without mutating the immutable paper version.
    """

    __tablename__ = "paper_metadata_records"

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    paper_version_id = db.Column(
        db.String(36),
        db.ForeignKey("paper_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    classification_run_id = db.Column(
        db.String(36),
        db.ForeignKey("cou_classification_runs.id", ondelete="SET NULL"),
        index=True,
    )
    input_hash = db.Column(db.String(128), nullable=False)
    schema_version = db.Column(db.String(80), nullable=False)
    taxonomy_version = db.Column(db.String(80), nullable=False)
    classifier_version = db.Column(db.String(80), nullable=False)
    primary_category = db.Column(db.String(80), nullable=False, index=True)
    summary = db.Column(db.Text, nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    paper_version = db.relationship("PaperVersion", back_populates="metadata_record")
    tags = db.relationship(
        "PaperMetadataTag",
        back_populates="metadata_record",
        cascade="all, delete-orphan",
        order_by="PaperMetadataTag.ordinal",
        lazy="selectin",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "paper_version_id": self.paper_version_id,
            "classification_run_id": self.classification_run_id,
            "input_hash": self.input_hash,
            "schema_version": self.schema_version,
            "taxonomy_version": self.taxonomy_version,
            "classifier_version": self.classifier_version,
            "primary_category": self.primary_category,
            "summary": self.summary,
            "tags": [tag.to_dict() for tag in self.tags],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class PaperMetadataTag(db.Model):
    """Evidence-bearing, faceted tag produced by a classifier or an author."""

    __tablename__ = "paper_metadata_tags"
    __table_args__ = (
        db.UniqueConstraint(
            "metadata_record_id",
            "facet",
            "namespace",
            "slug",
            name="uq_paper_metadata_tag",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=new_id)
    metadata_record_id = db.Column(
        db.String(36),
        db.ForeignKey("paper_metadata_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    facet = db.Column(db.String(80), nullable=False, index=True)
    namespace = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(160), nullable=False, index=True)
    label = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=False)
    state = db.Column(db.String(32), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    evidence = db.Column(db.JSON, nullable=False, default=list)
    provenance = db.Column(db.String(80), nullable=False)
    ordinal = db.Column(db.Integer, nullable=False, default=0)

    metadata_record = db.relationship("PaperMetadataRecord", back_populates="tags")

    def to_dict(self) -> dict[str, object]:
        return {
            "facet": self.facet,
            "namespace": self.namespace,
            "slug": self.slug,
            "label": self.label,
            "description": self.description,
            "state": self.state,
            "weight": self.weight,
            "evidence": self.evidence,
            "provenance": self.provenance,
        }
