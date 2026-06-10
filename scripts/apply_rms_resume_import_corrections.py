#!/usr/bin/env python3
"""Apply RMS bulk resume import corrections from a CSV file."""
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
    print(f"扫描行数: {result.get('scanned', 0)}")
    print(f"would_create: {result.get('would_create', 0)}")
    print(f"created: {result.get('created', 0)}")
    print(f"would_update: {result.get('would_update', 0)}")
    print(f"updated: {result.get('updated', 0)}")
    print(f"跳过: {result.get('skipped', 0)}")
    print(f"重复跳过: {result.get('skipped_duplicate', 0)}")
    print(f"失败: {result.get('failed', 0)}")
    print(f"报告 CSV: {result.get('report_csv', '')}")
    print(f"报告 JSON: {result.get('report_json', '')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply RMS resume import corrections from CSV",
    )
    parser.add_argument("--csv", required=True, help="Path to corrections CSV")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview only; no DB writes")
    mode.add_argument("--commit", action="store_true", help="Apply corrections")
    parser.add_argument(
        "--report-dir",
        default=str(ROOT / "reports" / "rms_imports"),
        help="Report output directory",
    )
    parser.add_argument(
        "--uploaded-by-user-id",
        type=int,
        default=None,
        help="Uploader/creator user id for create rows (default: admin)",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"csv not found: {csv_path}", file=sys.stderr)
        return 1

    import main as crm_main
    from services.rms_resume_import_corrections import apply_resume_import_corrections

    db = crm_main.SessionLocal()
    try:
        uploaded_by = _resolve_uploaded_by_user_id(db, args.uploaded_by_user_id)
        result = apply_resume_import_corrections(
            db,
            csv_path=csv_path,
            dry_run=args.dry_run,
            commit=args.commit,
            uploaded_by_user_id=uploaded_by,
            models=crm_main.RMS_MODELS,
            report_dir=args.report_dir,
            upload_dir=crm_main.UPLOAD_DIR,
        )
    finally:
        db.close()

    _print_summary(result)
    if result.get("failed", 0) > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
