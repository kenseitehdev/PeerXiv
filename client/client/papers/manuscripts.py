"""Quarantined PDF validation and local manuscript storage.

The final ``peerxiv://manuscripts/...`` URI contract can be backed by object
storage later. Uploads never enter the public manuscript directory until they
have passed size/type checks, structural reconstruction, and configured
malware scans.
"""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import re
from uuid import uuid4

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from werkzeug.datastructures import FileStorage

from peerxiv.malware import MalwareScannerUnavailable, scan_path


MANUSCRIPT_URI_PREFIX = "peerxiv://manuscripts/"
MANUSCRIPT_NAME = re.compile(r"^[0-9a-f-]{36}\.pdf$")
ALLOWED_PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}


class InvalidManuscript(ValueError):
    pass


def _validate_pdf_envelope(path: Path) -> None:
    with path.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise InvalidManuscript("The uploaded file does not have a valid PDF signature")
        source.seek(0, os.SEEK_END)
        size = source.tell()
        source.seek(max(0, size - 8192))
        if b"%%EOF" not in source.read():
            raise InvalidManuscript("The uploaded PDF is incomplete or missing its end marker")


def _reconstruct_pdf(source: Path, destination: Path, *, max_pages: int) -> None:
    try:
        reader = PdfReader(source, strict=False)
        if reader.is_encrypted:
            raise InvalidManuscript("Encrypted or password-protected PDFs are not accepted")
        page_count = len(reader.pages)
        if page_count < 1:
            raise InvalidManuscript("The manuscript PDF must contain at least one page")
        if page_count > max_pages:
            raise InvalidManuscript(f"The manuscript PDF must contain at most {max_pages} pages")

        writer = PdfWriter()
        for page in reader.pages:
            # A fresh catalog plus annotation/action exclusion drops document
            # JavaScript, launch actions, forms, and embedded-file annotations.
            writer.add_page(page, excluded_keys=("/Annots", "/AA"))
        writer.metadata = {"/Producer": "PeerXiv PDF reconstruction"}
        with destination.open("wb") as output:
            writer.write(output)
    except InvalidManuscript:
        raise
    except (PdfReadError, OSError, TypeError, ValueError, KeyError) as error:
        raise InvalidManuscript("The uploaded file is not a structurally valid PDF") from error


def store_pdf(
    upload: FileStorage,
    *,
    version_id: str,
    storage_root: str | Path,
    max_bytes: int = 45 * 1024 * 1024,
    max_pages: int = 5000,
    clamav_host: str | None = None,
    clamav_port: int = 3310,
    clamav_timeout: float = 30.0,
    scan_required: bool = False,
) -> tuple[str, str, Path]:
    filename = (upload.filename or "").strip()
    if not filename:
        raise InvalidManuscript("A manuscript filename is required")
    if not filename.casefold().endswith(".pdf"):
        raise InvalidManuscript("The manuscript must use the .pdf extension")
    content_type = (upload.content_type or "").casefold()
    if content_type and content_type not in ALLOWED_PDF_CONTENT_TYPES:
        raise InvalidManuscript("The manuscript must use the application/pdf content type")

    root = Path(storage_root).resolve()
    quarantine = root / ".quarantine"
    root.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(mode=0o700, exist_ok=True)
    destination = root / f"{version_id}.pdf"
    raw_path = quarantine / f"{version_id}.{uuid4().hex}.raw"
    clean_path = quarantine / f"{version_id}.{uuid4().hex}.clean.pdf"

    try:
        upload.stream.seek(0)
        total = 0
        with raw_path.open("xb") as output:
            while chunk := upload.stream.read(1024 * 1024):
                total += len(chunk)
                if total > max_bytes:
                    raise InvalidManuscript(
                        f"The manuscript must be no larger than {max_bytes // (1024 * 1024)} MiB"
                    )
                output.write(chunk)
        if total == 0:
            raise InvalidManuscript("The manuscript PDF is empty")
        _validate_pdf_envelope(raw_path)

        if clamav_host:
            scan_path(raw_path, host=clamav_host, port=clamav_port, timeout=clamav_timeout)
        elif scan_required:
            raise MalwareScannerUnavailable("Malware scanning is required but not configured")

        _reconstruct_pdf(raw_path, clean_path, max_pages=max_pages)
        if clean_path.stat().st_size > max_bytes:
            raise InvalidManuscript("The reconstructed manuscript exceeds the upload size limit")
        _validate_pdf_envelope(clean_path)
        if clamav_host:
            scan_path(clean_path, host=clamav_host, port=clamav_port, timeout=clamav_timeout)

        digest = sha256()
        with clean_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        os.replace(clean_path, destination)
        destination.chmod(0o640)
    finally:
        raw_path.unlink(missing_ok=True)
        clean_path.unlink(missing_ok=True)

    uri = f"{MANUSCRIPT_URI_PREFIX}{destination.name}"
    return uri, f"sha256:{digest.hexdigest()}", destination


def resolve_local_pdf(uri: str, storage_root: str | Path) -> Path | None:
    if not uri.startswith(MANUSCRIPT_URI_PREFIX):
        return None
    name = uri.removeprefix(MANUSCRIPT_URI_PREFIX)
    if not MANUSCRIPT_NAME.fullmatch(name):
        return None
    root = Path(storage_root).resolve()
    candidate = (root / name).resolve()
    if candidate.parent != root:
        return None
    return candidate

