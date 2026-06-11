"""RMS Phase 3D-1: bulk resume import into talent pool."""
from __future__ import annotations

import csv
import importlib
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from services import rms_resume_import as import_svc
from services.rms_applications import reject_candidate_name_reason

from tests.helpers import auth_header
from tests.test_rms_application_workflow import (
    _resume_with_contact_and_education,
    _resume_with_split_name_labels,
)
from tests.test_rms_phase2_mvp import (
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
)

RAW_PHONE = "15988192434"
RAW_EMAIL = "15988192434@163.com"
IMPORT_NAME = "测试候选人"
DUP_IMPORT_NAME = "重复张三"


def _import_phone() -> str:
    """Mobile digits must match parser rule 1[3-9]\\d{9} (not 11x/12x from _unique_phone)."""
    second = 3 + uuid.uuid4().int % 7
    rest = uuid.uuid4().int % 10**9
    return f"1{second}{rest:09d}"


def _unique_name() -> str:
    return "张三"


def _minimal_resume(name: str, phone: str) -> str:
    return f"姓名：{name}\n手机 {phone}\n"


def _resume_content(*, name: str | None = None, phone: str | None = None) -> str:
    text = _resume_with_contact_and_education()
    resolved_name = name if name is not None else _unique_name()
    text = text.replace(IMPORT_NAME, resolved_name)
    resolved_phone = phone if phone is not None else _import_phone()
    text = text.replace(RAW_PHONE, resolved_phone)
    if RAW_EMAIL in text:
        text = text.replace(RAW_EMAIL, f"{resolved_phone}@163.com")
    return text


def _reload_rms_main():
    import main as crm_main

    importlib.reload(crm_main)
    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)
    return crm_main


@pytest.fixture
def import_engine(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    return _reload_rms_main().engine


@pytest.fixture
def rms_client(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    crm_main = _reload_rms_main()
    with TestClient(crm_main.app) as client:
        yield client, crm_main.engine


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


def _admin_user_id(engine) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM sys_user WHERE LOWER(username) = 'admin' LIMIT 1")
        ).fetchone()
    assert row is not None
    return int(row[0])


def _count_table(engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)


def _write_resume_txt(directory: Path, filename: str, content: str) -> Path:
    path = directory / filename
    path.write_text(content, encoding="utf-8")
    return path


def _run_import(
    engine,
    source_dir: Path,
    *,
    dry_run: bool = False,
    commit: bool = False,
    upload_dir: Path,
    report_dir: Path,
    limit: int | None = None,
    source: str = "批量导入",
):
    import main as crm_main

    db = crm_main.SessionLocal()
    try:
        return import_svc.import_resume_batch(
            db,
            source_dir=source_dir,
            dry_run=dry_run,
            commit=commit,
            uploaded_by_user_id=_admin_user_id(engine),
            models=crm_main.RMS_MODELS,
            report_dir=report_dir,
            upload_dir=str(upload_dir),
            limit=limit,
            source=source,
        )
    finally:
        db.close()


def test_dry_run_writes_no_db_rows(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "a.txt", _resume_content(phone=_import_phone()))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")

    result = _run_import(
        import_engine,
        src,
        dry_run=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert _count_table(import_engine, "rms_candidates") == before_c
    assert _count_table(import_engine, "rms_resumes") == before_r
    assert result["would_create"] == 1
    assert result["rows"][0]["status"] == "would_create"
    assert not list(upload_dir.glob("**/*"))


def test_dry_run_split_name_labels_unknown_txt(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "unknown.txt", _resume_with_split_name_labels())
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        dry_run=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["would_create"] == 1, result
    assert result["rows"][0]["name"] == "马兵文"


def test_commit_creates_candidate_and_resume(import_engine, tmp_path):
    phone = _import_phone()
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "resume.txt", _resume_content(phone=phone))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["created"] == 1, result
    assert _count_table(import_engine, "rms_candidates") == before_c + 1
    assert _count_table(import_engine, "rms_resumes") == before_r + 1
    assert list(upload_dir.rglob("rms/resumes/*"))
    resume_id = result["rows"][0]["resume_id"]
    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT parsed_text, parsed_json FROM rms_resumes WHERE id = :id"),
            {"id": resume_id},
        ).fetchone()
    assert row is not None
    assert row[0]
    parsed = json.loads(row[1])
    assert parsed.get("phone") == phone


