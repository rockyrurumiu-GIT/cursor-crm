"""RMS dashboard and roster check API tests."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
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
    _status_transition_body,
)


def _set_application_onboarding(engine, app_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'onboarding', current_stage = 'onboarding' "
                "WHERE id = :id"
            ),
            {"id": app_id},
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
    assert "lifecycle_funnel" in body
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


def test_dashboard_filter_options_delivery_users(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import (
        _ensure_dept,
        _set_user_dept,
        _create_user,
    )

    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    assert login.status_code == 200
    suffix = uniq
    delivery_dept = 991000 + (int(suffix[:6], 16) % 10000)
    other_dept = delivery_dept + 1
    _ensure_dept(
        rms_engine,
        delivery_dept,
        f"华东交付部_{suffix}",
        path=f"ROOT/DELIVERY_{delivery_dept}",
    )
    _ensure_dept(
        rms_engine,
        other_dept,
        f"OtherDel_{suffix}",
        path=f"ROOT/OTHER_DEL_{other_dept}",
    )

    delivery_uid = _create_user(client_rbac, admin_auth, f"del_{suffix}", [ROLE_DELIVERY])
    other_uid = _create_user(client_rbac, admin_auth, f"oth_del_{suffix}", [ROLE_DELIVERY])
    _set_user_dept(rms_engine, delivery_uid, delivery_dept)
    _set_user_dept(rms_engine, other_uid, other_dept)

    r = client_rbac.get("/api/rms/dashboard/filter-options", cookies=login.cookies)
    assert r.status_code == 200, r.text
    ids = {u["id"] for u in r.json()["delivery_users"]}
    assert delivery_uid in ids
    assert other_uid not in ids


def test_dashboard_filter_options_recruitment_users(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import (
        _create_client_admin,
        _ensure_dept,
        _set_client_recruitment,
        _set_user_dept,
        _create_user,
    )

    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    assert login.status_code == 200
    suffix = uniq
    recruit_dept = 990000 + (int(suffix[:6], 16) % 10000)
    other_dept = recruit_dept + 1
    _ensure_dept(
        rms_engine,
        recruit_dept,
        f"Recruit_{suffix}",
        path=f"ROOT/RECRUIT_{recruit_dept}",
    )
    _ensure_dept(
        rms_engine,
        other_dept,
        f"Other_{suffix}",
        path=f"ROOT/OTHER_{other_dept}",
    )

    recruit_uid = _create_user(client_rbac, admin_auth, f"rec_{suffix}", [ROLE_DELIVERY])
    other_uid = _create_user(client_rbac, admin_auth, f"oth_{suffix}", [ROLE_DELIVERY])
    _set_user_dept(rms_engine, recruit_uid, recruit_dept)
    _set_user_dept(rms_engine, other_uid, other_dept)

    cid = _create_client_admin(client_rbac, admin_auth, f"DashRecruit_{suffix}")
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=recruit_dept)

    r = client_rbac.get("/api/rms/dashboard/filter-options", cookies=login.cookies)
    assert r.status_code == 200, r.text
    ids = {u["id"] for u in r.json()["recruiter_users"]}
    assert recruit_uid in ids
    assert other_uid not in ids


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
    assert "生命周期转化" in tab_names
    assert "客户岗位分析" in tab_names
    assert "招聘人效" in tab_names
    assert "花名册核对" in tab_names
    assert "Test" not in tab_names
    overview = next(t for t in boards[0]["tabs"] if t["name"] == "总览")
    assert len(overview["widgets"]) >= 4
    blocks = {(w.get("config") or {}).get("block") for w in overview["widgets"]}
    assert "kpi_resume_count" in blocks
    assert "chart_pipeline" in blocks
    assert "chart_pending_backlog" in blocks


def test_rms_dashboard_create_board_seeds_default_tabs(client_rbac, admin_auth, rms_engine, uniq):
    login = _admin_login(client_rbac, admin_auth)
    r = client_rbac.post(
        "/api/rms/dashboard-boards",
        cookies=login.cookies,
        json={"name": f"总看板_{uniq}", "description": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "rms"
    assert body["name"] == f"总看板_{uniq}"
    tab_names = [t["name"] for t in body["tabs"]]
    assert "总览" in tab_names
    assert "生命周期转化" in tab_names
    assert "客户岗位分析" in tab_names
    assert "招聘人效" in tab_names
    assert "花名册核对" in tab_names
    assert "Test" not in tab_names
    overview = next(t for t in body["tabs"] if t["name"] == "总览")
    assert len(overview["widgets"]) >= 4
    blocks = {(w.get("config") or {}).get("block") for w in overview["widgets"]}
    assert "kpi_resume_count" in blocks
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


def test_rms_preset_style_config_roundtrip(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    overview = next(t for t in boards[0]["tabs"] if t["name"] == "总览")
    tab_id = overview["id"]
    created = client_rbac.post(
        f"/api/rms/dashboard-tabs/{tab_id}/widgets",
        json={
            "title": "待处理积压",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {
                "block": "chart_pending_backlog",
                "style": {
                    "color": "blue",
                    "color_shade": 2,
                    "sort": "value_asc",
                    "chart_type": "bar",
                    "show_grid": False,
                    "bar_radius": 8,
                    "max_items": 6,
                },
            },
            "x": 0,
            "y": 30,
            "w": 4,
            "h": 6,
        },
        cookies=login.cookies,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    wid = body["id"]
    assert body["config"]["block"] == "chart_pending_backlog"
    assert body["config"]["style"]["color"] == "blue"
    assert body["config"]["style"]["color_shade"] == 2
    assert body["config"]["style"]["sort"] == "value_asc"
    assert body["config"]["style"]["chart_type"] == "bar"
    assert body["config"]["style"]["show_grid"] is False
    assert body["config"]["style"]["bar_radius"] == 8
    assert body["config"]["style"]["max_items"] == 6

    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    overview = next(t for t in boards[0]["tabs"] if t["name"] == "总览")
    saved = next(w for w in overview["widgets"] if w["id"] == wid)
    assert saved["config"]["style"]["color"] == "blue"
    assert saved["config"]["style"]["max_items"] == 6

    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_preset_style_stripped_for_non_preset_block(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    tab = _lifecycle_tab(client_rbac, login.cookies)
    created = client_rbac.post(
        f"/api/rms/dashboard-tabs/{tab['id']}/widgets",
        json={
            "title": "历史数据",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {
                "block": "table_client_job_stage",
                "style": {
                    "color": "blue",
                    "color_shade": 2,
                    "sort": "value_asc",
                    "show_grid": False,
                    "bar_radius": 99,
                    "max_items": 0,
                },
                "extra_junk": "drop-me",
            },
            "x": 0,
            "y": 30,
            "w": 12,
            "h": 6,
        },
        cookies=login.cookies,
    )
    assert created.status_code == 200, created.text
    wid = created.json()["id"]

    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    history = next(t for t in boards[0]["tabs"] if t["id"] == tab["id"])
    saved = next(w for w in history["widgets"] if w["id"] == wid)
    assert saved["config"] == {"block": "table_client_job_stage"}

    client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)


def test_rms_preset_style_clamps_invalid_values(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    overview = next(t for t in boards[0]["tabs"] if t["name"] == "总览")
    tab_id = overview["id"]
    created = client_rbac.post(
        f"/api/rms/dashboard-tabs/{tab_id}/widgets",
        json={
            "title": "招聘管道",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {
                "block": "chart_pipeline",
                "style": {
                    "color": "not_a_color",
                    "palette": "not_a_palette",
                    "sort": "bad_sort",
                    "chart_type": "not_a_chart",
                    "bar_radius": 999,
                    "max_items": 0,
                },
            },
            "x": 0,
            "y": 40,
            "w": 8,
            "h": 6,
        },
        cookies=login.cookies,
    )
    assert created.status_code == 200, created.text
    style = created.json()["config"]["style"]
    assert style["color"] == "blue"
    assert style["sort"] == "value_desc"
    assert style["chart_type"] == "horizontal_bar"
    assert style["bar_radius"] == 8
    assert style["max_items"] == 8

    client_rbac.delete(f"/api/rms/dashboard-widgets/{created.json()['id']}", cookies=login.cookies)


def test_rms_backfill_missing_client_job_table(client_rbac, admin_auth, rms_engine, uniq):
    import main as crm_main
    from services.dashboards import _dump_json, _parse_json, seed_default_dashboards

    login = _admin_login(client_rbac, admin_auth)
    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    client_job_tab = next(t for t in boards[0]["tabs"] if t["name"] == "客户岗位分析")
    table_w = next(
        (w for w in client_job_tab["widgets"] if (w.get("config") or {}).get("block") == "table_client_job_stage"),
        None,
    )
    assert table_w is not None, "seed should include table_client_job_stage"
    wid = table_w["id"]
    deleted = client_rbac.delete(f"/api/rms/dashboard-widgets/{wid}", cookies=login.cookies)
    assert deleted.status_code == 200, deleted.text

    db = crm_main.SessionLocal()
    try:
        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )

        boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
        client_job_tab = next(t for t in boards[0]["tabs"] if t["name"] == "客户岗位分析")
        blocks = {(w.get("config") or {}).get("block") for w in client_job_tab["widgets"]}
        assert "table_client_job_stage" not in blocks
        assert (client_job_tab.get("layout_json") or {}).get("widgets_locked") is True
    finally:
        tab = (
            db.query(crm_main.DashboardTab)
            .join(
                crm_main.DashboardDashboard,
                crm_main.DashboardTab.dashboard_id == crm_main.DashboardDashboard.id,
            )
            .filter(
                crm_main.DashboardDashboard.scope == "rms",
                crm_main.DashboardTab.name == "客户岗位分析",
            )
            .first()
        )
        if tab:
            layout = _parse_json(tab.layout_json or "{}", {})
            layout.pop("widgets_locked", None)
            tab.layout_json = _dump_json(layout)
            db.commit()
        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )
        db.close()


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
    assert any(b["key"] == "lifecycle_funnel" for b in body["rms_blocks"])
    addable_keys = {b["key"] for b in body["rms_blocks"]}
    for legacy_key in (
        "chart_client_job_stage_grouped",
        "chart_client_job_stage_stacked",
        "chart_client_job_stage_funnel",
        "chart_history_pass",
        "table_history",
    ):
        assert legacy_key not in addable_keys


def _lifecycle_tab(client, cookies):
    boards = client.get("/api/rms/dashboard-boards", cookies=cookies).json()
    return next(t for t in boards[0]["tabs"] if t["name"] == "生命周期转化")


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


def test_dashboard_lifecycle_funnel_respects_job_ids(client_rbac, admin_auth, rms_engine, uniq):
    login, job_a = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"lfa_{uniq}")
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
    job_c = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": job_a_body["client_id"],
            "title": f"Job C {uniq}",
            "owner_user_id": job_a_body["owner_user_id"],
            "delivery_owner_user_id": job_a_body["delivery_owner_user_id"],
        },
    )
    assert job_c.status_code == 200, job_c.text
    job_c_id = job_c.json()["id"]
    for job_id, name in (
        (job_a, "Cand A"),
        (job_b_id, "Cand B"),
        (job_c_id, "Cand C"),
    ):
        cand = client_rbac.post(
            "/api/rms/candidates",
            cookies=login.cookies,
            json=_candidate_json(job_id, name=name),
        )
        assert cand.status_code == 200, cand.text
        app = client_rbac.post(
            "/api/rms/applications",
            cookies=login.cookies,
            json={"job_id": job_id, "candidate_id": cand.json()["id"]},
        )
        assert app.status_code == 200, app.text

    all_r = client_rbac.get("/api/rms/dashboard", cookies=login.cookies)
    assert all_r.status_code == 200, all_r.text
    all_base = all_r.json()["lifecycle_funnel"]["base_count"]

    filtered_r = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_a},{job_b_id}",
        cookies=login.cookies,
    )
    assert filtered_r.status_code == 200, filtered_r.text
    filtered_base = filtered_r.json()["lifecycle_funnel"]["base_count"]
    assert filtered_base == 2
    assert filtered_base < all_base


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
    """Push before period; snapshot at date_to shows 已面试, push count excludes pre-period."""
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
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    with rms_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_application_status_history "
                "SET changed_at = :d WHERE application_id = :id"
            ),
            {"d": "2026-06-09", "id": app_id},
        )
    r = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from=2026-06-08&date_to=2026-06-10",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["pushed_resume_count"] == 0
    assert row["interview_passed"] == 1
    assert row["interviewed"] == 1


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
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    with rms_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_application_status_history "
                "SET changed_at = :d WHERE application_id = :id"
            ),
            {"d": "2026-06-09", "id": app_id},
        )
    r = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from=2026-06-08&date_to=2026-06-10",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["pushed_resume_count"] == 1
    assert row["interview_passed"] == 1
    assert row["interviewed"] == 1


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
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    row = dash_row()
    assert row["client_screen_passed"] == 1
    assert row["pending_interview"] == 0
    assert row["interviewed"] == 1
    assert row["interview_passed"] == 1
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["first_interview_passed_rate"] == "100%"
    assert row["second_interview_count"] == 0
    assert row["second_interview_passed_count"] == 0
    assert row["internal_screen_passed_rate"] == "100%"
    assert row["client_screen_passed_rate"] == "100%"
    assert row["interview_passed_rate"] == "100%"
    assert row["interview_abandoned_rate"] == "0%"

    for to_status in ("second_interview_passed", "pending_offer"):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    row = dash_row()
    assert row["pending_offer_count"] == 1
    assert row["interview_passed"] == 1
    assert row["interviewed"] == 1
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1
    assert row["second_interview_passed_rate"] == "100%"
    assert row["offer_dropped_count"] == 0
    assert row["onboarding_count"] == 0
    assert row["onboarding_lost_count"] == 0
    assert row["hired_count"] == 0

    _set_application_onboarding(rms_engine, app_id)

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
    assert row["onboarding_count"] == 0
    assert row["hired_count"] == 1
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1


def test_client_job_stage_interview_first_fail(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"if_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_failed",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 0
    assert row["first_interview_passed_rate"] == "0%"
    assert row["second_interview_count"] == 0
    assert row["second_interview_passed_count"] == 0


def test_client_job_stage_interview_first_pass_pending_second(
    client_rbac, admin_auth, rms_engine, uniq
):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"ip_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in ("scheduling_interview", "pending_first_interview", "first_interview_passed"):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["first_interview_passed_rate"] == "100%"
    assert row["second_interview_count"] == 0
    assert row["second_interview_passed_count"] == 0


def test_client_job_stage_interview_second_fail(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"sf_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_failed",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["first_interview_passed_rate"] == "100%"
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 0
    assert row["second_interview_passed_rate"] == "0%"


def test_client_job_stage_interview_second_pass(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"sp_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1
    assert row["second_interview_passed_rate"] == "100%"


def test_client_job_stage_row_fields(client_rbac, admin_auth, rms_engine, uniq):
    from services.rms_dashboard import _SUMMARY_METRIC_KEYS

    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"row_{uniq}")
    job = client_rbac.get(f"/api/rms/jobs/{job_id}", cookies=login.cookies).json()
    cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name="Row Fields"),
    )
    assert cand.status_code == 200
    app = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand.json()["id"]},
    )
    assert app.status_code == 200
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["client_id"] == job["client_id"]
    assert row["client_name"]
    assert row["job_title"]
    assert row["location"] is not None
    for key in _SUMMARY_METRIC_KEYS:
        assert key in row


def test_client_job_stage_total_equals_rows(client_rbac, admin_auth, rms_engine, uniq):
    from services.rms_dashboard import _SUMMARY_METRIC_KEYS

    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"tot_{uniq}")
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    summary = r.json()["client_job_stage_summary"]
    total = summary["total"]
    rows = summary["rows"]
    for key in _SUMMARY_METRIC_KEYS:
        row_sum = sum(int(row.get(key) or 0) for row in rows)
        assert int(total.get(key) or 0) == row_sum, key
    hc_sum = sum(int(row.get("headcount") or 0) for row in rows)
    assert int(total.get("headcount") or 0) == hc_sum


def test_client_job_stage_snapshot_scheduling_and_onboarding(
    client_rbac, admin_auth, rms_engine, uniq
):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"snap_{uniq}")
    job_id = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()["job_id"]

    def dash_row():
        r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
        assert r.status_code == 200, r.text
        return _job_row(r.json()["client_job_stage_summary"], job_id)

    tr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview", "reason": "ok"},
    )
    assert tr.status_code == 200, tr.text
    row = dash_row()
    assert row["scheduling_interview_count"] == 1
    assert row["pending_client_screen"] == 0

    for to_status in (
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text
    _set_application_onboarding(rms_engine, app_id)

    row = dash_row()
    assert row["scheduling_interview_count"] == 0
    assert row["pending_interview"] == 0
    assert row["interviewed"] == 1
    assert row["interview_passed"] == 1
    assert row["pending_offer_count"] == 0
    assert row["onboarding_count"] == 1


def test_dashboard_client_job_stage_city_filter(client_rbac, admin_auth, rms_engine, uniq):
    login, job_a = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"sh_{uniq}")
    job_a_body = client_rbac.get(f"/api/rms/jobs/{job_a}", cookies=login.cookies).json()
    patch_a = client_rbac.patch(
        f"/api/rms/jobs/{job_a}",
        cookies=login.cookies,
        json={"location": "上海"},
    )
    assert patch_a.status_code == 200, patch_a.text
    admin_user, admin_pwd = admin_auth
    job_b = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": job_a_body["client_id"],
            "title": f"Job BJ {uniq}",
            "owner_user_id": job_a_body["owner_user_id"],
            "delivery_owner_user_id": job_a_body["delivery_owner_user_id"],
            "location": "北京",
        },
    )
    assert job_b.status_code == 200, job_b.text
    job_b_id = job_b.json()["id"]
    r = client_rbac.get("/api/rms/dashboard?city=上海", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row_ids = {int(row["job_id"]) for row in r.json()["client_job_stage_summary"]["rows"]}
    assert int(job_a) in row_ids
    assert int(job_b_id) not in row_ids


def test_dashboard_forbidden_without_analytics_read(
    client_rbac, admin_auth, rms_engine, uniq, monkeypatch
):
    import main as crm_main
    from auth import policy
    from auth import service as auth_svc
    from auth.permissions import ALL_PERMISSION_CODES
    from auth.service import AuthContext

    suffix = uniq
    monkeypatch.setattr(
        policy, "generate_custom_role_code", lambda: f"CUSTOM_{suffix}_noana"
    )
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
            db, name=f"No Analytics {suffix}", description="test", actor=admin_user
        )
        perms = [p for p in ALL_PERMISSION_CODES if p != "rms.analytics.read"]
        auth_svc.set_role_permissions(
            db, role["id"], perms, actor=admin_user, actor_ctx=super_ctx
        )
        username = f"rms_noana_{suffix}"
        auth_svc.create_user(
            db,
            username=username,
            password="noana1",
            display_name="No Analytics",
            role_codes=[role["code"]],
            actor=admin_user,
            actor_ctx=super_ctx,
        )
        db.commit()
    finally:
        db.close()

    login = _login(client_rbac, username, "noana1")
    assert login.status_code == 200
    api_r = client_rbac.get("/api/rms/dashboard", cookies=login.cookies)
    assert api_r.status_code == 403
    page_r = client_rbac.get("/rms/dashboard", cookies=login.cookies)
    assert page_r.status_code == 403


def test_rms_dashboard_widget_create_client_job_stage_block(client_rbac, admin_auth, rms_engine, uniq):
    user, pwd = admin_auth
    login = _login(client_rbac, user, pwd)
    tab = _lifecycle_tab(client_rbac, login.cookies)
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


def test_rms_dashboard_default_tabs_without_test(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies)
    assert r.status_code == 200, r.text
    tab_names = [t["name"] for t in r.json()[0]["tabs"]]
    assert "Test" not in tab_names
    assert "生命周期转化" in tab_names
    assert "客户岗位分析" in tab_names


def test_rms_dashboard_lifecycle_funnel_rates(client_rbac, admin_auth, rms_engine, uniq):
    login = _delivery_login(client_rbac, admin_auth, uniq)
    r = client_rbac.get("/api/rms/dashboard", cookies=login.cookies)
    assert r.status_code == 200, r.text
    lf = r.json()["lifecycle_funnel"]
    assert "base_count" in lf
    assert "hired_count" in lf
    assert "resume_to_hire_rate" in lf
    assert lf["rows"]
    required = {
        "key", "label", "entered", "passed", "failed", "pending",
        "processed", "pass_rate", "pass_rate_value", "funnel_count",
    }
    for row in lf["rows"]:
        assert required.issubset(row.keys())
        assert row["processed"] == row["entered"] - row["pending"]


def test_lifecycle_funnel_internal_screen_entered_matches_resume_count(
    client_rbac, admin_auth, rms_engine, uniq
):
    """内审路径跳过 pending_internal_screen；漏斗「进入」应链式等于简历数。"""
    from sqlalchemy import text

    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"lfis_{uniq}")
    app_ids: list[int] = []
    for i in range(4):
        cand = client_rbac.post(
            "/api/rms/candidates",
            cookies=login.cookies,
            json=_candidate_json(job_id, name=f"Lfis {i} {uniq}"),
        )
        assert cand.status_code == 200, cand.text
        app = client_rbac.post(
            "/api/rms/applications",
            cookies=login.cookies,
            json={"job_id": job_id, "candidate_id": cand.json()["id"]},
        )
        assert app.status_code == 200, app.text
        app_ids.append(int(app.json()["id"]))

    period_day = "2026-06-14"
    with rms_engine.begin() as conn:
        for app_id in app_ids:
            conn.execute(
                text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
                {"d": period_day, "id": app_id},
            )

    for app_id in app_ids[:2]:
        r = client_rbac.post(
            f"/api/rms/applications/{app_id}/delivery-review",
            cookies=login.cookies,
            json={"result": "passed", "note": ""},
        )
        assert r.status_code == 200, r.text
    for app_id in app_ids[2:]:
        r = client_rbac.post(
            f"/api/rms/applications/{app_id}/delivery-review",
            cookies=login.cookies,
            json={"result": "failed", "note": "不符"},
        )
        assert r.status_code == 200, r.text

    with rms_engine.begin() as conn:
        for app_id in app_ids:
            conn.execute(
                text(
                    "UPDATE rms_application_status_history "
                    "SET changed_at = :d WHERE application_id = :id"
                ),
                {"d": period_day, "id": app_id},
            )

    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    lf = dash.json()["lifecycle_funnel"]
    assert lf["base_count"] == 4
    internal = next(row for row in lf["rows"] if row["key"] == "internal_screen")
    assert internal["entered"] == 4
    assert internal["passed"] == 2
    assert internal["failed"] == 2
    assert internal["processed"] == 4
    assert internal["pass_rate"] == "50.0%"

    hist_internal = next(
        s for s in dash.json()["historical_overview"][0]["stages"]
        if s["stage"] == "internal_screen"
    )
    assert hist_internal["entered"] == 0


def test_rms_dashboard_recruiter_recommended_count(client_rbac, admin_auth, rms_engine, uniq):
    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"rec_{uniq}")
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
    r = client_rbac.get("/api/rms/dashboard", cookies=login_del.cookies)
    assert r.status_code == 200, r.text
    perf = r.json()["recruiter_performance"]
    assert perf
    assert perf[0]["recommended_count"] >= 1


def test_rms_block_keys_legacy_still_valid(client_rbac, admin_auth, rms_engine, uniq):
    login = _admin_login(client_rbac, admin_auth)
    overview = _rms_overview_tab(client_rbac, login.cookies)
    created = client_rbac.post(
        f"/api/rms/dashboard-tabs/{overview['id']}/widgets",
        json={
            "title": "Legacy funnel",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {"block": "chart_client_job_stage_funnel"},
            "x": 0,
            "y": 99,
            "w": 12,
            "h": 6,
        },
        cookies=login.cookies,
    )
    assert created.status_code == 200, created.text
    client_rbac.delete(
        f"/api/rms/dashboard-widgets/{created.json()['id']}",
        cookies=login.cookies,
    )


def test_rms_dashboard_obsolete_seed_widgets_cleaned(client_rbac, admin_auth, rms_engine, uniq):
    import main as crm_main
    from services.dashboards import seed_default_dashboards

    login = _admin_login(client_rbac, admin_auth)
    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    dash_id = boards[0]["id"]
    custom_tab = client_rbac.post(
        f"/api/rms/dashboard-boards/{dash_id}/tabs",
        cookies=login.cookies,
        json={"name": f"自定义_{uniq}", "rms_template": "empty"},
    )
    assert custom_tab.status_code == 200, custom_tab.text
    tab_id = custom_tab.json()["id"]
    legacy = client_rbac.post(
        f"/api/rms/dashboard-tabs/{tab_id}/widgets",
        json={
            "title": "用户保留",
            "widget_type": "rms_block",
            "source_key": "",
            "config": {"block": "chart_client_job_stage_grouped"},
            "x": 0,
            "y": 0,
            "w": 12,
            "h": 6,
        },
        cookies=login.cookies,
    )
    assert legacy.status_code == 200, legacy.text
    legacy_id = legacy.json()["id"]

    db = crm_main.SessionLocal()
    try:
        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )
    finally:
        db.close()

    boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
    overview_blocks = {
        (w.get("config") or {}).get("block")
        for t in boards[0]["tabs"]
        if t["name"] == "总览"
        for w in t["widgets"]
    }
    assert "chart_client_job_stage_grouped" not in overview_blocks
    custom = next(t for t in boards[0]["tabs"] if t["id"] == tab_id)
    saved_blocks = {(w.get("config") or {}).get("block") for w in custom["widgets"]}
    assert "chart_client_job_stage_grouped" in saved_blocks

    client_rbac.delete(f"/api/rms/dashboard-widgets/{legacy_id}", cookies=login.cookies)
    client_rbac.delete(f"/api/rms/dashboard-tabs/{tab_id}", cookies=login.cookies)


def test_rms_dashboard_tab_ia_v2_sync(client_rbac, admin_auth, rms_engine, uniq):
    import main as crm_main
    from services.dashboards import (
        _dump_json,
        _parse_json,
        _widget_block,
        seed_default_dashboards,
    )

    login = _delivery_login(client_rbac, admin_auth, uniq)

    def tab_snapshot():
        boards = client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()
        tabs = boards[0]["tabs"]
        return [t["name"] for t in tabs], sum(
            1 for t in tabs if t["name"] == "客户岗位分析"
        )

    db = crm_main.SessionLocal()
    try:
        client_job_tab = (
            db.query(crm_main.DashboardTab)
            .join(
                crm_main.DashboardDashboard,
                crm_main.DashboardTab.dashboard_id == crm_main.DashboardDashboard.id,
            )
            .filter(
                crm_main.DashboardDashboard.scope == "rms",
                crm_main.DashboardTab.name == "客户岗位分析",
            )
            .first()
        )
        assert client_job_tab is not None
        layout = _parse_json(client_job_tab.layout_json or "{}", {})
        layout.pop("widgets_locked", None)
        client_job_tab.layout_json = _dump_json(layout)
        for w in db.query(crm_main.DashboardWidget).filter(
            crm_main.DashboardWidget.tab_id == client_job_tab.id
        ).all():
            if _widget_block(w) == "table_client_job_stage":
                db.delete(w)
        db.commit()

        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )
        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )
    finally:
        db.close()

    names, client_job_count = tab_snapshot()
    assert "生命周期转化" in names
    assert "历史转化" not in names
    assert client_job_count == 1
    client_tab = next(
        t for t in client_rbac.get("/api/rms/dashboard-boards", cookies=login.cookies).json()[0]["tabs"]
        if t["name"] == "客户岗位分析"
    )
    blocks = {(w.get("config") or {}).get("block") for w in client_tab["widgets"]}
    assert "table_client_job_stage" in blocks
    table_widgets = [
        w for w in client_tab["widgets"]
        if (w.get("config") or {}).get("block") == "table_client_job_stage"
    ]
    assert len(table_widgets) == 1


def test_dashboard_interview_metrics_exclude_rollback_to_pending_first(
    client_rbac, admin_auth, rms_engine, uniq
):
    """误点一面通过后改回待一面：已面试/面试通过不计入（当前仍在一面结果之后才计）。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"rb_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in ("scheduling_interview", "pending_first_interview", "first_interview_passed"):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["interviewed"] == 1
    assert row["interview_passed"] == 1
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    first_before = next(
        s for s in r.json()["lifecycle_funnel"]["rows"] if s["key"] == "first_interview"
    )
    assert first_before["passed"] == 1

    corr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={
            "to_status": "pending_first_interview",
            "mode": "correction",
            "note": "误点一面通过，改回待一面",
        },
    )
    assert corr.status_code == 200, corr.text

    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["interviewed"] == 0
    assert row["interview_passed"] == 0
    assert row["first_interview_count"] == 0
    assert row["first_interview_passed_count"] == 0
    assert row["second_interview_count"] == 0
    assert row["second_interview_passed_count"] == 0
    assert row["pending_interview"] == 1

    first_interview = next(
        s for s in r.json()["lifecycle_funnel"]["rows"] if s["key"] == "first_interview"
    )
    assert first_interview["passed"] == 0


