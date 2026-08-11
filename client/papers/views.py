import json
import re
from urllib.parse import urlsplit

from flask import current_app, g, jsonify, redirect, request, send_file

from accounts.auth import current_account, require_auth
from accounts.services import (
    notify_followers,
    notify_relevant_users,
    persist_match_notifications,
    record_activity,
    record_interests,
)

from discovery.notifications import match_notifications
from discovery.schemas import NotificationMatchInput, StoredPaperClassificationInput
from discovery.services import classify_paper, current_paper_metadata
from peerxiv.extensions import db, limiter
from peerxiv.malware import MalwareDetected, MalwareScannerUnavailable

from . import blueprint
from .manuscripts import InvalidManuscript, resolve_local_pdf, store_pdf
from .schemas import PaperCreate, PaperPublish
from .services import create_draft, get_paper, list_papers, publish_paper


def _multipart_list(name: str) -> list[str]:
    raw = request.form.get(name, "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = [value.strip() for value in raw.split(",")]
    if not isinstance(parsed, list):
        raise ValueError(f"{name}_must_be_an_array")
    return [str(value).strip() for value in parsed if str(value).strip()]


def _multipart_object(name: str) -> dict:
    raw = request.form.get(name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name}_must_be_json") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{name}_must_be_an_object")
    return parsed


def _publish_inputs() -> tuple[PaperPublish, StoredPaperClassificationInput]:
    if request.is_json:
        raw = request.get_json(silent=True) or {}
        return (
            PaperPublish.model_validate(raw),
            StoredPaperClassificationInput.model_validate(
                {
                    "keywords": raw.get("keywords", []),
                    "sections": raw.get("sections", []),
                    "metadata": raw.get("metadata", {}),
                }
            ),
        )
    authors = _multipart_list("authors")
    tags = _multipart_list("tags")
    sections_raw = request.form.get("sections", "[]")
    try:
        sections = json.loads(sections_raw)
    except json.JSONDecodeError as error:
        raise ValueError("sections_must_be_json") from error
    publish_payload = PaperPublish.model_validate(
        {
            "authors": authors,
            "tags": tags,
            "change_summary": request.form.get("change_summary", "Initial submission"),
        }
    )
    supplement = StoredPaperClassificationInput.model_validate(
        {
            "keywords": tags,
            "sections": sections,
            "metadata": _multipart_object("metadata"),
        }
    )
    return publish_payload, supplement


@blueprint.get("")
def index():
    include_drafts = request.args.get("include_drafts", "false").casefold() == "true"
    account = current_account()
    return jsonify(
        {
            "results": [
                {
                    **paper.to_dict(),
                    "versions": [version.to_dict() for version in paper.versions],
                }
                for paper in list_papers(
                    include_drafts=include_drafts,
                    user_id=account.id if account else None,
                )
            ]
        }
    )


@blueprint.post("")
@require_auth
def create():
    payload = PaperCreate.model_validate(request.get_json(silent=True) or {})
    paper = create_draft(payload, owner_id=g.current_account.id, commit=False)
    record_activity(
        g.current_account.id,
        verb="drafted",
        object_type="paper",
        object_id=paper.identifier,
        summary=f"{g.current_account.display_name} created a draft: {paper.title}",
    )
    db.session.commit()
    return jsonify(paper.to_dict()), 201


@blueprint.get("/<identifier>")
def detail(identifier: str):
    paper = get_paper(identifier)
    account = current_account()
    if paper is None or (
        paper.status == "draft" and (account is None or paper.owner_id != account.id)
    ):
        return jsonify({"error": {"code": "paper_not_found", "message": "Paper not found"}}), 404
    return jsonify({**paper.to_dict(), "versions": [version.to_dict() for version in paper.versions]})


