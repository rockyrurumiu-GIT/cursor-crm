"""RMS dashboard and roster check API tests."""
from __future__ import annotations

import importlib
import uuid

import pytest
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY
from tests.helpers import auth_header
from tests.test_rms_phase2_mvp import (
    _candidate_json,
    _create_client_admin,
    _create_user,
    _delivery_open_job,
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _login,
    _set_client_owner,
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
    assert "client_job_stage_summary" in body
    summary = body["client_job_stage_summary"]
    assert "rows" in summary
    assert "total" in summary
    assert "period_label" in summary
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
    assert "Test" in tab_names
    test_tab = next(t for t in boards[0]["tabs"] if t["name"] == "Test")
    test_blocks = {(w.get("config") or {}).get("block") for w in test_tab["widgets"]}
    assert {
        "chart_client_job_stage_grouped",
        "chart_client_job_stage_stacked",
        "chart_client_job_stage_funnel",
    }.issubset(test_blocks)
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


def _admin_login(client, admin_auth):
    user, pwd = admin_auth
    login = _login(client, user, pwd)
    assert login.status_code == 200
    return login


def _rms_overview_tab(client, cookies):
    boards = client.get("/api/rms/dashboard-boards", cookies=cookies).json()
    return next(t for t in boards[0]["tabs"] if t["name"] == "总览")


def _create_rms_widget(client, cookies, tab_id: int, **payload):
    body = {
        "title": "Test Widget",
        "widget_type": "number",
        "source_key": "rms_jobs",
        "config": {"metric": "count"},
        "x": 0,
        "y": 99,
        "w": 4,
        "h": 3,
    }
    body.update(payload)
    return client.post(
        f"/api/rms/dashboard-tabs/{tab_id}/widgets",
        json=body,
        cookies=cookies,
    )


def test_rms_dashboard_metadata(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard-metadata", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "rms_block" in body["widget_types"]
    assert "number" in body["widget_types"]
    source_keys = {s["key"] for s in body.get("sources") or []}
    assert {"rms_jobs", "rms_candidates", "rms_applications"}.issubset(source_keys)
    for key in ("rms_jobs", "rms_candidates", "rms_applications"):
        src = next(s for s in body["sources"] if s["key"] == key)
        assert len(src.get("fields") or []) > 0
    assert any(b["key"] == "kpi_jobs" for b in body["rms_blocks"])
    assert any(b["key"] == "table_client_job_stage" for b in body["rms_blocks"])
    for chart_key in (
        "chart_client_job_stage_grouped",
        "chart_client_job_stage_stacked",
        "chart_client_job_stage_funnel",
    ):
        assert any(b["key"] == chart_key for b in body["rms_blocks"])


def _history_tab(client, cookies):
    boards = client.get("/api/rms/dashboard-boards", cookies=cookies).json()
    return next(t for t in boards[0]["tabs"] if t["name"] == "历史转化")


def _job_row(summary: dict, job_id: int) -> dict:
    for row in summary.get("rows") or []:
        if int(row["job_id"]) == int(job_id):
            return row
    raise AssertionError(f"job {job_id} not in summary rows")


def test_dashboard_job_id_backward_compatible(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"jid_{uniq}")
    r = client_rbac.get(f"/api/rms/dashboard?job_id={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    rows = r.json()["client_job_stage_summary"]["rows"]
    assert rows
    assert all(int(row["job_id"]) == int(job_id) for row in rows)


def test_dashboard_job_ids_invalid_returns_400(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard?job_ids=1,x", cookies=login.cookies)
    assert r.status_code == 400, r.text


def test_dashboard_job_ids_multi_select(client_rbac, admin_auth, rms_engine, uniq):
    login, job_a = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"ja_{uniq}")
    job_a_body = client_rbac.get(f"/api/rms/jobs/{job_a}", cookies=login.cookies).json()
    admin_user, admin_pwd = admin_auth
    job_b = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": job_a_body["client_id"],
            "title": f"Job B {uniq}",
            "owner_user_id": job_a_body["owner_user_id"],
            "delivery_owner_user_id": job_a_body["delivery_owner_user_id"],
        },
    )
    assert job_b.status_code == 200, job_b.text
    job_b_id = job_b.json()["id"]
    _delivery_open_job(client_rbac, rms_engine, admin_auth, f"jc_{uniq}")
    r = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_a},{job_b_id}",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    row_ids = {int(row["job_id"]) for row in r.json()["client_job_stage_summary"]["rows"]}
    assert row_ids == {int(job_a), int(job_b_id)}


