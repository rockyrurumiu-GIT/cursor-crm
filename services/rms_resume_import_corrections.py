"""RMS bulk resume import corrections via CSV (create / update / skip)."""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session

from schemas.rms import utc_date_str
from services.rms_applications import (
    parse_resume_file_for_storage,
    reject_candidate_name_reason,
)
from services.rms_candidates import _find_duplicate_candidate, detect_duplicate_candidate
from services.rms_resume_import import (
    _candidate_fields_from_parsed,
    _commit_single_file,
    _is_unsupported_file,
    _mask_email_wechat,
    _mask_phone,
    _normalize_import_phone,
    _sync_email_wechat_fields,
)
from services.rms_resumes import MAX_RESUME_BYTES

CORRECTION_INPUT_FIELDS = (
    "resume_file_path",
    "action",
    "candidate_id",
    "name",
    "phone",
    "email_wechat",
    "school",
    "major",
    "education_level",
    "source",
)

VALID_ACTIONS = frozenset({"create", "update", "skip"})

_PARSED_JSON_SYNC_KEYS = (
    "name",
    "phone",
    "email_wechat",
    "school",
    "major",
    "education_level",
    "source",
)

_UPDATE_CANDIDATE_KEYS = _PARSED_JSON_SYNC_KEYS

REPORT_CSV_FIELDS = (
    "row_index",
    "action",
    "resume_file_path",
    "candidate_id",
    "resume_id",
    "status",
    "name",
    "phone_masked",
    "email_masked",
    "duplicate_reason",
    "error",
)


def _csv_field_nonempty(row: Dict[str, Any], key: str) -> bool:
    return bool(str(row.get(key) or "").strip())


