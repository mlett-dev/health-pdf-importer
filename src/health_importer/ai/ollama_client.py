"""Thin HTTP client for the local Ollama API.

Vision calls deliberately do not pass a `format` JSON schema. Ollama 0.33.3
builds a GBNF grammar from it, and that grammar can terminate while the model is
still mid-string; the next token then raises
``Unexpected empty grammar stack after accepting piece: / (14)`` in the sampler.
Ollama swallows the exception and answers HTTP 200 with empty message content,
which reaches the caller as a bare "no message content" error. Observed on
07.09.2026 on an invoice containing "Medizinische/Therapeutische" -- the "/" is
ordinary text, not a think token. Callers parse the JSON out of the free-text
answer (fenced ```json is what the model produces) and re-ask on invalid JSON.

`think` must stay False: with thinking enabled these models spend the whole
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
        # Deliberately no response_format: see the module docstring on the
        # grammar crash. Callers validate the JSON and repair it instead.
        return self.chat_with_images([image_path], prompt)

    def chat_with_images(
        self,
        images: list[Path],
        prompt: str,
        *,
        response_format: dict | None = None,
        num_predict: int = 2048,
    ) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [_encode_image(path) for path in images],
                }
            ],
        }
        if response_format is not None:
            payload["format"] = response_format
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama vision request failed: {exc}") from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError(
                "Ollama vision response did not contain message content "
                f"(model={self.model}, done_reason={data.get('done_reason')}, "
                f"eval_count={data.get('eval_count')}, "
                f"prompt_eval_count={data.get('prompt_eval_count')}, "
                f"thinking={bool(data.get('message', {}).get('thinking'))}); "
                "check `journalctl -u ollama` at this timestamp for a sampler exception"
            )
        return content.strip()


class OllamaTextClient:
    def __init__(self, *, base_url: str, model: str, timeout_seconds: int = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        format: dict | str | None = None,
        response_format: dict | str | None = None,
        num_predict: int = 2048,
    ) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0,
                "num_predict": num_predict,
            },
            "messages": messages,
        }
        schema_format = response_format if response_format is not None else format
        if schema_format is not None:
            payload["format"] = schema_format
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama text request failed: {exc}") from exc

        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama text response did not contain message content")
        return content.strip()


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
