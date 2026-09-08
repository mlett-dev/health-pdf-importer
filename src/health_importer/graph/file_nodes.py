from __future__ import annotations

import shutil
from pathlib import Path

from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_FILE_ID,
    STATE_FILE_PATH,
    STATE_IMPORT_PLAN,
    STATE_STATE_DB_PATH,
    STATE_TARGET_FILENAME,
    GraphEvent,
    GraphState,
    get_events,
    get_import_plan,
    get_target_filename,
)
from health_importer.state_db import StateDb
from health_importer.workflow.filesystem import unique_destination


def rename_file_to_target(state: GraphState) -> GraphState:
    """Rename for invoice flow (preserves backward compat with existing tests/graph)."""
    return _do_rename(state, node_name="rename_file_to_target")


def rename_kassen_file(state: GraphState) -> GraphState:
    """Rename for Kassen flow."""
    return _do_rename(state, node_name="rename_kassen_file")


def rename_befund_file(state: GraphState) -> GraphState:
    """Rename for Befund flow.

    Runs before the upload so Anytype stores the file under the final name
    rather than the scanner's.
    """
    return _do_rename(state, node_name="rename_befund_file")


def rename_pkv_file(state: GraphState) -> GraphState:
    """Rename for Pkv flow."""
    return _do_rename(state, node_name="rename_pkv_file")


def _do_rename(state: GraphState, *, node_name: str) -> GraphState:
    """Shared rename implementation used by flow-specific wrapper nodes."""
    next_state = _copy_state(state)
    plan = get_import_plan(state) or {}
    target_filename = plan.get(STATE_TARGET_FILENAME) if plan else get_target_filename(state)
    if not target_filename:
        next_state[STATE_EVENTS].append(
            _event(
                node_name,
                "RENAME_SKIPPED",
                "No target filename in plan or state.",
            )
        )
        return next_state

    pdf_path = Path(state[STATE_FILE_PATH])
    target_path = unique_destination(pdf_path.parent / target_filename)

    shutil.move(str(pdf_path), str(target_path))
    next_state[STATE_FILE_PATH] = str(target_path)

    if "state_db_path" in state and "file_id" in state:
        db = StateDb(Path(state[STATE_STATE_DB_PATH]))
        db.initialize()
        db.set_current_path(int(state[STATE_FILE_ID]), target_path)

    next_state[STATE_IMPORT_PLAN] = {**plan, "actual_filename": target_path.name}
    # Clear so downstream nodes cannot rename again
    next_state[STATE_TARGET_FILENAME] = None
    next_state[STATE_EVENTS].append(
        _event(
            node_name,
            "RENAMED",
            f"Renamed {pdf_path.name} to {target_path.name}.",
        )
    )
    return next_state


def _copy_state(state: GraphState) -> GraphState:
    next_state = dict(state)
    next_state[STATE_EVENTS] = list(get_events(state))
    return next_state  # type: ignore[return-value]


def _event(node: str, status: str, message: str) -> GraphEvent:
    return {"node": node, "status": status, "message": message}
