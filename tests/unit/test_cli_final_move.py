"""Tests for CLI _move_to_final_folder edge cases."""

from pathlib import Path
from unittest.mock import MagicMock

from health_importer.commands.common import move_to_final_folder
from health_importer.config import AppConfig, FolderConfig, StateDbConfig


def _make_config(tmp_path: Path) -> AppConfig:
    """Build a minimal Config for testing."""
    folders = FolderConfig(
        inbox=tmp_path / "inbox",
        processing=tmp_path / "processing",
        done=tmp_path / "done",
        review=tmp_path / "review",
        error=tmp_path / "error",
    )
    state_db = StateDbConfig(path=tmp_path / "state.db")
    cfg = MagicMock(spec=AppConfig)
    cfg.folders = folders
    cfg.state_db = state_db
    return cfg


def test_move_to_final_folder_file_already_moved_by_graph(tmp_path: Path) -> None:
    """Regression: when graph node already moved file, detect it in target dir."""
    source = tmp_path / "processing" / "test.pdf"
    source.parent.mkdir()
    source.write_text("PDF")
    error_dir = tmp_path / "error"
    error_dir.mkdir()

    # Simulate graph already moved file to error dir
    moved = error_dir / "test.pdf"
    moved.write_text("PDF")
    source.unlink()

    result = {"ok": False, "status": "ERROR", "file_path": str(source), "events": []}
    cfg = _make_config(tmp_path)

    next_result = move_to_final_folder(source, cfg, result)

    assert next_result["final_path"] == str(moved)
    assert next_result["final_folder"] == "error"
    assert next_result["final_move_collision_resolved"] is False


def test_move_to_final_folder_already_in_target_dir(tmp_path: Path) -> None:
    """Regression: when file is already in target dir, no-op gracefully."""
    error_dir = tmp_path / "error"
    error_dir.mkdir()
    source = error_dir / "test.pdf"
    source.write_text("PDF")

    result = {"ok": False, "status": "ERROR", "file_path": str(source), "events": []}
    cfg = _make_config(tmp_path)

    next_result = move_to_final_folder(source, cfg, result)

    assert next_result["final_path"] == str(source)
    assert next_result["final_folder"] == "error"
    assert next_result["final_move_collision_resolved"] is False


def test_move_to_final_folder_review_status(tmp_path: Path) -> None:
    """Regression: REVIEW status routes to review folder."""
    source = tmp_path / "processing" / "test.pdf"
    source.parent.mkdir()
    source.write_text("PDF")

    result = {"ok": True, "status": "REVIEW", "file_path": str(source), "events": []}
    cfg = _make_config(tmp_path)

    next_result = move_to_final_folder(source, cfg, result)

    assert (tmp_path / "review" / "test.pdf").exists()
    assert next_result["final_folder"] == "review"


def test_move_to_final_folder_missing_source_raises(tmp_path: Path) -> None:
    """Regression: when source is missing and not in target, raise FileNotFoundError."""
    source = tmp_path / "processing" / "missing.pdf"
    result = {"ok": False, "status": "ERROR", "file_path": str(source), "events": []}
    cfg = _make_config(tmp_path)

    try:
        move_to_final_folder(source, cfg, result)
        assert False, "Expected FileNotFoundError"
    except FileNotFoundError as exc:
        assert "Source file does not exist" in str(exc)
