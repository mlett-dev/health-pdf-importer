"""Test that fixture JSONs validate against KassenRuckmeldungExtraction schema."""

import json
from pathlib import Path

from health_importer.ai.schemas import KassenRuckmeldungExtraction

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "expected_json"


def _load_expected(name: str) -> dict:
    path = FIXTURE_DIR / f"kassen_ruckmeldung_{name}.json"
    with open(path) as f:
        return json.load(f)


def test_positiv_max_validates() -> None:
    data = _load_expected("positiv_max")
    result = KassenRuckmeldungExtraction.model_validate(data)
    assert result.patient_first_name.value == "Max"
    assert result.aufwendungsbetrag_eur.value is None
    assert result.erstattungsbetrag_eur.value == 85.00
    assert result.bescheids_datum.value == "2026-05-13"
    assert result.aktenzeichen.value == "TEST-AZ-0001"
    assert result.doctor_name.value == "Dr. med. Testarzt A"


def test_positiv_anna_validates() -> None:
    data = _load_expected("positiv_anna")
    result = KassenRuckmeldungExtraction.model_validate(data)
    assert result.patient_first_name.value == "Anna"
    assert result.aufwendungsbetrag_eur.value is None
    assert result.erstattungsbetrag_eur.value == 120.00
    assert result.aktenzeichen.value is None


def test_unsicher_validates() -> None:
    data = _load_expected("unsicher")
    result = KassenRuckmeldungExtraction.model_validate(data)
    assert result.patient_first_name.value == "Max"
    assert result.aufwendungsbetrag_eur.value == 200.00
    assert result.erstattungsbetrag_eur.value == 170.00
    assert "multiple_amounts_detected" in result.warnings
