"""Tests for GraphState getter/setter helpers (TDD-first)."""

from __future__ import annotations

from typing import cast

from health_importer.graph.state import (
    STATE_ALLOWED_PATIENTS,
    STATE_ANYTYPE_CONFIG,
    STATE_ANYTYPE_DRY_RUN,
    STATE_CORRECTION_OVERRIDES,
    STATE_EMAIL_CONFIG,
    STATE_ERROR,
    STATE_EVENTS,
    STATE_FILE_ID,
    STATE_FILE_PATH,
    STATE_IMPORT_PLAN,
    STATE_INVOICE_EXTRACTION,
    STATE_KASSEN_FILE_NAMING,
    STATE_KASSEN_MATCH_AUTO_MIN,
    STATE_KASSEN_MATCH_REVIEW_MIN,
    STATE_KASSEN_RUCKMELDUNG_EXTRACTION,
    STATE_MATCHING_CANDIDATES,
    STATE_MATCHING_CONFIDENCE,
    STATE_MAX_AMOUNT_EUR,
    STATE_MAX_TOPIC_LENGTH,
    STATE_MIN_AREA_RATIO,
    STATE_MIN_PIXEL_HEIGHT,
    STATE_MIN_PIXEL_WIDTH,
    STATE_MIN_TEXT_CHARS,
    STATE_NEXT_ROUTE,
    STATE_OCR_LANGUAGE,
    STATE_OCR_TEXT,
    STATE_OCR_TEXT_QUALITY,
    STATE_OK,
    STATE_OLLAMA_BASE_URL,
    STATE_OLLAMA_TIMEOUT_SECONDS,
    STATE_PDF_TEXT,
    STATE_PKV_ANTWORT_EXTRACTION,
    STATE_RENDER_DPI,
    STATE_REQUIRED_CONFIDENCE_MIN,
    STATE_REVIEW_FOLDER,
    STATE_ROUTING_DECISION,
    STATE_SELECTED_MATCH,
    STATE_SIDECAR_POLICY,
    STATE_STATUS,
    STATE_TEXT_MODEL,
    STATE_TEXT_QUALITY,
    STATE_TEXT_VERIFICATION,
    STATE_VALIDATION,
    STATE_VISION_MODEL,
    STATE_WRITE_SIDECAR_JSON,
    GraphError,
    GraphEvent,
    GraphState,
    append_event,
    get_allowed_patients,
    get_anytype_config,
    get_anytype_dry_run,
    get_correction_overrides,
    get_done_folder,
    get_email_config,
    get_email_draft_path,
    get_error,
    get_error_folder,
    get_events,
    get_extraction_method,
    get_extraction_verification,
    get_file_id,
    get_file_name,
    get_file_naming_date_format,
    get_file_naming_pattern,
    get_file_path,
    get_file_size,
    get_import_plan,
    get_invoice_extraction,
    get_kassen_anytype_file_id,
    get_kassen_file_naming,
    get_kassen_match_thresholds,
    get_kassen_ruckmeldung_extraction,
    get_matching_candidates,
    get_matching_confidence,
    get_max_amount_eur,
    get_max_topic_length,
    get_max_vision_pages,
    get_min_area_ratio,
    get_min_pixel_height,
    get_min_pixel_width,
    get_min_text_chars,
    get_next_route,
    get_ocr_language,
    get_ocr_pdf_path,
    get_ocr_text,
    get_ocr_text_quality,
    get_ok,
    get_ollama_base_url,
    get_ollama_timeout_seconds,
    get_pdf_image_stats,
    get_pdf_text,
    get_pkv_antwort_extraction,
    get_pkv_anytype_file_id,
    get_pkv_draft_path,
    get_render_dpi,
    get_required_confidence_min,
    get_review_artifact,
    get_review_folder,
    get_routing_decision,
    get_selected_match,
    get_sha256,
    get_sidecar_payload,
    get_sidecar_policy,
    get_status,
    get_target_filename,
    get_text_model,
    get_text_quality,
    get_text_verification,
    get_validation,
    get_verify_extraction_enabled,
    get_vision_model,
    get_vision_pages,
    get_vision_pages_temp_dir,
    get_write_sidecar_json,
    set_error,
    set_file_id,
    set_import_plan,
    set_invoice_extraction,
    set_kassen_ruckmeldung_extraction,
    set_matching_candidates,
    set_matching_confidence,
    set_next_route,
    set_ocr_text,
    set_ok,
    set_pdf_text,
    set_pkv_antwort_extraction,
    set_routing_decision,
    set_selected_match,
    set_status,
    set_target_filename,
    set_text_quality,
    set_text_verification,
    set_validation,
)
from health_importer.graph.state_helpers import (
    event,
)

