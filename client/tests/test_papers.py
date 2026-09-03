def draft_payload():
    return {
        "title": "State Reconstruction Under Incomplete Evidence",
        "abstract": "A sufficiently long abstract for the backend contract test.",
        "authors": ["Jay Kumar"],
        "subject": "Mathematics",
        "subfield": "Dynamical Systems",
        "tags": ["CoU", "Evidence"],
    }


def test_create_publish_and_discover_paper(client):
    created = client.post("/api/v1/papers", json=draft_payload())
    assert created.status_code == 201
    paper = created.get_json()
    assert paper["status"] == "draft"
    assert paper["authors"] == ["Jay Kumar"]
    assert paper["tags"] == ["cou", "evidence"]

    published = client.post(
        f"/api/v1/papers/{paper['identifier']}/publish",
        json={
            "authors": ["Jay Kumar"],
            "tags": ["cou", "evidence"],
            "manuscript_uri": "object://manuscripts/test.pdf",
            "manuscript_checksum": "sha256:test",
        },
    )
    assert published.status_code == 201
    assert published.get_json()["number"] == 1

    feed = client.get("/api/v1/discovery/feed").get_json()
    assert len(feed["results"]) == 1
    assert feed["results"][0]["identifier"] == paper["identifier"]


def test_authors_must_be_an_array(client):
    payload = draft_payload()
    payload["authors"] = "Jay Kumar"
    response = client.post("/api/v1/papers", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_drafts_and_publication_are_owner_scoped(app, client, anonymous_client):
    from tests.test_accounts import register

    draft = client.post("/api/v1/papers", json=draft_payload()).get_json()
    identifier = draft["identifier"]
    assert anonymous_client.get(f"/api/v1/papers/{identifier}").status_code == 404

    other, _other_user = register(
        app,
        email="other.paper.owner@example.com",
        name="Other Researcher",
    )
    assert other.get(f"/api/v1/papers/{identifier}").status_code == 404
    forbidden = other.post(
        f"/api/v1/papers/{identifier}/publish",
        json={"authors": ["Other Researcher"], "tags": ["ownership"]},
    )
    assert forbidden.status_code == 403
    assert forbidden.get_json()["error"]["code"] == "paper_forbidden"

    owner_listing = client.get("/api/v1/papers?include_drafts=true").get_json()["results"]
    other_listing = other.get("/api/v1/papers?include_drafts=true").get_json()["results"]
    assert any(paper["identifier"] == identifier for paper in owner_listing)
    assert all(paper["identifier"] != identifier for paper in other_listing)
