"""RMS bulk resume import into talent pool (candidates + resumes only)."""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session

import security_foundation as sec
from schemas.rms import utc_date_str
from services.rms_applications import parse_resume_file_for_storage as _parse_resume_for_storage
from services.rms_candidates import PHONE_RE, detect_duplicate_candidate
from services.rms_resumes import MAX_RESUME_BYTES, RESUME_ALLOWED_SUFFIXES

SUPPORTED_SUFFIXES = RESUME_ALLOWED_SUFFIXES

REPORT_CSV_FIELDS = (
    "file_path",
    "file_name",
    "status",
    "candidate_id",
    "resume_id",
    "name",
    "phone_masked",
    "email_masked",
    "duplicate_reason",
    "parse_status",
    "error",
)

_CANDIDATE_FIELD_KEYS = (
    "name",
    "phone",
    "email",
    "wechat",
    "email_wechat",
    "age",
    "work_years",
    "school",
    "major",
    "education_level",
    "gender",
    "marital_status",
    "city",
    "current_company",
    "current_title",
)


def _mask_phone(value: str) -> str:
    s = (value or "").strip()
    if len(s) <= 7:
        return "***"
    return f"{s[:3]}****{s[-4:]}"


def _mask_email(value: str) -> str:
    s = (value or "").strip()
    if "@" not in s:
        return "***"
    local, _, domain = s.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _mask_email_wechat(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if "@" in s:
        return _mask_email(s)
    return f"{s[0]}***{s[-1]}" if len(s) > 2 else "**"


def parse_resume_file_for_storage(file_name: str, content: bytes) -> tuple[str, str]:
    """Wrapper for tests to monkeypatch without touching rms_applications."""
    return _parse_resume_for_storage(file_name, content)


def discover_resume_files(
    source_dir: str | Path,
    *,
    recursive: bool = False,
    limit: int | None = None,
) -> List[Path]:
    root = Path(source_dir)
    if not root.is_dir():
        raise ValueError(f"source_dir is not a directory: {root}")
    paths: List[Path] = []
    iterator = root.rglob("*") if recursive else root.iterdir()
    for entry in sorted(iterator, key=lambda p: str(p).lower()):
        if not entry.is_file():
            continue
        paths.append(entry.resolve())
        if limit is not None and len(paths) >= limit:
            break
    return paths


def _is_supported_suffix(ext: str) -> bool:
    return ext.lower() in SUPPORTED_SUFFIXES


def _is_unsupported_file(ext: str) -> bool:
    ext = ext.lower()
    if ext in SUPPORTED_SUFFIXES:
        return False
    return True


def _normalize_import_phone(phone: Any) -> Optional[str]:
    p = str(phone or "").strip()
    if not p or not PHONE_RE.match(p):
        return None
    return p


def _sync_email_wechat_fields(data: Dict[str, Any]) -> None:
    ew = str(data.get("email_wechat") or "").strip()
    if not ew:
        return
    data["email_wechat"] = ew
    if "@" in ew:
        data["email"] = ew
    else:
        data["wechat"] = ew


def _candidate_fields_from_parsed(parsed: Dict[str, Any], *, source: str) -> Dict[str, str]:
    out: Dict[str, str] = {k: str(parsed.get(k) or "").strip() for k in _CANDIDATE_FIELD_KEYS}
    out["source"] = source
    _sync_email_wechat_fields(out)
    return out


def _parse_status(parsed: Dict[str, Any], parsed_text: str) -> str:
    name = str(parsed.get("name") or "").strip()
    phone = _normalize_import_phone(parsed.get("phone"))
    if name and phone:
        return "parsed"
    if not parsed_text and not any(str(parsed.get(k) or "").strip() for k in _CANDIDATE_FIELD_KEYS):
        return "empty"
    return "partial"


def _report_row(
    *,
    file_path: Path,
    status: str,
    name: str = "",
    phone: str = "",
    email: str = "",
    email_wechat: str = "",
    candidate_id: Any = "",
    resume_id: Any = "",
    duplicate_reason: str = "",
    parse_status: str = "",
    error: str = "",
) -> Dict[str, Any]:
    contact = email or email_wechat
    return {
        "file_path": str(file_path),
        "file_name": file_path.name,
        "status": status,
        "candidate_id": candidate_id,
        "resume_id": resume_id,
        "name": name,
        "phone_masked": _mask_phone(phone) if phone else "",
        "email_masked": _mask_email_wechat(contact) if contact else "",
        "duplicate_reason": duplicate_reason,
        "parse_status": parse_status,
        "error": error,
    }


def _save_resume_bytes(
    upload_dir: str,
    candidate_id: int,
    file_name: str,
    content: bytes,
) -> Tuple[str, str, str]:
    raw_name = file_name or ""
    ext = os.path.splitext(raw_name)[1].lower()
    safe = sec.safe_visit_attachment_name(raw_name)
    if not os.path.splitext(safe)[1]:
        safe = safe + ext
    rel = f"rms/resumes/{candidate_id}/{int(time.time() * 1000000)}_{safe}"
    abs_target = sec.resolve_upload_path(upload_dir, rel)
    os.makedirs(os.path.dirname(abs_target), exist_ok=True)
    with open(abs_target, "wb") as f:
        f.write(content)
    return rel, ext.lstrip("."), abs_target


def _remove_file_if_exists(abs_path: str) -> None:
    if abs_path and os.path.isfile(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass


def _write_reports(
    report_dir: str | Path,
    rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Tuple[Path, Path]:
    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"rms_resume_import_{stamp}.csv"
    json_path = out_dir / f"rms_resume_import_{stamp}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in REPORT_CSV_FIELDS})

    payload = {"summary": summary, "rows": rows}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def _is_batch_duplicate(
    db: Session,
    RmsCandidate: Type[Any],
    *,
    name: str,
    phone: str,
    batch_seen: set[tuple[str, str]],
) -> bool:
    key = (name, phone)
    if key in batch_seen:
        return True
    if detect_duplicate_candidate(db, RmsCandidate, name=name, phone=phone):
        return True
    return False


def _commit_single_file(
    db: Session,
    *,
    fields: Dict[str, str],
    file_path: Path,
    content: bytes,
    parsed_text: str,
    parsed_json: str,
    uploaded_by_user_id: int,
    upload_dir: str,
    RmsCandidate: Type[Any],
    RmsResume: Type[Any],
) -> Tuple[int, int]:
    now = utc_date_str()
    candidate = RmsCandidate(
        name=fields.get("name") or "",
        phone=fields.get("phone") or "",
        email=fields.get("email") or "",
        wechat=fields.get("wechat") or "",
        email_wechat=fields.get("email_wechat") or "",
        age=fields.get("age") or "",
        work_years=fields.get("work_years") or "",
        education_level=fields.get("education_level") or "",
        school=fields.get("school") or "",
        major=fields.get("major") or "",
        gender=fields.get("gender") or "",
        marital_status=fields.get("marital_status") or "",
        city=fields.get("city") or "",
        current_company=fields.get("current_company") or "",
        current_title=fields.get("current_title") or "",
        source=fields.get("source") or "",
        tags="[]",
        created_by_user_id=uploaded_by_user_id,
        created_at=now,
        updated_at=now,
    )
    saved_abs = ""
    try:
        db.add(candidate)
        db.flush()
        rel_path, file_type, saved_abs = _save_resume_bytes(
            upload_dir,
            int(candidate.id),
            file_path.name,
            content,
        )
        resume = RmsResume(
            candidate_id=int(candidate.id),
            file_name=file_path.name,
            file_path=rel_path,
            file_type=file_type,
            parsed_text=parsed_text,
            parsed_json=parsed_json,
            uploaded_by=uploaded_by_user_id,
            created_at=now,
        )
        db.add(resume)
        db.commit()
        db.refresh(candidate)
        db.refresh(resume)
        return int(candidate.id), int(resume.id)
    except Exception:
        db.rollback()
        _remove_file_if_exists(saved_abs)
        raise


def import_resume_batch(
    db: Session,
    *,
    source_dir: str | Path,
    dry_run: bool,
    commit: bool,
    recursive: bool = False,
    source: str = "批量导入",
    uploaded_by_user_id: int,
    models: Dict[str, Type[Any]],
    report_dir: str | Path,
    upload_dir: str,
    limit: int | None = None,
) -> Dict[str, Any]:
    if dry_run == commit:
        raise ValueError("exactly one of dry_run or commit must be True")

    RmsCandidate = models["RmsCandidate"]
    RmsResume = models["RmsResume"]

    files = discover_resume_files(source_dir, recursive=recursive, limit=limit)
    rows: List[Dict[str, Any]] = []
    batch_seen: set[tuple[str, str]] = set()
    counts = {
        "scanned": len(files),
        "supported": 0,
        "would_create": 0,
        "created": 0,
        "skipped_duplicate": 0,
        "skipped_unparseable": 0,
        "skipped_unsupported": 0,
        "failed": 0,
    }

    for file_path in files:
        ext = file_path.suffix.lower()
        if _is_unsupported_file(ext):
            counts["skipped_unsupported"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="skipped_unsupported",
                    error="unsupported_file_type",
                )
            )
            continue

        counts["supported"] += 1
        try:
            content = file_path.read_bytes()
        except OSError as exc:
            counts["failed"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="failed",
                    error=str(exc)[:500],
                )
            )
            continue

        if len(content) > MAX_RESUME_BYTES:
            counts["failed"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="failed",
                    error="file_too_large",
                )
            )
            continue

        try:
            parsed_text, parsed_json_str = parse_resume_file_for_storage(
                file_path.name, content
            )
        except Exception as exc:
            counts["failed"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="failed",
                    parse_status="empty",
                    error=str(exc)[:500],
                )
            )
            continue

        try:
            parsed = json.loads(parsed_json_str or "{}")
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}

        pstatus = _parse_status(parsed, parsed_text)
        fields = _candidate_fields_from_parsed(parsed, source=source)
        name = str(fields.get("name") or "").strip()
        phone = _normalize_import_phone(fields.get("phone"))

        if not name or not phone:
            counts["skipped_unparseable"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="skipped_unparseable",
                    name=name,
                    phone=phone or "",
                    email=fields.get("email") or "",
                    email_wechat=fields.get("email_wechat") or "",
                    parse_status=pstatus,
                    error="missing_name_or_phone",
                )
            )
            continue

        fields["name"] = name
        fields["phone"] = phone

        if _is_batch_duplicate(db, RmsCandidate, name=name, phone=phone, batch_seen=batch_seen):
            counts["skipped_duplicate"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="skipped_duplicate",
                    name=name,
                    phone=phone,
                    email=fields.get("email") or "",
                    email_wechat=fields.get("email_wechat") or "",
                    duplicate_reason="name_phone_match",
                    parse_status=pstatus,
                )
            )
            continue

        if dry_run:
            counts["would_create"] += 1
            batch_seen.add((name, phone))
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="would_create",
                    name=name,
                    phone=phone,
                    email=fields.get("email") or "",
                    email_wechat=fields.get("email_wechat") or "",
                    parse_status=pstatus,
                )
            )
            continue

        try:
            cand_id, resume_id = _commit_single_file(
                db,
                fields=fields,
                file_path=file_path,
                content=content,
                parsed_text=parsed_text,
                parsed_json=parsed_json_str,
                uploaded_by_user_id=uploaded_by_user_id,
                upload_dir=upload_dir,
                RmsCandidate=RmsCandidate,
                RmsResume=RmsResume,
            )
            counts["created"] += 1
            batch_seen.add((name, phone))
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="created",
                    name=name,
                    phone=phone,
                    email=fields.get("email") or "",
                    email_wechat=fields.get("email_wechat") or "",
                    candidate_id=cand_id,
                    resume_id=resume_id,
                    parse_status=pstatus,
                )
            )
        except Exception as exc:
            counts["failed"] += 1
            rows.append(
                _report_row(
                    file_path=file_path,
                    status="failed",
                    name=name,
                    phone=phone,
                    email=fields.get("email") or "",
                    email_wechat=fields.get("email_wechat") or "",
                    parse_status=pstatus,
                    error=str(exc)[:500],
                )
            )

    summary = {**counts}
    csv_path, json_path = _write_reports(report_dir, rows, summary)
    return {
        **counts,
        "report_csv": str(csv_path),
        "report_json": str(json_path),
        "rows": rows,
    }
