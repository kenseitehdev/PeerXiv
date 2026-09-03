import os
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory
from redis import Redis
from sqlalchemy import text
from sqlalchemy import select

from .classifier import classifier
from .extensions import db
from .malware import check_clamd

blueprint = Blueprint("server", __name__)


@blueprint.get("/")
def frontend():
    return send_from_directory(current_app.template_folder, "index.html")


@blueprint.get("/papers/<identifier>/versions/<int:number>")
def paper_landing(identifier: str, number: int):
    """Server-rendered, version-specific scholarly landing page."""

    from papers.models import Paper, PaperVersion

    version = db.session.scalar(
        select(PaperVersion)
        .join(Paper, Paper.id == PaperVersion.paper_id)
        .where(Paper.identifier == identifier, PaperVersion.number == number)
    )
    if version is None or version.paper.status != "published":
        return render_template("record_not_found.html"), 404
    doi_record = version.doi_record
    registered_doi = (
        doi_record.doi
        if doi_record is not None and doi_record.state == "published"
        else None
    )
    return render_template(
        "paper_record.html",
        paper=version.paper,
        version=version,
        doi_record=doi_record,
        registered_doi=registered_doi,
        json_ld={
            "@context": "https://schema.org",
            "@type": "ScholarlyArticle",
            "name": version.title,
            "headline": version.title,
            "abstract": version.abstract,
            "author": [
                {"@type": "Person", "name": author} for author in version.authors
            ],
            "datePublished": version.published_at.date().isoformat(),
            "version": f"v{version.number}",
            "license": version.paper.license,
            "identifier": registered_doi or version.paper.identifier,
            "url": request.url,
        },
    )


@blueprint.get("/api/v1/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": current_app.config["APP_NAME"],
            "api_version": current_app.config["API_VERSION"],
        }
    )


@blueprint.get("/api/v1/ready")
def ready():
    dependencies = {
        "database": "ready",
        "redis": "disabled",
        "manuscripts": "ready",
        "malware_scanner": "disabled",
    }
    try:
        db.session.execute(text("SELECT 1"))
        storage_root = Path(current_app.config["MANUSCRIPT_STORAGE_ROOT"])
        storage_root.mkdir(parents=True, exist_ok=True)
        if not os.access(storage_root, os.W_OK):
            raise OSError("Manuscript storage is not writable")
        redis_url = current_app.config["REDIS_URL"]
        if redis_url:
            Redis.from_url(
                redis_url,
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            ).ping()
            dependencies["redis"] = "ready"
        clamav_host = current_app.config["CLAMAV_HOST"]
        if clamav_host:
            check_clamd(
                clamav_host,
                port=current_app.config["CLAMAV_PORT"],
                timeout=min(current_app.config["CLAMAV_TIMEOUT"], 5.0),
            )
            dependencies["malware_scanner"] = "ready"
    except Exception as error:
        current_app.logger.error("Readiness check failed", exc_info=error)
        return jsonify(
            {
                "ok": False,
                "service": current_app.config["APP_NAME"],
                "dependencies": dependencies,
            }
        ), 503
    return jsonify(
        {
            "ok": True,
            "service": current_app.config["APP_NAME"],
            "database": dependencies["database"],
            "dependencies": dependencies,
            "classifier": classifier.status(),
        }
    )


@blueprint.get("/api/v1/bootstrap")
def bootstrap():
    return jsonify(
        {
            "service": current_app.config["APP_NAME"],
            "api_version": current_app.config["API_VERSION"],
            "registration_mode": current_app.config["REGISTRATION_MODE"],
            "orcid": {
                "enabled": current_app.config["ORCID_ENABLED"],
                "environment": current_app.config["ORCID_ENVIRONMENT"],
            },
            "zenodo": {
                "enabled": current_app.config["ZENODO_ENABLED"],
                "environment": current_app.config["ZENODO_ENVIRONMENT"],
                "production_publish_enabled": current_app.config[
                    "ZENODO_ALLOW_PRODUCTION_PUBLISH"
                ],
            },
            "modules": ["accounts", "papers", "social", "discovery", "journals", "spaces"],
            "realtime": {"transport": "socket.io", "namespace": "/social"},
            "classifier": {"kind": "cou", **classifier.status()},
        }
    )
