"""Classification-driven notification matching.

This module returns notification projections.  Durable per-user delivery waits
for Accounts; callers must provide explicit interest signals and exclusions.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from papers.models import PaperMetadataRecord
from peerxiv.extensions import db

from .schemas import (
    NotificationClassificationInput,
    NotificationMatchInput,
    PaperClassificationInput,
)
from .services import classify_candidate


FACET_WEIGHT = {
    "concept": 1.00,
    "method": 0.92,
    "subject": 0.68,
    "contribution": 0.52,
    "evidence": 0.44,
    "paper-type": 0.36,
    "artifact": 0.30,
}
EXACT_SUBTOPIC_FACETS = {"concept", "method"}


def match_notifications(payload: NotificationMatchInput) -> list[dict[str, Any]]:
    interest = {
        (tag.namespace.casefold(), tag.slug.casefold()): tag
        for tag in payload.tags
    }
    excluded_identifiers = {value.casefold() for value in payload.exclude_identifiers}
    excluded_authors = {value.casefold() for value in payload.exclude_authors}
    denominator = sum(
        FACET_WEIGHT.get(tag.facet, 0.25) * tag.weight
        for tag in interest.values()
    ) or 1.0

    records = db.session.scalars(select(PaperMetadataRecord)).all()
    matches: list[dict[str, Any]] = []
    seen_papers: set[str] = set()
    for record in records:
        version = record.paper_version
        paper = version.paper
        if paper.identifier.casefold() in excluded_identifiers or paper.identifier in seen_papers:
            continue
        if paper.versions[-1].id != version.id:
            continue
        candidate_authors = {author.casefold() for author in version.authors}
        if excluded_authors & candidate_authors:
            continue

        overlap = []
        numerator = 0.0
        exact_subtopics = []
        for tag in record.tags:
            key = (tag.namespace.casefold(), tag.slug.casefold())
            source = interest.get(key)
            if source is None:
                continue
            strength = FACET_WEIGHT.get(tag.facet, 0.25) * min(float(tag.weight), source.weight)
            numerator += strength
            matched = {
                "facet": tag.facet,
                "namespace": tag.namespace,
                "slug": tag.slug,
                "label": tag.label,
                "strength": round(strength, 6),
            }
            overlap.append(matched)
            if tag.facet in EXACT_SUBTOPIC_FACETS:
                exact_subtopics.append(matched)

        score = min(1.0, numerator / denominator)
        if not exact_subtopics and not (len(overlap) >= 2 and score >= 0.18):
            continue
        overlap.sort(key=lambda item: item["strength"], reverse=True)
        exact_subtopics.sort(key=lambda item: item["strength"], reverse=True)
        labels = [item["label"] for item in (exact_subtopics or overlap)[:4]]
        match_kind = {
            "research": "similar-paper",
            "comment": "comment-research-match",
            "discussion": "discussion-research-match",
        }[payload.source_kind]
        prefix = {
            "research": "Research matching your work",
            "comment": "Research matching your comment",
            "discussion": "Research matching your discussion",
        }[payload.source_kind]
        matches.append(
            {
                "kind": match_kind,
                "paper": paper.identifier,
                "paper_version": version.number,
                "title": version.title,
                "authors": version.authors,
                "text": f"{prefix}: {version.title}",
                "reason": f"Exact overlap: {', '.join(labels)}",
                "score": round(score, 6),
                "matched_tags": overlap,
                "source": {
                    "kind": payload.source_kind,
                    "id": payload.source_id,
                    "title": payload.source_title,
                },
            }
        )
        seen_papers.add(paper.identifier)

    matches.sort(key=lambda item: (-item["score"], item["title"]))
    return matches[: payload.limit]


def classify_and_match_notifications(
    payload: NotificationClassificationInput,
) -> dict[str, Any]:
    document = PaperClassificationInput(
        title=payload.title,
        abstract=payload.text,
        keywords=payload.keywords,
        metadata={
            "source_kind": payload.source_kind,
            "source_id": payload.source_id,
        },
    )
    classification = classify_candidate(document)
    metadata = dict(classification.components["descriptive_metadata"])
    tags = [
        {
            "facet": tag["facet"],
            "namespace": tag["namespace"],
            "slug": tag["slug"],
            "label": tag["label"],
            "weight": tag["weight"],
        }
        for tag in metadata["tags"]
    ]
    match_payload = NotificationMatchInput(
        source_kind=payload.source_kind,
        source_id=payload.source_id,
        source_title=payload.title,
        tags=tags,
        exclude_identifiers=payload.exclude_identifiers,
        exclude_authors=payload.exclude_authors,
        limit=payload.limit,
    )
    return {
        "source_classification": {
            "label": classification.label,
            "classifier_version": classification.classifier_version,
            "metadata": metadata,
        },
        "notifications": match_notifications(match_payload),
    }
