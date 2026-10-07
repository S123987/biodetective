"""Small standard-library client for a local Ollama server."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, path: str, payload: dict[str, Any] | None = None, timeout: float = 15) -> Any:
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")[:500]
            raise OllamaError(f"Local model service returned HTTP {exc.code}: {message}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError("Ollama is not responding at 127.0.0.1:11434. Start Ollama and try again.") from exc

    def is_available(self) -> bool:
        try:
            self._request("/api/version", timeout=2)
            return True
        except OllamaError:
            return False

    def version(self) -> str | None:
        try:
            return str(self._request("/api/version", timeout=2).get("version", "unknown"))
        except (OllamaError, AttributeError):
            return None

    def list_models(self) -> list[dict[str, Any]]:
        payload = self._request("/api/tags", timeout=5)
        return list(payload.get("models", []))

    def chat(self, model: str, messages: list[dict[str, str]], *, json_mode: bool = False, timeout: float = 900) -> str:
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 8192},
        }
        if json_mode:
            body["format"] = "json"
        response = self._request("/api/chat", body, timeout=timeout)
        return str(response.get("message", {}).get("content", "")).strip()

    def pull_model(self, model: str, progress: Callable[[str, int | None], None]) -> None:
        payload = json.dumps({"name": model, "stream": True}).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/pull",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                for raw_line in response:
                    if not raw_line.strip():
                        continue
                    event = json.loads(raw_line.decode("utf-8"))
                    status = str(event.get("status", "Downloading model…"))
                    total = event.get("total")
                    completed = event.get("completed")
                    percent = int(completed * 100 / total) if total and completed is not None else None
                    progress(status, percent)
                    if event.get("error"):
                        raise OllamaError(str(event["error"]))
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")[:500]
            raise OllamaError(f"Model download failed (HTTP {exc.code}): {message}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaError("Could not reach the local Ollama service or model registry.") from exc

