import json
from pathlib import Path

from health_importer.workflow.review import create_review_artifact


def test_create_review_artifact_moves_pdf_and_writes_context_files(tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"%PDF-1.4\n% test\n")
    review_dir = tmp_path / "Review"

    artifact = create_review_artifact(
        source,
        review_dir,
        sidecar_payload={
            "original_filename": "scan.pdf",
            "sha256": "abc123",
        },
        review_reasons=["amount_not_found_in_text", "doctor_match_ambiguous"],
        extracted_fields={
            "patient": "Anna",
            "amount": "120.00",
        },
    )

    assert not source.exists()
    assert artifact.pdf_path == review_dir / "invoice.pdf"
    assert artifact.pdf_path.exists()
    assert artifact.sidecar_path == review_dir / "invoice.import.json"
    assert artifact.markdown_path == review_dir / "invoice.review.md"
    sidecar = json.loads(artifact.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["review_reasons"] == [
        "amount_not_found_in_text",
        "doctor_match_ambiguous",
    ]
    markdown = artifact.markdown_path.read_text(encoding="utf-8")
    assert "`amount_not_found_in_text`" in markdown
    assert "`patient`: `Anna`" in markdown


def test_create_review_artifact_preserves_existing_review_pdf(tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"%PDF-1.4\n% test\n")
    review_dir = tmp_path / "Review"
    review_dir.mkdir()
    (review_dir / "invoice.pdf").write_bytes(b"existing")

    artifact = create_review_artifact(
        source,
        review_dir,
        sidecar_payload={},
        review_reasons=["date_not_found_in_text"],
    )

    assert artifact.pdf_path == review_dir / "invoice_2.pdf"
    assert artifact.sidecar_path == review_dir / "invoice_2.import.json"
