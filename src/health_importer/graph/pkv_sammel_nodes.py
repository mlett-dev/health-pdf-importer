"""Graph nodes for Pkv-Antworten that settle several treatments (Sammelbriefe).

The letter is uploaded once and attached to every invoice it settles; each
invoice gets its own row's Erstattung. Nothing is written unless every row
validated, the rows add up to the letter's totals, and every row found its
own invoice -- a half-applied Sammelbrief is harder to spot and fix than one
waiting in review.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from health_importer.ai.schemas import PkvAntwortExtraction
from health_importer.anytype.client import AnytypeClientError, build_anytype_client
from health_importer.anytype.kassen_matching import find_invoice_candidates
from health_importer.anytype.kassen_update import (
    attach_kassen_pdf,
    mark_invoice_done,
    update_pkv_properties,
)
from health_importer.anytype.pkv_sammel_matching import match_sammelbrief_positions
from health_importer.config import PkvFileNamingConfig
from health_importer.graph.anytype_update_nodes import _existing_attachment_file_ids
from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_MATCHING_CANDIDATES,
    STATE_MATCHING_CONFIDENCE,
    STATE_NEXT_ROUTE,
    STATE_OK,
    STATE_PKV_SAMMEL_MATCHES,
    STATE_PKV_SAMMEL_WRITTEN,
    STATE_PKV_SAMMELBRIEF,
    STATE_SELECTED_MATCH,
    STATE_STATUS,
    STATE_TARGET_FILENAME,
    STATE_VALIDATION,
    GraphState,
    get_anytype_dry_run,
    get_correction_overrides,
    get_ok,
    get_pkv_antwort_extraction,
    get_pkv_anytype_file_id,
    get_pkv_file_naming,
    get_pkv_sammel_matches,
    get_pkv_sammelbrief,
    get_required_confidence_min,
    get_status,
)
from health_importer.graph.state_helpers import (
    anytype_config_from_state,
    copy_state,
    event,
    property_key_warning_events,
)
from health_importer.workflow.filenames import generate_pkv_sammel_filename
from health_importer.workflow.pkv_sammelbrief import (
    PkvSammelbriefValidation,
    validate_pkv_sammelbrief,
)

logger = logging.getLogger(__name__)


def is_pkv_sammelbrief(state: GraphState) -> bool:
    raw = get_pkv_antwort_extraction(state)
    if not raw:
        return False
    return PkvAntwortExtraction.model_validate(raw).is_sammelbrief()


def validate_pkv_sammelbrief_node(state: GraphState) -> GraphState:
    """Validate each row of a Sammelbrief and check it against the letter's totals."""
    extraction = PkvAntwortExtraction.model_validate(get_pkv_antwort_extraction(state))
    anytype_cfg = anytype_config_from_state(state)
    result = validate_pkv_sammelbrief(
        extraction,
        allowed_patients=tuple(state.get("allowed_patients", ())),
        patient_aliases=anytype_cfg.patient_alias_map,
        required_confidence_min=float(get_required_confidence_min(state)),
    )
    errors = list(result.errors)
    # A manual correction names one invoice; a Sammelbrief needs one per row.
    if get_correction_overrides(state).get("pkv_match_object_id"):
        errors.append("manual_match_correction_unsupported_for_sammelbrief")

    next_state = copy_state(state)
    next_state[STATE_PKV_SAMMELBRIEF] = result.to_dict()
    ok = not errors
    next_state[STATE_VALIDATION] = {
        "ok": ok,
        "errors": errors,
        "warnings": result.warnings,
        "pkv": None,
        "sammelbrief": result.to_dict(),
    }
    if ok:
        next_state[STATE_STATUS] = "PKV_SAMMEL_VALIDATED"
        next_state[STATE_EVENTS].append(
            event(
                "validate_pkv_sammelbrief",
                "PKV_SAMMEL_VALIDATED",
                f"Sammelbrief with {len(result.positionen)} positionen adds up to "
                f"Auszahlung {result.auszahlung_eur}.",
            )
        )
    else:
        next_state[STATE_STATUS] = "PKV_VALIDATION_FAILED"
        next_state[STATE_EVENTS].append(
            event(
                "validate_pkv_sammelbrief",
                "PKV_VALIDATION_FAILED",
                f"Errors: {errors}",
            )
        )
    return next_state


