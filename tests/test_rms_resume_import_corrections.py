"""RMS Phase 3D-1C: bulk import corrections CSV + import help page."""
from __future__ import annotations

import csv
import importlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY, ROLE_VIEWER
from services.rms_resume_import_corrections import (
    CORRECTION_INPUT_FIELDS,
    REPORT_CSV_FIELDS,
    apply_resume_import_corrections,
)
from tests.helpers import auth_header
from tests.test_rms_phase0_permissions import _create_user, _revoke_role_permissions
from tests.test_rms_phase2_mvp import (
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _grant_role_permissions,
)
from tests.test_rms_resume_import import (
    _admin_user_id,
    _count_table,
    _import_phone,
    _minimal_resume,
    _reload_rms_main,
    _run_import,
    _write_resume_txt,
)

NAV_PATH = Path(__file__).resolve().parents[1] / "templates" / "partials" / "nav.html"
HELP_PATH = Path(__file__).resolve().parents[1] / "templates" / "pages" / "rms_import_help.html"


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


def _write_corrections_csv(path: Path, rows: list[dict]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(CORRECTION_INPUT_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CORRECTION_INPUT_FIELDS})
    return path


def _run_corrections(
    engine,
    csv_path: Path,
    *,
    dry_run: bool = False,
    commit: bool = False,
    upload_dir: Path,
    report_dir: Path,
):
    import main as crm_main

    db = crm_main.SessionLocal()
    try:
        return apply_resume_import_corrections(
            db,
            csv_path=csv_path,
            dry_run=dry_run,
            commit=commit,
            uploaded_by_user_id=_admin_user_id(engine),
            models=crm_main.RMS_MODELS,
            report_dir=report_dir,
            upload_dir=str(upload_dir),
        )
    finally:
        db.close()


def _import_candidate_with_resume(
    engine,
    tmp_path,
    *,
    name: str,
    phone: str,
    school: str = "西安工业大学",
) -> int:
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    content = _minimal_resume(name, phone) + f"学校：{school}\n"
    _write_resume_txt(src, "seed.txt", content)
    result = _run_import(
        engine,
        src,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["created"] == 1, result
    return int(result["rows"][0]["candidate_id"])


def test_correction_dry_run_create_writes_no_db(import_engine, tmp_path):
    phone = _import_phone()
    resume = tmp_path / "resume.txt"
    resume.write_text(_minimal_resume("周鹏飞", phone), encoding="utf-8")
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": str(resume),
                "action": "create",
                "candidate_id": "",
                "name": "周鹏飞",
                "phone": phone,
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "批量导入",
            }
        ],
    )
    before = _count_table(import_engine, "rms_candidates")
    result = _run_corrections(
        import_engine,
        csv_path,
        dry_run=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["would_create"] == 1
    assert result["created"] == 0
    assert _count_table(import_engine, "rms_candidates") == before


def test_correction_commit_create_persists_candidate_and_resume(import_engine, tmp_path):
    phone = _import_phone()
    resume = tmp_path / "resume.txt"
    resume.write_text(_minimal_resume("刘昱辰", phone), encoding="utf-8")
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": str(resume),
                "action": "create",
                "candidate_id": "",
                "name": "刘昱辰",
                "phone": phone,
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "批量导入",
            }
        ],
    )
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["created"] == 1, result
    assert list((tmp_path / "uploads").rglob("rms/resumes/*"))


def test_correction_create_syncs_parsed_json_summary(
    rms_client, admin_auth, tmp_path, uniq
):
    client, engine = rms_client
    _grant_role_permissions(engine, ROLE_DELIVERY, ("rms.contacts.view",))
    phone = _import_phone()
    resume = tmp_path / "bad_name.txt"
    resume.write_text(_minimal_resume("电话", phone), encoding="utf-8")
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": str(resume),
                "action": "create",
                "candidate_id": "",
                "name": "张三",
                "phone": phone,
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "批量导入",
            }
        ],
    )
    result = _run_corrections(
        engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["created"] == 1, result
    cand_id = int(result["rows"][0]["candidate_id"])
    user, pwd = admin_auth
    r = client.get(
        f"/api/rms/candidates/{cand_id}",
        headers=auth_header(user, pwd),
    )
    assert r.status_code == 200, r.text
    summary = r.json().get("latest_resume_parse_summary") or {}
    assert summary.get("name") == "张三"
    assert summary.get("phone") == phone


def test_correction_update_non_empty_only(import_engine, tmp_path):
    phone = _import_phone()
    cand_id = _import_candidate_with_resume(
        import_engine, tmp_path, name="李四", phone=phone, school="原学校"
    )
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": "",
                "action": "update",
                "candidate_id": str(cand_id),
                "name": "王五",
                "phone": "",
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["updated"] == 1, result
    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, phone, school FROM rms_candidates WHERE id = :id"),
            {"id": cand_id},
        ).fetchone()
    assert row[0] == "王五"
    assert row[1] == phone
    assert row[2] == "原学校"


