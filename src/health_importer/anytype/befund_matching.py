"""Match a Befund / Patientenbrief to the invoice object it belongs to.

A Befund carries no amount, no Aktenzeichen and no Rechnungsnummer -- exactly
the criteria the Kassen scorer weighs highest. Only patient, doctor and
treatment date remain, so those three are weighed equally here and the caller
applies a stricter threshold than the Kassen flow does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from rapidfuzz import fuzz

from health_importer.anytype.kassen_matching import (
    _extract_invoice_file_id,
    _get_date_prop,
    _get_patient_tags,
    _get_string_prop,
    _normalize_for_match,
)

if TYPE_CHECKING:
    from health_importer.anytype.client import AnytypeObjectRef
    from health_importer.config import AnytypeConfig

# A Befund and its invoice describe the same visit, so the dates should agree
# closely; the tolerance covers a report written a few days after treatment.
BEFUND_DATE_TOLERANCE_DAYS = 7


@dataclass
class BefundMatchCandidate:
    object_ref: "AnytypeObjectRef"
    score: float
    match_reasons: list[str]
    invoice_file_id: str | None = None
    properties: dict = field(default_factory=dict)


def score_befund_candidates(
    candidates: list["AnytypeObjectRef"],
    *,
    patient_first_name: str,
    doctor_name: str | None,
    appointment_date: date | None,
    object_properties: dict[str, dict],
    config: "AnytypeConfig",
) -> list[BefundMatchCandidate]:
    """Score invoice candidates against a Befund, best match first."""
    scored: list[BefundMatchCandidate] = []
    for obj_ref in candidates:
        props = object_properties.get(obj_ref.id, {})
        score, reasons = _compute_befund_score(
            props,
            patient_first_name=patient_first_name,
            doctor_name=doctor_name,
            appointment_date=appointment_date,
            date_property_id=config.date_property_id,
            patient_tag_property_id=config.patient_tag_property_id,
        )
        scored.append(
            BefundMatchCandidate(
                object_ref=obj_ref,
                score=score,
                match_reasons=reasons,
                invoice_file_id=_extract_invoice_file_id(props, config.attachment_property_id),
                properties=props,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def _compute_befund_score(
    props: dict,
    *,
    patient_first_name: str,
    doctor_name: str | None,
    appointment_date: date | None,
    date_property_id: str,
    patient_tag_property_id: str,
) -> tuple[float, list[str]]:
    """Equal weight on patient, doctor and date -- nothing else is available.

    A missing value on the Befund side scores 0 rather than being dropped from
    the average: with only three criteria, ignoring an absent one would let a
    Befund without a date match on patient and doctor alone.
    """
    reasons: list[str] = []
    scores: list[float] = []

    patient_tags = _get_patient_tags(props, patient_tag_property_id)
    if patient_first_name in patient_tags:
        scores.append(1.0)
        reasons.append(f"patient_exact:{patient_first_name}")
    else:
        scores.append(0.0)
        reasons.append(f"patient_mismatch:{patient_tags}")

    if doctor_name:
        invoice_doctor = _get_string_prop(props, "doctor_name")
        if invoice_doctor:
            ratio = (
                fuzz.token_set_ratio(
                    _normalize_for_match(invoice_doctor), _normalize_for_match(doctor_name)
                )
                / 100.0
            )
            scores.append(ratio)
            reasons.append(f"doctor_fuzzy:{ratio:.2f}")
        else:
            scores.append(0.0)
            reasons.append("doctor_missing_in_invoice")
    else:
        scores.append(0.0)
        reasons.append("doctor_missing_in_befund")

    if appointment_date:
        invoice_date = _get_date_prop(props, date_property_id)
        if invoice_date:
            delta = abs((invoice_date - appointment_date).days)
            if delta <= BEFUND_DATE_TOLERANCE_DAYS:
                ratio = 1.0 - (delta / BEFUND_DATE_TOLERANCE_DAYS)
                scores.append(ratio)
                reasons.append(f"date_close:{delta}d")
            else:
                scores.append(0.0)
                reasons.append(f"date_far:{delta}d")
        else:
            scores.append(0.0)
            reasons.append("date_missing_in_invoice")
    else:
        scores.append(0.0)
        reasons.append("date_missing_in_befund")

    return sum(scores) / len(scores), reasons
