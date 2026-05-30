from __future__ import annotations

from decimal import Decimal
from typing import Any

from health_importer.config import AnytypeConfig, PatientEntry
from health_importer.graph.state import (
    STATE_ANYTYPE_CONFIG,
    STATE_EVENTS,
    STATE_OCR_TEXT,
    STATE_OK,
    STATE_PDF_TEXT,
    STATE_VALIDATION,
    GraphEvent,
    GraphState,
    get_anytype_dry_run,
    get_events,
)
from health_importer.pdf.quality import join_page_text
from health_importer.workflow.routing import RouteAction, RoutingDecision
from health_importer.workflow.text_verification import TextVerificationResult
from health_importer.workflow.validation import (
    ValidatedInvoice,
    ValidatedPkvAntwort,
    ValidationResult,
)


def safe_decimal(value: object) -> Decimal:
    """Safely convert a value to Decimal, handling ExtractedField dicts, None, empty strings, and German comma format."""
    if isinstance(value, dict):
        value = value.get("value")
    if value is None or value == "":
        raise ValueError("Decimal value is None or empty")
    s = str(value).strip().replace(",", ".")
    try:
        return Decimal(s)
    except Exception as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal: {exc}") from exc


def copy_state(state: GraphState) -> GraphState:
    next_state = dict(state)
    next_state[STATE_EVENTS] = list(get_events(state))
    return next_state  # type: ignore[return-value]


