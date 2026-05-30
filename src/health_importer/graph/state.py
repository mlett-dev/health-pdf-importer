from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NotRequired, TypedDict, cast


class GraphEvent(TypedDict):
    node: str
    status: str
    message: str
    code: NotRequired[str]
    severity: NotRequired[str]
    file_id: NotRequired[int]
    details: NotRequired[dict[str, Any]]


class GraphError(TypedDict):
    type: str
    message: str


class GraphState(TypedDict):
    file_path: str
    status: str
    events: list[GraphEvent]
    file_name: NotRequired[str]
    file_size: NotRequired[int]
    sha256: NotRequired[str]
    pdf_text: NotRequired[dict]
    ocr_pdf_path: NotRequired[str]
    ocr_text: NotRequired[dict]
    vision_pages: NotRequired[list[dict]]
    invoice_extraction: NotRequired[dict]
    kassen_ruckmeldung_extraction: NotRequired[dict]
    pkv_antwort_extraction: NotRequired[dict]
    matching_candidates: NotRequired[list[dict]]
    selected_match: NotRequired[dict | None]
    matching_confidence: NotRequired[float]
    email_draft_path: NotRequired[str | None]
    kassen_file_naming: NotRequired[dict]
    pkv_file_naming: NotRequired[dict]
    kassen_match_auto_min: NotRequired[float]
    kassen_match_review_min: NotRequired[float]
    correction_overrides: NotRequired[dict]
    extraction_method: NotRequired[str]
    extraction_verification: NotRequired[dict | None]
    validation: NotRequired[dict]
    text_verification: NotRequired[dict]
    routing_decision: NotRequired[dict]
    import_plan: NotRequired[dict]
    anytype_execution: NotRequired[dict]
    text_quality: NotRequired[dict]
    ocr_text_quality: NotRequired[dict]
    next_route: NotRequired[str | None]
    ocr_language: NotRequired[str]
    render_dpi: NotRequired[int]
    max_vision_pages: NotRequired[int]
    min_area_ratio: NotRequired[float]
    min_pixel_width: NotRequired[int]
    min_pixel_height: NotRequired[int]
    min_text_chars: NotRequired[int]
    ollama_base_url: NotRequired[str]
    text_model: NotRequired[str]
    vision_model: NotRequired[str]
    ollama_timeout_seconds: NotRequired[int]
    verify_extraction_enabled: NotRequired[bool]
    allowed_patients: NotRequired[tuple[str, ...]]
    required_confidence_min: NotRequired[float]
    max_amount_eur: NotRequired[str]
    max_topic_length: NotRequired[int]
    file_naming_pattern: NotRequired[str]
    file_naming_date_format: NotRequired[str]
    anytype_dry_run: NotRequired[bool]
    anytype_config: NotRequired[dict]
    state_db_path: NotRequired[str]
    file_id: NotRequired[int]
    error: NotRequired[GraphError]
    ok: NotRequired[bool]
    review_folder: NotRequired[str]
    done_folder: NotRequired[str]
    error_folder: NotRequired[str]
    pdf_image_stats: NotRequired[dict]
    vision_pages_temp_dir: NotRequired[str]
    kassen_anytype_file_id: NotRequired[str]
    pkv_anytype_file_id: NotRequired[str]
    pkv_draft_path: NotRequired[str]
    email_config: NotRequired[dict]
    review_artifact: NotRequired[dict]
    sidecar_policy: NotRequired[str]
    sidecar_payload: NotRequired[dict]
    write_sidecar_json: NotRequired[bool]
    target_filename: NotRequired[str | None]


# ─── State key constants ──────────────────────────────────────────

