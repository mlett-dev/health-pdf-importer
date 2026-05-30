from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from health_importer.anytype.client import AnytypeClient, AnytypeFileRef, AnytypeOperationError
from health_importer.state_db import StateDb


class AnytypeFileUploadError(RuntimeError):
    """Raised when a PDF cannot be uploaded to Anytype."""


@dataclass(frozen=True)
class UploadResult:
    file_ref: AnytypeFileRef
    reused_existing: bool


def upload_pdf_once(
    client: AnytypeClient,
    state_db: StateDb,
    *,
    file_id: int,
    pdf_path: Path,
) -> UploadResult:
    record = state_db.get_file(file_id)
    if record.anytype_file_id:
        return UploadResult(
            file_ref=AnytypeFileRef(
                id=record.anytype_file_id,
                name=pdf_path.name,
                path=str(pdf_path),
            ),
            reused_existing=True,
        )

    try:
        file_ref = client.upload_file(pdf_path)
    except AnytypeOperationError as exc:
        state_db.add_event(file_id, "anytype_file_upload_failed", {"error": type(exc).__name__})
        raise AnytypeFileUploadError(str(exc)) from exc

    state_db.set_anytype_file_id(file_id, file_ref.id)
    return UploadResult(file_ref=file_ref, reused_existing=False)
