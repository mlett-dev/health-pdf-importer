from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    path: Path
    width: int
    height: int


def render_pages(
    pdf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 220,
    max_pages: int = 3,
) -> list[RenderedPage]:
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if max_pages <= 0:
        raise ValueError("max_pages must be positive")

    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[RenderedPage] = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document.pages(), start=1):
            if len(rendered) >= max_pages:
                break
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            output_path = output_dir / f"{pdf_path.stem}_page_{index:03d}.png"
            pixmap.save(output_path)
            rendered.append(
                RenderedPage(
                    page_number=index,
                    path=output_path,
                    width=pixmap.width,
                    height=pixmap.height,
                )
            )

    return rendered
