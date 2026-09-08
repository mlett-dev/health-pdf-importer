"""Scoring a Befund against candidate invoice objects."""

from dataclasses import dataclass
from datetime import date

from health_importer.anytype.befund_matching import score_befund_candidates


@dataclass
class _Ref:
    id: str
    name: str


class _Config:
    date_property_id = "date"
    patient_tag_property_id = "patient"
    attachment_property_id = "rechnung,_gkk"


def _invoice_props(*, patient: str, doctor: str | None, day: str | None) -> dict:
    props: dict = {"patient": {"value": [{"name": patient}]}}
    if day:
        props["date"] = {"value": day}
    if doctor:
        props["__resolved_doctor_name__"] = doctor
    return props


def _score(befund: dict, invoice: dict) -> tuple[float, list[str]]:
    ref = _Ref(id="obj1", name="Rechnung")
    scored = score_befund_candidates(
        [ref],
        patient_first_name=befund["patient"],
        doctor_name=befund["doctor"],
        appointment_date=befund["date"],
        object_properties={"obj1": invoice},
        config=_Config(),
    )
    return scored[0].score, scored[0].match_reasons


def test_same_patient_doctor_and_day_scores_top() -> None:
    score, reasons = _score(
        {"patient": "Kathi", "doctor": "Dr. Testarzt Epsilon", "date": date(2026, 9, 2)},
        _invoice_props(patient="Kathi", doctor="Dr. Testarzt Epsilon", day="2026-09-02"),
    )
    assert score == 1.0
    assert "patient_exact:Kathi" in reasons
    assert "date_close:0d" in reasons


def test_different_patient_cannot_reach_the_auto_threshold() -> None:
    score, reasons = _score(
        {"patient": "Kathi", "doctor": "Dr. Testarzt Epsilon", "date": date(2026, 9, 2)},
        _invoice_props(patient="Nora", doctor="Dr. Testarzt Epsilon", day="2026-09-02"),
    )
    assert score < 0.90
    assert any(r.startswith("patient_mismatch") for r in reasons)


def test_date_beyond_tolerance_drops_below_auto_threshold() -> None:
    score, reasons = _score(
        {"patient": "Kathi", "doctor": "Dr. Testarzt Epsilon", "date": date(2026, 9, 2)},
        _invoice_props(patient="Kathi", doctor="Dr. Testarzt Epsilon", day="2026-07-01"),
    )
    assert score < 0.90
    assert any(r.startswith("date_far") for r in reasons)


def test_missing_date_on_the_befund_scores_zero_for_that_criterion() -> None:
    # Not dropped from the average: with three criteria, ignoring an absent one
    # would let patient plus doctor alone reach the auto threshold.
    score, reasons = _score(
        {"patient": "Kathi", "doctor": "Dr. Testarzt Epsilon", "date": None},
        _invoice_props(patient="Kathi", doctor="Dr. Testarzt Epsilon", day="2026-09-02"),
    )
    assert score < 0.90
    assert "date_missing_in_befund" in reasons


def test_candidates_are_sorted_best_first() -> None:
    refs = [_Ref(id="far", name="Alt"), _Ref(id="near", name="Passend")]
    scored = score_befund_candidates(
        refs,
        patient_first_name="Kathi",
        doctor_name="Dr. Testarzt Epsilon",
        appointment_date=date(2026, 9, 2),
        object_properties={
            "far": _invoice_props(patient="Kathi", doctor="Dr. Andere", day="2026-01-01"),
            "near": _invoice_props(patient="Kathi", doctor="Dr. Testarzt Epsilon", day="2026-09-02"),
        },
        config=_Config(),
    )
    assert [c.object_ref.id for c in scored] == ["near", "far"]
