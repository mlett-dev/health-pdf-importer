from __future__ import annotations

import shutil
from pathlib import Path

from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_FILE_NAME,
    STATE_FILE_PATH,
    STATE_FILE_SIZE,
    STATE_SHA256,
    STATE_STATUS,
    GraphEvent,
    GraphState,
    get_events,
    get_ok,
    get_routing_decision,
    get_status,
    get_vision_pages_temp_dir,
)
from health_importer.state_db import compute_sha256


def load_file_metadata(state: GraphState) -> GraphState:
    path = Path(state[STATE_FILE_PATH])
    if not path.exists():
        raise FileNotFoundError(f"Input file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a file: {path}")

    next_state = _copy_state(state)
    next_state[STATE_FILE_NAME] = path.name
    next_state[STATE_FILE_SIZE] = path.stat().st_size
    next_state[STATE_SHA256] = compute_sha256(path)
    next_state[STATE_STATUS] = "METADATA_LOADED"
    next_state[STATE_EVENTS].append(
        _event("load_file_metadata", "METADATA_LOADED", "Loaded file metadata.")
    )
    return next_state


def mark_started(state: GraphState) -> GraphState:
    next_state = _copy_state(state)
    next_state[STATE_STATUS] = "PROCESSING"
    next_state[STATE_EVENTS].append(_event("mark_started", "PROCESSING", "Started workflow."))
    return next_state


def cleanup_vision_temp(state: GraphState) -> GraphState:
    next_state = _copy_state(state)
    temp_dir = get_vision_pages_temp_dir(state)
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
        next_state.pop("vision_pages_temp_dir", None)  # type: ignore[misc]
        next_state[STATE_EVENTS].append(
            _event(
                "cleanup_vision_temp",
                "VISION_TEMP_CLEANED",
                f"Removed vision temp dir: {temp_dir}",
            )
        )
    else:
        next_state[STATE_EVENTS].append(
            _event("cleanup_vision_temp", "VISION_TEMP_CLEANED", "No vision temp dir to clean.")
        )
    return next_state


def mark_finished(state: GraphState) -> GraphState:
    next_state = _copy_state(state)
    if get_ok(state) is False or str(get_status(state)).endswith("ERROR"):
        final_status = "ERROR"
    elif (get_routing_decision(state) or {}).get("action") == "REVIEW_ONLY" or str(
        get_status(state)
    ).endswith("REVIEW"):
        final_status = "REVIEW"
    else:
        final_status = "DONE"
    next_state[STATE_STATUS] = final_status
    next_state[STATE_EVENTS].append(_event("mark_finished", final_status, "Finished workflow."))
    return next_state


def _copy_state(state: GraphState) -> GraphState:
    next_state = dict(state)
    next_state[STATE_EVENTS] = list(get_events(state))
    return next_state  # type: ignore[return-value]


def _event(node: str, status: str, message: str) -> GraphEvent:
    return {"node": node, "status": status, "message": message}
