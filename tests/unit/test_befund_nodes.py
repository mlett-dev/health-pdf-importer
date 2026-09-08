"""Befund / Patientenbrief flow: match to an invoice object, attach, or error out."""

from pathlib import Path

from health_importer.graph.befund_nodes import (
    decide_befund_match,
    match_befund_invoice,
    move_befund_to_target,
    prepare_befund_target_filename,
)
from health_importer.graph.classification_nodes import route_by_document_type


def _state(**overrides) -> dict:
    state = {
        "events": [],
        "status": "INVOICE_EXTRACTED",
        "invoice_extraction": {
            "document_type": {"value": "befund", "confidence": 0.95},
            "patient_first_name": {"value": "Katharina", "confidence": 0.9},
            "doctor_name": {"value": "Dr. Testarzt Epsilon", "confidence": 0.9},
            "appointment_date": {"value": "2026-09-02", "confidence": 0.9},
        },
    }
    state.update(overrides)
    return state


def test_befund_document_type_gets_its_own_route() -> None:
    result = route_by_document_type(_state())
    assert result["next_route"] == "befund_flow"


def test_honorarnote_still_takes_the_invoice_route() -> None:
    state = _state()
    state["invoice_extraction"]["document_type"]["value"] = "honorarnote"
    assert route_by_document_type(state)["next_route"] == "invoice_flow"


def test_confident_match_routes_to_attach() -> None:
    state = _state(
        matching_confidence=0.95,
        selected_match={"object_id": "obj1", "name": "Rechnung"},
        befund_match_auto_min=0.90,
    )
    result = decide_befund_match(state)
    assert result["next_route"] == "befund_attach"
    assert result["status"] == "BEFUND_AUTO_MATCH"


def test_weak_match_is_not_attached() -> None:
    state = _state(
        matching_confidence=0.72,
        selected_match={"object_id": "obj1", "name": "Rechnung"},
        befund_match_auto_min=0.90,
    )
    result = decide_befund_match(state)
    assert result["next_route"] == "befund_no_match"
    assert result["ok"] is False


def test_no_candidate_at_all_is_not_attached() -> None:
    result = decide_befund_match(_state(matching_confidence=0.0, selected_match=None))
    assert result["next_route"] == "befund_no_match"


def test_missing_patient_short_circuits_the_search() -> None:
    state = _state()
    state["invoice_extraction"]["patient_first_name"] = {"value": None, "confidence": 0.0}
    result = match_befund_invoice(state)
    assert result["status"] == "BEFUND_NO_MATCH"
    assert result["selected_match"] is None


def test_unmatched_befund_goes_to_the_error_folder(tmp_path: Path) -> None:
    # The invoice creates the Anytype object, so a Befund arriving first has
    # nothing to attach to; the error folder keeps it re-runnable.
    pdf = tmp_path / "brief.pdf"
    pdf.write_bytes(b"pdf")
    done, error = tmp_path / "done", tmp_path / "error"
    result = move_befund_to_target(
        _state(
            file_path=str(pdf),
            status="BEFUND_NO_MATCH",
            ok=False,
            done_folder=str(done),
            error_folder=str(error),
        )
    )
    assert Path(result["file_path"]).parent == error
    assert not (done / "brief.pdf").exists()


def test_attached_befund_goes_to_the_done_folder(tmp_path: Path) -> None:
    pdf = tmp_path / "brief.pdf"
    pdf.write_bytes(b"pdf")
    done, error = tmp_path / "done", tmp_path / "error"
    result = move_befund_to_target(
        _state(
            file_path=str(pdf),
            status="BEFUND_ATTACHED",
            done_folder=str(done),
            error_folder=str(error),
        )
    )
    assert Path(result["file_path"]).parent == done


def test_target_filename_follows_the_invoice_convention() -> None:
    state = _state(
        befund_file_naming={
            "enabled": True,
            "pattern": "{date}_{doctor_last_name}_{patient}_befund.pdf",
            "date_format": "%Y_%m_%d",
        },
        anytype_config={"patients": [{"name": "Kathi", "aliases": ["Katharina"]}]},
    )
    result = prepare_befund_target_filename(state)
    assert result["target_filename"] == "2026_09_02_Epsilon_Kathi_befund.pdf"