def test_dashboard_interview_metrics_exclude_rollback_to_first_passed(
    client_rbac, admin_auth, rms_engine, uniq
):
    """误点二面通过后改回待二面：二面字段归零，一面字段保留。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"rb2_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1

    corr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={
            "to_status": "first_interview_passed",
            "mode": "correction",
            "note": "误点二面通过，改回待二面",
        },
    )
    assert corr.status_code == 200, corr.text

    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["second_interview_count"] == 0
    assert row["second_interview_passed_count"] == 0
    assert row["pending_second_interview"] == 1


def test_rms_dashboard_metrics_6a2b(client_rbac, admin_auth, rms_engine, uniq):
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"hc_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    close = client_rbac.patch(
        f"/api/rms/jobs/{job_id}",
        cookies=login.cookies,
        json={"status": "closed"},
    )
    assert close.status_code == 200, close.text
    r = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    row = _job_row(r.json()["client_job_stage_summary"], job_id)
    assert row["headcount"] == 0
    assert "pending_roster_conversion_count" in row

    page = client_rbac.get("/rms/dashboard", cookies=login.cookies)
    assert page.status_code == 200, page.text
    assert "pending_roster_conversion_count" not in page.text
    assert "待转花名册" not in page.text


def test_lifecycle_client_screen_pass_includes_later_status_without_scheduling(
    client_rbac, admin_auth, rms_engine, uniq
):
    """周期内到达 pending_first_interview 及之后（无 scheduling_interview 历史）仍计客筛通过。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lcsp_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-27"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_client_screen', 'pending_first_interview', "
                "'status_correction', '补录待一面', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'pending_first_interview', "
                "current_stage = 'pending_first_interview' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    client_screen = next(
        row for row in dash.json()["lifecycle_funnel"]["rows"] if row["key"] == "client_screen"
    )
    assert client_screen["passed"] == 1


