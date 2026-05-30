from typing import cast

from health_importer.anytype.client import AnytypeClient, AnytypeObjectRef
from health_importer.anytype.doctor_matching import (
    DoctorMatchStatus,
    load_doctor_candidates,
    match_doctor,
    normalize_doctor_name,
)


def test_normalize_doctor_name_removes_titles_and_umlauts() -> None:
    assert normalize_doctor_name("Ordination Dr. Testarzt Eins") == "testarzt eins"


def test_match_doctor_accepts_normalized_exact_match() -> None:
    result = match_doctor("Dr. Testarzt Eins", _doctors("Testarzt Eins", "Testarzt Zwei"))

    assert result.status is DoctorMatchStatus.MATCHED
    assert result.doctor is not None
    assert result.doctor.name == "Testarzt Eins"
    assert result.score == 100.0
    assert result.should_set_relation is True


def test_match_doctor_accepts_clear_fuzzy_match() -> None:
    result = match_doctor("Testarzt Ein", _doctors("Testarzt Eins", "Testarzt Zwei"))

    assert result.status is DoctorMatchStatus.MATCHED
    assert result.doctor is not None
    assert result.doctor.name == "Testarzt Eins"
    assert result.score >= 92.0


def test_match_doctor_sends_uncertain_match_to_review() -> None:
    result = match_doctor("Testarzt Alfa", _doctors("Testarzt Alpha", "Testarzt Gamma"))

    assert result.status is DoctorMatchStatus.REVIEW
    assert result.doctor is None
    assert result.review_reason == "doctor_match_below_confidence_threshold"


def test_match_doctor_does_not_link_unknown_doctor() -> None:
    result = match_doctor("Completely Unknown", _doctors("Testarzt Eins", "Testarzt Zwei"))

    assert result.status is DoctorMatchStatus.NO_MATCH
    assert result.doctor is None
    assert result.review_reason == "doctor_match_not_found"


def test_match_doctor_sends_ambiguous_match_to_review() -> None:
    result = match_doctor("Testarzt Ambig", _doctors("Testarzt Ambig A", "Testarzt Ambig B"))

    assert result.status is DoctorMatchStatus.REVIEW
    assert result.doctor is None
    assert result.review_reason == "doctor_match_ambiguous"


def test_load_doctor_candidates_uses_arzt_type() -> None:
    class Client:
        def __init__(self) -> None:
            self.type_name = ""
            self.query = "not-called"

        def search_object_by_type(self, type_name: str, query: str):
            self.type_name = type_name
            self.query = query
            return _doctors("Testarzt Eins")

    client = Client()

    assert load_doctor_candidates(cast(AnytypeClient, client))[0].name == "Testarzt Eins"
    assert client.type_name == "arzt"
    assert client.query == ""


def _doctors(*names: str) -> list[AnytypeObjectRef]:
    return [
        AnytypeObjectRef(id=f"doctor-{index}", name=name, type_key="arzt")
        for index, name in enumerate(names, start=1)
    ]
