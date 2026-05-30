"""Tests for Pkv email draft generation."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from health_importer.email import FileOnlyProvider
from health_importer.email.pkv_draft import build_pkv_draft


def test_build_pkv_draft_basic() -> None:
    draft = build_pkv_draft(
        patient_first_name="Max",
        bescheids_datum=date(2024, 3, 15),
        erstattungsbetrag_eur=Decimal("85.00"),
        rechnungsnummer="R-123",
        aktenzeichen="AZ-456",
        betreffender_termin=date(2024, 3, 1),
        invoice_object_name="Rechnung Max März",
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Einreichung — {patient} — {date}",
        body_template="Sehr geehrte Damen und Herren,\n\n{details}\n\nMit freundlichen Grüßen,\n",
    )
    assert draft.to == "pkv-service@example.invalid"
    assert "Max" in draft.subject
    assert "85,00" in draft.body_text
    assert "R-123" in draft.body_text
    assert "AZ-456" in draft.body_text
    assert "Rechnung Max März" in draft.body_text


def test_build_pkv_draft_no_invoice_match() -> None:
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum=None,
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Einreichung — {patient}",
        body_template="Sehr geehrte Damen und Herren,\n\n{details}\n\nMit freundlichen Grüßen,\n",
    )
    assert "Anna" in draft.subject
    assert "50,00" in draft.body_text
    assert "zugehörige Rechnung" not in draft.body_text


def test_file_only_provider_creates_markdown(tmp_path: Path) -> None:
    provider = FileOnlyProvider(tmp_path)
    draft_path = provider.create_draft(
        build_pkv_draft(
            patient_first_name="Max",
            bescheids_datum=date(2024, 3, 15),
            erstattungsbetrag_eur=Decimal("85.00"),
            rechnungsnummer=None,
            aktenzeichen=None,
            betreffender_termin=None,
            invoice_object_name=None,
            kassen_pdf_path=tmp_path / "kasse.pdf",
            invoice_pdf_path=None,
            pkv_recipient="pkv-service@example.invalid",
            subject_template="Test — {patient}",
            body_template="Sehr geehrte Damen und Herren,\n\n{details}\n\nMit freundlichen Grüßen,\n",
        )
    )
    path = Path(draft_path)
    assert path.exists()
    content = path.read_text()
    assert "E-Mail Entwurf" in content
    assert "pkv-service@example.invalid" in content
    assert "85,00" in content
