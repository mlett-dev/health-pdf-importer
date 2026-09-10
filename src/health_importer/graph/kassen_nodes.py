from __future__ import annotations

import logging
import re
import traceback
from datetime import date
from pathlib import Path

from health_importer.ai.extractors import (
    extract_kassen_ruckmeldung_from_text,
    extract_kassen_ruckmeldung_from_vision_pages,
)
from health_importer.ai.schemas import KassenRuckmeldungExtraction
from health_importer.anytype.client import build_anytype_client
from health_importer.anytype.kassen_matching import (
    find_invoice_candidates,
    get_invoice_date,
    score_match_candidates,
)
from health_importer.anytype.kassen_upload import upload_kassen_pdf
from health_importer.config import KassenFileNamingConfig
from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_FILE_ID,
    STATE_FILE_PATH,
    STATE_KASSEN_ANYTYPE_FILE_ID,
    STATE_KASSEN_RUCKMELDUNG_EXTRACTION,
    STATE_MATCHING_CANDIDATES,
    STATE_MATCHING_CONFIDENCE,
    STATE_NEXT_ROUTE,
    STATE_OK,
    STATE_PKV_DRAFT_PATH,
    STATE_REVIEW_ARTIFACT,
    STATE_ROUTING_DECISION,
    STATE_SELECTED_MATCH,
    STATE_STATE_DB_PATH,
    STATE_STATUS,
    STATE_TARGET_FILENAME,
    STATE_VALIDATION,
    GraphState,
    get_anytype_dry_run,
    get_correction_overrides,
    get_done_folder,
    get_email_config,
    get_error_folder,
    get_events,
    get_extraction_method,
    get_file_id,
    get_file_name,
    get_file_path,
    get_kassen_file_naming,
    get_kassen_ruckmeldung_extraction,
    get_matching_candidates,
    get_matching_confidence,
    get_ok,
    get_ollama_base_url,
    get_ollama_timeout_seconds,
    get_required_confidence_min,
    get_review_folder,
    get_selected_match,
    get_sha256,
    get_sidecar_payload,
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
    safe_decimal,
    source_text_dict,
)
from health_importer.state_db import StateDb
from health_importer.workflow.filenames import generate_kassen_filename
from health_importer.workflow.kassen_review import (
    build_kassen_review_sidecar,
    move_to_kassen_review,
)
from health_importer.workflow.sidecar import (
    build_error_sidecar,
    build_kassen_done_sidecar,
    write_sidecar_if_policy,
)
from health_importer.workflow.validation import (
    ValidatedKassenRuckmeldung,
    validate_kassen_ruckmeldung,
)

logger = logging.getLogger(__name__)


