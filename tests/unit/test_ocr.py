from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from health_importer.pdf.ocr import OcrError, run_local_ocr


def test_run_local_ocr_builds_local_ocr_command(tmp_path: Path) -> None:
    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "output_ocr.pdf"
    input_path.write_bytes(b"pdf")

    completed = Mock(returncode=0, stderr="", stdout="")
    with (
        patch("health_importer.pdf.ocr.subprocess.run", return_value=completed) as run,
        patch("health_importer.pdf.ocr.extract_embedded_text") as extract_text,
    ):
        output_path.write_bytes(b"ocr-pdf")
        extract_text.return_value.method = "embedded_text"
        extract_text.return_value.total_chars = 10
        extract_text.return_value.page_count = 1
        result = run_local_ocr(input_path, output_path, language="deu+eng", timeout_seconds=10)

    command = run.call_args.args[0]
    assert command[:3] == [__import__("sys").executable, "-m", "ocrmypdf"]
    assert "--deskew" in command
    assert "--rotate-pages" in command
    assert ["--language", "deu+eng"] == command[command.index("--language") : command.index("--language") + 2]
    assert run.call_args.kwargs["timeout"] == 10
    assert result.output_path == output_path


def test_run_local_ocr_raises_structured_error_on_failure(tmp_path: Path) -> None:
    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "output_ocr.pdf"
    input_path.write_bytes(b"pdf")

    completed = Mock(returncode=1, stderr="tesseract missing", stdout="")
    with patch("health_importer.pdf.ocr.subprocess.run", return_value=completed):
        with pytest.raises(OcrError, match="tesseract missing"):
            run_local_ocr(input_path, output_path)