def match_pkv_sammelbrief(state: GraphState) -> GraphState:
    """Find one invoice per row; route to review unless every row matched."""
    next_state = copy_state(state)
    validation = PkvSammelbriefValidation.from_dict(get_pkv_sammelbrief(state) or {})
    config = anytype_config_from_state(state)
    client = build_anytype_client(config)

    candidates_by_patient = {}
    object_properties: dict[str, dict] = {}
    for patient in dict.fromkeys(p.patient_first_name for p in validation.positionen):
        candidates, props = find_invoice_candidates(client, patient, config)
        candidates_by_patient[patient] = candidates
        object_properties.update(props)
    next_state[STATE_EVENTS].extend(
        property_key_warning_events("match_pkv_sammelbrief", object_properties, config)
    )

    matches = match_sammelbrief_positions(
        validation.positionen,
        candidates_by_patient,
        object_properties,
        config,
        auto_min=float(state.get("kassen_match_auto_min", 0.90)),
    )
    match_dicts = []
    for match in matches:
        data = match.to_dict()
        if match.selected is not None:
            data["existing_file_ids"] = _existing_attachment_file_ids(
                match.selected.properties, property_id=config.attachment_property_id
            )
        match_dicts.append(data)

    next_state[STATE_PKV_SAMMEL_MATCHES] = match_dicts
    next_state[STATE_MATCHING_CANDIDATES] = match_dicts
    next_state[STATE_SELECTED_MATCH] = None
    unmatched = [m for m in matches if m.selected is None]
    if matches and not unmatched:
        next_state[STATE_MATCHING_CONFIDENCE] = min(m.selected.score for m in matches if m.selected)
        next_state[STATE_NEXT_ROUTE] = "pkv_sammel_auto_update"
        next_state[STATE_STATUS] = "PKV_SAMMEL_AUTO_MATCH"
        summary = ", ".join(
            f"#{m.position.index}->{m.selected.object_ref.name}" for m in matches if m.selected
        )
        next_state[STATE_EVENTS].append(
            event(
                "match_pkv_sammelbrief",
                "PKV_SAMMEL_AUTO_MATCH",
                f"All {len(matches)} positionen matched: {summary}.",
            )
        )
    else:
        next_state[STATE_MATCHING_CONFIDENCE] = 0.0
        next_state[STATE_NEXT_ROUTE] = "pkv_sammel_review"
        next_state[STATE_STATUS] = "PKV_SAMMEL_REVIEW"
        reasons = ", ".join(f"#{m.position.index}:{m.review_reason}" for m in unmatched)
        next_state[STATE_EVENTS].append(
            event(
                "match_pkv_sammelbrief",
                "PKV_SAMMEL_REVIEW",
                f"{len(unmatched)} of {len(matches)} positionen unmatched ({reasons}); "
                "nothing is written.",
            )
        )
    return next_state


def prepare_pkv_sammel_target_filename(state: GraphState) -> GraphState:
    next_state = copy_state(state)
    naming = get_pkv_file_naming(state)
    validation = PkvSammelbriefValidation.from_dict(get_pkv_sammelbrief(state) or {})
    filename = ""
    if naming and naming.get("enabled"):
        filename = generate_pkv_sammel_filename(
            bescheids_datum=validation.bescheids_datum,
            patients=[p.patient_first_name for p in validation.positionen],
            auszahlung_eur=validation.auszahlung_eur,
            config=PkvFileNamingConfig(**naming),
        )
    if filename:
        next_state[STATE_TARGET_FILENAME] = filename
        next_state[STATE_EVENTS].append(
            event(
                "prepare_pkv_sammel_target_filename",
                "FILENAME_PREPARED",
                f"Target filename: {filename}",
            )
        )
    else:
        next_state[STATE_EVENTS].append(
            event(
                "prepare_pkv_sammel_target_filename",
                "FILENAME_SKIPPED",
                "No pkv file naming configured.",
            )
        )
    return next_state


def update_pkv_sammel_anytype(state: GraphState) -> GraphState:
    """Attach the letter to every matched invoice and set each row's Erstattung."""
    next_state = copy_state(state)
    node = "update_pkv_sammel_anytype"

    if get_ok(state) is False or get_status(state) == "PKV_UPLOAD_FAILED":
        next_state[STATE_EVENTS].append(
            event(node, "PKV_UPDATE_SKIPPED", "Skipped because previous Pkv step failed.")
        )
        return next_state

    pkv_file_id = get_pkv_anytype_file_id(state)
    if not pkv_file_id:
        next_state[STATE_STATUS] = "PKV_UPDATE_SKIPPED"
        next_state[STATE_OK] = False
        next_state[STATE_EVENTS].append(
            event(node, "PKV_ATTACH_SKIPPED", "No pkv_anytype_file_id in state; nothing written.")
        )
        return next_state

    config = anytype_config_from_state(state)
    client = build_anytype_client(config)
    dry_run = bool(get_anytype_dry_run(state))
    written: list[str] = []

    for match in get_pkv_sammel_matches(state):
        object_id = str(match["object_id"])
        erstattung = Decimal(str(match["position"]["erstattungsbetrag_eur"]))
        try:
            attach_kassen_pdf(
                client,
                object_id=object_id,
                kassen_file_id=pkv_file_id,
                attachment_property_id=config.attachment_property_id,
                existing_file_ids=list(match.get("existing_file_ids") or []),
                dry_run=dry_run,
            )
            update_pkv_properties(
                client,
                object_id=object_id,
                erstattungsbetrag_eur=erstattung,
                pkv_property_id=config.pkv_property_id,
                dry_run=dry_run,
            )
            mark_invoice_done(
                client,
                object_id=object_id,
                done_property_id=config.done_property_id,
                dry_run=dry_run,
            )
        except AnytypeClientError as exc:
            logger.error(
                "PKV_SAMMEL_UPDATE_FAILED: exc=%s object_id=%s already_written=%s",
                exc,
                object_id,
                written,
            )
            next_state[STATE_STATUS] = "PKV_UPDATE_FAILED"
            next_state[STATE_OK] = False
            next_state[STATE_PKV_SAMMEL_WRITTEN] = written
            next_state[STATE_EVENTS].append(
                event(
                    node,
                    "PKV_UPDATE_FAILED",
                    f"Update of {match.get('name')} ({object_id}) failed "
                    f"({type(exc).__name__}). Already written: {written or 'none'}; "
                    "the remaining positionen were not touched.",
                    severity="error",
                )
            )
            return next_state
        written.append(object_id)
        next_state[STATE_EVENTS].append(
            event(
                node,
                "PKV_PROPERTY_UPDATED" if not dry_run else "PKV_PROPERTY_DRY_RUN",
                f"{'Applied' if not dry_run else 'Dry-run'} Pkv (€)={erstattung}, "
                f"attachment and Done to {match.get('name')} ({object_id}).",
            )
        )

    next_state[STATE_PKV_SAMMEL_WRITTEN] = written
    next_state[STATE_STATUS] = "PKV_UPDATED" if not dry_run else "PKV_UPDATE_DRY_RUN"
    return next_state
