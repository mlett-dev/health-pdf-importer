"""Attach a Befund / Patientenbrief to the invoice object of the same visit.

Mirrors the Kassen flow, with two deliberate differences: the match is scored
on patient, doctor and treatment date only (a Befund has no amount, Aktenzeichen
or Rechnungsnummer), and a document that finds no invoice goes to the error
folder rather than review -- the invoice creates the Anytype object, so a Befund
without one has nothing to attach to and needs to be re-run after the invoice.
"""

from __future__ import annotations

import logging
import traceback
from datetime import date
from pathlib import Path

from health_importer.anytype.befund_matching import score_befund_candidates
from health_importer.anytype.client import build_anytype_client
from health_importer.anytype.kassen_matching import find_invoice_candidates
from health_importer.anytype.kassen_update import attach_kassen_pdf
from health_importer.anytype.kassen_upload import upload_kassen_pdf
from health_importer.config import BefundFileNamingConfig
from health_importer.graph.anytype_update_nodes import _existing_attachment_file_ids
from health_importer.graph.state import (
    STATE_BEFUND_ANYTYPE_FILE_ID,
    STATE_EVENTS,
    STATE_FILE_PATH,
    STATE_MATCHING_CANDIDATES,
    STATE_MATCHING_CONFIDENCE,
    STATE_NEXT_ROUTE,
    STATE_OK,
    STATE_SELECTED_MATCH,
    STATE_STATE_DB_PATH,
    STATE_STATUS,
    STATE_TARGET_FILENAME,
    GraphState,
    get_anytype_dry_run,
    get_befund_anytype_file_id,
    get_befund_file_naming,
    get_befund_match_auto_min,
    get_done_folder,
    get_error_folder,
    get_file_id,
    get_file_path,
    get_invoice_extraction,
    get_ok,
    get_selected_match,
    get_state_db_path,
    get_status,
)
from health_importer.graph.state_helpers import anytype_config_from_state, copy_state, event
from health_importer.state_db import StateDb
from health_importer.workflow.filenames import generate_befund_filename
from health_importer.workflow.validation import normalize_patient_name

logger = logging.getLogger(__name__)


def _extracted(state: GraphState, field: str) -> str | None:
    extraction = get_invoice_extraction(state) or {}
    value = (extraction.get(field) or {}).get("value")
    return str(value) if value is not None else None


def match_befund_invoice(state: GraphState) -> GraphState:
    """Find the invoice object this Befund belongs to."""
    next_state = copy_state(state)
    patient = _extracted(state, "patient_first_name")
    if not patient:
        next_state[STATE_SELECTED_MATCH] = None
        next_state[STATE_MATCHING_CONFIDENCE] = 0.0
        next_state[STATE_STATUS] = "BEFUND_NO_MATCH"
        next_state[STATE_EVENTS].append(
            event("match_befund_invoice", "BEFUND_NO_MATCH", "No patient name to search for.")
        )
        return next_state

    config = anytype_config_from_state(state)
    patient = normalize_patient_name(patient, config.patient_alias_map)
    appointment = _extracted(state, "appointment_date")
    try:
        appointment_date = date.fromisoformat(appointment) if appointment else None
    except ValueError:
        appointment_date = None

    client = build_anytype_client(config)
    candidates, object_properties = find_invoice_candidates(client, patient, config)
    scored = score_befund_candidates(
        candidates,
        patient_first_name=patient,
        doctor_name=_extracted(state, "doctor_name"),
        appointment_date=appointment_date,
        object_properties=object_properties,
        config=config,
    )

    next_state[STATE_MATCHING_CANDIDATES] = [
        {
            "object_id": c.object_ref.id,
            "name": c.object_ref.name,
            "score": c.score,
            "reasons": c.match_reasons,
            "invoice_file_id": c.invoice_file_id,
        }
        for c in scored
    ]

    if not scored:
        next_state[STATE_SELECTED_MATCH] = None
        next_state[STATE_MATCHING_CONFIDENCE] = 0.0
        next_state[STATE_STATUS] = "BEFUND_NO_MATCH"
        next_state[STATE_EVENTS].append(
            event(
                "match_befund_invoice",
                "BEFUND_NO_MATCH",
                f"No invoice candidates for patient {patient}.",
            )
        )
        return next_state

    top = scored[0]
    next_state[STATE_SELECTED_MATCH] = {
        "object_id": top.object_ref.id,
        "name": top.object_ref.name,
        "score": top.score,
        "reasons": top.match_reasons,
        "invoice_file_id": top.invoice_file_id,
        "properties": top.properties,
    }
    next_state[STATE_MATCHING_CONFIDENCE] = top.score
    next_state[STATE_STATUS] = "BEFUND_MATCHED"
    next_state[STATE_EVENTS].append(
        event(
            "match_befund_invoice",
            "BEFUND_MATCHED",
            f"Top match: {top.object_ref.name} (score={top.score:.2f}).",
        )
    )
    return next_state


