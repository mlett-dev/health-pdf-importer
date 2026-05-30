from pathlib import Path

import fitz

from health_importer.pdf.images import first_page_has_relevant_images, first_page_image_stats


def test_first_page_image_stats_detects_no_images(tmp_path: Path) -> None:
    pdf_path = tmp_path / "text_only.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Rechnung Betrag EUR 120")
    document.save(pdf_path)
    document.close()

    stats = first_page_image_stats(pdf_path)

    assert stats.image_count == 0
    assert stats.relevant_image_count == 0
    assert first_page_has_relevant_images(pdf_path) is False


def test_first_page_image_stats_detects_logo_image(tmp_path: Path) -> None:
    pdf_path = tmp_path / "with_logo.pdf"
    image_path = tmp_path / "logo.png"
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 240, 120), False)
    pixmap.clear_with(200)
    pixmap.save(image_path)

    document = fitz.open()
    page = document.new_page()
    page.insert_image(fitz.Rect(50, 50, 250, 150), filename=str(image_path))
    page.insert_text((72, 200), "Rechnung Betrag EUR 120")
    document.save(pdf_path)
    document.close()

    stats = first_page_image_stats(pdf_path)

    assert stats.image_count >= 1
    assert stats.relevant_image_count >= 1
    assert stats.largest_area_ratio > 0
    assert first_page_has_relevant_images(pdf_path) is True
