#!/usr/bin/env python3
"""Bulk import resumes, then OCR retry rows missing name/phone."""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _resolve_uploaded_by_user_id(db, user_id: int | None) -> int:
    if user_id is not None:
        row = db.execute(
            text("SELECT id FROM sys_user WHERE id = :id LIMIT 1"),
            {"id": user_id},
        ).fetchone()
        if not row:
            raise SystemExit(f"sys_user id not found: {user_id}")
        return int(row[0])
    row = db.execute(
        text("SELECT id FROM sys_user WHERE LOWER(username) = 'admin' LIMIT 1"),
    ).fetchone()
    if not row:
        raise SystemExit("admin user not found; pass --uploaded-by-user-id")
    return int(row[0])


def _write_combined_json(
    report_dir: Path,
    import_result: Dict[str, Any],
    ocr_result: Dict[str, Any],
) -> Optional[Path]:
    try:
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = report_dir / f"rms_resume_import_with_ocr_retry_{stamp}.json"
        payload = {"import": import_result, "ocr_retry": ocr_result}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception as exc:
        print(f"warning: failed to write combined JSON: {exc}", file=sys.stderr)
        return None


def _print_combined_summary(
    import_result: Dict[str, Any],
    ocr_result: Dict[str, Any],
    combined_json: Optional[Path],
) -> None:
    print(f"Import report: {import_result.get('report_csv', '')}")
    print(f"OCR retry report: {ocr_result.get('report_csv', '')}")
    if combined_json:
        print(f"Combined JSON: {combined_json}")
    print()
    print("Import:")
    print(f"  scanned: {import_result.get('scanned', 0)}")
    print(f"  would_create: {import_result.get('would_create', 0)}")
    print(f"  created: {import_result.get('created', 0)}")
    print(f"  skipped_duplicate: {import_result.get('skipped_duplicate', 0)}")
    print(f"  skipped_unparseable: {import_result.get('skipped_unparseable', 0)}")
    print(f"  failed: {import_result.get('failed', 0)}")
    print()
    print("OCR retry:")
    print(f"  scanned: {ocr_result.get('scanned', 0)}")
    print(f"  ocr_attempted: {ocr_result.get('ocr_attempted', 0)}")
    print(f"  would_update: {ocr_result.get('would_update', 0)}")
    print(f"  updated: {ocr_result.get('updated', 0)}")
    print(f"  would_create: {ocr_result.get('would_create', 0)}")
    print(f"  created: {ocr_result.get('created', 0)}")
    print(f"  skipped_duplicate: {ocr_result.get('skipped_duplicate', 0)}")
    print(f"  skipped_unparseable: {ocr_result.get('skipped_unparseable', 0)}")
    print(f"  conflict: {ocr_result.get('conflict', 0)}")
    print(f"  failed: {ocr_result.get('failed', 0)}")


def run_import_with_ocr_retry(
    db,
    *,
    source_dir: Path,
    dry_run: bool,
    commit: bool,
    recursive: bool,
    source: str,
    limit: int | None,
    ocr_limit: int | None,
    report_dir: Path,
    uploaded_by_user_id: int,
    upload_dir: str,
    models: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[Path]]:
    from services.rms_resume_import import import_resume_batch
    from services.rms_resume_ocr_retry import retry_ocr_from_report

    import_result = import_resume_batch(
        db,
        source_dir=source_dir,
        dry_run=dry_run,
        commit=commit,
        recursive=recursive,
        source=source,
        uploaded_by_user_id=uploaded_by_user_id,
        models=models,
        report_dir=report_dir,
        upload_dir=upload_dir,
        limit=limit,
    )

    report_csv = (import_result.get("report_csv") or "").strip()
    if not report_csv:
        print("import completed but report_csv is missing", file=sys.stderr)
        raise SystemExit(2)

    ocr_result = retry_ocr_from_report(
        db,
        report_csv=report_csv,
        dry_run=dry_run,
        commit=commit,
        limit=ocr_limit,
        report_dir=report_dir,
        models=models,
        uploaded_by_user_id=uploaded_by_user_id,
        upload_dir=upload_dir,
        source=source,
    )

    combined_json = _write_combined_json(report_dir, import_result, ocr_result)
    return import_result, ocr_result, combined_json


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk import resumes, then OCR retry missing name/phone rows",
    )
    parser.add_argument("--source-dir", required=True, help="Folder containing resume files")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview only; no DB writes")
    mode.add_argument("--commit", action="store_true", help="Import and OCR retry commit")
    parser.add_argument("--recursive", action="store_true", help="Scan subdirectories")
    parser.add_argument("--source", default="批量导入", help="Candidate source label")
    parser.add_argument("--limit", type=int, default=None, help="Max files for import")
    parser.add_argument("--ocr-limit", type=int, default=None, help="Max OCR attempts")
    parser.add_argument(
        "--report-dir",
        default=str(ROOT / "reports" / "rms_imports"),
        help="Report output directory",
    )
    parser.add_argument(
        "--uploaded-by-user-id",
        type=int,
        default=None,
        help="Uploader/creator user id (default: admin)",
    )
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if not source_dir.is_dir():
        print(f"source-dir not found: {source_dir}", file=sys.stderr)
        return 1

    import main as crm_main

    db = crm_main.SessionLocal()
    try:
        uploaded_by = _resolve_uploaded_by_user_id(db, args.uploaded_by_user_id)
        import_result, ocr_result, combined_json = run_import_with_ocr_retry(
            db,
            source_dir=source_dir,
            dry_run=args.dry_run,
            commit=args.commit,
            recursive=args.recursive,
            source=args.source,
            limit=args.limit,
            ocr_limit=args.ocr_limit,
            report_dir=Path(args.report_dir),
            uploaded_by_user_id=uploaded_by,
            upload_dir=crm_main.UPLOAD_DIR,
            models=crm_main.RMS_MODELS,
        )
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        return 2
    finally:
        db.close()

    _print_combined_summary(import_result, ocr_result, combined_json)
    if import_result.get("failed", 0) > 0 or ocr_result.get("failed", 0) > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
