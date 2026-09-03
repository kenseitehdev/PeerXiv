"""DOI metadata and Zenodo deposit workflow for immutable paper versions."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from html import escape
import json
import re
from typing import Any

from flask import current_app
from sqlalchemy import select

from accounts.models import Account, ZenodoConnection
from accounts.zenodo import ZenodoApiError, ZenodoClient
from peerxiv.credentials import CredentialError, decrypt_credential
from peerxiv.extensions import db

from .manuscripts import resolve_local_pdf
from .models import Paper, PaperDoiRecord, PaperVersion, utc_now


DOI_PATTERN = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)


class DoiWorkflowError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _metadata_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def _license_id(label: str) -> str:
    normalized = " ".join(label.casefold().replace("-", " ").split())
    return {
        "cc by 4.0": "cc-by-4.0",
        "cc by sa 4.0": "cc-by-sa-4.0",
        "cc0 1.0": "cc-zero",
    }.get(normalized, "cc-by-4.0")


def _creator(author: str, owner: Account | None) -> dict[str, Any]:
    normalized = " ".join(author.split())
    if "," in normalized:
        family_name, given_name = (part.strip() for part in normalized.split(",", 1))
    else:
        parts = normalized.rsplit(" ", 1)
        given_name, family_name = parts if len(parts) == 2 else ("", parts[0])
    person: dict[str, Any] = {
        "type": "personal",
        "given_name": given_name,
        "family_name": family_name,
        "name": f"{family_name}, {given_name}".rstrip(", "),
    }
    if (
        owner is not None
        and owner.orcid_id
        and normalized.casefold() == owner.display_name.strip().casefold()
    ):
        person["identifiers"] = [{"scheme": "orcid", "identifier": owner.orcid_id}]
    return {"person_or_org": person}


def build_zenodo_metadata(
    paper: Paper,
    version: PaperVersion,
    *,
    landing_url: str,
) -> dict[str, Any]:
    abstract = escape(version.abstract).replace("\n", "<br>")
    published_at = version.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    classified_keywords = (
        [tag.label for tag in version.metadata_record.tags]
        if version.metadata_record is not None
        else []
    )
    keywords = list(dict.fromkeys([*version.tags, *classified_keywords]))[:32]
    return {
        "metadata": {
            "resource_type": {"id": "publication-preprint"},
            "publication_date": published_at.astimezone(UTC).date().isoformat(),
            "title": version.title,
            "description": (
                f"<p>{abstract}</p>"
                f"<p>PeerXiv record: <a href=\"{escape(landing_url, quote=True)}\">"
                f"{escape(paper.identifier)}</a></p>"
            ),
            "creators": [_creator(author, paper.owner) for author in version.authors],
            "publisher": "PeerXiv",
            "rights": [{"id": _license_id(paper.license)}],
            "subjects": [{"subject": keyword} for keyword in keywords],
            "version": f"v{version.number}",
            "languages": [{"id": "eng"}],
        },
        "access": {"record": "public", "files": "public"},
        "files": {"enabled": True},
    }


def prepare_doi_record(
    paper: Paper,
    *,
    actor_id: str,
    landing_url: str,
) -> PaperDoiRecord:
    if paper.status != "published" or not paper.versions:
        raise DoiWorkflowError(
            "paper_not_published", "Publish an immutable paper version before preparing a DOI"
        )
    version = paper.versions[-1]
    if not version.manuscript_uri or not version.manuscript_checksum:
        raise DoiWorkflowError(
            "manuscript_required", "A stored manuscript PDF is required before preparing a DOI"
        )
    metadata = build_zenodo_metadata(paper, version, landing_url=landing_url)
    digest = _metadata_hash(metadata)
    record = version.doi_record
    if record is not None:
        if record.metadata_hash != digest and record.state not in {"metadata_ready", "error"}:
            raise DoiWorkflowError(
                "doi_metadata_locked",
                "DOI metadata cannot change after a provider DOI has been reserved",
                status=409,
            )
        if record.state in {"metadata_ready", "error"} and not record.provider_record_id:
            record.metadata_payload = metadata
            record.metadata_hash = digest
            record.landing_url = landing_url
            record.manuscript_checksum = version.manuscript_checksum
            record.last_error = None
            record.state = "metadata_ready"
            db.session.commit()
        return record
    record = PaperDoiRecord(
        paper_version=version,
        created_by_id=actor_id,
        provider="zenodo",
        environment=current_app.config["ZENODO_ENVIRONMENT"],
        state="metadata_ready",
        landing_url=landing_url,
        metadata_hash=digest,
        metadata_payload=metadata,
        manuscript_checksum=version.manuscript_checksum,
        provider_payload={},
    )
    db.session.add(record)
    db.session.commit()
    return record


def _connection(account_id: str, environment: str) -> ZenodoConnection:
    connection = db.session.scalar(
        select(ZenodoConnection).where(
            ZenodoConnection.account_id == account_id,
            ZenodoConnection.environment == environment,
        )
    )
    if connection is None:
        raise DoiWorkflowError(
            "zenodo_not_connected",
            f"Connect a Zenodo {environment} account before reserving a DOI",
            status=409,
        )
    return connection


def _client(connection: ZenodoConnection):
    try:
        token = decrypt_credential(
            connection.encrypted_token,
            current_app.config["CREDENTIAL_ENCRYPTION_KEY"],
        )
    except CredentialError as error:
        raise DoiWorkflowError(
            "zenodo_credential_unavailable",
            "Reconnect Zenodo before continuing",
            status=409,
        ) from error
    factory = current_app.config.get("ZENODO_CLIENT_FACTORY") or ZenodoClient
    return factory(
        base_url=current_app.config["ZENODO_BASE_URL"],
        token=token,
        timeout=current_app.config["ZENODO_TIMEOUT"],
    )


def _safe_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    reserved = (
        metadata.get("prereserve_doi")
        if isinstance(metadata.get("prereserve_doi"), dict)
        else {}
    )
    pids = payload.get("pids") if isinstance(payload.get("pids"), dict) else {}
    doi_pid = pids.get("doi") if isinstance(pids.get("doi"), dict) else {}
    parent = payload.get("parent") if isinstance(payload.get("parent"), dict) else {}
    parent_pids = parent.get("pids") if isinstance(parent.get("pids"), dict) else {}
    concept_pid = (
        parent_pids.get("doi") if isinstance(parent_pids.get("doi"), dict) else {}
    )
    links = payload.get("links") if isinstance(payload.get("links"), dict) else {}
    records_api = bool(
        "is_draft" in payload
        or "pids" in payload
        or links.get("reserve_doi")
        or links.get("self_html")
    )
    return {
        "api": "records" if records_api else "legacy",
        "id": str(payload.get("id") or ""),
        "record_id": str(payload.get("record_id") or ""),
        "doi": str(
            payload.get("doi") or doi_pid.get("identifier") or reserved.get("doi") or ""
        ),
        "doi_provider": str(doi_pid.get("provider") or ""),
        "conceptdoi": str(
            payload.get("conceptdoi")
            or concept_pid.get("identifier")
            or metadata.get("conceptdoi")
            or ""
        ),
        "html": str(
            links.get("self_html")
            or links.get("record_html")
            or links.get("html")
            or payload.get("record_url")
            or ""
        ),
        "state": str(payload.get("status") or payload.get("state") or ""),
        "submitted": bool(payload.get("is_published") or payload.get("submitted")),
    }


def _managed_doi(payload: dict[str, Any]) -> str | None:
    pids = payload.get("pids") if isinstance(payload.get("pids"), dict) else {}
    doi_pid = pids.get("doi") if isinstance(pids.get("doi"), dict) else None
    if doi_pid is None:
        return None
    provider = str(doi_pid.get("provider") or "").casefold()
    identifier = str(doi_pid.get("identifier") or "")
    if provider == "external":
        raise ZenodoApiError("Zenodo marked this draft as having an external DOI")
    if provider != "datacite" or not DOI_PATTERN.fullmatch(identifier):
        raise ZenodoApiError("Zenodo did not return a valid managed DOI")
    return identifier.lower()


def _apply_provider_payload(record: PaperDoiRecord, payload: dict[str, Any]) -> None:
    safe = _safe_provider_payload(payload)
    if safe["doi"] and DOI_PATTERN.fullmatch(safe["doi"]):
        record.doi = safe["doi"].lower()
        record.doi_url = f"https://doi.org/{record.doi}"
    if safe["conceptdoi"] and DOI_PATTERN.fullmatch(safe["conceptdoi"]):
        record.concept_doi = safe["conceptdoi"].lower()
    if safe["html"].startswith("https://"):
        record.provider_record_url = safe["html"]
    record.provider_payload = safe


def reserve_zenodo_doi(record: PaperDoiRecord, *, actor_id: str) -> PaperDoiRecord:
    if record.created_by_id != actor_id:
        raise DoiWorkflowError("paper_forbidden", "You do not own this DOI workflow", status=403)
    if record.state == "published":
        return record
    if record.environment != current_app.config["ZENODO_ENVIRONMENT"]:
        raise DoiWorkflowError(
            "doi_environment_mismatch",
            "This DOI workflow belongs to a different Zenodo environment",
            status=409,
        )
    version = record.paper_version
    if version.manuscript_checksum != record.manuscript_checksum:
        raise DoiWorkflowError(
            "manuscript_changed", "The manuscript no longer matches the prepared DOI record", status=409
        )
    local_path = resolve_local_pdf(
        version.manuscript_uri, current_app.config["MANUSCRIPT_STORAGE_ROOT"]
    )
    if local_path is None or not local_path.is_file():
        raise DoiWorkflowError(
            "manuscript_storage_unavailable",
            "The DOI workflow currently requires a locally stored manuscript PDF",
            status=409,
        )
    connection = _connection(actor_id, record.environment)
    client = _client(connection)
    try:
        uses_records_api = record.provider_payload.get("api") == "records"
        if record.provider_record_id and uses_records_api:
            deposit = client.get_record_draft(record.provider_record_id)
        elif record.provider_record_id:
            deposit = client.get_deposition(record.provider_record_id)
        else:
            deposit = client.create_record(record.metadata_payload)
            record.provider_record_id = str(deposit["id"])
            _apply_provider_payload(record, deposit)
            record.provider_payload = {**record.provider_payload, "api": "records"}
            uses_records_api = True
            record.state = "deposit_created"
            record.last_error = None
            db.session.commit()

        filename = f"{version.paper.identifier.replace(':', '-')}-v{version.number}.pdf"
        if uses_records_api:
            managed_doi = _managed_doi(deposit)
            if managed_doi is None:
                deposit = client.reserve_record_doi(record.provider_record_id)
                managed_doi = _managed_doi(deposit)
            if managed_doi is None:
                raise ZenodoApiError("Zenodo did not return a managed DOI")
            links = deposit.get("links") if isinstance(deposit.get("links"), dict) else {}
            files_url = str(links.get("files") or "")
            if not files_url:
                raise ZenodoApiError("Zenodo did not provide a manuscript file endpoint")
            uploaded = client.upload_record_file(
                files_url, filename, local_path.read_bytes()
            )
            _apply_provider_payload(record, deposit)
        else:
            # Drafts created before PeerXiv 0.10 remain on Zenodo's legacy
            # deposition API so their provider identifiers are not orphaned.
            updated = client.update_metadata(record.provider_record_id, record.metadata_payload)
            links = updated.get("links") if isinstance(updated.get("links"), dict) else {}
            bucket_url = str(links.get("bucket") or "")
            if not bucket_url:
                deposit = client.get_deposition(record.provider_record_id)
                links = deposit.get("links") if isinstance(deposit.get("links"), dict) else {}
                bucket_url = str(links.get("bucket") or "")
            if not bucket_url:
                raise ZenodoApiError("Zenodo did not provide a manuscript upload location")
            uploaded = client.upload_file(bucket_url, filename, local_path.read_bytes())
            _apply_provider_payload(record, updated)
        record.provider_payload = {
            **record.provider_payload,
            "file": {
                "name": str(uploaded.get("key") or uploaded.get("filename") or filename),
                "checksum": str(uploaded.get("checksum") or ""),
                "size": int(uploaded.get("size") or uploaded.get("filesize") or 0),
            },
        }
        if not record.doi:
            raise ZenodoApiError("Zenodo did not return a reserved DOI")
        record.state = "reserved"
        record.reserved_at = utc_now()
        record.last_error = None
        db.session.commit()
        return record
    except ZenodoApiError as error:
        record.state = "error"
        record.last_error = str(error)[:500]
        db.session.commit()
        raise DoiWorkflowError(
            "zenodo_reservation_failed",
            "Zenodo could not reserve the DOI and preservation draft",
            status=502,
        ) from error


def publish_zenodo_doi(
    record: PaperDoiRecord,
    *,
    actor_id: str,
    confirmation: str,
) -> PaperDoiRecord:
    if record.created_by_id != actor_id:
        raise DoiWorkflowError("paper_forbidden", "You do not own this DOI workflow", status=403)
    if record.state == "published":
        return record
    if record.state != "reserved" or not record.doi or not record.provider_record_id:
        raise DoiWorkflowError(
            "doi_not_reserved", "Reserve and inspect the DOI draft before publishing", status=409
        )
    if confirmation.strip().casefold() != record.doi.casefold():
        raise DoiWorkflowError(
            "doi_confirmation_failed", "Enter the reserved DOI exactly to confirm publication"
        )
    if (
        record.environment == "production"
        and not current_app.config["ZENODO_ALLOW_PRODUCTION_PUBLISH"]
    ):
        raise DoiWorkflowError(
            "production_doi_publish_disabled",
            "Production DOI publication is disabled by the PeerXiv server configuration",
            status=403,
        )
    connection = _connection(actor_id, record.environment)
    client = _client(connection)
    try:
        if record.provider_payload.get("api") == "records":
            published = client.publish_record(record.provider_record_id)
        else:
            published = client.publish(record.provider_record_id)
        _apply_provider_payload(record, published)
        if not record.doi:
            raise ZenodoApiError("Zenodo published the record without a DOI")
        record.state = "published"
        record.published_at = utc_now()
        record.last_error = None
        db.session.commit()
        return record
    except ZenodoApiError as error:
        record.last_error = str(error)[:500]
        db.session.commit()
        raise DoiWorkflowError(
            "zenodo_publication_failed",
            "Zenodo could not publish the DOI record",
            status=502,
        ) from error
