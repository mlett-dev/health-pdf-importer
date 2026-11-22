"""Tests for Pkv Sammelbriefe: one letter settling several invoices."""

from datetime import date
from decimal import Decimal
from typing import Any, cast
from unittest.mock import MagicMock, patch

from health_importer.ai.schemas import PkvAntwortExtraction
from health_importer.anytype.client import AnytypeObjectRef, AnytypeOperationError
from health_importer.anytype.kassen_matching import missing_invoice_property_keys
from health_importer.anytype.pkv_sammel_matching import match_sammelbrief_positions
from health_importer.config import PkvFileNamingConfig
from health_importer.graph.build_graph import _pkv_extraction_router
from health_importer.graph.pkv_sammel_nodes import (
    update_pkv_sammel_anytype,
    validate_pkv_sammelbrief_node,
)
from health_importer.graph.state import GraphState
from health_importer.workflow.filenames import generate_pkv_sammel_filename
from health_importer.workflow.pkv_sammelbrief import (
    ValidatedPkvPosition,
    validate_pkv_sammelbrief,
)
from health_importer.workflow.validation import validate_pkv_antwort

ALLOWED = ("Max", "Erika")
ALIASES = {"maximilian": "Max"}


def _field(value: object, evidence: str = "sichtbar") -> dict[str, Any]:
    return {"value": value, "confidence": 0.95, "evidence": evidence, "page": 1}


def _row(patient: str, doctor: str, aufwand: object, termin: str, erstattung: object) -> dict:
    return {
        "patient_first_name": patient,
        "doctor_name": doctor,
        "aufwendungsbetrag_eur": aufwand,
        "betreffender_termin": termin,
        "erstattungsbetrag_eur": erstattung,
        "confidence": 0.95,
        "evidence": f"{doctor} {aufwand} {termin} {erstattung}",
    }


def _sammelbrief(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "document_type": _field("pkv_antwort"),
        "patient_first_name": _field("Maximilian"),
        "erstattungsbetrag_eur": _field(40.0),
        "bescheids_datum": _field("2024-09-14"),
        "positionen": [
            _row("Maximilian", "Dr. Test Eins", 100.0, "2024-09-02", 40.0),
            _row("Erika", "Dr. Test Zwei", 180.0, "2024-06-12", 70.10),
            _row("Erika", "Dr. Test Drei", "130,00", "24.07.2024", "52,40"),
        ],
        "personen_summen": [
            {"patient_first_name": "Maximilian", "gesamt_eur": 40.0},
            {"patient_first_name": "Erika", "gesamt_eur": "122,50"},
        ],
        "auszahlung_eur": _field("162,50"),
    }
    data.update(overrides)
    return data


def _validate(data: dict[str, Any]):
    return validate_pkv_sammelbrief(
        PkvAntwortExtraction.model_validate(data),
        allowed_patients=ALLOWED,
        patient_aliases=ALIASES,
    )


# --- Schema ------------------------------------------------------------------


def test_several_positionen_make_a_sammelbrief() -> None:
    assert PkvAntwortExtraction.model_validate(_sammelbrief()).is_sammelbrief()


def test_single_position_is_not_a_sammelbrief() -> None:
    data = _sammelbrief(
        positionen=[_row("Max", "Dr. Test", 100.0, "2024-09-02", 40.0)],
        personen_summen=[{"patient_first_name": "Max", "gesamt_eur": 40.0}],
    )
    assert not PkvAntwortExtraction.model_validate(data).is_sammelbrief()


def test_two_persons_with_one_row_are_still_a_sammelbrief() -> None:
    """The model dropped a row, but the second person's total gives it away."""
    data = _sammelbrief(
        positionen=[_row("Max", "Dr. Test", 100.0, "2024-09-02", 40.0)],
        personen_summen=[
            {"patient_first_name": "Max", "gesamt_eur": 40.0},
            {"patient_first_name": "Erika", "gesamt_eur": 20.0},
        ],
    )
    assert PkvAntwortExtraction.model_validate(data).is_sammelbrief()


def test_unfilled_placeholder_rows_are_dropped() -> None:
    empty = dict.fromkeys(
        (
            "patient_first_name",
            "doctor_name",
            "aufwendungsbetrag_eur",
            "betreffender_termin",
            "erstattungsbetrag_eur",
        )
    )
    data = _sammelbrief(
        positionen=[_row("Max", "Dr. Test", 100.0, "2024-09-02", 40.0), empty], personen_summen=[]
    )
    extraction = PkvAntwortExtraction.model_validate(data)
    assert len(extraction.positionen) == 1
    assert not extraction.is_sammelbrief()