# ─── Constants ────────────────────────────────────────────────────


def test_state_constants() -> None:
    assert STATE_FILE_PATH == "file_path"
    assert STATE_STATUS == "status"
    assert STATE_EVENTS == "events"
    assert STATE_MIN_TEXT_CHARS == "min_text_chars"
    assert STATE_MIN_AREA_RATIO == "min_area_ratio"
    assert STATE_MIN_PIXEL_WIDTH == "min_pixel_width"
    assert STATE_MIN_PIXEL_HEIGHT == "min_pixel_height"
    assert STATE_RENDER_DPI == "render_dpi"
    assert STATE_MAX_TOPIC_LENGTH == "max_topic_length"
    assert STATE_MAX_AMOUNT_EUR == "max_amount_eur"
    assert STATE_OCR_LANGUAGE == "ocr_language"
    assert STATE_OLLAMA_BASE_URL == "ollama_base_url"
    assert STATE_TEXT_MODEL == "text_model"
    assert STATE_VISION_MODEL == "vision_model"
    assert STATE_OLLAMA_TIMEOUT_SECONDS == "ollama_timeout_seconds"
    assert STATE_ALLOWED_PATIENTS == "allowed_patients"
    assert STATE_REQUIRED_CONFIDENCE_MIN == "required_confidence_min"
    assert STATE_ANYTYPE_DRY_RUN == "anytype_dry_run"
    assert STATE_CORRECTION_OVERRIDES == "correction_overrides"
    assert STATE_SIDECAR_POLICY == "sidecar_policy"
    assert STATE_WRITE_SIDECAR_JSON == "write_sidecar_json"
    assert STATE_FILE_ID == "file_id"
    assert STATE_PDF_TEXT == "pdf_text"
    assert STATE_OCR_TEXT == "ocr_text"
    assert STATE_TEXT_QUALITY == "text_quality"
    assert STATE_OCR_TEXT_QUALITY == "ocr_text_quality"
    assert STATE_NEXT_ROUTE == "next_route"
    assert STATE_INVOICE_EXTRACTION == "invoice_extraction"
    assert STATE_KASSEN_RUCKMELDUNG_EXTRACTION == "kassen_ruckmeldung_extraction"
    assert STATE_PKV_ANTWORT_EXTRACTION == "pkv_antwort_extraction"
    assert STATE_VALIDATION == "validation"
    assert STATE_TEXT_VERIFICATION == "text_verification"
    assert STATE_ROUTING_DECISION == "routing_decision"
    assert STATE_IMPORT_PLAN == "import_plan"
    assert STATE_MATCHING_CANDIDATES == "matching_candidates"
    assert STATE_SELECTED_MATCH == "selected_match"
    assert STATE_MATCHING_CONFIDENCE == "matching_confidence"
    assert STATE_KASSEN_FILE_NAMING == "kassen_file_naming"
    assert STATE_KASSEN_MATCH_AUTO_MIN == "kassen_match_auto_min"
    assert STATE_KASSEN_MATCH_REVIEW_MIN == "kassen_match_review_min"
    assert STATE_EMAIL_CONFIG == "email_config"
    assert STATE_ANYTYPE_CONFIG == "anytype_config"
    assert STATE_ERROR == "error"
    assert STATE_OK == "ok"
    assert STATE_REVIEW_FOLDER == "review_folder"


# ─── Getter defaults ──────────────────────────────────────────────


def test_get_min_text_chars_default() -> None:
    assert get_min_text_chars(cast(GraphState, {})) == 500


def test_get_min_area_ratio_default() -> None:
    assert get_min_area_ratio(cast(GraphState, {})) == 0.01


def test_get_min_pixel_width_default() -> None:
    assert get_min_pixel_width(cast(GraphState, {})) == 80


def test_get_min_pixel_height_default() -> None:
    assert get_min_pixel_height(cast(GraphState, {})) == 40


