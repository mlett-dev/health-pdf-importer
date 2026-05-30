from __future__ import annotations

import tempfile
from pathlib import Path

from health_importer.graph.state import (
    STATE_EVENTS,
    STATE_FILE_PATH,
    STATE_NEXT_ROUTE,
    STATE_OCR_PDF_PATH,
    STATE_OCR_TEXT,
    STATE_OCR_TEXT_QUALITY,
    STATE_PDF_IMAGE_STATS,
    STATE_PDF_TEXT,
    STATE_STATUS,
    STATE_TEXT_QUALITY,
    STATE_VISION_PAGES,
    STATE_VISION_PAGES_TEMP_DIR,
    GraphEvent,
    GraphState,
    get_events,
    get_file_path,
    get_max_vision_pages,
    get_min_area_ratio,
    get_min_pixel_height,
    get_min_pixel_width,
    get_min_text_chars,
    get_next_route,
    get_ocr_language,
    get_ocr_pdf_path,
    get_render_dpi,
)
from health_importer.pdf.extract_text import extract_embedded_text
from health_importer.pdf.images import first_page_image_stats
from health_importer.pdf.ocr import run_local_ocr
from health_importer.pdf.quality import evaluate_text_quality, join_page_text
from health_importer.pdf.render import render_pages


def extract_embedded_pdf_text(state: GraphState) -> GraphState:
    extraction = extract_embedded_text(Path(state[STATE_FILE_PATH]))
    next_state = _copy_state(state)
    next_state[STATE_PDF_TEXT] = extraction.to_dict()
    next_state[STATE_STATUS] = "EXTRACTED"
    next_state[STATE_EVENTS].append(
        _event(
            "extract_embedded_pdf_text",
            "EXTRACTED",
            f"Extracted {extraction.total_chars} chars from {extraction.page_count} pages.",
        )
    )
    return next_state


def evaluate_embedded_text_quality(state: GraphState) -> GraphState:
    min_text_chars = int(get_min_text_chars(state))
    quality = evaluate_text_quality(
        join_page_text(state.get(STATE_PDF_TEXT, {})), min_text_chars=min_text_chars
    )
    next_state = _copy_state(state)
    next_state[STATE_TEXT_QUALITY] = quality.to_dict()
    next_state[STATE_NEXT_ROUTE] = quality.route

    image_stats = first_page_image_stats(
        Path(state[STATE_FILE_PATH]),
        min_area_ratio=float(get_min_area_ratio(state)),
        min_pixel_width=int(get_min_pixel_width(state)),
        min_pixel_height=int(get_min_pixel_height(state)),
    )
    next_state[STATE_PDF_IMAGE_STATS] = {
        "page_number": image_stats.page_number,
        "image_count": image_stats.image_count,
        "relevant_image_count": image_stats.relevant_image_count,
        "largest_area_ratio": image_stats.largest_area_ratio,
        "min_area_ratio": image_stats.min_area_ratio,
        "min_pixel_width": image_stats.min_pixel_width,
        "min_pixel_height": image_stats.min_pixel_height,
        "skip_reason_summary": image_stats.skip_reason_summary(),
        "inspections": [
            {
                "index": inspection.index,
                "pixel_width": inspection.pixel_width,
                "pixel_height": inspection.pixel_height,
                "area_ratio": inspection.area_ratio,
                "is_relevant": inspection.is_relevant,
                "skip_reason": inspection.skip_reason,
            }
            for inspection in image_stats.inspections
        ],
    }
    if image_stats.relevant_image_count > 0:
        next_state[STATE_NEXT_ROUTE] = "vision"
        route_message = (
            f"Text quality score {quality.score:.3f}; first page has "
            f"{image_stats.relevant_image_count}/{image_stats.image_count} "
            f"relevant image(s) (largest area ratio "
            f"{image_stats.largest_area_ratio:.3f}); route vision."
        )
    else:
        route_message = (
            f"Text quality score {quality.score:.3f}; route {quality.route}; "
            f"image_count={image_stats.image_count}, relevant=0 "
            f"(reason={image_stats.skip_reason_summary()}, "
            f"thresholds: min_pixel={image_stats.min_pixel_width}x"
            f"{image_stats.min_pixel_height}, "
            f"min_area_ratio={image_stats.min_area_ratio}, "
            f"min_text_chars={min_text_chars})."
        )

    next_state[STATE_STATUS] = "TEXT_QUALITY_EVALUATED"
    next_state[STATE_EVENTS].append(
        _event(
            "evaluate_embedded_text_quality",
            "TEXT_QUALITY_EVALUATED",
            route_message,
        )
    )
    return next_state


