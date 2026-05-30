from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from health_importer.graph.state import GraphEvent

# Keys that must never appear in sidecar details.
_BLOCKED_DETAIL_KEYS = frozenset({
    "raw_prompt",
    "raw_response",
    "full_pdf_text",
    "ocr_text",
    "vision_page_base64",
})

# Top-level keys that must never appear in sidecar payloads.
_BLOCKED_TOP_LEVEL_KEYS = frozenset({
    "pdf_text",
    "ocr_text",
    "vision_pages",
})


def redact_event_for_sidecar(event: GraphEvent) -> GraphEvent:
    """Return a shallow copy with sensitive details stripped."""
    result = dict(event)
    details = result.get("details")
    if not isinstance(details, dict):
        return result  # type: ignore[return-value]

    redacted = {k: v for k, v in details.items() if k not in _BLOCKED_DETAIL_KEYS}
    if len(redacted) != len(details):
        result["details"] = redacted
    return result  # type: ignore[return-value]


def redact_events_for_sidecar(
    events: list[GraphEvent],
) -> list[GraphEvent]:
    return [redact_event_for_sidecar(ev) for ev in events]


def redact_payload_for_sidecar(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact a sidecar payload before JSON serialization."""
    result = dict(payload)
    if "events" in result:
        result["events"] = redact_events_for_sidecar(result["events"])
    for key in _BLOCKED_TOP_LEVEL_KEYS:
        result.pop(key, None)
    return result