def test_old_extractions_without_positionen_still_parse() -> None:
    extraction = PkvAntwortExtraction.model_validate(
        {"document_type": _field("pkv_antwort"), "patient_first_name": _field("Max")}
    )
    assert extraction.positionen == []
    assert not extraction.is_sammelbrief()


# --- Validation --------------------------------------------------------------


def test_valid_sammelbrief_adds_up() -> None:
    result = _validate(_sammelbrief())
    assert result.ok, result.errors
    assert [p.patient_first_name for p in result.positionen] == ["Max", "Erika", "Erika"]
    assert result.positionen[2].erstattungsbetrag_eur == Decimal("52.40")
    assert result.positionen[2].betreffender_termin == date(2024, 7, 24)
    assert result.auszahlung_eur == Decimal("162.50")


def test_german_date_is_read_day_first() -> None:
    rows = _sammelbrief()["positionen"]
    rows[0]["betreffender_termin"] = "05.08.2024"
    result = _validate(_sammelbrief(positionen=rows))
    assert result.positionen[0].betreffender_termin == date(2024, 8, 5)


def test_swapped_iso_termin_is_corrected_from_evidence() -> None:
    rows = _sammelbrief()["positionen"]
    rows[0]["betreffender_termin"] = "2024-02-09"
    rows[0]["evidence"] = "Dr. Test Eins 100,00 02.09.2024 40,00"
    result = _validate(_sammelbrief(positionen=rows))
    assert result.ok, result.errors
    assert result.positionen[0].betreffender_termin == date(2024, 9, 2)
    assert any("position_1_termin_taken_from_evidence" in w for w in result.warnings)


def test_auszahlung_mismatch_fails() -> None:
    result = _validate(_sammelbrief(auszahlung_eur=_field("199,99")))
    assert not result.ok
    assert any(e.startswith("sum_mismatch_auszahlung") for e in result.errors)


def test_person_total_mismatch_fails() -> None:
    summen = [
        {"patient_first_name": "Maximilian", "gesamt_eur": 40.0},
        {"patient_first_name": "Erika", "gesamt_eur": 150.0},
    ]
    result = _validate(_sammelbrief(personen_summen=summen, auszahlung_eur=_field("162,50")))
    assert not result.ok
    assert any(e.startswith("sum_mismatch_person:Erika") for e in result.errors)


def test_missing_auszahlung_fails() -> None:
    result = _validate(_sammelbrief(auszahlung_eur={"value": None, "confidence": 0.0}))
    assert not result.ok
    assert "auszahlung_missing" in result.errors


def test_row_without_termin_fails() -> None:
    rows = _sammelbrief()["positionen"]
    rows[1]["betreffender_termin"] = None
    result = _validate(_sammelbrief(positionen=rows))
    assert not result.ok
    assert "position_2_termin_missing_or_invalid" in result.errors


def test_unknown_patient_fails() -> None:
    rows = _sammelbrief()["positionen"]
    rows[0]["patient_first_name"] = "Fremd"
    result = _validate(_sammelbrief(positionen=rows))
    assert "position_1_patient_not_allowed:Fremd" in result.errors


def test_manual_match_correction_sends_sammelbrief_to_review() -> None:
    state = cast(
        GraphState,
        {
            "pkv_antwort_extraction": _sammelbrief(),
            "allowed_patients": ALLOWED,
            "anytype_config": {
                "patients": [{"name": "Max", "tag": "t", "aliases": ["Maximilian"]}]
            },
            "correction_overrides": {"pkv_match_object_id": "obj-1"},
            "events": [],
        },
    )
    result = validate_pkv_sammelbrief_node(state)
    assert result["status"] == "PKV_VALIDATION_FAILED"
    assert (
        "manual_match_correction_unsupported_for_sammelbrief"
        in cast(Any, result.get("validation"))["errors"]
    )


# --- Guard on the single-letter path -----------------------------------------


def _single(**overrides: Any) -> PkvAntwortExtraction:
    data: dict[str, Any] = {
        "document_type": _field("pkv_antwort"),
        "patient_first_name": _field("Max"),
        "erstattungsbetrag_eur": _field(40.0),
    }
    data.update(overrides)
    return PkvAntwortExtraction.model_validate(data)


