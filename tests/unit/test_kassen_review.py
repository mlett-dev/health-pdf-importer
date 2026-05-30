"""Tests for Kassen review sidecar and markdown generation."""

import json
from pathlib import Path

from health_importer.workflow.kassen_review import (
    build_kassen_review_sidecar,
    move_to_kassen_review,
)


def test_build_kassen_review_sidecar_structure() -> None:
    sidecar = build_kassen_review_sidecar(
        original_filename="kasse.pdf",
        sha256="abc123",
        extraction={"patient_first_name": "Max", "erstattungsbetrag_eur": "85.00"},
        matching_candidates=[
            {"name": "Rechnung A", "score": 0.75, "reasons": ["patient match"]},
        ],
        selected_match=None,
        validation_errors=[],
        validation_warnings=["low confidence"],
        suggested_action="Manuell zuordnen",
    )
    assert sidecar["document_type"] == "krankenkasse_antwort"
    assert sidecar["original_filename"] == "kasse.pdf"
    assert sidecar["sha256"] == "abc123"
    assert sidecar["extraction"]["patient_first_name"] == "Max"
    assert len(sidecar["matching_candidates"]) == 1
    assert sidecar["selected_match"] is None
    assert sidecar["validation"]["warnings"] == ["low confidence"]
    assert sidecar["suggested_action"] == "Manuell zuordnen"


def test_move_to_kassen_review(tmp_path: Path) -> None:
    source = tmp_path / "source" / "kasse.pdf"
    source.parent.mkdir()
    source.write_text("PDF content")
    review_dir = tmp_path / "review"
    review_dir.mkdir()

    payload = build_kassen_review_sidecar(
        original_filename="kasse.pdf",
        sha256="abc",
        extraction={"patient_first_name": "Max"},
        matching_candidates=[],
        selected_match=None,
        validation_errors=[],
        validation_warnings=[],
        suggested_action="Review",
    )

    artifact = move_to_kassen_review(
        source,
        review_dir,
        sidecar_payload=payload,
        review_reasons=["low matching confidence"],
    )

    assert artifact.pdf_path.exists()
    assert artifact.pdf_path.name == "kasse.pdf"
    assert artifact.sidecar_path.exists()
    assert artifact.sidecar_path.suffix == ".json"
    assert artifact.markdown_path.exists()
    assert artifact.markdown_path.suffix == ".md"

    # Verify sidecar content
    data = json.loads(artifact.sidecar_path.read_text())
    assert data["document_type"] == "krankenkasse_antwort"

    # Verify markdown contains key sections
    md = artifact.markdown_path.read_text()
    assert "# Kassenrückmeldung — Review" in md
    assert "low matching confidence" in md
    assert "Max" in md