def test_get_render_dpi_default() -> None:
    assert get_render_dpi(cast(GraphState, {})) == 220


def test_get_max_vision_pages_default() -> None:
    assert get_max_vision_pages(cast(GraphState, {})) == 3


def test_get_ocr_language_default() -> None:
    assert get_ocr_language(cast(GraphState, {})) == "deu+eng"


def test_get_ollama_base_url_default() -> None:
    assert get_ollama_base_url(cast(GraphState, {})) == "http://127.0.0.1:11434"


def test_get_text_model_default() -> None:
    assert get_text_model(cast(GraphState, {})) == "qwen3.6:35b-a3b-q8_0"


def test_get_vision_model_default() -> None:
    assert get_vision_model(cast(GraphState, {})) == "qwen3.6:35b-a3b-q8_0"


def test_get_ollama_timeout_seconds_default() -> None:
    assert get_ollama_timeout_seconds(cast(GraphState, {})) == 300


def test_get_anytype_dry_run_default() -> None:
    assert get_anytype_dry_run(cast(GraphState, {})) is True


def test_get_allowed_patients_default() -> None:
    assert get_allowed_patients(cast(GraphState, {})) == ("Max", "Anna")


def test_get_required_confidence_min_default() -> None:
    assert get_required_confidence_min(cast(GraphState, {})) == 0.8


def test_get_max_amount_eur_default() -> None:
    assert get_max_amount_eur(cast(GraphState, {})) == "5000"


def test_get_max_topic_length_default() -> None:
    assert get_max_topic_length(cast(GraphState, {})) == 60


def test_get_file_naming_pattern_default() -> None:
    assert get_file_naming_pattern(cast(GraphState, {})) == "{date}_{patient}_{topic}.pdf"


def test_get_file_naming_date_format_default() -> None:
    assert get_file_naming_date_format(cast(GraphState, {})) == "%Y_%m_%d"


def test_get_sidecar_policy_default() -> None:
    assert get_sidecar_policy(cast(GraphState, {})) == "always"


def test_get_write_sidecar_json_default() -> None:
    assert get_write_sidecar_json(cast(GraphState, {})) is True


def test_get_correction_overrides_default() -> None:
    assert get_correction_overrides(cast(GraphState, {})) == {}


def test_get_verify_extraction_enabled_default() -> None:
    assert get_verify_extraction_enabled(cast(GraphState, {})) is True


# ─── Getter missing fields return None ────────────────────────────


def test_get_file_id_default() -> None:
    assert get_file_id(cast(GraphState, {})) is None


def test_get_ocr_text_default() -> None:
    assert get_ocr_text(cast(GraphState, {})) is None


def test_get_text_quality_default() -> None:
    assert get_text_quality(cast(GraphState, {})) is None


def test_get_ocr_text_quality_default() -> None:
    assert get_ocr_text_quality(cast(GraphState, {})) is None


def test_get_next_route_default() -> None:
    assert get_next_route(cast(GraphState, {})) is None


def test_get_invoice_extraction_default() -> None:
    assert get_invoice_extraction(cast(GraphState, {})) is None


def test_get_kassen_ruckmeldung_extraction_default() -> None:
    assert get_kassen_ruckmeldung_extraction(cast(GraphState, {})) is None


def test_get_pkv_antwort_extraction_default() -> None:
    assert get_pkv_antwort_extraction(cast(GraphState, {})) is None


def test_get_validation_default() -> None:
    assert get_validation(cast(GraphState, {})) is None


def test_get_text_verification_default() -> None:
    assert get_text_verification(cast(GraphState, {})) is None


def test_get_routing_decision_default() -> None:
    assert get_routing_decision(cast(GraphState, {})) is None


def test_get_import_plan_default() -> None:
    assert get_import_plan(cast(GraphState, {})) is None


def test_get_matching_candidates_default() -> None:
    assert get_matching_candidates(cast(GraphState, {})) == []


def test_get_selected_match_default() -> None:
    assert get_selected_match(cast(GraphState, {})) is None


def test_get_matching_confidence_default() -> None:
    assert get_matching_confidence(cast(GraphState, {})) == 0.0


def test_get_kassen_file_naming_default() -> None:
    assert get_kassen_file_naming(cast(GraphState, {})) is None


def test_get_kassen_match_thresholds_default() -> None:
    assert get_kassen_match_thresholds(cast(GraphState, {})) is None


