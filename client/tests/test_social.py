from tests.test_accounts import register


def test_discussion_reply_follow_save_vote_and_notifications(app, client):
    maya, _maya_user = register(app, email="maya.social@example.com", name="Maya Chen")
    created = client.post(
        "/api/v1/social/discussions",
        json={
            "title": "How should predictive validation histories be retained?",
            "topic": "Open Science",
            "body": (
                "A revised preprint can change its evidence without making the validation "
                "history visible. What should the durable record retain?"
            ),
        },
    )
    assert created.status_code == 201
    discussion = created.get_json()
    assert discussion["following"] is True
    assert discussion["classification"]["metadata"]["schema_version"] == "peerxiv.descriptive-metadata.v1"

    discussion_id = discussion["id"]
    reply = maya.post(
        f"/api/v1/social/discussions/{discussion_id}/comments",
        json={"body": "It should retain each validation gate and the evidence state it accepted."},
    )
    assert reply.status_code == 201
    assert reply.get_json()["author"]["display_name"] == "Maya Chen"

    notifications = client.get("/api/v1/accounts/notifications").get_json()["results"]
    assert any(item["kind"] == "discussion-reply" for item in notifications)

    assert maya.post(
        f"/api/v1/social/discussions/{discussion_id}/follow", json={"enabled": True}
    ).get_json()["following"] is True
    assert maya.post(
        f"/api/v1/social/discussions/{discussion_id}/save", json={"enabled": True}
    ).get_json()["saved"] is True
    vote = maya.post(
        f"/api/v1/social/discussions/{discussion_id}/vote", json={"value": 1}
    ).get_json()
    assert vote["viewer_vote"] == 1
    assert vote["score"] == 2

    detail = maya.get(f"/api/v1/social/discussions/{discussion_id}").get_json()
    assert detail["comment_count"] == 1
    assert detail["following"] is True
    assert detail["saved"] is True
    assert detail["viewer_vote"] == 1
    assert detail["comments"][0]["body"].startswith("It should retain")

