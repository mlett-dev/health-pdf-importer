from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil import parser
from rapidfuzz import fuzz

from health_importer.ai.schemas import (
    InvoiceExtraction,
    KassenRuckmeldungExtraction,
    PkvAntwortExtraction,
)


@dataclass(frozen=True)
class ValidatedInvoice:
    patient_first_name: str
    date: date
    date_source: str
    topic: str
    total_amount_eur: Decimal
    doctor_name: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidatedKassenRuckmeldung:
    patient_first_name: str
    doctor_name: str | None
    bescheids_datum: date | None
    aufwendungsbetrag_eur: Decimal | None
    erstattungsbetrag_eur: Decimal
    rechnungsnummer: str | None
    aktenzeichen: str | None
    betreffender_termin: date | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidatedPkvAntwort:
    patient_first_name: str
    doctor_name: str | None
    bescheids_datum: date | None
    aufwendungsbetrag_eur: Decimal | None
    erstattungsbetrag_eur: Decimal
    rechnungsnummer: str | None
    betreffender_termin: date | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    invoice: ValidatedInvoice | None
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class KassenValidationResult:
    ok: bool
    kassen: ValidatedKassenRuckmeldung | None
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class PkvValidationResult:
    ok: bool
    pkv: ValidatedPkvAntwort | None
    errors: list[str]
    warnings: list[str]


