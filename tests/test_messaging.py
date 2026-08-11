def register(app, email: str, name: str):
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
    client.environ_base["HTTP_X_CSRF_TOKEN"] = response.get_json()["csrf_token"]
    return client, response.get_json()["user"]


def test_conversations_persist_enforce_membership_and_track_reads(app, client):
    maya, maya_user = register(app, "maya.messages@example.com", "Maya Chen")
    outsider, _ = register(app, "outsider@example.com", "Outside Researcher")

    created = client.post(
        "/api/v1/social/conversations",
        json={
            "recipient_email": maya_user["email"],
            "body": "  Evidence\u202e\tshould remain readable.  ",
        },
    )
    assert created.status_code == 201
    conversation = created.get_json()
    conversation_id = conversation["id"]
    assert conversation["messages"][0]["body"] == "Evidence should remain readable."

    creator_results = client.get("/api/v1/social/conversations").get_json()["results"]
    assert creator_results[0]["id"] == conversation_id
    assert creator_results[0]["unread_count"] == 0

    recipient_results = maya.get("/api/v1/social/conversations").get_json()["results"]
    assert recipient_results[0]["unread_count"] == 1
    inbox = maya.get(f"/api/v1/social/conversations/{conversation_id}/messages")
    assert inbox.status_code == 200
    assert inbox.get_json()["results"][0]["body"] == "Evidence should remain readable."
    assert maya.post(f"/api/v1/social/conversations/{conversation_id}/read").status_code == 200
    assert maya.get("/api/v1/social/conversations").get_json()["results"][0]["unread_count"] == 0

    reply = maya.post(
        f"/api/v1/social/conversations/{conversation_id}/messages",
        json={"body": "The validation result is reproducible."},
    )
    assert reply.status_code == 201
    assert client.get("/api/v1/social/conversations").get_json()["results"][0]["unread_count"] == 1

    assert outsider.get(f"/api/v1/social/conversations/{conversation_id}/messages").status_code == 404
    assert outsider.post(
        f"/api/v1/social/conversations/{conversation_id}/messages",
        json={"body": "This must not be accepted."},
    ).status_code == 404

    notifications = maya.get("/api/v1/accounts/notifications").get_json()["results"]
    assert any(item["kind"] == "new-message" for item in notifications)


def test_conversation_recipient_and_body_validation(client):
    missing = client.post(
        "/api/v1/social/conversations",
        json={"recipient_email": "missing@example.com", "body": "A valid initial message."},
    )
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "recipient_not_found"

    invalid = client.post(
        "/api/v1/social/conversations",
        json={"recipient_email": "not-an-email", "body": "A valid initial message."},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "validation_error"
