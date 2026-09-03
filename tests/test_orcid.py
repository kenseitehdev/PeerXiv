from urllib.parse import parse_qs, urlparse

from accounts.models import Account
from accounts.orcid import OrcidIdentity, normalize_orcid
from peerxiv.extensions import db


def configure_orcid(app, identity):
    app.config.update(
        ORCID_ENABLED=True,
        ORCID_CLIENT_ID="APP-TEST",
        ORCID_CLIENT_SECRET="test-secret",
        ORCID_AUTHORIZE_URL="https://sandbox.orcid.org/oauth/authorize",
        ORCID_TOKEN_URL="https://sandbox.orcid.org/oauth/token",
        ORCID_REDIRECT_URI="http://localhost/api/v1/accounts/orcid/callback",
        ORCID_TOKEN_EXCHANGER=lambda **_kwargs: identity,
    )


def start_state(client, mode):
    response = client.get(f"/api/v1/accounts/orcid/start?mode={mode}")
    assert response.status_code == 200
    url = response.get_json()["authorization_url"]
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "sandbox.orcid.org"
    assert query["scope"] == ["/authenticate"]
    assert query["redirect_uri"] == ["http://localhost/api/v1/accounts/orcid/callback"]
    return query["state"][0]


def test_orcid_link_then_login_uses_verified_server_identity(app, client):
    identity = OrcidIdentity("0000-0002-1825-0097", "Jay Kumar")
    configure_orcid(app, identity)

    state = start_state(client, "link")
    linked = client.get(
        f"/api/v1/accounts/orcid/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert linked.status_code == 302
    assert "orcid=linked" in linked.location
    account = client.get("/api/v1/accounts/me").get_json()["user"]
    assert account["orcid"]["id"] == identity.identifier
    assert account["orcid"]["verified_at"]

    assert client.post("/api/v1/accounts/logout").status_code == 204
    state = start_state(client, "login")
    signed_in = client.get(
        f"/api/v1/accounts/orcid/callback?code=another-code&state={state}",
        follow_redirects=False,
    )
    assert "orcid=signed-in" in signed_in.location
    assert client.get("/api/v1/accounts/me").get_json()["authenticated"] is True


def test_orcid_login_never_bypasses_registration_or_invitation(app):
    configure_orcid(app, OrcidIdentity("0000-0001-5109-3700", "Unknown Researcher"))
    candidate = app.test_client()
    state = start_state(candidate, "login")
    response = candidate.get(
        f"/api/v1/accounts/orcid/callback?code=test-code&state={state}",
        follow_redirects=False,
    )
    assert "orcid=unlinked" in response.location
    assert candidate.get("/api/v1/accounts/me").get_json()["authenticated"] is False
    with app.app_context():
        assert db.session.query(Account).count() == 0


def test_orcid_state_conflict_and_unlink_are_enforced(app, client):
    configure_orcid(app, OrcidIdentity("0000-0002-1825-0097", "Jay Kumar"))
    assert client.get(
        "/api/v1/accounts/orcid/callback?code=test-code&state=attacker-state",
        follow_redirects=False,
    ).location.endswith("?orcid=error&reason=state#profile")

    state = start_state(client, "link")
    client.get(f"/api/v1/accounts/orcid/callback?code=test-code&state={state}")
    removed = client.delete("/api/v1/accounts/orcid")
    assert removed.status_code == 204
    assert client.get("/api/v1/accounts/me").get_json()["user"]["orcid"] is None


def test_orcid_checksum_normalization():
    assert normalize_orcid("0000000218250097") == "0000-0002-1825-0097"