def _load_parsed_dict(parsed_json_str: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(parsed_json_str or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return parsed


def _sync_email_wechat_in_parsed(parsed: Dict[str, Any]) -> None:
    ew = str(parsed.get("email_wechat") or "").strip()
    if not ew:
        return
    parsed["email_wechat"] = ew
    if "@" in ew:
        parsed["email"] = ew
        parsed.pop("wechat", None)
    else:
        parsed["wechat"] = ew
        parsed.pop("email", None)


def _merge_csv_into_parsed(parsed_json_str: str, csv_row: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    parsed = _load_parsed_dict(parsed_json_str)
    for key in _PARSED_JSON_SYNC_KEYS:
        if _csv_field_nonempty(csv_row, key):
            parsed[key] = str(csv_row[key]).strip()
    _sync_email_wechat_in_parsed(parsed)
    return json.dumps(parsed, ensure_ascii=False), parsed


def _report_row(
    *,
    row_index: int,
    action: str = "",
    resume_file_path: str = "",
    candidate_id: Any = "",
    resume_id: Any = "",
    status: str = "",
    name: str = "",
    phone: str = "",
    email_wechat: str = "",
    duplicate_reason: str = "",
    error: str = "",
) -> Dict[str, Any]:
    return {
        "row_index": row_index,
        "action": action,
        "resume_file_path": resume_file_path,
        "candidate_id": candidate_id,
        "resume_id": resume_id,
        "status": status,
        "name": name,
        "phone_masked": _mask_phone(phone) if phone else "",
        "email_masked": _mask_email_wechat(email_wechat) if email_wechat else "",
        "duplicate_reason": duplicate_reason,
        "error": error,
    }


def _write_reports(
    report_dir: str | Path,
    rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Tuple[Path, Path]:
    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"rms_resume_correction_{stamp}.csv"
    json_path = out_dir / f"rms_resume_correction_{stamp}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in REPORT_CSV_FIELDS})

    payload = {"summary": summary, "rows": rows}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def _latest_resume_for_candidate(
    db: Session,
    RmsResume: Type[Any],
    candidate_id: int,
) -> Any:
    return (
        db.query(RmsResume)
        .filter(RmsResume.candidate_id == candidate_id)
        .order_by(RmsResume.created_at.desc(), RmsResume.id.desc())
        .first()
    )


def _duplicate_other_candidate(
    db: Session,
    RmsCandidate: Type[Any],
    *,
    name: str,
    phone: str,
    exclude_id: int,
) -> bool:
    dup = _find_duplicate_candidate(db, RmsCandidate, name=name, phone=phone)
    return dup is not None and int(dup.id) != int(exclude_id)


def _parse_candidate_id(raw: Any) -> Optional[int]:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def load_correction_rows(csv_path: str | Path) -> List[Dict[str, str]]:
    path = Path(csv_path)
    if not path.is_file():
        raise ValueError(f"csv file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        rows: List[Dict[str, str]] = []
        for raw in reader:
            norm = {
                (k or "").strip().lower(): str(v or "").strip()
                for k, v in (raw or {}).items()
            }
            row = {field: norm.get(field, "") for field in CORRECTION_INPUT_FIELDS}
            rows.append(row)
        return rows


def _fields_from_merged_parsed(parsed: Dict[str, Any], *, default_source: str) -> Dict[str, str]:
    source = str(parsed.get("source") or default_source or "批量导入").strip() or "批量导入"
    fields = _candidate_fields_from_parsed(parsed, source=source)
    _sync_email_wechat_fields(fields)
    return fields


def _apply_non_empty_csv_to_parsed(parsed: Dict[str, Any], csv_row: Dict[str, Any]) -> None:
    for key in _PARSED_JSON_SYNC_KEYS:
        if _csv_field_nonempty(csv_row, key):
            parsed[key] = str(csv_row[key]).strip()
    _sync_email_wechat_in_parsed(parsed)


def apply_resume_import_corrections(
    db: Session,
    *,
    csv_path: str | Path,
    dry_run: bool,
    commit: bool,
    uploaded_by_user_id: int,
    models: Dict[str, Type[Any]],
    report_dir: str | Path,
    upload_dir: str,
    default_source: str = "批量导入",
) -> Dict[str, Any]:
    if dry_run == commit:
        raise ValueError("exactly one of dry_run or commit must be True")

    RmsCandidate = models["RmsCandidate"]
    RmsResume = models["RmsResume"]

    input_rows = load_correction_rows(csv_path)
    rows: List[Dict[str, Any]] = []
    batch_seen: set[tuple[str, str]] = set()
    counts = {
        "scanned": len(input_rows),
        "would_create": 0,
        "created": 0,
        "would_update": 0,
        "updated": 0,
        "skipped": 0,
        "skipped_duplicate": 0,
        "failed": 0,
    }

    for idx, csv_row in enumerate(input_rows, start=1):
        action = str(csv_row.get("action") or "").strip().lower()
        resume_path_str = str(csv_row.get("resume_file_path") or "").strip()

        if action not in VALID_ACTIONS:
            counts["failed"] += 1
            rows.append(
                _report_row(
                    row_index=idx,
                    action=action,
                    resume_file_path=resume_path_str,
                    candidate_id=csv_row.get("candidate_id") or "",
                    status="failed",
                    error="invalid_action",
                )
            )
            continue

        if action == "skip":
            counts["skipped"] += 1
            rows.append(
                _report_row(
                    row_index=idx,
                    action=action,
                    resume_file_path=resume_path_str,
                    candidate_id=csv_row.get("candidate_id") or "",
                    status="skipped",
                )
            )
            continue

        if action == "create":
            _process_create_row(
                db,
                csv_row=csv_row,
                row_index=idx,
                resume_path_str=resume_path_str,
                dry_run=dry_run,
                uploaded_by_user_id=uploaded_by_user_id,
                upload_dir=upload_dir,
                default_source=default_source,
                RmsCandidate=RmsCandidate,
                RmsResume=RmsResume,
                batch_seen=batch_seen,
                counts=counts,
                rows=rows,
            )
            continue

        _process_update_row(
            db,
            csv_row=csv_row,
            row_index=idx,
            resume_path_str=resume_path_str,
            dry_run=dry_run,
            default_source=default_source,
            RmsCandidate=RmsCandidate,
            RmsResume=RmsResume,
            counts=counts,
            rows=rows,
        )

    summary = {**counts}
    report_csv, report_json = _write_reports(report_dir, rows, summary)
    return {
        **counts,
        "report_csv": str(report_csv),
        "report_json": str(report_json),
        "rows": rows,
    }


def _process_create_row(
    db: Session,
    *,
    csv_row: Dict[str, Any],
    row_index: int,
    resume_path_str: str,
    dry_run: bool,
    uploaded_by_user_id: int,
    upload_dir: str,
    default_source: str,
    RmsCandidate: Type[Any],
    RmsResume: Type[Any],
    batch_seen: set[tuple[str, str]],
    counts: Dict[str, int],
    rows: List[Dict[str, Any]],
) -> None:
    name_csv = str(csv_row.get("name") or "").strip()
    phone_csv = str(csv_row.get("phone") or "").strip()

    if not resume_path_str or not name_csv or not phone_csv:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name_csv,
                phone=phone_csv,
                email_wechat=str(csv_row.get("email_wechat") or ""),
                error="missing_required_fields",
            )
        )
        return

    file_path = Path(resume_path_str)
    if not file_path.is_file():
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name_csv,
                phone=phone_csv,
                error="file_not_found",
            )
        )
        return

    ext = file_path.suffix.lower()
    if _is_unsupported_file(ext):
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name_csv,
                phone=phone_csv,
                error="unsupported_file_type",
            )
        )
        return

    try:
        content = file_path.read_bytes()
    except OSError as exc:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name_csv,
                phone=phone_csv,
                error=str(exc)[:500],
            )
        )
        return

    if len(content) > MAX_RESUME_BYTES:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name_csv,
                phone=phone_csv,
                error="file_too_large",
            )
        )
        return

    try:
        parsed_text, parsed_json_str = parse_resume_file_for_storage(
            file_path.name, content
        )
    except Exception as exc:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name_csv,
                phone=phone_csv,
                error=str(exc)[:500],
            )
        )
        return

    merged_json_str, parsed = _merge_csv_into_parsed(parsed_json_str, csv_row)
    fields = _fields_from_merged_parsed(parsed, default_source=default_source)
    name = str(fields.get("name") or name_csv).strip()
    phone = _normalize_import_phone(fields.get("phone") or phone_csv)
    email_wechat = str(fields.get("email_wechat") or "").strip()

    if not name or not phone:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name,
                phone=phone or phone_csv,
                email_wechat=email_wechat,
                error="missing_name_or_phone",
            )
        )
        return

    fields["name"] = name
    fields["phone"] = phone

    name_reject = reject_candidate_name_reason(name, strict_length=True)
    if name_reject:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name,
                phone=phone,
                email_wechat=email_wechat,
                error="invalid_candidate_name",
            )
        )
        return

    key = (name, phone)
    if key in batch_seen or detect_duplicate_candidate(
        db, RmsCandidate, name=name, phone=phone
    ):
        counts["skipped_duplicate"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="skipped_duplicate",
                name=name,
                phone=phone,
                email_wechat=email_wechat,
                duplicate_reason="name_phone_match",
            )
        )
        return

    if dry_run:
        counts["would_create"] += 1
        batch_seen.add(key)
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="would_create",
                name=name,
                phone=phone,
                email_wechat=email_wechat,
            )
        )
        return

    try:
        cand_id, resume_id = _commit_single_file(
            db,
            fields=fields,
            file_path=file_path,
            content=content,
            parsed_text=parsed_text,
            parsed_json=merged_json_str,
            uploaded_by_user_id=uploaded_by_user_id,
            upload_dir=upload_dir,
            RmsCandidate=RmsCandidate,
            RmsResume=RmsResume,
        )
        counts["created"] += 1
        batch_seen.add(key)
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="created",
                name=name,
                phone=phone,
                email_wechat=email_wechat,
                candidate_id=cand_id,
                resume_id=resume_id,
            )
        )
    except Exception as exc:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="create",
                resume_file_path=resume_path_str,
                status="failed",
                name=name,
                phone=phone,
                email_wechat=email_wechat,
                error=str(exc)[:500],
            )
        )


