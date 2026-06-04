from __future__ import annotations

import logging
import traceback
from pathlib import Path

from health_importer.ai.extractors import (
    extract_pkv_antwort_from_text,
    extract_pkv_antwort_from_vision_pages,
)
from health_importer.ai.schemas import PkvAntwortExtraction
from health_importer.anytype.client import build_anytype_client
from health_importer.anytype.kassen_matching import find_invoice_candidates
from health_importer.anytype.kassen_upload import upload_kassen_pdf
from health_importer.anytype.pkv_matching import (
    has_pkv_strong_match_signal,
    score_pkv_candidates,
)
from health_importer.config import PkvFileNamingConfig
from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_FILE_PATH,
    STATE_MATCHING_CANDIDATES,
    STATE_MATCHING_CONFIDENCE,
    STATE_NEXT_ROUTE,
    STATE_OK,
    STATE_PKV_ANTWORT_EXTRACTION,
    STATE_PKV_ANYTYPE_FILE_ID,
    STATE_ROUTING_DECISION,
    STATE_SELECTED_MATCH,
    STATE_STATUS,
    STATE_TARGET_FILENAME,
    STATE_VALIDATION,
    GraphState,
    get_anytype_dry_run,
    get_correction_overrides,
    get_done_folder,
    get_error_folder,
    get_events,
    get_extraction_method,
    get_file_id,
    get_file_name,
    get_matching_candidates,
    get_matching_confidence,
    get_next_route,
    get_ok,
    get_ollama_base_url,
    get_ollama_timeout_seconds,
    get_pkv_antwort_extraction,
    get_pkv_file_naming,
    get_required_confidence_min,
    get_review_folder,
    get_selected_match,
    get_sha256,
    get_sidecar_policy,
    get_state_db_path,
    get_status,
    get_validation,
    get_vision_model,
    get_vision_pages,
    get_write_sidecar_json,
)
from health_importer.graph.state_helpers import (
    anytype_config_from_state,
    copy_state,
    event,
    pkv_from_dict,
    pkv_to_dict,
    source_text_dict,
)
from health_importer.state_db import StateDb
from health_importer.workflow.filenames import generate_pkv_filename
from health_importer.workflow.sidecar import (
    build_error_sidecar,
    build_pkv_done_sidecar,
    write_sidecar_if_policy,
)
from health_importer.workflow.validation import validate_pkv_antwort

logger = logging.getLogger(__name__)


