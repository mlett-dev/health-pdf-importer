"""Tests for Kassen manual corrections in graph nodes."""

from typing import cast

from health_importer.graph.nodes import match_kassen_invoice
from health_importer.graph.state import GraphState


def test_match_kassen_invoice_with_manual_correction() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "validation": {
                "kassen": {
                    "patient_first_name": "Max",
                    "doctor_name": "Dr. Testarzt",
                    "bescheids_datum": None,
                    "aufwendungsbetrag_eur": None,
                    "erstattungsbetrag_eur": "85.00",
                    "rechnungsnummer": None,
                    "aktenzeichen": None,
                    "betreffender_termin": None,
                    "warnings": [],
                }
            },
            "correction_overrides": {
                "kassen_match_object_id": "manual-object-123",
                "kassen_match_object_name": "Rechnung Max März",
            },
        },
    )
    result = match_kassen_invoice(state)
    assert result["status"] == "KASSEN_MATCHED_CORRECTED"
    match = result.get("selected_match")
    assert match is not None
    assert match["object_id"] == "manual-object-123"
    assert match["name"] == "Rechnung Max März"
    assert result.get("matching_confidence") == 1.0


def test_match_kassen_invoice_without_correction() -> None:
    state = cast(
        GraphState,
        {
            "events": [],
            "anytype_config": {
                "space_id": "space_test",
                "collection_name": "test",
                "collection_id": "col_test",
                "custom_type_name": "Rechnung",
                "custom_type_key": "rechnung",
                "app_key": "test",
                "gkk_property_id": "prop_gkk",
                "attachment_property_id": "prop_attach",
            },
            "validation": {
                "kassen": {
                    "patient_first_name": "Max",
                    "doctor_name": "Dr. Testarzt",
                    "bescheids_datum": None,
                    "aufwendungsbetrag_eur": None,
                    "erstattungsbetrag_eur": "85.00",
                    "rechnungsnummer": None,
                    "aktenzeichen": None,
                    "betreffender_termin": None,
                    "warnings": [],
                }
            },
            "correction_overrides": {},
        },
    )
    result = match_kassen_invoice(state)
    assert result["status"] == "KASSEN_NO_MATCH"
