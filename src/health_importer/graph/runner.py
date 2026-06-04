from __future__ import annotations

import shutil
import traceback
import warnings
from pathlib import Path
from typing import Any, cast

from health_importer.config import (
    AnytypeConfig,
    ConfigError,
    EmailConfig,
    FileNamingConfig,
    KassenFileNamingConfig,
    KassenMatchConfig,
    PkvFileNamingConfig,
    is_local_http_url,
)
from health_importer.graph.state import (
    STATE_ANYTYPE_CONFIG,
    STATE_DONE_FOLDER,
    STATE_EMAIL_CONFIG,
    STATE_ERROR_FOLDER,
    STATE_FILE_ID,
    STATE_KASSEN_FILE_NAMING,
    STATE_KASSEN_MATCH_AUTO_MIN,
    STATE_KASSEN_MATCH_REVIEW_MIN,
    STATE_PKV_FILE_NAMING,
    STATE_PKV_INSURER_NAMES,
    STATE_REVIEW_FOLDER,
    STATE_STATE_DB_PATH,
    STATE_STATUS,
    GraphState,
    get_events,
    get_ok,
    get_sidecar_policy,
    get_vision_pages_temp_dir,
    get_write_sidecar_json,
)
from health_importer.state_db import StateDb
from health_importer.workflow.sidecar import should_write_sidecar, write_sidecar