STATE_FILE_PATH = "file_path"
STATE_STATUS = "status"
STATE_EVENTS = "events"
STATE_FILE_NAME = "file_name"
STATE_FILE_SIZE = "file_size"
STATE_SHA256 = "sha256"
STATE_PDF_TEXT = "pdf_text"
STATE_OCR_PDF_PATH = "ocr_pdf_path"
STATE_OCR_TEXT = "ocr_text"
STATE_VISION_PAGES = "vision_pages"
STATE_INVOICE_EXTRACTION = "invoice_extraction"
STATE_KASSEN_RUCKMELDUNG_EXTRACTION = "kassen_ruckmeldung_extraction"
STATE_PKV_ANTWORT_EXTRACTION = "pkv_antwort_extraction"
STATE_MATCHING_CANDIDATES = "matching_candidates"
STATE_SELECTED_MATCH = "selected_match"
STATE_MATCHING_CONFIDENCE = "matching_confidence"
STATE_EMAIL_DRAFT_PATH = "email_draft_path"
STATE_KASSEN_FILE_NAMING = "kassen_file_naming"
STATE_PKV_FILE_NAMING = "pkv_file_naming"
STATE_KASSEN_MATCH_AUTO_MIN = "kassen_match_auto_min"
STATE_KASSEN_MATCH_REVIEW_MIN = "kassen_match_review_min"
STATE_CORRECTION_OVERRIDES = "correction_overrides"
STATE_EXTRACTION_METHOD = "extraction_method"
STATE_EXTRACTION_VERIFICATION = "extraction_verification"
STATE_VALIDATION = "validation"
STATE_TEXT_VERIFICATION = "text_verification"
STATE_ROUTING_DECISION = "routing_decision"
STATE_IMPORT_PLAN = "import_plan"
STATE_ANYTYPE_EXECUTION = "anytype_execution"
STATE_TEXT_QUALITY = "text_quality"
STATE_OCR_TEXT_QUALITY = "ocr_text_quality"
STATE_NEXT_ROUTE = "next_route"
STATE_OCR_LANGUAGE = "ocr_language"
STATE_RENDER_DPI = "render_dpi"
STATE_MAX_VISION_PAGES = "max_vision_pages"
STATE_MIN_AREA_RATIO = "min_area_ratio"
STATE_MIN_PIXEL_WIDTH = "min_pixel_width"
STATE_MIN_PIXEL_HEIGHT = "min_pixel_height"
STATE_MIN_TEXT_CHARS = "min_text_chars"
STATE_OLLAMA_BASE_URL = "ollama_base_url"
STATE_TEXT_MODEL = "text_model"
STATE_VISION_MODEL = "vision_model"
STATE_OLLAMA_TIMEOUT_SECONDS = "ollama_timeout_seconds"
STATE_VERIFY_EXTRACTION_ENABLED = "verify_extraction_enabled"
STATE_ALLOWED_PATIENTS = "allowed_patients"
STATE_REQUIRED_CONFIDENCE_MIN = "required_confidence_min"
STATE_MAX_AMOUNT_EUR = "max_amount_eur"
STATE_MAX_TOPIC_LENGTH = "max_topic_length"
STATE_FILE_NAMING_PATTERN = "file_naming_pattern"
STATE_FILE_NAMING_DATE_FORMAT = "file_naming_date_format"
STATE_ANYTYPE_DRY_RUN = "anytype_dry_run"
STATE_ANYTYPE_CONFIG = "anytype_config"
STATE_STATE_DB_PATH = "state_db_path"
STATE_FILE_ID = "file_id"
STATE_ERROR = "error"
STATE_OK = "ok"
STATE_REVIEW_FOLDER = "review_folder"
STATE_DONE_FOLDER = "done_folder"
STATE_ERROR_FOLDER = "error_folder"
STATE_PDF_IMAGE_STATS = "pdf_image_stats"
STATE_VISION_PAGES_TEMP_DIR = "vision_pages_temp_dir"
STATE_KASSEN_ANYTYPE_FILE_ID = "kassen_anytype_file_id"
STATE_PKV_ANYTYPE_FILE_ID = "pkv_anytype_file_id"
STATE_PKV_DRAFT_PATH = "pkv_draft_path"
STATE_EMAIL_CONFIG = "email_config"
STATE_REVIEW_ARTIFACT = "review_artifact"
STATE_SIDECAR_POLICY = "sidecar_policy"
STATE_SIDECAR_PAYLOAD = "sidecar_payload"
STATE_WRITE_SIDECAR_JSON = "write_sidecar_json"
STATE_TARGET_FILENAME = "target_filename"


# ─── Defaults ─────────────────────────────────────────────────────