def test_single_letter_with_matching_auszahlung_passes() -> None:
    result = validate_pkv_antwort(_single(auszahlung_eur=_field("40,00")), allowed_patients=ALLOWED)
    assert result.ok, result.errors


def test_single_letter_whose_auszahlung_covers_more_fails() -> None:
    """The model read only the first row; the Auszahlung still covers all of them."""
    result = validate_pkv_antwort(
        _single(auszahlung_eur=_field("162,50")), allowed_patients=ALLOWED
    )
    assert not result.ok
    assert any(e.startswith("auszahlung_differs_from_erstattung") for e in result.errors)


def test_single_letter_whose_person_total_covers_more_fails() -> None:
    result = validate_pkv_antwort(
        _single(personen_summen=[{"patient_first_name": "Max", "gesamt_eur": 90.0}]),
        allowed_patients=ALLOWED,
    )
    assert not result.ok


def test_single_letter_without_auszahlung_check_fails() -> None:
    result = validate_pkv_antwort(
        _single(warnings=["auszahlung_extraction_failed"]), allowed_patients=ALLOWED
    )
    assert "auszahlung_extraction_failed" in result.errors


def test_extraction_router_splits_single_and_sammel() -> None:
    sammel = cast(GraphState, {"pkv_antwort_extraction": _sammelbrief()})
    single = cast(GraphState, {"pkv_antwort_extraction": _single().model_dump(mode="json")})
    assert _pkv_extraction_router(sammel) == "sammel"
    assert _pkv_extraction_router(single) == "single"


# --- Matching ----------------------------------------------------------------


def _config() -> MagicMock:
    mock = MagicMock()
    mock.patient_tag_property_id = "patient"
    mock.amount_property_id = "betrag"
    mock.date_property_id = "termin"
    mock.attachment_property_id = "anhaenge"
    return mock


def _invoice(object_id: str, patient: str, amount: float, termin: str) -> tuple:
    ref = AnytypeObjectRef(id=object_id, name=f"Rechnung {object_id}", type_key="rechnung")
    props = {
        "patient": {"value": [{"name": patient}]},
        "betrag": {"value": amount},
        "termin": {"value": termin},
    }
    return ref, props


def _position(index: int, patient: str, amount: str, termin: date) -> ValidatedPkvPosition:
    return ValidatedPkvPosition(
        index=index,
        patient_first_name=patient,
        doctor_name=None,
        aufwendungsbetrag_eur=Decimal(amount),
        betreffender_termin=termin,
        erstattungsbetrag_eur=Decimal("10"),
    )


def test_same_amount_invoices_are_told_apart_by_termin() -> None:
    july, july_props = _invoice("july", "Erika", 130, "2024-07-24")
    aug, aug_props = _invoice("aug", "Erika", 130, "2024-08-22")
    matches = match_sammelbrief_positions(
        [_position(1, "Erika", "130", date(2024, 7, 24))],
        {"Erika": [july, aug]},
        {"july": july_props, "aug": aug_props},
        _config(),
        auto_min=0.9,
    )
    assert matches[0].selected is not None
    assert matches[0].selected.object_ref.id == "july"


def test_row_without_close_termin_is_not_auto_matched() -> None:
    far, far_props = _invoice("far", "Erika", 130, "2024-03-01")
    matches = match_sammelbrief_positions(
        [_position(1, "Erika", "130", date(2024, 7, 24))],
        {"Erika": [far]},
        {"far": far_props},
        _config(),
        auto_min=0.9,
    )
    assert matches[0].selected is None
    assert matches[0].review_reason == "top_candidate_lacks:termin_close"


def test_two_rows_cannot_share_one_invoice() -> None:
    only, only_props = _invoice("only", "Erika", 130, "2024-07-24")
    matches = match_sammelbrief_positions(
        [
            _position(1, "Erika", "130", date(2024, 7, 24)),
            _position(2, "Erika", "130", date(2024, 7, 25)),
        ],
        {"Erika": [only]},
        {"only": only_props},
        _config(),
        auto_min=0.8,
    )
    assert all(m.selected is None for m in matches)
    assert {m.review_reason for m in matches} == {"invoice_matched_by_several_positionen"}


# --- Anytype update ----------------------------------------------------------


