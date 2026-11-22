"""Thin HTTP client for the local LLM server.

Since 22.11.2026 this talks to a llama.cpp server (llama-server, optionally behind
llama-swap) through the OpenAI-compatible `/v1/chat/completions` API instead of Ollama's
`/api/chat`. The class names keep "Ollama" so callers stay unchanged; the rules below still
hold and were kept on purpose: no JSON schema/grammar, thinking off, temperature 0, images
downscaled to JPEG. The history of each rule is Ollama 0.33.3's and is kept for context.

Neither client can pass a `format` JSON schema -- there is no parameter for it,
so a caller cannot reintroduce one by accident. Ollama 0.33.3 builds a GBNF
grammar from that schema, and the grammar breaks the answer in two ways.

It can terminate while the model is still mid-string; the next token then raises
``Unexpected empty grammar stack after accepting piece: / (14)`` in the sampler.
Ollama swallows the exception and answers HTTP 200 with empty message content,
which reaches the caller as a bare "no message content" error. Observed on
07.09.2026 on an invoice containing "Medizinische/Therapeutische" -- the "/" is
ordinary text, not a think token. Callers parse the JSON out of the free-text
answer (fenced ```json is what the model produces) and re-ask on invalid JSON.

The quieter failure, measured on the text path on 10.09.2026: under the grammar
the model simply omits optional properties. An OeGK response whose text reads
"Behandlerin: Dr. Testarzt Zeta" came back without a `doctor_name` key at
all, so pydantic filled the field with its null default and the model never
listed it in `missing_fields` -- it looked like a field absent from the
document. The identical call without the schema returned the name at confidence
0.95. Field order deviated from the schema too, so 0.33.3 is not enforcing the
grammar it built. A missing doctor_name capped Kassen matching at 0.857 and sent
every OeGK response to review.

Thinking must stay off (`chat_template_kwargs.enable_thinking: false`; Ollama: `think: false`):
with thinking enabled these models spend the whole
num_predict budget on the thinking block and return empty content with
done_reason "length" (reproduced 3/3).

Page renders are downscaled and re-encoded as JPEG before sending. This is an
accuracy measure, unrelated to the grammar crash: a 220 dpi A4 render is
4.67 Mpx, above ollama's own image_max_pixels of 4.19 Mpx, so it gets rescaled
server-side anyway. Doing it here with a clean LANCZOS pass measurably improves
reading (2/2 each way on the same invoice: raw PNG produced appointment_date
2026-05-31 from the sideways receipt string "31.5.2026" and found 1 line item;
the 2000 px JPEG produced the correct 2026-09-02 and all 6 line items).
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


VISION_IMAGE_MAX_EDGE = 2000
VISION_IMAGE_JPEG_QUALITY = 90


class OllamaError(RuntimeError):
    """Raised when the local Ollama API cannot produce a response."""


class OllamaContaminatedResponseError(OllamaError):
    """The answer belongs to another request: the server leaked earlier state.

    Ollama's ROCm build carries the recurrent state of hybrid Gated-DeltaNet
    models (qwen3.8) from one request into the next (ollama/ollama#18528,
    ggml-org/llama.cpp#29092). On 25.09.2026 an invoice extraction answered
    with another agent's `exec` tool call. When the leaked text parses as a
    tool call, Ollama's own parser trips over it and returns HTTP 500 with an
    XML error. This error only covers leaks shaped like tool calls -- leaked
    plain text arrives as an ordinary answer and cannot be told apart here.
    The actual protection is running on a backend without the leak (a
    dedicated Vulkan server instance); this is the tripwire.
    """


# The importer never sends tools, so any tool-call markup in an answer, or a
# tool-call parse failure on the server, can only come from someone else's
# conversation.
_TOOL_CALL_MARKERS = ("<tool_call>", "<function=", "</parameter>")
_TOOL_PARSE_ERROR_MARKERS = ("tool call parsing", "element <function>", "<function>")

_CONTAMINATION_HINT = (
    "The LLM server answered with content from another request (known state leak "
    "on the ROCm backend, ollama/ollama#18528). Nothing was imported. Make sure the "
    "importer uses its own LLM server instance on the Vulkan backend and retry the "
    "file."
)


def _payload(model: str, messages: list[dict], num_predict: int) -> dict:
    return {
        "model": model,
        "stream": False,
        "temperature": 0,
        "max_tokens": num_predict,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": messages,
    }


def _post_chat(base_url: str, payload: dict, *, timeout_seconds: int, what: str) -> str:
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = _error_body(exc)
        if any(marker in body for marker in _TOOL_PARSE_ERROR_MARKERS):
            raise OllamaContaminatedResponseError(
                f"{what}: HTTP {exc.code} {body[:200]}. {_CONTAMINATION_HINT}"
            ) from exc
        raise OllamaError(f"{what} failed: {exc} {body[:200]}".rstrip()) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OllamaError(f"{what} failed: {exc}") from exc

    choices = data.get("choices") if isinstance(data, dict) else None
    choice = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    )
    message = choice.get("message") or {}
    usage = (data.get("usage") or {}) if isinstance(data, dict) else {}
    content = message.get("content")
    if message.get("tool_calls") or (
        isinstance(content, str) and any(marker in content for marker in _TOOL_CALL_MARKERS)
    ):
        raise OllamaContaminatedResponseError(
            f"{what}: the answer contains a tool call. {_CONTAMINATION_HINT}"
        )
    if not isinstance(content, str) or not content.strip():
        raise OllamaError(
            f"{what} did not contain message content "
            f"(model={payload.get('model')}, finish_reason={choice.get('finish_reason')}, "
            f"completion_tokens={usage.get('completion_tokens')}, "
            f"prompt_tokens={usage.get('prompt_tokens')}, "
            f"thinking={bool(message.get('reasoning_content'))}); "
            "check the LLM server log at this timestamp for a server error"
        )
    return content.strip()


def _error_body(exc: urllib.error.HTTPError) -> str:
    """The server's error text. Ollama sent {"error": "..."} with `<` escaped as \\u003c,
    llama.cpp sends {"error": {"message": "..."}}."""
    try:
        raw = exc.read().decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - the body is diagnostics only.
        return ""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), str):
        return parsed["error"]
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        return str(parsed["error"].get("message", ""))
    return raw


@dataclass(frozen=True)
class VisionPageResult:
    page_number: int
    image_path: Path
    text: str

    def to_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "image_path": str(self.image_path),
            "text": self.text,
        }


class OllamaVisionClient:
    def __init__(self, *, base_url: str, model: str, timeout_seconds: int = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def describe_image(self, image_path: Path, prompt: str) -> str:
        return self.chat_with_images([image_path], prompt)

    def chat_with_images(
        self,
        images: list[Path],
        prompt: str,
        *,
        num_predict: int = 2048,
    ) -> str:
        content: list[dict] = [{"type": "text", "text": prompt}]
        content += [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64," + _encode_image(path)},
            }
            for path in images
        ]
        payload = _payload(self.model, [{"role": "user", "content": content}], num_predict)
        return _post_chat(
            self.base_url,
            payload,
            timeout_seconds=self.timeout_seconds,
            what="Ollama vision request",
        )


class OllamaTextClient:
    def __init__(self, *, base_url: str, model: str, timeout_seconds: int = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        num_predict: int = 2048,
    ) -> str:
        payload = _payload(self.model, list(messages), num_predict)
        return _post_chat(
            self.base_url, payload, timeout_seconds=self.timeout_seconds, what="Ollama text request"
        )


def _encode_image(path: Path) -> str:
    try:
        with Image.open(path) as image:
            image.load()
            prepared = image.convert("RGB")
            longest_edge = max(prepared.size)
            if longest_edge > VISION_IMAGE_MAX_EDGE:
                scale = VISION_IMAGE_MAX_EDGE / longest_edge
                prepared = prepared.resize(
                    (max(1, round(prepared.width * scale)), max(1, round(prepared.height * scale))),
                    Image.LANCZOS,
                )
            buffer = io.BytesIO()
            prepared.save(buffer, format="JPEG", quality=VISION_IMAGE_JPEG_QUALITY)
    except OSError as exc:
        raise OllamaError(f"Could not read vision image {path}: {exc}") from exc
    return base64.b64encode(buffer.getvalue()).decode("ascii")
