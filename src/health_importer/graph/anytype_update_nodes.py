from __future__ import annotations

import logging
import traceback
from decimal import Decimal
from typing import Any

from health_importer.anytype.client import AnytypeClientError, build_anytype_client
from health_importer.anytype.kassen_update import (
    attach_kassen_pdf,
    mark_invoice_done,
    update_kassen_properties,
    update_pkv_eingereicht,
    update_pkv_properties,
)
from health_importer.config import AnytypeConfig, PatientEntry
from health_importer.graph.state import (
    STATE_ANYTYPE_CONFIG,
    STATE_ANYTYPE_EXECUTION,
    STATE_EVENTS,
    STATE_OK,
    STATE_STATUS,
    GraphEvent,
    GraphState,
    get_anytype_dry_run,
    get_email_config,
    get_events,
    get_kassen_anytype_file_id,
    get_kassen_ruckmeldung_extraction,
    get_ok,
    get_pkv_antwort_extraction,
    get_pkv_anytype_file_id,
    get_selected_match,
    get_status,
)

logger = logging.getLogger(__name__)


def update_pkv_anytype(state: GraphState) -> GraphState:
    """Update Anytype invoice object with Pkv (€) property and mark as Done."""
    next_state = _copy_state(state)

    if get_ok(state) is False or get_status(state) == "PKV_UPLOAD_FAILED":
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_UPDATE_SKIPPED",
                "Skipped because previous Pkv step failed.",
            )
        )
        return next_state

    match = get_selected_match(state)
    if not match or not match.get("object_id"):
        next_state[STATE_STATUS] = "PKV_UPDATE_SKIPPED"
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_UPDATE_SKIPPED",
                "No matching invoice object to update.",
            )
        )
        return next_state

    extraction = get_pkv_antwort_extraction(state) or {}
    pkv_betrag = extraction.get("erstattungsbetrag_eur", {}).get("value")
    if pkv_betrag is None:
        next_state[STATE_STATUS] = "PKV_UPDATE_SKIPPED"
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_UPDATE_SKIPPED",
                "No Pkv erstattungsbetrag in extraction.",
            )
        )
        return next_state

    config = _anytype_config_from_state(state)
    client = build_anytype_client(config)
    dry_run = bool(get_anytype_dry_run(state))

    pkv_file_id = get_pkv_anytype_file_id(state)
    if not pkv_file_id:
        next_state[STATE_STATUS] = "PKV_UPDATE_SKIPPED"
        next_state[STATE_OK] = False
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_ATTACH_SKIPPED",
                "No pkv_anytype_file_id in state; skipping property update and Done.",
            )
        )
        return next_state

    try:
        existing_files = _existing_attachment_file_ids(
            match.get("properties", {}),
            property_id=config.attachment_property_id,
        )
        attach_result = attach_kassen_pdf(
            client,
            object_id=match["object_id"],
            kassen_file_id=pkv_file_id,
            attachment_property_id=config.attachment_property_id,
            existing_file_ids=existing_files,
            dry_run=dry_run,
        )
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_ATTACHED" if not dry_run else "PKV_ATTACH_DRY_RUN",
                f"{'Attached' if not dry_run else 'Dry-run'} Pkv PDF "
                f"(file_ids={attach_result.file_ids}).",
            )
        )
    except AnytypeClientError as exc:
        next_state[STATE_STATUS] = "PKV_UPDATE_FAILED"
        next_state[STATE_OK] = False
        tb = traceback.format_exc()
        logger.error(
            "PKV_ATTACH_FAILED: exc=%s object_id=%s pkv_file_id=%s\n%s",
            exc,
            match.get("object_id"),
            pkv_file_id,
            tb,
        )
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_ATTACH_FAILED",
                f"Attachment failed ({type(exc).__name__}).",
            )
        )
        return next_state

    try:
        prop_result = update_pkv_properties(
            client,
            object_id=match["object_id"],
            erstattungsbetrag_eur=Decimal(str(pkv_betrag)),
            pkv_property_id=config.pkv_property_id,
            dry_run=dry_run,
        )
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_PROPERTY_UPDATED" if not dry_run else "PKV_PROPERTY_DRY_RUN",
                f"{'Applied' if not dry_run else 'Dry-run'} Pkv (€)={prop_result.value['number']} "
                f"to object {prop_result.object_id}.",
            )
        )
    except AnytypeClientError as exc:
        next_state[STATE_STATUS] = "PKV_UPDATE_FAILED"
        next_state[STATE_OK] = False
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_UPDATE_FAILED",
                f"Property update failed ({type(exc).__name__}).",
            )
        )
        return next_state

    try:
        done_result = mark_invoice_done(
            client,
            object_id=match["object_id"],
            done_property_id=config.done_property_id,
            dry_run=dry_run,
        )
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_DONE_UPDATED" if not dry_run else "PKV_DONE_DRY_RUN",
                f"{'Applied' if not dry_run else 'Dry-run'} Done=true "
                f"to object {done_result.object_id}.",
            )
        )
    except AnytypeClientError as exc:
        next_state[STATE_STATUS] = "PKV_UPDATE_FAILED"
        next_state[STATE_OK] = False
        next_state[STATE_EVENTS].append(
            _event(
                "update_pkv_anytype",
                "PKV_DONE_FAILED",
                f"Done update failed ({type(exc).__name__}).",
            )
        )
        return next_state

    next_state[STATE_STATUS] = "PKV_UPDATED" if not dry_run else "PKV_UPDATE_DRY_RUN"
    next_state[STATE_ANYTYPE_EXECUTION] = {
        "executed": not dry_run,
        "dry_run": dry_run,
        "operations": [
            {"operation": "update_pkv_properties", "dry_run": dry_run},
            {
                "operation": "attach_pkv_pdf",
                "dry_run": dry_run,
                "skipped": pkv_file_id is None,
            },
            {"operation": "mark_invoice_done", "dry_run": dry_run},
        ],
    }
    return next_state