def test_lifecycle_scheduling_pass_includes_later_status_without_pending_first(
    client_rbac, admin_auth, rms_engine, uniq
):
    """周期内到达 onboarding 等（无 pending_first_interview 历史）仍计约面成功。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lssp_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-27"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_client_screen', 'onboarding', "
                "'status_correction', '补录在途', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'onboarding', "
                "current_stage = 'onboarding' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    scheduling = next(
        row for row in dash.json()["lifecycle_funnel"]["rows"] if row["key"] == "scheduling"
    )
    assert scheduling["passed"] == 1


def test_lifecycle_first_interview_pass_includes_later_status_without_first_passed(
    client_rbac, admin_auth, rms_engine, uniq
):
    """周期内到达 onboarding 等（无 first_interview_passed 历史）仍计一面通过。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lfip_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-27"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_first_interview', 'onboarding', "
                "'status_correction', '补录在途', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'onboarding', "
                "current_stage = 'onboarding' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    first_interview = next(
        row for row in dash.json()["lifecycle_funnel"]["rows"] if row["key"] == "first_interview"
    )
    assert first_interview["passed"] == 1


def test_client_job_stage_first_interview_count_aligns_with_pass_after_skip(
    client_rbac, admin_auth, rms_engine, uniq
):
    """修正跳过 first_interview_passed 但已到二面：一面数与一面通过均计入。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"fics_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-27"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_client_screen', 'second_interview_passed', "
                "'status_correction', '补录二面通过', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'second_interview_passed', "
                "current_stage = 'second_interview_passed' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["first_interview_count"] == 1
    assert row["first_interview_passed_count"] == 1
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1


def test_lifecycle_second_interview_pass_includes_later_status_without_second_passed(
    client_rbac, admin_auth, rms_engine, uniq
):
    """周期内到达 onboarding 等（无 second_interview_passed 历史）仍计二面通过。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lsip_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-27"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'first_interview_passed', 'onboarding', "
                "'status_correction', '补录在途', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'onboarding', "
                "current_stage = 'onboarding' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    second_interview = next(
        row for row in dash.json()["lifecycle_funnel"]["rows"] if row["key"] == "second_interview"
    )
    assert second_interview["passed"] == 1
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1


