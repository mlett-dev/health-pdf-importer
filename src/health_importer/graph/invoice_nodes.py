from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from health_importer.ai.extractors import (
    consolidate_vision_pages,
    extract_invoice_from_text,
    extract_invoice_from_vision_pages,
    verify_extraction,
    verify_extraction_vision,
    verify_invoice_values_vision,
)
from health_importer.ai.schemas import (
    InvoiceExtraction,
    VerificationStatus,
    VisionValueVerification,
)
from health_importer.anytype.client import AnytypeClientError, build_anytype_client
from health_importer.anytype.doctor_matching import load_doctor_candidates, match_doctor
from health_importer.anytype.file_upload import upload_pdf_once
from health_importer.anytype.invoice_object import create_invoice_object_once
from health_importer.config import FileNamingConfig
from health_importer.graph.state import (
    STATE_ANYTYPE_EXECUTION,
    STATE_EVENTS,
    STATE_EXTRACTION_METHOD,
    STATE_EXTRACTION_VERIFICATION,
    STATE_FILE_ID,
    STATE_FILE_PATH,
    STATE_IMPORT_PLAN,
    STATE_INVOICE_EXTRACTION,
    STATE_NEXT_ROUTE,
    STATE_ROUTING_DECISION,
    STATE_SIDECAR_PAYLOAD,
    STATE_STATE_DB_PATH,
    STATE_STATUS,
    STATE_TARGET_FILENAME,
    STATE_TEXT_VERIFICATION,
    STATE_VALIDATION,
    STATE_VISION_MODEL,
    STATE_VISION_PAGES,
    STATE_VISION_PAGES_TEMP_DIR,
    GraphState,
    get_anytype_dry_run,
    get_correction_overrides,
    get_done_folder,
    get_error_folder,
    get_events,
    get_extraction_method,
    get_extraction_verification,
    get_file_naming_date_format,
    get_file_naming_pattern,
    get_file_path,
    get_import_plan,
    get_invoice_extraction,
    get_max_amount_eur,
    get_max_topic_length,
    get_max_vision_pages,
    get_next_route,
    get_ocr_pdf_path,
    get_ok,
    get_ollama_base_url,
    get_ollama_timeout_seconds,
    get_pkv_insurer_names,
    get_render_dpi,
    get_required_confidence_min,
    get_review_folder,
    get_routing_decision,
    get_sha256,
    get_sidecar_payload,
    get_sidecar_policy,
    get_status,
    get_text_model,
    get_text_verification,
    get_verify_extraction_enabled,
    get_vision_model,
    get_vision_pages,
    get_write_sidecar_json,
)
from health_importer.graph.state_helpers import (
    anytype_config_from_state,
    copy_state,
    event,
    routing_decision_from_dict,
    source_text,
    source_text_dict,
    text_verification_from_dict,
    validation_from_state,
    validation_to_dict,
)
from health_importer.pdf.render import render_pages
from health_importer.state_db import StateDb
from health_importer.workflow.filenames import generate_invoice_filename
from health_importer.workflow.routing import decide_next_action
from health_importer.workflow.sidecar import build_sidecar_payload, write_sidecar_if_policy
from health_importer.workflow.text_verification import verify_amount_and_date_in_text
from health_importer.workflow.validation import (
    ValidatedInvoice,
    ValidationResult,
    doctor_patient_name_too_similar,
    validate_invoice_extraction,
)


