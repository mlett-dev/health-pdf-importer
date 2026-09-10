"""Tests for Kassen matching logic including doctor name resolution."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from health_importer.anytype.kassen_matching import (
    _compute_match_score,
    get_resolved_doctor_name,
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


def test_resolved_doctor_name_is_read_from_the_resolved_key() -> None:
    props = {"__resolved_doctor_name__": "Testarzt Alpha"}
    assert get_resolved_doctor_name(props) == "Testarzt Alpha"


def test_unresolved_doctor_name_is_none_not_some_other_property() -> None:
    """The predecessor scanned every property and returned the first `name` it
    found -- a property label like "GKK eingereicht", never a doctor."""
    props = {"test-gkk-id": {"name": "GKK eingereicht", "value": True}}
    assert get_resolved_doctor_name(props) is None


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


def test_score_match_candidates_ignores_rechnungsnummer_when_not_configured() -> None:
    obj_ref = MagicMock()
    obj_ref.id = "inv-1"
    obj_ref.name = "Augenuntersuchung"

    object_properties = {
        "inv-1": {
            "test-patient-tag-id": {"value": [{"name": "Anna"}]},
            "test-date-id": {"value": "2026-03-25T00:00:00Z"},
            "test-amount-id": {"value": 200},
            "__resolved_doctor_name__": "Testarzt Alpha",
            "some-title": {"text": "Augenuntersuchung"},
        },
    }

    kassen = ValidatedKassenRuckmeldung(
        patient_first_name="Anna",
        doctor_name="Dr. Testarzt Alpha",
        bescheids_datum=date(2026, 4, 15),
        aufwendungsbetrag_eur=Decimal("200.00"),
        erstattungsbetrag_eur=Decimal("31.59"),
        rechnungsnummer="R-2026-001",
        aktenzeichen=None,
        betreffender_termin=date(2026, 3, 25),
    )

    mock_config = MagicMock()
    mock_config.patient_tag_property_id = "test-patient-tag-id"
    mock_config.amount_property_id = "test-amount-id"
    mock_config.date_property_id = "test-date-id"
    mock_config.attachment_property_id = "rechnung,_gkk"

    scored = score_match_candidates([obj_ref], kassen, object_properties, mock_config)

    assert scored[0].score == 1.0
    assert "rechnungsnummer_not_configured" in scored[0].match_reasons
    assert "rechnungsnummer_mismatch" not in scored[0].match_reasons


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


def _oegk_invoice_props() -> dict:
    """An invoice object as Anytype returns it: no aktenzeichen property at all."""
    return {
        "test-patient-tag-id": {
            "format": "multi_select",
            "name": "Patient",
            "value": [{"name": "Nora"}],
        },
        "test-date-id": {"format": "date", "name": "Termin", "value": "2026-06-12T00:00:00Z"},
        "test-amount-id": {"format": "number", "name": "Betrag (€)", "value": 160},
        "test-gkk-id": {"format": "checkbox", "name": "GKK eingereicht", "value": True},
        "__resolved_doctor_name__": "Testarzt Zeta",
    }


def _oegk_kassen(**overrides) -> ValidatedKassenRuckmeldung:
    base = dict(
        patient_first_name="Nora",
        doctor_name="Dr. Testarzt Zeta",
        bescheids_datum=date(2026, 7, 3),
        aufwendungsbetrag_eur=Decimal("160"),
        erstattungsbetrag_eur=Decimal("63.05"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=date(2026, 6, 12),
    )
    return ValidatedKassenRuckmeldung(**{**base, **overrides})


def _score(kassen: ValidatedKassenRuckmeldung) -> tuple[float, list[str]]:
    return _compute_match_score(
        _oegk_invoice_props(), kassen, "test-date-id", "test-amount-id", "test-patient-tag-id"
    )


def test_unconfigured_aktenzeichen_does_not_count_against_the_match() -> None:
    # OeGK prints "Unser Zeichen", the Wahlarztrechnung type has no matching
    # property, and the invoice cannot answer. Scoring it 0 at weight 1.5 pushed
    # a perfect match from 1.0 down to 0.7 -- below auto_match_min, so the
    # response went to review. Same treatment 9c6483a gave Rechnungsnummer.
    score, reasons = _score(_oegk_kassen(aktenzeichen="6286 07 03 26"))

    assert "aktenzeichen_not_configured" in reasons
    assert score == 1.0


def test_configured_aktenzeichen_still_has_to_match() -> None:
    props = _oegk_invoice_props()
    props["aktenzeichen"] = {"value": "ANDERES-AZ"}
    score, reasons = _compute_match_score(
        props,
        _oegk_kassen(aktenzeichen="6286 07 03 26"),
        "test-date-id",
        "test-amount-id",
        "test-patient-tag-id",
    )

    assert "aktenzeichen_mismatch" in reasons
    assert score < 1.0


def test_aktenzeichen_is_read_from_its_own_property_only() -> None:
    # The scanning helper returned the "GKK eingereicht" label here and compared
    # that against the Aktenzeichen from the response.
    props = _oegk_invoice_props()
    props["aktenzeichen"] = {"value": "6286 07 03 26"}
    score, reasons = _compute_match_score(
        props,
        _oegk_kassen(aktenzeichen="6286 07 03 26"),
        "test-date-id",
        "test-amount-id",
        "test-patient-tag-id",
    )

    assert "aktenzeichen_exact:6286 07 03 26" in reasons
    assert score == 1.0


def test_unresolved_doctor_link_scores_missing_not_a_random_property() -> None:
    props = _oegk_invoice_props()
    del props["__resolved_doctor_name__"]
    score, reasons = _compute_match_score(
        props, _oegk_kassen(), "test-date-id", "test-amount-id", "test-patient-tag-id"
    )

    assert "doctor_missing_in_invoice" in reasons
    assert score < 1.0