def test_client_job_stage_second_interview_count_aligns_with_pass_after_skip(
    client_rbac, admin_auth, rms_engine, uniq
):
    """修正跳过 second_interview_passed 但已到在途：二面数与二面通过均计入。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"sics_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-27"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'first_interview_passed', 'onboarding', "
                "'status_correction', '补录在途', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'onboarding', "
                "current_stage = 'onboarding' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["second_interview_count"] == 1
    assert row["second_interview_passed_count"] == 1


def test_client_job_stage_loss_metrics_include_candidate_names(
    client_rbac, admin_auth, rms_engine, uniq
):
    """放弃面试/弃offer/在途流失单元格附带统计到的人员姓名。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    suffix = f"loss_{uniq}"
    cand_name = f"Cand {suffix}"
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, suffix)
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-28"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'first_interview_passed', 'second_interview_abandoned', "
                "'transition', '二面弃面', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_offer', 'offer_dropped', "
                "'offer_dropped', '弃offer', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'onboarding', 'onboarding_lost', "
                "'onboarding_lost', '在途流失', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["interview_abandoned"] == 1
    assert row["interview_abandoned_names"] == [cand_name]
    assert row["offer_dropped_count"] == 1
    assert row["offer_dropped_names"] == [cand_name]
    assert row["onboarding_lost_count"] == 1
    assert row["onboarding_lost_names"] == [cand_name]
    total = dash.json()["client_job_stage_summary"]["total"]
    assert cand_name in total["interview_abandoned_names"]
    assert cand_name in total["offer_dropped_names"]
    assert cand_name in total["onboarding_lost_names"]


