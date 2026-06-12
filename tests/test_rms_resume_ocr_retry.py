"""RMS Phase 3D-1E: OCR retry for import rows missing name/phone."""
from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

from services.rms_resume_import import REPORT_CSV_FIELDS as IMPORT_REPORT_FIELDS
from services.rms_resume_ocr_retry import (
    TESSERACT_MISSING_MSG,
    resolve_resume_file_path,
    retry_ocr_from_report,
)
from tests.test_rms_application_workflow import _make_text_pdf
from tests.test_rms_resume_import import (
    _admin_user_id,
    _count_table,
    _import_phone,
    _minimal_resume,
    _reload_rms_main,
    _run_import,
    _write_resume_txt,
)

OCR_TEXT_LIXIANGLONG = "姓名：李向龙\n电话：18392024583\n"
OCR_TEXT_PHONE_ONLY = "电话：18392024583\n"
OCR_TEXT_NAME_ONLY = "姓名：李向龙\n"


@pytest.fixture
def import_engine(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    return _reload_rms_main().engine


def _write_import_report_csv(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(IMPORT_REPORT_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in IMPORT_REPORT_FIELDS})
    return path


def _write_pdf(path: Path, content: str = OCR_TEXT_LIXIANGLONG) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_make_text_pdf(content))
    return path


def _run_ocr_retry(
    engine,
    report_csv: Path,
    *,
    dry_run: bool = False,
    commit: bool = False,
    report_dir: Path,
    limit: int | None = None,
    upload_dir: Path | None = None,
    uploaded_by_user_id: int | None = None,
    source: str = "批量导入",
):
    import main as crm_main

    db = crm_main.SessionLocal()
    try:
        kwargs = {
            "db": db,
            "report_csv": report_csv,
            "dry_run": dry_run,
            "commit": commit,
            "limit": limit,
            "report_dir": report_dir,
            "models": crm_main.RMS_MODELS,
            "source": source,
        }
        if upload_dir is not None:
            kwargs["upload_dir"] = str(upload_dir)
        if uploaded_by_user_id is not None:
            kwargs["uploaded_by_user_id"] = uploaded_by_user_id
        return retry_ocr_from_report(**kwargs)
    finally:
        db.close()


def _import_candidate(import_engine, tmp_path, *, name: str, phone: str) -> int:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    _write_resume_txt(src, "seed.txt", _minimal_resume(name, phone))
    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["created"] == 1, result
    return int(result["rows"][0]["candidate_id"])


def test_resolve_relative_path_against_report_dir(tmp_path):
    report_csv = tmp_path / "reports" / "import.csv"
    pdf = _write_pdf(tmp_path / "reports" / "resumes" / "a.pdf")
    report_csv.write_text("file_path\nresumes/a.pdf\n", encoding="utf-8")
    resolved = resolve_resume_file_path("resumes/a.pdf", report_csv)
    assert resolved == pdf


def test_resolve_relative_path_falls_back_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pdf = _write_pdf(tmp_path / "resumes" / "b.pdf")
    report_csv = tmp_path / "reports" / "import.csv"
    report_csv.parent.mkdir(parents=True, exist_ok=True)
    report_csv.write_text("file_path\nresumes/b.pdf\n", encoding="utf-8")
    resolved = resolve_resume_file_path("resumes/b.pdf", report_csv)
    assert resolved == pdf


def test_only_missing_field_rows_invoke_ocr(import_engine, tmp_path):
    phone = _import_phone()
    pdf_dir = tmp_path / "pdfs"
    pdf_a = _write_pdf(pdf_dir / "a.pdf")
    pdf_b = _write_pdf(pdf_dir / "b.pdf")
    pdf_c = _write_pdf(pdf_dir / "c.pdf")
    pdf_d = _write_pdf(pdf_dir / "d.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf_a),
                "name": "张三",
                "phone_masked": "138****0000",
            },
            {
                "file_path": str(pdf_b),
                "name": "李四",
                "phone_masked": "",
            },
            {
                "file_path": str(pdf_c),
                "name": "",
                "phone_masked": "139****0001",
            },
            {
                "file_path": str(pdf_d),
                "name": "",
                "phone_masked": "",
            },
        ],
    )
    ocr_calls: list[str] = []

    def _fake_ocr(path):
        ocr_calls.append(str(path))
        return OCR_TEXT_LIXIANGLONG

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        side_effect=_fake_ocr,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            dry_run=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["ocr_attempted"] == 3
    assert result["skipped_not_needed"] == 1
    assert {Path(p).name for p in ocr_calls} == {"b.pdf", "c.pdf", "d.pdf"}


def test_dry_run_does_not_write_db(import_engine, tmp_path):
    phone = _import_phone()
    pdf = _write_pdf(tmp_path / "retry.pdf")
    cand_id = _import_candidate(import_engine, tmp_path, name="王五", phone=phone)
    with import_engine.connect() as conn:
        conn.execute(
            text("UPDATE rms_candidates SET phone = '' WHERE id = :id"),
            {"id": cand_id},
        )
        conn.commit()

    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "candidate_id": str(cand_id),
                "name": "王五",
                "phone_masked": "",
            }
        ],
    )
    before = _count_table(import_engine, "rms_candidates")

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_PHONE_ONLY,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            dry_run=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["would_update"] == 1
    assert result["updated"] == 0
    assert _count_table(import_engine, "rms_candidates") == before
    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT phone FROM rms_candidates WHERE id = :id"),
            {"id": cand_id},
        ).fetchone()
    assert row[0] == ""