def decide_befund_match(state: GraphState) -> GraphState:
    """Attach only on a confident match; anything else goes to the error folder."""
    next_state = copy_state(state)
    confidence = float(state.get(STATE_MATCHING_CONFIDENCE, 0.0) or 0.0)
    auto_min = get_befund_match_auto_min(state)

    if get_selected_match(state) and confidence >= auto_min:
        next_state[STATE_NEXT_ROUTE] = "befund_attach"
        next_state[STATE_STATUS] = "BEFUND_AUTO_MATCH"
        next_state[STATE_EVENTS].append(
            event(
                "decide_befund_match",
                "BEFUND_AUTO_MATCH",
                f"Confidence {confidence:.2f} >= auto_min {auto_min}.",
            )
        )
    else:
        next_state[STATE_NEXT_ROUTE] = "befund_no_match"
        next_state[STATE_STATUS] = "BEFUND_NO_MATCH"
        next_state[STATE_OK] = False
        next_state[STATE_EVENTS].append(
            event(
                "decide_befund_match",
                "BEFUND_NO_MATCH",
                f"Confidence {confidence:.2f} < auto_min {auto_min}; no invoice to attach to.",
            )
        )
    return next_state


def prepare_befund_target_filename(state: GraphState) -> GraphState:
    next_state = copy_state(state)
    naming = get_befund_file_naming(state)
    patient = _extracted(state, "patient_first_name")
    if not naming or not naming.get("enabled") or not patient:
        next_state[STATE_EVENTS].append(
            event(
                "prepare_befund_target_filename",
                "FILENAME_SKIPPED",
                "No befund file naming configured or no patient name.",
            )
        )
        return next_state

    config = anytype_config_from_state(state)
    appointment = _extracted(state, "appointment_date")
    try:
        appointment_date = date.fromisoformat(appointment) if appointment else None
    except ValueError:
        appointment_date = None

    filename = generate_befund_filename(
        BefundFileNamingConfig(**naming),
        appointment_date=appointment_date,
        doctor_name=_extracted(state, "doctor_name"),
        patient_first_name=normalize_patient_name(patient, config.patient_alias_map),
    )
    if filename:
        next_state[STATE_TARGET_FILENAME] = filename
        next_state[STATE_EVENTS].append(
            event(
                "prepare_befund_target_filename",
                "FILENAME_PREPARED",
                f"Target filename: {filename}",
            )
        )
    return next_state


def upload_befund_pdf(state: GraphState) -> GraphState:
    """Upload the Befund PDF, keeping the file reference for the attachment step."""
    next_state = copy_state(state)
    file_id = get_file_id(state)
    if file_id is None:
        next_state[STATE_EVENTS].append(
            event("upload_befund_pdf", "BEFUND_UPLOAD_SKIPPED", "No file_id in state.")
        )
        return next_state

    config = anytype_config_from_state(state)
    client = build_anytype_client(config)
    dry_run = bool(get_anytype_dry_run(state))
    pdf_path = Path(str(get_file_path(state)))
    db_path = get_state_db_path(state)

    try:
        db = None
        if db_path:
            db = StateDb(Path(str(db_path)))
            db.initialize()
        result = upload_kassen_pdf(
            client, db, file_id=int(file_id), pdf_path=pdf_path, dry_run=dry_run
        )
        next_state[STATE_BEFUND_ANYTYPE_FILE_ID] = result.file_id
        next_state[STATE_STATUS] = "BEFUND_UPLOADED"
        next_state[STATE_EVENTS].append(
            event(
                "upload_befund_pdf",
                "BEFUND_UPLOADED",
                f"Uploaded Befund PDF (file_id={result.file_id}, reused={result.reused}).",
            )
        )
    except Exception as exc:  # noqa: BLE001 - upload failure must not lose the document
        logger.error("BEFUND_UPLOAD_FAILED: exc=%s pdf=%s\n%s", exc, pdf_path, traceback.format_exc())
        next_state[STATE_OK] = False
        next_state[STATE_STATUS] = "BEFUND_UPLOAD_FAILED"
        next_state[STATE_EVENTS].append(
            event(
                "upload_befund_pdf",
                "BEFUND_UPLOAD_FAILED",
                f"Upload failed ({type(exc).__name__}).",
            )
        )
    return next_state


