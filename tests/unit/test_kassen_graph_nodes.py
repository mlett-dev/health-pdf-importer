"""Regression tests for uncovered Kassen graph nodes."""

from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

from health_importer.anytype.client import AnytypeOperationError
from health_importer.graph.anytype_update_nodes import update_kassen_anytype
from health_importer.graph.nodes import (
    decide_kassen_match,
    extract_kassen_ruckmeldung,
    match_kassen_invoice,
)
from health_importer.graph.state import GraphState


def _anytype_cfg():
    return {
        "space_id": "sp-1",
        "collection_name": "Wahlarztrechnung",
        "collection_id": "col-1",
        "custom_type_name": "Wahlarztrechnung",
        "custom_type_key": "type-1",
        "dry_run": False,
        "api_url": "http://localhost:8080",
        "app_key": "test-key",
        "pkv_property_id": "prop-pkv-amount",
        "pkv_eingereicht_property_id": "prop-pkv-submitted",
    }


def test_match_kassen_invoice_no_validation_data() -> None:
    """Regression: match_kassen_invoice must fail gracefully without validated data."""
    state = cast(GraphState, {"validation": {}, "events": []})
    result = match_kassen_invoice(state)
    assert result["status"] == "KASSEN_MATCHING_FAILED"
    assert "No validated kassen data" in result["events"][0]["message"]


def test_match_kassen_invoice_no_candidates() -> None:
    """Regression: match_kassen_invoice when find_invoice_candidates returns empty."""
    state = cast(
        GraphState,
        {
            "validation": {
                "kassen": {
                    "patient_first_name": "Anna",
                    "doctor_name": "Dr. Testarzt F",
                    "bescheids_datum": "2026-03-25",
                    "aufwendungsbetrag_eur": None,
                    "erstattungsbetrag_eur": 100.0,
                    "rechnungsnummer": None,
                    "aktenzeichen": None,
                    "betreffender_termin": None,
                    "warnings": [],
                }
            },
            "anytype_config": _anytype_cfg(),
            "events": [],
        },
    )
    with (
        patch("health_importer.graph.kassen_nodes.build_anytype_client"),
        patch("health_importer.anytype.kassen_matching.find_invoice_candidates") as mock_find,
        patch("health_importer.anytype.kassen_matching.score_match_candidates") as mock_score,
    ):
        mock_find.return_value = ([], {})
        mock_score.return_value = []
        result = match_kassen_invoice(state)

    assert result["status"] == "KASSEN_NO_MATCH"
    assert cast(Any, result).get("selected_match") is None
    assert cast(Any, result).get("matching_confidence") == 0.0


def test_decide_kassen_match_unclear() -> None:
    """Regression: decide_kassen_match for unclear confidence."""
    state = cast(
        GraphState,
        {
            "matching_confidence": 0.4,
            "kassen_match_auto_min": 0.90,
            "kassen_match_review_min": 0.60,
            "events": [],
        },
    )
    result = decide_kassen_match(state)
    assert cast(Any, result).get("next_route") == "kassen_review_unclear"
    assert result["status"] == "KASSEN_REVIEW_UNCLEAR"


def test_extract_kassen_ruckmeldung_uses_vision_when_invoice_extraction_used_vision(
    monkeypatch,
) -> None:
    class FakeExtraction:
        def model_dump(self, mode):
            assert mode == "json"
            return {"patient_first_name": {"value": "Anna"}}

    def fail_text_extract(*args, **kwargs):
        raise AssertionError("text extractor should not be used")

    def fake_vision_extract(images, **kwargs):
        assert images == [(1, Path("/tmp/page.png"))]
        return FakeExtraction()

    monkeypatch.setattr(
        "health_importer.graph.kassen_nodes.extract_kassen_ruckmeldung_from_text",
        fail_text_extract,
    )
    monkeypatch.setattr(
        "health_importer.graph.kassen_nodes.extract_kassen_ruckmeldung_from_vision_pages",
        fake_vision_extract,
    )
    state = cast(
        GraphState,
        {
            "pdf_text": {"pages": [{"page_number": 1, "text": ""}]},
            "extraction_method": "vision",
            "vision_pages": [{"page_number": 1, "path": "/tmp/page.png"}],
            "events": [],
        },
    )

    result = extract_kassen_ruckmeldung(state)

    assert result["status"] == "KASSEN_EXTRACTED"
    assert result["events"][-1]["message"] == "Extracted Kassenrückmeldung data using vision."
    extraction = cast(Any, result)["kassen_ruckmeldung_extraction"]
    assert extraction["patient_first_name"]["value"] == "Anna"


def test_update_kassen_anytype_no_match() -> None:
    """Regression: update_kassen_anytype when no match is selected."""
    state = cast(
        GraphState,
        {
            "selected_match": None,
            "anytype_config": _anytype_cfg(),
            "events": [],
        },
    )
    result = update_kassen_anytype(state)
    assert result["status"] == "KASSEN_UPDATE_SKIPPED"


