from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from health_importer.pdf.extract_text import PdfTextExtraction, extract_embedded_text


class OcrError(RuntimeError):
    """Raised when local OCR fails."""


@dataclass(frozen=True)
class OcrResult:
    input_path: Path
    output_path: Path
    language: str
    text: PdfTextExtraction


def run_local_ocr(
    input_path: Path,
    output_path: Path,
    *,
    language: str = "deu+eng",
    deskew: bool = True,
    rotate_pages: bool = True,
    timeout_seconds: int = 300,
) -> OcrResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "ocrmypdf"]
    if deskew:
        command.append("--deskew")
    if rotate_pages:
        command.append("--rotate-pages")
    command.extend(["--language", language, str(input_path), str(output_path)])

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise OcrError(f"OCR timed out after {timeout_seconds} seconds") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise OcrError(f"OCR failed with exit code {completed.returncode}: {stderr}")
    if not output_path.exists():
        raise OcrError(f"OCR finished without creating output file: {output_path}")

    return OcrResult(
        input_path=input_path,
        output_path=output_path,
        language=language,
        text=extract_embedded_text(output_path),
    )