_DEFAULT_OCR_LANGUAGE = "deu+eng"
_DEFAULT_RENDER_DPI = 220
_DEFAULT_MAX_VISION_PAGES = 3
_DEFAULT_MIN_TEXT_CHARS = 500
_DEFAULT_MIN_AREA_RATIO = 0.01
_DEFAULT_MIN_PIXEL_WIDTH = 80
_DEFAULT_MIN_PIXEL_HEIGHT = 40
_DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_DEFAULT_TEXT_MODEL = "qwen3.6:35b-a3b-q8_0"
_DEFAULT_VISION_MODEL = "qwen3.6:35b-a3b-q8_0"
_DEFAULT_OLLAMA_TIMEOUT_SECONDS = 300
_DEFAULT_VERIFY_EXTRACTION_ENABLED = True
_DEFAULT_ALLOWED_PATIENTS = ("Max", "Anna")
_DEFAULT_REQUIRED_CONFIDENCE_MIN = 0.8
_DEFAULT_MAX_AMOUNT_EUR = "5000"
_DEFAULT_MAX_TOPIC_LENGTH = 60
_DEFAULT_FILE_NAMING_PATTERN = "{date}_{patient}_{topic}.pdf"
_DEFAULT_FILE_NAMING_DATE_FORMAT = "%Y_%m_%d"
_DEFAULT_ANYTYPE_DRY_RUN = True
_DEFAULT_CORRECTION_OVERRIDES: dict = {}
_DEFAULT_SIDECAR_POLICY = "always"
_DEFAULT_WRITE_SIDECAR_JSON = True


# ─── Getters ──────────────────────────────────────────────────────


def get_file_path(state: GraphState) -> str | None:
    return state.get(STATE_FILE_PATH)


def get_status(state: GraphState) -> str | None:
    return state.get(STATE_STATUS)


def get_events(state: GraphState) -> Sequence[dict[str, Any]]:
    return cast(Sequence[dict[str, Any]], state.get(STATE_EVENTS, []))


def get_file_name(state: GraphState) -> str | None:
    return state.get(STATE_FILE_NAME)


def get_file_size(state: GraphState) -> int | None:
    return state.get(STATE_FILE_SIZE)


def get_sha256(state: GraphState) -> str | None:
    return state.get(STATE_SHA256)


def get_pdf_text(state: GraphState) -> dict | None:
    return state.get(STATE_PDF_TEXT)


def get_ocr_pdf_path(state: GraphState) -> str | None:
    return state.get(STATE_OCR_PDF_PATH)


def get_ocr_text(state: GraphState) -> dict | None:
    return state.get(STATE_OCR_TEXT)


def get_vision_pages(state: GraphState) -> list[dict] | None:
    return state.get(STATE_VISION_PAGES)


def get_invoice_extraction(state: GraphState) -> dict | None:
    return state.get(STATE_INVOICE_EXTRACTION)


def get_kassen_ruckmeldung_extraction(state: GraphState) -> dict | None:
    return state.get(STATE_KASSEN_RUCKMELDUNG_EXTRACTION)


def get_pkv_antwort_extraction(state: GraphState) -> dict | None:
    return state.get(STATE_PKV_ANTWORT_EXTRACTION)


def get_matching_candidates(state: GraphState) -> list[dict]:
    return state.get(STATE_MATCHING_CANDIDATES, [])


def get_selected_match(state: GraphState) -> dict | None:
    return state.get(STATE_SELECTED_MATCH)


def get_matching_confidence(state: GraphState) -> float:
    return state.get(STATE_MATCHING_CONFIDENCE, 0.0)


def get_email_draft_path(state: GraphState) -> str | None:
    return state.get(STATE_EMAIL_DRAFT_PATH)


def get_kassen_file_naming(state: GraphState) -> dict | None:
    return state.get(STATE_KASSEN_FILE_NAMING)


def get_pkv_file_naming(state: GraphState) -> dict | None:
    return state.get(STATE_PKV_FILE_NAMING)


def get_kassen_match_thresholds(state: GraphState) -> tuple[float, float] | None:
    auto_min = state.get(STATE_KASSEN_MATCH_AUTO_MIN)
    review_min = state.get(STATE_KASSEN_MATCH_REVIEW_MIN)
    if auto_min is None or review_min is None:
        return None
    return (auto_min, review_min)


def get_correction_overrides(state: GraphState) -> dict:
    return state.get(STATE_CORRECTION_OVERRIDES, _DEFAULT_CORRECTION_OVERRIDES)


def get_extraction_method(state: GraphState) -> str | None:
    return state.get(STATE_EXTRACTION_METHOD)


def get_extraction_verification(state: GraphState) -> dict | None:
    return state.get(STATE_EXTRACTION_VERIFICATION)


def get_validation(state: GraphState) -> dict | None:
    return state.get(STATE_VALIDATION)


def get_text_verification(state: GraphState) -> dict | None:
    return state.get(STATE_TEXT_VERIFICATION)


def get_routing_decision(state: GraphState) -> dict | None:
    return state.get(STATE_ROUTING_DECISION)


def get_import_plan(state: GraphState) -> dict | None:
    return state.get(STATE_IMPORT_PLAN)


def get_anytype_execution(state: GraphState) -> dict | None:
    return state.get(STATE_ANYTYPE_EXECUTION)