def test_dashboard_client_job_stage_client_filter(client_rbac, admin_auth, rms_engine, uniq):
    login_a, job_a = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"ca_{uniq}")
    login_b, job_b = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"cb_{uniq}")
    cand_a = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_a.cookies,
        json=_candidate_json(job_a, name="Cand A"),
    )
    assert cand_a.status_code == 200
    app_a = client_rbac.post(
        "/api/rms/applications",
        cookies=login_a.cookies,
        json={"job_id": job_a, "candidate_id": cand_a.json()["id"]},
    )
    assert app_a.status_code == 200
    cand_b = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_b.cookies,
        json=_candidate_json(job_b, name="Cand B"),
    )
    assert cand_b.status_code == 200
    app_b = client_rbac.post(
        "/api/rms/applications",
        cookies=login_b.cookies,
        json={"job_id": job_b, "candidate_id": cand_b.json()["id"]},
    )
    assert app_b.status_code == 200
    client_a_id = app_a.json()["client_id"]
    r = client_rbac.get(
        f"/api/rms/dashboard?client_id={client_a_id}",
        cookies=login_a.cookies,
    )
    assert r.status_code == 200, r.text
    row_ids = {int(row["job_id"]) for row in r.json()["client_job_stage_summary"]["rows"]}
    assert int(job_a) in row_ids
    assert int(job_b) not in row_ids


def test_dashboard_client_job_stage_date_filter(client_rbac, admin_auth, rms_engine, uniq):
    from sqlalchemy import text

    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"dt_{uniq}")
    cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name="In Range"),
    )
    assert cand.status_code == 200
    app_in = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand.json()["id"]},
    )
    assert app_in.status_code == 200
    cand2 = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name="Out Range"),
    )
    assert cand2.status_code == 200
    app_out = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand2.json()["id"]},
    )
    assert app_out.status_code == 200
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": "2020-01-01", "id": app_out.json()["id"]},
        )
    r = client_rbac.get(
        "/api/rms/dashboard?date_from=2026-01-01&date_to=2026-12-31",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["pushed_resume_count"] == 1


def test_dashboard_period_event_pass_without_push_in_range(
    client_rbac, admin_auth, rms_engine, uniq
):
    """Push before period, first-interview pass inside period — pass counts, push does not."""
    from sqlalchemy import text
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"pep_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": "2026-06-01", "id": app_id},
        )
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": to_status, "reason": "ok"},
        )
        assert tr.status_code == 200, tr.text
    with rms_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_application_status_history "
                "SET changed_at = :d WHERE application_id = :id AND to_status = :st"
            ),
            {"d": "2026-06-09", "id": app_id, "st": "first_interview_passed"},
        )
    r = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from=2026-06-08&date_to=2026-06-10",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["pushed_resume_count"] == 0
    assert row["interview_passed"] == 1


def test_dashboard_period_push_and_pass_same_range(
    client_rbac, admin_auth, rms_engine, uniq
):
    from sqlalchemy import text
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"ppr_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": "2026-06-08", "id": app_id},
        )
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": to_status, "reason": "ok"},
        )
        assert tr.status_code == 200, tr.text
    with rms_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_application_status_history "
                "SET changed_at = :d WHERE application_id = :id AND to_status = :st"
            ),
            {"d": "2026-06-09", "id": app_id, "st": "first_interview_passed"},
        )
    r = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from=2026-06-08&date_to=2026-06-10",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["pushed_resume_count"] == 1
    assert row["interview_passed"] == 1