def attach_befund_to_invoice(state: GraphState) -> GraphState:
    """Append the Befund to the matched invoice object's attachment property."""
    next_state = copy_state(state)
    match = get_selected_match(state)
    befund_file_id = get_befund_anytype_file_id(state)

    if get_ok(state) is False or not match or not befund_file_id:
        # Not attaching is a failure for this flow: the whole point of a Befund
        # is to end up on its invoice object. Marking it keeps mark_finished
        # from reporting DONE and moving the file to the done folder.
        next_state[STATE_OK] = False
        next_state[STATE_STATUS] = "BEFUND_ATTACH_SKIPPED"
        next_state[STATE_EVENTS].append(
            event(
                "attach_befund_to_invoice",
                "BEFUND_ATTACH_SKIPPED",
                f"Nothing to attach (match={bool(match)}, uploaded={bool(befund_file_id)}).",
            )
        )
        return next_state

    config = anytype_config_from_state(state)
    client = build_anytype_client(config)
    dry_run = bool(get_anytype_dry_run(state))

    try:
        result = attach_kassen_pdf(
            client,
            object_id=match["object_id"],
            kassen_file_id=befund_file_id,
            attachment_property_id=config.attachment_property_id,
            existing_file_ids=_existing_attachment_file_ids(
                match.get("properties", {}), property_id=config.attachment_property_id
            ),
            dry_run=dry_run,
        )
        next_state[STATE_STATUS] = "BEFUND_ATTACHED"
        next_state[STATE_EVENTS].append(
            event(
                "attach_befund_to_invoice",
                "BEFUND_ATTACHED" if not dry_run else "BEFUND_ATTACH_DRY_RUN",
                f"{'Attached' if not dry_run else 'Dry-run'} Befund to "
                f"{match.get('name')} (file_ids={result.file_ids}).",
            )
        )
    except Exception as exc:  # noqa: BLE001 - report, then route to the error folder
        logger.error(
            "BEFUND_ATTACH_FAILED: exc=%s object_id=%s\n%s",
            exc,
            match.get("object_id"),
            traceback.format_exc(),
        )
        next_state[STATE_OK] = False
        next_state[STATE_STATUS] = "BEFUND_ATTACH_FAILED"
        next_state[STATE_EVENTS].append(
            event(
                "attach_befund_to_invoice",
                "BEFUND_ATTACH_FAILED",
                f"Attachment failed ({type(exc).__name__}).",
            )
        )
    return next_state


def move_befund_to_target(state: GraphState) -> GraphState:
    """Done when attached, error otherwise -- an unmatched Befund is re-runnable."""
    from health_importer.workflow.filesystem import safe_move

    next_state = copy_state(state)
    pdf_path = Path(str(state[STATE_FILE_PATH]))
    failed = get_ok(state) is False or get_status(state) != "BEFUND_ATTACHED"
    target_dir = Path(get_error_folder(state) if failed else get_done_folder(state))
    target_dir.mkdir(parents=True, exist_ok=True)

    moved = safe_move(pdf_path, target_dir).destination
    next_state[STATE_FILE_PATH] = str(moved)

    db_path = get_state_db_path(state)
    file_id = get_file_id(state)
    if db_path and file_id is not None:
        db = StateDb(Path(str(state[STATE_STATE_DB_PATH])))
        db.initialize()
        db.set_current_path(int(file_id), moved)

    if failed:
        # mark_finished derives the final status from ok, and the caller moves
        # the file according to that status -- without this the file would be
        # pulled back out of the error folder.
        next_state[STATE_OK] = False
    next_state[STATE_EVENTS].append(
        event(
            "move_befund_to_target",
            "BEFUND_MOVED_TO_ERROR" if failed else "BEFUND_MOVED_TO_DONE",
            f"Moved to {target_dir.name}: {moved.name}",
        )
    )
    return next_state
