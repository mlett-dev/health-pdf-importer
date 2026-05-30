import os
import time
from pathlib import Path

import pytest

from health_importer.config import FolderConfig
from health_importer.workflow.filesystem import (
    cleanup_temporary_artifacts,
    ensure_workflow_folders,
    safe_move,
)


def test_ensure_workflow_folders_creates_all_directories(tmp_path: Path) -> None:
    folders = FolderConfig(
        inbox=tmp_path / "Inbox",
        processing=tmp_path / "Processing",
        done=tmp_path / "Done",
        review=tmp_path / "Review",
        error=tmp_path / "Error",
    )

    ensure_workflow_folders(folders)

    assert folders.inbox.is_dir()
    assert folders.processing.is_dir()
    assert folders.done.is_dir()
    assert folders.review.is_dir()
    assert folders.error.is_dir()


def test_safe_move_moves_file_to_destination(tmp_path: Path) -> None:
    source = tmp_path / "Inbox" / "invoice.pdf"
    destination_dir = tmp_path / "Processing"
    source.parent.mkdir()
    source.write_text("pdf", encoding="utf-8")

    result = safe_move(source, destination_dir)

    assert not source.exists()
    assert result.destination == destination_dir / "invoice.pdf"
    assert result.destination.read_text(encoding="utf-8") == "pdf"
    assert result.collision_resolved is False


def test_safe_move_preserves_existing_file_with_suffix(tmp_path: Path) -> None:
    source = tmp_path / "Inbox" / "invoice.pdf"
    destination_dir = tmp_path / "Processing"
    source.parent.mkdir()
    destination_dir.mkdir()
    source.write_text("new", encoding="utf-8")
    (destination_dir / "invoice.pdf").write_text("existing", encoding="utf-8")

    result = safe_move(source, destination_dir)

    assert (destination_dir / "invoice.pdf").read_text(encoding="utf-8") == "existing"
    assert result.destination == destination_dir / "invoice_2.pdf"
    assert result.destination.read_text(encoding="utf-8") == "new"
    assert result.collision_resolved is True


def test_safe_move_rejects_missing_source(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        safe_move(tmp_path / "missing.pdf", tmp_path / "Processing")


def test_cleanup_temporary_artifacts_removes_old_render_and_ocr_files(tmp_path: Path) -> None:
    old_render_dir = tmp_path / "invoice_vision_pages"
    old_render_dir.mkdir()
    (old_render_dir / "page.png").write_text("png", encoding="utf-8")
    old_ocr_pdf = tmp_path / "invoice_ocr.pdf"
    old_ocr_pdf.write_text("pdf", encoding="utf-8")
    fresh_tmp = tmp_path / "fresh.tmp"
    fresh_tmp.write_text("tmp", encoding="utf-8")
    old_timestamp = time.time() - 48 * 60 * 60
    os.utime(old_render_dir / "page.png", (old_timestamp, old_timestamp))
    os.utime(old_render_dir, (old_timestamp, old_timestamp))
    os.utime(old_ocr_pdf, (old_timestamp, old_timestamp))

    removed = cleanup_temporary_artifacts(tmp_path, older_than_hours=24)

    assert old_render_dir in removed
    assert old_ocr_pdf in removed
    assert not old_render_dir.exists()
    assert not old_ocr_pdf.exists()
    assert fresh_tmp.exists()


def test_cleanup_temporary_artifacts_rejects_negative_retention(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="older_than_hours"):
        cleanup_temporary_artifacts(tmp_path, older_than_hours=-1)