def test_get_email_config_default() -> None:
    assert get_email_config(cast(GraphState, {})) is None


def test_get_anytype_config_default() -> None:
    assert get_anytype_config(cast(GraphState, {})) is None


def test_get_error_default() -> None:
    assert get_error(cast(GraphState, {})) is None


def test_get_ok_default() -> None:
    assert get_ok(cast(GraphState, {})) is True


def test_get_review_folder_default() -> None:
    assert get_review_folder(cast(GraphState, {})) == "review"


def test_get_done_folder_default() -> None:
    assert get_done_folder(cast(GraphState, {})) == "done"


def test_get_error_folder_default() -> None:
    assert get_error_folder(cast(GraphState, {})) == "error"


def test_get_pdf_image_stats_default() -> None:
    assert get_pdf_image_stats(cast(GraphState, {})) is None


def test_get_vision_pages_temp_dir_default() -> None:
    assert get_vision_pages_temp_dir(cast(GraphState, {})) is None


def test_get_kassen_anytype_file_id_default() -> None:
    assert get_kassen_anytype_file_id(cast(GraphState, {})) is None


def test_get_pkv_anytype_file_id_default() -> None:
    assert get_pkv_anytype_file_id(cast(GraphState, {})) is None


def test_get_pkv_draft_path_default() -> None:
    assert get_pkv_draft_path(cast(GraphState, {})) is None


def test_get_extraction_method_default() -> None:
    assert get_extraction_method(cast(GraphState, {})) is None


def test_get_extraction_verification_default() -> None:
    assert get_extraction_verification(cast(GraphState, {})) is None


def test_get_email_draft_path_default() -> None:
    assert get_email_draft_path(cast(GraphState, {})) is None


def test_get_file_name_default() -> None:
    assert get_file_name(cast(GraphState, {})) is None


def test_get_file_size_default() -> None:
    assert get_file_size(cast(GraphState, {})) is None


def test_get_sha256_default() -> None:
    assert get_sha256(cast(GraphState, {})) is None


def test_get_ocr_pdf_path_default() -> None:
    assert get_ocr_pdf_path(cast(GraphState, {})) is None


def test_get_vision_pages_default() -> None:
    assert get_vision_pages(cast(GraphState, {})) is None


def test_get_sidecar_payload_default() -> None:
    assert get_sidecar_payload(cast(GraphState, {})) is None


def test_get_target_filename_default() -> None:
    assert get_target_filename(cast(GraphState, {})) is None


def test_get_review_artifact_default() -> None:
    assert get_review_artifact(cast(GraphState, {})) is None


# ─── Fields that return None when missing ─────────────────────────


def test_get_file_path_missing_returns_none() -> None:
    assert get_file_path(cast(GraphState, {})) is None


def test_get_status_missing_returns_none() -> None:
    assert get_status(cast(GraphState, {})) is None


def test_get_events_missing_returns_empty_list() -> None:
    assert get_events(cast(GraphState, {})) == []


def test_get_pdf_text_missing_returns_none() -> None:
    assert get_pdf_text(cast(GraphState, {})) is None


# ─── Getter present-value tests ───────────────────────────────────


def test_get_min_text_chars_present() -> None:
    assert get_min_text_chars(cast(GraphState, {"min_text_chars": 1000})) == 1000


def test_get_file_path_present() -> None:
    assert get_file_path(cast(GraphState, {"file_path": "/tmp/test.pdf"})) == "/tmp/test.pdf"


def test_get_status_present() -> None:
    assert get_status(cast(GraphState, {"status": "EXTRACTED"})) == "EXTRACTED"


def test_get_events_present() -> None:
    events = [{"node": "test", "status": "OK", "message": "msg"}]
    assert get_events(cast(GraphState, {"events": events})) == events


def test_get_anytype_dry_run_present() -> None:
    assert get_anytype_dry_run(cast(GraphState, {"anytype_dry_run": False})) is False


def test_get_ocr_language_present() -> None:
    assert get_ocr_language(cast(GraphState, {"ocr_language": "eng"})) == "eng"


def test_get_render_dpi_present() -> None:
    assert get_render_dpi(cast(GraphState, {"render_dpi": 300})) == 300


def test_get_file_id_present() -> None:
    assert get_file_id(cast(GraphState, {"file_id": 42})) == 42