_INVALID_NAME_CASES = [
    ("个人简历", "blocklist"),
    ("电话", "blocklist"),
    ("许昌学院", "institution_suffix"),
    ("相机效果测试", "length"),
    ("个人资料", "blocklist"),
    ("西安", "place_name"),
    ("[张帅]", "invalid_format"),
]

# Parser rejects these before import gate (no name in draft_fields).
_IMPORT_MISSING_NAME_CASES = [
    case for case in _INVALID_NAME_CASES if case[0] != "相机效果测试"
]
_IMPORT_INVALID_NAME_CASES = [
    case for case in _INVALID_NAME_CASES if case[0] == "相机效果测试"
]


@pytest.mark.parametrize("name,expected_reason", _INVALID_NAME_CASES)
def test_reject_candidate_name_reason_codes(name, expected_reason):
    assert reject_candidate_name_reason(name, strict_length=True) == expected_reason


@pytest.mark.parametrize("bad_name,expected_reason", _IMPORT_INVALID_NAME_CASES)
def test_import_rejects_invalid_candidate_name_commit(
    import_engine, tmp_path, bad_name, expected_reason
):
    phone = _import_phone()
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "resume.txt", _minimal_resume(bad_name, phone))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["created"] == 0, result
    assert result["skipped_unparseable"] == 1
    assert _count_table(import_engine, "rms_candidates") == before_c
    assert _count_table(import_engine, "rms_resumes") == before_r
    row = result["rows"][0]
    assert row["status"] == "skipped_unparseable"
    assert row["error"] == "invalid_candidate_name"
    assert row["name_reject_reason"] == expected_reason


@pytest.mark.parametrize("bad_name,expected_reason", _IMPORT_MISSING_NAME_CASES)
def test_import_skips_parser_rejected_candidate_name_commit(
    import_engine, tmp_path, bad_name, expected_reason
):
    phone = _import_phone()
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "resume.txt", _minimal_resume(bad_name, phone))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["created"] == 0, result
    assert result["skipped_unparseable"] == 1
    assert _count_table(import_engine, "rms_candidates") == before_c
    assert _count_table(import_engine, "rms_resumes") == before_r
    row = result["rows"][0]
    assert row["status"] == "skipped_unparseable"
    assert row["error"] == "missing_name_or_phone"
    assert row["name_reject_reason"] == ""


@pytest.mark.parametrize("bad_name,expected_reason", _IMPORT_INVALID_NAME_CASES)
def test_import_rejects_invalid_candidate_name_dry_run(
    import_engine, tmp_path, bad_name, expected_reason
):
    phone = _import_phone()
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "resume.txt", _minimal_resume(bad_name, phone))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        dry_run=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["would_create"] == 0, result
    assert result["skipped_unparseable"] == 1
    row = result["rows"][0]
    assert row["status"] == "skipped_unparseable"
    assert row["error"] == "invalid_candidate_name"
    assert row["name_reject_reason"] == expected_reason


@pytest.mark.parametrize("bad_name,expected_reason", _IMPORT_MISSING_NAME_CASES)
def test_import_skips_parser_rejected_candidate_name_dry_run(
    import_engine, tmp_path, bad_name, expected_reason
):
    phone = _import_phone()
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "resume.txt", _minimal_resume(bad_name, phone))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        dry_run=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["would_create"] == 0, result
    assert result["skipped_unparseable"] == 1
    row = result["rows"][0]
    assert row["status"] == "skipped_unparseable"
    assert row["error"] == "missing_name_or_phone"
    assert row["name_reject_reason"] == ""


