"""Office document → PDF preview conversion via LibreOffice headless."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import security_foundation as sec

_CONVERSION_TIMEOUT_SEC = 30
_MAC_SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"


class MaterialPreviewConversionError(Exception):
    """Office → PDF conversion failed (LibreOffice missing, timeout, corrupt file, etc.)."""


def find_libreoffice_bin() -> Optional[str]:
    env_bin = (os.environ.get("LIBREOFFICE_BIN") or "").strip()
    if env_bin and os.path.isfile(env_bin):
        return env_bin
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    if os.path.isfile(_MAC_SOFFICE):
        return _MAC_SOFFICE
    return None


def _format_updated_at_ts(updated_at: Any) -> str:
    if isinstance(updated_at, datetime):
        return updated_at.strftime("%Y%m%d%H%M%S")
    s = str(updated_at or "").strip()
    if not s:
        return datetime.now().strftime("%Y%m%d%H%M%S")
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s[:26])
        else:
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y%m%d%H%M%S")
    except ValueError:
        return datetime.now().strftime("%Y%m%d%H%M%S")


def preview_cache_rel_path(material_id: int, updated_at: Any) -> str:
    ts = _format_updated_at_ts(updated_at)
    return f"material_previews/{int(material_id)}-{ts}.pdf"


def _resolve_cache_abs_path(upload_dir: str, material_id: int, updated_at: Any) -> str:
    rel = preview_cache_rel_path(material_id, updated_at)
    try:
        return sec.resolve_upload_path(upload_dir, rel)
    except ValueError as exc:
        raise MaterialPreviewConversionError("invalid preview cache path") from exc


def convert_office_to_preview_pdf(
    *,
    source_abs: str,
    upload_dir: str,
    material_id: int,
    updated_at: Any,
) -> str:
    if not os.path.isfile(source_abs):
        raise MaterialPreviewConversionError("source file missing")

    cache_abs = _resolve_cache_abs_path(upload_dir, material_id, updated_at)
    if os.path.isfile(cache_abs):
        return cache_abs

    libreoffice_bin = find_libreoffice_bin()
    if not libreoffice_bin:
        raise MaterialPreviewConversionError("LibreOffice not installed")

    tmpdir = tempfile.mkdtemp(prefix="mat_preview_out_")
    tmp_profile_dir = tempfile.mkdtemp(prefix="mat_preview_profile_")
    try:
        profile_uri = Path(tmp_profile_dir).resolve().as_uri()
        cmd = [
            libreoffice_bin,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_uri}",
            "--convert-to",
            "pdf",
            "--outdir",
            tmpdir,
            source_abs,
        ]
        try:
            proc = subprocess.run(
                cmd,
                timeout=_CONVERSION_TIMEOUT_SEC,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise MaterialPreviewConversionError("conversion timeout") from exc

        if proc.returncode != 0:
            raise MaterialPreviewConversionError(
                f"LibreOffice exit {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()}"
            )

        stem = Path(source_abs).stem
        generated = os.path.join(tmpdir, f"{stem}.pdf")
        if not os.path.isfile(generated):
            pdfs = [f for f in os.listdir(tmpdir) if f.lower().endswith(".pdf")]
            if len(pdfs) == 1:
                generated = os.path.join(tmpdir, pdfs[0])
            else:
                raise MaterialPreviewConversionError("output PDF not found")

        os.makedirs(os.path.dirname(cache_abs), exist_ok=True)
        shutil.move(generated, cache_abs)
        return cache_abs
    except MaterialPreviewConversionError:
        raise
    except OSError as exc:
        raise MaterialPreviewConversionError(str(exc)) from exc
    finally:
        shutil.rmtree(tmp_profile_dir, ignore_errors=True)
        shutil.rmtree(tmpdir, ignore_errors=True)