def test_get_pdf_text_present() -> None:
    data = {"pages": [{"text": "hello"}]}
    assert get_pdf_text(cast(GraphState, {"pdf_text": data})) == data


def test_get_ocr_text_present() -> None:
    data = {"pages": [{"text": "ocr"}]}
    assert get_ocr_text(cast(GraphState, {"ocr_text": data})) == data


def test_get_next_route_present() -> None:
    assert get_next_route(cast(GraphState, {"next_route": "vision"})) == "vision"


def test_get_invoice_extraction_present() -> None:
    data = {"patient_first_name": "Max"}
    assert get_invoice_extraction(cast(GraphState, {"invoice_extraction": data})) == data


def test_get_matching_confidence_present() -> None:
    assert get_matching_confidence(cast(GraphState, {"matching_confidence": 0.85})) == 0.85


def test_get_error_present() -> None:
    err = {"type": "ValueError", "message": "boom"}
    assert get_error(cast(GraphState, {"error": err})) == err


def test_get_ok_present() -> None:
    assert get_ok(cast(GraphState, {"ok": False})) is False


# ─── Setter tests ───────────────────────────────────────────────


def test_set_status() -> None:
    state = cast(GraphState, {})
    set_status(state, "EXTRACTED")
    assert state["status"] == "EXTRACTED"


def test_set_next_route() -> None:
    state = cast(GraphState, {})
    set_next_route(state, "vision")
    assert state.get("next_route") == "vision"


def test_set_next_route_none() -> None:
    state = cast(GraphState, {})
    set_next_route(state, None)
    assert state.get("next_route") is None


def test_append_event() -> None:
    state = cast(GraphState, {"events": []})
    event: GraphEvent = {"node": "test", "status": "OK", "message": "msg"}
    append_event(state, event)
    assert state["events"] == [event]


def test_append_event_preserves_list_reference() -> None:
    state = cast(GraphState, {"events": []})
    original_list = state["events"]
    append_event(state, {"node": "test", "status": "OK", "message": "msg"})
    assert state["events"] is original_list


def test_set_invoice_extraction() -> None:
    state = cast(GraphState, {})
    data = {"patient_first_name": "Max"}
    set_invoice_extraction(state, data)
    assert state.get("invoice_extraction") == data


def test_set_kassen_ruckmeldung_extraction() -> None:
    state = cast(GraphState, {})
    data = {"erstattungsbetrag_eur": "120.50"}
    set_kassen_ruckmeldung_extraction(state, data)
    assert state.get("kassen_ruckmeldung_extraction") == data


def test_set_pkv_antwort_extraction() -> None:
    state = cast(GraphState, {})
    data = {"patient_first_name": "Anna"}
    set_pkv_antwort_extraction(state, data)
    assert state.get("pkv_antwort_extraction") == data


def test_set_validation() -> None:
    state = cast(GraphState, {})
    data = {"ok": True, "errors": []}
    set_validation(state, data)
    assert state.get("validation") == data


def test_set_text_verification() -> None:
    state = cast(GraphState, {})
    data = {"amount_found": True}
    set_text_verification(state, data)
    assert state.get("text_verification") == data


def test_set_routing_decision() -> None:
    state = cast(GraphState, {})
    data = {"action": "create"}
    set_routing_decision(state, data)
    assert state.get("routing_decision") == data


def test_set_import_plan() -> None:
    state = cast(GraphState, {})
    data = {"target_filename": "test.pdf"}
    set_import_plan(state, data)
    assert state.get("import_plan") == data


def test_set_target_filename() -> None:
    state = cast(GraphState, {})
    set_target_filename(state, "2026_05_10_Max_Test.pdf")
    assert state.get("target_filename") == "2026_05_10_Max_Test.pdf"


def test_set_target_filename_none() -> None:
    state = cast(GraphState, {})
    set_target_filename(state, None)
    assert state.get("target_filename") is None


def test_set_matching_candidates() -> None:
    state = cast(GraphState, {})
    data = [{"id": "1"}]
    set_matching_candidates(state, data)
    assert state.get("matching_candidates") == data


def test_set_selected_match() -> None:
    state = cast(GraphState, {})
    data = {"id": "1"}
    set_selected_match(state, data)
    assert state.get("selected_match") == data


