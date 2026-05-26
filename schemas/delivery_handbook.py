"""Delivery Handbook constants and schema definitions (Phase 5D)."""
from __future__ import annotations

HANDBOOK_ALLOWED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".doc",
    ".mp4",
    ".webm",
    ".ogg",
    ".mov",
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
}

HANDBOOK_STATUS_SET = frozenset({"draft", "published", "deprecated"})

HANDBOOK_SEARCH_BODY_MAX = 2_000_000
HANDBOOK_SEARCH_SNIPPET_LIST = 780
HANDBOOK_SEARCH_SNIPPET_MODAL = min(32_000, HANDBOOK_SEARCH_BODY_MAX)
HANDBOOK_OCR_MAX_PAGES = 120
HANDBOOK_OCR_ZOOM = 2.0
