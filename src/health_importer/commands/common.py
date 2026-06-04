from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path

from health_importer.anytype.client import AnytypeClientError, build_anytype_client
from health_importer.config import ConfigError
from health_importer.graph.runner import run_once
from health_importer.state_db import StateDb
from health_importer.watcher import scan_inbox
from health_importer.workflow.filesystem import ensure_workflow_folders, safe_move
from health_importer.workflow.sidecar import sidecar_path_for


def safe_json_dumps(obj: dict, **kwargs) -> str:
    """Serialize to JSON, converting Decimal/date to JSON-safe types."""

    class _CustomEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return float(o)
            if isinstance(o, datetime.datetime):
                return o.isoformat()
            if isinstance(o, datetime.date):
                return o.isoformat()
            return super().default(o)

    return json.dumps(
        obj, ensure_ascii=False, indent=2, sort_keys=True, cls=_CustomEncoder, **kwargs
    )


def add_dry_run_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="Force Anytype dry-run mode for this command.",
    )
    group.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Allow productive Anytype mode only when config also sets anytype.dry_run: false.",
    )


def effective_anytype_dry_run(config_dry_run: bool, args: argparse.Namespace) -> bool:
    if getattr(args, "dry_run", False):
        return True
    if getattr(args, "no_dry_run", False):
        if config_dry_run:
            raise ConfigError("--no-dry-run requires anytype.dry_run: false in config")
        return False
    return config_dry_run


def run_once_with_config(
    pdf_path: Path,
    config,
    *,
    anytype_dry_run: bool,
    correction_overrides: dict | None = None,
) -> dict:
    return run_once(
        pdf_path,
        state_db_path=config.state_db.path,
        ocr_language=config.pdf.ocr_language,
        render_dpi=config.pdf.render_dpi,
        max_vision_pages=config.pdf.max_vision_pages,
        min_text_chars=config.pdf.min_text_chars,
        min_area_ratio=config.pdf.min_area_ratio,
        min_pixel_width=config.pdf.min_pixel_width,
        min_pixel_height=config.pdf.min_pixel_height,
        ollama_base_url=config.ollama.base_url,
        text_model=config.ollama.text_model,
        vision_model=config.ollama.vision_model,
        ollama_timeout_seconds=config.ollama.timeout_seconds,
        allowed_patients=config.patients.allowed_first_names,
        pkv_insurer_names=config.pkv_insurers.names,
        required_confidence_min=config.confidence.required_fields_min,
        file_naming=config.file_naming,
        anytype_config=config.anytype,
        anytype_dry_run=anytype_dry_run,
        review_folder=config.folders.review,
        done_folder=config.folders.done,
        error_folder=config.folders.error,
        correction_overrides=correction_overrides,
        email_config=config.email,
        kassen_file_naming=config.kassen_file_naming,
        pkv_file_naming=config.pkv_file_naming,
        kassen_match=config.kassen_match,
        allow_external_services=config.privacy.allow_external_services,
        sidecar_policy=config.privacy.sidecar_policy,
        write_sidecar_json=config.privacy.write_sidecar_json,
    )


def scan_once(config, *, wait_seconds: float, anytype_dry_run: bool) -> list[dict]:
    ensure_workflow_folders(config.folders)
    results = []
    for path in scan_inbox(config.folders, wait_seconds=wait_seconds):
        sys.stderr.write(f"[health-importer] Found file: {path.name}\n")
        move_result = safe_move(path, config.folders.processing)
        sys.stderr.write(f"[health-importer] Moved to processing: {move_result.destination}\n")
        result = run_once_with_config(
            move_result.destination,
            config,
            anytype_dry_run=anytype_dry_run,
        )
        sys.stderr.write(
            f"[health-importer] Graph finished with status={result.get('status')} "
            f"file_path={result.get('file_path')}\n"
        )
        result = move_to_final_folder(move_result.destination, config, result)
        sys.stderr.write(
            f"[health-importer] Final move: {result.get('final_path')} "
            f"(folder={result.get('final_folder')})\n"
        )
        result["anytype_dry_run"] = anytype_dry_run
        result["original_path"] = str(move_result.source)
        result["processing_path"] = str(move_result.destination)
        results.append(result)
    return results


def move_to_final_folder(source: Path, config, result: dict) -> dict:
    actual_source = Path(result.get("file_path", source))
    target_dir = target_folder_for_result(config, result)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Robustness: Graph nodes may have already moved the file (e.g. move_kassen_to_done).
    if not actual_source.exists():
        candidate = target_dir / actual_source.name
        if candidate.exists():
            # File was already moved by a graph node; skip duplicate move.
            sys.stderr.write(
                f"[health-importer] File already in target dir (graph moved it): {candidate}\n"
            )
            destination = candidate
            collision_resolved = False
        else:
            raise FileNotFoundError(f"Source file does not exist: {actual_source}")
    elif actual_source.resolve(strict=False).parent == target_dir.resolve(strict=False):
        destination = actual_source
        collision_resolved = False
    else:
        move_result = safe_move(actual_source, target_dir)
        destination = move_result.destination
        collision_resolved = move_result.collision_resolved
    # Move sidecar JSON alongside PDF if it exists
    move_sidecar_if_present(actual_source, destination)

    next_result = dict(result)
    next_result["final_path"] = str(destination)
    next_result["final_folder"] = target_dir.name
    next_result["final_move_collision_resolved"] = collision_resolved
    file_id = next_result.get("file_id")
    if file_id is not None and "duplicate_of_file_id" not in next_result:
        db = StateDb(config.state_db.path)
        db.initialize()
        db.set_current_path(int(file_id), destination)
    return next_result


