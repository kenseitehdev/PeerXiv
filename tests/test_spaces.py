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


def test_collaborator_autosuggest_roles_permissions_and_removal(app, client):
    maya, maya_user = register(app, email="maya.collab@example.com", name="Maya Chen")
    noor, noor_user = register(app, email="noor.collab@example.com", name="Noor Al-Sayed")
    created = client.post(
        "/api/v1/spaces",
        json={
            "kind": "workspace",
            "title": "Verified collaboration workspace",
            "visibility": "private",
        },
    ).get_json()
    workspace_id = created["id"]
    assert created["viewer_access"]["role"] == "owner"
    assert "manage_members" in created["viewer_access"]["permissions"]

    suggestions = client.get("/api/v1/accounts/people/search?q=maya").get_json()["results"]
    assert [person["id"] for person in suggestions] == [maya_user["id"]]
    assert suggestions[0]["email_match"] is None
    exact_email = client.get(
        "/api/v1/accounts/people/search?q=maya.collab%40example.com"
    ).get_json()["results"]
    assert exact_email[0]["email_match"] == "maya.collab@example.com"

    added = client.post(
        f"/api/v1/spaces/{workspace_id}/members",
        json={"account_id": maya_user["id"], "role": "editor"},
    )
    assert added.status_code == 201
    assert "edit_space" in added.get_json()["permissions"]

    promoted = client.patch(
        f"/api/v1/spaces/{workspace_id}/members/{maya_user['id']}",
        json={"role": "maintainer"},
    )
    assert promoted.status_code == 200
    assert "manage_members" in promoted.get_json()["permissions"]

    forbidden_promotion = maya.post(
        f"/api/v1/spaces/{workspace_id}/members",
        json={"account_id": noor_user["id"], "role": "maintainer"},
    )
    assert forbidden_promotion.status_code == 403
    added_noor = maya.post(
        f"/api/v1/spaces/{workspace_id}/members",
        json={"account_id": noor_user["id"], "role": "reviewer"},
    )
    assert added_noor.status_code == 201
    assert added_noor.get_json()["permissions"] == ["view", "review"]

    reviewer_view = noor.get(f"/api/v1/spaces/{workspace_id}").get_json()
    assert reviewer_view["viewer_access"]["role"] == "reviewer"
    assert noor.patch(f"/api/v1/spaces/{workspace_id}", json={"status": "changed"}).status_code == 403

    removed = client.delete(f"/api/v1/spaces/{workspace_id}/members/{noor_user['id']}")
    assert removed.status_code == 204
    assert noor.get(f"/api/v1/spaces/{workspace_id}").status_code == 404
