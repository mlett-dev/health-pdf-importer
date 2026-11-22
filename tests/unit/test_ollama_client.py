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
    response.read.return_value = (
        b'{"choices":[{"message":{"content":"sichtbarer Text"},"finish_reason":"stop"}]}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch(
        "health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response
    ) as urlopen:
        text = OllamaVisionClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3.6:35b-a3b-q8_0",
            timeout_seconds=7,
        ).describe_image(image, "prompt")

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://127.0.0.1:11434/v1/chat/completions"
    assert urlopen.call_args.kwargs["timeout"] == 7
    assert text == "sichtbarer Text"


def test_describe_image_sends_no_format_schema(tmp_path: Path) -> None:
    # A `format` schema makes ollama 0.33.3 build a GBNF grammar that can crash
    # the sampler mid-string and return empty content; callers validate instead.
    image = _write_png(tmp_path / "page.png")
    response = Mock()
    response.read.return_value = (
        b'{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch(
        "health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response
    ) as urlopen:
        OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
            image, "prompt"
        )

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert "format" not in payload
    assert payload["chat_template_kwargs"]["enable_thinking"] is False


def test_describe_image_rejects_empty_response(tmp_path: Path) -> None:
    image = _write_png(tmp_path / "page.png")
    response = Mock()
    response.read.return_value = (
        b'{"choices":[{"message":{"content":""},"finish_reason":"stop"}],'
        b'"usage":{"completion_tokens":0,"prompt_tokens":6155}}'
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
    assert "finish_reason=stop" in message
    assert "completion_tokens=0" in message
    assert "server log" in message


def test_text_chat_calls_local_ollama_chat() -> None:
    response = Mock()
    response.read.return_value = (
        b'{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch(
        "health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response
    ) as urlopen:
        text = OllamaTextClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3.6:35b-a3b-q8_0",
            timeout_seconds=5,
        ).chat([{"role": "user", "content": "hi"}])

    assert urlopen.call_args.args[0].full_url == "http://127.0.0.1:11434/v1/chat/completions"
    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert payload["chat_template_kwargs"]["enable_thinking"] is False
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 2048
    assert urlopen.call_args.kwargs["timeout"] == 5
    assert text == "{}"


def test_text_chat_sends_no_format_schema() -> None:
    # Same grammar that crashes the sampler mid-string also makes the model drop
    # optional properties: an OeGK response came back without doctor_name, which
    # capped Kassen matching at 0.857. The parameter is gone so no caller can
    # reintroduce it; callers validate and repair the JSON instead.
    response = Mock()
    response.read.return_value = (
        b'{"choices":[{"message":{"content":"{}"},"finish_reason":"stop"}]}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch(
        "health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response
    ) as urlopen:
        OllamaTextClient(
            base_url="http://127.0.0.1:11434",
            model="qwen3.6:35b-a3b-q8_0",
            timeout_seconds=5,
        ).chat([{"role": "user", "content": "hi"}], num_predict=123)

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    assert "format" not in payload
    assert payload["chat_template_kwargs"]["enable_thinking"] is False
    assert payload["max_tokens"] == 123


def test_text_chat_rejects_a_format_schema_argument() -> None:
    # The call the type checker already rejects has to fail at runtime too: this
    # is the guard against the schema being reintroduced by a future caller.
    client = OllamaTextClient(base_url="http://127.0.0.1:11434", model="m", timeout_seconds=5)

    with pytest.raises(TypeError):
        client.chat(
            [{"role": "user", "content": "hi"}],
            response_format={"type": "object"},  # pyright: ignore[reportCallIssue]
        )


def test_vision_images_are_downscaled_to_jpeg(tmp_path: Path) -> None:
    # Accuracy measure, not a bug workaround: a 220 dpi A4 render exceeds
    # ollama's image_max_pixels and reads worse than a clean 2000 px downscale.
    image = _write_png(tmp_path / "page.png", (1819, 2570))
    response = Mock()
    response.read.return_value = (
        b'{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}'
    )
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)

    with patch(
        "health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response
    ) as urlopen:
        OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
            image, "prompt"
        )

    payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
    url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    sent = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
    assert sent.format == "JPEG"
    assert sent.size == (1416, VISION_IMAGE_MAX_EDGE)


