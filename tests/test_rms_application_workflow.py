"""RMS candidate-report parse-draft workflow."""
from __future__ import annotations

import importlib
import uuid

import pytest
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY
from tests.test_rms_phase2_mvp import (
    _create_user,
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _login,
    _trial_job_and_candidate,
)

PARSE_DRAFT_URL = "/api/rms/applications/candidate-report/parse-draft"
DELIVERY_REVIEW_LIST_URL = "/api/rms/applications/delivery-review"


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


@pytest.fixture
def rms_engine(client_rbac):
    import main as crm_main

    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)
    return crm_main.engine


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


def _delivery_login(client, admin_auth, uniq_suffix: str):
    delivery_user = f"rms_wf_delivery_{uniq_suffix}"
    _create_user(client, admin_auth, delivery_user, [ROLE_DELIVERY])
    login = _login(client, delivery_user)
    assert login.status_code == 200
    return login


def _make_text_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line, fontname="china-s", fontsize=11)
        y += 14
    data = doc.tobytes()
    doc.close()
    return data


def _resume_with_contact_and_education() -> str:
    return (
        "姓名：测试候选人\n"
        "手机 15988192434\n"
        "email: 15988192434@163.com\n"
        "教育背景\n"
        "2015.09 -- 2019.07  西安工业大学（学士）    测控技术与仪器专业\n"
        "2019.09 -- 2022.07  西安工业大学（硕士）    仪器仪表工程专业\n"
        "毕业论文：《基于DLP 系统的超短焦4K 投影镜头设计》\n"
        "项目经历\n"
        "杭州电子科技大学信息工程学院激光雷达中心"
    )


def _assert_contact_and_education_draft(draft: dict) -> None:
    assert draft.get("phone") == "15988192434"
    assert draft.get("email_wechat") == "15988192434@163.com"
    assert draft.get("school") == "西安工业大学"
    assert draft.get("major") == "仪器仪表工程"
    assert draft.get("education_level") == "硕士"
    major = draft.get("major") or ""
    school = draft.get("school") or ""
    assert "毕业论文" not in major
    assert "DLP" not in major
    assert "杭州" not in school
    assert "2015" not in school


def test_parse_draft_route_not_captured_by_application_id(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = "姓名：路由测试\n手机 13800138000\nemail: route@test.com"
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.status_code != 422


def test_parse_draft_txt_extracts_phone_email_and_work_years(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = (
        "姓名：张三\n"
        "手机 13800138077\n"
        "email: draft@example.com\n"
        "年龄：28\n"
        "工作年限：5年"
    )
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    draft = body.get("draft_fields") or {}
    assert draft.get("phone") == "13800138077"
    assert draft.get("email_wechat") == "draft@example.com"
    assert draft.get("work_years") == "5年"
    assert body.get("parsed_text")


def test_parse_draft_txt_contact_and_education(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    txt = _resume_with_contact_and_education()
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_contact_and_education_draft(body.get("draft_fields") or {})
    assert body.get("parsed_text")


def test_parse_draft_pdf_contact_and_education(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf(_resume_with_contact_and_education())
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_contact_and_education_draft(body.get("draft_fields") or {})
    assert body.get("parsed_text")


def test_parse_draft_pdf_extracts_fields_and_parsed_text(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    pdf_bytes = _make_text_pdf("姓名：王五\n手机 13700137000\nemail: pdf@test.com")
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    draft = body.get("draft_fields") or {}
    assert any(draft.get(k) for k in ("phone", "email_wechat", "name"))
    assert body.get("parsed_text")


def test_parse_draft_docx_returns_friendly_message(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.docx", b"PK fake docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("draft_fields") == {}
    assert "Word" in (body.get("message") or "")


def test_parse_draft_unknown_extension_returns_400(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.post(
        PARSE_DRAFT_URL,
        cookies=login.cookies,
        files={"file": ("resume.exe", b"binary", "application/octet-stream")},
    )
    assert r.status_code == 400, r.text


def test_delivery_review_route_not_captured_by_application_id(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert r.status_code != 422, r.text
    assert r.status_code == 200, r.text


def test_delivery_review_list_empty(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_delivery_review_list_returns_recommended(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"dr_{uniq}"
    )
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    app_id = created.json()["id"]

    r = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert r.status_code == 200, r.text
    ids = [item["id"] for item in r.json()]
    assert app_id in ids


def _create_recommended_application(client, admin_auth, rms_engine, suffix: str) -> tuple:
    login, job_id, cand_id, _ = _trial_job_and_candidate(client, rms_engine, admin_auth, suffix)
    created = client.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    return login, int(created.json()["id"])


def test_delivery_review_submit_passed_without_columns(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_pass_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed", "note": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "未持久化" in (body.get("message") or "")


def test_delivery_review_submit_failed_without_columns(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_fail_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "failed", "note": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "未持久化" in (body.get("message") or "")


def test_delivery_review_submit_invalid_result(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_bad_{uniq}"
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "maybe", "note": ""},
    )
    assert r.status_code == 422, r.text


def test_delivery_review_submit_does_not_remove_without_columns(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, app_id = _create_recommended_application(
        client_rbac, admin_auth, rms_engine, f"dr_stay_{uniq}"
    )
    submit = client_rbac.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed", "note": ""},
    )
    assert submit.status_code == 200, submit.text

    listed = client_rbac.get(DELIVERY_REVIEW_LIST_URL, cookies=login.cookies)
    assert listed.status_code == 200, listed.text
    ids = [item["id"] for item in listed.json()]
    assert app_id in ids
