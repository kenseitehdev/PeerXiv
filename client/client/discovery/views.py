from flask import g, jsonify, request
from sqlalchemy import select

from accounts.auth import require_auth
from accounts.services import persist_match_notifications, record_interests
from papers.models import Paper
from peerxiv.classifier import classifier
from peerxiv.extensions import db, limiter

from . import blueprint
from .notifications import classify_and_match_notifications, match_notifications
from .schemas import (
    NotificationClassificationInput,
    NotificationMatchInput,
    PaperClassificationInput,
)
from .services import classify_candidate


@blueprint.get("/feed")
def feed():
    papers = db.session.scalars(
        select(Paper).where(Paper.status == "published").order_by(Paper.created_at.desc()).limit(50)
    )
    return jsonify({"results": [paper.to_dict() for paper in papers], "order": "recent"})


@blueprint.get("/classifier")
def classifier_status():
    return jsonify({"kind": "cou", **classifier.status()})


@blueprint.post("/classify")
@limiter.limit("20 per hour")
def classify_document():
    document = PaperClassificationInput.model_validate(request.get_json(silent=True) or {})
    result = classify_candidate(document)
    return jsonify(result.to_dict())


@blueprint.post("/notifications/matches")
@require_auth
def notification_matches():
    payload = NotificationMatchInput.model_validate(request.get_json(silent=True) or {})
    results = match_notifications(payload)
    record_interests(g.current_account.id, payload.tags, source_kind=payload.source_kind)
    persist_match_notifications(g.current_account.id, results)
    db.session.commit()
    return jsonify({"results": results})


@blueprint.post("/notifications/classify")
@require_auth
@limiter.limit("60 per hour")
def classify_notification_source():
    payload = NotificationClassificationInput.model_validate(request.get_json(silent=True) or {})
    result = classify_and_match_notifications(payload)
    metadata = result["source_classification"]["metadata"]
    record_interests(g.current_account.id, metadata["tags"], source_kind=payload.source_kind)
    persist_match_notifications(g.current_account.id, result["notifications"])
    db.session.commit()
    return jsonify(result)
