"""Minimal HTTPS-only Zenodo records client.

The client deliberately rejects redirects so an Authorization header can never
be forwarded to a different host.  The API surface is small enough to replace
with a fake in tests through ``ZENODO_CLIENT_FACTORY``.

New deposits use Zenodo's current InvenioRDM records API.  The legacy deposit
methods remain only so PeerXiv can publish drafts created by releases before
0.10 without silently abandoning them.
"""

from __future__ import annotations

import http.client
import json
from pathlib import PurePath
from typing import Any
from urllib.parse import quote, urlencode, urlsplit


class ZenodoApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class ZenodoClient:
    def __init__(self, *, base_url: str, token: str, timeout: float = 30.0):
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
            raise ValueError("Zenodo base URL must be an HTTPS origin")
        self._scheme = parsed.scheme
        self._host = parsed.hostname
        self._port = parsed.port
        self._base_path = parsed.path.rstrip("/")
        self._token = token
        self._timeout = timeout

    def _connection(self, host: str, port: int | None = None):
        return http.client.HTTPSConnection(host, port=port, timeout=self._timeout)

    def _decode(self, response: http.client.HTTPResponse) -> Any:
        raw = response.read()
        if response.status < 200 or response.status >= 300:
            message = f"Zenodo returned HTTP {response.status}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                provider_message = str(payload.get("message") or "").strip()
                if provider_message:
                    message = provider_message[:500]
            except (UnicodeError, json.JSONDecodeError, AttributeError):
                pass
            raise ZenodoApiError(message, status=response.status)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ZenodoApiError("Zenodo returned an invalid response") from error

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Any | None = None,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> Any:
        if not path.startswith("/"):
            raise ValueError("Zenodo request paths must be absolute")
        encoded = body
        if payload is not None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            "User-Agent": "PeerXiv/0.10 DOI integration",
        }
        if encoded is not None:
            headers["Content-Type"] = content_type
            headers["Content-Length"] = str(len(encoded))
        connection = self._connection(self._host, self._port)
        try:
            connection.request(method, f"{self._base_path}{path}", body=encoded, headers=headers)
            return self._decode(connection.getresponse())
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            raise ZenodoApiError("Zenodo could not be reached") from error
        finally:
            connection.close()

    def _same_origin_path(self, url: str) -> str:
        parsed = urlsplit(url)
        if (
            parsed.scheme != self._scheme
            or parsed.hostname != self._host
            or parsed.port != self._port
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ZenodoApiError("Zenodo returned an unsafe API location")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path

    def _request_url(
        self,
        method: str,
        url: str,
        *,
        payload: Any | None = None,
        body: bytes | None = None,
        content_type: str = "application/json",
    ) -> Any:
        return self._request(
            method,
            self._same_origin_path(url),
            payload=payload,
            body=body,
            content_type=content_type,
        )

    def verify(self) -> None:
        query = urlencode({"page": 1, "size": 1})
        payload = self._request("GET", f"/api/deposit/depositions?{query}")
        if not isinstance(payload, list):
            raise ZenodoApiError("Zenodo did not validate this access token")

    def create_record(self, draft: dict[str, Any]) -> dict[str, Any]:
        payload = self._request("POST", "/api/records", payload=draft)
        if not isinstance(payload, dict) or not payload.get("id"):
            raise ZenodoApiError("Zenodo did not create a record draft")
        return payload

    def get_record_draft(self, record_id: str) -> dict[str, Any]:
        payload = self._request(
            "GET", f"/api/records/{quote(str(record_id), safe='')}/draft"
        )
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo returned an invalid record draft")
        return payload

    def reserve_record_doi(self, record_id: str) -> dict[str, Any]:
        payload = self._request(
            "POST", f"/api/records/{quote(str(record_id), safe='')}/draft/pids/doi"
        )
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo did not reserve a managed DOI")
        return payload

    def upload_record_file(
        self, files_url: str, filename: str, data: bytes
    ) -> dict[str, Any]:
        safe_name = PurePath(filename).name
        if not safe_name or safe_name in {".", ".."}:
            raise ZenodoApiError("The manuscript filename is invalid")
        initialized = self._request_url(
            "POST", files_url, payload=[{"key": safe_name}]
        )
        entries = (
            initialized.get("entries")
            if isinstance(initialized, dict)
            else initialized
        )
        if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
            raise ZenodoApiError("Zenodo did not initialize the manuscript upload")
        entry = entries[0]
        links = entry.get("links") if isinstance(entry.get("links"), dict) else {}
        content_url = str(links.get("content") or "")
        commit_url = str(links.get("commit") or "")
        if not content_url or not commit_url:
            raise ZenodoApiError("Zenodo returned an invalid manuscript upload")
        uploaded = self._request_url(
            "PUT",
            content_url,
            body=data,
            content_type="application/octet-stream",
        )
        committed = self._request_url("POST", commit_url)
        result = committed if isinstance(committed, dict) and committed else uploaded
        if not isinstance(result, dict):
            raise ZenodoApiError("Zenodo returned an invalid file record")
        return result

    def publish_record(self, record_id: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/api/records/{quote(str(record_id), safe='')}/draft/actions/publish",
        )
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo returned an invalid publication record")
        return payload

    def create_deposition(self) -> dict[str, Any]:
        payload = self._request("POST", "/api/deposit/depositions", payload={})
        if not isinstance(payload, dict) or not payload.get("id"):
            raise ZenodoApiError("Zenodo did not create a deposit draft")
        return payload

    def get_deposition(self, deposition_id: str) -> dict[str, Any]:
        payload = self._request("GET", f"/api/deposit/depositions/{quote(str(deposition_id))}")
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo returned an invalid deposit draft")
        return payload

    def update_metadata(self, deposition_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
        payload = self._request(
            "PUT",
            f"/api/deposit/depositions/{quote(str(deposition_id))}",
            payload={"metadata": metadata},
        )
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo did not accept the DOI metadata")
        return payload

    def upload_file(self, bucket_url: str, filename: str, data: bytes) -> dict[str, Any]:
        parsed = urlsplit(bucket_url)
        if (
            parsed.scheme != self._scheme
            or parsed.hostname != self._host
            or parsed.port != self._port
            or parsed.query
            or parsed.fragment
        ):
            raise ZenodoApiError("Zenodo returned an unsafe upload location")
        safe_name = quote(PurePath(filename).name, safe="")
        path = f"{parsed.path.rstrip('/')}/{safe_name}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
            # Zenodo's bucket endpoint accepts the manuscript as an opaque
            # binary object and requires this media type.
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
            "User-Agent": "PeerXiv/0.10 DOI integration",
        }
        connection = self._connection(self._host, self._port)
        try:
            connection.request("PUT", path, body=data, headers=headers)
            payload = self._decode(connection.getresponse())
        except (OSError, TimeoutError, http.client.HTTPException) as error:
            raise ZenodoApiError("The manuscript could not be uploaded to Zenodo") from error
        finally:
            connection.close()
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo returned an invalid file record")
        return payload

    def publish(self, deposition_id: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            f"/api/deposit/depositions/{quote(str(deposition_id))}/actions/publish",
        )
        if not isinstance(payload, dict):
            raise ZenodoApiError("Zenodo returned an invalid publication record")
        return payload
