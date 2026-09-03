from io import BytesIO
import json

from cryptography.fernet import Fernet
from pypdf import PdfWriter
from sqlalchemy import select

from accounts.models import ZenodoConnection
from papers.models import PaperDoiRecord, PaperVersion
from peerxiv.extensions import db


class FakeZenodo:
    def __init__(self, *, doi_provider="datacite"):
        self.verified = 0
        self.created = 0
        self.created_payload = None
        self.reserved = 0
        self.uploaded = None
        self.published = 0
        self.doi_provider = doi_provider

    def verify(self):
        self.verified += 1

    def _draft(self, *, reserved=False):
        payload = {
            "id": "74201",
            "is_draft": True,
            "status": "draft",
            "links": {
                "files": "https://sandbox.zenodo.org/api/records/74201/draft/files",
                "self_html": "https://sandbox.zenodo.org/uploads/74201",
                "reserve_doi": (
                    "https://sandbox.zenodo.org/api/records/74201/draft/pids/doi"
                ),
            },
        }
        if reserved:
            payload["pids"] = {
                "doi": {
                    "identifier": "10.5072/zenodo.74201",
                    "provider": self.doi_provider,
                }
            }
        return payload

    def create_record(self, draft):
        self.created += 1
        self.created_payload = draft
        return self._draft()

    def get_record_draft(self, deposition_id):
        assert str(deposition_id) == "74201"
        return self._draft(reserved=True)

    def reserve_record_doi(self, deposition_id):
        assert str(deposition_id) == "74201"
        self.reserved += 1
        return self._draft(reserved=True)

    def upload_record_file(self, files_url, filename, data):
        assert files_url == "https://sandbox.zenodo.org/api/records/74201/draft/files"
        self.uploaded = (filename, data)
        return {"key": filename, "checksum": "md5:test", "size": len(data)}

    def publish_record(self, deposition_id):
        assert str(deposition_id) == "74201"
        self.published += 1
        return {
            "id": "74201",
            "is_draft": False,
            "is_published": True,
            "status": "published",
            "pids": {
                "doi": {
                    "identifier": "10.5072/zenodo.74201",
                    "provider": "datacite",
                }
            },
            "parent": {
                "pids": {
                    "doi": {
                        "identifier": "10.5072/zenodo.74200",
                        "provider": "datacite",
                    }
                }
            },
            "links": {"self_html": "https://sandbox.zenodo.org/records/74201"},
        }


