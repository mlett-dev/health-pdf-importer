"""Tests for Pkv-Antwort matching logic."""

from datetime import date
from typing import cast
from unittest.mock import MagicMock

from health_importer.anytype.client import AnytypeObjectRef
from health_importer.anytype.pkv_matching import (
    PkvMatchCandidate,
    _compute_pkv_score,
    has_pkv_strong_match_signal,
    score_pkv_candidates,
)


def _config():
    mock = MagicMock()
    mock.patient_tag_property_id = "test-patient-tag-id"
    mock.amount_property_id = "test-amount-id"
    mock.date_property_id = "test-date-id"
    mock.attachment_property_id = "test-attachment-id"
    return mock


def test_compute_pkv_score_patient_match_only() -> None:
    """Patient match alone is not enough for auto-update."""
    props = {
        "test-patient-tag-id": {"multi_select": ["Max"]},
    }
    score, reasons = _compute_pkv_score(props, "Max", None, None, None, _config())
    assert score < 0.9
    assert any("patient_exact" in r for r in reasons)
    assert has_pkv_strong_match_signal(reasons) is False


def test_compute_pkv_score_patient_mismatch() -> None:
    """Patient mismatch gives 0.0 score."""
    props = {
        "test-patient-tag-id": {"multi_select": ["Anna"]},
    }
    score, reasons = _compute_pkv_score(props, "Max", None, None, None, _config())
    assert score == 0.0
    assert any("patient_mismatch" in r for r in reasons)


def test_compute_pkv_score_with_termin_close() -> None:
    """Patient + close treatment date gives high score."""
    props = {
        "test-patient-tag-id": {"multi_select": ["Max"]},
        "test-date-id": {"date": "2024-03-10"},
    }
    betreffender_termin = date(2024, 3, 10)
    score, reasons = _compute_pkv_score(props, "Max", None, betreffender_termin, None, _config())
    assert score > 0.9
    assert any("termin_close" in r for r in reasons)
    assert has_pkv_strong_match_signal(reasons) is True


def test_compute_pkv_score_with_aufwendungsbetrag() -> None:
    props = {
        "test-patient-tag-id": {"multi_select": ["Max"]},
        "test-amount-id": {"value": "120.50"},
    }
    score, reasons = _compute_pkv_score(props, "Max", "120.50", None, None, _config())
    assert score > 0.9
    assert any("aufwendungsbetrag_exact" in r for r in reasons)
    assert has_pkv_strong_match_signal(reasons) is True


def test_compute_pkv_score_with_rechnungsnummer() -> None:
    """Exact rechnungsnummer match boosts score significantly."""
    props = {
        "test-patient-tag-id": {"multi_select": ["Max"]},
        "rechnungsnummer": {"text": "R-2024-001"},
    }
    score, reasons = _compute_pkv_score(props, "Max", None, None, "R-2024-001", _config())
    assert score == 1.0
    assert any("rechnungsnummer_exact" in r for r in reasons)


def test_score_pkv_candidates_sorts_descending() -> None:
    """Candidates should be sorted by descending score."""
    obj1 = MagicMock()
    obj1.id = "obj-1"
    obj1.name = "Invoice A"

    obj2 = MagicMock()
    obj2.id = "obj-2"
    obj2.name = "Invoice B"

    candidates = [obj1, obj2]
    object_properties = {
        "obj-1": {"test-patient-tag-id": {"multi_select": ["Max"]}},
        "obj-2": {"test-patient-tag-id": {"multi_select": ["Anna"]}},
    }

    scored = score_pkv_candidates(
        cast(list[AnytypeObjectRef], candidates),
        "Max",
        None,
        None,
        None,
        object_properties,
        _config(),
    )
    assert len(scored) == 2
    assert scored[0].object_ref == obj1
    assert scored[0].score > scored[1].score
    assert scored[1].object_ref == obj2
    assert scored[1].score == 0.0


def test_pkv_match_candidate_dataclass() -> None:
    """PkvMatchCandidate holds all expected fields."""
    obj_ref = MagicMock()
    candidate = PkvMatchCandidate(
        object_ref=obj_ref,
        score=0.95,
        match_reasons=["patient_exact:Max"],
        invoice_file_id="file-123",
        properties={"key": "value"},
    )
    assert candidate.score == 0.95
    assert candidate.invoice_file_id == "file-123"
