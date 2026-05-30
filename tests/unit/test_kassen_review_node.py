"""Tests for kassen_review_node."""

from pathlib import Path
from typing import cast
from unittest.mock import patch

from health_importer.graph.nodes import kassen_review_node
from health_importer.graph.state import GraphState


def test_kassen_review_node_review_match(tmp_path: Path) -> None:
    """Regression: kassen_review_node moves PDF to review with sidecar."""
    pdf = tmp_path / "processing" / "test.pdf"
    pdf.parent.mkdir()
    pdf.write_text("PDF")
    review_dir = tmp_path / "review"

    state = cast(
        GraphState,
        {
            "file_path": str(pdf),
            "file_name": "test.pdf",
            "sha256": "abc123",
            "status": "KASSEN_REVIEW_MATCH",
            "review_folder": str(review_dir),
            "events": [],
            "kassen_ruckmeldung_extraction": {
                "patient_first_name": {"value": "Anna"},
            },
            "matching_candidates": [{"object_id": "obj-1", "name": "Invoice 1", "score": 0.75}],
            "selected_match": {"object_id": "obj-1", "name": "Invoice 1"},
            "validation": {"errors": [], "warnings": []},
        },
    )

    with patch("health_importer.workflow.kassen_review.move_to_kassen_review") as mock_move:
        mock_result = mock_move.return_value
        mock_result.pdf_path = review_dir / "test.pdf"
        mock_result.sidecar_path = review_dir / "test.import.json"
        mock_result.markdown_path = review_dir / "test.md"
        result = kassen_review_node(state)

    assert result["status"] == "KASSEN_REVIEWED"
    routing = result.get("routing_decision")
    assert routing is not None
    assert routing["action"] == "REVIEW_ONLY"
    assert "Moved to review" in result["events"][0]["message"]


def test_kassen_review_node_unclear(tmp_path: Path) -> None:
    """Regression: kassen_review_node for unclear status without candidates."""
    pdf = tmp_path / "processing" / "test.pdf"
    pdf.parent.mkdir()
    pdf.write_text("PDF")
    review_dir = tmp_path / "review"

    state = cast(
        GraphState,
        {
            "file_path": str(pdf),
            "file_name": "test.pdf",
            "sha256": "abc123",
            "status": "KASSEN_REVIEW_UNCLEAR",
            "review_folder": str(review_dir),
            "events": [],
            "kassen_ruckmeldung_extraction": {},
            "matching_candidates": [],
            "selected_match": None,
            "validation": {"errors": [], "warnings": []},
        },
    )

    with patch("health_importer.workflow.kassen_review.move_to_kassen_review") as mock_move:
        mock_result = mock_move.return_value
        mock_result.pdf_path = review_dir / "test.pdf"
        mock_result.sidecar_path = review_dir / "test.import.json"
        mock_result.markdown_path = review_dir / "test.md"
        result = kassen_review_node(state)

    assert result["status"] == "KASSEN_REVIEWED"
    artifact = result.get("review_artifact")
    assert artifact is not None
    assert artifact["pdf_path"] == str(review_dir / "test.pdf")