def test_conflict_does_not_overwrite_existing_phone(import_engine, tmp_path):
    existing_phone = _import_phone()
    pdf = _write_pdf(tmp_path / "retry.pdf")
    cand_id = _import_candidate(import_engine, tmp_path, name="赵六", phone=existing_phone)
    with import_engine.connect() as conn:
        conn.execute(
            text("UPDATE rms_candidates SET name = '' WHERE id = :id"),
            {"id": cand_id},
        )
        conn.commit()

    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "candidate_id": str(cand_id),
                "name": "",
                "phone_masked": "138****0000",
            }
        ],
    )

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_LIXIANGLONG,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            commit=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["conflict"] == 1
    assert result["updated"] == 0
    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT phone, name FROM rms_candidates WHERE id = :id"),
            {"id": cand_id},
        ).fetchone()
    assert row[0] == existing_phone
    assert row[1] == ""


def test_commit_fills_empty_phone(import_engine, tmp_path):
    phone = _import_phone()
    pdf = _write_pdf(tmp_path / "retry.pdf")
    cand_id = _import_candidate(import_engine, tmp_path, name="孙七", phone=phone)
    with import_engine.connect() as conn:
        conn.execute(
            text("UPDATE rms_candidates SET phone = '' WHERE id = :id"),
            {"id": cand_id},
        )
        conn.commit()

    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "candidate_id": str(cand_id),
                "name": "孙七",
                "phone_masked": "",
            }
        ],
    )

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_PHONE_ONLY,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            commit=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["updated"] == 1
    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT phone FROM rms_candidates WHERE id = :id"),
            {"id": cand_id},
        ).fetchone()
    assert row[0] == "18392024583"


def test_tesseract_missing_returns_friendly_error(import_engine, tmp_path):
    pdf = _write_pdf(tmp_path / "retry.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "name": "",
                "phone_masked": "",
            }
        ],
    )

    with patch("services.rms_resume_ocr_retry.shutil.which", return_value=None):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            dry_run=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["failed"] == 1
    row = next(r for r in csv.DictReader(open(result["report_csv"], encoding="utf-8")))
    assert "Tesseract not found" in row["error"]
    assert TESSERACT_MISSING_MSG.split(".")[0] in row["error"]


def test_phone_masked_non_empty_skips_ocr(import_engine, tmp_path):
    pdf = _write_pdf(tmp_path / "retry.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "name": "周八",
                "phone_masked": "183****4583",
            }
        ],
    )
    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
    ) as mock_ocr:
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            dry_run=True,
            report_dir=tmp_path / "retry_reports",
        )
    mock_ocr.assert_not_called()
    assert result["skipped_not_needed"] == 1


def test_no_candidate_id_ocr_dry_run_would_create(import_engine, tmp_path):
    pdf = _write_pdf(tmp_path / "retry.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "name": "",
                "phone_masked": "",
            }
        ],
    )
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_LIXIANGLONG,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            dry_run=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["would_create"] == 1
    assert result["created"] == 0
    assert _count_table(import_engine, "rms_candidates") == before_c
    assert _count_table(import_engine, "rms_resumes") == before_r


def test_no_candidate_id_ocr_commit_created(import_engine, tmp_path):
    pdf = _write_pdf(tmp_path / "retry.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "name": "",
                "phone_masked": "",
            }
        ],
    )
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")
    admin_id = _admin_user_id(import_engine)

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_LIXIANGLONG,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            commit=True,
            report_dir=tmp_path / "retry_reports",
            upload_dir=tmp_path / "uploads",
            uploaded_by_user_id=admin_id,
        )

    assert result["created"] == 1
    assert _count_table(import_engine, "rms_candidates") == before_c + 1
    assert _count_table(import_engine, "rms_resumes") == before_r + 1

    row = next(r for r in csv.DictReader(open(result["report_csv"], encoding="utf-8")))
    assert row["status"] == "created"
    assert row["candidate_id"]
    assert row["resume_id"]


def test_no_candidate_id_ocr_still_missing_phone(import_engine, tmp_path):
    pdf = _write_pdf(tmp_path / "retry.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import.csv",
        [
            {
                "file_path": str(pdf),
                "name": "",
                "phone_masked": "",
            }
        ],
    )

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_NAME_ONLY,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            dry_run=True,
            report_dir=tmp_path / "retry_reports",
        )

    assert result["skipped_unparseable"] == 1
    row = next(r for r in csv.DictReader(open(result["report_csv"], encoding="utf-8")))
    assert row["error"] == "missing_name_or_phone"


def test_no_candidate_id_duplicate_skipped(import_engine, tmp_path):
    name, phone = "李向龙", "18392024583"
    with import_engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM rms_candidates WHERE name = :n AND phone = :p"),
            {"n": name, "p": phone},
        ).fetchone()
    if existing is None:
        _import_candidate(import_engine, tmp_path, name=name, phone=phone)
    pdf = _write_pdf(tmp_path / "retry_dup.pdf")
    report_csv = _write_import_report_csv(
        tmp_path / "reports" / "import_dup.csv",
        [
            {
                "file_path": str(pdf),
                "name": "",
                "phone_masked": "",
            }
        ],
    )
    before_c = _count_table(import_engine, "rms_candidates")

    with patch(
        "services.rms_resume_ocr_retry.extract_text_with_tesseract",
        return_value=OCR_TEXT_LIXIANGLONG,
    ):
        result = _run_ocr_retry(
            import_engine,
            report_csv,
            commit=True,
            report_dir=tmp_path / "retry_reports",
            upload_dir=tmp_path / "uploads_dup",
            uploaded_by_user_id=_admin_user_id(import_engine),
        )

    assert result["skipped_duplicate"] == 1
    assert _count_table(import_engine, "rms_candidates") == before_c
    row = next(r for r in csv.DictReader(open(result["report_csv"], encoding="utf-8")))
    assert row["status"] == "skipped_duplicate"
    assert row["error"] == "name_phone_match"
