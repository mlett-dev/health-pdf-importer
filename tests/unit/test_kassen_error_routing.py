"""Tests for Kassen error routing and safe decimal conversion."""

from decimal import Decimal
from typing import cast

from health_importer.graph.nodes import _safe_decimal, create_pkv_draft
from health_importer.graph.state import GraphState


def test_safe_decimal_from_string() -> None:
    assert _safe_decimal("31.59") == Decimal("31.59")


def test_safe_decimal_from_decimal() -> None:
    assert _safe_decimal(Decimal("31.59")) == Decimal("31.59")


def test_safe_decimal_from_german_comma() -> None:
    assert _safe_decimal("31,59") == Decimal("31.59")


def test_safe_decimal_from_none_raises() -> None:
    try:
        _safe_decimal(None)
    except ValueError as exc:
        assert "None or empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for None")


def test_safe_decimal_from_empty_string_raises() -> None:
    try:
        _safe_decimal("")
    except ValueError as exc:
        assert "None or empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for empty string")


def test_safe_decimal_from_invalid_string_raises() -> None:
    try:
        _safe_decimal("not-a-number")
    except ValueError as exc:
        assert "Cannot convert" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid string")


def test_safe_decimal_from_extracted_field_dict() -> None:
    field = {
        "value": 31.59,
        "confidence": 0.95,
        "evidence": "haben wir Ihnen 31,59 Euro erstattet",
        "page": 1,
    }
    assert _safe_decimal(field) == Decimal("31.59")


def test_safe_decimal_from_extracted_field_dict_with_comma() -> None:
    field = {
        "value": "31,59",
        "confidence": 0.95,
        "evidence": "haben wir Ihnen 31,59 Euro erstattet",
        "page": 1,
    }
    assert _safe_decimal(field) == Decimal("31.59")


def test_safe_decimal_from_extracted_field_dict_none_value_raises() -> None:
    field = {
        "value": None,
        "confidence": 0.0,
    }
    try:
        _safe_decimal(field)
    except ValueError as exc:
        assert "None or empty" in str(exc)
    else:
        raise AssertionError("Expected ValueError for None value in dict")


def test_create_pkv_draft_skips_on_failed_status() -> None:
    state = cast(
        GraphState,
        {
            "file_path": "/tmp/test.pdf",
            "status": "KASSEN_UPDATE_FAILED",
            "ok": False,
            "events": [],
        },
    )
    result = create_pkv_draft(state)
    assert result["status"] == "KASSEN_EMAIL_SKIPPED"
    assert any(
        "Skipped because previous Kassen update failed" in e["message"] for e in result["events"]
    )


def test_create_pkv_draft_skips_on_ok_false() -> None:
    state = cast(
        GraphState,
        {
            "file_path": "/tmp/test.pdf",
            "status": "SOME_OTHER_STATUS",
            "ok": False,
            "events": [],
        },
    )
    result = create_pkv_draft(state)
    assert result["status"] == "KASSEN_EMAIL_SKIPPED"
    assert any(
        "Skipped because previous Kassen update failed" in e["message"] for e in result["events"]
    )
