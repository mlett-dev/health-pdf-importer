"""Pkv-Antwort matching: find the corresponding invoice for a Pkv response."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from health_importer.anytype.kassen_matching import (
    _get_date_prop,
    _get_invoice_amount,
    _get_patient_tags,
    _normalize_for_match,
)

if TYPE_CHECKING:
    from health_importer.anytype.client import AnytypeObjectRef
    from health_importer.config import AnytypeConfig


@dataclass
class PkvMatchCandidate:
    object_ref: "AnytypeObjectRef"
    score: float
    match_reasons: list[str]
    invoice_file_id: str | None = None
    properties: dict = field(default_factory=dict)


def score_pkv_candidates(
    candidates: list["AnytypeObjectRef"],
    patient_first_name: str,
    aufwendungsbetrag_eur: object | None,
    betreffender_termin: date | None,
    rechnungsnummer: str | None,
    object_properties: dict[str, dict],
    config: "AnytypeConfig",
) -> list[PkvMatchCandidate]:
    """Score invoice candidates against a Pkv-Antwort.

    Returns candidates sorted by descending score.
    """
    scored: list[PkvMatchCandidate] = []
    for obj_ref in candidates:
        props = object_properties.get(obj_ref.id, {})
        score, reasons = _compute_pkv_score(
            props,
            patient_first_name,
            aufwendungsbetrag_eur,
            betreffender_termin,
            rechnungsnummer,
            config,
        )
        invoice_file_id = _extract_invoice_file_id(props, config.attachment_property_id)
        scored.append(
            PkvMatchCandidate(
                object_ref=obj_ref,
                score=score,
                match_reasons=reasons,
                invoice_file_id=invoice_file_id,
                properties=props,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def _compute_pkv_score(
    props: dict,
    patient_first_name: str,
    aufwendungsbetrag_eur: object | None,
    betreffender_termin: date | None,
    rechnungsnummer: str | None,
    config: "AnytypeConfig",
) -> tuple[float, list[str]]:
    """Compute a weighted match score for Pkv-Antwort to invoice.

    Patient is a mandatory gate, but never an auto-match signal on its own.
    Strong signals are exact invoice number, exact original amount, or a close
    treatment date. The Pkv Bescheidsdatum is deliberately not matched against
    the invoice date.
    """
    reasons: list[str] = []
    scores: list[tuple[float, float]] = []  # (weight, score)

    # Patient (mandatory)
    patient_tags = _get_patient_tags(props, config.patient_tag_property_id)
    if patient_first_name in patient_tags:
        reasons.append(f"patient_exact:{patient_first_name}")
    else:
        reasons.append(f"patient_mismatch:{patient_tags}")
        return 0.0, reasons

    # Patient match only is review material, not an automatic update.
    scores.append((0.25, 1.0))

    amount = _decimal_or_none(aufwendungsbetrag_eur)
    invoice_amount = _get_invoice_amount(props, config.amount_property_id)
    if amount is not None and amount > 0:
        if invoice_amount is not None:
            diff = abs(invoice_amount - amount)
            if diff <= _AMOUNT_EPSILON:
                scores.append((1.5, 1.0))
                reasons.append(f"aufwendungsbetrag_exact:{invoice_amount}")
            else:
                scores.append((1.5, 0.0))
                reasons.append(f"aufwendungsbetrag_mismatch:{invoice_amount}")
        else:
            scores.append((1.5, 0.0))
            reasons.append("aufwendungsbetrag_invoice_amount_missing")

    if betreffender_termin:
        doc_date = _get_date_prop(props, config.date_property_id)
        if not doc_date:
            scores.append((1.0, 0.0))
            reasons.append("termin_missing_in_invoice")
        else:
            delta = abs((doc_date - betreffender_termin).days)
            if delta <= 7:
                score = 1.0 - (delta / 7.0)
                scores.append((1.0, score))
                reasons.append(f"termin_close:{delta}d")
            else:
                scores.append((1.0, 0.0))
                reasons.append(f"termin_far:{delta}d")

    # Rechnungsnummer (very high weight, only if present)
    if rechnungsnummer:
        if "rechnungsnummer" not in props:
            reasons.append("rechnungsnummer_not_configured")
        elif doc_rechnungsnr := _get_direct_string_prop(props, "rechnungsnummer"):
            if _normalize_for_match(doc_rechnungsnr) == _normalize_for_match(rechnungsnummer):
                scores.append((1.5, 1.0))
                reasons.append(f"rechnungsnummer_exact:{rechnungsnummer}")
            else:
                scores.append((1.5, 0.0))
                reasons.append("rechnungsnummer_mismatch")
        else:
            scores.append((1.5, 0.0))
            reasons.append("rechnungsnummer_missing_in_invoice")

    # Compute weighted average
    total_weight = sum(w for w, _ in scores)
    if total_weight == 0:
        return 0.0, reasons
    weighted_score = sum(w * s for w, s in scores) / total_weight
    if not has_pkv_strong_match_signal(reasons):
        return min(weighted_score, 0.6), reasons
    return weighted_score, reasons


def has_pkv_strong_match_signal(reasons: list[str]) -> bool:
    return any(
        reason.startswith(("rechnungsnummer_exact:", "aufwendungsbetrag_exact:", "termin_close:"))
        for reason in reasons
    )


def _decimal_or_none(value: object | None):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _get_direct_string_prop(props: dict, key: str) -> str | None:
    prop_value = props.get(key)
    if isinstance(prop_value, dict):
        value = prop_value.get("value")
        if value is not None:
            return str(value)
        for sub_key in ("text", "name", "string", "title"):
            if sub_key in prop_value and prop_value[sub_key] is not None:
                return str(prop_value[sub_key])
    elif prop_value is not None:
        return str(prop_value)
    return None


_AMOUNT_EPSILON = Decimal("0.01")


def _extract_invoice_file_id(props: dict, attachment_property_id: str) -> str | None:
    """Extract the first file ID from the Anhänge property."""
    attachments = props.get(attachment_property_id, {})
    if not isinstance(attachments, dict):
        return None
    files = attachments.get("files", [])
    if files:
        return str(files[0])
    return None