def pdf_bytes():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def publish_paper(client):
    draft = client.post(
        "/api/v1/papers",
        json={
            "title": "Versioned Uncertainty Evidence",
            "abstract": (
                "A sufficiently detailed abstract about uncertainty evidence, "
                "validation, and versioned research records."
            ),
            "authors": ["Jay Kumar"],
            "tags": ["uncertainty", "validation"],
        },
    ).get_json()
    response = client.post(
        f"/api/v1/papers/{draft['identifier']}/publish",
        data={
            "authors": json.dumps(["Jay Kumar"]),
            "tags": json.dumps(["uncertainty", "validation"]),
            "manuscript": (BytesIO(pdf_bytes()), "paper.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    return draft["identifier"]


def configure_zenodo(app, fake):
    key = Fernet.generate_key().decode("ascii")
    app.config.update(
        CREDENTIAL_ENCRYPTION_KEY=key,
        ZENODO_ENABLED=True,
        ZENODO_ENVIRONMENT="sandbox",
        ZENODO_BASE_URL="https://sandbox.zenodo.org",
        ZENODO_TIMEOUT=1,
        ZENODO_CLIENT_FACTORY=lambda **_kwargs: fake,
        ZENODO_ALLOW_PRODUCTION_PUBLISH=False,
    )
    return key


def test_zenodo_token_is_verified_encrypted_and_never_returned(app, client):
    fake = FakeZenodo()
    configure_zenodo(app, fake)
    token = "sandbox-secret-token-value-123456"
    response = client.post("/api/v1/accounts/zenodo", json={"token": token})
    assert response.status_code == 200
    assert fake.verified == 1
    assert response.get_json()["token_hint"] == "…3456"
    assert token not in response.get_data(as_text=True)

    with app.app_context():
        connection = db.session.scalar(select(ZenodoConnection))
        assert connection.encrypted_token != token
        assert token not in connection.encrypted_token

    me = client.get("/api/v1/accounts/me")
    assert me.get_json()["user"]["zenodo"]["environment"] == "sandbox"
    assert token not in me.get_data(as_text=True)


def test_doi_prepare_reserve_publish_and_machine_readable_landing(app, client):
    fake = FakeZenodo()
    configure_zenodo(app, fake)
    token = "sandbox-secret-token-value-123456"
    assert client.post("/api/v1/accounts/zenodo", json={"token": token}).status_code == 200
    identifier = publish_paper(client)

    prepared = client.post(f"/api/v1/papers/{identifier}/doi/prepare")
    assert prepared.status_code == 200
    assert prepared.get_json()["state"] == "metadata_ready"
    assert prepared.get_json()["doi"] is None

    blocked = client.post(
        f"/api/v1/papers/{identifier}/doi/reserve", json={"no_existing_doi": False}
    )
    assert blocked.status_code == 400
    assert fake.created == 0

    reserved = client.post(
        f"/api/v1/papers/{identifier}/doi/reserve", json={"no_existing_doi": True}
    )
    assert reserved.status_code == 200
    assert reserved.get_json()["state"] == "reserved"
    assert reserved.get_json()["doi"] == "10.5072/zenodo.74201"
    assert fake.created == 1
    assert fake.reserved == 1
    assert fake.created_payload["metadata"]["resource_type"]["id"] == "publication-preprint"
    assert fake.created_payload["metadata"]["creators"] == [
        {
            "person_or_org": {
                "type": "personal",
                "given_name": "Jay",
                "family_name": "Kumar",
                "name": "Kumar, Jay",
            }
        }
    ]
    assert "prereserve_doi" not in fake.created_payload["metadata"]
    assert fake.uploaded[0].endswith("-v1.pdf")
    assert fake.uploaded[1].startswith(b"%PDF-")

    wrong = client.post(
        f"/api/v1/papers/{identifier}/doi/publish",
        json={"confirmation": "10.5072/zenodo.wrong"},
    )
    assert wrong.status_code == 400
    assert fake.published == 0

    published = client.post(
        f"/api/v1/papers/{identifier}/doi/publish",
        json={"confirmation": "10.5072/zenodo.74201"},
    )
    assert published.status_code == 200
    assert published.get_json()["state"] == "published"
    assert published.get_json()["doi_url"] == "https://doi.org/10.5072/zenodo.74201"
    assert fake.published == 1

    detail = client.get(f"/api/v1/papers/{identifier}").get_json()
    version = detail["versions"][0]
    assert version["doi"]["doi"] == "10.5072/zenodo.74201"
    assert token not in json.dumps(detail)

    landing = client.get(f"/papers/{identifier}/versions/1")
    html = landing.get_data(as_text=True)
    assert landing.status_code == 200
    assert 'name="citation_doi" content="10.5072/zenodo.74201"' in html
    assert f"/api/v1/papers/{identifier}/versions/1/pdf" in html
    assert "sha256:" in html


def test_production_doi_publish_requires_explicit_server_switch(app, client):
    fake = FakeZenodo()
    configure_zenodo(app, fake)
    client.post(
        "/api/v1/accounts/zenodo", json={"token": "sandbox-secret-token-value-123456"}
    )
    identifier = publish_paper(client)
    client.post(f"/api/v1/papers/{identifier}/doi/prepare")
    client.post(
        f"/api/v1/papers/{identifier}/doi/reserve", json={"no_existing_doi": True}
    )

    with app.app_context():
        connection = db.session.scalar(select(ZenodoConnection))
        connection.environment = "production"
        version = db.session.scalar(select(PaperVersion))
        version.doi_record.environment = "production"
        db.session.commit()
    app.config.update(
        ZENODO_ENVIRONMENT="production",
        ZENODO_BASE_URL="https://zenodo.org",
        ZENODO_ALLOW_PRODUCTION_PUBLISH=False,
    )
    blocked = client.post(
        f"/api/v1/papers/{identifier}/doi/publish",
        json={"confirmation": "10.5072/zenodo.74201"},
    )
    assert blocked.status_code == 403
    assert blocked.get_json()["error"]["code"] == "production_doi_publish_disabled"
    assert fake.published == 0


def test_reservation_rejects_external_doi_state_before_upload(app, client):
    fake = FakeZenodo(doi_provider="external")
    configure_zenodo(app, fake)
    client.post(
        "/api/v1/accounts/zenodo", json={"token": "sandbox-secret-token-value-123456"}
    )
    identifier = publish_paper(client)
    client.post(f"/api/v1/papers/{identifier}/doi/prepare")

    response = client.post(
        f"/api/v1/papers/{identifier}/doi/reserve", json={"no_existing_doi": True}
    )

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "zenodo_reservation_failed"
    assert fake.uploaded is None
    with app.app_context():
        record = db.session.scalar(select(PaperDoiRecord))
        assert record.state == "error"
        assert record.last_error == "Zenodo marked this draft as having an external DOI"
