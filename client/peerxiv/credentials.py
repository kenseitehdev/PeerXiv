"""Encryption boundary for user-supplied provider credentials."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class CredentialError(RuntimeError):
    """Raised when an encrypted provider credential cannot be used."""


def encrypt_credential(value: str, key: str) -> str:
    if not value or not key:
        raise CredentialError("Credential encryption is not configured")
    return Fernet(key.encode("ascii")).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str, key: str) -> str:
    if not value or not key:
        raise CredentialError("Credential encryption is not configured")
    try:
        return Fernet(key.encode("ascii")).decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as error:
        raise CredentialError("The stored provider credential could not be decrypted") from error