def test_dashboard_client_job_stage_metrics(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"met_{uniq}")
    job_id = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()["job_id"]

    def dash_row():
        r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
        assert r.status_code == 200, r.text
        return _job_row(r.json()["client_job_stage_summary"], job_id)

    row = dash_row()
    assert row["pushed_resume_count"] == 1
    assert row["internal_screen_passed"] == 1
    assert row["pending_client_screen"] == 1

    for to_status in ("scheduling_interview", "pending_first_interview", "first_interview_passed"):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": to_status, "reason": "ok"},
        )
        assert tr.status_code == 200, tr.text

    row = dash_row()
    assert row["client_screen_passed"] == 1
    assert row["pending_interview"] == 0
    assert row["interviewed"] == 1
    assert row["interview_passed"] == 1
    assert row["internal_screen_passed_rate"] == "100%"
    assert row["client_screen_passed_rate"] == "100%"
    assert row["interview_passed_rate"] == "100%"
    assert row["interview_abandoned_rate"] == "0%"

    for to_status in ("second_interview_passed", "pending_offer"):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": to_status, "reason": "ok"},
        )
        assert tr.status_code == 200, tr.text

    row = dash_row()
    assert row["pending_offer_count"] == 1
    assert row["offer_dropped_count"] == 0
    assert row["onboarding_count"] == 0
    assert row["onboarding_lost_count"] == 0
    assert row["hired_count"] == 0

    tr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "onboarding", "reason": "ok"},
    )
    assert tr.status_code == 200, tr.text

    row = dash_row()
    assert row["pending_offer_count"] == 0
    assert row["onboarding_count"] == 1
    assert row["hired_count"] == 0

    tr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "reason": "ok", "hired_at": "2026-06-01"},
    )
    assert tr.status_code == 200, tr.text

    row = dash_row()
    assert row["onboarding_count"] == 1
    assert row["hired_count"] == 1


def test_rms_dashboard_widget_create_client_job_stage_block(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    tab = _history_tab(client_rbac, login.cookies)
    created = client_rbac.post(
        f"/api/rms/dashboard-tabs/{tab['id']}/widgets",
        json={
            "title": "历史数据",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {"block": "table_client_job_stage"},
            "x": 0,
            "y": 20,
            "w": 12,
            "h": 6,
        },
        cookies=login.cookies,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["widget_type"] == "rms_block"
    assert body["config"]["block"] == "table_client_job_stage"
    wid = body["id"]

    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    history = next(t for t in boards[0]["tabs"] if t["id"] == tab["id"])
    saved = next(w for w in history["widgets"] if w["id"] == wid)
    assert saved["config"]["block"] == "table_client_job_stage"

    deleted = client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)
    assert deleted.status_code == 200, deleted.text


def test_crm_dashboard_metadata_excludes_rms_sources(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    r = client_rbac.get("/api/dashboard-metadata", headers=auth_header(user, pwd))
    assert r.status_code == 200, r.text
    source_keys = {s["key"] for s in r.json().get("sources") or []}
    assert "clients" in source_keys
    assert "rms_jobs" not in source_keys
    assert "rms_candidates" not in source_keys
    assert "rms_applications" not in source_keys


def test_global_dashboard_rejects_rms_source(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    dash = client_rbac.post("/api/dashboards", headers=headers, json={"name": f"Iso {uniq}"})
    assert dash.status_code == 200, dash.text
    dash_id = dash.json()["id"]
    tab = client_rbac.post(
        f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"}
    )
    assert tab.status_code == 200, tab.text
    tab_id = tab.json()["id"]
    bad = client_rbac.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "Bad RMS",
            "widget_type": "number",
            "source_key": "rms_jobs",
            "config": {"metric": "count"},
        },
    )
    assert bad.status_code == 400
    assert "rms_jobs" in bad.json().get("detail", "")
    client_rbac.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_rms_widget_data_jobs_sum(client_rbac, admin_auth, rms_engine, uniq):
    login = _admin_login(client_rbac, admin_auth)
    suffix = uniq
    sales = f"rms_dash_s_{suffix}"
    delivery = f"rms_dash_d_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_DELIVERY])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    cid = _create_client_admin(client_rbac, admin_auth, f"Dash Job {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    admin_user, admin_pwd = admin_auth
    job = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"HC Job {suffix}",
            "owner_user_id": sales_uid,
            "delivery_owner_user_id": delivery_uid,
            "headcount": 5,
        },
    )
    assert job.status_code == 200, job.text

    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        title="HC 汇总",
        widget_type="number",
        source_key="rms_jobs",
        config={"metric": "sum", "field": "headcount"},
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    body = data.json()
    assert body["status"] == "ok"
    assert body["kind"] == "scalar"
    assert float(body["value"]) >= 5.0
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_group_label_resolver():
    from schemas.rms import application_progress_label, resolve_rms_group_label

    assert application_progress_label("first_interview_passed") == "一面通过"
    assert application_progress_label("hired") == "已入职"
    assert application_progress_label("pending_internal_screen") == "待内筛"
    assert resolve_rms_group_label("rms_applications", "current_stage", "hired") == "已入职"
    assert resolve_rms_group_label("rms_jobs", "priority", "high") == "高"


