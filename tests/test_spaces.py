from tests.test_accounts import register


def test_private_research_space_members_papers_and_resources(app, client, anonymous_client):
    draft = client.post(
        "/api/v1/papers",
        json={
            "title": "A Durable Research Space",
            "abstract": "A sufficiently long abstract for a linked research-space record.",
            "authors": ["Jay Kumar"],
            "tags": ["provenance"],
        },
    ).get_json()
    created = client.post(
        "/api/v1/spaces",
        json={
            "kind": "workspace",
            "title": "Calculus of Uncertainty",
            "description": "Papers, source, validation traces, and collaborators.",
            "visibility": "private",
            "paper_identifiers": [draft["identifier"]],
            "details": {"repository": "https://example.com/jay/cou"},
        },
    )
    assert created.status_code == 201
    space = created.get_json()
    space_id = space["id"]
    assert space["papers"][0]["paper"]["identifier"] == draft["identifier"]
    assert anonymous_client.get(f"/api/v1/spaces/{space_id}").status_code == 404

    resource = client.post(
        f"/api/v1/spaces/{space_id}/resources",
        json={
            "resource_type": "repository",
            "title": "CoU source",
            "url": "https://example.com/jay/cou",
        },
    )
    assert resource.status_code == 201
    assert resource.get_json()["id"]

    maya, _maya_user = register(app, email="maya.spaces@example.com", name="Maya Chen")
    assert maya.get(f"/api/v1/spaces/{space_id}").status_code == 404
    member = client.post(
        f"/api/v1/spaces/{space_id}/members",
        json={"email": "maya.spaces@example.com", "role": "editor"},
    )
    assert member.status_code == 201
    assert maya.get(f"/api/v1/spaces/{space_id}").status_code == 200
    member_notifications = maya.get("/api/v1/accounts/notifications").get_json()["results"]
    assert any(item["kind"] == "research-space-member" for item in member_notifications)

    updated = maya.patch(
        f"/api/v1/spaces/{space_id}",
        json={"status": "review"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["status"] == "review"
