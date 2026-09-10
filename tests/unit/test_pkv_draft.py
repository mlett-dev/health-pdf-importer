"""Tests for build_pkv_draft template placeholders and body generation."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from health_importer.email.pkv_draft import build_pkv_draft


def test_default_body_template() -> None:
    """Default body contains hardcoded greeting and patient name."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("123.45"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Einreichung — {patient} — {date}",
        body_template=(
            "Sehr geehrte Damen und Herren,\n\n"
            "hiermit reiche ich die Wahlarztrechnung für {patient} ein.\n\n"
            "{details}\n\n"
            "Mit freundlichen Grüßen,\n\n"
        ),
    )
    assert "Anna" in draft.body_text
    assert "Sehr geehrte Damen und Herren," in draft.body_text
    assert "Mit freundlichen Grüßen," in draft.body_text
    assert "123,45 €" in draft.body_text


def test_custom_body_with_sender_placeholders() -> None:
    """Custom body template uses sender_name and sender_policy_number."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("150.00"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Test — {patient}",
        body_template=(
            "Sehr geehrtes Pkv Team,\n\n"
            "ich ersuche um Rückerstattung.\n\n"
            "{details}\n\n"
            "Vielen Dank im Voraus.\n\n"
            "Mit freundlichen Grüßen,\n"
            "{sender_name}\n"
            "Polizzennummer: {sender_policy_number}\n"
        ),
        sender_name="Max Mustermann",
        sender_policy_number="2015123456KV",
    )
    assert "Sehr geehrtes Pkv Team," in draft.body_text
    assert "Max Mustermann" in draft.body_text
    assert "Polizzennummer: 2015123456KV" in draft.body_text
    assert "150,00 €" in draft.body_text
    assert draft.subject == "Test — Anna"


def test_details_placeholder_with_optional_fields() -> None:
    """Details block includes optional fields when present."""
    draft = build_pkv_draft(
        patient_first_name="Max",
        bescheids_datum=date(2026, 4, 15),
        erstattungsbetrag_eur=Decimal("200"),
        rechnungsnummer="R-2026-001",
        aktenzeichen="A12345",
        betreffender_termin="2026-04-10",
        invoice_object_name="Rechnung Dr. Testarzt F",
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="{patient} — {date}",
        body_template="{details}",
    )
    assert "- Erstattungsbetrag: 200,00 €" in draft.body_text
    assert "- Aktenzeichen: A12345" in draft.body_text
    assert "- Rechnungsnummer: R-2026-001" in draft.body_text
    assert "- Betreffender Termin: 10.04.2026" in draft.body_text
    assert "- zugehörige Rechnung: Rechnung Dr. Testarzt F" in draft.body_text


def test_missing_optional_fields_are_empty_in_body() -> None:
    """When optional fields are None, individual placeholders are empty strings."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-05-01",
        erstattungsbetrag_eur=Decimal("50.00"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Test",
        body_template="{aktenzeichen}|{rechnungsnummer}|{termin}|{rechnungsname}",
    )
    assert draft.body_text == "|||"


def test_individual_placeholders_without_details() -> None:
    """Body can use individual placeholders instead of {details}."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-06-20",
        erstattungsbetrag_eur=Decimal("99.99"),
        rechnungsnummer="RN-001",
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="service@example.invalid",
        subject_template="Test",
        body_template="Betrag: {erstattungsbetrag}; Rechnung: {rechnungsnummer}; Empfänger: {recipient}",
        sender_name="",
        sender_policy_number="",
    )
    assert "Betrag: 99,99" in draft.body_text
    assert "Rechnung: RN-001" in draft.body_text
    assert "Empfänger: service@example.invalid" in draft.body_text


def test_attachments_from_existing_paths(tmp_path: Path) -> None:
    """Attachments are included when PDF paths exist."""
    kassen_pdf = tmp_path / "kasse.pdf"
    kassen_pdf.write_text("pdf")
    invoice_pdf = tmp_path / "invoice.pdf"
    invoice_pdf.write_text("pdf")

    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("100"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=kassen_pdf,
        invoice_pdf_path=invoice_pdf,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Test",
        body_template="Body",
    )
    assert len(draft.attachments) == 2
    assert kassen_pdf in draft.attachments
    assert invoice_pdf in draft.attachments


def test_missing_pdf_paths_ignored() -> None:
    """Non-existing PDF paths are not added as attachments."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("100"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=Path("/nonexistent/kasse.pdf"),
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Test",
        body_template="Body",
    )
    assert draft.attachments == []


def test_rechnungsdatum_in_subject_and_body() -> None:
    """The Honorarnote date distinguishes drafts that are otherwise identical."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("123.45"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Rückerstattung der Arztkosten — Honorarnote vom {rechnungsdatum}",
        body_template=(
            "Sehr geehrtes Muki Team,\n\n"
            "ich ersuche um Rückerstattung gemäß beiliegender Honorarnote "
            "vom {rechnungsdatum}.\n\n{details}\n"
        ),
        rechnungsdatum="2026-02-11",
    )
    assert draft.subject == "Rückerstattung der Arztkosten — Honorarnote vom 11.02.2026"
    assert "Honorarnote vom 11.02.2026." in draft.body_text
    assert "- Rechnungsdatum: 11.02.2026" in draft.body_text


def test_missing_rechnungsdatum_leaves_no_dangling_separator() -> None:
    """Without an invoice date the subject must not end in its separator."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("123.45"),
        rechnungsnummer=None,
        aktenzeichen=None,
        betreffender_termin=None,
        invoice_object_name=None,
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="Rückerstattung der Arztkosten — {rechnungsdatum}",
        body_template="{details}\n",
    )
    assert draft.subject == "Rückerstattung der Arztkosten"
    assert "Rechnungsdatum" not in draft.body_text


def test_subject_accepts_the_full_placeholder_set() -> None:
    """Subject and body share placeholders, so a subject may use any of them."""
    draft = build_pkv_draft(
        patient_first_name="Anna",
        bescheids_datum="2026-03-25",
        erstattungsbetrag_eur=Decimal("123.45"),
        rechnungsnummer="R-9",
        aktenzeichen="AZ-1",
        betreffender_termin=date(2026, 1, 7),
        invoice_object_name="2026_02_11_Testarzt_Anna",
        kassen_pdf_path=None,
        invoice_pdf_path=None,
        pkv_recipient="pkv-service@example.invalid",
        subject_template="{patient} {rechnungsnummer} {aktenzeichen} {termin} {rechnungsname}",
        body_template="{details}\n",
    )
    assert draft.subject == "Anna R-9 AZ-1 07.01.2026 2026_02_11_Testarzt_Anna"
