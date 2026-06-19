"""Delivery employee file constants."""
from __future__ import annotations

EMPLOYEE_FILE_ALLOWED_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".zip",
    ".rar",
}

EMPLOYEE_FILE_STATUS_SET = frozenset({"draft", "published", "deprecated"})
