"""Tests for Kassen PDF attachment to Anytype invoice objects."""

from unittest.mock import MagicMock

import pytest

from health_importer.anytype.client import AnytypeSchemaError
from health_importer.anytype.kassen_update import attach_kassen_pdf


def test_attach_kassen_pdf_dry_run() -> None:
    """Dry-run should not call set_property and return planned file list."""
    client = MagicMock()

    result = attach_kassen_pdf(
        client,
        object_id="obj-123",
        kassen_file_id="file-456",
        attachment_property_id="rechnung,_gkk",
        existing_file_ids=["file-existing"],
        dry_run=True,
    )

    client.set_property.assert_not_called()
    assert result.object_id == "obj-123"
    assert result.property_id == "rechnung,_gkk"
    assert result.file_ids == ["file-existing", "file-456"]
    assert result.dry_run is True


def test_attach_kassen_pdf_live() -> None:
    """Live mode should call set_property with merged file list."""
    client = MagicMock()

    result = attach_kassen_pdf(
        client,
        object_id="obj-789",
        kassen_file_id="file-new",
        attachment_property_id="rechnung,_gkk",
        existing_file_ids=["file-old"],
        dry_run=False,
    )

    client.set_property.assert_called_once_with(
        "obj-789",
        "rechnung,_gkk",
        {"files": ["file-old", "file-new"]},
    )
    assert result.dry_run is False
    assert result.file_ids == ["file-old", "file-new"]


def test_attach_kassen_pdf_no_existing() -> None:
    """If no existing files, only new file ID should be in the list."""
    client = MagicMock()

    result = attach_kassen_pdf(
        client,
        object_id="obj-abc",
        kassen_file_id="file-single",
        attachment_property_id="rechnung,_gkk",
        existing_file_ids=None,
        dry_run=True,
    )

    assert result.file_ids == ["file-single"]


def test_attach_kassen_pdf_duplicate_idempotent() -> None:
    """If file already attached, do not duplicate it."""
    client = MagicMock()

    result = attach_kassen_pdf(
        client,
        object_id="obj-def",
        kassen_file_id="file-already",
        attachment_property_id="rechnung,_gkk",
        existing_file_ids=["file-already"],
        dry_run=True,
    )

    assert result.file_ids == ["file-already"]


def test_attach_kassen_pdf_dead_id_with_hyphens() -> None:
    """Retry must parse dead file IDs containing hyphens (e.g. UUID-style)."""
    client = MagicMock()
    dead_id = "b672a8fc-3b3f-44c1-9c2d-5e9e1f0a2b3c"
    exc = AnytypeSchemaError(f"invalid file reference for rechnung,_gkk: {dead_id}")
    client.set_property.side_effect = [exc, None]

    result = attach_kassen_pdf(
        client,
        object_id="obj-hyphen",
        kassen_file_id="file-new",
        attachment_property_id="rechnung,_gkk",
        existing_file_ids=[dead_id, "file-old"],
        dry_run=False,
    )

    assert result.file_ids == ["file-old", "file-new"]
    # Verify fallback call excluded the dead hyphenated ID
    fallback_call = client.set_property.call_args_list[1]
    assert fallback_call[0][2] == {"files": ["file-old", "file-new"]}


def test_attach_kassen_pdf_dead_id_all_dead_fallback() -> None:
    """When all existing IDs are dead, fallback must use only the new file ID."""
    client = MagicMock()
    dead_id = "dead-file-id"
    exc = AnytypeSchemaError(f"invalid file reference for rechnung,_gkk: {dead_id}")
    client.set_property.side_effect = [exc, None]

    result = attach_kassen_pdf(
        client,
        object_id="obj-all-dead",
        kassen_file_id="file-new",
        attachment_property_id="rechnung,_gkk",
        existing_file_ids=[dead_id],
        dry_run=False,
    )

    assert result.file_ids == ["file-new"]
    fallback_call = client.set_property.call_args_list[1]
    assert fallback_call[0][2] == {"files": ["file-new"]}


def test_attach_kassen_pdf_re_raises_on_unrelated_schema_error() -> None:
    """Schema errors without dead-ID text must propagate instead of being retried."""

    client = MagicMock()
    client.set_property.side_effect = AnytypeSchemaError("type mismatch on property")

    with pytest.raises(AnytypeSchemaError, match="type mismatch on property"):
        attach_kassen_pdf(
            client,
            object_id="obj-1",
            kassen_file_id="file-new",
            attachment_property_id="rechnung,_gkk",
            existing_file_ids=["file-old"],
            dry_run=False,
        )


def test_attach_kassen_pdf_re_raises_on_non_schema_error() -> None:
    """Non-schema exceptions must propagate directly."""

    client = MagicMock()
    client.set_property.side_effect = RuntimeError("network timeout")

    with pytest.raises(RuntimeError, match="network timeout"):
        attach_kassen_pdf(
            client,
            object_id="obj-1",
            kassen_file_id="file-new",
            attachment_property_id="rechnung,_gkk",
            existing_file_ids=["file-old"],
            dry_run=False,
        )