def run_once(
    path: Path,
    *,
    state_db_path: Path | None = None,
    ocr_language: str = "deu+eng",
    render_dpi: int = 220,
    max_vision_pages: int = 3,
    min_text_chars: int = 500,
    min_area_ratio: float = 0.01,
    min_pixel_width: int = 80,
    min_pixel_height: int = 40,
    ollama_base_url: str = "http://127.0.0.1:11434",
    text_model: str = "qwen3.6:35b-a3b-q8_0",
    vision_model: str = "qwen3.6:35b-a3b-q8_0",
    ollama_timeout_seconds: int = 300,
    verify_extraction_enabled: bool = True,
    allowed_patients: tuple[str, ...] = ("Max", "Anna"),
    pkv_insurer_names: tuple[str, ...] = ("Uniqua", "Donau", "Merkur"),
    required_confidence_min: float = 0.8,
    max_amount_eur: str = "5000",
    file_naming: FileNamingConfig | None = None,
    anytype_config: AnytypeConfig | None = None,
    anytype_dry_run: bool = True,
    review_folder: Path | None = None,
    done_folder: Path | None = None,
    error_folder: Path | None = None,
    correction_overrides: dict | None = None,
    email_config: EmailConfig | None = None,
    kassen_file_naming: KassenFileNamingConfig | None = None,
    pkv_file_naming: PkvFileNamingConfig | None = None,
    kassen_match: KassenMatchConfig | None = None,
    allow_external_services: bool = False,
    sidecar_policy: str = "always",
    write_sidecar_json: bool = True,
) -> dict[str, Any]:
    file_naming = file_naming or FileNamingConfig(
        pattern="{date}_{patient}_{topic}.pdf",
        date_format="%Y_%m_%d",
        max_topic_length=60,
    )
    if not allow_external_services and not is_local_http_url(ollama_base_url):
        raise ConfigError(
            f"allow_external_services is false, but ollama_base_url is not local: {ollama_base_url}"
        )
    if email_config and email_config.enabled and email_config.provider != "file_only":
        if not allow_external_services:
            raise ConfigError(
                "allow_external_services is false, but email.provider is external: "
                f"{email_config.provider}"
            )
    initial_state: GraphState = {
        "file_path": str(path),
        "status": "NEW",
        "events": [],
        "ocr_language": ocr_language,
        "render_dpi": render_dpi,
        "max_vision_pages": max_vision_pages,
        "min_text_chars": min_text_chars,
        "min_area_ratio": min_area_ratio,
        "min_pixel_width": min_pixel_width,
        "min_pixel_height": min_pixel_height,
        "ollama_base_url": ollama_base_url,
        "text_model": text_model,
        "vision_model": vision_model,
        "ollama_timeout_seconds": ollama_timeout_seconds,
        "verify_extraction_enabled": verify_extraction_enabled,
        "allowed_patients": allowed_patients,
        "pkv_insurer_names": pkv_insurer_names,
        "required_confidence_min": required_confidence_min,
        "max_amount_eur": max_amount_eur,
        "max_topic_length": file_naming.max_topic_length,
        "file_naming_pattern": file_naming.pattern,
        "file_naming_date_format": file_naming.date_format,
        "anytype_dry_run": anytype_dry_run,
        "correction_overrides": correction_overrides or {},
        "sidecar_policy": sidecar_policy,
        "write_sidecar_json": write_sidecar_json,
    }
    if review_folder is not None:
        initial_state[STATE_REVIEW_FOLDER] = str(review_folder)
    if done_folder is not None:
        initial_state[STATE_DONE_FOLDER] = str(done_folder)
    if error_folder is not None:
        initial_state[STATE_ERROR_FOLDER] = str(error_folder)
    if email_config is not None:
        initial_state[STATE_EMAIL_CONFIG] = {
            "enabled": email_config.enabled,
            "provider": email_config.provider,
            "draft_folder": str(email_config.draft_folder),
            "pkv_recipient": email_config.pkv_recipient,
            "pkv_subject_template": email_config.pkv_subject_template,
            "pkv_body_template": email_config.pkv_body_template,
            "pkv_sender_name": email_config.pkv_sender_name,
            "pkv_sender_policy_number": email_config.pkv_sender_policy_number,
            "smtp_config": email_config.smtp_config,
        }
    if kassen_file_naming is not None:
        initial_state[STATE_KASSEN_FILE_NAMING] = {
            "enabled": kassen_file_naming.enabled,
            "pattern": kassen_file_naming.pattern,
            "date_format": kassen_file_naming.date_format,
            "max_topic_length": kassen_file_naming.max_topic_length,
        }
    if pkv_file_naming is not None:
        initial_state[STATE_PKV_FILE_NAMING] = {
            "enabled": pkv_file_naming.enabled,
            "pattern": pkv_file_naming.pattern,
            "date_format": pkv_file_naming.date_format,
            "max_topic_length": pkv_file_naming.max_topic_length,
        }
    initial_state[STATE_PKV_INSURER_NAMES] = pkv_insurer_names
    if kassen_match is not None:
        initial_state[STATE_KASSEN_MATCH_AUTO_MIN] = kassen_match.auto_match_min
        initial_state[STATE_KASSEN_MATCH_REVIEW_MIN] = kassen_match.review_match_min
    if anytype_config is not None:
        initial_state[STATE_ANYTYPE_CONFIG] = {
            "space_id": anytype_config.space_id,
            "collection_name": anytype_config.collection_name,
            "collection_id": anytype_config.collection_id,
            "custom_type_name": anytype_config.custom_type_name,
            "custom_type_key": anytype_config.custom_type_key,
            "gkk_property_id": anytype_config.gkk_property_id,
            "pkv_property_id": anytype_config.pkv_property_id,
            "pkv_eingereicht_property_id": anytype_config.pkv_eingereicht_property_id,
            "attachment_property_id": anytype_config.attachment_property_id,
            "done_property_id": anytype_config.done_property_id,
            "patients": [
                {"name": p.name, "tag": p.tag, "aliases": list(p.aliases)}
                for p in anytype_config.patients
            ],
            "patient_tag_property_id": anytype_config.patient_tag_property_id,
            "amount_property_id": anytype_config.amount_property_id,
            "date_property_id": anytype_config.date_property_id,
            "doctor_property_id": anytype_config.doctor_property_id,
            "extension_command": anytype_config.extension_command,
            "dry_run": anytype_dry_run,
        }
    if state_db_path:
        initial_state[STATE_STATE_DB_PATH] = str(state_db_path)
    state_db: StateDb | None = None
    file_id: int | None = None
    result: dict[str, Any] | None = None

    try:
        if state_db_path:
            state_db = StateDb(state_db_path)
            state_db.initialize()
            record, created = state_db.register_file(path)
            file_id = record.id
            if not created and record.status == "DONE":
                return {
                    "ok": True,
                    "status": "SKIPPED_DUPLICATE",
                    "file_id": record.id,
                    "sha256": record.sha256,
                    "file_path": str(path),
                    "duplicate_of_file_id": record.id,
                    "events": [
                        {
                            "node": "state_db",
                            "status": "SKIPPED_DUPLICATE",
                            "message": "File was already imported successfully.",
                        }
                    ],
                }
            state_db.begin_attempt(record.id, path)
            initial_state[STATE_FILE_ID] = record.id

        from langchain_core._api.deprecation import (
            LangChainDeprecationWarning,
            LangChainPendingDeprecationWarning,
        )

        warnings.filterwarnings(
            "ignore",
            message=".*allowed_objects.*",
            category=LangChainDeprecationWarning,
        )
        warnings.filterwarnings(
            "ignore",
            message=".*allowed_objects.*",
            category=LangChainPendingDeprecationWarning,
        )
        from health_importer.graph.build_graph import build_graph

        result = build_graph().invoke(initial_state)
    except Exception as exc:  # noqa: BLE001 - CLI must return structured failures.
        tb = traceback.format_exc()
        if state_db and file_id is not None:
            state_db.set_status(file_id, "ERROR", last_error=f"{exc}\n{tb}")
        if should_write_sidecar(
            write_sidecar_json=get_write_sidecar_json(initial_state),
            sidecar_policy=get_sidecar_policy(initial_state),
            target_is_review_or_error=True,
        ):
            # Note: initial_state events only contain pre-graph entries because
            # LangGraph.invoke() does not mutate the input dict.
            error_payload = {
                "status": "ERROR",
                "file_path": str(path),
                "error": {"type": type(exc).__name__, "message": str(exc), "traceback": tb},
                "events": get_events(initial_state),
            }
            write_sidecar(path, error_payload)
        return {
            "ok": False,
            "status": "ERROR",
            "file_id": file_id,
            "file_path": str(path),
            "events": get_events(initial_state),
            "error": {"type": type(exc).__name__, "message": str(exc), "traceback": tb},
        }
    finally:
        # LangGraph.invoke() returns a new state dict and does not mutate
        # initial_state, so the temp dir path lives in result, not initial_state.
        if result is not None:
            temp_dir = get_vision_pages_temp_dir(cast(GraphState, result))
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

    if result is None:
        return {"ok": False, "status": "ERROR", "file_path": str(path), "events": []}

    if state_db and file_id is not None:
        status = result[STATE_STATUS]
        if status in ("ERROR", "KASSEN_ERROR") or not get_ok(cast(GraphState, result)):
            db_status = "ERROR"
        elif status == "REVIEW" or status.startswith("KASSEN_REVIEW"):
            db_status = "REVIEW"
        else:
            db_status = "DONE"
        record = state_db.set_status(file_id, db_status)
        result[STATE_FILE_ID] = record.id
        result["attempt_count"] = record.attempt_count
    return {"ok": get_ok(cast(GraphState, result)), **result}