@pytest.mark.parametrize("good_name", ["周鹏飞", "刘昱辰", "张丽娜"])
def test_import_accepts_valid_candidate_names(import_engine, tmp_path, good_name):
    phone = _import_phone()
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "resume.txt", _minimal_resume(good_name, phone))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["created"] == 1, result
    assert result["rows"][0]["name"] == good_name


def test_missing_name_or_phone_skipped(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "no_phone.txt", "姓名：只有名字\n")
    _write_resume_txt(src, "no_name.txt", f"手机 {RAW_PHONE}\n")
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["skipped_unparseable"] == 2
    assert result["created"] == 0
    statuses = {r["file_name"]: r for r in result["rows"]}
    assert statuses["no_phone.txt"]["status"] == "skipped_unparseable"
    assert statuses["no_phone.txt"]["error"] == "missing_name_or_phone"
    assert statuses["no_name.txt"]["status"] == "skipped_unparseable"


def test_duplicate_name_phone_skipped(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    phone = _import_phone()
    content = _resume_content(name=DUP_IMPORT_NAME, phone=phone)
    _write_resume_txt(src, "first.txt", content)
    _write_resume_txt(src, "second.txt", content)
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["created"] == 1
    assert result["skipped_duplicate"] == 1
    dup = next(r for r in result["rows"] if r["status"] == "skipped_duplicate")
    assert dup["duplicate_reason"] == "name_phone_match"


def test_unsupported_image_in_report(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "photo.png").write_bytes(b"\x89PNG")
    _write_resume_txt(src, "ok.txt", _resume_content(phone=_import_phone()))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["skipped_unsupported"] == 1
    assert result["created"] == 1
    png_row = next(r for r in result["rows"] if r["file_name"] == "photo.png")
    assert png_row["status"] == "skipped_unsupported"


def test_bad_file_does_not_block_batch(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "bad.txt", f"姓名：坏文件\n手机 {_import_phone()}\n")
    _write_resume_txt(src, "good.txt", _resume_content(phone=_import_phone()))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    from services.rms_applications import parse_resume_file_for_storage as real_parse

    orig_parse = import_svc.parse_resume_file_for_storage

    def _boom(name, content):
        if name == "bad.txt":
            raise RuntimeError("parse failed")
        return real_parse(name, content)

    import_svc.parse_resume_file_for_storage = _boom
    try:
        result = _run_import(
            import_engine,
            src,
            commit=True,
            upload_dir=upload_dir,
            report_dir=report_dir,
        )
    finally:
        import_svc.parse_resume_file_for_storage = orig_parse

    assert result["failed"] == 1
    assert result["created"] == 1


def test_commit_partial_failure_rolls_back_candidate(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(src, "fail.txt", _resume_content(phone=_import_phone()))
    _write_resume_txt(src, "ok.txt", _resume_content(name="另一候选", phone=_import_phone()))
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"
    before_c = _count_table(import_engine, "rms_candidates")
    before_r = _count_table(import_engine, "rms_resumes")

    orig_save = import_svc._save_resume_bytes

    def _save_fail(upload_dir, candidate_id, file_name, content):
        if file_name == "fail.txt":
            raise OSError("disk full")
        return orig_save(upload_dir, candidate_id, file_name, content)

    with patch.object(import_svc, "_save_resume_bytes", side_effect=_save_fail):
        result = _run_import(
            import_engine,
            src,
            commit=True,
            upload_dir=upload_dir,
            report_dir=report_dir,
        )

    assert result["failed"] == 1
    assert result["created"] == 1
    assert _count_table(import_engine, "rms_candidates") == before_c + 1
    assert _count_table(import_engine, "rms_resumes") == before_r + 1
    fail_row = next(r for r in result["rows"] if r["file_name"] == "fail.txt")
    assert fail_row["status"] == "failed"


def test_docx_empty_parse_skipped_unparseable(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "empty.docx").write_bytes(b"PK\x03\x04fake")
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["skipped_unparseable"] == 1
    row = result["rows"][0]
    assert row["status"] == "skipped_unparseable"
    assert row["status"] != "skipped_unsupported"


def test_reports_csv_json_and_masked_contacts(import_engine, tmp_path):
    phone = _import_phone()
    email = f"{phone}@163.com"
    src = tmp_path / "src"
    src.mkdir()
    _write_resume_txt(
        src,
        "resume.txt",
        _resume_content(phone=phone).replace(RAW_EMAIL, email),
    )
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        dry_run=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )

    assert result["would_create"] == 1, result
    csv_path = Path(result["report_csv"])
    json_path = Path(result["report_json"])
    assert csv_path.is_file()
    assert json_path.is_file()
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(import_svc.REPORT_CSV_FIELDS)
        rows = list(reader)
    assert len(rows) == 1
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "summary" in payload
    assert "rows" in payload

    row = result["rows"][0]
    assert phone not in row["phone_masked"]
    assert "****" in row["phone_masked"]
    assert email not in row["email_masked"]
    raw_csv = csv_path.read_text(encoding="utf-8")
    raw_json = json_path.read_text(encoding="utf-8")
    assert phone not in raw_csv
    assert phone not in raw_json
    assert email not in raw_csv
    assert email not in raw_json


def test_limit_processes_n_files(import_engine, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    limit_names = ["张三", "李四", "王五", "赵六", "孙七"]
    for i in range(5):
        _write_resume_txt(
            src,
            f"cand_{i}.txt",
            _minimal_resume(limit_names[i], _import_phone()),
        )
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        import_engine,
        src,
        dry_run=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
        limit=2,
    )

    assert result["scanned"] == 2
    assert len(result["rows"]) == 2


def test_import_visible_in_candidates_api(rms_client, admin_auth, tmp_path, uniq):
    client, engine = rms_client
    src = tmp_path / "src"
    src.mkdir()
    name = "周鹏飞"
    phone = _import_phone()
    content = _resume_content(name=name, phone=phone)
    _write_resume_txt(src, "resume.txt", content)
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
        source=f"导入来源{uniq[:6]}",
    )
    assert result["created"] == 1, result
    cand_id = result["rows"][0]["candidate_id"]
    user, pwd = admin_auth
    listed = client.get(
        "/api/rms/candidates",
        headers=auth_header(user, pwd),
        params={"q": name},
    )
    assert listed.status_code == 200, listed.text
    ids = {item["id"] for item in listed.json()}
    assert cand_id in ids


