"""RMS dashboard and roster check API tests."""
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


def _delivery_login(client, admin_auth, suffix: str):
    user = f"rms_dash_{suffix}"
    _create_user(client, admin_auth, user, [ROLE_DELIVERY])
    login = _login(client, user)
    assert login.status_code == 200
    return login


def test_dashboard_returns_structure(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "demand_overview" in body
    assert "pipeline_overview" in body
    assert "historical_overview" in body
    assert "recruiter_performance" in body
    assert "open_job_count" in body["demand_overview"]
    stages = body["historical_overview"][0]["stages"]
    assert stages, "expected at least one historical stage"
    for stage in stages:
        assert "pending_count" in stage
        assert "denominator" in stage
        assert stage["denominator"] == stage["entered"] - stage["pending_count"]


def test_dashboard_page_accessible(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/rms/dashboard", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert "rms-dashboard.js" in r.text


def test_hired_roster_check_summary(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/applications/hired-roster-check", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "summary" in body
    assert "items" in body
    assert body["summary"]["total_hired"] == 0


def test_rms_dashboard_boards_seeded(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies)
    assert r.status_code == 200, r.text
    boards = r.json()
    assert isinstance(boards, list)
    assert len(boards) >= 1
    assert boards[0]["scope"] == "rms"
    tab_names = [t["name"] for t in boards[0]["tabs"]]
    assert "总览" in tab_names
    assert "历史转化" in tab_names
    overview = next(t for t in boards[0]["tabs"] if t["name"] == "总览")
    assert len(overview["widgets"]) >= 4
    blocks = {(w.get("config") or {}).get("block") for w in overview["widgets"]}
    assert "kpi_jobs" in blocks
    assert "chart_pipeline" in blocks


def test_rms_dashboard_widget_crud(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    overview = next(t for t in boards[0]["tabs"] if t["name"] == "总览")
    tab_id = overview["id"]
    created = client_rbac.post(
        f"/api/rms/dashboard-tabs/{tab_id}/widgets",
        json={
            "title": "测试 KPI",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {"block": "kpi_hc"},
            "x": 0,
            "y": 20,
            "w": 4,
            "h": 3,
        },
        cookies=login.cookies,
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    updated = client_rbac.put(
        f"/api/rms/dashboard-widgets/{wid}",
        json={
            "title": "测试 KPI 改",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {"block": "kpi_hc"},
            "x": 0,
            "y": 20,
            "w": 6,
            "h": 3,
        },
        cookies=login.cookies,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "测试 KPI 改"
    deleted = client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)
    assert deleted.status_code == 200, deleted.text


def test_rms_dashboard_metadata(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard-metadata", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rms_block" in body["widget_types"]
    assert "number" in body["widget_types"]
    assert len(body.get("sources") or []) > 0
    assert any(b["key"] == "kpi_jobs" for b in body["rms_blocks"])
