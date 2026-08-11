def test_health_and_bootstrap(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.get_json() == {"api_version": "v1", "ok": True, "service": "PeerXiv"}

    bootstrap = client.get("/api/v1/bootstrap").get_json()
    assert bootstrap["modules"] == [
        "accounts",
        "papers",
        "social",
        "discovery",
        "journals",
        "spaces",
    ]
    assert bootstrap["classifier"] == {
        "configured": True,
        "kind": "cou",
        "version": "cou-paper-lateral-0.1.0",
    }


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"PeerXiv" in response.data
    response.close()

    javascript = client.get("/templates/src/main.js")
    assert javascript.status_code == 200
    assert b"PeerXiv" in javascript.data
    javascript.close()
