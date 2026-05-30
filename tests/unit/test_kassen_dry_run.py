"""Tests for Kassen update dry-run traceability."""

from typing import Any, cast
from unittest.mock import MagicMock, patch

from health_importer.graph.anytype_update_nodes import update_kassen_anytype
from health_importer.graph.nodes import upload_kassen_pdf_node
from health_importer.graph.state import GraphState


def _make_state(
    *,
    dry_run: bool = True,
    has_match: bool = True,
    has_kassen_data: bool = True,
    has_file_id: bool = True,
) -> GraphState:
    state: GraphState = {
        "file_path": "/tmp/kasse.pdf",
        "status": "KASSEN_MATCHED",
        "events": [],
        "anytype_dry_run": dry_run,
        "anytype_config": {
            "space_id": "space-1",
            "collection_name": "Wahlarztrechnungen",
            "collection_id": "col-1",
            "custom_type_name": "Wahlarztrechnung",
            "custom_type_key": "wahlarztrechnung",
            "dry_run": dry_run,
        },
        "file_id": cast(int, 42 if has_file_id else None),
    }
    if has_match:
        state["selected_match"] = {
            "object_id": "obj-123",
            "name": "Test Rechnung",
            "score": 0.95,
            "properties": {"rechnung,_gkk": {"files": ["old-file-1"]}},
        }
    if has_kassen_data:
        state["kassen_ruckmeldung_extraction"] = {
            "patient_first_name": "Max",
            "erstattungsbetrag_eur": "85.00",
        }
    if has_file_id:
        state["kassen_anytype_file_id"] = "kassen-file-456"
    return state


def test_upload_node_dry_run_sets_state() -> None:
    """Dry-run upload node should set kassen_anytype_file_id stub."""
    state = _make_state(dry_run=True)

    with patch("health_importer.anytype.client.build_anytype_client"):
        result = upload_kassen_pdf_node(state)

    assert cast(Any, result).get("kassen_anytype_file_id") == "dry-run-file-id"
    assert result["status"] == "KASSEN_UPLOAD_DRY_RUN"
    event = result["events"][-1]
    assert "Dry-run" in event["message"]


def test_update_node_dry_run_traceability() -> None:
    """Dry-run update node should store anytype_execution with operations."""
    state = _make_state(dry_run=True)

    with patch("health_importer.graph.anytype_update_nodes.build_anytype_client"):
        result = update_kassen_anytype(state)

    assert result["status"] == "KASSEN_UPDATE_DRY_RUN"
    anytype_exec = cast(Any, result).get("anytype_execution")
    assert anytype_exec is not None
    assert anytype_exec["executed"] is False
    assert anytype_exec["dry_run"] is True
    assert anytype_exec["reason"] == "dry_run"
    ops = anytype_exec["operations"]
    assert len(ops) == 3
    assert ops[0]["operation"] == "attach_kassen_pdf"
    assert ops[1]["operation"] == "update_kassen_properties"
    assert ops[2]["operation"] == "update_pkv_eingereicht"
    assert ops[2]["skipped"] is True  # no email_config in test state


def test_update_node_live_traceability() -> None:
    """Live update node should store anytype_execution as executed."""
    state = _make_state(dry_run=False)

    with patch("health_importer.graph.anytype_update_nodes.build_anytype_client") as mock_build:
        client = MagicMock()
        mock_build.return_value = client
        result = update_kassen_anytype(state)

    assert result["status"] == "KASSEN_UPDATED"
    anytype_exec = cast(Any, result).get("anytype_execution")
    assert anytype_exec is not None
    assert anytype_exec["executed"] is True
    assert anytype_exec["dry_run"] is False
    assert anytype_exec["reason"] == "kassen_update"
