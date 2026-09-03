from sqlalchemy import or_, select

from peerxiv.extensions import db

from .models import Paper, PaperVersion
from .schemas import PaperCreate, PaperPublish


def list_papers(*, include_drafts: bool = False, user_id: str | None = None) -> list[Paper]:
    statement = select(Paper).order_by(Paper.created_at.desc())
    if include_drafts and user_id:
        statement = statement.where(or_(Paper.status == "published", Paper.owner_id == user_id))
    else:
        statement = statement.where(Paper.status == "published")
    return list(db.session.scalars(statement))


def get_paper(identifier: str) -> Paper | None:
    return db.session.scalar(select(Paper).where(Paper.identifier == identifier))


def create_draft(
    data: PaperCreate,
    *,
    owner_id: str | None = None,
    commit: bool = True,
) -> Paper:
    paper = Paper(
        owner_id=owner_id,
        title=data.title,
        abstract=data.abstract,
        subject=data.subject,
        subfield=data.subfield,
        license=data.license,
        open_review=data.open_review,
        status="draft",
    )
    # Draft authors and tags are retained without pretending a published
    # version exists. They become immutable version data at publication.
    paper.draft_authors = data.authors
    paper.draft_tags = data.tags
    db.session.add(paper)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return paper


def publish_paper(paper: Paper, data: PaperPublish, *, commit: bool = True) -> PaperVersion:
    version = PaperVersion(
        paper=paper,
        number=len(paper.versions) + 1,
        title=paper.title,
        abstract=paper.abstract,
        authors=data.authors,
        tags=data.tags,
        manuscript_uri=data.manuscript_uri,
        manuscript_checksum=data.manuscript_checksum,
        change_summary=data.change_summary,
    )
    paper.status = "published"
    db.session.add(version)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return version