def get_text_quality(state: GraphState) -> dict | None:
    return state.get(STATE_TEXT_QUALITY)


def get_ocr_text_quality(state: GraphState) -> dict | None:
    return state.get(STATE_OCR_TEXT_QUALITY)


def get_next_route(state: GraphState) -> str | None:
    return state.get(STATE_NEXT_ROUTE)


def get_ocr_language(state: GraphState) -> str:
    return state.get(STATE_OCR_LANGUAGE, _DEFAULT_OCR_LANGUAGE)


def get_render_dpi(state: GraphState) -> int:
    return state.get(STATE_RENDER_DPI, _DEFAULT_RENDER_DPI)


def get_max_vision_pages(state: GraphState) -> int:
    return state.get(STATE_MAX_VISION_PAGES, _DEFAULT_MAX_VISION_PAGES)


def get_min_area_ratio(state: GraphState) -> float:
    return state.get(STATE_MIN_AREA_RATIO, _DEFAULT_MIN_AREA_RATIO)


def get_min_pixel_width(state: GraphState) -> int:
    return state.get(STATE_MIN_PIXEL_WIDTH, _DEFAULT_MIN_PIXEL_WIDTH)


def get_min_pixel_height(state: GraphState) -> int:
    return state.get(STATE_MIN_PIXEL_HEIGHT, _DEFAULT_MIN_PIXEL_HEIGHT)


def get_min_text_chars(state: GraphState) -> int:
    return state.get(STATE_MIN_TEXT_CHARS, _DEFAULT_MIN_TEXT_CHARS)


def get_ollama_base_url(state: GraphState) -> str:
    return state.get(STATE_OLLAMA_BASE_URL, _DEFAULT_OLLAMA_BASE_URL)


def get_text_model(state: GraphState) -> str:
    return state.get(STATE_TEXT_MODEL, _DEFAULT_TEXT_MODEL)


def get_vision_model(state: GraphState) -> str:
    return state.get(STATE_VISION_MODEL, _DEFAULT_VISION_MODEL)


def get_ollama_timeout_seconds(state: GraphState) -> int:
    return state.get(STATE_OLLAMA_TIMEOUT_SECONDS, _DEFAULT_OLLAMA_TIMEOUT_SECONDS)


def get_verify_extraction_enabled(state: GraphState) -> bool:
    return state.get(STATE_VERIFY_EXTRACTION_ENABLED, _DEFAULT_VERIFY_EXTRACTION_ENABLED)


def get_allowed_patients(state: GraphState) -> tuple[str, ...]:
    return state.get(STATE_ALLOWED_PATIENTS, _DEFAULT_ALLOWED_PATIENTS)


def get_required_confidence_min(state: GraphState) -> float:
    return state.get(STATE_REQUIRED_CONFIDENCE_MIN, _DEFAULT_REQUIRED_CONFIDENCE_MIN)


def get_max_amount_eur(state: GraphState) -> str:
    return state.get(STATE_MAX_AMOUNT_EUR, _DEFAULT_MAX_AMOUNT_EUR)


def get_max_topic_length(state: GraphState) -> int:
    return state.get(STATE_MAX_TOPIC_LENGTH, _DEFAULT_MAX_TOPIC_LENGTH)


def get_file_naming_pattern(state: GraphState) -> str:
    return state.get(STATE_FILE_NAMING_PATTERN, _DEFAULT_FILE_NAMING_PATTERN)


def get_file_naming_date_format(state: GraphState) -> str:
    return state.get(STATE_FILE_NAMING_DATE_FORMAT, _DEFAULT_FILE_NAMING_DATE_FORMAT)


def get_anytype_dry_run(state: GraphState) -> bool:
    return state.get(STATE_ANYTYPE_DRY_RUN, _DEFAULT_ANYTYPE_DRY_RUN)


def get_anytype_config(state: GraphState) -> dict | None:
    return state.get(STATE_ANYTYPE_CONFIG)


def get_state_db_path(state: GraphState) -> str | None:
    return state.get(STATE_STATE_DB_PATH)


def get_file_id(state: GraphState) -> int | None:
    return state.get(STATE_FILE_ID)


def get_error(state: GraphState) -> GraphError | None:
    return state.get(STATE_ERROR)


def get_ok(state: GraphState) -> bool:
    return state.get(STATE_OK, True)


def get_review_folder(state: GraphState) -> str:
    return state.get(STATE_REVIEW_FOLDER, "review")


