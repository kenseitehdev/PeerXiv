from io import BytesIO
import json

from pypdf import PdfWriter

from peerxiv.malware import MalwareDetected


def make_pdf_bytes(*, javascript: bool = False) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if javascript:
        writer.add_js("app.alert('this action must be removed')")
    writer.write(output)
    return output.getvalue()


PDF_BYTES = make_pdf_bytes()


def create_paper(client, *, title, abstract, authors, tags):
    response = client.post(
        "/api/v1/papers",
        json={
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "subject": "Pending CoU classification",
            "tags": tags,
        },
    )
    assert response.status_code == 201
    return response.get_json()


def test_publish_uploads_pdf_and_automates_category_and_metadata(client):
    draft = create_paper(
        client,
        title="Lateral Recurrent Classification Under Uncertainty",
        abstract=(
            "A recurrent machine learning classifier uses lateral propagation, "
            "eligibility traces, uncertainty evidence, and predictive validation."
        ),
        authors=["Jay Kumar"],
        tags=["lateral propagation", "recurrent classification", "uncertainty"],
    )
    response = client.post(
        f"/api/v1/papers/{draft['identifier']}/publish",
        data={
            "authors": json.dumps(["Jay Kumar"]),
            "tags": json.dumps(
                ["lateral propagation", "recurrent classification", "uncertainty"]
            ),
            "sections": json.dumps(
                [
                    {
                        "heading": "Method",
                        "text": (
                            "Local prediction discrepancies propagate laterally through "
                            "related recurrent category states without backpropagation."
                        ),
                    }
                ]
            ),
            "manuscript": (BytesIO(PDF_BYTES), "classifier.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    published = response.get_json()
    assert published["classification"]["label"] == "cs.LG"
    assert published["metadata"]["primary_category"] == "cs.LG"
    assert published["manuscript_uri"].startswith("peerxiv://manuscripts/")
    assert published["manuscript_checksum"].startswith("sha256:")

    detail = client.get(f"/api/v1/papers/{draft['identifier']}").get_json()
    assert detail["subject"] == "Machine Learning"
    assert detail["subfield"] == "cs.LG"

    public_feed = client.get("/api/v1/papers").get_json()["results"]
    public_record = next(item for item in public_feed if item["identifier"] == draft["identifier"])
    assert public_record["versions"][0]["manuscript_uri"] == published["manuscript_uri"]

    pdf = client.get(f"/api/v1/papers/{draft['identifier']}/pdf")
    assert pdf.status_code == 200
    assert pdf.content_type == "application/pdf"
    assert pdf.data.startswith(b"%PDF-")
    assert b"%%EOF" in pdf.data[-8192:]
    assert b"/JavaScript" not in pdf.data
    assert pdf.headers["Content-Disposition"].startswith("inline;")
    assert pdf.headers["X-PeerXiv-Checksum"] == published["manuscript_checksum"]
    pdf.close()


def test_invalid_pdf_rolls_back_publication(client):
    draft = create_paper(
        client,
        title="Invalid Manuscript Test",
        abstract="A long enough abstract for testing invalid manuscript handling.",
        authors=["Jay Kumar"],
        tags=["testing"],
    )
    response = client.post(
        f"/api/v1/papers/{draft['identifier']}/publish",
        data={
            "authors": json.dumps(["Jay Kumar"]),
            "tags": json.dumps(["testing"]),
            "manuscript": (BytesIO(b"not a pdf"), "paper.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_manuscript"
    detail = client.get(f"/api/v1/papers/{draft['identifier']}").get_json()
    assert detail["status"] == "draft"
    assert detail["versions"] == []


def test_pdf_is_reconstructed_without_document_actions(client):
    draft = create_paper(
        client,
        title="Active PDF Reconstruction Test",
        abstract="A long enough abstract for testing removal of active PDF document actions.",
        authors=["Jay Kumar"],
        tags=["security"],
    )
    original = make_pdf_bytes(javascript=True)
    assert b"/JavaScript" in original
    response = client.post(
        f"/api/v1/papers/{draft['identifier']}/publish",
        data={
            "authors": json.dumps(["Jay Kumar"]),
            "tags": json.dumps(["security"]),
            "manuscript": (BytesIO(original), "active.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    pdf = client.get(f"/api/v1/papers/{draft['identifier']}/pdf")
    assert b"/JavaScript" not in pdf.data
    assert b"app.alert" not in pdf.data
    quarantine = client.application.config["MANUSCRIPT_STORAGE_ROOT"] + "/.quarantine"
    from pathlib import Path

    assert list(Path(quarantine).iterdir()) == []
    pdf.close()


def test_malware_detection_rejects_and_rolls_back(client, monkeypatch):
    draft = create_paper(
        client,
        title="Malware Scan Rejection Test",
        abstract="A long enough abstract for testing malware rejection before publication.",
        authors=["Jay Kumar"],
        tags=["security"],
    )
    client.application.config["CLAMAV_HOST"] = "private-scanner"

    def reject(*_args, **_kwargs):
        raise MalwareDetected("The manuscript was rejected by malware scanning (Test.Signature)")

    monkeypatch.setattr("papers.manuscripts.scan_path", reject)
    response = client.post(
        f"/api/v1/papers/{draft['identifier']}/publish",
        data={
            "authors": json.dumps(["Jay Kumar"]),
            "tags": json.dumps(["security"]),
            "manuscript": (BytesIO(PDF_BYTES), "infected.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "unsafe_manuscript"
    assert client.get(f"/api/v1/papers/{draft['identifier']}").get_json()["versions"] == []


def test_required_scanner_fails_closed(client):
    draft = create_paper(
        client,
        title="Unavailable Scanner Test",
        abstract="A long enough abstract for testing fail-closed manuscript scanning behavior.",
        authors=["Jay Kumar"],
        tags=["security"],
    )
    client.application.config.update(CLAMAV_HOST=None, MALWARE_SCAN_REQUIRED=True)
    response = client.post(
        f"/api/v1/papers/{draft['identifier']}/publish",
        data={
            "authors": json.dumps(["Jay Kumar"]),
            "tags": json.dumps(["security"]),
            "manuscript": (BytesIO(PDF_BYTES), "paper.pdf"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "manuscript_scan_unavailable"


def test_publish_and_discussion_notifications_match_exact_subtopics(client):
    first = create_paper(
        client,
        title="Validated Lateral Propagation for Recurrent Classifiers",
        abstract=(
            "We use lateral propagation and predictive validation in a recurrent "
            "machine learning classifier with explicit uncertainty evidence."
        ),
        authors=["Maya Chen"],
        tags=["lateral propagation", "recurrent modeling", "predictive validation"],
    )
    first_publish = client.post(
        f"/api/v1/papers/{first['identifier']}/publish",
        json={
            "authors": ["Maya Chen"],
            "tags": ["lateral propagation", "recurrent modeling", "predictive validation"],
        },
    )
    assert first_publish.status_code == 201

    second = create_paper(
        client,
        title="Uncertainty-Gated Lateral Learning Without Backpropagation",
        abstract=(
            "This recurrent classifier propagates local state changes through lateral "
            "connections and applies uncertainty and rolling predictive validation."
        ),
        authors=["Noor Al-Sayed"],
        tags=["lateral propagation", "recurrent modeling", "uncertainty"],
    )
    second_publish = client.post(
        f"/api/v1/papers/{second['identifier']}/publish",
        json={
            "authors": ["Noor Al-Sayed"],
            "tags": ["lateral propagation", "recurrent modeling", "uncertainty"],
        },
    )
    assert second_publish.status_code == 201
    automatic = second_publish.get_json()["notifications"]
    assert any(item["paper"] == first["identifier"] for item in automatic)
    match = next(item for item in automatic if item["paper"] == first["identifier"])
    assert match["kind"] == "similar-paper"
    assert "Lateral propagation" in match["reason"]

    discussion = client.post(
        "/api/v1/discovery/notifications/classify",
        json={
            "source_kind": "discussion",
            "source_id": "discussion:test",
            "title": "Can lateral propagation replace backpropagation?",
            "text": (
                "I want to compare recurrent classification using lateral propagation, "
                "eligibility traces, uncertainty evidence, and predictive validation."
            ),
            "keywords": ["lateral propagation", "recurrent modeling"],
            "exclude_authors": ["Jay Kumar"],
        },
    )
    assert discussion.status_code == 200
    notifications = discussion.get_json()["notifications"]
    assert {item["paper"] for item in notifications} == {
        first["identifier"],
        second["identifier"],
    }
    assert all(item["kind"] == "discussion-research-match" for item in notifications)
