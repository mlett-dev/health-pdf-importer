from __future__ import annotations

from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_NEXT_ROUTE,
    GraphEvent,
    GraphState,
    get_events,
    get_invoice_extraction,
)


def route_by_document_type(state: GraphState) -> GraphState:
    """Route document based on extracted document_type after invoice extraction."""
    extraction = get_invoice_extraction(state) or {}
    doc_type_field = extraction.get("document_type", {})
    doc_type = doc_type_field.get("value", "sonstiges")

    next_state = _copy_state(state)
    if doc_type == "krankenkasse_antwort":
        next_state[STATE_NEXT_ROUTE] = "kassen_flow"
        next_state[STATE_EVENTS].append(
            _event(
                "route_by_document_type", "KASSEN_FLOW", "Document type is krankenkasse_antwort."
            )
        )
    elif doc_type == "befund":
        next_state[STATE_NEXT_ROUTE] = "befund_flow"
        next_state[STATE_EVENTS].append(
            _event("route_by_document_type", "BEFUND_FLOW", "Document type is befund.")
        )
    elif doc_type == "pkv_antwort":
        next_state[STATE_NEXT_ROUTE] = "pkv_flow"
        next_state[STATE_EVENTS].append(
            _event("route_by_document_type", "PKV_FLOW", "Document type is pkv_antwort.")
        )
    else:
        next_state[STATE_NEXT_ROUTE] = "invoice_flow"
        next_state[STATE_EVENTS].append(
            _event("route_by_document_type", "INVOICE_FLOW", f"Document type is {doc_type}.")
        )
    return next_state


def _copy_state(state: GraphState) -> GraphState:
    next_state = dict(state)
    next_state[STATE_EVENTS] = list(get_events(state))
    return next_state  # type: ignore[return-value]


def _event(node: str, status: str, message: str) -> GraphEvent:
    return {"node": node, "status": status, "message": message}