def test_lifecycle_offer_pass_includes_onboarding_lost(
    client_rbac, admin_auth, rms_engine, uniq
):
    """在途流失仍计接 offer（已进在途后才流失）；弃 offer 不计。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"loil_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-29"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_offer', 'onboarding', "
                "'transition', '接offer进在途', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'onboarding', 'onboarding_lost', "
                "'onboarding_lost', '在途流失', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'onboarding_lost', "
                "current_stage = 'onboarding_lost' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    by_key = {s["key"]: s for s in dash.json()["lifecycle_funnel"]["rows"]}
    assert by_key["offer"]["passed"] == 1
    assert by_key["offer"]["failed"] == 0


def test_lifecycle_offer_pass_excludes_offer_dropped(
    client_rbac, admin_auth, rms_engine, uniq
):
    """弃 offer 不计接 offer。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"loed_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    period_day = "2026-06-29"
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_at = :d WHERE id = :id"),
            {"d": period_day, "id": app_id},
        )
        conn.execute(
            text(
                "INSERT INTO rms_application_status_history "
                "(application_id, from_status, to_status, reason, note, changed_by, changed_at) "
                "VALUES (:app_id, 'pending_offer', 'offer_dropped', "
                "'offer_dropped', '弃offer', 1, :d)"
            ),
            {"app_id": app_id, "d": period_day},
        )
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'offer_dropped', "
                "current_stage = 'offer_dropped' WHERE id = :id"
            ),
            {"id": app_id},
        )
    dash = client_rbac.get(
        f"/api/rms/dashboard?job_ids={job_id}&date_from={period_day}&date_to={period_day}",
        cookies=login.cookies,
    )
    assert dash.status_code == 200, dash.text
    by_key = {s["key"]: s for s in dash.json()["lifecycle_funnel"]["rows"]}
    assert by_key["offer"]["passed"] == 0
    assert by_key["offer"]["failed"] == 1


