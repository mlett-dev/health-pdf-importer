from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .schemas import VisionPageExtraction


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
        return self.chat_with_images(
            [image_path],
            prompt,
            response_format=VisionPageExtraction.model_json_schema(),
        )

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
            raise OllamaError("Ollama vision response did not contain message content")
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
    return base64.b64encode(path.read_bytes()).decode("ascii")
