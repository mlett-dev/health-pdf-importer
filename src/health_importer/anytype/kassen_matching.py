from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from health_importer.anytype.client import AnytypeClient, AnytypeObjectRef
    from health_importer.config import AnytypeConfig
    from health_importer.workflow.validation import ValidatedKassenRuckmeldung


@dataclass
class KassenMatchCandidate:
    object_ref: "AnytypeObjectRef"
    score: float
    match_reasons: list[str]
    invoice_file_id: str | None = None
    properties: dict = field(default_factory=dict)


def find_invoice_candidates(
    client: "AnytypeClient",
    patient_first_name: str,
    config: "AnytypeConfig",
) -> tuple[list["AnytypeObjectRef"], dict[str, dict]]:
    """Search for Wahlarztrechnung objects matching a patient name.

    Anytype's search-space-compact does not search relation/tag properties,
    only object titles. Therefore we fetch ALL objects of the type and filter
    client-side by the Patient tag.

    Returns (candidates, object_properties_map).
    """
    import sys

    all_refs = client.search_object_by_type(
        type_name=config.custom_type_key,
        query="",
    )
    sys.stderr.write(
        f"[find_invoice_candidates] Fetched {len(all_refs)} objects of type "
        f"{config.custom_type_key}, filtering for patient={patient_first_name}\n"
    )

    candidates = []
    object_properties: dict[str, dict] = {}
    for ref in all_refs:
        props = ref.properties if isinstance(ref.properties, dict) else {}
        object_properties[ref.id] = props
        tags = _get_patient_tags(props, config.patient_tag_property_id)
        if patient_first_name in tags:
            candidates.append(ref)

    # Resolve linked doctor names so the scoring can match on them.
    doctor_names = _resolve_doctor_names(client, config, object_properties)
    for inv_id, props in object_properties.items():
        arzt_prop = props.get(config.doctor_property_id, {})
        if isinstance(arzt_prop, dict):
            linked_ids = arzt_prop.get("value") or arzt_prop.get("objects", [])
            if isinstance(linked_ids, list):
                for d_id in linked_ids:
                    if d_id in doctor_names:
                        props["__resolved_doctor_name__"] = doctor_names[d_id]
                        break

    sys.stderr.write(
        f"[find_invoice_candidates] Found {len(candidates)} candidates for patient={patient_first_name}\n"
    )
    return candidates, object_properties