def test_vision_rejects_unreadable_image(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"not an image")

    with pytest.raises(OllamaError, match="Could not read vision image"):
        OllamaVisionClient(base_url="http://127.0.0.1:11434", model="vision").describe_image(
            image, "prompt"
        )


# --- Leaked state from other requests (ollama/ollama#18528) -----------------


def _ok_response(body: bytes) -> Mock:
    response = Mock()
    response.read.return_value = body
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=None)
    return response


def test_server_tool_call_parse_error_is_reported_as_contamination(tmp_path: Path) -> None:
    import urllib.error

    from health_importer.ai.ollama_client import OllamaContaminatedResponseError

    # The exact body Ollama 0.33.3 returned on 25.09.2026, `<` escaped as JSON.
    body = io.BytesIO(
        b'{"error":"XML syntax error on line 6: element \\u003cfunction\\u003e '
        b'closed by \\u003c/parameter\\u003e"}'
    )
    error = urllib.error.HTTPError("http://127.0.0.1:8080/api/chat", 500, "ISE", {}, body)
    image = _write_png(tmp_path / "page.png")
    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", side_effect=error):
        with pytest.raises(OllamaContaminatedResponseError, match="Vulkan backend"):
            OllamaVisionClient(base_url="http://127.0.0.1:8080", model="m").describe_image(
                image, "prompt"
            )


def test_tool_call_in_a_200_answer_is_reported_as_contamination() -> None:
    from health_importer.ai.ollama_client import OllamaContaminatedResponseError

    leaked = {
        "choices": [
            {
                "message": {
                    "content": "<tool_call>\n<function=exec>\n<parameter=command>\nls /tmp\n"
                    "</parameter>\n</function>\n</tool_call>"
                }
            }
        ]
    }
    response = _ok_response(json.dumps(leaked).encode())
    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", return_value=response):
        with pytest.raises(OllamaContaminatedResponseError):
            OllamaTextClient(base_url="http://127.0.0.1:8080", model="m").chat(
                [{"role": "user", "content": "x"}]
            )


def test_contamination_is_still_an_ollama_error() -> None:
    """Callers that already tolerate Ollama failures keep doing so."""
    from health_importer.ai.ollama_client import OllamaContaminatedResponseError

    assert issubclass(OllamaContaminatedResponseError, OllamaError)


def test_llama_cpp_error_body_is_reported(tmp_path: Path) -> None:
    import urllib.error

    body = io.BytesIO(
        b'{"error":{"code":500,"message":"model failed to load","type":"server_error"}}'
    )
    error = urllib.error.HTTPError(
        "http://127.0.0.1:8080/v1/chat/completions", 500, "ISE", {}, body
    )
    image = _write_png(tmp_path / "page.png")
    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", side_effect=error):
        with pytest.raises(OllamaError, match="model failed to load"):
            OllamaVisionClient(base_url="http://127.0.0.1:8080", model="m").describe_image(
                image, "prompt"
            )


def test_other_http_errors_stay_plain_ollama_errors(tmp_path: Path) -> None:
    import urllib.error

    from health_importer.ai.ollama_client import OllamaContaminatedResponseError

    body = io.BytesIO(b'{"error":"model requires more system memory"}')
    error = urllib.error.HTTPError("http://127.0.0.1:8080/api/chat", 500, "ISE", {}, body)
    image = _write_png(tmp_path / "page.png")
    with patch("health_importer.ai.ollama_client.urllib.request.urlopen", side_effect=error):
        with pytest.raises(OllamaError, match="more system memory") as info:
            OllamaVisionClient(base_url="http://127.0.0.1:8080", model="m").describe_image(
                image, "prompt"
            )
    assert not isinstance(info.value, OllamaContaminatedResponseError)