@blueprint.post("/<identifier>/publish")
@require_auth
@limiter.limit("20 per hour")
def publish(identifier: str):
    paper = get_paper(identifier)
    if paper is None:
        return jsonify({"error": {"code": "paper_not_found", "message": "Paper not found"}}), 404
    try:
        payload, supplement = _publish_inputs()
    except ValueError as error:
        return jsonify(
            {"error": {"code": "invalid_publish_payload", "message": str(error)}}
        ), 400
    if paper.owner_id not in {None, g.current_account.id}:
        return jsonify(
            {"error": {"code": "paper_forbidden", "message": "You do not own this paper"}}
        ), 403
    paper.owner_id = g.current_account.id

    manuscript_path = None
    try:
        version = publish_paper(paper, payload, commit=False)
        upload = request.files.get("manuscript")
        if upload is not None and upload.filename:
            uri, checksum, manuscript_path = store_pdf(
                upload,
                version_id=version.id,
                storage_root=current_app.config["MANUSCRIPT_STORAGE_ROOT"],
                max_bytes=current_app.config["MAX_MANUSCRIPT_BYTES"],
                max_pages=current_app.config["MAX_MANUSCRIPT_PAGES"],
                clamav_host=current_app.config["CLAMAV_HOST"],
                clamav_port=current_app.config["CLAMAV_PORT"],
                clamav_timeout=current_app.config["CLAMAV_TIMEOUT"],
                scan_required=current_app.config["MALWARE_SCAN_REQUIRED"],
            )
            version.manuscript_uri = uri
            version.manuscript_checksum = checksum
        classified, reused = classify_paper(paper, supplement, commit=False)
    except MalwareDetected as error:
        db.session.rollback()
        if manuscript_path is not None:
            manuscript_path.unlink(missing_ok=True)
        return jsonify(
            {"error": {"code": "unsafe_manuscript", "message": str(error)}}
        ), 422
    except MalwareScannerUnavailable as error:
        db.session.rollback()
        if manuscript_path is not None:
            manuscript_path.unlink(missing_ok=True)
        return jsonify(
            {"error": {"code": "manuscript_scan_unavailable", "message": str(error)}}
        ), 503
    except InvalidManuscript as error:
        db.session.rollback()
        if manuscript_path is not None:
            manuscript_path.unlink(missing_ok=True)
        return jsonify(
            {"error": {"code": "invalid_manuscript", "message": str(error)}}
        ), 400
    except Exception:
        db.session.rollback()
        if manuscript_path is not None:
            manuscript_path.unlink(missing_ok=True)
        raise

    try:
        metadata = classified["metadata"]
        notifications = match_notifications(
            NotificationMatchInput(
                source_kind="research",
                source_id=paper.identifier,
                source_title=paper.title,
                tags=metadata["tags"],
                exclude_identifiers=[paper.identifier],
                exclude_authors=payload.authors,
            )
        )
        record_interests(g.current_account.id, metadata["tags"], source_kind="research")
        persist_match_notifications(g.current_account.id, notifications)
        record_activity(
            g.current_account.id,
            verb="published",
            object_type="paper",
            object_id=paper.identifier,
            summary=f"{g.current_account.display_name} published {paper.title}",
            payload={"category": metadata["primary_category"]},
        )
        notify_followers(
            g.current_account.id,
            kind="followed-researcher-published",
            text=f"{g.current_account.display_name} published {paper.title}",
            dedupe_suffix=f"paper:{paper.identifier}:v{version.number}",
            object_type="paper",
            object_id=paper.identifier,
            payload={"paper": paper.identifier},
        )
        notify_relevant_users(
            actor_id=g.current_account.id,
            paper_identifier=paper.identifier,
            paper_title=paper.title,
            tags=metadata["tags"],
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        if manuscript_path is not None:
            manuscript_path.unlink(missing_ok=True)
        raise
    return jsonify(
        {
            **version.to_dict(),
            "classification": classified["classification"],
            "metadata": metadata,
            "classification_reused": reused,
            "notifications": notifications,
        }
    ), 201


@blueprint.post("/<identifier>/classify")
@require_auth
def classify(identifier: str):
    paper = get_paper(identifier)
    if paper is None:
        return jsonify({"error": {"code": "paper_not_found", "message": "Paper not found"}}), 404
    if paper.owner_id not in {None, g.current_account.id}:
        return jsonify({"error": {"code": "paper_forbidden"}}), 403
    payload = StoredPaperClassificationInput.model_validate(request.get_json(silent=True) or {})
    try:
        result, reused = classify_paper(paper, payload)
    except ValueError as error:
        if str(error) == "paper_not_published":
            return jsonify(
                {
                    "error": {
                        "code": "paper_not_published",
                        "message": "Publish a paper version before classifying it",
                    }
                }
            ), 409
        raise
    return jsonify({**result, "reused": reused})


@blueprint.get("/<identifier>/metadata")
def metadata(identifier: str):
    paper = get_paper(identifier)
    if paper is None:
        return jsonify({"error": {"code": "paper_not_found", "message": "Paper not found"}}), 404
    record = current_paper_metadata(paper)
    if record is None:
        return jsonify(
            {
                "error": {
                    "code": "metadata_not_generated",
                    "message": "No CoU descriptive metadata exists for the current paper version",
                }
            }
        ), 404
    return jsonify(record.to_dict())


@blueprint.get("/<identifier>/pdf")
def pdf(identifier: str):
    paper = get_paper(identifier)
    if paper is None:
        return jsonify({"error": {"code": "paper_not_found", "message": "Paper not found"}}), 404
    if not paper.versions or not paper.versions[-1].manuscript_uri:
        return jsonify(
            {"error": {"code": "pdf_not_available", "message": "No PDF is attached"}}
        ), 404
    version = paper.versions[-1]
    uri = version.manuscript_uri
    local_path = resolve_local_pdf(uri, current_app.config["MANUSCRIPT_STORAGE_ROOT"])
    if local_path is not None:
        if not local_path.is_file():
            return jsonify(
                {"error": {"code": "pdf_missing", "message": "The manuscript file is missing"}}
            ), 404
        filename = re.sub(r"[^a-z0-9]+", "-", paper.title.casefold()).strip("-") or "paper"
        response = send_file(
            local_path,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=f"{filename}-v{version.number}.pdf",
            conditional=True,
        )
        response.headers["X-PeerXiv-Checksum"] = version.manuscript_checksum or ""
        return response
    parsed = urlsplit(uri)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        allowed_hosts = current_app.config["MANUSCRIPT_REDIRECT_HOSTS"] or ()
        if parsed.hostname in allowed_hosts:
            return redirect(uri, code=302)
    return jsonify(
        {
            "error": {
                "code": "pdf_storage_unresolved",
                "message": "The manuscript exists but its storage provider is not configured",
            }
        }
    ), 409
