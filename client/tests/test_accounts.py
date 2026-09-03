def register(app, *, email, name):
    client = app.test_client()
    response = client.post(
        "/api/v1/accounts/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": name,
            "role": "Researcher",
        },
    )
    assert response.status_code == 201
    payload = response.get_json()
    client.environ_base["HTTP_X_CSRF_TOKEN"] = payload["csrf_token"]
    return client, payload["user"]


def test_session_csrf_follow_recommendations_and_activity(app, client, anonymous_client):
    assert anonymous_client.get("/api/v1/accounts/me").get_json()["authenticated"] is False
    blocked = anonymous_client.post("/api/v1/accounts/notifications/read-all")
    assert blocked.status_code == 401

    maya, maya_user = register(app, email="maya@example.com", name="Maya Chen")
    me = client.get("/api/v1/accounts/me").get_json()
    assert me["authenticated"] is True
    jay_id = me["user"]["id"]

    no_csrf = app.test_client()
    login = no_csrf.post(
        "/api/v1/accounts/login",
        json={"email": "maya@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    assert no_csrf.post(f"/api/v1/accounts/people/{jay_id}/follow").status_code == 403

    followed = maya.post(f"/api/v1/accounts/people/{jay_id}/follow", json={"following": True})
    assert followed.status_code == 200
    assert followed.get_json()["following"] is True

    notification_results = client.get("/api/v1/accounts/notifications").get_json()["results"]
    assert any(item["kind"] == "new-follower" and "Maya Chen" in item["text"] for item in notification_results)

    recommendations = client.get("/api/v1/accounts/people/recommendations").get_json()["results"]
    maya_result = next(item for item in recommendations if item["id"] == maya_user["id"])
    assert maya_result["reason"] == "New researcher on PeerXiv"

    activity = maya.get("/api/v1/accounts/activity").get_json()["results"]
    assert any(item["verb"] == "followed" and item["object_id"] == jay_id for item in activity)


def test_logout_clears_session(client):
    assert client.post("/api/v1/accounts/logout").status_code == 204
    assert client.get("/api/v1/accounts/me").get_json()["authenticated"] is False


def test_alpha_registration_requires_exact_invite_and_cleans_profile(app):
    app.config.update(REGISTRATION_MODE="invite", ALPHA_INVITE_CODE="alpha-invite-code-2026")
    candidate = app.test_client()
    base = {
        "email": "invited@example.com",
        "password": "correct-horse-battery-staple",
        "display_name": "  Invited\u202e\tResearcher  ",
        "role": "  Systems\tResearcher ",
    }
    missing = candidate.post("/api/v1/accounts/register", json=base)
    assert missing.status_code == 403
    assert missing.get_json()["error"]["code"] == "invite_required"
    incorrect = candidate.post(
        "/api/v1/accounts/register", json={**base, "invite_code": "wrong-invite-code"}
    )
    assert incorrect.status_code == 403

    accepted = candidate.post(
        "/api/v1/accounts/register",
        json={**base, "invite_code": "alpha-invite-code-2026"},
    )
    assert accepted.status_code == 201
    assert accepted.get_json()["user"]["display_name"] == "Invited Researcher"
    assert accepted.get_json()["user"]["role"] == "Systems Researcher"


def test_registration_can_be_disabled(app):
    app.config["REGISTRATION_MODE"] = "disabled"
    response = app.test_client().post(
        "/api/v1/accounts/register",
        json={
            "email": "closed@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Closed Researcher",
            "role": "Researcher",
        },
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "registration_disabled"


def test_exact_subtopic_interests_generate_relevant_paper_notification(app, client):
    first = client.post(
        "/api/v1/papers",
        json={
            "title": "Lateral Propagation for Recurrent Research Classification",
            "abstract": (
                "A recurrent classifier uses lateral propagation, uncertainty evidence, "
                "and predictive validation without global backpropagation."
            ),
            "authors": ["Jay Kumar"],
            "tags": ["lateral propagation", "predictive validation"],
        },
    ).get_json()
    assert client.post(
        f"/api/v1/papers/{first['identifier']}/publish",
        json={
            "authors": ["Jay Kumar"],
            "tags": ["lateral propagation", "predictive validation"],
        },
    ).status_code == 201

    maya, _maya_user = register(app, email="maya.relevance@example.com", name="Maya Chen")
    second = maya.post(
        "/api/v1/papers",
        json={
            "title": "Validated Lateral Learning Under Uncertainty",
            "abstract": (
                "This recurrent learning system uses lateral propagation and rolling "
                "predictive validation to retain uncertain evidence."
            ),
            "authors": ["Maya Chen"],
            "tags": ["lateral propagation", "predictive validation"],
        },
    ).get_json()
    assert maya.post(
        f"/api/v1/papers/{second['identifier']}/publish",
        json={
            "authors": ["Maya Chen"],
            "tags": ["lateral propagation", "predictive validation"],
        },
    ).status_code == 201

    notifications = client.get("/api/v1/accounts/notifications").get_json()["results"]
    relevant = next(item for item in notifications if item["kind"] == "relevant-paper")
    assert relevant["object_id"] == second["identifier"]
    assert "Exact overlap" in relevant["reason"]
