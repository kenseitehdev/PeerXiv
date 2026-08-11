import pytest

from peerxiv import create_app
from peerxiv.extensions import db, socketio


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        "testing",
        {
            "SECRET_KEY": "peerxiv-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "MANUSCRIPT_STORAGE_ROOT": str(tmp_path / "manuscripts"),
        },
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    test_client = app.test_client()
    response = test_client.post(
        "/api/v1/accounts/register",
        json={
            "email": "jay@example.com",
            "password": "correct-horse-battery-staple",
            "display_name": "Jay Kumar",
            "role": "Independent Researcher",
        },
    )
    assert response.status_code == 201
    test_client.environ_base["HTTP_X_CSRF_TOKEN"] = response.get_json()["csrf_token"]
    return test_client


@pytest.fixture()
def anonymous_client(app):
    return app.test_client()


@pytest.fixture()
def socket_client(app):
    client = socketio.test_client(app, namespace="/social")
    yield client
    if client.is_connected("/social"):
        client.disconnect(namespace="/social")