def test_correction_update_syncs_parsed_json_summary(
    rms_client, admin_auth, tmp_path
):
    client, engine = rms_client
    _grant_role_permissions(engine, ROLE_DELIVERY, ("rms.contacts.view",))
    phone = _import_phone()
    cand_id = _import_candidate_with_resume(
        engine, tmp_path, name="李四", phone=phone
    )
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": "",
                "action": "update",
                "candidate_id": str(cand_id),
                "name": "王五",
                "phone": "",
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    result = _run_corrections(
        engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["updated"] == 1, result
    user, pwd = admin_auth
    r = client.get(
        f"/api/rms/candidates/{cand_id}",
        headers=auth_header(user, pwd),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("name") == "王五"
    summary = body.get("latest_resume_parse_summary") or {}
    assert summary.get("name") == "王五"


def test_correction_update_duplicate_name_phone_fails(import_engine, tmp_path):
    phone_a = _import_phone()
    phone_b = _import_phone()
    _import_candidate_with_resume(import_engine, tmp_path, name="赵六", phone=phone_a)
    cand_b = _import_candidate_with_resume(
        import_engine, tmp_path, name="孙七", phone=phone_b
    )
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": "",
                "action": "update",
                "candidate_id": str(cand_b),
                "name": "赵六",
                "phone": phone_a,
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["failed"] == 1
    assert result["rows"][0]["error"] == "duplicate_name_phone"
    with import_engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, phone FROM rms_candidates WHERE id = :id"),
            {"id": cand_b},
        ).fetchone()
    assert row[0] == "孙七"
    assert row[1] == phone_b


def test_correction_skip_writes_no_db(import_engine, tmp_path):
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": "/tmp/ignored.pdf",
                "action": "skip",
                "candidate_id": "",
                "name": "",
                "phone": "",
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    before = _count_table(import_engine, "rms_candidates")
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["skipped"] == 1
    assert _count_table(import_engine, "rms_candidates") == before


def test_correction_invalid_action_failed(import_engine, tmp_path):
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": "",
                "action": "delete",
                "candidate_id": "",
                "name": "",
                "phone": "",
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["failed"] == 1
    assert result["rows"][0]["error"] == "invalid_action"


def test_correction_create_missing_name_phone_failed(import_engine, tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text(_minimal_resume("周鹏飞", _import_phone()), encoding="utf-8")
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": str(resume),
                "action": "create",
                "candidate_id": "",
                "name": "",
                "phone": "",
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["failed"] == 1
    assert result["rows"][0]["error"] == "missing_required_fields"


def test_correction_create_duplicate_skipped(import_engine, tmp_path):
    phone = _import_phone()
    _import_candidate_with_resume(import_engine, tmp_path, name="张丽娜", phone=phone)
    resume = tmp_path / "dup.txt"
    resume.write_text(_minimal_resume("张丽娜", phone), encoding="utf-8")
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": str(resume),
                "action": "create",
                "candidate_id": "",
                "name": "张丽娜",
                "phone": phone,
                "email_wechat": "",
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    before = _count_table(import_engine, "rms_candidates")
    result = _run_corrections(
        import_engine,
        csv_path,
        commit=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    assert result["skipped_duplicate"] == 1
    assert _count_table(import_engine, "rms_candidates") == before


def test_correction_reports_masked(import_engine, tmp_path):
    phone = _import_phone()
    resume = tmp_path / "resume.txt"
    resume.write_text(_minimal_resume("周鹏飞", phone), encoding="utf-8")
    email = f"{phone}@example.com"
    csv_path = _write_corrections_csv(
        tmp_path / "corr.csv",
        [
            {
                "resume_file_path": str(resume),
                "action": "create",
                "candidate_id": "",
                "name": "周鹏飞",
                "phone": phone,
                "email_wechat": email,
                "school": "",
                "major": "",
                "education_level": "",
                "source": "",
            }
        ],
    )
    result = _run_corrections(
        import_engine,
        csv_path,
        dry_run=True,
        upload_dir=tmp_path / "uploads",
        report_dir=tmp_path / "reports",
    )
    csv_file = Path(result["report_csv"])
    json_file = Path(result["report_json"])
    assert csv_file.is_file()
    assert json_file.is_file()
    with csv_file.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(REPORT_CSV_FIELDS)
        rows = list(reader)
    assert len(rows) == 1
    raw_csv = csv_file.read_text(encoding="utf-8")
    raw_json = json_file.read_text(encoding="utf-8")
    assert phone not in raw_csv
    assert phone not in raw_json
    assert email not in raw_csv
    assert email not in raw_json


def test_import_help_page_content_and_placeholders():
    html = HELP_PATH.read_text(encoding="utf-8")
    assert "批量导入候选人" in html
    assert "import_rms_resumes_with_ocr_retry.py" in html
    assert "--dry-run" in html
    assert "--commit" in html
    assert "created" in html
    assert "updated" in html
    assert "skipped_duplicate" in html
    assert "skipped_unparseable" in html
    assert "corrections.csv" in html
    assert "/你的简历目录" in html
    assert "/你的修正CSV路径" in html
    assert "/Users/rocky" not in html


def test_import_help_requires_super_admin(rms_client, admin_auth, uniq):
    client, engine = rms_client
    user, pwd = admin_auth
    ok = client.get("/rms/import-help", headers=auth_header(user, pwd))
    assert ok.status_code == 200, ok.text

    viewer = f"viewer_no_cand_{uniq[:8]}"
    _create_user(client, admin_auth, viewer, [ROLE_VIEWER])
    denied = client.get("/rms/import-help", headers=auth_header(viewer, "pass1234"))
    assert denied.status_code == 403


def test_import_help_nav_super_admin_only():
    nav = NAV_PATH.read_text(encoding="utf-8")
    assert 'data-crm-nav-super="1">帮助文件-如何批量导入候选人' in nav
    assert 'data-crm-nav-help-center="1"' in nav
