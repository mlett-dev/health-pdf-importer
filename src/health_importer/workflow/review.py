from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from health_importer.workflow.filesystem import safe_move
from health_importer.workflow.sidecar import sidecar_path_for, write_sidecar


@dataclass(frozen=True)
class ReviewArtifact:
    pdf_path: Path
    sidecar_path: Path
    markdown_path: Path


def create_review_artifact(
    source_pdf: Path,
    review_dir: Path,
    *,
    sidecar_payload: dict[str, Any],
    review_reasons: list[str],
    extracted_fields: dict[str, Any] | None = None,
    recommended_action: str = "Review fields, correct uncertain values, then retry.",
) -> ReviewArtifact:
    move_result = safe_move(source_pdf, review_dir)
    pdf_path = move_result.destination
    payload = dict(sidecar_payload)
    payload["review_reasons"] = review_reasons
    sidecar_path = write_sidecar(pdf_path, payload)
    markdown_path = pdf_path.with_suffix(".review.md")
    markdown_path.write_text(
        _review_markdown(
            pdf_path=pdf_path,
            review_reasons=review_reasons,
            extracted_fields=extracted_fields or {},
            recommended_action=recommended_action,
            sidecar_path=sidecar_path_for(pdf_path),
        ),
        encoding="utf-8",
    )
    return ReviewArtifact(
        pdf_path=pdf_path,
        sidecar_path=sidecar_path,
        markdown_path=markdown_path,
    )


def _review_markdown(
    *,
    pdf_path: Path,
    review_reasons: list[str],
    extracted_fields: dict[str, Any],
    recommended_action: str,
    sidecar_path: Path,
) -> str:
    lines = [
        "# Import Review",
        "",
        f"- PDF: `{pdf_path.name}`",
        f"- Sidecar: `{sidecar_path.name}`",
        f"- Recommended action: {recommended_action}",
        "",
        "## Review Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in review_reasons)
    lines.extend(["", "## Extracted Fields", ""])
    if extracted_fields:
        for key, value in sorted(extracted_fields.items()):
            lines.append(f"- `{key}`: `{value}`")
    else:
        lines.append("- No extracted fields available.")
    lines.append("")
    return "\n".join(lines)