def score_match_candidates(
    candidates: list["AnytypeObjectRef"],
    kassen: "ValidatedKassenRuckmeldung",
    object_properties: dict[str, dict],
    config: "AnytypeConfig",
) -> list[KassenMatchCandidate]:
    """Score invoice candidates against a Kassenrückmeldung.

    Returns candidates sorted by descending score.
    """
    scored: list[KassenMatchCandidate] = []
    for obj_ref in candidates:
        props = object_properties.get(obj_ref.id, {})
        score, reasons = _compute_match_score(
            props,
            kassen,
            config.date_property_id,
            config.amount_property_id,
            config.patient_tag_property_id,
        )
        invoice_file_id = _extract_invoice_file_id(props, config.attachment_property_id)
        scored.append(
            KassenMatchCandidate(
                object_ref=obj_ref,
                score=score,
                match_reasons=reasons,
                invoice_file_id=invoice_file_id,
                properties=props,
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def _compute_match_score(
    props: dict,
    kassen: "ValidatedKassenRuckmeldung",
    date_property_id: str,
    amount_property_id: str,
    patient_tag_property_id: str,
) -> tuple[float, list[str]]:
    """Compute a weighted match score and return reasons.

    Weights:
    - Patient:      mandatory, exact tag match (0.0 or 1.0)
    - Betrag:       high weight, exact match → 1.0, proportional falloff
    - Aktenzeichen: very high weight, exact match → 1.0
    - Rechnungsnr:  very high weight, exact match → 1.0
    - Arzt:         medium weight, rapidfuzz → 0.0–1.0
    - Termin:       medium weight, within 7 days → 1.0
    """
    reasons: list[str] = []
    scores: list[tuple[float, float]] = []  # (weight, score)

    # Patient (mandatory) — already filtered by search, but double-check
    patient_tags = _get_patient_tags(props, patient_tag_property_id)
    if kassen.patient_first_name in patient_tags:
        scores.append((1.0, 1.0))
        reasons.append(f"patient_exact:{kassen.patient_first_name}")
    else:
        scores.append((1.0, 0.0))
        reasons.append(f"patient_mismatch:{patient_tags}")

    # Betrag-Matching: Aufwendungsbetrag (ursprünglicher Rechnungsbetrag) hat höchste Priorität
    invoice_amount = _get_invoice_amount(props, amount_property_id)
    epsilon = Decimal("0.01")
    if kassen.aufwendungsbetrag_eur is not None and kassen.aufwendungsbetrag_eur > 0:
        # Aufwendungsbetrag ist der ursprüngliche Rechnungsbetrag → sehr starkes Signal
        if invoice_amount is not None:
            diff = abs(invoice_amount - kassen.aufwendungsbetrag_eur)
            if diff <= epsilon:
                scores.append((1.5, 1.0))
                reasons.append(f"aufwendungsbetrag_exact:{invoice_amount}")
            else:
                max_amount = max(invoice_amount, kassen.aufwendungsbetrag_eur)
                if max_amount > 0:
                    ratio = 1.0 - float(diff / max_amount)
                    ratio = max(0.0, ratio)
                    scores.append((1.5, ratio))
                    reasons.append(f"aufwendungsbetrag_ratio:{ratio:.2f}")
        else:
            scores.append((1.5, 0.0))
            reasons.append("aufwendungsbetrag_invoice_amount_missing")
    elif invoice_amount is not None and kassen.erstattungsbetrag_eur > 0:
        # Fallback: Erstattungsbetrag mit Rechnungsbetrag vergleichen
        diff = abs(invoice_amount - kassen.erstattungsbetrag_eur)
        if diff <= epsilon:
            scores.append((1.0, 1.0))
            reasons.append(f"amount_exact:{invoice_amount}")
        else:
            max_amount = max(invoice_amount, kassen.erstattungsbetrag_eur)
            if max_amount > 0:
                ratio = 1.0 - float(diff / max_amount)
                ratio = max(0.0, ratio)
                scores.append((1.0, ratio))
                reasons.append(f"amount_ratio:{ratio:.2f}")
    else:
        scores.append((1.0, 0.0))
        reasons.append("amount_missing")

    # Aktenzeichen (very high weight)
    if kassen.aktenzeichen:
        if "aktenzeichen" not in props:
            reasons.append("aktenzeichen_not_configured")
        elif doc_aktenzeichen := _get_direct_string_prop(props, "aktenzeichen"):
            if _normalize_for_match(doc_aktenzeichen) == _normalize_for_match(kassen.aktenzeichen):
                scores.append((1.5, 1.0))
                reasons.append(f"aktenzeichen_exact:{kassen.aktenzeichen}")
            else:
                scores.append((1.5, 0.0))
                reasons.append("aktenzeichen_mismatch")
        else:
            scores.append((1.5, 0.0))
            reasons.append("aktenzeichen_missing_in_invoice")

    # Rechnungsnummer (very high weight)
    if kassen.rechnungsnummer:
        if "rechnungsnummer" not in props:
            reasons.append("rechnungsnummer_not_configured")
        elif doc_rechnungsnr := _get_direct_string_prop(props, "rechnungsnummer"):
            if _normalize_for_match(doc_rechnungsnr) == _normalize_for_match(
                kassen.rechnungsnummer
            ):
                scores.append((1.5, 1.0))
                reasons.append(f"rechnungsnummer_exact:{kassen.rechnungsnummer}")
            else:
                scores.append((1.5, 0.0))
                reasons.append("rechnungsnummer_mismatch")
        else:
            scores.append((1.5, 0.0))
            reasons.append("rechnungsnummer_missing_in_invoice")

    # Arzt (medium weight)
    if kassen.doctor_name:
        doc_doctor = get_resolved_doctor_name(props)
        if doc_doctor:
            score = (
                fuzz.token_set_ratio(
                    _normalize_for_match(doc_doctor),
                    _normalize_for_match(kassen.doctor_name),
                )
                / 100.0
            )
            scores.append((0.5, score))
            reasons.append(f"doctor_fuzzy:{score:.2f}")
        else:
            scores.append((0.5, 0.0))
            reasons.append("doctor_missing_in_invoice")
    else:
        scores.append((0.5, 0.0))
        reasons.append("doctor_missing_in_kassen")

    # Termin (medium weight)
    if kassen.betreffender_termin:
        doc_date = _get_date_prop(props, date_property_id)
        if doc_date:
            delta = abs((doc_date - kassen.betreffender_termin).days)
            if delta <= 7:
                score = 1.0 - (delta / 7.0)
                scores.append((0.5, score))
                reasons.append(f"date_close:{delta}d")
            else:
                scores.append((0.5, 0.0))
                reasons.append(f"date_far:{delta}d")
        else:
            scores.append((0.5, 0.0))
            reasons.append("date_missing_in_invoice")
    else:
        scores.append((0.5, 0.0))
        reasons.append("date_missing_in_kassen")

    # Compute weighted average
    total_weight = sum(w for w, _ in scores)
    if total_weight == 0:
        return 0.0, reasons
    weighted_score = sum(w * s for w, s in scores) / total_weight
    return weighted_score, reasons


# --- Property helpers --------------------------------------------------------


def _resolve_doctor_names(
    client: "AnytypeClient",
    config: "AnytypeConfig",
    object_properties: dict[str, dict],
) -> dict[str, str]:
    """Resolve linked doctor object IDs to human-readable names via Anytype.

    Collects all unique doctor object IDs from the Arzt (objects) property,
    fetches them in one batch via ``get-objects-compact-many``, and returns
    a mapping ``object_id -> name``.
    """
    runner = getattr(client, "runner", None)
    if runner is None:
        return {}

    doctor_ids: set[str] = set()
    for props in object_properties.values():
        arzt_prop = props.get(config.doctor_property_id, {})
        if isinstance(arzt_prop, dict):
            ids = arzt_prop.get("value") or arzt_prop.get("objects", [])
            if isinstance(ids, list):
                for d_id in ids:
                    if isinstance(d_id, str) and d_id:
                        doctor_ids.add(d_id)

    if not doctor_ids:
        return {}

    try:
        result = runner.call_extension(
            "get-objects-compact-many",
            {
                "space_id": config.space_id,
                "object_ids": sorted(doctor_ids),
            },
        )
        names: dict[str, str] = {}
        for entry in result.get("objects", []):
            obj = entry.get("object", {})
            oid = obj.get("id")
            name = obj.get("name", "")
            if oid and name:
                names[str(oid)] = str(name)
        return names
    except Exception:
        return {}


def _get_patient_tags(props: dict, patient_tag_property_id: str) -> list[str]:
    """Extract patient tag names from Anytype multi_select / select property."""
    patient_prop = props.get(patient_tag_property_id, {})
    if not isinstance(patient_prop, dict):
        return []
    value = patient_prop.get("value") or patient_prop.get("multi_select") or []
    if not isinstance(value, list):
        return []
    return [
        str(tag.get("name", tag)) if isinstance(tag, dict) else str(tag) for tag in value if tag
    ]


def _get_invoice_amount(props: dict, amount_property_id: str) -> Decimal | None:
    """Extract invoice amount from Anytype number property."""
    amount_prop = props.get(amount_property_id, {})
    if not isinstance(amount_prop, dict):
        return None
    value = amount_prop.get("value")
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _get_date_prop(props: dict, key: str) -> date | None:
    """Extract date from Anytype date property."""
    prop = props.get(key, {})
    if not isinstance(prop, dict):
        return None
    value = prop.get("value") or prop.get("date")
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def get_invoice_date(props: dict, date_property_id: str) -> date | None:
    """Return the Rechnungsdatum stored on a Wahlarztrechnung object."""
    return _get_date_prop(props, date_property_id)


def get_resolved_doctor_name(props: dict) -> str | None:
    """Return the doctor name find_invoice_candidates resolved for this object.

    The Arzt property holds linked object IDs, so the readable name only exists
    once _resolve_doctor_names has written it back. Returning None when it did
    not is the honest answer -- the predecessor of this function fell back to
    scanning every property and handing back the first one carrying a `name`
    sub-key, which is a property label such as "GKK eingereicht", never a
    doctor.
    """
    resolved = props.get("__resolved_doctor_name__")
    return str(resolved) if resolved else None


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


def _extract_invoice_file_id(props: dict, attachment_property_id: str) -> str | None:
    """Extract the first file ID from the Anhänge property."""
    attachments = props.get(attachment_property_id, {})
    if not isinstance(attachments, dict):
        return None
    files = attachments.get("value") or attachments.get("files", [])
    if isinstance(files, list) and files:
        return str(files[0])
    return None


def _normalize_for_match(value: str) -> str:
    """Normalize a string for comparison."""
    return " ".join(str(value).lower().split())