def validate_invoice_extraction(
    extraction: InvoiceExtraction,
    *,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None = None,
    required_confidence_min: float = 0.8,
    max_amount_eur: Decimal = Decimal("5000"),
    max_topic_length: int = 60,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(extraction.warnings)

    patient = _validate_patient(
        extraction, allowed_patients, patient_aliases, required_confidence_min, errors
    )
    invoice_date, date_source = _validate_date(extraction, required_confidence_min, errors)
    amount = _validate_amount(extraction, required_confidence_min, max_amount_eur, errors)
    topic = _validate_topic(extraction, required_confidence_min, max_topic_length, errors)

    doctor_name = None
    if extraction.doctor_name.value is not None:
        doctor_name = str(extraction.doctor_name.value).strip()
        if extraction.doctor_name.confidence < required_confidence_min:
            warnings.append("doctor_name_below_confidence_threshold")

    if errors:
        return ValidationResult(ok=False, invoice=None, errors=errors, warnings=warnings)

    return ValidationResult(
        ok=True,
        invoice=ValidatedInvoice(
            patient_first_name=patient,
            date=invoice_date,
            date_source=date_source,
            topic=topic,
            total_amount_eur=amount,
            doctor_name=doctor_name,
            warnings=warnings,
        ),
        errors=[],
        warnings=warnings,
    )


def normalize_topic(value: str, *, max_length: int = 60) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = _UNSAFE_TOPIC_RE.sub(" ", normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized[:max_length].rstrip()


def _validate_patient(
    extraction: InvoiceExtraction,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None,
    required_confidence_min: float,
    errors: list[str],
) -> str:
    field = extraction.patient_first_name
    if field.value is None:
        errors.append("patient_first_name_missing")
        return ""
    if field.confidence < required_confidence_min:
        errors.append("patient_first_name_below_confidence_threshold")
    aliases = patient_aliases or {}
    patient = normalize_patient_name(str(field.value), aliases)
    if patient not in allowed_patients:
        errors.append(f"patient_first_name_not_allowed:{patient}")
    return patient


def normalize_patient_name(value: str, aliases: dict[str, str]) -> str:
    normalized = value.strip()
    return aliases.get(normalized.casefold(), normalized)


def doctor_patient_name_too_similar(
    doctor_name: str | None,
    patient_first_name: str | None,
    *,
    threshold: float = 85.0,
) -> bool:
    """Return True when doctor and patient names are suspiciously similar.

    Models occasionally copy the patient name into ``doctor_name`` when no real
    doctor name is visible in the text but a logo or stamp carries it. In that
    case we want to fall back to vision instead of trusting the text result.
    """

    if not doctor_name or not patient_first_name:
        return False

    doctor = _normalize_for_similarity(doctor_name)
    patient = _normalize_for_similarity(patient_first_name)
    if not doctor or not patient:
        return False

    if patient and patient in doctor.split():
        return True

    score = fuzz.token_set_ratio(doctor, patient)
    return score >= threshold


def _normalize_for_similarity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"\b(dr|dr\.|prof|prof\.|mag|mag\.|med|univ|univ\.)\b", " ", normalized)
    normalized = _SPACE_RE.sub(" ", normalized).strip()
    return normalized


def _validate_date(
    extraction: InvoiceExtraction,
    required_confidence_min: float,
    errors: list[str],
) -> tuple[date, str]:
    for field_name in ("appointment_date", "invoice_date"):
        field = getattr(extraction, field_name)
        if field.value is None:
            continue
        if field.confidence < required_confidence_min:
            errors.append(f"{field_name}_below_confidence_threshold")
        try:
            return parser.parse(str(field.value), dayfirst=False).date(), field_name
        except (TypeError, ValueError, OverflowError):
            errors.append(f"{field_name}_invalid")
            break
    errors.append("appointment_date_or_invoice_date_missing")
    return date.min, ""


def _validate_amount(
    extraction: InvoiceExtraction,
    required_confidence_min: float,
    max_amount_eur: Decimal,
    errors: list[str],
) -> Decimal:
    field = extraction.total_amount_eur
    if field.value is None:
        errors.append("total_amount_eur_missing")
        return Decimal("0")
    if field.confidence < required_confidence_min:
        errors.append("total_amount_eur_below_confidence_threshold")
    try:
        amount = Decimal(str(field.value))
    except (InvalidOperation, ValueError):
        errors.append("total_amount_eur_invalid")
        return Decimal("0")
    if amount <= 0:
        errors.append("total_amount_eur_not_positive")
    if amount > max_amount_eur:
        errors.append("total_amount_eur_above_max")
    return amount


def _validate_topic(
    extraction: InvoiceExtraction,
    required_confidence_min: float,
    max_topic_length: int,
    errors: list[str],
) -> str:
    field = extraction.topic
    if field.value is None:
        errors.append("topic_missing")
        return ""
    if field.confidence < required_confidence_min:
        errors.append("topic_below_confidence_threshold")
    topic = normalize_topic(str(field.value), max_length=max_topic_length)
    if not topic:
        errors.append("topic_empty_after_normalization")
    return topic


_UNSAFE_TOPIC_RE = re.compile(r"[^\w äöüÄÖÜß+.-]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def validate_kassen_ruckmeldung(
    extraction: KassenRuckmeldungExtraction,
    *,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None = None,
    required_confidence_min: float = 0.8,
    max_amount_eur: Decimal = Decimal("10000"),
) -> KassenValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(extraction.warnings)

    patient = _validate_kassen_patient(
        extraction, allowed_patients, patient_aliases, required_confidence_min, errors
    )
    bescheids_datum = _validate_kassen_date(
        extraction, "bescheids_datum", required_confidence_min, warnings
    )
    betreffender_termin = _validate_kassen_date(
        extraction, "betreffender_termin", required_confidence_min, warnings
    )
    amount = _validate_kassen_amount(
        extraction, "erstattungsbetrag_eur", required_confidence_min, max_amount_eur, errors
    )
    aufwendungsbetrag = _validate_kassen_amount_optional(
        extraction, "aufwendungsbetrag_eur", required_confidence_min, max_amount_eur, warnings
    )

    doctor_name = None
    if extraction.doctor_name.value is not None:
        doctor_name = str(extraction.doctor_name.value).strip()
        if extraction.doctor_name.confidence < required_confidence_min:
            warnings.append("doctor_name_below_confidence_threshold")

    rechnungsnummer = None
    if extraction.rechnungsnummer.value is not None:
        rechnungsnummer = str(extraction.rechnungsnummer.value).strip()

    aktenzeichen = None
    if extraction.aktenzeichen.value is not None:
        aktenzeichen = str(extraction.aktenzeichen.value).strip()

    if errors:
        return KassenValidationResult(ok=False, kassen=None, errors=errors, warnings=warnings)

    return KassenValidationResult(
        ok=True,
        kassen=ValidatedKassenRuckmeldung(
            patient_first_name=patient,
            doctor_name=doctor_name,
            bescheids_datum=bescheids_datum,
            aufwendungsbetrag_eur=aufwendungsbetrag,
            erstattungsbetrag_eur=amount,
            rechnungsnummer=rechnungsnummer,
            aktenzeichen=aktenzeichen,
            betreffender_termin=betreffender_termin,
            warnings=warnings,
        ),
        errors=[],
        warnings=warnings,
    )


def validate_pkv_antwort(
    extraction: PkvAntwortExtraction,
    *,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None = None,
    required_confidence_min: float = 0.8,
    max_amount_eur: Decimal = Decimal("10000"),
) -> PkvValidationResult:
    errors: list[str] = []
    warnings: list[str] = list(extraction.warnings)

    patient = _validate_pkv_patient(
        extraction, allowed_patients, patient_aliases, required_confidence_min, errors
    )
    bescheids_datum = _validate_pkv_date(
        extraction, "bescheids_datum", required_confidence_min, warnings
    )
    betreffender_termin = _validate_pkv_date(
        extraction, "betreffender_termin", required_confidence_min, warnings
    )
    erstattungsbetrag = _validate_pkv_amount(
        extraction, "erstattungsbetrag_eur", required_confidence_min, max_amount_eur, errors
    )
    aufwendungsbetrag = _validate_pkv_amount_optional(
        extraction, "aufwendungsbetrag_eur", required_confidence_min, max_amount_eur, warnings
    )

    doctor_name = None
    if extraction.doctor_name.value is not None:
        doctor_name = str(extraction.doctor_name.value).strip()
        if extraction.doctor_name.confidence < required_confidence_min:
            warnings.append("doctor_name_below_confidence_threshold")

    rechnungsnummer = None
    if extraction.rechnungsnummer.value is not None:
        rechnungsnummer = str(extraction.rechnungsnummer.value).strip()

    if errors:
        return PkvValidationResult(ok=False, pkv=None, errors=errors, warnings=warnings)

    return PkvValidationResult(
        ok=True,
        pkv=ValidatedPkvAntwort(
            patient_first_name=patient,
            doctor_name=doctor_name,
            bescheids_datum=bescheids_datum,
            aufwendungsbetrag_eur=aufwendungsbetrag,
            erstattungsbetrag_eur=erstattungsbetrag,
            rechnungsnummer=rechnungsnummer,
            betreffender_termin=betreffender_termin,
            warnings=warnings,
        ),
        errors=[],
        warnings=warnings,
    )


def _validate_kassen_patient(
    extraction: KassenRuckmeldungExtraction,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None,
    required_confidence_min: float,
    errors: list[str],
) -> str:
    field = extraction.patient_first_name
    if field.value is None:
        errors.append("patient_first_name_missing")
        return ""
    if field.confidence < required_confidence_min:
        errors.append("patient_first_name_below_confidence_threshold")
    aliases = patient_aliases or {}
    patient = normalize_patient_name(str(field.value), aliases)
    if patient not in allowed_patients:
        errors.append(f"patient_first_name_not_allowed:{patient}")
    return patient


def _validate_pkv_patient(
    extraction: PkvAntwortExtraction,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None,
    required_confidence_min: float,
    errors: list[str],
) -> str:
    field = extraction.patient_first_name
    if field.value is None:
        errors.append("patient_first_name_missing")
        return ""
    if field.confidence < required_confidence_min:
        errors.append("patient_first_name_below_confidence_threshold")
    aliases = patient_aliases or {}
    patient = normalize_patient_name(str(field.value), aliases)
    if patient not in allowed_patients:
        errors.append(f"patient_first_name_not_allowed:{patient}")
    return patient


def _validate_kassen_date(
    extraction: KassenRuckmeldungExtraction,
    field_name: str,
    required_confidence_min: float,
    warnings: list[str],
) -> date | None:
    field = getattr(extraction, field_name)
    if field.value is None:
        return None
    if field.confidence < required_confidence_min:
        warnings.append(f"{field_name}_below_confidence_threshold")
    try:
        return parser.parse(str(field.value), dayfirst=False).date()
    except (TypeError, ValueError, OverflowError):
        warnings.append(f"{field_name}_invalid")
        return None


def _validate_pkv_date(
    extraction: PkvAntwortExtraction,
    field_name: str,
    required_confidence_min: float,
    warnings: list[str],
) -> date | None:
    field = getattr(extraction, field_name)
    if field.value is None:
        return None
    if field.confidence < required_confidence_min:
        warnings.append(f"{field_name}_below_confidence_threshold")
    try:
        return parser.parse(str(field.value), dayfirst=False).date()
    except (TypeError, ValueError, OverflowError):
        warnings.append(f"{field_name}_invalid")
        return None


def _validate_kassen_amount(
    extraction: KassenRuckmeldungExtraction,
    field_name: str,
    required_confidence_min: float,
    max_amount_eur: Decimal,
    errors: list[str],
) -> Decimal:
    field = getattr(extraction, field_name)
    if field.value is None:
        errors.append(f"{field_name}_missing")
        return Decimal("0")
    if field.confidence < required_confidence_min:
        errors.append(f"{field_name}_below_confidence_threshold")
    try:
        amount = Decimal(str(field.value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field_name}_invalid")
        return Decimal("0")
    if amount <= 0:
        errors.append(f"{field_name}_not_positive")
    if amount > max_amount_eur:
        errors.append(f"{field_name}_above_max")
    return amount


def _validate_pkv_amount(
    extraction: PkvAntwortExtraction,
    field_name: str,
    required_confidence_min: float,
    max_amount_eur: Decimal,
    errors: list[str],
) -> Decimal:
    field = getattr(extraction, field_name)
    if field.value is None:
        errors.append(f"{field_name}_missing")
        return Decimal("0")
    if field.confidence < required_confidence_min:
        errors.append(f"{field_name}_below_confidence_threshold")
    try:
        amount = Decimal(str(field.value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field_name}_invalid")
        return Decimal("0")
    if amount <= 0:
        errors.append(f"{field_name}_not_positive")
    if amount > max_amount_eur:
        errors.append(f"{field_name}_above_max")
    return amount


def _validate_kassen_amount_optional(
    extraction: KassenRuckmeldungExtraction,
    field_name: str,
    required_confidence_min: float,
    max_amount_eur: Decimal,
    warnings: list[str],
) -> Decimal | None:
    field = getattr(extraction, field_name)
    if field.value is None:
        return None
    if field.confidence < required_confidence_min:
        warnings.append(f"{field_name}_below_confidence_threshold")
    try:
        amount = Decimal(str(field.value))
    except (InvalidOperation, ValueError):
        warnings.append(f"{field_name}_invalid")
        return None
    if amount <= 0:
        warnings.append(f"{field_name}_not_positive")
    if amount > max_amount_eur:
        warnings.append(f"{field_name}_above_max")
    return amount


def _validate_pkv_amount_optional(
    extraction: PkvAntwortExtraction,
    field_name: str,
    required_confidence_min: float,
    max_amount_eur: Decimal,
    warnings: list[str],
) -> Decimal | None:
    field = getattr(extraction, field_name)
    if field.value is None:
        return None
    if field.confidence < required_confidence_min:
        warnings.append(f"{field_name}_below_confidence_threshold")
    try:
        amount = Decimal(str(field.value))
    except (InvalidOperation, ValueError):
        warnings.append(f"{field_name}_invalid")
        return None
    if amount <= 0:
        warnings.append(f"{field_name}_not_positive")
    if amount > max_amount_eur:
        warnings.append(f"{field_name}_above_max")
    return amount