def get_done_folder(state: GraphState) -> str:
    return state.get(STATE_DONE_FOLDER, "done")


def get_error_folder(state: GraphState) -> str:
    return state.get(STATE_ERROR_FOLDER, "error")


def get_pdf_image_stats(state: GraphState) -> dict | None:
    return state.get(STATE_PDF_IMAGE_STATS)


def get_vision_pages_temp_dir(state: GraphState) -> str | None:
    return state.get(STATE_VISION_PAGES_TEMP_DIR)


def get_kassen_anytype_file_id(state: GraphState) -> str | None:
    return state.get(STATE_KASSEN_ANYTYPE_FILE_ID)


def get_pkv_anytype_file_id(state: GraphState) -> str | None:
    return state.get(STATE_PKV_ANYTYPE_FILE_ID)


def get_pkv_draft_path(state: GraphState) -> str | None:
    return state.get(STATE_PKV_DRAFT_PATH)


def get_email_config(state: GraphState) -> dict | None:
    return state.get(STATE_EMAIL_CONFIG)


def get_review_artifact(state: GraphState) -> dict | None:
    return state.get(STATE_REVIEW_ARTIFACT)


def get_sidecar_policy(state: GraphState) -> str:
    return state.get(STATE_SIDECAR_POLICY, _DEFAULT_SIDECAR_POLICY)


def get_sidecar_payload(state: GraphState) -> dict | None:
    return state.get(STATE_SIDECAR_PAYLOAD)


def get_target_filename(state: GraphState) -> str | None:
    return state.get(STATE_TARGET_FILENAME)


def get_write_sidecar_json(state: GraphState) -> bool:
    return state.get(STATE_WRITE_SIDECAR_JSON, _DEFAULT_WRITE_SIDECAR_JSON)


# ─── Setters ──────────────────────────────────────────────────────


def set_status(state: GraphState, status: str) -> None:
    state[STATE_STATUS] = status


def set_next_route(state: GraphState, route: str | None) -> None:
    state[STATE_NEXT_ROUTE] = route


def append_event(state: GraphState, event: GraphEvent) -> None:
    state[STATE_EVENTS].append(event)


def set_invoice_extraction(state: GraphState, extraction: dict) -> None:
    state[STATE_INVOICE_EXTRACTION] = extraction


def set_kassen_ruckmeldung_extraction(state: GraphState, extraction: dict) -> None:
    state[STATE_KASSEN_RUCKMELDUNG_EXTRACTION] = extraction


def set_pkv_antwort_extraction(state: GraphState, extraction: dict) -> None:
    state[STATE_PKV_ANTWORT_EXTRACTION] = extraction


def set_validation(state: GraphState, validation: dict) -> None:
    state[STATE_VALIDATION] = validation


def set_text_verification(state: GraphState, verification: dict) -> None:
    state[STATE_TEXT_VERIFICATION] = verification


def set_routing_decision(state: GraphState, decision: dict) -> None:
    state[STATE_ROUTING_DECISION] = decision


def set_import_plan(state: GraphState, plan: dict) -> None:
    state[STATE_IMPORT_PLAN] = plan


def set_anytype_execution(state: GraphState, execution: dict) -> None:
    state[STATE_ANYTYPE_EXECUTION] = execution


def set_target_filename(state: GraphState, filename: str | None) -> None:
    state[STATE_TARGET_FILENAME] = filename


def set_matching_candidates(state: GraphState, candidates: list[dict]) -> None:
    state[STATE_MATCHING_CANDIDATES] = candidates


def set_selected_match(state: GraphState, match: dict | None) -> None:
    state[STATE_SELECTED_MATCH] = match


def set_matching_confidence(state: GraphState, confidence: float) -> None:
    state[STATE_MATCHING_CONFIDENCE] = confidence


def set_file_id(state: GraphState, file_id: int) -> None:
    state[STATE_FILE_ID] = file_id


def set_pdf_text(state: GraphState, text: dict) -> None:
    state[STATE_PDF_TEXT] = text


def set_ocr_text(state: GraphState, text: dict) -> None:
    state[STATE_OCR_TEXT] = text


def set_text_quality(state: GraphState, quality: dict) -> None:
    state[STATE_TEXT_QUALITY] = quality


def set_ocr_text_quality(state: GraphState, quality: dict) -> None:
    state[STATE_OCR_TEXT_QUALITY] = quality


def set_error(state: GraphState, error: GraphError) -> None:
    state[STATE_ERROR] = error


def set_ok(state: GraphState, ok: bool) -> None:
    state[STATE_OK] = ok
