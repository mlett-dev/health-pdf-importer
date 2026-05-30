"""File upload operations for Kassenrückmeldung PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from health_importer.anytype.client import AnytypeClient
from health_importer.anytype.file_upload import upload_pdf_once
from health_importer.state_db import StateDb


@dataclass(frozen=True)
class KassenUploadResult:
    file_id: str
    reused: bool
    dry_run: bool


def upload_kassen_pdf(
    client: AnytypeClient,
    state_db: StateDb | None,
    *,
    file_id: int,
    pdf_path: Path,
    dry_run: bool = True,
) -> KassenUploadResult:
    """Upload Kassen-PDF to Anytype, reusing existing upload on retry.

    Returns KassenUploadResult with the Anytype file reference ID.
    """
    if dry_run:
        return KassenUploadResult(
            file_id="dry-run-file-id",
            reused=False,
            dry_run=True,
        )

    if state_db is None:
        raise RuntimeError("upload_pdf_once requires state_db, got None")
    result = upload_pdf_once(client, state_db, file_id=file_id, pdf_path=pdf_path)
    return KassenUploadResult(
        file_id=result.file_ref.id,
        reused=result.reused_existing,
        dry_run=False,
    )