def test_update_kassen_anytype_exception_during_update() -> None:
    """Regression: update_kassen_anytype exception handling during property update."""
    state = cast(
        GraphState,
        {
            "selected_match": {"object_id": "obj-1"},
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": {"value": "Anna"},
                "erstattungsbetrag_eur": {"value": "100.00"},
            },
            "anytype_dry_run": False,
            "anytype_config": _anytype_cfg(),
            "events": [],
        },
    )
    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch("health_importer.graph.anytype_update_nodes.update_kassen_properties") as mock_update,
    ):
        mock_update.side_effect = AnytypeOperationError("Anytype API down")
        result = update_kassen_anytype(state)

    assert result["status"] == "KASSEN_UPDATE_FAILED"
    assert any(
        "Property update failed (AnytypeOperationError)" in event["message"]
        for event in result["events"]
    )


def test_update_kassen_anytype_updates_pkv_eingereicht() -> None:
    """Regression: update_kassen_anytype updates pkv_eingereicht when email enabled."""
    state = cast(
        GraphState,
        {
            "selected_match": {"object_id": "obj-1"},
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": {"value": "Anna"},
                "erstattungsbetrag_eur": {"value": "100.00"},
            },
            "anytype_dry_run": False,
            "anytype_config": _anytype_cfg(),
            "email_config": {"enabled": True},
            "events": [],
        },
    )

    mock_result = MagicMock()
    mock_result.object_id = "obj-1"
    mock_result.value = {"number": 100}

    mock_date_result = MagicMock()
    mock_date_result.object_id = "obj-1"
    mock_date_result.value = {"date": "2026-03-25"}

    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch("health_importer.graph.anytype_update_nodes.update_kassen_properties") as mock_update,
        patch(
            "health_importer.graph.anytype_update_nodes.update_pkv_eingereicht"
        ) as mock_eingereicht,
        patch("health_importer.graph.anytype_update_nodes.attach_kassen_pdf") as mock_attach,
        patch("health_importer.graph.anytype_update_nodes.mark_invoice_done") as mock_done,
    ):
        mock_update.return_value = mock_result
        mock_eingereicht.return_value = mock_date_result
        mock_attach.return_value = None
        mock_done.return_value = None
        result = update_kassen_anytype(state)

    assert result["status"] == "KASSEN_UPDATED"
    # Verify pkv_eingereicht was called
    mock_eingereicht.assert_called_once()
    assert mock_eingereicht.call_args.kwargs["pkv_property_id"] == "prop-pkv-submitted"


def test_update_kassen_anytype_attaches_before_property_updates() -> None:
    state = cast(
        GraphState,
        {
            "selected_match": {"object_id": "obj-1"},
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": {"value": "Anna"},
                "erstattungsbetrag_eur": {"value": "100.00"},
            },
            "kassen_anytype_file_id": "file-1",
            "anytype_dry_run": False,
            "anytype_config": _anytype_cfg(),
            "email_config": {"enabled": True},
            "events": [],
        },
    )
    calls = []
    attach_result = MagicMock()
    attach_result.file_ids = ["file-1"]
    prop_result = MagicMock()
    prop_result.object_id = "obj-1"
    prop_result.value = {"number": 100}
    date_result = MagicMock()
    date_result.object_id = "obj-1"
    date_result.value = {"date": "2026-03-25"}

    def attach_pdf(*args, **kwargs):
        calls.append("attach_kassen_pdf")
        return attach_result

    def update_properties(*args, **kwargs):
        calls.append("update_kassen_properties")
        return prop_result

    def update_pkv(*args, **kwargs):
        calls.append("update_pkv_eingereicht")
        return date_result

    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch("health_importer.graph.anytype_update_nodes.attach_kassen_pdf", attach_pdf),
        patch(
            "health_importer.graph.anytype_update_nodes.update_kassen_properties", update_properties
        ),
        patch("health_importer.graph.anytype_update_nodes.update_pkv_eingereicht", update_pkv),
    ):
        result = update_kassen_anytype(state)

    assert result["status"] == "KASSEN_UPDATED"
    assert calls == ["attach_kassen_pdf", "update_kassen_properties", "update_pkv_eingereicht"]


def test_update_kassen_anytype_does_not_update_properties_when_attachment_fails() -> None:
    state = cast(
        GraphState,
        {
            "selected_match": {"object_id": "obj-1"},
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": {"value": "Anna"},
                "erstattungsbetrag_eur": {"value": "100.00"},
            },
            "kassen_anytype_file_id": "file-1",
            "anytype_dry_run": False,
            "anytype_config": _anytype_cfg(),
            "events": [],
        },
    )

    with (
        patch("health_importer.graph.anytype_update_nodes.build_anytype_client"),
        patch(
            "health_importer.graph.anytype_update_nodes.attach_kassen_pdf",
            side_effect=AnytypeOperationError("boom"),
        ),
        patch("health_importer.graph.anytype_update_nodes.update_kassen_properties") as mock_update,
        patch("health_importer.graph.anytype_update_nodes.update_pkv_eingereicht") as mock_pkv,
    ):
        result = update_kassen_anytype(state)

    assert cast(Any, result).get("ok") is False
    assert result["status"] == "KASSEN_UPDATE_FAILED"
    mock_update.assert_not_called()
    mock_pkv.assert_not_called()