def test_rms_widget_data_applications_group_labels(client_rbac, admin_auth, rms_engine, uniq):
    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"stage_{uniq}")
    cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_id),
    )
    assert cand.status_code == 200, cand.text
    app = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": cand.json()["id"]},
    )
    assert app.status_code == 200, app.text

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        title="阶段分布",
        widget_type="pie",
        source_key="rms_applications",
        config={"metric": "count", "group_by": "current_stage"},
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    body = data.json()
    assert body["status"] == "ok"
    assert "待内筛" in body.get("labels", [])
    assert "pending_internal_screen" not in body.get("labels", [])
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_widget_data_candidates_group(client_rbac, admin_auth, rms_engine, uniq):
    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"cand_{uniq}")
    cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_id, source="内推"),
    )
    assert cand.status_code == 200, cand.text

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        title="来源分布",
        widget_type="bar",
        source_key="rms_candidates",
        config={"metric": "count", "group_by": "source"},
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    body = data.json()
    assert body["status"] == "ok"
    assert body["kind"] == "series"
    assert "内推" in body.get("labels", [])
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_widget_data_forbidden_without_jobs_read(client_rbac, admin_auth, rms_engine, uniq, monkeypatch):
    import main as crm_main
    from auth import policy
    from auth import service as auth_svc
    from auth.permissions import ALL_PERMISSION_CODES
    from auth.service import AuthContext

    suffix = uniq
    monkeypatch.setattr(policy, "generate_custom_role_code", lambda: f"CUSTOM_{suffix}_jobs")
    db = crm_main.SessionLocal()
    try:
        admin_user, _ = admin_auth
        super_ctx = AuthContext(
            username=admin_user,
            user_id=1,
            roles=["SUPER_ADMIN"],
            permissions=sorted(ALL_PERMISSION_CODES),
            dept_ids=[],
            role_data_scopes={},
            is_super=True,
        )
        role = auth_svc.create_custom_role(
            db, name=f"RMS Analytics Only {suffix}", description="test", actor=admin_user
        )
        perms = [
            p for p in ALL_PERMISSION_CODES
            if p not in ("rms.jobs.read", "rms.jobs.write")
        ]
        auth_svc.set_role_permissions(
            db, role["id"], perms, actor=admin_user, actor_ctx=super_ctx
        )
        username = f"rms_analytics_{suffix}"
        auth_svc.create_user(
            db,
            username=username,
            password="analytics1",
            display_name="Analytics Only",
            role_codes=[role["code"]],
            actor=admin_user,
            actor_ctx=super_ctx,
        )
        db.commit()
    finally:
        db.close()

    login = _login(client_rbac, username, "analytics1")
    assert login.status_code == 200
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        title="Forbidden jobs",
        source_key="rms_jobs",
        config={"metric": "count"},
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    assert data.json()["status"] == "forbidden"
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_candidates_empty_visible_returns_zero(client_rbac, admin_auth, rms_engine, uniq, monkeypatch):
    import main as crm_main
    from auth import policy
    from auth import service as auth_svc
    from auth.permissions import ALL_PERMISSION_CODES
    from auth.service import AuthContext

    suffix = uniq
    monkeypatch.setattr(policy, "generate_custom_role_code", lambda: f"CUSTOM_{suffix}_cand")
    db = crm_main.SessionLocal()
    try:
        admin_user, _ = admin_auth
        super_ctx = AuthContext(
            username=admin_user,
            user_id=1,
            roles=["SUPER_ADMIN"],
            permissions=sorted(ALL_PERMISSION_CODES),
            dept_ids=[],
            role_data_scopes={},
            is_super=True,
        )
        role = auth_svc.create_custom_role(
            db, name=f"RMS Cand Read {suffix}", description="test", actor=admin_user
        )
        auth_svc.set_role_permissions(
            db,
            role["id"],
            ["dashboard.read", "dashboard.write", "rms.analytics.read", "rms.candidates.read"],
            actor=admin_user,
            actor_ctx=super_ctx,
        )
        username = f"rms_cand_empty_{suffix}"
        auth_svc.create_user(
            db,
            username=username,
            password="candempty1",
            display_name="Cand Empty",
            role_codes=[role["code"]],
            actor=admin_user,
            actor_ctx=super_ctx,
        )
        db.commit()
    finally:
        db.close()

    login = _login(client_rbac, username, "candempty1")
    assert login.status_code == 200
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        title="Empty candidates",
        source_key="rms_candidates",
        config={"metric": "count"},
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    body = data.json()
    assert body["status"] == "ok"
    assert body["kind"] == "scalar"
    assert float(body["value"]) == 0.0
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_dashboard_metadata_field_roles_and_enums(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard-metadata", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "primary_axis_sorts" in body
    assert "secondary_axis_sorts" in body
    assert "group_modes" in body
    assert "axis_name_displays" in body
    assert "position_asc" in body["primary_axis_sorts"]
    assert body["primary_axis_sorts"] == [
        "position_asc", "position_desc",
        "label_asc", "label_desc",
        "sum_asc", "sum_desc",
        "manual",
    ]
    assert "value_asc" not in body["primary_axis_sorts"]
    apps = next(s for s in body["sources"] if s["key"] == "rms_applications")
    stage = next(f for f in apps["fields"] if f["key"] == "current_stage")
    assert stage.get("role") == "dimension"
    assert stage.get("filterable") is True


def test_rms_widget_config_normalize_round_trip(client_rbac, admin_auth, rms_engine, uniq):
    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={"metric": "count", "group_by": "current_stage", "sort": "value_desc"},
    )
    assert created.status_code == 200, created.text
    cfg = created.json()["config"]
    assert cfg.get("primary_axis_field") == "current_stage"
    assert cfg.get("group_by") == "current_stage"
    assert cfg.get("aggregate_field") == ""
    assert cfg.get("field") == ""
    assert "primary_axis_sort" in cfg
    assert cfg.get("primary_axis_sort") == "sum_desc"
    assert cfg.get("sort") == "value_desc"
    assert "display_legend" in cfg
    assert "show_legend" in cfg
    client_rbac.delete(f"/api/rms/dashboard-widgets/{created.json()['id']}", cookies=login.cookies)


