import base64
import io
from pathlib import Path
from unittest.mock import Mock, patch
import json

import pytest
from PIL import Image

from health_importer.ai.ollama_client import (
    VISION_IMAGE_MAX_EDGE,
    OllamaError,
    OllamaTextClient,
    OllamaVisionClient,
)


def _write_png(path: Path, size: tuple[int, int] = (40, 60)) -> Path:
    Image.new("RGB", size, "white").save(path)
    return path


def test_describe_image_calls_local_ollama_chat(tmp_path: Path) -> None:
    image = _write_png(tmp_path / "page.png")
    response = Mock()
    response.read.return_value = b'{"message":{"content":"sichtbarer Text"}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response) as urlopen:
        text = OllamaVisionClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3.6:35b-a3b-q8_0",
            timeout_seconds=7,
        ).describe_image(image, "prompt")

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/api/chat"
    assert urlopen.call_args.kwargs["timeout"] == 7
    assert text == "sichtbarer Text"


def test_describe_image_sends_no_format_schema(tmp_path: Path) -> None:
    # A `format` schema makes ollama 0.33.3 build a GBNF grammar that can crash
    # the sampler mid-string and return empty content; callers validate instead.
    image = _write_png(tmp_path / "page.png")
    response = Mock()
    response.read.return_value = b'{"message":{"content":"{}"}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response) as urlopen:
        OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
            image, "prompt"
        )

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert "format" not in payload
    assert payload["think"] is False


def test_describe_image_rejects_empty_response(tmp_path: Path) -> None:
    image = _write_png(tmp_path / "page.png")
    response = Mock()
    response.read.return_value = (
        b'{"message":{"content":""},"done_reason":"stop","eval_count":0,'
        b'"prompt_eval_count":6155}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response):
        with pytest.raises(OllamaError) as excinfo:
            OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
                image, "prompt"
            )

    # These fields are what distinguishes a sampler crash from a thinking overrun.
    message = str(excinfo.value)
    assert "done_reason=stop" in message
    assert "eval_count=0" in message
    assert "journalctl" in message


def test_text_chat_calls_local_ollama_chat() -> None:
    response = Mock()
    response.read.return_value = b'{"message":{"content":"{}"}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response) as urlopen:
        text = OllamaTextClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3.6:35b-a3b-q8_0",
            timeout_seconds=5,
        ).chat([{"role": "user", "content": "hi"}])

    assert urlopen.call_args.args[0].full_url == "http://127.0.0.1:11434/api/chat"
    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert payload["think"] is False
    assert payload["options"]["temperature"] == 0
    assert payload["options"]["num_predict"] == 2048
    assert urlopen.call_args.kwargs["timeout"] == 5
    assert text == "{}"


def test_text_chat_sends_schema_format_and_num_predict() -> None:
    response = Mock()
    response.read.return_value = b'{"message":{"content":"{}"}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response) as urlopen:
        OllamaTextClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3.6:35b-a3b-q8_0",
            timeout_seconds=5,
        ).chat(
            [{"role": "user", "content": "hi"}],
            response_format={"type": "object"},
            num_predict=123,
        )

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert payload["format"] == {"type": "object"}
    assert payload["options"]["num_predict"] == 123


def test_vision_images_are_downscaled_to_jpeg(tmp_path: Path) -> None:
    # Accuracy measure, not a bug workaround: a 220 dpi A4 render exceeds
    # ollama's image_max_pixels and reads worse than a clean 2000 px downscale.
    image = _write_png(tmp_path / "page.png", (1819, 2570))
    response = Mock()
    response.read.return_value = b'{"message":{"content":"ok"}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch(
        "health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response
    ) as urlopen:
        OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
            image, "prompt"
        )

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    sent = Image.open(io.BytesIO(base64.b64decode(payload["messages"][0]["images"][0])))
    assert sent.format == "JPEG"
    assert sent.size == (1416, VISION_IMAGE_MAX_EDGE)


def test_vision_rejects_unreadable_image(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"not an image")

    with pytest.raises(OllamaError, match="Could not read vision image"):
        OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
            image, "prompt"
        )