def update_kassen_anytype(state: GraphState) -> GraphState:
    """Update Anytype invoice object with GKK (€) property from Kassenrückmeldung."""
    next_state = _copy_state(state)

    if get_ok(state) is False or get_status(state) == "KASSEN_UPLOAD_FAILED":
        next_state[STATE_EVENTS].append(
            _event(
                "update_kassen_anytype",
                "KASSEN_UPDATE_SKIPPED",
                "Skipped because previous Kassen step failed.",
            )
        )
        return next_state

    match = get_selected_match(state)
    if not match or not match.get("object_id"):
        next_state[STATE_STATUS] = "KASSEN_UPDATE_SKIPPED"
        next_state[STATE_EVENTS].append(
            _event(
                "update_kassen_anytype",
                "KASSEN_UPDATE_SKIPPED",
                "No matching invoice object to update.",
            )
        )
        return next_state

    kassen_data = get_kassen_ruckmeldung_extraction(state)
    if not kassen_data:
        next_state[STATE_STATUS] = "KASSEN_UPDATE_SKIPPED"
        next_state[STATE_EVENTS].append(
            _event(
                "update_kassen_anytype",
                "KASSEN_UPDATE_SKIPPED",
                "No validated Kassenrückmeldung to apply.",
            )
        )
        return next_state

    config = _anytype_config_from_state(state)
    client = build_anytype_client(config)
    dry_run = bool(get_anytype_dry_run(state))

    kassen_file_id = get_kassen_anytype_file_id(state)
    if kassen_file_id:
        try:
            existing_files = _existing_attachment_file_ids(
                match.get("properties", {}),
                property_id=config.attachment_property_id,
            )
            attach_result = attach_kassen_pdf(
                client,
                object_id=match["object_id"],
                kassen_file_id=kassen_file_id,
                attachment_property_id=config.attachment_property_id,
                existing_file_ids=existing_files,
                dry_run=dry_run,
            )
            next_state[STATE_EVENTS].append(
                _event(
                    "update_kassen_anytype",
                    "KASSEN_ATTACHED" if not dry_run else "KASSEN_ATTACH_DRY_RUN",
                    f"{'Attached' if not dry_run else 'Dry-run'} Kassen-PDF "
                    f"(file_ids={attach_result.file_ids}).",
                )
            )
        except AnytypeClientError as exc:
            next_state[STATE_STATUS] = "KASSEN_UPDATE_FAILED"
            next_state[STATE_OK] = False
            tb = traceback.format_exc()
            logger.error(
                "KASSEN_ATTACH_FAILED: exc=%s object_id=%s kassen_file_id=%s\n%s",
                exc,
                match.get("object_id"),
                kassen_file_id,
                tb,
            )
            next_state[STATE_EVENTS].append(
                _event(
                    "update_kassen_anytype",
                    "KASSEN_ATTACH_FAILED",
                    f"Attachment failed ({type(exc).__name__}).",
                )
            )
            return next_state
    else:
        next_state[STATE_EVENTS].append(
            _event(
                "update_kassen_anytype",
                "KASSEN_ATTACH_SKIPPED",
                "No kassen_anytype_file_id in state; skipping attachment.",
            )
        )

    try:
        raw_erstattung = kassen_data.get("erstattungsbetrag_eur")
        erstattungsbetrag_eur = _safe_decimal(raw_erstattung)
        prop_result = update_kassen_properties(
            client,
            object_id=match["object_id"],
            erstattungsbetrag_eur=erstattungsbetrag_eur,
            gkk_property_id=config.gkk_property_id,
            dry_run=dry_run,
        )
        next_state[STATE_EVENTS].append(
            _event(
                "update_kassen_anytype",
                "KASSEN_PROPERTY_UPDATED" if not dry_run else "KASSEN_PROPERTY_DRY_RUN",
                f"{'Applied' if not dry_run else 'Dry-run'} GKK (€)={prop_result.value['number']} "
                f"to object {prop_result.object_id}.",
            )
        )
    except AnytypeClientError as exc:
        next_state[STATE_STATUS] = "KASSEN_UPDATE_FAILED"
        next_state[STATE_OK] = False
        tb = traceback.format_exc()
        logger.error("update_kassen_anytype failed: %s\n%s", exc, tb)
        next_state[STATE_EVENTS].append(
            _event(
                "update_kassen_anytype",
                "KASSEN_UPDATE_FAILED",
                f"Property update failed ({type(exc).__name__}).",
            )
        )
        return next_state

    email_config = get_email_config(state)
    if email_config and email_config.get("enabled"):
        try:
            pkv_result = update_pkv_eingereicht(
                client,
                object_id=match["object_id"],
                pkv_property_id=config.pkv_eingereicht_property_id,
                dry_run=dry_run,
            )
            next_state[STATE_EVENTS].append(
                _event(
                    "update_kassen_anytype",
                    "PKV_EINGEREICHT_UPDATED" if not dry_run else "PKV_EINGEREICHT_DRY_RUN",
                    f"{'Applied' if not dry_run else 'Dry-run'} Pkv eingereicht={pkv_result.value['date']} "
                    f"to object {pkv_result.object_id}.",
                )
            )
        except AnytypeClientError as exc:
            next_state[STATE_STATUS] = "KASSEN_UPDATE_FAILED"
            next_state[STATE_OK] = False
            next_state[STATE_EVENTS].append(
                _event(
                    "update_kassen_anytype",
                    "PKV_EINGEREICHT_FAILED",
                    f"Pkv eingereicht update failed ({type(exc).__name__}).",
                )
            )
            return next_state

    next_state[STATE_STATUS] = "KASSEN_UPDATED" if not dry_run else "KASSEN_UPDATE_DRY_RUN"
    next_state[STATE_ANYTYPE_EXECUTION] = {
        "executed": not dry_run,
        "dry_run": dry_run,
        "reason": "dry_run" if dry_run else "kassen_update",
        "operations": [
            {"operation": "attach_kassen_pdf", "dry_run": dry_run},
            {"operation": "update_kassen_properties", "dry_run": dry_run},
            {
                "operation": "update_pkv_eingereicht",
                "dry_run": dry_run,
                "skipped": not (email_config and email_config.get("enabled")),
            },
        ],
    }
    return next_state


