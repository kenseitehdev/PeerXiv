from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import uuid4

from sqlalchemy import select

from papers.models import Paper, PaperMetadataRecord, PaperMetadataTag
from peerxiv.classifier import CoUClassification, CoUClassificationRun, CoUSnapshot, classifier
from peerxiv.extensions import db

from .schemas import PaperClassificationInput, StoredPaperClassificationInput


def canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha256(encoded).hexdigest()


def build_snapshot(
    document: PaperClassificationInput,
    *,
    subject_type: str,
    subject_id: str,
    subject_version: str,
) -> CoUSnapshot:
    payload = document.model_dump(mode="json")
    evidence = []
    if payload["title"]:
        evidence.append({"kind": "title", "position": 0, "source": "paper"})
    if payload["keywords"]:
        evidence.append({"kind": "keywords", "position": 1, "source": "author"})
    if payload["abstract"]:
        evidence.append({"kind": "abstract", "position": 2, "source": "paper"})
    evidence.extend(
        {
            "kind": "section",
            "position": position,
            "heading": section["heading"],
            "source": "paper",
        }
        for position, section in enumerate(payload["sections"], start=3)
    )
    return CoUSnapshot(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_version=subject_version,
        state={"document": payload},
        evidence=tuple(evidence),
        validation=(
            {"rule": "structural-validity-isolation", "status": "requested"},
            {"rule": "rolling-predictive-validation", "status": "requested"},
        ),
        movement=({"measure": "delta-mu", "status": "computed-per-observation"},),
        dependency=({"kind": "taxonomy", "version": "resolved-by-classifier"},),
        context={
            "purpose": "paper-review-and-categorization",
            "metadata": payload["metadata"],
        },
    )


def classify_candidate(document: PaperClassificationInput) -> CoUClassification:
    payload = document.model_dump(mode="json")
    input_hash = canonical_hash(payload)
    snapshot = build_snapshot(
        document,
        subject_type="paper_candidate",
        subject_id=f"candidate:{input_hash[:16]}",
        subject_version=input_hash,
    )
    return classifier.classify(snapshot)


def classify_paper(
    paper: Paper,
    supplement: StoredPaperClassificationInput,
    *,
    commit: bool = True,
) -> tuple[dict[str, object], bool]:
    if not paper.versions:
        raise ValueError("paper_not_published")
    version = paper.versions[-1]
    keywords = list(dict.fromkeys([*version.tags, *supplement.keywords]))
    document = PaperClassificationInput(
        title=version.title,
        abstract=version.abstract,
        authors=version.authors,
        keywords=keywords,
        sections=supplement.sections,
        metadata={
            **supplement.metadata,
            "peerxiv_identifier": paper.identifier,
            "paper_version": version.number,
            "manuscript_uri": version.manuscript_uri,
            "manuscript_checksum": version.manuscript_checksum,
        },
    )
    snapshot = build_snapshot(
        document,
        subject_type="paper_version",
        subject_id=version.id,
        subject_version=f"v{version.number}",
    )
    input_hash = canonical_hash(snapshot.to_dict()["state"])

    current = version.metadata_record
    if (
        current is not None
        and current.input_hash == input_hash
        and current.classifier_version == classifier.version
        and current.classification_run_id
    ):
        run = db.session.get(CoUClassificationRun, current.classification_run_id)
        if run is not None:
            return {"classification": run.to_dict(), "metadata": current.to_dict()}, True

    result = classifier.classify(snapshot)
    completed_at = result.classified_at
    run = CoUClassificationRun(
        id=result.run_id,
        subject_type=result.subject_type,
        subject_id=result.subject_id,
        subject_version=result.subject_version,
        classifier_version=result.classifier_version,
        input_hash=input_hash,
        status="completed",
        snapshot=snapshot.to_dict(),
        label=result.label,
        components=dict(result.components),
        trace=list(result.trace),
        requested_at=completed_at,
        completed_at=completed_at,
    )
    db.session.add(run)
    # The metadata record references this run by identifier rather than by an
    # ORM relationship. Flush explicitly so databases with enforced foreign
    # keys cannot schedule the metadata update ahead of the run insert.
    db.session.flush()

    metadata = dict(result.components["descriptive_metadata"])
    if current is None:
        current = PaperMetadataRecord(paper_version=version)
        db.session.add(current)
    else:
        current.tags.clear()
    current.classification_run_id = result.run_id
    current.input_hash = input_hash
    current.schema_version = str(metadata["schema_version"])
    current.taxonomy_version = str(metadata["taxonomy_version"])
    current.classifier_version = result.classifier_version
    current.primary_category = result.label
    current.summary = str(metadata["summary"])
    current.payload = metadata
    current.updated_at = datetime.now(UTC)
    primary_subject = metadata["primary_subject"]
    paper.subject = str(primary_subject["label"])
    paper.subfield = str(primary_subject["code"])
    db.session.flush()

    for ordinal, tag in enumerate(metadata["tags"]):
        current.tags.append(
            PaperMetadataTag(
                id=str(uuid4()),
                facet=str(tag["facet"]),
                namespace=str(tag["namespace"]),
                slug=str(tag["slug"])[:160],
                label=str(tag["label"])[:240],
                description=str(tag["description"]),
                state=str(tag["state"]),
                weight=float(tag["weight"]),
                evidence=list(tag["evidence"]),
                provenance=str(tag["provenance"]),
                ordinal=ordinal,
            )
        )
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return {"classification": result.to_dict(), "metadata": current.to_dict()}, False


def current_paper_metadata(paper: Paper) -> PaperMetadataRecord | None:
    if not paper.versions:
        return None
    version = paper.versions[-1]
    return db.session.scalar(
        select(PaperMetadataRecord).where(PaperMetadataRecord.paper_version_id == version.id)
    )
