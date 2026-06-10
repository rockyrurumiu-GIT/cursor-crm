#!/usr/bin/env python3
"""Bulk import resumes from a folder into RMS talent pool (candidates + resumes only)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

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


def _print_summary(result: dict) -> None:
    print(f"扫描文件数: {result.get('scanned', 0)}")
    print(f"支持文件数: {result.get('supported', 0)}")
    print(f"would_create: {result.get('would_create', 0)}")
    print(f"created: {result.get('created', 0)}")
    print(f"重复跳过: {result.get('skipped_duplicate', 0)}")
    print(f"解析失败跳过: {result.get('skipped_unparseable', 0)}")
    print(f"不支持格式: {result.get('skipped_unsupported', 0)}")
    print(f"失败: {result.get('failed', 0)}")
    print(f"报告 CSV: {result.get('report_csv', '')}")
    print(f"报告 JSON: {result.get('report_json', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import resumes from a folder into RMS talent pool",
    )
    parser.add_argument("--source-dir", required=True, help="Folder containing resume files")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview only; no DB or file writes")
    mode.add_argument("--commit", action="store_true", help="Write candidates, resumes, and files")
    parser.add_argument("--recursive", action="store_true", help="Scan subdirectories")
    parser.add_argument("--source", default="批量导入", help="Candidate source label")
    parser.add_argument("--limit", type=int, default=None, help="Max files to process")
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
    from services.rms_resume_import import import_resume_batch

    db = crm_main.SessionLocal()
    try:
        uploaded_by = _resolve_uploaded_by_user_id(db, args.uploaded_by_user_id)
        result = import_resume_batch(
            db,
            source_dir=source_dir,
            dry_run=args.dry_run,
            commit=args.commit,
            recursive=args.recursive,
            source=args.source,
            uploaded_by_user_id=uploaded_by,
            models=crm_main.RMS_MODELS,
            report_dir=args.report_dir,
            upload_dir=crm_main.UPLOAD_DIR,
            limit=args.limit,
        )
    finally:
        db.close()

    _print_summary(result)
    if result.get("failed", 0) > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