def test_rms_widget_data_grouped_series(client_rbac, admin_auth, rms_engine, uniq):
    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"grp_{uniq}")
    for i in range(2):
        cand = client_rbac.post(
            "/api/rms/candidates",
            cookies=login_del.cookies,
            json=_candidate_json(job_id, source="内推", name=f"Cand {i}"),
        )
        assert cand.status_code == 200, cand.text
        app = client_rbac.post(
            "/api/rms/applications",
            cookies=login_del.cookies,
            json={"job_id": job_id, "candidate_id": cand.json()["id"]},
        )
        assert app.status_code == 200, app.text

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={
            "metric": "count",
            "primary_axis_field": "current_stage",
            "secondary_axis_field": "client_id",
            "group_mode": "stacked",
        },
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    body = data.json()
    assert body["kind"] == "grouped_series"
    assert body.get("keys")
    assert body.get("data")
    assert "xAxisLabel" in body
    assert "yAxisLabel" in body
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_pie_rejects_secondary_axis_400(client_rbac, admin_auth, rms_engine, uniq):
    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    bad = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="pie",
        source_key="rms_applications",
        config={
            "metric": "count",
            "primary_axis_field": "current_stage",
            "secondary_axis_field": "client_id",
        },
    )
    assert bad.status_code == 400


