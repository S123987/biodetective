"""Configuration for the BioDetective web application."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PROJECT_ROOT / ".env")


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
_requested_gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
GEMINI_MODEL = _requested_gemini_model if _requested_gemini_model in {
    "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"
} else "gemini-3.8-flash"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_FILE_TEXT_CHARS = 48_000

