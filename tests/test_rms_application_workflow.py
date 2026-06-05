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
)

PARSE_DRAFT_URL = "/api/rms/applications/candidate-report/parse-draft"


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
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


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
