from pathlib import Path
from unittest.mock import Mock, patch

from health_importer.graph.pdf_nodes import (
    evaluate_embedded_text_quality,
    render_vision_pages_if_needed,
)


def test_evaluate_embedded_text_quality_uses_configured_min_text_chars(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"pdf")
    quality = Mock()
    quality.route = "llm_text_extraction"
    quality.score = 0.9
    quality.to_dict.return_value = {"score": 0.9, "route": "llm_text_extraction"}
    image_stats = Mock()
    image_stats.page_number = 1
    image_stats.image_count = 0
    image_stats.relevant_image_count = 0
    image_stats.largest_area_ratio = 0.0
    image_stats.min_area_ratio = 0.01
    image_stats.min_pixel_width = 80
    image_stats.min_pixel_height = 40
    image_stats.inspections = []
    image_stats.skip_reason_summary.return_value = "no_images"

    with (
        patch(
            "health_importer.graph.pdf_nodes.evaluate_text_quality", return_value=quality
        ) as eval_quality,
        patch("health_importer.graph.pdf_nodes.first_page_image_stats", return_value=image_stats),
    ):
        result = evaluate_embedded_text_quality(
            {
                "file_path": str(pdf_path),
                "status": "LOADED",
                "pdf_text": {"pages": [{"text": "short"}]},
                "events": [],
                "min_text_chars": 1234,
            }
        )

    eval_quality.assert_called_once()
    assert eval_quality.call_args.kwargs["min_text_chars"] == 1234
    assert result["status"] == "TEXT_QUALITY_EVALUATED"


def test_render_vision_pages_if_needed_renders_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "invoice.pdf"
    pdf_path.write_bytes(b"pdf")
    rendered_page = Mock()
    rendered_page.page_number = 1
    rendered_page.path = tmp_path / "page.png"
    rendered_page.width = 100
    rendered_page.height = 200

    with patch(
        "health_importer.graph.pdf_nodes.render_pages", return_value=[rendered_page]
    ) as render:
        result = render_vision_pages_if_needed(
            {
                "file_path": str(pdf_path),
                "status": "OCR_EXTRACTED",
                "events": [],
                "next_route": "vision",
                "render_dpi": 180,
                "max_vision_pages": 2,
            }
        )

    render.assert_called_once()
    assert result["status"] == "VISION_PAGES_RENDERED"
    vision_pages = result.get("vision_pages")
    assert vision_pages is not None
    assert vision_pages[0]["page_number"] == 1
    assert vision_pages[0]["path"] == str(tmp_path / "page.png")
    assert "vision_results" not in result


def test_render_vision_pages_if_needed_skips_when_not_needed(tmp_path: Path) -> None:
    result = render_vision_pages_if_needed(
        {
            "file_path": str(tmp_path / "invoice.pdf"),
            "status": "DONE",
            "events": [],
            "next_route": "llm_text_extraction",
        }
    )

    assert result["events"][0]["status"] == "VISION_SKIPPED"
