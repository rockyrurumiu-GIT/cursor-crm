"""OCR retry for RMS bulk import rows missing name and/or phone."""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session

from schemas.rms import utc_date_str
from services.rms_applications import (
    _extract_draft_fields_from_text,
    reject_candidate_name_reason,
)
from services.rms_resume_import import (
    _candidate_fields_from_parsed,
    _commit_single_file,
    _is_batch_duplicate,
    _normalize_import_phone,
)
from services.rms_resumes import MAX_RESUME_BYTES

REPORT_CSV_FIELDS = (
    "resume_file_path",
    "candidate_id",
    "resume_id",
    "original_name",
    "original_phone",
    "ocr_name",
    "ocr_phone",
    "final_name",
    "final_phone",
    "status",
    "error",
    "conflict_reason",
)

OCR_MAX_PAGES = 5
OCR_ZOOM = 2.0
TESSERACT_LANG = "chi_sim+eng"
TESSERACT_MISSING_MSG = (
    "Tesseract not found. Install with: brew install tesseract tesseract-lang"
)


def _normalize_row(raw: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, val in (raw or {}).items():
        out[(key or "").strip().lower()] = str(val or "").strip()
    return out


def _parse_candidate_id(raw: Any) -> Optional[int]:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _raw_path_from_row(row: Dict[str, str]) -> str:
    return (row.get("resume_file_path") or row.get("file_path") or "").strip()


def resolve_resume_file_path(raw_path: str, report_csv: Path) -> Optional[Path]:
    val = (raw_path or "").strip()
    if not val:
        return None
    p = Path(val)
    if p.is_absolute():
        return p if p.is_file() else None
    via_report = report_csv.parent / p
    if via_report.is_file():
        return via_report
    via_cwd = Path.cwd() / p
    if via_cwd.is_file():
        return via_cwd
    return None


def _report_row(**kwargs: Any) -> Dict[str, Any]:
    return {field: kwargs.get(field, "") for field in REPORT_CSV_FIELDS}


def _write_reports(
    report_dir: str | Path,
    rows: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> Tuple[Path, Path]:
    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"rms_resume_ocr_retry_{stamp}.csv"
    json_path = out_dir / f"rms_resume_ocr_retry_{stamp}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(REPORT_CSV_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in REPORT_CSV_FIELDS})

    payload = {"summary": summary, "rows": rows}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def load_import_report_rows(report_csv: str | Path) -> List[Dict[str, str]]:
    path = Path(report_csv)
    if not path.is_file():
        raise ValueError(f"report csv not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [_normalize_row(raw) for raw in reader]


def _original_fields_from_db(
    db: Session,
    RmsCandidate: Type[Any],
    candidate_id: int,
) -> Tuple[str, str]:
    candidate = db.query(RmsCandidate).filter(RmsCandidate.id == candidate_id).first()
    if candidate is None:
        return "", ""
    return str(candidate.name or "").strip(), str(candidate.phone or "").strip()


def _row_needs_ocr(
    row: Dict[str, str],
    *,
    db: Session,
    RmsCandidate: Type[Any],
) -> bool:
    cand_id = _parse_candidate_id(row.get("candidate_id"))
    if cand_id is not None:
        name, phone = _original_fields_from_db(db, RmsCandidate, cand_id)
        return not name or not phone

    name = (row.get("name") or "").strip()
    phone = (row.get("phone") or "").strip()
    phone_masked = (row.get("phone_masked") or "").strip()
    has_phone = bool(phone) or bool(phone_masked)
    return not name or not has_phone


def _original_fields_for_row(
    row: Dict[str, str],
    *,
    db: Session,
    RmsCandidate: Type[Any],
) -> Tuple[str, str]:
    cand_id = _parse_candidate_id(row.get("candidate_id"))
    if cand_id is not None:
        return _original_fields_from_db(db, RmsCandidate, cand_id)
    return (row.get("name") or "").strip(), (row.get("phone") or "").strip()


def _merge_ocr_fields(
    original_name: str,
    original_phone: str,
    ocr_name: str,
    ocr_phone: str,
) -> Tuple[str, str, str, Dict[str, str]]:
    conflict_reasons: List[str] = []
    final_name = original_name
    final_phone = original_phone
    patch: Dict[str, str] = {}

    if original_name and ocr_name and original_name != ocr_name:
        conflict_reasons.append("name")
    elif not original_name and ocr_name:
        final_name = ocr_name
        patch["name"] = ocr_name

    if original_phone and ocr_phone and original_phone != ocr_phone:
        conflict_reasons.append("phone")
    elif not original_phone and ocr_phone:
        final_phone = ocr_phone
        patch["phone"] = ocr_phone

    return final_name, final_phone, ";".join(conflict_reasons), patch


def extract_text_with_tesseract(pdf_path: str | Path) -> str:
    if shutil.which("tesseract") is None:
        raise RuntimeError(TESSERACT_MISSING_MSG)

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(f"PyMuPDF not installed ({exc})") from exc

    path = Path(pdf_path)
    doc = fitz.open(str(path))
    try:
        mat = fitz.Matrix(OCR_ZOOM, OCR_ZOOM)
        parts: List[str] = []
        page_count = min(len(doc), OCR_MAX_PAGES)
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(page_count):
                pix = doc.load_page(i).get_pixmap(matrix=mat, alpha=False)
                png_path = os.path.join(tmpdir, f"page_{i + 1}.png")
                pix.save(png_path)
                proc = subprocess.run(
                    ["tesseract", png_path, "stdout", "-l", TESSERACT_LANG],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    err = (proc.stderr or proc.stdout or "").strip()
                    raise RuntimeError(err or f"tesseract failed on page {i + 1}")
                parts.append(proc.stdout or "")
        return "\n".join(parts).strip()
    finally:
        doc.close()


def _parse_ocr_fields(ocr_text: str, *, file_name: str) -> Tuple[str, str]:
    draft = _extract_draft_fields_from_text(ocr_text or "", file_name=file_name)
    ocr_name = str(draft.get("name") or "").strip()
    ocr_phone = _normalize_import_phone(draft.get("phone")) or ""
    return ocr_name, ocr_phone


def _create_candidate_from_ocr_retry(
    db: Session,
    *,
    RmsCandidate: Type[Any],
    RmsResume: Type[Any],
    resume_file_path: Path,
    ocr_text: str,
    final_name: str,
    final_phone: str,
    content: bytes,
    uploaded_by_user_id: int,
    upload_dir: str,
    source: str,
) -> Tuple[int, int]:
    draft = _extract_draft_fields_from_text(ocr_text or "", file_name=resume_file_path.name)
    draft["name"] = final_name
    draft["phone"] = final_phone
    fields = _candidate_fields_from_parsed(draft, source=source)
    return _commit_single_file(
        db,
        fields=fields,
        file_path=resume_file_path,
        content=content,
        parsed_text=ocr_text,
        parsed_json=json.dumps(draft, ensure_ascii=False),
        uploaded_by_user_id=uploaded_by_user_id,
        upload_dir=upload_dir,
        RmsCandidate=RmsCandidate,
        RmsResume=RmsResume,
    )


def retry_ocr_from_report(
    db: Session,
    *,
    report_csv: str | Path,
    dry_run: bool,
    commit: bool,
    limit: int | None = None,
    report_dir: str | Path,
    models: Dict[str, Type[Any]],
    uploaded_by_user_id: int | None = None,
    upload_dir: str | None = None,
    source: str = "批量导入",
) -> Dict[str, Any]:
    if dry_run == commit:
        raise ValueError("exactly one of dry_run or commit must be True")

    report_path = Path(report_csv)
    RmsCandidate = models["RmsCandidate"]
    RmsResume = models["RmsResume"]
    rows_out: List[Dict[str, Any]] = []
    batch_seen: set[tuple[str, str]] = set()
    counts: Dict[str, int] = {
        "scanned": 0,
        "ocr_attempted": 0,
        "would_update": 0,
        "updated": 0,
        "would_create": 0,
        "created": 0,
        "conflict": 0,
        "skipped_not_needed": 0,
        "skipped_missing_file_path": 0,
        "skipped_file_missing": 0,
        "skipped_non_pdf": 0,
        "skipped_ocr_empty": 0,
        "skipped_duplicate": 0,
        "skipped_unparseable": 0,
        "failed": 0,
    }

    source_rows = load_import_report_rows(report_path)
    ocr_budget = limit

    for source_row in source_rows:
        counts["scanned"] += 1
        raw_path = _raw_path_from_row(source_row)
        cand_id = _parse_candidate_id(source_row.get("candidate_id"))
        original_name, original_phone = _original_fields_for_row(
            source_row, db=db, RmsCandidate=RmsCandidate
        )

        base = dict(
            resume_file_path=raw_path,
            candidate_id=cand_id or "",
            original_name=original_name,
            original_phone=original_phone,
        )

        if not raw_path:
            counts["skipped_missing_file_path"] += 1
            rows_out.append(
                _report_row(**base, status="skipped_missing_file_path")
            )
            continue

        if not _row_needs_ocr(source_row, db=db, RmsCandidate=RmsCandidate):
            counts["skipped_not_needed"] += 1
            rows_out.append(
                _report_row(
                    **base,
                    final_name=original_name,
                    final_phone=original_phone,
                    status="skipped_not_needed",
                )
            )
            continue

        resolved = resolve_resume_file_path(raw_path, report_path)
        if resolved is None:
            counts["skipped_file_missing"] += 1
            rows_out.append(
                _report_row(**base, status="skipped_file_missing")
            )
            continue

        if resolved.suffix.lower() != ".pdf":
            counts["skipped_non_pdf"] += 1
            rows_out.append(
                _report_row(**base, status="skipped_non_pdf")
            )
            continue

        if ocr_budget is not None and ocr_budget <= 0:
            rows_out.append(
                _report_row(**base, status="skipped_not_needed", error="ocr_limit_reached")
            )
            continue

        counts["ocr_attempted"] += 1
        if ocr_budget is not None:
            ocr_budget -= 1

        try:
            ocr_text = extract_text_with_tesseract(resolved)
        except RuntimeError as exc:
            msg = str(exc)
            counts["failed"] += 1
            rows_out.append(
                _report_row(**base, status="failed", error=msg[:500])
            )
            continue
        except Exception as exc:
            counts["failed"] += 1
            rows_out.append(
                _report_row(**base, status="failed", error=str(exc)[:500])
            )
            continue

        if not (ocr_text or "").strip():
            counts["skipped_ocr_empty"] += 1
            rows_out.append(
                _report_row(**base, status="skipped_ocr_empty")
            )
            continue

        ocr_name, ocr_phone = _parse_ocr_fields(
            ocr_text, file_name=resolved.name
        )
        final_name, final_phone, conflict_reason, patch = _merge_ocr_fields(
            original_name, original_phone, ocr_name, ocr_phone
        )

        row_data = dict(
            **base,
            ocr_name=ocr_name,
            ocr_phone=ocr_phone,
            final_name=final_name,
            final_phone=final_phone,
            conflict_reason=conflict_reason,
        )

        if conflict_reason:
            counts["conflict"] += 1
            rows_out.append(_report_row(**row_data, status="conflict"))
            continue

        if cand_id is None:
            final_name = (final_name or "").strip()
            final_phone = _normalize_import_phone(final_phone) or ""
            row_data["final_name"] = final_name
            row_data["final_phone"] = final_phone

            if not final_name or not final_phone:
                counts["skipped_unparseable"] += 1
                rows_out.append(
                    _report_row(
                        **row_data,
                        status="skipped_unparseable",
                        error="missing_name_or_phone",
                    )
                )
                continue

            name_reject_reason = reject_candidate_name_reason(
                final_name, strict_length=True
            )
            if name_reject_reason:
                counts["skipped_unparseable"] += 1
                rows_out.append(
                    _report_row(
                        **row_data,
                        status="skipped_unparseable",
                        error="invalid_candidate_name",
                    )
                )
                continue

            if _is_batch_duplicate(
                db,
                RmsCandidate,
                name=final_name,
                phone=final_phone,
                batch_seen=batch_seen,
            ):
                counts["skipped_duplicate"] += 1
                rows_out.append(
                    _report_row(
                        **row_data,
                        status="skipped_duplicate",
                        error="name_phone_match",
                    )
                )
                continue

            if dry_run:
                batch_seen.add((final_name, final_phone))
                counts["would_create"] += 1
                rows_out.append(_report_row(**row_data, status="would_create"))
                continue

            if uploaded_by_user_id is None or upload_dir is None:
                raise ValueError(
                    "uploaded_by_user_id and upload_dir required for commit create"
                )

            if resolved.stat().st_size > MAX_RESUME_BYTES:
                counts["failed"] += 1
                rows_out.append(
                    _report_row(**row_data, status="failed", error="file_too_large")
                )
                continue

            try:
                content = resolved.read_bytes()
                if len(content) > MAX_RESUME_BYTES:
                    counts["failed"] += 1
                    rows_out.append(
                        _report_row(**row_data, status="failed", error="file_too_large")
                    )
                    continue
                new_cand_id, new_resume_id = _create_candidate_from_ocr_retry(
                    db,
                    RmsCandidate=RmsCandidate,
                    RmsResume=RmsResume,
                    resume_file_path=resolved,
                    ocr_text=ocr_text,
                    final_name=final_name,
                    final_phone=final_phone,
                    content=content,
                    uploaded_by_user_id=uploaded_by_user_id,
                    upload_dir=upload_dir,
                    source=source,
                )
            except Exception as exc:
                counts["failed"] += 1
                rows_out.append(
                    _report_row(**row_data, status="failed", error=str(exc)[:500])
                )
                continue

            batch_seen.add((final_name, final_phone))
            counts["created"] += 1
            rows_out.append(
                _report_row(
                    **{
                        **row_data,
                        "candidate_id": new_cand_id,
                        "resume_id": new_resume_id,
                        "status": "created",
                    }
                )
            )
            continue

        if not patch:
            counts["skipped_not_needed"] += 1
            rows_out.append(
                _report_row(**row_data, status="skipped_not_needed")
            )
            continue

        candidate = db.query(RmsCandidate).filter(RmsCandidate.id == cand_id).first()
        if candidate is None:
            counts["failed"] += 1
            rows_out.append(
                _report_row(
                    **row_data,
                    status="failed",
                    error="candidate_not_found",
                )
            )
            continue

        if dry_run:
            counts["would_update"] += 1
            rows_out.append(_report_row(**row_data, status="would_update"))
            continue

        for key, val in patch.items():
            setattr(candidate, key, val)
        candidate.updated_at = utc_date_str()
        db.commit()
        db.refresh(candidate)
        counts["updated"] += 1
        rows_out.append(_report_row(**row_data, status="updated"))

    csv_out, json_out = _write_reports(report_dir, rows_out, counts)
    return {
        **counts,
        "report_csv": str(csv_out),
        "report_json": str(json_out),
    }
