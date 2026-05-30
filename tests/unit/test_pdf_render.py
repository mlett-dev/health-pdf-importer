from pathlib import Path

import fitz
import pytest

from health_importer.pdf.render import render_pages


def test_render_pages_writes_limited_pngs(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    output_dir = tmp_path / "rendered"
    _write_pdf(pdf_path, ["page 1", "page 2", "page 3"])

    rendered = render_pages(pdf_path, output_dir, dpi=100, max_pages=2)

    assert [page.page_number for page in rendered] == [1, 2]
    assert rendered[0].path.name == "invoice_page_001.png"
    assert rendered[0].path.exists()
    assert rendered[1].path.exists()
    assert len(list(output_dir.glob("*.png"))) == 2
    assert rendered[0].width > 0
    assert rendered[0].height > 0


def test_render_pages_rejects_invalid_limits(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    _write_pdf(pdf_path, ["page 1"])

    with pytest.raises(ValueError, match="dpi"):
        render_pages(pdf_path, tmp_path / "out", dpi=0)
    with pytest.raises(ValueError, match="max_pages"):
        render_pages(pdf_path, tmp_path / "out", max_pages=0)


def _write_pdf(path: Path, pages: list[str]) -> None:
    document = fitz.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()
