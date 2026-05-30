"""Tests for observability redaction helpers."""

from __future__ import annotations

from health_importer.graph.state import GraphEvent
from health_importer.observability.redaction import (
    redact_event_for_sidecar,
    redact_events_for_sidecar,
    redact_payload_for_sidecar,
)


def test_redact_event_without_details_returns_unchanged() -> None:
    ev: GraphEvent = {"node": "n", "status": "S", "message": "m"}
    assert redact_event_for_sidecar(ev) == ev


def test_redact_event_strips_blocked_detail_keys() -> None:
    ev: GraphEvent = {
        "node": "n",
        "status": "S",
        "message": "m",
        "details": {
            "raw_prompt": "secret prompt",
            "raw_response": "secret response",
            "ok": True,
            "traceback": "tb",
        },
    }
    result = redact_event_for_sidecar(ev)
    assert "details" in result
    assert result["details"] == {"ok": True, "traceback": "tb"}


def test_redact_event_leaves_non_blocked_details_intact() -> None:
    ev: GraphEvent = {
        "node": "n",
        "status": "S",
        "message": "m",
        "details": {"duration_ms": 120},
    }
    result = redact_event_for_sidecar(ev)
    assert "details" in result
    assert result["details"] == {"duration_ms": 120}


def test_redact_events_for_sidecar_processes_list() -> None:
    events: list[GraphEvent] = [
        {"node": "a", "status": "S", "message": "m", "details": {"raw_prompt": "x"}},
        {"node": "b", "status": "S", "message": "m", "details": {"ok": True}},
    ]
    result = redact_events_for_sidecar(events)
    assert "details" in result[0]
    assert result[0]["details"] == {}
    assert "details" in result[1]
    assert result[1]["details"] == {"ok": True}


def test_redact_payload_strips_top_level_blocked_keys() -> None:
    payload = {
        "original_filename": "x.pdf",
        "pdf_text": {"pages": ["secret"]},
        "ocr_text": {"pages": ["secret"]},
        "vision_pages": [{"base64": "secret"}],
    }
    result = redact_payload_for_sidecar(payload)
    assert "pdf_text" not in result
    assert "ocr_text" not in result
    assert "vision_pages" not in result
    assert result["original_filename"] == "x.pdf"


def test_redact_payload_redacts_events_array() -> None:
    payload = {
        "events": [
            {
                "node": "n",
                "status": "S",
                "message": "m",
                "details": {"raw_prompt": "secret", "ok": True},
            }
        ],
    }
    result = redact_payload_for_sidecar(payload)
    assert "details" in result["events"][0]
    assert result["events"][0]["details"] == {"ok": True}


def test_redact_payload_without_events_is_safe() -> None:
    payload = {"foo": "bar"}
    assert redact_payload_for_sidecar(payload) == {"foo": "bar"}