def extract_structured_invoice(state: GraphState) -> GraphState:
    next_state = copy_state(state)
    if get_next_route(state) == "vision":
        extraction = _extract_via_vision(state)
        method = "vision"
    else:
        text = source_text_dict(state)
        extraction = extract_invoice_from_text(
            text,
            model=str(state.get("text_model", get_vision_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
            pkv_insurer_names=get_pkv_insurer_names(state),
        )
        method = "text"

        doctor_value = extraction.doctor_name.value
        patient_value = extraction.patient_first_name.value
        doctor_str = str(doctor_value) if doctor_value is not None else None
        patient_str = str(patient_value) if patient_value is not None else None
        if doctor_patient_name_too_similar(doctor_str, patient_str):
            next_state[STATE_EVENTS].append(
                event(
                    "extract_structured_invoice",
                    "DOCTOR_PATIENT_SIMILARITY_FALLBACK",
                    (
                        "Doctor name suspiciously similar to patient name "
                        f"(doctor={doctor_str!r}, patient={patient_str!r}); "
                        "falling back to vision extraction."
                    ),
                )
            )
            next_state[STATE_NEXT_ROUTE] = "vision"
            extraction = _extract_via_vision(next_state)
            method = "vision_doctor_similarity_fallback"

    next_state[STATE_INVOICE_EXTRACTION] = extraction.model_dump(mode="json")
    next_state[STATE_EXTRACTION_METHOD] = method
    next_state[STATE_STATUS] = "INVOICE_EXTRACTED"
    next_state[STATE_EVENTS].append(
        event("extract_structured_invoice", "INVOICE_EXTRACTED", f"Used {method} extraction.")
    )
    return next_state


def apply_manual_corrections(state: GraphState) -> GraphState:
    corrections = get_correction_overrides(state)
    if not corrections:
        next_state = copy_state(state)
        next_state[STATE_EVENTS].append(
            event("apply_manual_corrections", "CORRECTIONS_SKIPPED", "No manual corrections.")
        )
        return next_state

    extraction = dict(state.get(STATE_INVOICE_EXTRACTION, {}))
    for source_key, target_key in _CORRECTION_FIELD_MAP.items():
        if source_key in corrections:
            extraction[target_key] = {
                "value": corrections[source_key],
                "confidence": 1.0,
                "evidence": "manual correction",
                "page": 1,
            }

    next_state = copy_state(state)
    next_state[STATE_INVOICE_EXTRACTION] = extraction
    next_state[STATE_EVENTS].append(
        event(
            "apply_manual_corrections",
            "CORRECTIONS_APPLIED",
            f"Applied {len(corrections)} manual corrections.",
        )
    )
    return next_state


def verify_structured_invoice(state: GraphState) -> GraphState:
    if not bool(get_verify_extraction_enabled(state)):
        next_state = copy_state(state)
        next_state[STATE_EXTRACTION_VERIFICATION] = None
        next_state[STATE_EVENTS].append(
            event("verify_structured_invoice", "VERIFICATION_SKIPPED", "Verifier disabled.")
        )
        return next_state

    extraction_data = state.get(STATE_INVOICE_EXTRACTION, {})
    extraction = InvoiceExtraction.model_validate(extraction_data)
    method = str(get_extraction_method(state))

    if method.startswith("vision"):
        vision_pages = get_vision_pages(state) or []
        images = [(int(page["page_number"]), Path(str(page["path"]))) for page in vision_pages]
        verification = verify_extraction_vision(
            images,
            extraction,
            model=str(state.get("vision_model", get_text_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
        )
    else:
        text = source_text(state)
        verification = verify_extraction(
            text,
            extraction,
            model=str(state.get("text_model", get_vision_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
        )
    next_state = copy_state(state)
    next_state[STATE_EXTRACTION_VERIFICATION] = (
        verification.model_dump(mode="json") if verification else None
    )
    next_state[STATE_STATUS] = "EXTRACTION_VERIFIED"
    next_state[STATE_EVENTS].append(
        event("verify_structured_invoice", "EXTRACTION_VERIFIED", "Verified extraction.")
    )
    return next_state


def validate_structured_invoice(state: GraphState) -> GraphState:
    extraction_data = state.get(STATE_INVOICE_EXTRACTION, {})
    extraction = InvoiceExtraction.model_validate(extraction_data)
    anytype_cfg = anytype_config_from_state(state)
    validation = validate_invoice_extraction(
        extraction,
        allowed_patients=tuple(state.get("allowed_patients", ("Max", "Anna"))),
        patient_aliases=anytype_cfg.patient_alias_map,
        required_confidence_min=float(get_required_confidence_min(state)),
        max_amount_eur=Decimal(str(get_max_amount_eur(state))),
        max_topic_length=int(get_max_topic_length(state)),
    )
    next_state = copy_state(state)
    next_state[STATE_VALIDATION] = validation_to_dict(validation)
    next_state[STATE_STATUS] = "VALIDATED"
    next_state[STATE_EVENTS].append(
        event("validate_structured_invoice", "VALIDATED", "Validated extracted fields.")
    )
    return next_state


def verify_invoice_text_values(state: GraphState) -> GraphState:
    validation = validation_from_state(state)
    next_state = copy_state(state)
    if not validation.ok or validation.invoice is None:
        next_state[STATE_TEXT_VERIFICATION] = {
            "amount_found": False,
            "date_found": False,
            "amount_candidates": [],
            "date_candidates": [],
            "warnings": [],
        }
        next_state[STATE_EVENTS].append(
            event("verify_invoice_text_values", "TEXT_VERIFICATION_SKIPPED", "Validation failed.")
        )
        return next_state

    method = str(get_extraction_method(state))
    if method.startswith("vision"):
        result = _verify_invoice_values_in_vision(state, validation.invoice)
        next_state[STATE_TEXT_VERIFICATION] = {
            "source": "vision",
            "amount_found": result.amount_found,
            "date_found": result.date_found,
            "amount_candidates": [],
            "date_candidates": [],
            "amount_evidence": result.amount_evidence,
            "date_evidence": result.date_evidence,
            "warnings": result.warnings,
            "confidence": result.confidence,
        }
    else:
        result = verify_amount_and_date_in_text(
            source_text(state),
            amount=validation.invoice.total_amount_eur,
            target_date=validation.invoice.date,
        )
        next_state[STATE_TEXT_VERIFICATION] = {
            "source": "text",
            "amount_found": result.amount_found,
            "date_found": result.date_found,
            "amount_candidates": [str(amount) for amount in result.amount_candidates],
            "date_candidates": [candidate.isoformat() for candidate in result.date_candidates],
            "warnings": result.warnings,
        }
    next_state[STATE_STATUS] = "TEXT_VALUES_VERIFIED"
    next_state[STATE_EVENTS].append(
        event("verify_invoice_text_values", "TEXT_VALUES_VERIFIED", "Checked amount and date.")
    )
    return next_state


def decide_import_route(state: GraphState) -> GraphState:
    validation = validation_from_state(state)
    text_verification = get_text_verification(state)
    decision = decide_next_action(
        validation,
        text_verification=text_verification_from_dict(text_verification or {}),
    )
    verification = get_extraction_verification(state)
    if verification and verification.get("status") != VerificationStatus.VALID:
        decision = decide_next_action(
            ValidationResult(
                ok=False,
                invoice=validation.invoice,
                errors=[f"verification_{verification['status']}"],
                warnings=validation.warnings + list(verification.get("issues", [])),
            ),
            text_verification=text_verification_from_dict(text_verification or {}),
        )

    next_state = copy_state(state)
    next_state[STATE_ROUTING_DECISION] = decision.to_dict()
    next_state[STATE_STATUS] = decision.action.value
    next_state[STATE_EVENTS].append(
        event("decide_import_route", decision.action.value, "Decided import route.")
    )
    return next_state


def prepare_import_plan(state: GraphState) -> GraphState:
    validation = validation_from_state(state)
    decision = state.get(STATE_ROUTING_DECISION, {})
    next_state = copy_state(state)
    plan: dict = {"routing_decision": decision, "anytype_operations": []}
    if validation.invoice is not None:
        naming_config = FileNamingConfig(
            pattern=str(get_file_naming_pattern(state)),
            date_format=str(get_file_naming_date_format(state)),
            max_topic_length=int(get_max_topic_length(state)),
        )
        plan[STATE_TARGET_FILENAME] = generate_invoice_filename(validation.invoice, naming_config)
        plan["target_object_name"] = validation.invoice.topic
    if decision["action"] in {"AUTO_CREATE", "CREATE_WITH_REVIEW_STATUS"}:
        plan["anytype_operations"] = [
            {"operation": "upload_file", "dry_run": bool(get_anytype_dry_run(state))},
            {"operation": "create_object", "dry_run": bool(get_anytype_dry_run(state))},
            {"operation": "attach_file", "dry_run": bool(get_anytype_dry_run(state))},
        ]
    sidecar_payload = build_sidecar_payload(
        original_filename=str(state.get("file_name", Path(state[STATE_FILE_PATH]).name)),
        sha256=str(get_sha256(state)),
        extraction_method=str(get_extraction_method(state)),
        llm_model=str(state.get("text_model", get_vision_model(state))),
        extracted_fields=get_invoice_extraction(state),
        validation=validation,
        routing_decision=routing_decision_from_dict(decision),
        events=get_events(state),
    )
    plan[STATE_SIDECAR_PAYLOAD] = sidecar_payload
    next_state[STATE_SIDECAR_PAYLOAD] = sidecar_payload
    next_state[STATE_IMPORT_PLAN] = plan
    next_state[STATE_EVENTS].append(
        event("prepare_import_plan", "IMPORT_PLAN_PREPARED", "Prepared local import plan.")
    )
    return next_state


def execute_anytype_import(state: GraphState) -> GraphState:
    decision = get_routing_decision(state) or {}
    if decision.get("action") not in {"AUTO_CREATE", "CREATE_WITH_REVIEW_STATUS"}:
        return _with_anytype_execution(
            state,
            {
                "executed": False,
                "reason": "route_does_not_create_anytype_object",
                "operations": [],
            },
        )
    if bool(get_anytype_dry_run(state)):
        return _with_anytype_execution(
            state,
            {
                "executed": False,
                "reason": "dry_run",
                "operations": (get_import_plan(state) or {}).get("anytype_operations", []),
            },
        )
    if "state_db_path" not in state or "file_id" not in state:
        raise AnytypeClientError("Productive Anytype import requires state_db_path and file_id")
    if "anytype_config" not in state:
        raise AnytypeClientError("Productive Anytype import requires anytype_config")

    validation = validation_from_state(state)
    if validation.invoice is None:
        raise AnytypeClientError("Productive Anytype import requires a validated invoice")

    config = anytype_config_from_state(state)
    db = StateDb(Path(state[STATE_STATE_DB_PATH]))
    db.initialize()
    client = build_anytype_client(config)
    file_id = int(state[STATE_FILE_ID])
    pdf_path = Path(state[STATE_FILE_PATH])

    operations = []
    upload_result = upload_pdf_once(client, db, file_id=file_id, pdf_path=pdf_path)
    operations.append(
        {
            "operation": "upload_file",
            "file_id": upload_result.file_ref.id,
            "reused_existing": upload_result.reused_existing,
        }
    )

    doctor_match = None
    if validation.invoice.doctor_name:
        doctor_match = match_doctor(
            validation.invoice.doctor_name,
            load_doctor_candidates(client),
        )
        operations.append(
            {
                "operation": "match_doctor",
                "status": doctor_match.status.value,
                "doctor_id": doctor_match.doctor.id if doctor_match.doctor else None,
                "review_reason": doctor_match.review_reason,
            }
        )

    object_name = (get_import_plan(state) or {}).get("target_object_name")
    object_result = create_invoice_object_once(
        client,
        db,
        file_id=file_id,
        config=config,
        invoice=validation.invoice,
        anytype_file_id=upload_result.file_ref.id,
        doctor_match=doctor_match,
        object_name=object_name,
    )
    operations.append(
        {
            "operation": "create_object",
            "object_id": object_result.object_ref.id,
            "object_name": object_result.object_ref.name,
            "reused_existing": object_result.reused_existing,
        }
    )
    operations.append(
        {
            "operation": "add_object_to_collection",
            "collection_id": config.collection_id,
            "object_id": object_result.object_ref.id,
        }
    )

    return _with_anytype_execution(
        state,
        {
            "executed": True,
            "dry_run": False,
            "anytype_file_id": upload_result.file_ref.id,
            "anytype_object_id": object_result.object_ref.id,
            "operations": operations,
        },
    )


def move_invoice_to_target(state: GraphState) -> GraphState:
    """Move invoice PDF to done, review, or error folder and write sidecar per policy."""
    next_state = copy_state(state)
    pdf_path = Path(state[STATE_FILE_PATH])
    decision = get_routing_decision(state) or {}
    action = decision.get("action", "")
    is_failed = get_ok(state) is False or get_status(state) == "ERROR"

    if is_failed:
        target_dir = Path(get_error_folder(state))
        target_is_review_or_error = True
        event_status = "MOVED_TO_ERROR"
    elif action == "REVIEW_ONLY":
        target_dir = Path(get_review_folder(state))
        target_is_review_or_error = True
        event_status = "MOVED_TO_REVIEW"
    elif action in {"AUTO_CREATE", "CREATE_WITH_REVIEW_STATUS"}:
        target_dir = Path(get_done_folder(state))
        target_is_review_or_error = action == "CREATE_WITH_REVIEW_STATUS"
        event_status = "MOVED_TO_DONE"
    else:
        next_state[STATE_EVENTS].append(
            event("move_invoice_to_target", "MOVE_SKIPPED", f"Unknown action: {action}")
        )
        return next_state

    target_dir.mkdir(parents=True, exist_ok=True)

    from health_importer.workflow.filesystem import safe_move

    move_result = safe_move(pdf_path, target_dir)
    moved_path = move_result.destination

    sidecar_payload = get_sidecar_payload(state)
    if sidecar_payload:
        sidecar_payload[STATE_EVENTS] = get_events(state)
        write_sidecar_if_policy(
            moved_path,
            sidecar_payload,
            write_sidecar_json=bool(get_write_sidecar_json(state)),
            sidecar_policy=str(get_sidecar_policy(state)),
            target_is_review_or_error=target_is_review_or_error,
        )

    if "state_db_path" in state and "file_id" in state:
        db = StateDb(Path(state[STATE_STATE_DB_PATH]))
        db.initialize()
        db.set_current_path(int(state[STATE_FILE_ID]), moved_path)

    next_state[STATE_FILE_PATH] = str(moved_path)
    next_state[STATE_EVENTS].append(
        event(
            "move_invoice_to_target",
            event_status,
            f"Moved to {target_dir.name}: {moved_path.name}",
        )
    )
    return next_state


def _extract_via_vision(state: GraphState) -> InvoiceExtraction:
    vision_pages = get_vision_pages(state) or []
    if not vision_pages:
        pdf_path = Path(get_ocr_pdf_path(state) or get_file_path(state) or "")
        render_dir = Path(tempfile.mkdtemp(prefix="health-importer-vision-"))
        state[STATE_VISION_PAGES_TEMP_DIR] = str(render_dir)  # type: ignore[typeddict-item]
        rendered_pages = render_pages(
            pdf_path,
            render_dir,
            dpi=int(get_render_dpi(state)),
            max_pages=int(get_max_vision_pages(state)),
        )
        vision_pages = [
            {
                "page_number": page.page_number,
                "path": str(page.path),
                "width": page.width,
                "height": page.height,
            }
            for page in rendered_pages
        ]
        state[STATE_VISION_PAGES] = vision_pages  # type: ignore[typeddict-item]

    pages = [(int(page["page_number"]), Path(str(page["path"]))) for page in vision_pages]
    return consolidate_vision_pages(
        extract_invoice_from_vision_pages(
            pages,
            model=str(state.get(STATE_VISION_MODEL, "")),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
            pkv_insurer_names=get_pkv_insurer_names(state),
        )
    )


def _verify_invoice_values_in_vision(
    state: GraphState,
    invoice: ValidatedInvoice,
) -> VisionValueVerification:
    vision_pages = get_vision_pages(state) or []
    images = [(int(page["page_number"]), Path(str(page["path"]))) for page in vision_pages]
    verification = verify_invoice_values_vision(
        images,
        amount=str(invoice.total_amount_eur),
        target_date=invoice.date.isoformat(),
        model=str(state.get("vision_model", get_text_model(state))),
        base_url=str(get_ollama_base_url(state)),
        timeout_seconds=int(get_ollama_timeout_seconds(state)),
    )
    if verification is None:
        return VisionValueVerification(
            amount_found=False,
            date_found=False,
            warnings=["vision_value_verification_disabled"],
            confidence=0.0,
        )
    return verification


def _with_anytype_execution(state: GraphState, execution: dict) -> GraphState:
    next_state = copy_state(state)
    next_state[STATE_ANYTYPE_EXECUTION] = execution
    status = "ANYTYPE_EXECUTED" if execution.get("executed") else "ANYTYPE_SKIPPED"
    next_state[STATE_EVENTS].append(
        event("execute_anytype_import", status, str(execution.get("reason", "Anytype done.")))
    )
    return next_state


_CORRECTION_FIELD_MAP = {
    "patient": "patient_first_name",
    "patient_first_name": "patient_first_name",
    "termin": "appointment_date",
    "appointment_date": "appointment_date",
    "thema": "topic",
    "topic": "topic",
    "betrag": "total_amount_eur",
    "total_amount_eur": "total_amount_eur",
    "arzt": "doctor_name",
    "doctor_name": "doctor_name",
}
