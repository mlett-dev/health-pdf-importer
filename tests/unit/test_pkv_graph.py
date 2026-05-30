"""Tests for Pkv-Antwort graph nodes and routing."""

import json
from decimal import Decimal
from typing import Any, cast
from unittest.mock import MagicMock, patch

from health_importer.anytype.client import AnytypeOperationError
from health_importer.graph.anytype_update_nodes import update_pkv_anytype
from health_importer.graph.nodes import (
    decide_pkv_match,
    extract_pkv_antwort,
    match_pkv_invoice,
    move_pkv_to_done,
    upload_pkv_pdf_node,
    validate_pkv_antwort_node,
)
from health_importer.graph.state import GraphState


def test_decide_pkv_match_auto() -> None:
    state = cast(
        GraphState,
        {
            "matching_confidence": 0.95,
            "kassen_match_auto_min": 0.90,
            "selected_match": {"reasons": ["rechnungsnummer_exact:R-1"]},
            "events": [],
        },
    )
    result = decide_pkv_match(state)
    assert cast(Any, result).get("next_route") == "pkv_auto_update"
    assert result["status"] == "PKV_AUTO_MATCH"


def test_decide_pkv_match_review() -> None:
    state = cast(
        GraphState, {"matching_confidence": 0.75, "kassen_match_auto_min": 0.90, "events": []}
    )
    result = decide_pkv_match(state)
    assert cast(Any, result).get("next_route") == "pkv_review_match"
    assert result["status"] == "PKV_REVIEW_MATCH"


def test_decide_pkv_match_patient_only_review() -> None:
    state = cast(
        GraphState,
        {
            "matching_confidence": 0.95,
            "kassen_match_auto_min": 0.90,
            "selected_match": {"reasons": ["patient_exact:Max"]},
            "events": [],
        },
    )
    result = decide_pkv_match(state)
    assert cast(Any, result).get("next_route") == "pkv_review_match"
    assert result["status"] == "PKV_REVIEW_MATCH"


def test_decide_pkv_match_unclear() -> None:
    state = cast(
        GraphState, {"matching_confidence": 0.40, "kassen_match_auto_min": 0.90, "events": []}
    )
    result = decide_pkv_match(state)
    assert cast(Any, result).get("next_route") == "pkv_review_unclear"
    assert result["status"] == "PKV_REVIEW_UNCLEAR"


def test_match_pkv_invoice_no_patient() -> None:
    state = cast(GraphState, {"validation": {}, "events": []})
    result = match_pkv_invoice(state)
    assert result["status"] == "PKV_MATCHING_FAILED"


def test_match_pkv_invoice_manual_correction() -> None:
    state = cast(
        GraphState,
        {
            "correction_overrides": {"pkv_match_object_id": "manual-obj-1"},
            "events": [],
        },
    )
    result = match_pkv_invoice(state)
    assert result["status"] == "PKV_MATCHED_CORRECTED"
    match = cast(Any, result).get("selected_match")
    assert match is not None
    assert match["object_id"] == "manual-obj-1"


def test_update_pkv_anytype_no_match() -> None:
    state = cast(GraphState, {"selected_match": None, "events": []})
    result = update_pkv_anytype(state)
    assert result["status"] == "PKV_UPDATE_SKIPPED"


def test_update_pkv_anytype_no_betrag() -> None:
    state = cast(
        GraphState,
        {
            "selected_match": {"object_id": "obj-1"},
            "invoice_extraction": {},
            "events": [],
        },
    )
    result = update_pkv_anytype(state)
    assert result["status"] == "PKV_UPDATE_SKIPPED"


