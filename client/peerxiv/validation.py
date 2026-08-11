from __future__ import annotations

import re
import math
import unicodedata
from typing import Any


_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\r\n]+")
_ALL_WHITESPACE = re.compile(r"\s+")
_DANGEROUS_FORMAT_CONTROLS = {
    *(chr(value) for value in range(0x202A, 0x202F)),
    *(chr(value) for value in range(0x2066, 0x206A)),
    "\u200b",
    "\u200e",
    "\u200f",
    "\ufeff",
}


def _clean_characters(value: str, *, multiline: bool) -> str:
    normalized = unicodedata.normalize("NFC", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    output: list[str] = []
    for character in normalized:
        if character in _DANGEROUS_FORMAT_CONTROLS:
            continue
        category = unicodedata.category(character)
        if character == "\n" and multiline:
            output.append(character)
        elif character == "\t":
            output.append(" ")
        elif category in {"Cc", "Cs"}:
            output.append(" ")
        else:
            output.append(character)
    return "".join(output)


def clean_single_line(value: Any) -> str:
    """Normalize untrusted labels without damaging scientific Unicode."""

    return _ALL_WHITESPACE.sub(" ", _clean_characters(str(value), multiline=False)).strip()


def clean_multiline(value: Any) -> str:
    """Normalize prose while retaining intentional paragraph boundaries."""

    cleaned = _clean_characters(str(value), multiline=True)
    lines = [_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in cleaned.split("\n")]
    compacted: list[str] = []
    blank = False
    for line in lines:
        if line:
            compacted.append(line)
            blank = False
        elif compacted and not blank:
            compacted.append("")
            blank = True
    return "\n".join(compacted).strip()


def clean_string_list(values: Any, *, casefold: bool = False) -> list[str]:
    if not isinstance(values, list):
        return values
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise ValueError("Text lists may contain strings only")
        value = clean_single_line(raw)
        if not value:
            continue
        if casefold:
            value = value.casefold()
        key = value.casefold()
        if key not in seen:
            cleaned.append(value)
            seen.add(key)
    return cleaned


def clean_json(value: Any, *, depth: int = 0) -> Any:
    """Bound and normalize JSON stored in research-space metadata."""

    if depth > 6:
        raise ValueError("JSON metadata nesting must not exceed six levels")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON metadata numbers must be finite")
        return value
    if isinstance(value, str):
        cleaned = clean_multiline(value)
        if len(cleaned) > 10_000:
            raise ValueError("JSON metadata strings must be at most 10000 characters")
        return cleaned
    if isinstance(value, list):
        if len(value) > 100:
            raise ValueError("JSON metadata lists must contain at most 100 items")
        return [clean_json(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 100:
            raise ValueError("JSON metadata objects must contain at most 100 fields")
        result: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = clean_single_line(raw_key)
            if not key or len(key) > 120:
                raise ValueError("JSON metadata keys must contain 1 to 120 visible characters")
            if key in result:
                raise ValueError("JSON metadata keys must remain unique after normalization")
            result[key] = clean_json(raw_value, depth=depth + 1)
        return result
    raise ValueError("JSON metadata contains an unsupported value")
