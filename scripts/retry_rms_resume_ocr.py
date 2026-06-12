#!/usr/bin/env python3

"""OCR retry for RMS import report rows missing name and/or phone."""

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

    print(f"OCR 尝试: {result.get('ocr_attempted', 0)}")

    print(f"would_update: {result.get('would_update', 0)}")

    print(f"updated: {result.get('updated', 0)}")

    print(f"would_create: {result.get('would_create', 0)}")

    print(f"created: {result.get('created', 0)}")

    print(f"conflict: {result.get('conflict', 0)}")

    print(f"跳过(无需 OCR): {result.get('skipped_not_needed', 0)}")

    print(f"跳过(重复): {result.get('skipped_duplicate', 0)}")

    print(f"跳过(不可解析): {result.get('skipped_unparseable', 0)}")

    print(f"跳过(缺路径): {result.get('skipped_missing_file_path', 0)}")

    print(f"跳过(文件不存在): {result.get('skipped_file_missing', 0)}")

    print(f"跳过(非 PDF): {result.get('skipped_non_pdf', 0)}")

    print(f"跳过(OCR 空): {result.get('skipped_ocr_empty', 0)}")

    print(f"失败: {result.get('failed', 0)}")

    print(f"报告 CSV: {result.get('report_csv', '')}")

    print(f"报告 JSON: {result.get('report_json', '')}")





def main() -> int:

    parser = argparse.ArgumentParser(

        description="OCR retry for RMS import rows missing name or phone",

    )

    parser.add_argument(

        "--report-csv",

        required=True,

        help="Path to bulk import or corrections report CSV",

    )

    mode = parser.add_mutually_exclusive_group(required=True)

    mode.add_argument("--dry-run", action="store_true", help="Preview only; no DB writes")

    mode.add_argument("--commit", action="store_true", help="Update or create candidates")

    parser.add_argument("--limit", type=int, default=None, help="Max OCR attempts")

    parser.add_argument(

        "--report-dir",

        default=str(ROOT / "reports" / "rms_imports"),

        help="Retry report output directory",

    )

    parser.add_argument(

        "--uploaded-by-user-id",

        type=int,

        default=None,

        help="Uploader/creator user id (default: admin)",

    )

    args = parser.parse_args()



    report_csv = Path(args.report_csv)

    if not report_csv.is_file():

        print(f"report csv not found: {report_csv}", file=sys.stderr)

        return 1



    import main as crm_main

    from services.rms_resume_ocr_retry import retry_ocr_from_report



    db = crm_main.SessionLocal()

    try:

        uploaded_by = _resolve_uploaded_by_user_id(db, args.uploaded_by_user_id)

        result = retry_ocr_from_report(

            db,

            report_csv=report_csv,

            dry_run=args.dry_run,

            commit=args.commit,

            limit=args.limit,

            report_dir=args.report_dir,

            models=crm_main.RMS_MODELS,

            uploaded_by_user_id=uploaded_by,

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