def test_rms_applications_current_stage_pipeline_order(client_rbac, admin_auth, rms_engine, uniq):
    from sqlalchemy import text

    from schemas.rms import APPLICATION_PROGRESS_ORDER, application_progress_label

    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"ord_{uniq}")
    app_ids = []
    stages = ["hired", "pending_internal_screen", "pending_client_screen"]
    for st in stages:
        cand = client_rbac.post(
            "/api/rms/candidates",
            cookies=login_del.cookies,
            json=_candidate_json(job_id, name=f"Cand {st}"),
        )
        assert cand.status_code == 200, cand.text
        app = client_rbac.post(
            "/api/rms/applications",
            cookies=login_del.cookies,
            json={"job_id": job_id, "candidate_id": cand.json()["id"]},
        )
        assert app.status_code == 200, app.text
        app_ids.append((app.json()["id"], st))

    with rms_engine.begin() as conn:
        for app_id, st in app_ids:
            conn.execute(
                text(
                    "UPDATE rms_applications SET status = :status, current_stage = :status WHERE id = :id"
                ),
                {"id": app_id, "status": st},
            )

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={
            "metric": "count",
            "primary_axis_field": "current_stage",
            "primary_axis_sort": "position_asc",
        },
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    labels = data.json().get("labels") or []
    expected = [application_progress_label(s) for s in APPLICATION_PROGRESS_ORDER if application_progress_label(s) in labels]
    assert labels == expected
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_widget_data_manual_primary_axis_order(client_rbac, admin_auth, rms_engine, uniq):
    from sqlalchemy import text

    from schemas.rms import application_progress_label

    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"manual_{uniq}")
    stages = ["pending_internal_screen", "pending_client_screen", "pending_first_interview"]
    for st in stages:
        cand = client_rbac.post(
            "/api/rms/candidates",
            cookies=login_del.cookies,
            json=_candidate_json(job_id, name=f"Cand {st}"),
        )
        assert cand.status_code == 200, cand.text
        app = client_rbac.post(
            "/api/rms/applications",
            cookies=login_del.cookies,
            json={"job_id": job_id, "candidate_id": cand.json()["id"]},
        )
        assert app.status_code == 200, app.text
        with rms_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE rms_applications SET status = :status, current_stage = :status WHERE id = :id"
                ),
                {"id": app.json()["id"], "status": st},
            )

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    labels = [application_progress_label(s) for s in stages]
    manual_order = [labels[2], labels[0], labels[1]]
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={
            "metric": "count",
            "primary_axis_field": "current_stage",
            "primary_axis_sort": "manual",
            "primary_axis_order": manual_order,
        },
    )
    assert created.status_code == 200, created.text
    cfg = created.json()["config"]
    assert cfg.get("primary_axis_order") == manual_order
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    labels = data.json().get("labels") or []
    for i, lb in enumerate(manual_order):
        assert labels.index(lb) == i
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_widget_sort_sum_desc(client_rbac, admin_auth, rms_engine, uniq):
    from sqlalchemy import text

    from schemas.rms import application_progress_label

    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"sum_{uniq}")
    stages = ["pending_internal_screen", "pending_client_screen", "pending_first_interview"]
    counts = [5, 1, 3]
    for st, cnt in zip(stages, counts):
        for i in range(cnt):
            cand = client_rbac.post(
                "/api/rms/candidates",
                cookies=login_del.cookies,
                json=_candidate_json(job_id, name=f"Cand {st} {i}"),
            )
            assert cand.status_code == 200, cand.text
            app = client_rbac.post(
                "/api/rms/applications",
                cookies=login_del.cookies,
                json={"job_id": job_id, "candidate_id": cand.json()["id"]},
            )
            assert app.status_code == 200, app.text
            with rms_engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE rms_applications SET status = :status, current_stage = :status WHERE id = :id"
                    ),
                    {"id": app.json()["id"], "status": st},
                )

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={
            "metric": "count",
            "primary_axis_field": "current_stage",
            "primary_axis_sort": "sum_desc",
            "filters": [
                {"field": "job_id", "op": "eq", "value": job_id},
            ],
        },
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    body = data.json()
    labels = body.get("labels") or []
    values = body.get("values") or []
    assert values == sorted(values, reverse=True)
    by_label = dict(zip(labels, values))
    assert by_label[application_progress_label("pending_internal_screen")] == 5
    assert by_label[application_progress_label("pending_first_interview")] == 3
    assert by_label[application_progress_label("pending_client_screen")] == 1
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_widget_sort_position_on_status_field(client_rbac, admin_auth, rms_engine, uniq):
    from sqlalchemy import text

    from schemas.rms import APPLICATION_PROGRESS_ORDER, application_progress_label

    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"st_{uniq}")
    stages = ["hired", "pending_internal_screen", "pending_client_screen"]
    for st in stages:
        cand = client_rbac.post(
            "/api/rms/candidates",
            cookies=login_del.cookies,
            json=_candidate_json(job_id, name=f"Cand {st}"),
        )
        assert cand.status_code == 200, cand.text
        app = client_rbac.post(
            "/api/rms/applications",
            cookies=login_del.cookies,
            json={"job_id": job_id, "candidate_id": cand.json()["id"]},
        )
        assert app.status_code == 200, app.text
        with rms_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE rms_applications SET status = :status, current_stage = :status WHERE id = :id"
                ),
                {"id": app.json()["id"], "status": st},
            )

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={
            "metric": "count",
            "primary_axis_field": "status",
            "primary_axis_sort": "position_asc",
        },
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    labels = data.json().get("labels") or []
    expected = [application_progress_label(s) for s in APPLICATION_PROGRESS_ORDER if application_progress_label(s) in labels]
    assert labels == expected
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_fk_group_labels_in_widget_data(client_rbac, admin_auth, rms_engine, uniq):
    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"fk_{uniq}")
    cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_id),
    )
    assert cand.status_code == 200, cand.text
    app = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": cand.json()["id"]},
    )
    assert app.status_code == 200, app.text

    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = _create_rms_widget(
        client_rbac,
        login.cookies,
        overview["id"],
        widget_type="bar",
        source_key="rms_applications",
        config={"metric": "count", "primary_axis_field": "client_id"},
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]
    data = client_rbac.get(f"/api/rms/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert data.status_code == 200, data.text
    labels = data.json().get("labels") or []
    assert labels
    assert not any(lb.isdigit() for lb in labels if lb and lb != "(空)")
    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)
