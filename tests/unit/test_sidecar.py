import json
from datetime import date
from decimal import Decimal

from health_importer.ai.schemas import InvoiceExtraction
from health_importer.workflow.routing import RouteAction, RoutingDecision
from health_importer.workflow.sidecar import (
    build_kassen_done_sidecar,
    build_pkv_done_sidecar,
    build_sidecar_payload,
    should_write_sidecar,
    sidecar_path_for,
    write_sidecar,
    write_sidecar_if_policy,
)
from health_importer.workflow.validation import (
    ValidatedInvoice,
    ValidationResult,
)


def test_sidecar_path_uses_import_json_suffix(tmp_path) -> None:
    assert sidecar_path_for(tmp_path / "invoice.pdf") == tmp_path / "invoice.import.json"


def test_should_write_sidecar_respects_policy() -> None:
    assert (
        should_write_sidecar(
            write_sidecar_json=True,
            sidecar_policy="always",
            target_is_review_or_error=False,
        )
        is True
    )
    assert (
        should_write_sidecar(
            write_sidecar_json=True,
            sidecar_policy="review_error",
            target_is_review_or_error=False,
        )
        is False
    )
    assert (
        should_write_sidecar(
            write_sidecar_json=True,
            sidecar_policy="review_error",
            target_is_review_or_error=True,
        )
        is True
    )
    assert (
        should_write_sidecar(
            write_sidecar_json=False,
            sidecar_policy="always",
            target_is_review_or_error=True,
        )
        is False
    )


def test_write_sidecar_if_policy_returns_none_when_blocked(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_text("pdf", encoding="utf-8")
    result = write_sidecar_if_policy(
        pdf_path,
        {"data": "test"},
        write_sidecar_json=False,
        sidecar_policy="always",
        target_is_review_or_error=False,
    )
    assert result is None


def test_write_sidecar_if_policy_writes_when_allowed(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_text("pdf", encoding="utf-8")
    result = write_sidecar_if_policy(
        pdf_path,
        {"data": "test"},
        write_sidecar_json=True,
        sidecar_policy="always",
        target_is_review_or_error=False,
    )
    assert result is not None
    assert result.exists()


def test_build_kassen_done_sidecar_structure() -> None:
    payload = build_kassen_done_sidecar(
        original_filename="kassen.pdf",
        sha256="abc",
        extraction={"erstattungsbetrag_eur": {"value": 100}},
        matched_invoice={"object_id": "obj1"},
        erstattungsbetrag_eur="100.00",
    )
    assert payload["document_type"] == "krankenkasse_antwort"
    assert payload["suggested_action"] == "auto_matched"
    assert payload["matched_invoice"]["object_id"] == "obj1"


def test_build_pkv_done_sidecar_structure() -> None:
    payload = build_pkv_done_sidecar(
        original_filename="pkv.pdf",
        sha256="def",
        matched_invoice={"object_id": "obj2"},
        status="PKV_DONE",
    )
    assert payload["document_type"] == "pkv_antwort"
    assert payload["status"] == "PKV_DONE"


def test_build_sidecar_payload_keeps_structured_audit_data() -> None:
    payload = build_sidecar_payload(
        original_filename="scan.pdf",
        sha256="abc123",
        extraction_method="embedded_text",
        llm_model="qwen3.6:35b-a3b-q8_0",
        extracted_fields=_extraction(),
        validation=ValidationResult(
            ok=True,
            invoice=ValidatedInvoice(
                patient_first_name="Anna",
                date=date(2026, 5, 8),
                date_source="appointment_date",
                topic="Kontrolle",
                total_amount_eur=Decimal("120.00"),
                doctor_name="Dr. Testarzt",
            ),
            errors=[],
            warnings=["doctor_name_below_confidence_threshold"],
        ),
        routing_decision=RoutingDecision(
            action=RouteAction.CREATE_WITH_REVIEW_STATUS,
            review_reasons=["doctor_name_below_confidence_threshold"],
            warnings=["doctor_name_below_confidence_threshold"],
        ),
        anytype_object_id="obj-1",
    )

    assert payload["original_filename"] == "scan.pdf"
    assert payload["extracted_fields"]["patient_first_name"]["value"] == "Anna"
    assert payload["validation"]["invoice"]["date"] == "2026-05-08"
    assert payload["review_reasons"] == ["doctor_name_below_confidence_threshold"]
    assert payload["anytype_object_id"] == "obj-1"


def test_write_sidecar_serializes_dates_and_decimals(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_text("pdf", encoding="utf-8")
    payload = {
        "date": date(2026, 5, 8),
        "amount": Decimal("120.00"),
    }

    target = write_sidecar(pdf_path, payload)

    assert target == tmp_path / "invoice.import.json"
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "amount": "120.00",
        "date": "2026-05-08",
    }


def _extraction() -> InvoiceExtraction:
    return InvoiceExtraction.model_validate(
        {
            "document_type": _field("honorarnote", "Honorarnote"),
            "patient_first_name": _field("Anna", "Anna"),
            "doctor_name": _field("Dr. Testarzt", "Dr. Testarzt", confidence=0.7),
            "appointment_date": _field("2026-05-08", "08.05.2026"),
            "invoice_date": _field(None, None, confidence=0.0),
            "topic": _field("Kontrolle", "Kontrolle"),
            "total_amount_eur": _field(120.0, "EUR 120,00"),
        }
    )


def test_write_sidecar_if_policy_redacts_sensitive_details(tmp_path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_text("pdf", encoding="utf-8")
    payload = {
        "original_filename": "scan.pdf",
        "events": [
            {
                "node": "extract",
                "status": "DONE",
                "message": "Extracted",
                "details": {"raw_prompt": "secret prompt", "ok": True},
            }
        ],
        "pdf_text": {"pages": [{"text": "secret"}]},
    }
    result = write_sidecar_if_policy(
        pdf_path,
        payload,
        write_sidecar_json=True,
        sidecar_policy="always",
        target_is_review_or_error=False,
    )
    assert result is not None
    written = json.loads(result.read_text(encoding="utf-8"))
    assert "pdf_text" not in written
    assert written["events"][0]["details"] == {"ok": True}
    assert "raw_prompt" not in written["events"][0]["details"]


def _field(value, evidence, *, confidence=0.9):
    return {"value": value, "confidence": confidence, "evidence": evidence, "page": 1}