def test_lifecycle_second_interview_pass_excludes_rollback_to_prior_status(
    client_rbac, admin_auth, rms_engine, uniq
):
    """曾到二面及之后但当前改回待一面/二面 fail：不计二面通过。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lsre_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    corr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={
            "to_status": "pending_first_interview",
            "mode": "correction",
            "note": "误操作改回待一面",
        },
    )
    assert corr.status_code == 200, corr.text

    dash = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert dash.status_code == 200, dash.text
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["second_interview_passed_count"] == 0
    second_interview = next(
        s for s in dash.json()["lifecycle_funnel"]["rows"] if s["key"] == "second_interview"
    )
    assert second_interview["passed"] == 0


def test_lifecycle_hired_pass_requires_current_hired_status(
    client_rbac, admin_auth, rms_engine, uniq
):
    """曾到 hired 但当前改回在途：不计已入职。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lhr_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    _set_application_onboarding(rms_engine, app_id)
    tr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "reason": "ok", "hired_at": "2026-06-01"},
    )
    assert tr.status_code == 200, tr.text

    corr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={
            "to_status": "onboarding",
            "mode": "correction",
            "note": "误操作改回在途",
        },
    )
    assert corr.status_code == 200, corr.text

    dash = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert dash.status_code == 200, dash.text
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["hired_count"] == 0
    assert row["onboarding_count"] == 1
    hired_summary = next(
        s for s in dash.json()["lifecycle_funnel"]["rows"] if s["key"] == "hired_summary"
    )
    assert hired_summary["passed"] == 0
    assert hired_summary["pending"] == 1


