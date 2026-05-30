from pathlib import Path
from unittest.mock import Mock, patch
import json

import pytest

from health_importer.ai.ollama_client import OllamaError, OllamaTextClient, OllamaVisionClient


def test_describe_image_calls_local_ollama_chat(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
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


def test_describe_image_rejects_empty_response(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"png")
    response = Mock()
    response.read.return_value = b'{"message":{"content":""}}'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response):
        with pytest.raises(OllamaError):
            OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
                image, "prompt"
            )


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
