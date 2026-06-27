"""Recruitment org department: nav-only access to 招聘 + 帮助中心."""
from __future__ import annotations

import importlib
import secrets
from pathlib import Path

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth import recruitment_nav as recruit_nav
from auth.permissions import ROLE_DELIVERY
from auth.service import AuthContext
from tests.test_rms_phase0_permissions import _create_user, _login
from tests.test_rms_phase2_mvp import _ensure_dept, _set_user_dept

SIDEBAR_PATH = Path(__file__).resolve().parent.parent / "templates" / "partials" / "sidebar_nav.html"
BASE_PATH = Path(__file__).resolve().parent.parent / "templates" / "base.html"


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

    return crm_main.engine


def test_recruitment_org_dept_match_by_name_and_path(rms_engine):
    dept_id = 991001
    _ensure_dept(rms_engine, dept_id, "华东招聘部", path="ROOT/RECRUIT_EAST")
    child_id = dept_id + 1
    _ensure_dept(
        rms_engine,
        child_id,
        "招聘一组",
        path=f"ROOT/RECRUIT_EAST/G1",
        parent_id=dept_id,
    )
    with rms_engine.connect() as conn:
        db = __import__("sqlalchemy.orm", fromlist=["Session"]).Session(bind=conn)
        try:
            ids = recruit_nav.recruitment_org_dept_ids(db)
            assert dept_id in ids
            assert child_id in ids
            ctx = AuthContext(username="u", user_id=1, dept_ids=[child_id], primary_dept_id=child_id)
            assert recruit_nav.user_in_recruitment_org_dept(db, ctx) is True
            other = AuthContext(username="o", user_id=2, dept_ids=[999999], primary_dept_id=999999)
            assert recruit_nav.user_in_recruitment_org_dept(db, other) is False
        finally:
            db.close()


def test_recruitment_nav_only_me_and_page_redirect(client_rbac, admin_auth, rms_engine):
    suffix = secrets.token_hex(4)
    recruit_dept = 992000 + (int(suffix[:6], 16) % 10000)
    _ensure_dept(rms_engine, recruit_dept, f"招聘部_{suffix}", path=f"ROOT/RECRUIT_{recruit_dept}")

    username = f"rec_nav_{suffix}"
    uid = _create_user(client_rbac, admin_auth, username, [ROLE_DELIVERY])
    _set_user_dept(rms_engine, uid, recruit_dept)

    login = _login(client_rbac, username, "pass1234")
    me = client_rbac.get("/api/me", cookies=login.cookies)
    assert me.status_code == 200
    assert me.json()["recruitment_nav_only"] is True

    blocked = client_rbac.get("/customers", cookies=login.cookies, follow_redirects=False)
    assert blocked.status_code == 302
    assert blocked.headers["location"] == "/rms"

    allowed = client_rbac.get("/rms", cookies=login.cookies)
    assert allowed.status_code == 200

    help_page = client_rbac.get("/rms/import-help", cookies=login.cookies, follow_redirects=False)
    assert help_page.status_code == 403


def test_non_recruitment_user_not_nav_restricted(client_rbac, admin_auth, rms_engine):
    suffix = secrets.token_hex(4)
    other_dept = 993000 + (int(suffix[:6], 16) % 10000)
    _ensure_dept(rms_engine, other_dept, f"销售部_{suffix}", path=f"ROOT/SALES_{other_dept}")

    username = f"sales_nav_{suffix}"
    uid = _create_user(client_rbac, admin_auth, username, [ROLE_DELIVERY])
    _set_user_dept(rms_engine, uid, other_dept)

    login = _login(client_rbac, username, "pass1234")
    me = client_rbac.get("/api/me", cookies=login.cookies)
    assert me.status_code == 200
    assert me.json()["recruitment_nav_only"] is False

    page = client_rbac.get("/customers", cookies=login.cookies, follow_redirects=False)
    assert page.status_code in (200, 302)
    if page.status_code == 302:
        assert page.headers["location"] != "/rms"


def test_sidebar_marks_recruitment_allowed_groups():
    html = SIDEBAR_PATH.read_text(encoding="utf-8")
    assert html.count('data-crm-nav-recruitment-allow="1"') == 1
    assert 'class="bms-nav-label">招聘' in html
    assert 'class="bms-nav-label">帮助中心' in html
    assert 'data-crm-nav-help-center="1"' in html


def test_base_shell_applies_recruitment_nav_only_flag():
    html = BASE_PATH.read_text(encoding="utf-8")
    assert "crmRecruitmentNavOnly" in html
    assert "data.recruitment_nav_only" in html
    assert "data-crm-nav-recruitment-allow" in html
