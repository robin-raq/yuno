"""Extract the first JSON object from agent prose, fenced blocks, or raw JSON."""
from __future__ import annotations

import json
import re
from typing import Iterator


class JsonExtractError(ValueError):
    """Raised when text does not contain a parseable JSON object."""


_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_object(text: str) -> dict:
    """Return the first JSON object found in *text*.

  Handles raw JSON, markdown fenced blocks, and prose wrapping a balanced
  ``{...}`` object. Raises :class:`JsonExtractError` when no object can be
  extracted or the parsed value is not a JSON object.
    """
    if not text or not text.strip():
        raise JsonExtractError("empty input")

    stripped = text.strip()

    for candidate in _candidate_fragments(stripped):
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
        raise JsonExtractError(f"expected JSON object, got {type(value).__name__}")

    raise JsonExtractError("no JSON object found in text")


def _candidate_fragments(text: str) -> Iterator[str]:
    yield text
    for block in _FENCE_RE.findall(text):
        fragment = block.strip()
        if fragment:
            yield fragment
    yield from _balanced_object_fragments(text)


def _balanced_object_fragments(text: str) -> Iterator[str]:
    start = 0
    while True:
        brace = text.find("{", start)
        if brace < 0:
            break
        fragment = _balanced_object_at(text, brace)
        if fragment is not None:
            yield fragment
        start = brace + 1


def _balanced_object_at(text: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escape = False
    quote = ""

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
