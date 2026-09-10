"""Thin HTTP client for the local Ollama API.

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
        return self.chat_with_images([image_path], prompt)

    def chat_with_images(
        self,
        images: list[Path],
        prompt: str,
        *,
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
