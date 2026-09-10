"""Generate Pkv email drafts for Kassenrückmeldungen."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from health_importer.email import DraftMessage


def _to_date(value: object) -> date | None:
    """Convert string, dict or date to a date object."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, dict):
        jahr = value.get("jahr", value.get("year"))
        monat = value.get("monat", value.get("month"))
        tag = value.get("tag", value.get("day"))
        if jahr is not None and monat is not None and tag is not None:
            try:
                return date(int(jahr), int(monat), int(tag))
            except Exception:
                return None
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _format_amount_eur(amount: Decimal) -> str:
    return f"{amount:.2f}".replace(".", ",")


def _build_details_block(
    *,
    erstattungsbetrag_eur: Decimal,
    aktenzeichen: str | None,
    rechnungsnummer: str | None,
    betreffender_termin: object,
    invoice_object_name: str | None,
    rechnungsdatum: object = None,
) -> str:
    lines = [f"- Erstattungsbetrag: {_format_amount_eur(erstattungsbetrag_eur)} €"]
    rechnungs_date = _to_date(rechnungsdatum)
    if rechnungs_date:
        lines.append(f"- Rechnungsdatum: {rechnungs_date.strftime('%d.%m.%Y')}")
    if aktenzeichen:
        lines.append(f"- Aktenzeichen: {aktenzeichen}")
    if rechnungsnummer:
        lines.append(f"- Rechnungsnummer: {rechnungsnummer}")
    termin_date = _to_date(betreffender_termin)
    if termin_date:
        lines.append(f"- Betreffender Termin: {termin_date.strftime('%d.%m.%Y')}")
    if invoice_object_name:
        lines.append(f"- zugehörige Rechnung: {invoice_object_name}")
    return "\n".join(lines)


def build_pkv_draft(
    *,
    patient_first_name: str,
    bescheids_datum: object,
    erstattungsbetrag_eur: Decimal,
    rechnungsnummer: str | None,
    aktenzeichen: str | None,
    betreffender_termin: object,
    invoice_object_name: str | None,
    kassen_pdf_path: Path | None,
    invoice_pdf_path: Path | None,
    pkv_recipient: str,
    subject_template: str,
    body_template: str,
    sender_name: str = "",
    sender_policy_number: str = "",
    rechnungsdatum: object = None,
) -> DraftMessage:
    """Build a Pkv submission draft email.

    Subject and body share the same placeholders, except {details}, whose
    multi-line block only makes sense in the body.

    Available placeholders:
        {patient}                -> patient first name
        {date}                   -> bescheids date (dd.mm.yyyy)
        {rechnungsdatum}         -> Honorarnote invoice date (dd.mm.yyyy) or ""
        {details}                -> auto-built details block
        {erstattungsbetrag}      -> refund amount as "123,45"
        {aktenzeichen}           -> file number or ""
        {rechnungsnummer}        -> invoice number or ""
        {termin}                 -> appointment date (dd.mm.yyyy) or ""
        {rechnungsname}          -> invoice object name or ""
        {sender_name}            -> sender name or ""
        {sender_policy_number}   -> policy number or ""
        {recipient}              -> pkv recipient email
    """
    bescheids_date = _to_date(bescheids_datum) or date.today()
    date_str = bescheids_date.strftime("%d.%m.%Y")

    details = _build_details_block(
        erstattungsbetrag_eur=erstattungsbetrag_eur,
        aktenzeichen=aktenzeichen,
        rechnungsnummer=rechnungsnummer,
        betreffender_termin=betreffender_termin,
        invoice_object_name=invoice_object_name,
        rechnungsdatum=rechnungsdatum,
    )

    termin_date = _to_date(betreffender_termin)
    rechnungs_date = _to_date(rechnungsdatum)
    placeholders = {
        "patient": patient_first_name,
        "date": date_str,
        "rechnungsdatum": rechnungs_date.strftime("%d.%m.%Y") if rechnungs_date else "",
        "erstattungsbetrag": _format_amount_eur(erstattungsbetrag_eur),
        "aktenzeichen": aktenzeichen or "",
        "rechnungsnummer": rechnungsnummer or "",
        "termin": termin_date.strftime("%d.%m.%Y") if termin_date else "",
        "rechnungsname": invoice_object_name or "",
        "sender_name": sender_name,
        "sender_policy_number": sender_policy_number,
        "recipient": pkv_recipient,
    }

    # Without a Rechnungsdatum the subject would end in the separator the
    # template put in front of it, so trim that off again.
    subject = subject_template.format(**placeholders).strip(" \t\u2014-\u2013|")
    body = body_template.format(details=details, **placeholders)

    attachments: list[Path] = []
    if kassen_pdf_path and kassen_pdf_path.exists():
        attachments.append(kassen_pdf_path)
    if invoice_pdf_path and invoice_pdf_path.exists():
        attachments.append(invoice_pdf_path)

    return DraftMessage(
        to=pkv_recipient,
        subject=subject,
        body_text=body,
        attachments=attachments,
    )
