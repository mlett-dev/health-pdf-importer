from datetime import date
from decimal import Decimal

import pytest

from health_importer.config import FileNamingConfig
from health_importer.workflow.filenames import (
    generate_invoice_filename,
    generate_unique_invoice_path,
)
from health_importer.workflow.validation import ValidatedInvoice


def test_generate_invoice_filename_uses_configured_pattern() -> None:
    filename = generate_invoice_filename(
        _invoice(topic="Organscreening"),
        FileNamingConfig(
            pattern="{date}_{patient}_{topic}.pdf",
            date_format="%Y_%m_%d",
            max_topic_length=60,
        ),
    )

    assert filename == "2026_05_08_Anna_Organscreening.pdf"


def test_generate_invoice_filename_slugifies_umlauts_and_unsafe_chars() -> None:
    filename = generate_invoice_filename(
        _invoice(patient="Mäx", topic="Organ/Screening: Spezial + Öl"),
        FileNamingConfig(
            pattern="{date}_{patient}_{topic}",
            date_format="%Y_%m_%d",
            max_topic_length=18,
        ),
    )

    assert filename == "2026_05_08_Maex_Organ_Screening_Sp.pdf"


def test_generate_unique_invoice_path_preserves_existing_file(tmp_path) -> None:
    config = FileNamingConfig(
        pattern="{date}_{patient}_{topic}.pdf",
        date_format="%Y_%m_%d",
        max_topic_length=60,
    )
    existing = tmp_path / "2026_05_08_Anna_Kontrolle.pdf"
    existing.write_text("existing", encoding="utf-8")

    destination = generate_unique_invoice_path(_invoice(topic="Kontrolle"), config, tmp_path)

    assert destination == tmp_path / "2026_05_08_Anna_Kontrolle_2.pdf"


def test_generate_invoice_filename_rejects_unknown_pattern_placeholder() -> None:
    with pytest.raises(ValueError, match="foo"):
        generate_invoice_filename(
            _invoice(),
            FileNamingConfig(
                pattern="{date}_{patient}_{foo}.pdf",
                date_format="%Y_%m_%d",
                max_topic_length=60,
            ),
        )


def test_generate_invoice_filename_doctor_placeholders() -> None:
    filename = generate_invoice_filename(
        _invoice(doctor_name="Dr. Testarzt F", total_amount_eur=Decimal("123.45")),
        FileNamingConfig(
            pattern="{date}_{patient}_{doctor}_{doctor_last_name}_{total_amount_eur}.pdf",
            date_format="%Y_%m_%d",
            max_topic_length=60,
        ),
    )
    assert filename == "2026_05_08_Anna_Dr._Testarzt_F_F_123,45.pdf"


def test_generate_invoice_filename_no_doctor_fallback() -> None:
    filename = generate_invoice_filename(
        _invoice(doctor_name=None),
        FileNamingConfig(
            pattern="{date}_{patient}_{doctor}_{doctor_last_name}_{total_amount_eur}.pdf",
            date_format="%Y_%m_%d",
            max_topic_length=60,
        ),
    )
    assert filename == "2026_05_08_Anna_Unbekannt_Unbekannt_120,00.pdf"


def _invoice(
    *,
    patient: str = "Anna",
    topic: str = "Kontrolle",
    doctor_name: str | None = None,
    total_amount_eur: Decimal = Decimal("120.00"),
) -> ValidatedInvoice:
    return ValidatedInvoice(
        patient_first_name=patient,
        date=date(2026, 5, 8),
        date_source="appointment_date",
        topic=topic,
        total_amount_eur=total_amount_eur,
        doctor_name=doctor_name,
    )
