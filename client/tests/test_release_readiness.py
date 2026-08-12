import runpy
from pathlib import Path

import pytest
from sqlalchemy import text

from peerxiv import create_app
from peerxiv.extensions import db


def test_gunicorn_bind_can_be_restricted_to_loopback(monkeypatch):
    monkeypatch.setenv("PEERXIV_GUNICORN_BIND", "127.0.0.1:8123")
    config = runpy.run_path(str(Path(__file__).parents[1] / "gunicorn.conf.py"))

    assert config["bind"] == "127.0.0.1:8123"


def test_production_rejects_unsafe_defaults():
    with pytest.raises(RuntimeError, match="Unsafe PeerXiv production configuration"):
        create_app("production")


def test_render_hostname_is_accepted_as_a_production_trusted_host(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "peerxiv-alpha.onrender.com")
    from peerxiv.settings import _trusted_hosts

    assert _trusted_hosts() == ("peerxiv-alpha.onrender.com",)


def test_production_headers_trusted_hosts_and_readiness(tmp_path):
    application = create_app(
        "production",
        {
            "TESTING": True,
            "SECRET_KEY": "a-production-secret-that-is-longer-than-32-characters",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "ALLOW_SQLITE_PRODUCTION": True,
            "TRUSTED_HOSTS": ["peerxiv.example"],
            "REGISTRATION_MODE": "disabled",
            "MALWARE_SCAN_REQUIRED": False,
            "FRONTEND_ORIGINS": None,
            "SOCKETIO_MESSAGE_QUEUE": None,
            "RATELIMIT_ENABLED": False,
            "MANUSCRIPT_STORAGE_ROOT": str(tmp_path / "manuscripts"),
        },
    )
    with application.app_context():
        db.create_all()
        assert db.session.scalar(text("PRAGMA foreign_keys")) == 1

    client = application.test_client()
    ready = client.get("/api/v1/ready", base_url="https://peerxiv.example")
    assert ready.status_code == 200
    assert ready.get_json()["database"] == "ready"
    assert ready.headers["Cache-Control"] == "no-store"
    assert ready.headers["X-Content-Type-Options"] == "nosniff"
    assert ready.headers["X-Frame-Options"] == "DENY"
    assert ready.headers["Strict-Transport-Security"].startswith("max-age=31536000")
    assert "default-src 'self'" in ready.headers["Content-Security-Policy"]

    bootstrap = client.get("/api/v1/bootstrap", base_url="https://peerxiv.example")
    assert "demo_data" not in bootstrap.get_json()

    rejected_host = client.get("/api/v1/health", base_url="https://attacker.example")
    assert rejected_host.status_code == 400
    assert rejected_host.get_json()["error"]["code"] == "bad_request"


def test_validation_errors_do_not_reflect_secret_inputs(anonymous_client):
    secret = "do-not-reflect-this-password-" * 12
    response = anonymous_client.post(
        "/api/v1/accounts/register",
        json={
            "email": "release@example.com",
            "password": secret,
            "display_name": "Release Tester",
            "role": "Researcher",
        },
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"
    assert secret.encode() not in response.data
    assert all("input" not in detail for detail in response.get_json()["error"]["details"])


def test_json_request_limit_returns_json_error(app):
    app.config["MAX_JSON_CONTENT_LENGTH"] = 256
    response = app.test_client().post(
        "/api/v1/discovery/classify",
        json={
            "title": "Oversized classifier input",
            "abstract": "evidence " * 100,
        },
    )
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "request_too_large"


def test_readiness_fails_when_configured_redis_is_unavailable(app):
    app.config["REDIS_URL"] = "redis://127.0.0.1:1/0"
    response = app.test_client().get("/api/v1/ready")
    assert response.status_code == 503
    assert response.get_json()["ok"] is False
    assert response.get_json()["dependencies"]["database"] == "ready"


def test_readiness_fails_when_configured_malware_scanner_is_unavailable(app):
    app.config.update(CLAMAV_HOST="127.0.0.1", CLAMAV_PORT=1, CLAMAV_TIMEOUT=0.1)
    response = app.test_client().get("/api/v1/ready")
    assert response.status_code == 503
    assert response.get_json()["ok"] is False


def test_login_rate_limit_is_enforced(tmp_path):
    application = create_app(
        "testing",
        {
            "RATELIMIT_ENABLED": True,
            "RATELIMIT_STORAGE_URI": "memory://",
            "RATELIMIT_KEY_PREFIX": "peerxiv-release-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "MANUSCRIPT_STORAGE_ROOT": str(tmp_path / "manuscripts"),
        },
    )
    with application.app_context():
        db.create_all()
    client = application.test_client()
    client.environ_base["REMOTE_ADDR"] = "192.0.2.44"
    responses = [
        client.post(
            "/api/v1/accounts/login",
            json={"email": "missing@example.com", "password": "wrong"},
        )
        for _ in range(11)
    ]
    assert all(response.status_code == 401 for response in responses[:10])
    assert responses[-1].status_code == 429
    assert responses[-1].get_json()["error"]["code"] == "rate_limit_exceeded"