def _process_update_row(
    db: Session,
    *,
    csv_row: Dict[str, Any],
    row_index: int,
    resume_path_str: str,
    dry_run: bool,
    default_source: str,
    RmsCandidate: Type[Any],
    RmsResume: Type[Any],
    counts: Dict[str, int],
    rows: List[Dict[str, Any]],
) -> None:
    cand_id = _parse_candidate_id(csv_row.get("candidate_id"))
    if cand_id is None:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="update",
                resume_file_path=resume_path_str,
                candidate_id=csv_row.get("candidate_id") or "",
                status="failed",
                error="missing_candidate_id",
            )
        )
        return

    candidate = db.query(RmsCandidate).filter(RmsCandidate.id == cand_id).first()
    if candidate is None:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="update",
                resume_file_path=resume_path_str,
                candidate_id=cand_id,
                status="failed",
                error="candidate_not_found",
            )
        )
        return

    patch: Dict[str, str] = {}
    if _csv_field_nonempty(csv_row, "phone"):
        phone = _normalize_import_phone(csv_row.get("phone"))
        if not phone:
            counts["failed"] += 1
            rows.append(
                _report_row(
                    row_index=row_index,
                    action="update",
                    resume_file_path=resume_path_str,
                    candidate_id=cand_id,
                    status="failed",
                    name=str(candidate.name or ""),
                    phone=str(csv_row.get("phone") or ""),
                    error="invalid_phone",
                )
            )
            return
        patch["phone"] = phone

    for key in ("name", "email_wechat", "school", "major", "education_level", "source"):
        if _csv_field_nonempty(csv_row, key):
            patch[key] = str(csv_row[key]).strip()

    final_name = patch.get("name", str(candidate.name or "").strip())
    final_phone = patch.get("phone", str(candidate.phone or "").strip())
    email_wechat = patch.get("email_wechat", str(candidate.email_wechat or "").strip())

    if not final_name or not final_phone:
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="update",
                resume_file_path=resume_path_str,
                candidate_id=cand_id,
                status="failed",
                name=final_name,
                phone=final_phone,
                email_wechat=email_wechat,
                error="missing_name_or_phone",
            )
        )
        return

    if _duplicate_other_candidate(
        db,
        RmsCandidate,
        name=final_name,
        phone=final_phone,
        exclude_id=cand_id,
    ):
        counts["failed"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="update",
                resume_file_path=resume_path_str,
                candidate_id=cand_id,
                status="failed",
                name=final_name,
                phone=final_phone,
                email_wechat=email_wechat,
                error="duplicate_name_phone",
            )
        )
        return

    if dry_run:
        counts["would_update"] += 1
        rows.append(
            _report_row(
                row_index=row_index,
                action="update",
                resume_file_path=resume_path_str,
                candidate_id=cand_id,
                status="would_update",
                name=final_name,
                phone=final_phone,
                email_wechat=email_wechat,
            )
        )
        return

    for key, val in patch.items():
        setattr(candidate, key, val)
    if "email_wechat" in patch:
        sync_data: Dict[str, Any] = {"email_wechat": patch["email_wechat"]}
        _sync_email_wechat_fields(sync_data)
        if sync_data.get("email"):
            candidate.email = sync_data["email"]
            candidate.wechat = ""
        elif sync_data.get("wechat"):
            candidate.wechat = sync_data["wechat"]
            candidate.email = ""
    candidate.updated_at = utc_date_str()

    resume = _latest_resume_for_candidate(db, RmsResume, cand_id)
    resume_id = ""
    if resume is not None:
        parsed = _load_parsed_dict(resume.parsed_json or "{}")
        _apply_non_empty_csv_to_parsed(parsed, csv_row)
        if not _csv_field_nonempty(csv_row, "source"):
            parsed.setdefault("source", str(candidate.source or default_source))
        resume.parsed_json = json.dumps(parsed, ensure_ascii=False)
        resume_id = int(resume.id)

    db.commit()
    db.refresh(candidate)
    counts["updated"] += 1
    rows.append(
        _report_row(
            row_index=row_index,
            action="update",
            resume_file_path=resume_path_str,
            candidate_id=cand_id,
            resume_id=resume_id,
            status="updated",
            name=final_name,
            phone=final_phone,
            email_wechat=email_wechat,
        )
    )
