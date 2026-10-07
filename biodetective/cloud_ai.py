"""Server-side adapter for the Gemini API."""

from __future__ import annotations

import json
import re
from threading import Lock
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from .config import GEMINI_API_KEY, GEMINI_MODEL


MODEL_OPTIONS = [
    {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "description": "Most capable Flash · complex reasoning"},
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "description": "Balanced · routine research tasks"},
    {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite", "description": "Fast · high-throughput fallback"},
    {"id": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash-Lite", "description": "Fastest · shorter tasks"},
]
ALLOWED_MODELS = {item["id"] for item in MODEL_OPTIONS}
ALLOWED_REASONING = {"low", "medium", "high"}
_CAPACITY_FALLBACKS = {
    "gemini-3.8-flash": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "gemini-3.5-flash": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "gemini-3.5-flash-lite": ["gemini-3.1-flash-lite"],
    "gemini-3.1-flash-lite": [],
}


class AIConfigurationError(RuntimeError):
    pass


_CLIENT: genai.Client | None = None
_CLIENT_LOCK = Lock()


def client() -> genai.Client:
    global _CLIENT
    if not GEMINI_API_KEY:
        raise AIConfigurationError(
            "Gemini is not configured. Create a Gemini API key in Google AI Studio, add GEMINI_API_KEY to the project .env.local file, and restart BioDetective."
        )
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                _CLIENT = genai.Client(api_key=GEMINI_API_KEY)
    return _CLIENT


def _model(value: str) -> str:
    return value if value in ALLOWED_MODELS else GEMINI_MODEL if GEMINI_MODEL in ALLOWED_MODELS else "gemini-3.8-flash"


def _reasoning(value: str) -> str:
    return value if value in ALLOWED_REASONING else "medium"


def _contents(value: Any) -> Any:
    """Map chat history into Gemini's user/model turn format."""
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return str(value)
    messages = []
    for item in value:
        if not isinstance(item, dict):
            continue
        role = "model" if item.get("role") == "assistant" else "user"
        text = str(item.get("content", "")).strip()
        if not text:
            continue
        if messages and messages[-1].role == role:
            messages[-1] = types.Content(role=role, parts=[*(messages[-1].parts or []), types.Part.from_text(text=text)])
        else:
            messages.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    return messages


def _config(instructions: str, reasoning_effort: str, *, json_output: bool = False) -> types.GenerateContentConfig:
    values: dict[str, Any] = {
        "system_instruction": instructions,
        "thinking_config": types.ThinkingConfig(thinking_level=_reasoning(reasoning_effort)),
    }
    if json_output:
        values["response_mime_type"] = "application/json"
    return types.GenerateContentConfig(**values)


def _is_high_demand(exc: APIError) -> bool:
    try:
        status = int(getattr(exc, "code", 0) or 0)
    except (TypeError, ValueError):
        status = 0
    message = str(getattr(exc, "message", "") or exc).lower()
    return status == 503 and any(term in message for term in ("high demand", "overloaded", "capacity"))


def _model_label(model: str) -> str:
    return next((item["label"] for item in MODEL_OPTIONS if item["id"] == model), model)


def _generate_content(
    model: str,
    contents: Any,
    config: types.GenerateContentConfig | None = None,
) -> tuple[Any, str]:
    selected = _model(model)
    candidates = [selected] + _CAPACITY_FALLBACKS.get(selected, [])
    for index, candidate in enumerate(candidates):
        try:
            arguments: dict[str, Any] = {"model": candidate, "contents": contents}
            if config is not None:
                arguments["config"] = config
            return client().models.generate_content(**arguments), candidate
        except APIError as exc:
            if not _is_high_demand(exc) or index == len(candidates) - 1:
                raise
    raise RuntimeError("No Gemini model was available to answer this request.")


def _fallback_notice(selected: str, used: str) -> str | None:
    if used == selected:
        return None
    return f"{_model_label(selected)} was busy, so this response used {_model_label(used)}."


def response_text(
    instructions: str,
    content: Any,
    *,
    web_search: bool = False,
    model: str = GEMINI_MODEL,
    reasoning_effort: str = "medium",
) -> tuple[str, list[dict[str, str]]]:
    del web_search  # Chat citations come from BioDetective's scholarly literature indexes.
    response, used_model = _generate_content(
        model,
        _contents(content),
        _config(instructions, reasoning_effort),
    )
    reply = str(response.text or "").strip()
    notice = _fallback_notice(_model(model), used_model)
    if notice:
        reply = f"> **Model availability:** {notice}\n\n{reply}"
    return reply, []


def response_json(
    instructions: str,
    content: str,
    *,
    model: str = GEMINI_MODEL,
    reasoning_effort: str = "medium",
) -> dict[str, Any]:
    response, used_model = _generate_content(model, content, _config(instructions, reasoning_effort, json_output=True))
    text = str(response.text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("The AI returned an invalid structured response.")
    notice = _fallback_notice(_model(model), used_model)
    if notice:
        value["_provider_notice"] = notice
    return value


def transcribe(audio_file: Any) -> str:
    filename, stream, mime_type = audio_file
    raw = stream.read()
    if not raw:
        return ""
    if mime_type == "application/octet-stream":
        suffix = str(filename).rsplit(".", 1)[-1].lower()
        mime_type = {
            "webm": "audio/webm", "mp4": "audio/mp4", "m4a": "audio/mp4", "ogg": "audio/ogg",
            "wav": "audio/wav", "mp3": "audio/mpeg", "mpeg": "audio/mpeg", "mpga": "audio/mpeg", "flac": "audio/flac",
        }.get(suffix, "audio/webm")
    response, _used_model = _generate_content(
        GEMINI_MODEL,
        [
            "Transcribe the spoken words accurately. Return only the transcription, preserving the speaker's language and wording.",
            types.Part.from_bytes(data=raw, mime_type=mime_type),
        ],
    )
    return str(response.text or "").strip()


__all__ = [
    "AIConfigurationError", "APIError", "ALLOWED_MODELS", "ALLOWED_REASONING", "GEMINI_MODEL", "MODEL_OPTIONS",
    "client", "response_json", "response_text", "transcribe",
]

