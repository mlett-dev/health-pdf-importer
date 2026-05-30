"""Test Kassenrückmeldung validation with fixture data."""

import json
from decimal import Decimal
from pathlib import Path

from health_importer.ai.schemas import ExtractedField, KassenRuckmeldungExtraction
from health_importer.workflow.validation import validate_kassen_ruckmeldung

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "expected_json"


def _load_extraction(name: str) -> KassenRuckmeldungExtraction:
    path = FIXTURE_DIR / f"kassen_ruckmeldung_{name}.json"
    with open(path) as f:
        return KassenRuckmeldungExtraction.model_validate(json.load(f))


def test_positiv_max_passes_validation() -> None:
    extraction = _load_extraction("positiv_max")
    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Max", "Anna"),
        required_confidence_min=0.8,
    )
    assert result.ok is True
    assert result.kassen is not None
    assert result.kassen.patient_first_name == "Max"
    assert result.kassen.aufwendungsbetrag_eur is None
    assert result.kassen.erstattungsbetrag_eur == Decimal("85.00")
    assert result.kassen.aktenzeichen == "TEST-AZ-0001"


def test_positiv_anna_passes_validation() -> None:
    extraction = _load_extraction("positiv_anna")
    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Max", "Anna"),
        required_confidence_min=0.8,
    )
    assert result.ok is True
    assert result.kassen is not None
    assert result.kassen.patient_first_name == "Anna"
    assert result.kassen.aufwendungsbetrag_eur is None
    assert result.kassen.aktenzeichen is None


def test_unsicher_passes_validation() -> None:
    extraction = _load_extraction("unsicher")
    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Max", "Anna"),
        required_confidence_min=0.8,
    )
    assert result.ok is True
    assert result.kassen is not None
    assert result.kassen.aufwendungsbetrag_eur == Decimal("200.00")
    assert result.kassen.erstattungsbetrag_eur == Decimal("170.00")


def test_rejects_unknown_patient() -> None:
    extraction = _load_extraction("positiv_max")
    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Anna",),
        required_confidence_min=0.8,
    )
    assert result.ok is False
    assert "patient_first_name_not_allowed:Max" in result.errors


def test_rejects_zero_amount() -> None:
    extraction = _load_extraction("positiv_max")
    extraction.erstattungsbetrag_eur = ExtractedField(value=0, confidence=0.95, evidence="test")
    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=("Max", "Anna"),
        required_confidence_min=0.8,
    )
    assert result.ok is False
    assert "erstattungsbetrag_eur_not_positive" in result.errors
