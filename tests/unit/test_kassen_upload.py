"""Tests for Kassen PDF upload to Anytype."""

from pathlib import Path
from unittest.mock import MagicMock

from health_importer.anytype.client import AnytypeFileRef
from health_importer.anytype.kassen_upload import upload_kassen_pdf


def test_upload_kassen_pdf_dry_run() -> None:
    """Dry-run should not call upload_file and return a stub result."""
    client = MagicMock()
    state_db = MagicMock()

    result = upload_kassen_pdf(
        client,
        state_db,
        file_id=42,
        pdf_path=Path("/tmp/kasse.pdf"),
        dry_run=True,
    )

    client.upload_file.assert_not_called()
    state_db.get_file.assert_not_called()
    assert result.file_id == "dry-run-file-id"
    assert result.reused is False
    assert result.dry_run is True


def test_upload_kassen_pdf_live_reuses_existing() -> None:
    """If state_db already has anytype_file_id, reuse it."""
    client = MagicMock()
    state_db = MagicMock()
    record = MagicMock()
    record.anytype_file_id = "existing-file-123"
    state_db.get_file.return_value = record

    result = upload_kassen_pdf(
        client,
        state_db,
        file_id=42,
        pdf_path=Path("/tmp/kasse.pdf"),
        dry_run=False,
    )

    client.upload_file.assert_not_called()
    assert result.file_id == "existing-file-123"
    assert result.reused is True
    assert result.dry_run is False


def test_upload_kassen_pdf_live_new_upload() -> None:
    """If no existing file_id, upload and store in state_db."""
    client = MagicMock()
    file_ref = AnytypeFileRef(id="new-file-456", name="kasse.pdf", path="/tmp/kasse.pdf")
    client.upload_file.return_value = file_ref

    state_db = MagicMock()
    record = MagicMock()
    record.anytype_file_id = None
    state_db.get_file.return_value = record

    result = upload_kassen_pdf(
        client,
        state_db,
        file_id=42,
        pdf_path=Path("/tmp/kasse.pdf"),
        dry_run=False,
    )

    client.upload_file.assert_called_once_with(Path("/tmp/kasse.pdf"))
    state_db.set_anytype_file_id.assert_called_once_with(42, "new-file-456")
    assert result.file_id == "new-file-456"
    assert result.reused is False
    assert result.dry_run is False