def move_sidecar_if_present(source_pdf: Path, destination_pdf: Path) -> None:
    source_sidecar = sidecar_path_for(source_pdf)
    if not source_sidecar.exists():
        return
    destination_sidecar = sidecar_path_for(destination_pdf)
    if source_sidecar == destination_sidecar:
        return
    if destination_sidecar.exists():
        # sidecar_path_for produces .import.json, so strip that suffix
        base_name = destination_pdf.stem
        parent = destination_sidecar.parent
        counter = 2
        while True:
            candidate = parent / f"{base_name}_{counter}.import.json"
            if not candidate.exists():
                destination_sidecar = candidate
                break
            counter += 1
    shutil.move(str(source_sidecar), str(destination_sidecar))


def target_folder_for_result(config, result: dict) -> Path:
    if not result.get("ok") or result.get("status") == "ERROR":
        return config.folders.error
    if result.get("status") == "REVIEW":
        return config.folders.review
    return config.folders.done


def record_to_json(record) -> dict:
    return {
        "id": record.id,
        "status": record.status,
        "current_path": record.current_path,
        "original_path": record.original_path,
        "attempt_count": record.attempt_count,
        "last_error": record.last_error,
        "updated_at": record.updated_at,
    }


def list_email_drafts(config) -> list[dict]:
    draft_folder = config.email.draft_folder
    drafts: list[dict] = []
    if draft_folder.exists():
        for path in sorted(draft_folder.glob("*.md")):
            drafts.append(
                {
                    "type": "local_markdown",
                    "id": str(path),
                    "path": str(path),
                    "name": path.name,
                    "mtime": path.stat().st_mtime,
                }
            )
    return drafts


def doctor_report(config) -> dict:
    checks = [
        _check_folders(config),
        _check_sqlite(config),
        _check_ocr_tools(),
        _check_ollama(config),
        _check_ollama_model(config, config.ollama.text_model, capability=None, name="text_model"),
        _check_ollama_model(
            config,
            config.ollama.vision_model,
            capability="vision",
            name="vision_model",
        ),
        _check_anytype_client(config),
    ]
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


def _check_folders(config) -> dict:
    missing = [
        name
        for name, path in vars(config.folders).items()
        if not Path(path).exists() or not Path(path).is_dir()
    ]
    return {
        "name": "folders",
        "ok": not missing,
        "message": "all workflow folders exist" if not missing else f"missing folders: {missing}",
    }


def _check_sqlite(config) -> dict:
    try:
        db = StateDb(config.state_db.path)
        db.initialize()
    except OSError as exc:
        return {"name": "sqlite", "ok": False, "message": str(exc)}
    return {"name": "sqlite", "ok": True, "message": str(config.state_db.path)}


def _check_ocr_tools() -> dict:
    missing = [tool for tool in ("ocrmypdf", "tesseract", "gs") if shutil.which(tool) is None]
    return {
        "name": "ocr_tools",
        "ok": not missing,
        "message": "ocr tools found" if not missing else f"missing tools: {missing}",
    }


def _check_ollama(config) -> dict:
    try:
        _ollama_json(config, "/api/tags")
    except (OSError, ValueError) as exc:
        return {"name": "ollama", "ok": False, "message": str(exc)}
    return {"name": "ollama", "ok": True, "message": config.ollama.base_url}


def _check_ollama_model(config, model: str, *, capability: str | None, name: str) -> dict:
    try:
        data = _ollama_json(config, "/api/show", {"model": model})
    except (OSError, ValueError) as exc:
        return {"name": name, "ok": False, "message": str(exc), "model": model}
    capabilities = data.get("capabilities") or []
    has_capability = capability is None or capability in capabilities
    return {
        "name": name,
        "ok": has_capability,
        "message": (
            "model available"
            if has_capability
            else f"model lacks required capability: {capability}"
        ),
        "model": model,
        "capabilities": capabilities,
    }


def _check_anytype_client(config) -> dict:
    try:
        client = build_anytype_client(config.anytype)
        collection = client.search_collection(config.anytype.collection_name)
    except AnytypeClientError as exc:
        return {"name": "anytype_client", "ok": False, "message": str(exc)}
    return {
        "name": "anytype_client",
        "ok": collection is not None,
        "message": "collection reachable" if collection else "collection not found",
    }


def _ollama_json(config, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{config.ollama.base_url.rstrip('/')}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"Ollama request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("Ollama response was not a JSON object")
    return result