def extract_pkv_antwort(state: GraphState) -> GraphState:
    """Extract structured data from a Pkv-Antwort PDF."""
    vision_pages = get_vision_pages(state) or []
    if str(get_extraction_method(state)).startswith("vision") and vision_pages:
        images = [(int(page["page_number"]), Path(str(page["path"]))) for page in vision_pages]
        extraction = extract_pkv_antwort_from_vision_pages(
            images,
            model=str(state.get("vision_model", get_vision_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
        )
        method = "vision"
    else:
        source_text = source_text_dict(state)
        extraction = extract_pkv_antwort_from_text(
            source_text,
            model=str(state.get("text_model", get_vision_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
        )
        method = "text"

    next_state = copy_state(state)
    next_state[STATE_PKV_ANTWORT_EXTRACTION] = extraction.model_dump(mode="json")
    next_state[STATE_STATUS] = "PKV_EXTRACTED"
    next_state[STATE_EVENTS].append(
        event(
            "extract_pkv_antwort",
            "PKV_EXTRACTED",
            f"Extracted Pkv-Antwort data using {method}.",
        )
    )
    return next_state


def validate_pkv_antwort_node(state: GraphState) -> GraphState:
    """Validate extracted Pkv-Antwort data before matching."""
    raw = get_pkv_antwort_extraction(state)
    extraction = PkvAntwortExtraction.model_validate(raw)
    anytype_cfg = anytype_config_from_state(state)
    result = validate_pkv_antwort(
        extraction,
        allowed_patients=tuple(state.get("allowed_patients", ())),
        patient_aliases=anytype_cfg.patient_alias_map,
        required_confidence_min=float(get_required_confidence_min(state)),
    )

    next_state = copy_state(state)
    if result.ok and result.pkv is not None:
        next_state[STATE_STATUS] = "PKV_VALIDATED"
        next_state[STATE_EVENTS].append(
            event("validate_pkv_antwort", "PKV_VALIDATED", "Validation passed.")
        )
    else:
        next_state[STATE_STATUS] = "PKV_VALIDATION_FAILED"
        next_state[STATE_EVENTS].append(
            event("validate_pkv_antwort", "PKV_VALIDATION_FAILED", f"Errors: {result.errors}")
        )

    next_state[STATE_VALIDATION] = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "pkv": pkv_to_dict(result.pkv) if result.pkv else None,
    }
    return next_state


def match_pkv_invoice(state: GraphState) -> GraphState:
    """Find the best matching invoice for a Pkv-Antwort."""
    next_state = copy_state(state)

    # Check for manual correction override
    corrections = get_correction_overrides(state)
    manual_object_id = corrections.get("pkv_match_object_id")
    if manual_object_id:
        next_state[STATE_SELECTED_MATCH] = {
            "object_id": manual_object_id,
            "name": "manual_correction",
            "score": 1.0,
            "invoice_file_id": None,
            "properties": {},
        }
        next_state[STATE_MATCHING_CONFIDENCE] = 1.0
        next_state[STATE_STATUS] = "PKV_MATCHED_CORRECTED"
        next_state[STATE_EVENTS].append(
            event(
                "match_pkv_invoice",
                "PKV_MATCHED_CORRECTED",
                f"Manual correction applied: object_id={manual_object_id}",
            )
        )
        return next_state

    validation = get_validation(state) or {}
    pkv_data = validation.get("pkv")
    if not pkv_data:
        next_state[STATE_STATUS] = "PKV_MATCHING_FAILED"
        next_state[STATE_EVENTS].append(
            event("match_pkv_invoice", "PKV_MATCHING_FAILED", "No validated Pkv data.")
        )
        return next_state

    pkv = pkv_from_dict(pkv_data)

    config = anytype_config_from_state(state)
    client = build_anytype_client(config)
    candidates, object_properties = find_invoice_candidates(client, pkv.patient_first_name, config)

    scored = score_pkv_candidates(
        candidates,
        pkv.patient_first_name,
        pkv.aufwendungsbetrag_eur,
        pkv.betreffender_termin,
        pkv.rechnungsnummer,
        object_properties,
        config,
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

    if scored:
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
        next_state[STATE_STATUS] = "PKV_MATCHED"
        next_state[STATE_EVENTS].append(
            event(
                "match_pkv_invoice",
                "PKV_MATCHED",
                f"Top match: {top.object_ref.name} (score={top.score:.2f}).",
            )
        )
    else:
        next_state[STATE_SELECTED_MATCH] = None
        next_state[STATE_MATCHING_CONFIDENCE] = 0.0
        next_state[STATE_STATUS] = "PKV_NO_MATCH"
        next_state[STATE_EVENTS].append(
            event("match_pkv_invoice", "PKV_NO_MATCH", "No invoice candidates found.")
        )

    return next_state


def decide_pkv_match(state: GraphState) -> GraphState:
    """Decide routing based on Pkv matching quality."""
    confidence = float(get_matching_confidence(state))
    auto_min = float(state.get("kassen_match_auto_min", 0.90))
    review_min = float(state.get("kassen_match_review_min", 0.60))

    next_state = copy_state(state)
    selected_match = get_selected_match(state) or {}
    reasons = selected_match.get("reasons") or []

    has_strong_signal = has_pkv_strong_match_signal(list(reasons))

    if confidence >= auto_min and has_strong_signal:
        next_state[STATE_NEXT_ROUTE] = "pkv_auto_update"
        next_state[STATE_STATUS] = "PKV_AUTO_MATCH"
        next_state[STATE_EVENTS].append(
            event(
                "decide_pkv_match",
                "PKV_AUTO_MATCH",
                f"Confidence {confidence:.2f} >= auto_min {auto_min} with strong signal.",
            )
        )
    elif confidence >= review_min:
        next_state[STATE_NEXT_ROUTE] = "pkv_review_match"
        next_state[STATE_STATUS] = "PKV_REVIEW_MATCH"
        next_state[STATE_EVENTS].append(
            event(
                "decide_pkv_match",
                "PKV_REVIEW_MATCH",
                f"Confidence {confidence:.2f} >= review_min {review_min}.",
            )
        )
    else:
        next_state[STATE_NEXT_ROUTE] = "pkv_review_unclear"
        next_state[STATE_STATUS] = "PKV_REVIEW_UNCLEAR"
        next_state[STATE_EVENTS].append(
            event(
                "decide_pkv_match",
                "PKV_REVIEW_UNCLEAR",
                f"Confidence {confidence:.2f} < review_min {review_min}.",
            )
        )

    return next_state


def _pkv_review_reason(state: GraphState) -> str:
    validation = get_validation(state)
    if validation and validation.get("ok") is False:
        return "PKV_VALIDATION_FAILED"
    status = str(get_status(state))
    if status == "PKV_MATCHING_FAILED":
        return status
    if get_selected_match(state) and not get_next_route(state) == "pkv_auto_update":
        return "PKV_MATCH_REVIEW"
    return status


def mark_pkv_review(state: GraphState) -> GraphState:
    """Move Pkv-Antwort to review folder with diagnostic sidecar."""
    next_state = copy_state(state)
    pdf_path = Path(state[STATE_FILE_PATH])
    review_dir = Path(get_review_folder(state))
    review_dir.mkdir(parents=True, exist_ok=True)

    from health_importer.workflow.filesystem import safe_move

    move_result = safe_move(pdf_path, review_dir)
    moved_path = move_result.destination

    sidecar = {
        "document_type": "pkv_antwort",
        "original_filename": str(get_file_name(state)),
        "sha256": str(get_sha256(state)),
        "extraction": get_pkv_antwort_extraction(state),
        "validation": get_validation(state),
        "matching_candidates": get_matching_candidates(state),
        "selected_match": get_selected_match(state),
        "review_reason": _pkv_review_reason(state),
        "suggested_action": "inspect_match_or_extraction",
        "events": get_events(state),
    }
    write_sidecar_if_policy(
        moved_path,
        sidecar,
        write_sidecar_json=bool(get_write_sidecar_json(state)),
        sidecar_policy=str(get_sidecar_policy(state)),
        target_is_review_or_error=True,
    )

    next_state[STATE_FILE_PATH] = str(moved_path)
    next_state[STATE_ROUTING_DECISION] = {"action": "REVIEW_ONLY"}
    next_state[STATE_STATUS] = "PKV_REVIEW"
    next_state[STATE_EVENTS].append(
        event(
            "mark_pkv_review",
            "PKV_REVIEW",
            f"Pkv-Antwort moved to review: {moved_path.name}",
        )
    )
    return next_state


def prepare_pkv_target_filename(state: GraphState) -> GraphState:
    """Generate target filename for Pkv-Antwort before upload."""
    next_state = copy_state(state)
    pkv_naming = get_pkv_file_naming(state)
    if pkv_naming and pkv_naming.get("enabled"):
        raw = get_pkv_antwort_extraction(state)
        extraction = PkvAntwortExtraction.model_validate(raw)
        allowed = tuple(state.get("allowed_patients", ()))
        required_confidence_min = float(get_required_confidence_min(state))
        anytype_cfg = anytype_config_from_state(state)
        validation_result = validate_pkv_antwort(
            extraction,
            allowed_patients=allowed,
            patient_aliases=anytype_cfg.patient_alias_map,
            required_confidence_min=required_confidence_min,
        )
        if validation_result.ok and validation_result.pkv is not None:
            config = PkvFileNamingConfig(**pkv_naming)
            selected_match = get_selected_match(state)
            invoice_topic = None
            if selected_match and isinstance(selected_match, dict):
                invoice_topic = selected_match.get("name")
            filename = generate_pkv_filename(
                validation_result.pkv, config, invoice_topic=invoice_topic
            )
            if filename:
                next_state[STATE_TARGET_FILENAME] = filename
                next_state[STATE_EVENTS].append(
                    event(
                        "prepare_pkv_target_filename",
                        "FILENAME_PREPARED",
                        f"Target filename: {filename}",
                    )
                )
                return next_state

    next_state[STATE_EVENTS].append(
        event(
            "prepare_pkv_target_filename",
            "FILENAME_SKIPPED",
            "No pkv file naming configured or validation failed.",
        )
    )
    return next_state


def upload_pkv_pdf_node(state: GraphState) -> GraphState:
    """Upload Pkv-Antwort-PDF to Anytype, storing file reference for attachment."""
    next_state = copy_state(state)

    pdf_path = Path(state[STATE_FILE_PATH])
    file_id = get_file_id(state)
    if file_id is None:
        next_state[STATE_STATUS] = "PKV_UPLOAD_SKIPPED"
        next_state[STATE_EVENTS].append(
            event(
                "upload_pkv_pdf_node",
                "PKV_UPLOAD_SKIPPED",
                "No file_id in state; cannot track upload.",
            )
        )
        return next_state

    config = anytype_config_from_state(state)
    client = build_anytype_client(config)
    dry_run = bool(get_anytype_dry_run(state))
    db_path = get_state_db_path(state)

    try:
        if db_path:
            db = StateDb(Path(db_path))
            db.initialize()
        else:
            db = None

        result = upload_kassen_pdf(
            client,
            db,
            file_id=int(file_id),
            pdf_path=pdf_path,
            dry_run=dry_run,
        )
        next_state[STATE_PKV_ANYTYPE_FILE_ID] = result.file_id
        next_state[STATE_EVENTS].append(
            event(
                "upload_pkv_pdf_node",
                "PKV_UPLOADED" if not dry_run else "PKV_UPLOAD_DRY_RUN",
                f"{'Uploaded' if not dry_run else 'Dry-run'} Pkv PDF: file_id={result.file_id} "
                f"(reused={result.reused}).",
            )
        )
    except Exception as exc:
        next_state[STATE_STATUS] = "PKV_UPLOAD_FAILED"
        next_state[STATE_OK] = False
        tb = traceback.format_exc()
        logger.error(
            "upload_pkv_pdf_node failed: exc=%s pdf_path=%s file_id=%s",
            exc,
            pdf_path,
            file_id,
        )
        next_state[STATE_EVENTS].append(
            event(
                "upload_pkv_pdf_node",
                "PKV_UPLOAD_FAILED",
                f"Upload failed: {exc}; traceback: {tb}",
            )
        )

    return next_state


def move_pkv_to_done(state: GraphState) -> GraphState:
    """Move Pkv-Antwort PDF to done or error folder depending on processing outcome."""
    next_state = copy_state(state)
    pdf_path = Path(state[STATE_FILE_PATH])
    is_failed = get_ok(state) is False or get_status(state) in {
        "PKV_UPLOAD_FAILED",
        "PKV_UPDATE_FAILED",
        "PKV_UPDATE_SKIPPED",
    }
    target_dir = Path(get_error_folder(state)) if is_failed else Path(get_done_folder(state))
    target_dir.mkdir(parents=True, exist_ok=True)

    from health_importer.workflow.filesystem import safe_move

    move_result = safe_move(pdf_path, target_dir)
    moved_path = move_result.destination

    selected_match = get_selected_match(state)
    if is_failed:
        sidecar_payload = build_error_sidecar(
            document_type="pkv_antwort",
            original_filename=str(get_file_name(state)),
            sha256=str(get_sha256(state)),
            status=str(get_status(state)),
            extraction=get_pkv_antwort_extraction(state),
            matched_invoice=selected_match if selected_match else None,
            events=get_events(state),
        )
    else:
        sidecar_payload = build_pkv_done_sidecar(
            original_filename=str(get_file_name(state)),
            sha256=str(get_sha256(state)),
            matched_invoice=selected_match if selected_match else None,
            status=str(get_status(state)),
            events=get_events(state),
        )
    write_sidecar_if_policy(
        moved_path,
        sidecar_payload,
        write_sidecar_json=bool(get_write_sidecar_json(state)),
        sidecar_policy=str(get_sidecar_policy(state)),
        target_is_review_or_error=is_failed,
    )

    next_state[STATE_FILE_PATH] = str(moved_path)
    if is_failed:
        next_state[STATE_STATUS] = "PKV_ERROR"
        next_state[STATE_EVENTS].append(
            event(
                "move_pkv_to_done",
                "PKV_MOVED_TO_ERROR",
                f"Moved to error: {moved_path.name}",
            )
        )
    else:
        next_state[STATE_STATUS] = "DONE"
        next_state[STATE_EVENTS].append(
            event(
                "move_pkv_to_done",
                "PKV_MOVED_TO_DONE",
                f"Moved to done: {moved_path.name}",
            )
        )
    return next_state