def extract_kassen_ruckmeldung(state: GraphState) -> GraphState:
    """Extract structured data from a Krankenkassen-Rückmeldung PDF."""
    vision_pages = get_vision_pages(state) or []
    if str(get_extraction_method(state)).startswith("vision") and vision_pages:
        images = [(int(page["page_number"]), Path(str(page["path"]))) for page in vision_pages]
        extraction = extract_kassen_ruckmeldung_from_vision_pages(
            images,
            model=str(state.get("vision_model", get_vision_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
        )
        method = "vision"
    else:
        source_text = source_text_dict(state)
        extraction = extract_kassen_ruckmeldung_from_text(
            source_text,
            model=str(state.get("text_model", get_vision_model(state))),
            base_url=str(get_ollama_base_url(state)),
            timeout_seconds=int(get_ollama_timeout_seconds(state)),
        )
        method = "text"

    next_state = copy_state(state)
    next_state[STATE_KASSEN_RUCKMELDUNG_EXTRACTION] = extraction.model_dump(mode="json")
    next_state[STATE_STATUS] = "KASSEN_EXTRACTED"
    next_state[STATE_EVENTS].append(
        event(
            "extract_kassen_ruckmeldung",
            "KASSEN_EXTRACTED",
            f"Extracted Kassenrückmeldung data using {method}.",
        )
    )
    return next_state


def validate_kassen_ruckmeldung_node(state: GraphState) -> GraphState:
    """Validate extracted Kassenrückmeldung data."""
    raw = get_kassen_ruckmeldung_extraction(state)
    extraction = KassenRuckmeldungExtraction.model_validate(raw)

    allowed = tuple(state.get("allowed_patients", ()))
    anytype_cfg = anytype_config_from_state(state)
    result = validate_kassen_ruckmeldung(
        extraction,
        allowed_patients=allowed,
        patient_aliases=anytype_cfg.patient_alias_map,
        required_confidence_min=float(get_required_confidence_min(state)),
    )

    next_state = copy_state(state)
    if result.ok and result.kassen is not None:
        next_state[STATE_STATUS] = "KASSEN_VALIDATED"
        next_state[STATE_EVENTS].append(
            event("validate_kassen_ruckmeldung", "KASSEN_VALIDATED", "Validation passed.")
        )
    else:
        next_state[STATE_STATUS] = "KASSEN_VALIDATION_FAILED"
        next_state[STATE_EVENTS].append(
            event(
                "validate_kassen_ruckmeldung",
                "KASSEN_VALIDATION_FAILED",
                f"Errors: {result.errors}",
            )
        )

    # Store validation result in state for downstream nodes
    next_state[STATE_VALIDATION] = {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "kassen": result.kassen.__dict__ if result.kassen else None,
    }
    return next_state


def match_kassen_invoice(state: GraphState) -> GraphState:
    """Find and score matching invoice for a Kassenrückmeldung."""
    corrections = get_correction_overrides(state)
    manual_object_id = corrections.get("kassen_match_object_id") or corrections.get(
        "kassen_object_id"
    )
    if manual_object_id:
        next_state = copy_state(state)
        next_state[STATE_SELECTED_MATCH] = {
            "object_id": manual_object_id,
            "name": corrections.get("kassen_match_object_name", "Manuell zugeordnet"),
            "score": 1.0,
            "invoice_file_id": None,
            "properties": {},
        }
        next_state[STATE_MATCHING_CONFIDENCE] = 1.0
        next_state[STATE_STATUS] = "KASSEN_MATCHED_CORRECTED"
        next_state[STATE_EVENTS].append(
            event(
                "match_kassen_invoice",
                "KASSEN_MATCHED_CORRECTED",
                f"Manual correction applied: object_id={manual_object_id}",
            )
        )
        return next_state

    validation = get_validation(state) or {}
    kassen_data = validation.get("kassen")
    if not kassen_data:
        next_state = copy_state(state)
        next_state[STATE_STATUS] = "KASSEN_MATCHING_FAILED"
        next_state[STATE_EVENTS].append(
            event("match_kassen_invoice", "KASSEN_MATCHING_FAILED", "No validated kassen data.")
        )
        return next_state

    kassen = ValidatedKassenRuckmeldung(**kassen_data)
    config = anytype_config_from_state(state)

    client = build_anytype_client(config)
    candidates, object_properties = find_invoice_candidates(
        client, kassen.patient_first_name, config
    )

    scored = score_match_candidates(candidates, kassen, object_properties, config)

    next_state = copy_state(state)
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
        next_state[STATE_STATUS] = "KASSEN_MATCHED"
        next_state[STATE_EVENTS].append(
            event(
                "match_kassen_invoice",
                "KASSEN_MATCHED",
                f"Top match: {top.object_ref.name} (score={top.score:.2f}).",
            )
        )
    else:
        next_state[STATE_SELECTED_MATCH] = None
        next_state[STATE_MATCHING_CONFIDENCE] = 0.0
        next_state[STATE_STATUS] = "KASSEN_NO_MATCH"
        next_state[STATE_EVENTS].append(
            event("match_kassen_invoice", "KASSEN_NO_MATCH", "No invoice candidates found.")
        )

    return next_state


def decide_kassen_match(state: GraphState) -> GraphState:
    """Decide routing based on matching quality."""
    confidence = float(get_matching_confidence(state))
    auto_min = float(state.get("kassen_match_auto_min", 0.90))
    review_min = float(state.get("kassen_match_review_min", 0.60))

    next_state = copy_state(state)

    if confidence >= auto_min:
        next_state[STATE_NEXT_ROUTE] = "kassen_auto_update"
        next_state[STATE_STATUS] = "KASSEN_AUTO_MATCH"
        next_state[STATE_EVENTS].append(
            event(
                "decide_kassen_match",
                "KASSEN_AUTO_MATCH",
                f"Confidence {confidence:.2f} >= auto_min {auto_min}.",
            )
        )
    elif confidence >= review_min:
        next_state[STATE_NEXT_ROUTE] = "kassen_review_match"
        next_state[STATE_STATUS] = "KASSEN_REVIEW_MATCH"
        next_state[STATE_EVENTS].append(
            event(
                "decide_kassen_match",
                "KASSEN_REVIEW_MATCH",
                f"Confidence {confidence:.2f} >= review_min {review_min}.",
            )
        )
    else:
        next_state[STATE_NEXT_ROUTE] = "kassen_review_unclear"
        next_state[STATE_STATUS] = "KASSEN_REVIEW_UNCLEAR"
        next_state[STATE_EVENTS].append(
            event(
                "decide_kassen_match",
                "KASSEN_REVIEW_UNCLEAR",
                f"Confidence {confidence:.2f} < review_min {review_min}.",
            )
        )

    return next_state


def prepare_kassen_target_filename(state: GraphState) -> GraphState:
    """Generate target filename for Kassenrückmeldung before upload."""
    next_state = copy_state(state)
    kassen_naming = get_kassen_file_naming(state)
    if kassen_naming and kassen_naming.get("enabled"):
        raw = get_kassen_ruckmeldung_extraction(state)
        extraction = KassenRuckmeldungExtraction.model_validate(raw)
        allowed = tuple(state.get("allowed_patients", ()))
        required_confidence_min = float(get_required_confidence_min(state))
        anytype_cfg = anytype_config_from_state(state)
        validation_result = validate_kassen_ruckmeldung(
            extraction,
            allowed_patients=allowed,
            patient_aliases=anytype_cfg.patient_alias_map,
            required_confidence_min=required_confidence_min,
        )
        if validation_result.ok and validation_result.kassen is not None:
            config = KassenFileNamingConfig(**kassen_naming)
            selected_match = get_selected_match(state)
            invoice_topic = None
            if selected_match and isinstance(selected_match, dict):
                invoice_topic = selected_match.get("name")
            filename = generate_kassen_filename(
                validation_result.kassen, config, invoice_topic=invoice_topic
            )
            if filename:
                next_state[STATE_TARGET_FILENAME] = filename
                next_state[STATE_EVENTS].append(
                    event(
                        "prepare_kassen_target_filename",
                        "FILENAME_PREPARED",
                        f"Target filename: {filename}",
                    )
                )
                return next_state

    next_state[STATE_EVENTS].append(
        event(
            "prepare_kassen_target_filename",
            "FILENAME_SKIPPED",
            "No kassen file naming configured or validation failed.",
        )
    )
    return next_state


def upload_kassen_pdf_node(state: GraphState) -> GraphState:
    """Upload Kassen-PDF to Anytype, storing file reference for attachment."""
    next_state = copy_state(state)

    pdf_path = Path(state[STATE_FILE_PATH])
    file_id = get_file_id(state)
    if file_id is None:
        next_state[STATE_STATUS] = "KASSEN_UPLOAD_SKIPPED"
        next_state[STATE_EVENTS].append(
            event(
                "upload_kassen_pdf_node",
                "KASSEN_UPLOAD_SKIPPED",
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
            result = upload_kassen_pdf(
                client, db, file_id=file_id, pdf_path=pdf_path, dry_run=dry_run
            )
        else:
            result = upload_kassen_pdf(
                client, None, file_id=file_id, pdf_path=pdf_path, dry_run=dry_run
            )
        next_state[STATE_KASSEN_ANYTYPE_FILE_ID] = result.file_id
        next_state[STATE_STATUS] = "KASSEN_UPLOADED" if not dry_run else "KASSEN_UPLOAD_DRY_RUN"
        next_state[STATE_EVENTS].append(
            event(
                "upload_kassen_pdf_node",
                next_state[STATE_STATUS],
                f"{'Uploaded' if not dry_run else 'Dry-run'} Kassen-PDF "
                f"(file_id={result.file_id}, reused={result.reused}).",
            )
        )
    except Exception as exc:
        next_state[STATE_STATUS] = "KASSEN_UPLOAD_FAILED"
        next_state[STATE_OK] = False
        tb = traceback.format_exc()
        logger.error(
            "upload_kassen_pdf_node failed: exc=%s pdf_path=%s file_id=%s",
            exc,
            pdf_path,
            file_id,
        )
        next_state[STATE_EVENTS].append(
            event(
                "upload_kassen_pdf_node",
                "KASSEN_UPLOAD_FAILED",
                f"Anytype file upload failed: {exc}; traceback: {tb}",
            )
        )

    return next_state


def kassen_review_node(state: GraphState) -> GraphState:
    """Move Kassen PDF to review folder when matching is uncertain."""
    next_state = copy_state(state)
    pdf_path = Path(state[STATE_FILE_PATH])
    review_reasons = []
    if get_status(state) == "KASSEN_REVIEW_MATCH":
        review_reasons.append("Matching confidence below auto threshold.")
    elif get_status(state) == "KASSEN_REVIEW_UNCLEAR":
        review_reasons.append("No matching invoice found.")
    else:
        review_reasons.append("Review required.")

    kassen_data = get_kassen_ruckmeldung_extraction(state)
    candidates = get_matching_candidates(state)
    selected = get_selected_match(state)

    sidecar = build_kassen_review_sidecar(
        original_filename=str(get_file_name(state) or pdf_path.name),
        sha256=str(get_sha256(state)),
        extraction=kassen_data or {},
        matching_candidates=candidates,
        selected_match=selected,
        validation_errors=(get_validation(state) or {}).get("errors", []),
        validation_warnings=(get_validation(state) or {}).get("warnings", []),
        suggested_action="Manuell zuordnen" if candidates else "Kein eindeutiger Match",
    )

    review_folder = get_review_folder(state)

    logger.debug("kassen_review_node review_folder from state: %s", review_folder)
    review_dir = Path(review_folder)
    review_dir.mkdir(parents=True, exist_ok=True)
    artifact = move_to_kassen_review(
        pdf_path,
        review_dir,
        sidecar_payload=sidecar,
        review_reasons=review_reasons,
    )

    next_state[STATE_FILE_PATH] = str(artifact.pdf_path)
    next_state[STATE_ROUTING_DECISION] = {"action": "REVIEW_ONLY"}
    next_state[STATE_STATUS] = "KASSEN_REVIEWED"
    next_state[STATE_REVIEW_ARTIFACT] = {
        "pdf_path": str(artifact.pdf_path),
        "sidecar_path": str(artifact.sidecar_path),
        "markdown_path": str(artifact.markdown_path),
    }
    next_state[STATE_EVENTS].append(
        event(
            "kassen_review_node",
            "KASSEN_REVIEWED",
            f"Moved to review: {artifact.pdf_path.name}",
        )
    )
    return next_state


def _invoice_date_from_match(selected_match: dict | None, date_property_id: str) -> date | None:
    """Read the Honorarnote's Rechnungsdatum out of the matched invoice object.

    Manually corrected matches carry no properties, so fall back to the leading
    date in the object name -- invoices are titled from ``file_naming.pattern``,
    whose ``{date}`` is that very same Rechnungsdatum.
    """
    if not selected_match:
        return None

    props = selected_match.get("properties")
    if isinstance(props, dict):
        invoice_date = get_invoice_date(props, date_property_id)
        if invoice_date:
            return invoice_date

    name = selected_match.get("name")
    if name:
        match = re.match(r"(\d{4})[_-](\d{2})[_-](\d{2})", str(name))
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None
    return None


def create_pkv_draft(state: GraphState) -> GraphState:
    """Create a Pkv email draft after successful Kassen update."""
    next_state = copy_state(state)

    if get_ok(state) is False or get_status(state) == "KASSEN_UPDATE_FAILED":
        next_state[STATE_STATUS] = "KASSEN_EMAIL_SKIPPED"
        next_state[STATE_EVENTS].append(
            event(
                "create_pkv_draft",
                "EMAIL_SKIPPED",
                "Skipped because previous Kassen update failed.",
            )
        )
        return next_state

    from health_importer.email import FileOnlyProvider, build_provider
    from health_importer.email.pkv_draft import build_pkv_draft

    kassen_data = get_kassen_ruckmeldung_extraction(state) or {}
    selected_match = get_selected_match(state)

    def _field_value(key: str) -> str | None:
        v = kassen_data.get(key)
        if isinstance(v, dict):
            return v.get("value")
        return v if v is not None and v != "" else None

    erstattungsbetrag_eur = safe_decimal(kassen_data.get("erstattungsbetrag_eur"))

    anytype_config = anytype_config_from_state(state)

    invoice_pdf_path: Path | None = None
    invoice_file_id = selected_match.get("invoice_file_id") if selected_match else None
    if invoice_file_id:
        try:
            client = build_anytype_client(anytype_config)
            invoice_pdf_path = client.download_file(str(invoice_file_id))
        except Exception as exc:
            logger.warning("Failed to download invoice file %s: %s", invoice_file_id, exc)

    rechnungsdatum = _invoice_date_from_match(selected_match, anytype_config.date_property_id)

    email_config = get_email_config(state) or {}
    draft = build_pkv_draft(
        patient_first_name=str(_field_value("patient_first_name") or ""),
        bescheids_datum=_field_value("bescheids_datum"),
        erstattungsbetrag_eur=erstattungsbetrag_eur,
        rechnungsnummer=_field_value("rechnungsnummer"),
        aktenzeichen=_field_value("aktenzeichen"),
        betreffender_termin=_field_value("betreffender_termin"),
        invoice_object_name=selected_match.get("name") if selected_match else None,
        kassen_pdf_path=Path(get_file_path(state) or ""),
        invoice_pdf_path=invoice_pdf_path,
        pkv_recipient=email_config.get("pkv_recipient", "pkv-service@example.invalid"),
        subject_template=email_config.get(
            "pkv_subject_template", "Einreichung — {patient} — {date}"
        ),
        body_template=email_config.get(
            "pkv_body_template",
            (
                "Sehr geehrte Damen und Herren,\n\n"
                "hiermit reiche ich die Wahlarztrechnung für {patient} ein.\n\n"
                "{details}\n\n"
                "Mit freundlichen Grüßen,\n\n"
            ),
        ),
        sender_name=email_config.get("pkv_sender_name", ""),
        sender_policy_number=email_config.get("pkv_sender_policy_number", ""),
        rechnungsdatum=rechnungsdatum,
    )

    if email_config and email_config.get("enabled"):
        provider = build_provider(email_config)
        draft_path = provider.create_draft(draft)
    else:
        draft_folder = Path(get_review_folder(state)) / "drafts"
        provider = FileOnlyProvider(draft_folder)
        draft_path = provider.create_draft(draft)

    next_state[STATE_PKV_DRAFT_PATH] = draft_path
    next_state[STATE_STATUS] = "KASSEN_EMAIL_DRAFT_CREATED"
    next_state[STATE_EVENTS].append(
        event(
            "create_pkv_draft",
            "EMAIL_DRAFT_CREATED",
            f"Pkv draft saved: {draft_path}",
        )
    )
    return next_state


def move_kassen_to_done(state: GraphState) -> GraphState:
    """Move Kassen PDF to done or error folder depending on processing outcome."""
    next_state = copy_state(state)
    pdf_path = Path(state[STATE_FILE_PATH])

    is_failed = get_ok(state) is False or get_status(state) == "KASSEN_UPDATE_FAILED"
    target_dir = Path(get_error_folder(state)) if is_failed else Path(get_done_folder(state))
    target_dir.mkdir(parents=True, exist_ok=True)

    from health_importer.workflow.filesystem import safe_move

    move_result = safe_move(pdf_path, target_dir)
    target_path = move_result.destination
    next_state[STATE_FILE_PATH] = str(target_path)

    if "state_db_path" in state and "file_id" in state:
        db = StateDb(Path(state[STATE_STATE_DB_PATH]))
        db.initialize()
        db.set_current_path(int(state[STATE_FILE_ID]), target_path)

    # Build sidecar payload if not already present in state
    sidecar_payload = get_sidecar_payload(state)
    kassen_data = get_kassen_ruckmeldung_extraction(state) or {}
    selected_match = get_selected_match(state)
    if not sidecar_payload and is_failed:
        sidecar_payload = build_error_sidecar(
            document_type="krankenkasse_antwort",
            original_filename=str(get_file_name(state) or pdf_path.name),
            sha256=str(get_sha256(state)),
            status=str(get_status(state)),
            extraction=kassen_data,
            matched_invoice=selected_match if selected_match else None,
            events=get_events(state),
        )
    elif not sidecar_payload:
        try:
            erstattungsbetrag_eur = safe_decimal(kassen_data.get("erstattungsbetrag_eur"))
            erstattungsbetrag_str = str(erstattungsbetrag_eur)
        except Exception:
            erstattungsbetrag_str = ""
        sidecar_payload = build_kassen_done_sidecar(
            original_filename=str(get_file_name(state) or pdf_path.name),
            sha256=str(get_sha256(state)),
            extraction=kassen_data,
            matched_invoice=selected_match if selected_match else None,
            erstattungsbetrag_eur=erstattungsbetrag_str,
            events=get_events(state),
        )

    if sidecar_payload:
        write_sidecar_if_policy(
            target_path,
            sidecar_payload,
            write_sidecar_json=bool(get_write_sidecar_json(state)),
            sidecar_policy=str(get_sidecar_policy(state)),
            target_is_review_or_error=is_failed,
        )

    if is_failed:
        next_state[STATE_STATUS] = "KASSEN_ERROR"
        next_state[STATE_EVENTS].append(
            event(
                "move_kassen_to_done",
                "MOVED_TO_ERROR",
                f"Moved to error: {target_path.name}",
            )
        )
    else:
        next_state[STATE_STATUS] = "KASSEN_DONE"
        next_state[STATE_EVENTS].append(
            event(
                "move_kassen_to_done",
                "MOVED_TO_DONE",
                f"Moved to {target_path.name}",
            )
        )
    return next_state