def test_lifecycle_stage_pass_excludes_rollback_to_prior_status(
    client_rbac, admin_auth, rms_engine, uniq
):
    """改回前序节点后，各阶段通过数均不计（以当前进展为准）。"""
    from tests.test_rms_phase2_mvp import _app_for_status

    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, f"lsp_{uniq}")
    job_id = client_rbac.get(
        f"/api/rms/applications/{app_id}", cookies=login.cookies
    ).json()["job_id"]
    for to_status in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
    ):
        tr = client_rbac.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json=_status_transition_body(to_status, reason="ok"),
        )
        assert tr.status_code == 200, tr.text

    corr = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={
            "to_status": "pending_client_screen",
            "mode": "correction",
            "note": "误操作改回待客筛",
        },
    )
    assert corr.status_code == 200, corr.text

    dash = client_rbac.get(f"/api/rms/dashboard?job_ids={job_id}", cookies=login.cookies)
    assert dash.status_code == 200, dash.text
    row = _job_row(dash.json()["client_job_stage_summary"], job_id)
    assert row["client_screen_passed"] == 0
    assert row["first_interview_passed_count"] == 0
    assert row["second_interview_passed_count"] == 0
    by_key = {s["key"]: s for s in dash.json()["lifecycle_funnel"]["rows"]}
    assert by_key["client_screen"]["passed"] == 0
    assert by_key["scheduling"]["passed"] == 0
    assert by_key["first_interview"]["passed"] == 0
    assert by_key["second_interview"]["passed"] == 0
    assert by_key["final_interview"]["passed"] == 0
    assert by_key["offer"]["passed"] == 0
