import json

import pytest

from accounts.zenodo import ZenodoApiError, ZenodoClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self._raw


def connection_factory(monkeypatch, responses):
    requests = []

    class FakeConnection:
        def __init__(self, host, port=None, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout

        def request(self, method, path, body=None, headers=None):
            requests.append((method, path, body, headers))

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            pass

    monkeypatch.setattr("accounts.zenodo.http.client.HTTPSConnection", FakeConnection)
    return requests


def test_zenodo_client_happy_path_never_places_token_in_url(monkeypatch):
    responses = [
        FakeResponse([]),
        FakeResponse({"id": "abc12", "links": {}}),
        FakeResponse({"id": "abc12", "links": {}}),
        FakeResponse(
            {
                "id": "abc12",
                "pids": {
                    "doi": {
                        "identifier": "10.5072/zenodo.12",
                        "provider": "datacite",
                    }
                },
            },
            status=201,
        ),
        FakeResponse(
            {
                "entries": [
                    {
                        "key": "paper name.pdf",
                        "links": {
                            "content": (
                                "https://sandbox.zenodo.org/api/records/abc12/draft/"
                                "files/paper%20name.pdf/content"
                            ),
                            "commit": (
                                "https://sandbox.zenodo.org/api/records/abc12/draft/"
                                "files/paper%20name.pdf/commit"
                            ),
                        },
                    }
                ]
            },
            status=201,
        ),
        FakeResponse({"key": "paper name.pdf", "size": 4}),
        FakeResponse({"key": "paper name.pdf", "size": 4}),
        FakeResponse(
            {
                "id": "abc12",
                "pids": {
                    "doi": {
                        "identifier": "10.5072/zenodo.12",
                        "provider": "datacite",
                    }
                },
            },
            status=202,
        ),
    ]
    requests = connection_factory(monkeypatch, responses)
    client = ZenodoClient(
        base_url="https://sandbox.zenodo.org", token="top-secret-token", timeout=4
    )

    client.verify()
    assert client.create_record({"metadata": {"title": "Paper"}})["id"] == "abc12"
    assert client.get_record_draft("abc12")["id"] == "abc12"
    assert (
        client.reserve_record_doi("abc12")["pids"]["doi"]["identifier"]
        == "10.5072/zenodo.12"
    )
    assert client.upload_record_file(
        "https://sandbox.zenodo.org/api/records/abc12/draft/files",
        "paper name.pdf",
        b"%PDF",
    )["key"] == "paper name.pdf"
    assert (
        client.publish_record("abc12")["pids"]["doi"]["identifier"]
        == "10.5072/zenodo.12"
    )

    assert all("top-secret-token" not in path for _method, path, _body, _headers in requests)
    assert all(
        request_headers["Authorization"] == "Bearer top-secret-token"
        for _method, _path, _body, request_headers in requests
    )
    assert requests[0][1].startswith("/api/deposit/depositions?")
    assert requests[1][1] == "/api/records"
    assert requests[3][1] == "/api/records/abc12/draft/pids/doi"
    assert requests[5][1].endswith("/paper%20name.pdf/content")
    assert requests[5][3]["Content-Type"] == "application/octet-stream"
    assert requests[6][1].endswith("/paper%20name.pdf/commit")


def test_zenodo_client_rejects_redirects_errors_and_foreign_upload_hosts(monkeypatch):
    responses = [
        FakeResponse({"message": "Invalid access token"}, status=401),
        FakeResponse(b"not-json"),
    ]
    connection_factory(monkeypatch, responses)
    client = ZenodoClient(base_url="https://zenodo.org", token="secret-token-value")

    with pytest.raises(ZenodoApiError, match="Invalid access token") as rejected:
        client.verify()
    assert rejected.value.status == 401

    with pytest.raises(ZenodoApiError, match="invalid response"):
        client.create_record({"metadata": {"title": "Paper"}})

    with pytest.raises(ZenodoApiError, match="unsafe API location"):
        client.upload_record_file("https://attacker.example/upload", "paper.pdf", b"data")

    with pytest.raises(ValueError, match="HTTPS origin"):
        ZenodoClient(base_url="http://zenodo.org", token="secret-token-value")


def test_zenodo_client_wraps_transport_failures(monkeypatch):
    class BrokenConnection:
        def __init__(self, *_args, **_kwargs):
            pass

        def request(self, *_args, **_kwargs):
            raise OSError("network down")

        def close(self):
            pass

    monkeypatch.setattr("accounts.zenodo.http.client.HTTPSConnection", BrokenConnection)
    client = ZenodoClient(base_url="https://sandbox.zenodo.org", token="secret-token-value")
    with pytest.raises(ZenodoApiError, match="could not be reached"):
        client.verify()
