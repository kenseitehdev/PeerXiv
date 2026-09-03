"""Small, dependency-free ORCID OAuth client.

PeerXiv asks ORCID only to authenticate an iD.  It deliberately does not retain
the returned access token: the public API authentication scope is sufficient
for verified identity and avoids pretending that PeerXiv can update records.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ORCID_PATTERN = re.compile(r"^(\d{4})-(\d{4})-(\d{4})-(\d{3}[\dX])$", re.IGNORECASE)


class OrcidExchangeError(RuntimeError):
    """Raised when ORCID does not return a usable verified identity."""


@dataclass(frozen=True)
class OrcidIdentity:
    identifier: str
    name: str


def normalize_orcid(value: str) -> str:
    compact = re.sub(r"[^\dX]", "", str(value).upper())
    if not re.fullmatch(r"\d{15}[\dX]", compact):
        raise ValueError("Invalid ORCID iD")
    total = 0
    for digit in compact[:15]:
        total = (total + int(digit)) * 2
    result = (12 - (total % 11)) % 11
    expected = "X" if result == 10 else str(result)
    if compact[-1] != expected:
        raise ValueError("Invalid ORCID iD checksum")
    return "-".join((compact[:4], compact[4:8], compact[8:12], compact[12:]))


def authorization_url(*, authorize_url: str, client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "scope": "/authenticate",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return f"{authorize_url}?{query}"


def exchange_code(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
    timeout: float = 10.0,
) -> OrcidIdentity:
    body = urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        }
    ).encode("utf-8")
    request = Request(
        token_url,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "PeerXiv/0.9 ORCID integration",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed configured ORCID host
            payload: dict[str, Any] = json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise OrcidExchangeError("ORCID authentication could not be completed") from error

    if payload.get("error"):
        raise OrcidExchangeError(str(payload.get("error_description") or payload["error"]))
    try:
        identifier = normalize_orcid(str(payload["orcid"]))
    except (KeyError, ValueError) as error:
        raise OrcidExchangeError("ORCID did not return a valid authenticated iD") from error
    name = str(payload.get("name") or identifier).strip()[:160]
    return OrcidIdentity(identifier=identifier, name=name)
