"""Review workflow for Kassenrückmeldungen with uncertain matches."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from health_importer.workflow.filesystem import safe_move
from health_importer.workflow.sidecar import sidecar_path_for, write_sidecar


@dataclass(frozen=True)
class KassenReviewArtifact:
    pdf_path: Path
    sidecar_path: Path
    markdown_path: Path


def build_kassen_review_sidecar(
    *,
    original_filename: str,
    sha256: str,
    extraction: dict[str, Any],
    matching_candidates: list[dict[str, Any]],
    selected_match: dict[str, Any] | None,
    validation_errors: list[str],
    validation_warnings: list[str],
    suggested_action: str,
) -> dict[str, Any]:
    """Build a sidecar JSON for Kassen review cases."""
    return {
        "document_type": "krankenkasse_antwort",
        "original_filename": original_filename,
        "sha256": sha256,
        "extraction": extraction,
        "matching_candidates": matching_candidates,
        "selected_match": selected_match,
        "validation": {
            "errors": validation_errors,
            "warnings": validation_warnings,
        },
        "suggested_action": suggested_action,
    }


def move_to_kassen_review(
    source_pdf: Path,
    review_dir: Path,
    *,
    sidecar_payload: dict[str, Any],
    review_reasons: list[str],
) -> KassenReviewArtifact:
    """Move a Kassen PDF to review folder with sidecar and markdown."""
    move_result = safe_move(source_pdf, review_dir)
    pdf_path = move_result.destination
    sidecar_path = write_sidecar(pdf_path, sidecar_payload)
    markdown_path = pdf_path.with_suffix(".review.md")
    markdown_path.write_text(
        _kassen_review_markdown(
            pdf_path=pdf_path,
            review_reasons=review_reasons,
            sidecar_path=sidecar_path_for(pdf_path),
            extraction=sidecar_payload.get("extraction", {}),
            candidates=sidecar_payload.get("matching_candidates", []),
            suggested_action=sidecar_payload.get("suggested_action", ""),
        ),
        encoding="utf-8",
    )
    return KassenReviewArtifact(
        pdf_path=pdf_path,
        sidecar_path=sidecar_path,
        markdown_path=markdown_path,
    )


def _kassen_review_markdown(
    *,
    pdf_path: Path,
    review_reasons: list[str],
    sidecar_path: Path,
    extraction: dict[str, Any],
    candidates: list[dict[str, Any]],
    suggested_action: str,
) -> str:
    lines = [
        "# Kassenrückmeldung — Review",
        "",
        f"- PDF: `{pdf_path.name}`",
        f"- Sidecar: `{sidecar_path.name}`",
        f"- Suggested action: {suggested_action}",
        "",
        "## Review Reasons",
        "",
    ]
    for reason in review_reasons:
        lines.append(f"- {reason}")
    lines.extend([
        "",
        "## Extraction",
        "",
        "```json",
        _json_pretty(extraction),
        "```",
        "",
        "## Matching Candidates",
        "",
    ])
    if candidates:
        for c in candidates:
            lines.append(f"- **{c.get('name', '?')}** (score={c.get('score', 0):.2f}): {c.get('reasons', [])}")
    else:
        lines.append("_No candidates found._")
    lines.extend([
        "",
        "## Correction",
        "",
        "1. Find the file ID: `health-importer review-list`",
        "2. Create a correction YAML (e.g. `correction.yaml`) with manual overrides",
        "3. Retry: `health-importer retry <file_id> --correction correction.yaml`",
        "",
    ])
    return "\n".join(lines) + "\n"


def _json_pretty(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