def _update_state(dry_run: bool) -> GraphState:
    return cast(
        GraphState,
        {
            "pkv_anytype_file_id": "file-muki",
            "anytype_dry_run": dry_run,
            "anytype_config": {
                "attachment_property_id": "anhaenge",
                "pkv_property_id": "muki_eu",
                "done_property_id": "done",
            },
            "pkv_sammel_matches": [
                {
                    "object_id": "obj-1",
                    "name": "Rechnung 1",
                    "existing_file_ids": ["file-rechnung-1"],
                    "position": {"erstattungsbetrag_eur": "70.10"},
                },
                {
                    "object_id": "obj-2",
                    "name": "Rechnung 2",
                    "existing_file_ids": [],
                    "position": {"erstattungsbetrag_eur": "52.40"},
                },
            ],
            "events": [],
        },
    )


def test_update_writes_each_rows_own_erstattung() -> None:
    client = MagicMock()
    with patch("health_importer.graph.pkv_sammel_nodes.build_anytype_client", return_value=client):
        result = update_pkv_sammel_anytype(_update_state(dry_run=False))

    assert result["status"] == "PKV_UPDATED"
    calls = [c.args for c in client.set_property.call_args_list]
    assert ("obj-1", "anhaenge", {"files": ["file-rechnung-1", "file-muki"]}) in calls
    assert ("obj-1", "muki_eu", {"number": 70.10}) in calls
    assert ("obj-2", "muki_eu", {"number": 52.40}) in calls
    assert ("obj-2", "done", {"checkbox": True}) in calls
    assert cast(Any, result).get("pkv_sammel_written") == ["obj-1", "obj-2"]


def test_failed_update_reports_what_was_already_written() -> None:
    client = MagicMock()

    def fail_on_second(object_id: str, *_args: object) -> None:
        if object_id == "obj-2":
            raise AnytypeOperationError("boom")

    client.set_property.side_effect = fail_on_second
    with patch("health_importer.graph.pkv_sammel_nodes.build_anytype_client", return_value=client):
        result = update_pkv_sammel_anytype(_update_state(dry_run=False))

    assert result["status"] == "PKV_UPDATE_FAILED"
    assert result.get("ok") is False
    assert cast(Any, result).get("pkv_sammel_written") == ["obj-1"]
    assert "Already written: ['obj-1']" in result["events"][-1]["message"]


# --- Missing property keys ---------------------------------------------------


def test_missing_property_keys_are_reported() -> None:
    config = _config()
    props = {"a": {"renamed_patient": {}, "termin": {}, "betrag": {}}}
    assert missing_invoice_property_keys(props, config) == ["patient_tag_property_id=patient"]


def test_no_objects_means_nothing_to_report() -> None:
    assert missing_invoice_property_keys({}, _config()) == []


# --- Filename ----------------------------------------------------------------


def test_sammel_filename_uses_configured_pattern() -> None:
    config = PkvFileNamingConfig(pattern="{service_date}_{doctor_last_name}_{patient}_muki.pdf")
    name = generate_pkv_sammel_filename(
        bescheids_datum=date(2024, 9, 14),
        patients=["Max", "Erika", "Erika"],
        auszahlung_eur=Decimal("162.50"),
        config=config,
    )
    assert name == "2024_09_14_Sammelabrechnung_Max_Erika_muki.pdf"


# --- Auszahlung read ---------------------------------------------------------


def test_vision_auszahlung_is_parsed_from_the_copied_sentence() -> None:
    from pathlib import Path

    from health_importer.ai.extractors import extract_pkv_auszahlung_from_vision_pages

    client = MagicMock()
    client.chat_with_images.return_value = (
        "„Der Betrag von EUR 162,50 wird auf das Konto IBAN AT00 überwiesen.“"
    )
    with patch("health_importer.ai.extractors.OllamaVisionClient", return_value=client):
        found = extract_pkv_auszahlung_from_vision_pages(
            [(1, Path("page.png"))], model="m", base_url="http://127.0.0.1", timeout_seconds=1
        )
    assert found.value == "162,50"
    assert found.confidence >= 0.8


def test_vision_auszahlung_without_sentence_is_empty() -> None:
    from pathlib import Path

    from health_importer.ai.extractors import extract_pkv_auszahlung_from_vision_pages

    client = MagicMock()
    client.chat_with_images.return_value = "KEINE"
    with patch("health_importer.ai.extractors.OllamaVisionClient", return_value=client):
        found = extract_pkv_auszahlung_from_vision_pages(
            [(1, Path("page.png"))], model="m", base_url="http://127.0.0.1", timeout_seconds=1
        )
    assert found.value is None