def _existing_attachment_file_ids(properties: object, *, property_id: str) -> list[str]:
    if not isinstance(properties, dict) or property_id not in properties:
        return []
    prop_value = properties[property_id]
    if not isinstance(prop_value, dict):
        return []
    value = prop_value.get("value")
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if isinstance(value, dict):
        return [str(v) for v in value.get("files", []) if v]
    return [str(v) for v in prop_value.get("files", []) if v]


def _safe_decimal(value: object) -> Decimal:
    if isinstance(value, dict):
        value = value.get("value")
    if value is None or value == "":
        raise ValueError("Decimal value is None or empty")
    text = str(value).strip().replace(",", ".")
    try:
        return Decimal(text)
    except Exception as exc:
        raise ValueError(f"Cannot convert {value!r} to Decimal: {exc}") from exc


def _copy_state(state: GraphState) -> GraphState:
    next_state = dict(state)
    next_state[STATE_EVENTS] = list(get_events(state))
    return next_state  # type: ignore[return-value]


def _event(node: str, status: str, message: str) -> GraphEvent:
    return {"node": node, "status": status, "message": message}


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
    legacy_tags = data.get("patient_tags")
    if isinstance(legacy_tags, dict):
        return tuple(PatientEntry(name=str(k), tag=str(v)) for k, v in legacy_tags.items())
    return ()


def _anytype_config_from_state(state: GraphState) -> AnytypeConfig:
    data = state.get(STATE_ANYTYPE_CONFIG, {})
    return AnytypeConfig(
        space_id=str(data.get("space_id", "")),
        collection_name=str(data.get("collection_name", "")),
        collection_id=str(data.get("collection_id", "")),
        custom_type_name=str(data.get("custom_type_name", "")),
        custom_type_key=str(data.get("custom_type_key", "")),
        dry_run=bool(get_anytype_dry_run(state)),
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
    )
