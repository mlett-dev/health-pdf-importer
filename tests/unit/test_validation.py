from decimal import Decimal

from health_importer.ai.schemas import InvoiceExtraction
from health_importer.workflow.validation import (
    normalize_patient_name,
    normalize_topic,
    validate_invoice_extraction,
)


def test_validate_invoice_extraction_accepts_valid_invoice() -> None:
    result = validate_invoice_extraction(
        _extraction(),
        allowed_patients=("Max", "Anna"),
        required_confidence_min=0.8,
    )

    assert result.ok is True
    assert result.errors == []
    assert result.invoice is not None
    assert result.invoice.patient_first_name == "Max"
    assert result.invoice.date.isoformat() == "2026-05-08"
    assert result.invoice.date_source == "appointment_date"
    assert result.invoice.total_amount_eur == Decimal("120.0")


def test_validate_invoice_extraction_rejects_missing_or_low_confidence_fields() -> None:
    extraction = _extraction(patient=None, amount=0, patient_confidence=0.4)

    result = validate_invoice_extraction(
        extraction,
        allowed_patients=("Max",),
        required_confidence_min=0.8,
    )

    assert result.ok is False
    assert "patient_first_name_missing" in result.errors
    assert "total_amount_eur_not_positive" in result.errors


def test_validate_invoice_extraction_rejects_unknown_patient_and_large_amount() -> None:
    result = validate_invoice_extraction(
        _extraction(patient="Alex", amount=9000),
        allowed_patients=("Max",),
        max_amount_eur=Decimal("5000"),
    )

    assert result.ok is False
    assert "patient_first_name_not_allowed:Alex" in result.errors
    assert "total_amount_eur_above_max" in result.errors


def test_invoice_date_is_fallback_when_appointment_missing() -> None:
    result = validate_invoice_extraction(
        _extraction(appointment_date=None, invoice_date="2026-05-09"),
        allowed_patients=("Max",),
    )

    assert result.ok is True
    assert result.invoice is not None
    assert result.invoice.date.isoformat() == "2026-05-09"
    assert result.invoice.date_source == "invoice_date"


def test_validate_invoice_extraction_maps_patient_long_names_to_anytype_tags() -> None:
    result = validate_invoice_extraction(
        _extraction(patient="Maximilian"),
        allowed_patients=("Max",),
        patient_aliases={"maximilian": "Max", "maxi": "Max", "max": "Max"},
    )

    assert result.ok is True
    assert result.invoice is not None
    assert result.invoice.patient_first_name == "Max"


def test_normalize_patient_name_maps_known_aliases() -> None:
    aliases = {
        "annika": "Anna",
        "anni": "Anna",
        "maximilian": "Max",
        "maxi": "Max",
        "max": "Max",
    }
    assert normalize_patient_name("Annika", aliases) == "Anna"
    assert normalize_patient_name("Maximilian", aliases) == "Max"


def test_normalize_topic_removes_unsafe_characters_and_limits_length() -> None:
    assert normalize_topic("  Organ/Screening: Spezial!!!  ", max_length=12) == "Organ Screen"


def _extraction(
    *,
    patient: str | None = "Max",
    amount=120.0,
    patient_confidence=0.9,
    appointment_date: str | None = "2026-05-08",
    invoice_date=None,
) -> InvoiceExtraction:
    return InvoiceExtraction.model_validate(
        {
            "document_type": _field("honorarnote", "Honorarnote"),
            "patient_first_name": _field(patient, "Patient", confidence=patient_confidence),
            "doctor_name": _field("Dr. Testarzt", "Dr. Testarzt"),
            "appointment_date": _field(appointment_date, "08.05.2026"),
            "invoice_date": _field(invoice_date, "09.05.2026" if invoice_date else None),
            "topic": _field("Kontrolle", "Kontrolle"),
            "total_amount_eur": _field(amount, "EUR 120"),
        }
    )


def _field(value, evidence, *, confidence=0.9):
    return {"value": value, "confidence": confidence, "evidence": evidence, "page": 1}