def test_import_detail_shows_parse_summary(rms_client, admin_auth, tmp_path, uniq):
    client, engine = rms_client
    src = tmp_path / "src"
    src.mkdir()
    phone = _import_phone()
    content = _resume_content(name="周鹏飞", phone=phone)
    _write_resume_txt(src, "resume.txt", content)
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )
    assert result["created"] == 1, result
    cand_id = result["rows"][0]["candidate_id"]
    user, pwd = admin_auth
    r = client.get(
        f"/api/rms/candidates/{cand_id}",
        headers=auth_header(user, pwd),
    )
    assert r.status_code == 200, r.text
    summary = r.json().get("latest_resume_parse_summary")
    assert isinstance(summary, dict)
    assert summary.get("phone") == phone


def test_list_excludes_parse_summary(rms_client, admin_auth, tmp_path, uniq):
    client, engine = rms_client
    src = tmp_path / "src"
    src.mkdir()
    content = _resume_content(name="周鹏飞", phone=_import_phone())
    _write_resume_txt(src, "resume.txt", content)
    upload_dir = tmp_path / "uploads"
    report_dir = tmp_path / "reports"

    result = _run_import(
        engine,
        src,
        commit=True,
        upload_dir=upload_dir,
        report_dir=report_dir,
    )
    assert result["created"] == 1, result
    cand_id = result["rows"][0]["candidate_id"]
    user, pwd = admin_auth
    listed = client.get("/api/rms/candidates", headers=auth_header(user, pwd))
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == cand_id)
    assert "latest_resume_parse_summary" not in row
