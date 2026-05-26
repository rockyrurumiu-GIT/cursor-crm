"""Shared CSV utility functions used across delivery domains."""
from __future__ import annotations

import unicodedata


def strip_csv_header_noise(s: str) -> str:
    """去掉 BOM、零宽字符、不间断空格等。"""
    t = unicodedata.normalize("NFKC", str(s))
    t = t.strip().strip("\ufeff")
    t = t.replace("\u00a0", "").replace("\u3000", "")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Cf")
    return t.strip()