def event(
    node: str,
    status: str,
    message: str,
    *,
    code: str | None = None,
    severity: str = "info",
    file_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> GraphEvent:
    ev: GraphEvent = {"node": node, "status": status, "message": message}
    if code:
        ev["code"] = code
    if severity != "info":
        ev["severity"] = severity
    if file_id is not None:
        ev["file_id"] = file_id
    if details:
        ev["details"] = details
    return ev


def source_text_dict(state: GraphState) -> dict:
    if "ocr_text" in state:
        return state.get(STATE_OCR_TEXT, {})
    return state.get(STATE_PDF_TEXT, {})


def source_text(state: GraphState) -> str:
    return join_page_text(source_text_dict(state))


def validation_to_dict(validation: ValidationResult) -> dict:
    return {
        "ok": validation.ok,
        "invoice": invoice_to_dict(validation.invoice) if validation.invoice else None,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }


def validation_from_state(state: GraphState) -> ValidationResult:
    data = state.get(STATE_VALIDATION, {})
    invoice = data.get("invoice")
    return ValidationResult(
        ok=bool(data[STATE_OK]),
        invoice=invoice_from_dict(invoice) if invoice else None,
        errors=list(data.get("errors", [])),
        warnings=list(data.get("warnings", [])),
    )


def invoice_to_dict(invoice: ValidatedInvoice) -> dict:
    return {
        "patient_first_name": invoice.patient_first_name,
        "date": invoice.date.isoformat(),
        "date_source": invoice.date_source,
        "topic": invoice.topic,
        "total_amount_eur": str(invoice.total_amount_eur),
        "doctor_name": invoice.doctor_name,
        "warnings": invoice.warnings,
    }


def pkv_to_dict(pkv: ValidatedPkvAntwort) -> dict:
    return {
        "patient_first_name": pkv.patient_first_name,
        "bescheids_datum": pkv.bescheids_datum.isoformat() if pkv.bescheids_datum else None,
        "aufwendungsbetrag_eur": (
            str(pkv.aufwendungsbetrag_eur) if pkv.aufwendungsbetrag_eur is not None else None
        ),
        "erstattungsbetrag_eur": str(pkv.erstattungsbetrag_eur),
        "rechnungsnummer": pkv.rechnungsnummer,
        "betreffender_termin": (
            pkv.betreffender_termin.isoformat() if pkv.betreffender_termin else None
        ),
        "warnings": pkv.warnings,
    }


def pkv_from_dict(data: dict) -> ValidatedPkvAntwort:
    from datetime import date

    bescheids_datum = data.get("bescheids_datum")
    betreffender_termin = data.get("betreffender_termin")
    aufwendungsbetrag_eur = data.get("aufwendungsbetrag_eur")
    return ValidatedPkvAntwort(
        patient_first_name=str(data["patient_first_name"]),
        doctor_name=data.get("doctor_name"),
        bescheids_datum=date.fromisoformat(str(bescheids_datum)) if bescheids_datum else None,
        aufwendungsbetrag_eur=(
            Decimal(str(aufwendungsbetrag_eur)) if aufwendungsbetrag_eur is not None else None
        ),
        erstattungsbetrag_eur=Decimal(str(data["erstattungsbetrag_eur"])),
        rechnungsnummer=data.get("rechnungsnummer"),
        betreffender_termin=(
            date.fromisoformat(str(betreffender_termin)) if betreffender_termin else None
        ),
        warnings=list(data.get("warnings", [])),
    )


def invoice_from_dict(data: dict) -> ValidatedInvoice:
    from datetime import date

    return ValidatedInvoice(
        patient_first_name=str(data["patient_first_name"]),
        date=date.fromisoformat(str(data["date"])),
        date_source=str(data["date_source"]),
        topic=str(data["topic"]),
        total_amount_eur=Decimal(str(data["total_amount_eur"])),
        doctor_name=data.get("doctor_name"),
        warnings=list(data.get("warnings", [])),
    )


def text_verification_from_dict(data: dict) -> TextVerificationResult:
    from datetime import date

    return TextVerificationResult(
        amount_found=bool(data.get("amount_found", False)),
        date_found=bool(data.get("date_found", False)),
        amount_candidates=[Decimal(str(amount)) for amount in data.get("amount_candidates", [])],
        date_candidates=[
            date.fromisoformat(str(candidate)) for candidate in data.get("date_candidates", [])
        ],
        warnings=list(data.get("warnings", [])),
    )


def routing_decision_from_dict(data: dict) -> RoutingDecision:
    return RoutingDecision(
        action=RouteAction(str(data["action"])),
        review_reasons=list(data.get("review_reasons", [])),
        blocking_reasons=list(data.get("blocking_reasons", [])),
        warnings=list(data.get("warnings", [])),
    )


def _patients_from_state(data: dict[str, Any]) -> tuple[PatientEntry, ...]:
    """Deserialize patients from state with backward compat for old patient_tags dict."""
    patients_raw = data.get("patients")
    if isinstance(patients_raw, list):
        return tuple(
            PatientEntry(
                name=str(p.get("name", "")),
                tag=str(p.get("tag", "")),
                aliases=tuple(str(a) for a in p.get("aliases", [])),
            )
            for p in patients_raw
        )
    # Legacy fallback: patient_tags dict -> PatientEntry without aliases
    legacy_tags = data.get("patient_tags")
    if isinstance(legacy_tags, dict):
        return tuple(PatientEntry(name=str(k), tag=str(v)) for k, v in legacy_tags.items())
    return ()


def anytype_config_from_state(state: GraphState) -> AnytypeConfig:
    data = state.get(STATE_ANYTYPE_CONFIG, {})
    return AnytypeConfig(
        space_id=str(data.get("space_id", "")),
        collection_name=str(data.get("collection_name", "")),
        collection_id=str(data.get("collection_id", "")),
        custom_type_name=str(data.get("custom_type_name", "")),
        custom_type_key=str(data.get("custom_type_key", "")),
        gkk_property_id=str(data.get("gkk_property_id", "")),
        pkv_property_id=str(data.get("pkv_property_id", "")),
        pkv_eingereicht_property_id=str(data.get("pkv_eingereicht_property_id", "")),
        attachment_property_id=str(data.get("attachment_property_id", "")),
        done_property_id=str(data.get("done_property_id", "")),
        patients=_patients_from_state(data),
        patient_tag_property_id=str(data.get("patient_tag_property_id", "")),
        amount_property_id=str(data.get("amount_property_id", "")),
        date_property_id=str(data.get("date_property_id", "")),
        doctor_property_id=str(data.get("doctor_property_id", "")),
        extension_command=str(data.get("extension_command", "anytype-extension-mcp-wrapper")),
        dry_run=bool(get_anytype_dry_run(state)),
    )
