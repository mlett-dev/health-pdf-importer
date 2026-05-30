"""Tests for Kassen matching logic including doctor name resolution."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from health_importer.anytype.kassen_matching import (
    _get_string_prop,
    _resolve_doctor_names,
    find_invoice_candidates,
    score_match_candidates,
)
from health_importer.workflow.validation import ValidatedKassenRuckmeldung


def test_resolve_doctor_names_fetches_via_runner() -> None:
    """_resolve_doctor_names batches object IDs and returns name mapping."""
    mock_runner = MagicMock()
    mock_runner.call_extension.return_value = {
        "objects": [
            {"object": {"id": "doc-1", "name": "Testarzt Alpha"}},
            {"object": {"id": "doc-2", "name": "Testarzt Beta"}},
        ]
    }

    mock_client = MagicMock()
    mock_client.runner = mock_runner

    mock_config = MagicMock()
    mock_config.space_id = "space-1"
    mock_config.doctor_property_id = "test-doctor-id"

    object_properties = {
        "inv-1": {
            "test-doctor-id": {
                "value": ["doc-1", "doc-2"],
            },
        },
    }

    result = _resolve_doctor_names(mock_client, mock_config, object_properties)
    assert result == {"doc-1": "Testarzt Alpha", "doc-2": "Testarzt Beta"}
    mock_runner.call_extension.assert_called_once_with(
        "get-objects-compact-many",
        {
            "space_id": "space-1",
            "object_ids": ["doc-1", "doc-2"],
        },
    )


def test_resolve_doctor_names_without_runner_returns_empty() -> None:
    """If client lacks a runner, return empty mapping gracefully."""
    mock_client = MagicMock(spec=[])
    mock_config = MagicMock()
    result = _resolve_doctor_names(mock_client, mock_config, {})
    assert result == {}


def test_get_string_prop_prefers_resolved_doctor_name() -> None:
    """_get_string_prop returns __resolved_doctor_name__ when present."""
    props = {"__resolved_doctor_name__": "Testarzt Alpha"}
    assert _get_string_prop(props, "doctor_name") == "Testarzt Alpha"


def test_get_string_prop_falls_back_to_regular_props() -> None:
    """Without __resolved_doctor_name__, scans regular properties."""
    props = {"some_key": {"text": "hello"}}
    assert _get_string_prop(props, "doctor_name") == "hello"


def test_score_match_candidates_with_resolved_doctor_name() -> None:
    """When doctor names are resolved, score can reach 1.0."""
    obj_ref = MagicMock()
    obj_ref.id = "inv-1"
    obj_ref.name = "Augenuntersuchung"

    object_properties = {
        "inv-1": {
            "test-patient-tag-id": {"value": [{"name": "Anna"}]},
            "test-date-id": {"value": "2026-03-25T00:00:00Z"},
            "test-amount-id": {"value": 200},
            "__resolved_doctor_name__": "Testarzt Alpha",
        },
    }

    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Anna",
        doctor_name="Dr. Testarzt Alpha",
        bescheids_datum=date(2026, 4, 15),
        aufwendungsbetrag_eur=Decimal("200.00"),
        erstattungsbetrag_eur=Decimal("31.59"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=date(2026, 3, 25),
    )

    mock_config = MagicMock()
    mock_config.patient_tag_property_id = "test-patient-tag-id"
    mock_config.amount_property_id = "test-amount-id"
    mock_config.date_property_id = "test-date-id"
    mock_config.attachment_property_id = "rechnung,_gkk"

    scored = score_match_candidates([obj_ref], kassen, object_properties, mock_config)
    assert len(scored) == 1
    assert scored[0].score == 1.0
    assert any("doctor_fuzzy:1.00" in r for r in scored[0].match_reasons)


def test_find_invoice_candidates_injects_resolved_doctor_names() -> None:
    """find_invoice_candidates resolves doctor names into properties."""
    mock_runner = MagicMock()
    mock_runner.call_extension.return_value = {
        "objects": [
            {"object": {"id": "doc-1", "name": "Testarzt Alpha"}},
        ]
    }

    mock_client = MagicMock()
    mock_client.runner = mock_runner
    ref = MagicMock()
    ref.id = "inv-1"
    ref.name = "Augenuntersuchung"
    ref.properties = {
        "test-patient-tag-id": {"value": [{"name": "Anna"}]},
        "test-doctor-id": {"value": ["doc-1"]},
    }
    mock_client.search_object_by_type.return_value = [ref]

    mock_config = MagicMock()
    mock_config.space_id = "space-1"
    mock_config.custom_type_key = "wahlarztrechnung"
    mock_config.patient_tag_property_id = "test-patient-tag-id"
    mock_config.doctor_property_id = "test-doctor-id"

    candidates, object_properties = find_invoice_candidates(mock_client, "Anna", mock_config)

    assert len(candidates) == 1
    assert object_properties["inv-1"]["__resolved_doctor_name__"] == "Testarzt Alpha"
