from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from health_importer.observability.redaction import redact_payload_for_sidecar
from health_importer.workflow.routing import RoutingDecision
from health_importer.workflow.validation import ValidationResult


def sidecar_path_for(pdf_path: Path) -> Path:
    return pdf_path.with_suffix(".import.json")


def should_write_sidecar(
    *,
    write_sidecar_json: bool,
    sidecar_policy: str,
    target_is_review_or_error: bool,
) -> bool:
    if not write_sidecar_json or sidecar_policy == "never":
        return False
    if sidecar_policy == "always":
        return True
    if sidecar_policy == "review_error":
        return target_is_review_or_error
    raise ValueError(f"Unsupported sidecar policy: {sidecar_policy}")


def write_sidecar_if_policy(
    pdf_path: Path,
    payload: dict[str, Any],
    *,
    write_sidecar_json: bool,
    sidecar_policy: str,
    target_is_review_or_error: bool,
) -> Path | None:
    """Write sidecar only if policy allows it for the given target folder."""
    if not should_write_sidecar(
        write_sidecar_json=write_sidecar_json,
        sidecar_policy=sidecar_policy,
        target_is_review_or_error=target_is_review_or_error,
    ):
        return None
    safe_payload = redact_payload_for_sidecar(payload)
    return write_sidecar(pdf_path, safe_payload)


def build_sidecar_payload(
    *,
    original_filename: str,
    sha256: str,
    extraction_method: str,
    llm_model: str,
    extracted_fields: Any,
    validation: ValidationResult,
    routing_decision: RoutingDecision,
    anytype_object_id: str | None = None,
    events: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "original_filename": original_filename,
        "sha256": sha256,
        "extraction_method": extraction_method,
        "llm_model": llm_model,
        "extracted_fields": _to_jsonable(extracted_fields),
        "validation": _to_jsonable(validation),
        "routing_decision": routing_decision.to_dict(),
        "review_reasons": routing_decision.review_reasons,
        "anytype_object_id": anytype_object_id,
        "events": events or [],
    }


def build_kassen_done_sidecar(
    *,
    original_filename: str,
    sha256: str,
    extraction: dict[str, Any],
    matched_invoice: dict[str, Any] | None,
    erstattungsbetrag_eur: str,
    events: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "document_type": "krankenkasse_antwort",
        "original_filename": original_filename,
        "sha256": sha256,
        "extraction": extraction,
        "matched_invoice": matched_invoice,
        "erstattungsbetrag_eur": erstattungsbetrag_eur,
        "suggested_action": "auto_matched",
        "events": events or [],
    }


def build_pkv_done_sidecar(
    *,
    original_filename: str,
    sha256: str,
    matched_invoice: dict[str, Any] | None,
    status: str,
    events: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "document_type": "pkv_antwort",
        "original_filename": original_filename,
        "sha256": sha256,
        "matched_invoice": matched_invoice,
        "status": status,
        "events": events or [],
    }


def build_error_sidecar(
    *,
    document_type: str,
    original_filename: str,
    sha256: str,
    status: str,
    extraction: dict[str, Any] | None = None,
    matched_invoice: dict[str, Any] | None = None,
    events: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "document_type": document_type,
        "original_filename": original_filename,
        "sha256": sha256,
        "status": status,
        "extraction": extraction or {},
        "matched_invoice": matched_invoice,
        "suggested_action": "inspect_error",
        "events": events or [],
    }


def write_sidecar(pdf_path: Path, payload: dict[str, Any]) -> Path:
    target = sidecar_path_for(pdf_path)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default)
        + "\n",
        encoding="utf-8",
    )
    return target


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Decimal | date | datetime):
        return _json_default(value)
    return value


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
