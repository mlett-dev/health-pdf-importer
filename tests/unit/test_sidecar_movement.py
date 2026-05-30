"""Tests for sidecar JSON movement alongside PDF files."""

from pathlib import Path

from health_importer.commands.common import move_sidecar_if_present


def test_move_sidecar_simple(tmp_path: Path) -> None:
    pdf_source = tmp_path / "processing" / "test.pdf"
    pdf_source.parent.mkdir()
    pdf_source.write_text("PDF")

    sidecar = pdf_source.with_suffix(".import.json")
    sidecar.write_text('{"status": "ERROR"}')

    pdf_dest = tmp_path / "error" / "test.pdf"
    pdf_dest.parent.mkdir()

    move_sidecar_if_present(pdf_source, pdf_dest)

    assert not sidecar.exists()
    assert (pdf_dest.with_suffix(".import.json")).exists()
    assert (pdf_dest.with_suffix(".import.json")).read_text() == '{"status": "ERROR"}'


def test_move_sidecar_collision(tmp_path: Path) -> None:
    """When destination sidecar already exists, create numbered variant."""
    pdf_source = tmp_path / "processing" / "test.pdf"
    pdf_source.parent.mkdir()
    pdf_source.write_text("PDF")

    sidecar = pdf_source.with_suffix(".import.json")
    sidecar.write_text('{"status": "ERROR"}')

    pdf_dest = tmp_path / "error" / "test.pdf"
    pdf_dest.parent.mkdir()
    pdf_dest.write_text("PDF2")

    # Pre-existing sidecar at destination
    existing = pdf_dest.with_suffix(".import.json")
    existing.write_text('{"status": "OK"}')

    move_sidecar_if_present(pdf_source, pdf_dest)

    assert not sidecar.exists()
    assert existing.exists()
    # Numbered variant should have been created (test_2.import.json)
    numbered = pdf_dest.parent / "test_2.import.json"
    assert numbered.exists()
    assert numbered.read_text() == '{"status": "ERROR"}'


def test_move_sidecar_no_sidecar(tmp_path: Path) -> None:
    """When no sidecar exists at source, do nothing gracefully."""
    pdf_source = tmp_path / "processing" / "test.pdf"
    pdf_source.parent.mkdir()
    pdf_source.write_text("PDF")

    pdf_dest = tmp_path / "error" / "test.pdf"
    pdf_dest.parent.mkdir()

    # Must not raise
    move_sidecar_if_present(pdf_source, pdf_dest)

    assert not (pdf_dest.with_suffix(".import.json")).exists()


def test_move_sidecar_same_source_destination(tmp_path: Path) -> None:
    """When source and destination are the same path, do not rename sidecar."""
    pdf = tmp_path / "error" / "test.pdf"
    pdf.parent.mkdir()
    pdf.write_text("PDF")

    sidecar = pdf.with_suffix(".import.json")
    sidecar.write_text('{"status": "ERROR"}')

    move_sidecar_if_present(pdf, pdf)

    assert sidecar.exists()
    assert not (pdf.parent / "test_2.import.json").exists()
