"""Validation for Pkv-Antworten that settle several treatments at once.

A Muki Sammelbrief lists one row per treatment, grouped by insured person,
with a "Gesamt" per person and one Auszahlung for the whole letter. Every row
becomes its own update on its own invoice, so the rows are only trusted when
they add up to the totals printed on the letter: that arithmetic is what
catches a misread amount or a row the model dropped or invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from dateutil import parser

from health_importer.ai.schemas import PkvAntwortExtraction
from health_importer.workflow.validation import normalize_patient_name, parse_amount_eur

_GERMAN_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


@dataclass(frozen=True)
class ValidatedPkvPosition:
    index: int
    patient_first_name: str
    doctor_name: str | None
    aufwendungsbetrag_eur: Decimal
    betreffender_termin: date
    erstattungsbetrag_eur: Decimal
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "patient_first_name": self.patient_first_name,
            "doctor_name": self.doctor_name,
            "aufwendungsbetrag_eur": str(self.aufwendungsbetrag_eur),
            "betreffender_termin": self.betreffender_termin.isoformat(),
            "erstattungsbetrag_eur": str(self.erstattungsbetrag_eur),
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidatedPkvPosition":
        return cls(
            index=int(data["index"]),
            patient_first_name=str(data["patient_first_name"]),
            doctor_name=data.get("doctor_name"),
            aufwendungsbetrag_eur=Decimal(str(data["aufwendungsbetrag_eur"])),
            betreffender_termin=date.fromisoformat(str(data["betreffender_termin"])),
            erstattungsbetrag_eur=Decimal(str(data["erstattungsbetrag_eur"])),
            evidence=data.get("evidence"),
        )


@dataclass(frozen=True)
class PkvSammelbriefValidation:
    ok: bool
    positionen: list[ValidatedPkvPosition]
    bescheids_datum: date | None
    auszahlung_eur: Decimal | None
    errors: list[str]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "positionen": [p.to_dict() for p in self.positionen],
            "bescheids_datum": self.bescheids_datum.isoformat() if self.bescheids_datum else None,
            "auszahlung_eur": str(self.auszahlung_eur) if self.auszahlung_eur is not None else None,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PkvSammelbriefValidation":
        bescheids_datum = data.get("bescheids_datum")
        auszahlung = data.get("auszahlung_eur")
        return cls(
            ok=bool(data.get("ok")),
            positionen=[ValidatedPkvPosition.from_dict(p) for p in data.get("positionen", [])],
            bescheids_datum=date.fromisoformat(bescheids_datum) if bescheids_datum else None,
            auszahlung_eur=Decimal(str(auszahlung)) if auszahlung is not None else None,
            errors=list(data.get("errors", [])),
            warnings=list(data.get("warnings", [])),
        )


def validate_pkv_sammelbrief(
    extraction: PkvAntwortExtraction,
    *,
    allowed_patients: tuple[str, ...],
    patient_aliases: dict[str, str] | None = None,
    required_confidence_min: float = 0.8,
    max_amount_eur: Decimal = Decimal("10000"),
) -> PkvSammelbriefValidation:
    """Validate every row of a Sammelbrief and check it against the letter's totals."""
    errors: list[str] = []
    warnings: list[str] = list(extraction.warnings)
    aliases = patient_aliases or {}

    positionen: list[ValidatedPkvPosition] = []
    for index, raw in enumerate(extraction.positionen, start=1):
        prefix = f"position_{index}"
        row_errors: list[str] = []
        if raw.confidence < required_confidence_min:
            row_errors.append(f"{prefix}_below_confidence_threshold")

        patient = ""
        if raw.patient_first_name and str(raw.patient_first_name).strip():
            patient = normalize_patient_name(str(raw.patient_first_name), aliases)
            if patient not in allowed_patients:
                row_errors.append(f"{prefix}_patient_not_allowed:{patient}")
        else:
            row_errors.append(f"{prefix}_patient_missing")

        aufwand = _amount(raw.aufwendungsbetrag_eur, f"{prefix}_aufwendungsbetrag", max_amount_eur)
        erstattung = _amount(raw.erstattungsbetrag_eur, f"{prefix}_erstattung", max_amount_eur)
        termin = _date(raw.betreffender_termin)
        evidence_termin = _single_german_date(raw.evidence)
        if evidence_termin is not None and evidence_termin != termin:
            # The evidence is the row copied verbatim; the ISO value is the
            # model's own conversion of it, which has been seen to swap day
            # and month (02.09. -> 2026-02-09).
            warnings.append(f"{prefix}_termin_taken_from_evidence:{termin}->{evidence_termin}")
            termin = evidence_termin
        if isinstance(aufwand, str):
            row_errors.append(aufwand)
        if isinstance(erstattung, str):
            row_errors.append(erstattung)
        if termin is None:
            row_errors.append(f"{prefix}_termin_missing_or_invalid")

        errors.extend(row_errors)
        if row_errors or isinstance(aufwand, str) or isinstance(erstattung, str) or not termin:
            continue
        doctor = str(raw.doctor_name).strip() if raw.doctor_name else None
        positionen.append(
            ValidatedPkvPosition(
                index=index,
                patient_first_name=patient,
                doctor_name=doctor or None,
                aufwendungsbetrag_eur=aufwand,
                betreffender_termin=termin,
                erstattungsbetrag_eur=erstattung,
                evidence=raw.evidence,
            )
        )

    if len(extraction.positionen) < 2:
        errors.append(f"sammelbrief_too_few_positionen:{len(extraction.positionen)}")

    auszahlung = _amount(extraction.auszahlung_eur.value, "auszahlung", max_amount_eur)
    if isinstance(auszahlung, str):
        errors.append(auszahlung)
        auszahlung = None
    elif extraction.auszahlung_eur.confidence < required_confidence_min:
        errors.append("auszahlung_below_confidence_threshold")

    # The totals are only meaningful when every row parsed; a missing row
    # would otherwise be reported twice, once itself and once as a sum gap.
    if not errors and auszahlung is not None:
        total = sum((p.erstattungsbetrag_eur for p in positionen), Decimal("0"))
        if total != auszahlung:
            errors.append(f"sum_mismatch_auszahlung:positionen={total},auszahlung={auszahlung}")

        for summe in extraction.personen_summen:
            if not summe.patient_first_name or not str(summe.patient_first_name).strip():
                errors.append("personen_summe_patient_missing")
                continue
            patient = normalize_patient_name(str(summe.patient_first_name), aliases)
            gesamt = _amount(summe.gesamt_eur, f"gesamt_{patient}", max_amount_eur)
            if isinstance(gesamt, str):
                errors.append(gesamt)
                continue
            person_total = sum(
                (p.erstattungsbetrag_eur for p in positionen if p.patient_first_name == patient),
                Decimal("0"),
            )
            if person_total != gesamt:
                errors.append(
                    f"sum_mismatch_person:{patient}:positionen={person_total},gesamt={gesamt}"
                )
        if not extraction.personen_summen:
            warnings.append("personen_summen_missing")

    bescheids_datum = _date(extraction.bescheids_datum.value)
    if bescheids_datum is None:
        warnings.append("bescheids_datum_missing_or_invalid")

    return PkvSammelbriefValidation(
        ok=not errors,
        positionen=positionen,
        bescheids_datum=bescheids_datum,
        auszahlung_eur=auszahlung,
        errors=errors,
        warnings=warnings,
    )


def _amount(value: object, name: str, max_amount_eur: Decimal) -> Decimal | str:
    """Parse an amount to the cent; a string return value is the error code."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return f"{name}_missing"
    amount = parse_amount_eur(value)
    if amount is None:
        return f"{name}_invalid"
    if amount <= 0:
        return f"{name}_not_positive"
    if amount > max_amount_eur:
        return f"{name}_above_max"
    return amount


def _single_german_date(text: str | None) -> date | None:
    """The one DD.MM.YYYY date in a text, or None if there is none or several."""
    if not text:
        return None
    found = {m.group(0) for m in _GERMAN_DATE.finditer(text)}
    if len(found) != 1:
        return None
    return _date(found.pop())


def _date(value: object) -> date | None:
    if value is None or not str(value).strip():
        return None
    text = str(value).strip()
    # The prompt asks for ISO dates, but a model copying the letter verbatim
    # writes 05.08.2026, which dateutil would read month-first.
    if german := _GERMAN_DATE.fullmatch(text):
        day, month, year = (int(g) for g in german.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    try:
        return parser.parse(text, dayfirst=False).date()
    except (TypeError, ValueError, OverflowError):
        return None
