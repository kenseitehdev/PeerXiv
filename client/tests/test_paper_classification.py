from sqlalchemy import func, select

from peerxiv.classifier import CoUClassificationRun
from peerxiv.extensions import db


def classification_payload():
    return {
        "title": "A CoU-Gated Lateral Recurrent Classifier for Research Papers",
        "abstract": (
            "We introduce a recurrent neural classifier that replaces global "
            "backpropagation with lateral propagation, eligibility traces, state "
            "reconstruction, uncertainty evidence, and rolling predictive validation."
        ),
        "authors": ["Jay Kumar"],
        "keywords": [
            "Calculus of Uncertainty",
            "lateral propagation",
            "recurrent classification",
        ],
        "sections": [
            {
                "heading": "Method",
                "text": (
                    "The learning algorithm propagates local prediction errors laterally "
                    "through a category graph. A validation gate retains evidence and "
                    "state movement without backpropagation."
                ),
            }
        ],
    }


def test_candidate_classifier_uses_lateral_updates_and_descriptive_tags(client):
    response = client.post("/api/v1/discovery/classify", json=classification_payload())
    assert response.status_code == 200
    result = response.get_json()

    assert result["label"] == "cs.LG"
    algorithm = result["components"]["algorithm"]
    assert algorithm["global_backpropagation"] is False
    assert algorithm["learning"] == "local-eligibility-and-lateral-propagation"
    assert any(step["step"] == "lateral-recurrent-update" for step in result["trace"])
    assert any(step["step"] == "predictive-validation" for step in result["trace"])

    metadata = result["components"]["descriptive_metadata"]
    assert metadata["schema_version"] == "peerxiv.descriptive-metadata.v1"
    lateral = next(tag for tag in metadata["tags"] if tag["slug"] == "lateral-propagation")
    assert lateral["facet"] == "method"
    assert lateral["description"]
    assert lateral["evidence"][0]["excerpt"]
    assert lateral["provenance"] == "cou-faceted-extraction"


def test_published_paper_classification_persists_queryable_metadata(client, app):
    document = classification_payload()
    created = client.post(
        "/api/v1/papers",
        json={
            "title": document["title"],
            "abstract": document["abstract"],
            "authors": document["authors"],
            "subject": "Computer Science",
            "subfield": "Machine Learning",
            "tags": document["keywords"],
        },
    ).get_json()
    published = client.post(
        f"/api/v1/papers/{created['identifier']}/publish",
        json={
            "authors": document["authors"],
            "tags": document["keywords"],
            "manuscript_uri": "object://manuscripts/lateral-classifier.pdf",
            "manuscript_checksum": "sha256:lateral-classifier",
        },
    )
    assert published.status_code == 201
    assert published.get_json()["classification"]["label"] == "cs.LG"
    assert published.get_json()["metadata"]["primary_category"] == "cs.LG"

    first = client.post(
        f"/api/v1/papers/{created['identifier']}/classify",
        json={"sections": document["sections"]},
    )
    assert first.status_code == 200
    classified = first.get_json()
    assert classified["reused"] is False
    assert classified["classification"]["label"] == "cs.LG"
    assert classified["metadata"]["primary_category"] == "cs.LG"
    assert any(tag["facet"] == "subject" for tag in classified["metadata"]["tags"])
    assert any(tag["facet"] == "method" for tag in classified["metadata"]["tags"])

    metadata = client.get(f"/api/v1/papers/{created['identifier']}/metadata")
    assert metadata.status_code == 200
    assert metadata.get_json()["classification_run_id"] == classified["classification"]["run_id"]

    second = client.post(
        f"/api/v1/papers/{created['identifier']}/classify",
        json={"sections": document["sections"]},
    )
    assert second.status_code == 200
    assert second.get_json()["reused"] is True

    with app.app_context():
        run_count = db.session.scalar(select(func.count()).select_from(CoUClassificationRun))
        assert run_count == 2


def test_draft_must_be_published_before_classification(client):
    document = classification_payload()
    created = client.post(
        "/api/v1/papers",
        json={
            "title": document["title"],
            "abstract": document["abstract"],
            "authors": document["authors"],
            "subject": "Computer Science",
            "tags": document["keywords"],
        },
    ).get_json()
    response = client.post(f"/api/v1/papers/{created['identifier']}/classify", json={})
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "paper_not_published"