def run_ocr_if_needed(state: GraphState) -> GraphState:
    if get_next_route(state) != "ocr":
        next_state = _copy_state(state)
        next_state[STATE_EVENTS].append(
            _event("run_ocr_if_needed", "OCR_SKIPPED", "Embedded text is good enough.")
        )
        return next_state

    input_path = Path(state[STATE_FILE_PATH])
    output_path = input_path.with_name(f"{input_path.stem}_ocr{input_path.suffix}")
    ocr_result = run_local_ocr(
        input_path,
        output_path,
        language=str(get_ocr_language(state)),
    )
    ocr_quality = evaluate_text_quality(
        join_page_text(ocr_result.text.to_dict()),
        min_text_chars=int(get_min_text_chars(state)),
    )

    next_state = _copy_state(state)
    next_state[STATE_OCR_PDF_PATH] = str(ocr_result.output_path)
    next_state[STATE_OCR_TEXT] = ocr_result.text.to_dict()
    next_state[STATE_OCR_TEXT_QUALITY] = ocr_quality.to_dict()
    next_state[STATE_NEXT_ROUTE] = ocr_quality.route if ocr_quality.route != "ocr" else "vision"
    next_state[STATE_STATUS] = "OCR_EXTRACTED"
    next_state[STATE_EVENTS].append(
        _event(
            "run_ocr_if_needed",
            "OCR_EXTRACTED",
            f"OCR extracted {ocr_result.text.total_chars} chars; route {next_state.get('next_route', 'unknown')}.",
        )
    )
    return next_state


def render_vision_pages_if_needed(state: GraphState) -> GraphState:
    if get_next_route(state) != "vision":
        next_state = _copy_state(state)
        next_state[STATE_EVENTS].append(
            _event("render_vision_pages_if_needed", "VISION_SKIPPED", "Vision fallback not needed.")
        )
        return next_state

    pdf_path = Path(get_ocr_pdf_path(state) or get_file_path(state) or "")
    render_dir = Path(tempfile.mkdtemp(prefix="health-importer-vision-"))
    rendered_pages = render_pages(
        pdf_path,
        render_dir,
        dpi=int(get_render_dpi(state)),
        max_pages=int(get_max_vision_pages(state)),
    )

    next_state = _copy_state(state)
    next_state[STATE_VISION_PAGES] = [
        {
            "page_number": page.page_number,
            "path": str(page.path),
            "width": page.width,
            "height": page.height,
        }
        for page in rendered_pages
    ]
    next_state[STATE_VISION_PAGES_TEMP_DIR] = str(render_dir)
    next_state[STATE_STATUS] = "VISION_PAGES_RENDERED"
    next_state[STATE_EVENTS].append(
        _event(
            "render_vision_pages_if_needed",
            "VISION_PAGES_RENDERED",
            f"Rendered {len(rendered_pages)} pages for vision extraction.",
        )
    )
    return next_state


def _copy_state(state: GraphState) -> GraphState:
    next_state = dict(state)
    next_state[STATE_EVENTS] = list(get_events(state))
    return next_state  # type: ignore[return-value]


def _event(node: str, status: str, message: str) -> GraphEvent:
    return {"node": node, "status": status, "message": message}
