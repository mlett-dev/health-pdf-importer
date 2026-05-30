from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import fitz


@dataclass(frozen=True)
class ImageInspection:
    index: int
    pixel_width: int
    pixel_height: int
    area_ratio: float
    is_relevant: bool
    skip_reason: str | None


@dataclass(frozen=True)
class PageImageStats:
    page_number: int
    image_count: int
    relevant_image_count: int
    largest_area_ratio: float
    min_area_ratio: float
    min_pixel_width: int
    min_pixel_height: int
    inspections: list[ImageInspection] = field(default_factory=list)

    def skip_reason_summary(self) -> str:
        if self.image_count == 0:
            return "no_images_on_first_page"
        if self.relevant_image_count > 0:
            return "relevant_images_present"
        reasons = [
            inspection.skip_reason
            for inspection in self.inspections
            if inspection.skip_reason is not None
        ]
        if not reasons:
            return "all_images_filtered"
        return ",".join(sorted(set(reasons)))


def first_page_image_stats(
    pdf_path: Path,
    *,
    min_area_ratio: float = 0.01,
    min_pixel_width: int = 80,
    min_pixel_height: int = 40,
) -> PageImageStats:
    """Inspect the first page for embedded images that likely carry semantic content.

    A logo, doctor stamp or letterhead typically occupies a non-trivial portion of the
    page, so very small icons, hairlines or 1x1 decorative pixmaps are ignored. The
    returned stats include per-image inspections so callers can explain in events why
    a page was (not) routed to vision.
    """

    with fitz.open(pdf_path) as document:
        if document.page_count == 0:
            return PageImageStats(
                page_number=0,
                image_count=0,
                relevant_image_count=0,
                largest_area_ratio=0.0,
                min_area_ratio=min_area_ratio,
                min_pixel_width=min_pixel_width,
                min_pixel_height=min_pixel_height,
                inspections=[],
            )

        page = document.load_page(0)
        page_area = float(page.rect.width) * float(page.rect.height)
        info_items = page.get_image_info(xrefs=True) or []
        image_count = len(info_items)
        relevant_image_count = 0
        largest_area_ratio = 0.0
        inspections: list[ImageInspection] = []

        for index, info in enumerate(info_items):
            bbox = info.get("bbox")
            width = int(info.get("width", 0) or 0)
            height = int(info.get("height", 0) or 0)

            if bbox is None or page_area <= 0:
                area_ratio = 0.0
            else:
                x0, y0, x1, y1 = bbox
                area_ratio = max(0.0, (x1 - x0) * (y1 - y0) / page_area)
                largest_area_ratio = max(largest_area_ratio, area_ratio)

            skip_reason: str | None = None
            if width < min_pixel_width or height < min_pixel_height:
                skip_reason = "below_min_pixel_size"
            elif bbox is None or page_area <= 0:
                skip_reason = "missing_bbox"
            elif area_ratio < min_area_ratio:
                skip_reason = "below_min_area_ratio"

            is_relevant = skip_reason is None
            if is_relevant:
                relevant_image_count += 1

            inspections.append(
                ImageInspection(
                    index=index,
                    pixel_width=width,
                    pixel_height=height,
                    area_ratio=round(area_ratio, 4),
                    is_relevant=is_relevant,
                    skip_reason=skip_reason,
                )
            )

        return PageImageStats(
            page_number=1,
            image_count=image_count,
            relevant_image_count=relevant_image_count,
            largest_area_ratio=round(largest_area_ratio, 4),
            min_area_ratio=min_area_ratio,
            min_pixel_width=min_pixel_width,
            min_pixel_height=min_pixel_height,
            inspections=inspections,
        )


def first_page_has_relevant_images(pdf_path: Path) -> bool:
    return first_page_image_stats(pdf_path).relevant_image_count > 0