def test_update_pkv_anytype_requires_uploaded_file_before_property_update() -> None:
    state = cast(
        GraphState,
        {
            "selected_match": {"object_id": "obj-1"},
            "pkv_antwort_extraction": {"erstattungsbetrag_eur": {"value": "42.50"}},
            "anytype_config": {
                "space_id": "space",
                "collection_name": "Invoices",
                "collection_id": "collection",
                "custom_type_name": "Invoice",
                "custom_type_key": "invoice",
            },
            "events": [],
        },
    )

    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch("health_importer.graph.anytype_update_nodes.update_pkv_properties") as mock_update,
        patch("health_importer.graph.anytype_update_nodes.attach_kassen_pdf") as mock_attach,
        patch("health_importer.graph.anytype_update_nodes.mark_invoice_done") as mock_done,
    ):
        result = update_pkv_anytype(state)

    assert cast(Any, result).get("ok") is False
    assert result["status"] == "PKV_UPDATE_SKIPPED"
    mock_update.assert_not_called()
    mock_attach.assert_not_called()
    mock_done.assert_not_called()


def test_move_pkv_to_done(tmp_path) -> None:
    source = tmp_path / "pkv.pdf"
    source.write_text("PDF content")
    done_dir = tmp_path / "done"

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "done_folder": str(done_dir),
            "events": [],
        },
    )
    result = move_pkv_to_done(state)
    assert result["status"] == "DONE"
    assert not source.exists()
    assert (done_dir / "pkv.pdf").exists()


def test_move_pkv_to_error_on_failed_status(tmp_path) -> None:
    source = tmp_path / "pkv.pdf"
    source.write_text("PDF content")
    error_dir = tmp_path / "error"

    state = cast(
        GraphState,
        {
            "file_path": str(source),
            "error_folder": str(error_dir),
            "events": [],
            "ok": False,
            "status": "PKV_UPDATE_FAILED",
            "pkv_antwort_extraction": {"patient_first_name": {"value": "Max"}},
            "selected_match": {"object_id": "obj-1", "name": "Augenuntersuchung"},
        },
    )

    result = move_pkv_to_done(state)

    assert result["status"] == "PKV_ERROR"
    moved_path = error_dir / "pkv.pdf"
    assert moved_path.exists()
    assert not source.exists()
    sidecar = json.loads(moved_path.with_suffix(".import.json").read_text(encoding="utf-8"))
    assert sidecar["document_type"] == "pkv_antwort"
    assert sidecar["status"] == "PKV_UPDATE_FAILED"
    assert sidecar["matched_invoice"]["object_id"] == "obj-1"


def test_upload_pkv_pdf_node_no_file_id() -> None:
    state = cast(GraphState, {"file_path": "/tmp/pkv.pdf", "events": []})
    result = upload_pkv_pdf_node(state)
    assert result["status"] == "PKV_UPLOAD_SKIPPED"


def test_update_pkv_anytype_skips_after_upload_failure() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "ok": False,
            "status": "PKV_UPLOAD_FAILED",
            "selected_match": {"object_id": "obj-1"},
            "pkv_antwort_extraction": {"erstattungsbetrag_eur": {"value": "10.00"}},
        },
    )

    result = update_pkv_anytype(state)

    assert result["status"] == "PKV_UPLOAD_FAILED"
    assert any(event["status"] == "PKV_UPDATE_SKIPPED" for event in result["events"])