def test_set_matching_confidence() -> None:
    state = cast(GraphState, {})
    set_matching_confidence(state, 0.92)
    assert state.get("matching_confidence") == 0.92


def test_set_file_id() -> None:
    state = cast(GraphState, {})
    set_file_id(state, 7)
    assert state.get("file_id") == 7


def test_set_pdf_text() -> None:
    state = cast(GraphState, {})
    data = {"total_chars": 100}
    set_pdf_text(state, data)
    assert state.get("pdf_text") == data


def test_set_ocr_text() -> None:
    state = cast(GraphState, {})
    data = {"total_chars": 200}
    set_ocr_text(state, data)
    assert state.get("ocr_text") == data


def test_set_text_quality() -> None:
    state = cast(GraphState, {})
    data = {"route": "vision"}
    set_text_quality(state, data)
    assert state.get("text_quality") == data


def test_set_error() -> None:
    state = cast(GraphState, {})
    err = cast(GraphError, {"type": "ValueError", "message": "boom"})
    set_error(state, err)
    assert state.get("error") == err


def test_set_ok() -> None:
    state = cast(GraphState, {})
    set_ok(state, True)
    assert state.get("ok") is True


# ─── Roundtrip test ───────────────────────────────────────────────


def test_roundtrip_setters_and_getters() -> None:
    state = cast(
        GraphState,
        {
            "file_path": "/tmp/test.pdf",
            "status": "NEW",
            "events": [],
        },
    )

    set_status(state, "EXTRACTED")
    set_next_route(state, "vision")
    set_pdf_text(state, {"total_chars": 500})
    set_ocr_text(state, {"total_chars": 600})
    set_text_quality(state, {"route": "vision"})
    set_invoice_extraction(state, {"patient_first_name": "Max"})
    set_validation(state, {"ok": True})
    set_text_verification(state, {"amount_found": True})
    set_routing_decision(state, {"action": "create"})
    set_import_plan(state, {"target_filename": "x.pdf"})
    set_matching_candidates(state, [{"id": "1"}])
    set_selected_match(state, {"id": "1"})
    set_matching_confidence(state, 0.95)
    set_file_id(state, 3)
    set_error(state, {"type": "X", "message": "y"})
    set_ok(state, True)
    set_target_filename(state, "x.pdf")

    assert get_file_path(state) == "/tmp/test.pdf"
    assert get_status(state) == "EXTRACTED"
    assert get_events(state) == []
    assert get_next_route(state) == "vision"
    assert get_pdf_text(state) == {"total_chars": 500}
    assert get_ocr_text(state) == {"total_chars": 600}
    assert get_text_quality(state) == {"route": "vision"}
    assert get_invoice_extraction(state) == {"patient_first_name": "Max"}
    assert get_validation(state) == {"ok": True}
    assert get_text_verification(state) == {"amount_found": True}
    assert get_routing_decision(state) == {"action": "create"}
    assert get_import_plan(state) == {"target_filename": "x.pdf"}
    assert get_matching_candidates(state) == [{"id": "1"}]
    assert get_selected_match(state) == {"id": "1"}
    assert get_matching_confidence(state) == 0.95
    assert get_file_id(state) == 3
    assert get_error(state) == {"type": "X", "message": "y"}
    assert get_ok(state) is True
    assert get_target_filename(state) == "x.pdf"


# ─── event() helper tests ─────────────────────────────────────────


def test_event_legacy_signature_returns_basic_dict() -> None:
    ev = event("node_a", "STATUS", "hello")
    assert ev == {"node": "node_a", "status": "STATUS", "message": "hello"}


def test_event_accepts_code_and_details() -> None:
    ev = event("node_b", "ERR", "oops", code="E123", details={"traceback": "tb"})
    assert "code" in ev
    assert ev["code"] == "E123"
    assert "details" in ev
    assert ev["details"] == {"traceback": "tb"}


def test_event_omits_default_severity() -> None:
    ev = event("n", "S", "m", severity="info")
    assert "severity" not in ev


def test_event_includes_non_default_severity() -> None:
    ev = event("n", "S", "m", severity="warning")
    assert "severity" in ev
    assert ev["severity"] == "warning"


def test_event_includes_file_id_when_present() -> None:
    ev = event("n", "S", "m", file_id=42)
    assert "file_id" in ev
    assert ev["file_id"] == 42
