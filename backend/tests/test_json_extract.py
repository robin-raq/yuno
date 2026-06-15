"""P0 — tolerant JSON object extraction from Goose / agent prose output."""
from __future__ import annotations

import json

import pytest

from app.domain.remittance.json_extract import JsonExtractError, extract_json_object


def _brief() -> dict:
    return {
        "transfer_type": "cash_send",
        "amount_usd": 500.0,
        "sender_city": "Austin, TX",
        "sender_country": "US",
        "recipient_country": "Colombia",
        "recipient_city": "Bogotá",
        "send_currency": "USD",
        "receive_currency": "COP",
        "data_source": "fixture",
        "sender_profile": {
            "previously_flagged": False,
            "kyc_verified": True,
            "account_tier": "standard",
        },
        "missing_fields": [],
    }


def test_extract_raw_json_object():
    brief = _brief()
    assert extract_json_object(json.dumps(brief)) == brief


def test_extract_fenced_json_block():
    brief = _brief()
    wrapped = f"Transfer brief:\n```json\n{json.dumps(brief)}\n```\nDone."
    assert extract_json_object(wrapped) == brief


def test_extract_prose_wrapped_json():
    brief = _brief()
    wrapped = (
        "I'll help you research remittance quotes.\n"
        f"{json.dumps(brief)}\n"
        "Let me know if you need more."
    )
    assert extract_json_object(wrapped) == brief


def test_extract_first_balanced_object_when_prose_contains_braces():
    brief = _brief()
    wrapped = f"Notes {{ignored}} before object {json.dumps(brief)} trailing text"
    assert extract_json_object(wrapped) == brief


def test_extract_invalid_json_raises_typed_error():
    with pytest.raises(JsonExtractError):
        extract_json_object("not json at all")


def test_extract_empty_input_raises_typed_error():
    with pytest.raises(JsonExtractError):
        extract_json_object("")


def test_extract_json_array_raises_typed_error():
    with pytest.raises(JsonExtractError):
        extract_json_object("[1, 2, 3]")