def test_update_pkv_anytype_marks_done_after_attachment() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "selected_match": {
                "object_id": "obj-1",
                "properties": {"test-attachment-id": {"files": ["old-file"]}},
            },
            "pkv_antwort_extraction": {"erstattungsbetrag_eur": {"value": "42.50"}},
            "pkv_anytype_file_id": "file-1",
            "anytype_config": {
                "space_id": "space",
                "collection_name": "Invoices",
                "collection_id": "collection",
                "custom_type_name": "Invoice",
                "custom_type_key": "invoice",
                "pkv_property_id": "pkv-amount-prop",
                "done_property_id": "done-prop",
                "attachment_property_id": "test-attachment-id",
            },
        },
    )
    calls = []
    prop_result = MagicMock()
    prop_result.object_id = "obj-1"
    prop_result.value = {"number": 42.5}
    attach_result = MagicMock()
    attach_result.object_id = "obj-1"
    done_result = MagicMock()
    done_result.object_id = "obj-1"

    def update_properties(*args, **kwargs):
        calls.append("update_pkv_properties")
        assert kwargs["erstattungsbetrag_eur"] == Decimal("42.50")
        assert kwargs["pkv_property_id"] == "pkv-amount-prop"
        return prop_result

    def attach_pdf(*args, **kwargs):
        calls.append("attach_kassen_pdf")
        assert kwargs["existing_file_ids"] == ["old-file"]
        return attach_result

    def mark_done(*args, **kwargs):
        calls.append("mark_invoice_done")
        assert kwargs["done_property_id"] == "done-prop"
        return done_result

    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch(
            "health_importer.graph.anytype_update_nodes.update_pkv_properties", update_properties
        ),
        patch("health_importer.graph.anytype_update_nodes.attach_kassen_pdf", attach_pdf),
        patch("health_importer.graph.anytype_update_nodes.mark_invoice_done", mark_done),
    ):
        result = update_pkv_anytype(state)

    assert result.get("ok", True) is True
    assert calls == ["attach_kassen_pdf", "update_pkv_properties", "mark_invoice_done"]
    assert result["status"] == "PKV_UPDATE_DRY_RUN"


def test_update_pkv_anytype_does_not_mark_done_when_attachment_fails() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "selected_match": {"object_id": "obj-1"},
            "pkv_antwort_extraction": {"erstattungsbetrag_eur": {"value": "42.50"}},
            "pkv_anytype_file_id": "file-1",
            "anytype_config": {
                "space_id": "space",
                "collection_name": "Invoices",
                "collection_id": "collection",
                "custom_type_name": "Invoice",
                "custom_type_key": "invoice",
            },
        },
    )
    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch("health_importer.graph.anytype_update_nodes.update_pkv_properties") as mock_update,
        patch(
            "health_importer.graph.anytype_update_nodes.attach_kassen_pdf",
            side_effect=AnytypeOperationError("boom"),
        ),
        patch("health_importer.graph.anytype_update_nodes.mark_invoice_done") as mark_done,
    ):
        result = update_pkv_anytype(state)

    assert cast(Any, result).get("ok") is False
    assert result["status"] == "PKV_UPDATE_FAILED"
    mock_update.assert_not_called()
    mark_done.assert_not_called()


def test_extract_pkv_antwort_node(monkeypatch) -> None:
    class FakeExtraction:
        def model_dump(self, mode):
            assert mode == "json"
            return {"patient_first_name": {"value": "Max"}}

    def fake_extract(*args, **kwargs):
        return FakeExtraction()

    monkeypatch.setattr(
        "health_importer.graph.pkv_nodes.extract_pkv_antwort_from_text", fake_extract
    )
    state = cast(
        GraphState, {"pdf_text": {"pages": [{"page_number": 1, "text": "Pkv"}]}, "events": []}
    )
    result = extract_pkv_antwort(state)
    assert result["status"] == "PKV_EXTRACTED"
    pkv_extraction = cast(Any, result).get("pkv_antwort_extraction")
    assert pkv_extraction is not None
    assert pkv_extraction["patient_first_name"]["value"] == "Max"


def test_validate_pkv_antwort_node_invalid_goes_to_failed() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "allowed_patients": ("Max",),
            "pkv_antwort_extraction": {
                "document_type": {"value": "pkv_antwort", "confidence": 0.95, "evidence": "Pkv"},
                "patient_first_name": {"value": "Max", "confidence": 0.9, "evidence": "Max"},
                "erstattungsbetrag_eur": {"value": None, "confidence": 0.0},
            },
        },
    )
    result = validate_pkv_antwort_node(state)
    assert result["status"] == "PKV_VALIDATION_FAILED"
    validation = cast(Any, result).get("validation")
    assert validation is not None
    assert validation["ok"] is False
