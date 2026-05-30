from datetime import date
from decimal import Decimal

from health_importer.state_db import StateDb
from health_importer.workflow.routing import (
    RouteAction,
    decide_next_action,
    store_routing_decision,
)
from health_importer.workflow.text_verification import TextVerificationResult
from health_importer.workflow.validation import ValidationResult


def test_decide_next_action_auto_creates_valid_confident_invoice() -> None:
    decision = decide_next_action(_valid_result())

    assert decision.action is RouteAction.AUTO_CREATE
    assert decision.review_reasons == []
    assert decision.blocking_reasons == []


def test_decide_next_action_creates_with_review_status_for_optional_warnings() -> None:
    decision = decide_next_action(
        _valid_result(warnings=["doctor_name_below_confidence_threshold"])
    )

    assert decision.action is RouteAction.CREATE_WITH_REVIEW_STATUS
    assert decision.review_reasons == ["doctor_name_below_confidence_threshold"]
    assert decision.blocking_reasons == []


def test_decide_next_action_blocks_uncertain_required_fields() -> None:
    decision = decide_next_action(
        _invalid_result(["patient_first_name_below_confidence_threshold"])
    )

    assert decision.action is RouteAction.REVIEW_ONLY
    assert decision.blocking_reasons == ["patient_first_name_below_confidence_threshold"]


def test_decide_next_action_blocks_amount_and_date_text_mismatches() -> None:
    decision = decide_next_action(
        _valid_result(),
        text_verification=TextVerificationResult(
            amount_found=False,
            date_found=False,
            amount_candidates=[Decimal("100")],
            date_candidates=[date(2026, 1, 1)],
            warnings=["amount_not_found_in_text", "date_not_found_in_text"],
        ),
    )

    assert decision.action is RouteAction.REVIEW_ONLY
    assert decision.blocking_reasons == [
        "amount_not_found_in_text",
        "date_not_found_in_text",
    ]


def test_decide_next_action_blocks_amount_and_date_vision_mismatches() -> None:
    decision = decide_next_action(
        _valid_result(),
        text_verification=TextVerificationResult(
            amount_found=False,
            date_found=False,
            warnings=["amount_not_found_in_vision", "date_not_found_in_vision"],
        ),
    )

    assert decision.action is RouteAction.REVIEW_ONLY
    assert decision.blocking_reasons == [
        "amount_not_found_in_vision",
        "date_not_found_in_vision",
    ]


def test_decide_next_action_routes_technical_failures_to_error() -> None:
    decision = decide_next_action(_valid_result(), technical_error="ocr_failed")

    assert decision.action is RouteAction.ERROR
    assert decision.blocking_reasons == ["ocr_failed"]


def test_store_routing_decision_adds_state_db_event(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% test\n")
    db = StateDb(tmp_path / "state.sqlite")
    db.initialize()
    record, _ = db.register_file(pdf_path)

    store_routing_decision(
        db,
        file_id=record.id,
        decision=decide_next_action(_valid_result(warnings=["multiple_amounts_found"])),
    )

    events = db.list_events(record.id)
    assert events[-1]["event_type"] == "routing_decision"
    assert events[-1]["payload"]["action"] == "CREATE_WITH_REVIEW_STATUS"
    assert events[-1]["payload"]["review_reasons"] == ["multiple_amounts_found"]


def _valid_result(*, warnings: list[str] | None = None) -> ValidationResult:
    return ValidationResult(ok=True, invoice=None, errors=[], warnings=warnings or [])


def _invalid_result(errors: list[str]) -> ValidationResult:
    return ValidationResult(ok=False, invoice=None, errors=errors, warnings=[])
