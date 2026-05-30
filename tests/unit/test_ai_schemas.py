import pytest
from pydantic import ValidationError

from health_importer.ai.schemas import DocumentType, InvoiceExtraction


def test_valid_invoice_extraction_accepts_required_fields() -> None:
    extraction = InvoiceExtraction.model_validate(
        {
            "document_type": _field("honorarnote", "Honorarnote"),
            "patient_first_name": _field("Max", "Patientin Max"),
            "doctor_name": _field("Dr. Testarzt", "Ordination Dr. Testarzt"),
            "appointment_date": _field("2026-05-08", "Behandlung am 08.05.2026"),
            "invoice_date": _field(None, None),
            "topic": _field("Organscreening", "Organscreening"),
            "total_amount_eur": _field(230.0, "Gesamtbetrag EUR 230,00"),
            "warnings": [],
            "missing_fields": [],
        }
    )

    assert extraction.document_type.value == DocumentType.HONORARNOTE
    assert extraction.workflow_required_missing_fields() == []
    assert extraction.is_ready_for_code_validation() is True


def test_missing_values_are_null_and_reported_by_required_helper() -> None:
    extraction = InvoiceExtraction.model_validate(
        {
            "document_type": _field("sonstiges", "unklar"),
            "patient_first_name": _field(None, None),
            "doctor_name": _field(None, None),
            "appointment_date": _field(None, None),
            "invoice_date": _field(None, None),
            "topic": _field(None, None),
            "total_amount_eur": _field(None, None),
        }
    )

    assert extraction.workflow_required_missing_fields() == [
        "patient_first_name",
        "appointment_date_or_invoice_date",
        "topic",
        "total_amount_eur",
    ]
    assert extraction.is_ready_for_code_validation() is False


def test_evidence_is_required_when_value_is_set() -> None:
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate(
            {
                "document_type": _field("honorarnote", "Honorarnote"),
                "patient_first_name": _field("Max", None),
                "doctor_name": _field(None, None),
                "appointment_date": _field(None, None),
                "invoice_date": _field("2026-05-09", "Rechnungsdatum 09.05.2026"),
                "topic": _field("Kontrolle", "Kontrolle"),
                "total_amount_eur": _field(120.0, "EUR 120,00"),
            }
        )


def test_invalid_document_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate(
            {
                "document_type": _field("rechnung", "Rechnung"),
                "patient_first_name": _field(None, None),
                "doctor_name": _field(None, None),
                "appointment_date": _field(None, None),
                "invoice_date": _field(None, None),
                "topic": _field(None, None),
                "total_amount_eur": _field(None, None),
            }
        )


def _field(value, evidence):
    return {"value": value, "confidence": 0.8, "evidence": evidence, "page": 1}
