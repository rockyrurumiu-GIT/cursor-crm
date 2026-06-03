"""Dashboard builder module tests."""
from __future__ import annotations

import importlib
import json
import os

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.helpers import auth_header


@pytest.fixture(scope="module")
def client_rbac(_test_env):
    os.environ["CRM_AUTH_MODE"] = "rbac"
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _admin_headers(admin_auth):
    user, pwd = admin_auth
    return auth_header(user, pwd)


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_restricted(client, admin_auth, suffix: str):
    user, pwd = admin_auth
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    username = f"dash_rbac_{suffix}"
    r = client.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": username,
            "password": "restricted1",
            "display_name": "Dash Restricted",
            "role_codes": ["RESTRICTED"],
        },
    )
    if r.status_code == 400 and "已存在" in r.text:
        return username, "restricted1"
    assert r.status_code == 200, r.text
    return username, "restricted1"


def _create_dashboard_only_role(admin_auth, suffix: str):
    """Create role with only dashboard.read and a user assigned to it (via service layer)."""
    import main as crm_main
    from auth import service as auth_svc
    from auth.permissions import ALL_PERMISSION_CODES
    from auth.service import AuthContext

    user, pwd = admin_auth
    db = crm_main.SessionLocal()
    try:
        super_ctx = AuthContext(
            username=user,
            user_id=1,
            roles=["SUPER_ADMIN"],
            permissions=sorted(ALL_PERMISSION_CODES),
            dept_ids=[],
            role_data_scopes={},
            is_super=True,
        )
        role = auth_svc.create_custom_role(
            db, name=f"Dashboard Only {suffix}", description="test", actor=user
        )
        auth_svc.set_role_permissions(db, role["id"], ["dashboard.read"], actor=user, actor_ctx=super_ctx)
        username = f"dash_only_{suffix}"
        try:
            auth_svc.create_user(
                db,
                username=username,
                password="dashonly1",
                display_name="Dash Only",
                role_codes=[role["code"]],
                actor=user,
                actor_ctx=super_ctx,
            )
        except ValueError as e:
            if "已存在" not in str(e):
                raise
        db.commit()
        return username, "dashonly1"
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def test_seed_default_dashboard_exists(client, admin_auth):
    headers = _admin_headers(admin_auth)
    r = client.get("/api/dashboards", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) >= 1
    names = [d["name"] for d in data]
    assert "经营总览" in names


def test_admin_create_dashboard_tab_widgets(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    r = client.post("/api/dashboards", headers=headers, json={"name": "Test Dash", "description": "t"})
    assert r.status_code == 200, r.text
    dash_id = r.json()["id"]

    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "Tab1"})
    assert r.status_code == 200, r.text
    tab_id = r.json()["id"]

    for wt, cfg, sk in [
        ("number", {"metric": "count"}, "clients"),
        ("bar", {"metric": "count", "group_by": "phase", "limit": 5}, "clients"),
        ("pie", {"metric": "count", "group_by": "stage", "limit": 5}, "opportunities"),
        ("line", {"metric": "count", "group_by": "status", "limit": 5}, "handoff_requests"),
        ("rich_text", {"content": "Hello dashboard"}, ""),
        ("iframe", {"url": "https://example.com"}, ""),
    ]:
        body = {
            "title": f"Widget {wt}",
            "widget_type": wt,
            "source_key": sk,
            "config": cfg,
            "x": 0, "y": 0, "w": 4, "h": 3,
        }
        r = client.post(f"/api/dashboard-tabs/{tab_id}/widgets", headers=headers, json=body)
        assert r.status_code == 200, f"{wt}: {r.text}"

    listed = client.get("/api/dashboards", headers=headers)
    assert listed.status_code == 200
    dash = next(d for d in listed.json() if d["id"] == dash_id)
    assert len(dash["tabs"]) == 1
    assert len(dash["tabs"][0]["widgets"]) == 6

    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_restricted_forbidden_dashboard_list(client_rbac, admin_auth):
    suffix = str(os.getpid())
    username, pwd = _create_restricted(client_rbac, admin_auth, suffix)
    login = _login(client_rbac, username, pwd)
    assert login.status_code == 200
    r = client_rbac.get("/api/dashboards", cookies=login.cookies)
    assert r.status_code == 403
    assert "dashboard.read" in r.json().get("detail", "")


def test_widget_data_forbidden_without_source_permission(client, client_rbac, admin_auth):
    suffix = str(os.getpid())
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}

    # Setup with non-rbac client (admin has implicit full access)
    r = client.post("/api/dashboards", headers=headers, json={"name": f"Perm Dash {suffix}"})
    assert r.status_code == 200, r.text
    dash_id = r.json()["id"]
    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"})
    tab_id = r.json()["id"]
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "Clients count",
            "widget_type": "number",
            "source_key": "clients",
            "config": {"metric": "count"},
        },
    )
    widget_id = r.json()["id"]

    username, pwd_only = _create_dashboard_only_role(admin_auth, suffix)
    login = _login(client_rbac, username, pwd_only)
    assert login.status_code == 200
    r = client_rbac.get(f"/api/dashboard-widgets/{widget_id}/data", cookies=login.cookies)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "forbidden"
    assert "value" not in data
    assert "display" not in data

    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


@pytest.mark.parametrize(
    "payload,detail_part",
    [
        ({"title": "Bad", "widget_type": "number", "source_key": "unknown_src", "config": {"metric": "count"}}, "未知数据源"),
        ({"title": "Bad", "widget_type": "number", "source_key": "clients", "config": {"metric": "sum", "field": "bad_field"}}, "bad_field"),
        ({"title": "Bad", "widget_type": "bar", "source_key": "clients", "config": {"metric": "count", "group_by": "bad_col", "limit": 5}}, "未知分组字段"),
    ],
)
def test_invalid_widget_config_returns_400(client, admin_auth, payload, detail_part):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    r = client.post("/api/dashboards", headers=headers, json={"name": "Invalid Config Dash"})
    dash_id = r.json()["id"]
    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"})
    tab_id = r.json()["id"]
    r = client.post(f"/api/dashboard-tabs/{tab_id}/widgets", headers=headers, json=payload)
    assert r.status_code == 400
    assert detail_part in r.json().get("detail", "")
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "file:///etc/passwd", "http://example.com", "<script>"],
)
def test_iframe_rejects_invalid_urls(client, admin_auth, url):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    r = client.post("/api/dashboards", headers=headers, json={"name": "Iframe Dash"})
    dash_id = r.json()["id"]
    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"})
    tab_id = r.json()["id"]
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={"title": "Iframe", "widget_type": "iframe", "source_key": "", "config": {"url": url}},
    )
    assert r.status_code == 400
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_delete_dashboard_cascades_tabs_widgets(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    import main as crm_main

    r = client.post("/api/dashboards", headers=headers, json={"name": "Cascade Dash"})
    dash_id = r.json()["id"]
    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"})
    tab_id = r.json()["id"]
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={"title": "W", "widget_type": "number", "source_key": "clients", "config": {"metric": "count"}},
    )
    widget_id = r.json()["id"]

    r = client.delete(f"/api/dashboards/{dash_id}", headers=headers)
    assert r.status_code == 200

    with crm_main.engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM dashboard_dashboards WHERE id = :id"), {"id": dash_id}).fetchone() is None
        assert conn.execute(text("SELECT id FROM dashboard_tabs WHERE id = :id"), {"id": tab_id}).fetchone() is None
        assert conn.execute(text("SELECT id FROM dashboard_widgets WHERE id = :id"), {"id": widget_id}).fetchone() is None


def test_dashboard_metadata(client, admin_auth):
    headers = _admin_headers(admin_auth)
    r = client.get("/api/dashboard-metadata", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "clients" in [s["key"] for s in data["sources"]]
    assert "number" in data["widget_types"]
    assert "horizontal_bar" in data["widget_types"]
    assert data["widget_types"].index("horizontal_bar") < data["widget_types"].index("pie")
    assert "count" in data["metrics"]
    # Twenty-parity style metadata.
    assert "blue" in data["colors"]
    assert "jade" in data["colors"]
    assert data["colors"][0] == "red"
    assert data["color_shades"] == [0, 1, 2, 3, 4]
    assert "value_desc" in data["sorts"]
    assert "doughnut" in data["chart_extra_renders"]
    assert "horizontal_bar" in data["chart_extra_renders"]


def _make_tab(client, headers, name):
    r = client.post("/api/dashboards", headers=headers, json={"name": name})
    dash_id = r.json()["id"]
    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"})
    return dash_id, r.json()["id"]


@pytest.mark.parametrize(
    "bad_config,detail_part",
    [
        ({"metric": "count", "group_by": "stage", "color": "rainbow"}, "未知配色"),
        ({"metric": "count", "group_by": "stage", "color": "blue", "color_shade": 9}, "color_shade"),
        ({"metric": "count", "group_by": "stage", "sort": "random"}, "未知排序"),
    ],
)
def test_invalid_style_returns_400(client, admin_auth, bad_config, detail_part):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Style Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={"title": "W", "widget_type": "pie", "source_key": "opportunities", "config": bad_config},
    )
    assert r.status_code == 400
    assert detail_part in r.json().get("detail", "")
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_chart_color_jade_and_shade_saves(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Color Jade Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "Jade chart",
            "widget_type": "bar",
            "source_key": "opportunities",
            "config": {
                "metric": "count",
                "group_by": "stage",
                "color": "jade",
                "color_shade": 4,
            },
        },
    )
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert cfg["color"] == "jade"
    assert cfg["color_shade"] == 4
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


@pytest.mark.parametrize(
    "bad_extra,detail_part",
    [
        ([{"render": "invalid", "x": 0, "y": 0, "w": 6, "h": 6}], "extra_views.render"),
        ([{"render": "doughnut", "x": 12, "y": 0, "w": 6, "h": 6}], "extra_views.x"),
        ([{"render": "horizontal_bar", "x": 0, "y": 0, "w": 0, "h": 6}], "extra_views.w"),
    ],
)
def test_invalid_extra_views_returns_400(client, admin_auth, bad_extra, detail_part):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Extra Views Bad")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "GM",
            "widget_type": "bar",
            "source_key": "opportunities",
            "config": {
                "metric": "count",
                "group_by": "stage",
                "extra_views": bad_extra,
            },
        },
    )
    assert r.status_code == 400
    assert detail_part in r.json().get("detail", "")
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_horizontal_bar_primary_widget_type(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "HBar Primary")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "阶段排名",
            "widget_type": "horizontal_bar",
            "source_key": "opportunities",
            "config": {"metric": "count", "group_by": "stage", "limit": 10},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["widget_type"] == "horizontal_bar"
    assert body["config"]["limit"] == 10
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_extra_views_persist_round_trip(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Extra Views OK")
    extra = [
        {"render": "doughnut", "x": 6, "y": 0, "w": 6, "h": 6, "title": "环形"},
        {"render": "horizontal_bar", "x": 0, "y": 6, "w": 6, "h": 5, "limit": 8},
    ]
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "By client",
            "widget_type": "bar",
            "source_key": "opportunities",
            "config": {
                "metric": "count",
                "group_by": "stage",
                "extra_views": extra,
            },
        },
    )
    assert r.status_code == 200, r.text
    cfg = r.json()["config"]
    assert len(cfg["extra_views"]) == 2
    assert cfg["extra_views"][0]["render"] == "doughnut"
    assert cfg["extra_views"][0]["title"] == "环形"
    assert cfg["extra_views"][1]["limit"] == 8

    listed = client.get("/api/dashboards", headers=headers).json()
    dash = next(d for d in listed if d["id"] == dash_id)
    tab = next(t for t in dash["tabs"] if t["id"] == tab_id)
    w = next(x for x in tab["widgets"] if x["title"] == "By client")
    assert w["config"]["extra_views"] == cfg["extra_views"]
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_chart_color_shade_defaults_to_2(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Color Default Shade Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "Legacy color",
            "widget_type": "pie",
            "source_key": "opportunities",
            "config": {"metric": "count", "group_by": "stage", "color": "blue"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["config"]["color"] == "blue"
    assert r.json()["config"]["color_shade"] == 2
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_series_returns_total_and_respects_hide_empty(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Series Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "By stage",
            "widget_type": "pie",
            "source_key": "opportunities",
            "config": {"metric": "count", "group_by": "stage", "hide_empty": True, "sort": "value_desc"},
        },
    )
    assert r.status_code == 200, r.text
    widget_id = r.json()["id"]
    r = client.get(f"/api/dashboard-widgets/{widget_id}/data", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert data["kind"] == "series"
    assert "total" in data
    assert data["total"] == sum(data["values"])
    # hide_empty drops zero-valued buckets.
    assert all(v != 0 for v in data["values"])
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


@pytest.mark.parametrize("op", ["eq", "in", "contains"])
def test_filters_eq_in_contains(client, admin_auth, op):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, f"Filter Dash {op}")
    value = "勘察,签约" if op == "in" else "签约"
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "Filtered",
            "widget_type": "number",
            "source_key": "opportunities",
            "config": {"metric": "count", "filters": [{"field": "stage", "op": op, "value": value}]},
        },
    )
    assert r.status_code == 200, r.text
    widget_id = r.json()["id"]
    r = client.get(f"/api/dashboard-widgets/{widget_id}/data", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def _make_roster_client(name: str, rows: list):
    """Insert a Client + roster entries directly. rows: list of (quote, salary, gms, status)."""
    import main as crm_main

    db = crm_main.SessionLocal()
    try:
        c = crm_main.Client(name=name)
        db.add(c)
        db.flush()
        for quote, salary, gms, status in rows:
            db.add(crm_main.RosterEntry(
                client_id=c.id,
                monthly_quote_tax=quote,
                pre_tax_salary=salary,
                gms=gms,
                employment_status=status,
            ))
        db.commit()
        return c.id
    finally:
        db.close()


def _roster_summary_widget(client, headers, title, config):
    dash_id, tab_id = _make_tab(client, headers, title + " Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={"title": title, "widget_type": "roster_summary", "source_key": "roster_entries", "config": config},
    )
    assert r.status_code == 200, r.text
    return dash_id, r.json()["id"]


def test_roster_summary_overall_and_client_scope(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    cid = _make_roster_client(
        f"RosterCo-{os.getpid()}",
        [("23320", "11000", "7695", "在职"), ("22000", "17500", "1515", ""), ("9700", "6500", "893", "已离职")],
    )

    # All clients, active pool (excludes 离职): revenue 45320, salary 28500, gms 9210.
    dash_id, wid = _roster_summary_widget(client, headers, "All", {})
    data = client.get(f"/api/dashboard-widgets/{wid}/data", headers=headers).json()
    assert data["status"] == "ok" and data["kind"] == "roster_summary"
    assert data["scope"] == "all"
    assert data["revenue"]["value"] == pytest.approx(45320)
    assert data["salary"]["value"] == pytest.approx(28500)
    assert data["gms"]["value"] == pytest.approx(9210)
    expected_gm = 9210 / (45320 / 1.0672) * 100
    assert data["gm_pct"]["value"] == pytest.approx(expected_gm)
    assert data["headcount"] == 2
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)

    # Client-scoped returns same client name.
    dash_id2, wid2 = _roster_summary_widget(client, headers, "One", {"client_id": cid})
    d2 = client.get(f"/api/dashboard-widgets/{wid2}/data", headers=headers).json()
    assert d2["scope"] == "client" and d2["client_id"] == cid
    assert d2["revenue"]["value"] == pytest.approx(45320)
    client.delete(f"/api/dashboards/{dash_id2}", headers=headers)


def test_roster_summary_include_left_flips_active_pool(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    cid = _make_roster_client(
        f"RosterLeft-{os.getpid()}",
        [("10000", "5000", "1000", "在职"), ("8000", "4000", "800", "已离职")],
    )
    # Default active-only excludes 离职; include_left adds it back. Compare GM$ sums.
    dash_id, wid = _roster_summary_widget(client, headers, "Active", {"client_id": cid})
    active = client.get(f"/api/dashboard-widgets/{wid}/data", headers=headers).json()
    dash_id2, wid2 = _roster_summary_widget(client, headers, "WithLeft", {"client_id": cid, "include_left": True})
    withleft = client.get(f"/api/dashboard-widgets/{wid2}/data", headers=headers).json()
    assert active["headcount"] == 1
    assert withleft["headcount"] == 2
    assert withleft["gms"]["value"] > active["gms"]["value"]
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)
    client.delete(f"/api/dashboards/{dash_id2}", headers=headers)


def test_roster_summary_forbidden_without_roster_permission(client, client_rbac, admin_auth):
    suffix = "rs" + str(os.getpid())
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    _make_roster_client(f"RosterPerm-{os.getpid()}", [("10000", "5000", "1000", "在职")])
    dash_id, wid = _roster_summary_widget(client, headers, "Perm", {})

    username, pwd = _create_dashboard_only_role(admin_auth, suffix)
    login = _login(client_rbac, username, pwd)
    assert login.status_code == 200
    r = client_rbac.get(f"/api/dashboard-widgets/{wid}/data", cookies=login.cookies)
    assert r.status_code == 200
    assert r.json()["status"] == "forbidden"
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_roster_bar_group_by_client(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    name = f"RosterBar-{os.getpid()}"
    _make_roster_client(name, [("10000", "5000", "1000", "在职"), ("20000", "9000", "2000", "在职")])
    dash_id, tab_id = _make_tab(client, headers, "Bar Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "各客户月报价",
            "widget_type": "bar",
            "source_key": "roster_entries",
            "config": {"metric": "sum", "field": "monthly_quote_tax", "group_by": "client", "limit": 20},
        },
    )
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    data = client.get(f"/api/dashboard-widgets/{wid}/data", headers=headers).json()
    assert data["status"] == "ok" and data["kind"] == "series"
    assert name in data["labels"]
    idx = data["labels"].index(name)
    assert data["values"][idx] == pytest.approx(30000)
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_roster_pie_excludes_left_by_default(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    name = f"RosterPie-{os.getpid()}"
    _make_roster_client(
        name,
        [("10000", "5000", "1000", "在职"), ("8000", "4000", "800", "已离职")],
    )
    dash_id, tab_id = _make_tab(client, headers, "Pie Dash")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "按客户人数",
            "widget_type": "pie",
            "source_key": "roster_entries",
            "config": {"metric": "count", "group_by": "client", "limit": 20},
        },
    )
    assert r.status_code == 200, r.text
    wid = r.json()["id"]
    data = client.get(f"/api/dashboard-widgets/{wid}/data", headers=headers).json()
    assert data["status"] == "ok" and data["kind"] == "series"
    idx = data["labels"].index(name)
    assert data["values"][idx] == pytest.approx(1)

    r2 = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={
            "title": "含离职",
            "widget_type": "pie",
            "source_key": "roster_entries",
            "config": {"metric": "count", "group_by": "client", "limit": 20, "include_left": True},
        },
    )
    assert r2.status_code == 200, r2.text
    wid2 = r2.json()["id"]
    data2 = client.get(f"/api/dashboard-widgets/{wid2}/data", headers=headers).json()
    idx2 = data2["labels"].index(name)
    assert data2["values"][idx2] == pytest.approx(2)
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_roster_clients_endpoint(client, admin_auth):
    headers = _admin_headers(admin_auth)
    name = f"RosterList-{os.getpid()}"
    _make_roster_client(name, [("10000", "5000", "1000", "在职")])
    r = client.get("/api/dashboard/roster-clients", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert name in [c["name"] for c in data["clients"]]


def test_roster_summary_rejects_wrong_source(client, admin_auth):
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    dash_id, tab_id = _make_tab(client, headers, "Wrong Src")
    r = client.post(
        f"/api/dashboard-tabs/{tab_id}/widgets",
        headers=headers,
        json={"title": "X", "widget_type": "roster_summary", "source_key": "clients", "config": {}},
    )
    assert r.status_code == 400
    assert "花名册" in r.json().get("detail", "")
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)


def test_seed_roster_margin_dashboard_exists(client, admin_auth):
    headers = _admin_headers(admin_auth)
    r = client.get("/api/dashboards", headers=headers)
    assert r.status_code == 200
    assert "交付毛利总览" in [d["name"] for d in r.json()]


def test_roster_margin_preset_layout_sync(client, admin_auth):
    """Sync adds missing presets and preserves user layout/config; backfills extra_views on GM bar."""
    import main as crm_main
    from services.dashboards import (
        _ROSTER_SEED_NAME,
        _roster_margin_preset_specs,
        seed_default_dashboards,
    )

    db = crm_main.SessionLocal()
    try:
        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )

        d = (
            db.query(crm_main.DashboardDashboard)
            .filter(
                crm_main.DashboardDashboard.name == _ROSTER_SEED_NAME,
                crm_main.DashboardDashboard.created_by == "system",
            )
            .first()
        )
        assert d is not None

        tab = (
            db.query(crm_main.DashboardTab)
            .filter(
                crm_main.DashboardTab.dashboard_id == d.id,
                crm_main.DashboardTab.name == "毛利总览",
            )
            .first()
        )
        assert tab is not None

        bar_quote = (
            db.query(crm_main.DashboardWidget)
            .filter(
                crm_main.DashboardWidget.tab_id == tab.id,
                crm_main.DashboardWidget.title == "各客户月报价(含税)",
                crm_main.DashboardWidget.widget_type == "bar",
                crm_main.DashboardWidget.source_key == "roster_entries",
            )
            .one()
        )
        bar_quote_id = bar_quote.id
        bar_quote.w = 4
        bar_quote.h = 5
        cfg = json.loads(bar_quote.config_json or "{}")
        cfg["data_labels"] = True
        cfg["color"] = "purple"
        cfg["limit"] = 99
        bar_quote.config_json = json.dumps(cfg, ensure_ascii=False)

        single_client = (
            db.query(crm_main.DashboardWidget)
            .filter(
                crm_main.DashboardWidget.tab_id == tab.id,
                crm_main.DashboardWidget.title == "单客户毛利概览",
                crm_main.DashboardWidget.widget_type == "roster_summary",
                crm_main.DashboardWidget.source_key == "roster_entries",
            )
            .one()
        )
        single_client_id = single_client.id
        sc_cfg = json.loads(single_client.config_json or "{}")
        sc_cfg["client_id"] = 424242
        single_client.config_json = json.dumps(sc_cfg, ensure_ascii=False)

        legacy_pie = crm_main.DashboardWidget(
            tab_id=tab.id,
            title="单客户毛利概览",
            widget_type="pie",
            source_key="roster_entries",
            config_json='{"metric": "count", "group_by": "client"}',
            x=4,
            y=0,
            w=4,
            h=5,
            sort_order=50,
        )
        copy_w = crm_main.DashboardWidget(
            tab_id=tab.id,
            title="单客户毛利概览 副本",
            widget_type="number",
            source_key="clients",
            config_json='{"metric": "count"}',
            x=4,
            y=5,
            w=4,
            h=5,
            sort_order=51,
        )
        user_w = crm_main.DashboardWidget(
            tab_id=tab.id,
            title="用户自定义",
            widget_type="number",
            source_key="clients",
            config_json='{"metric": "count"}',
            x=0,
            y=12,
            w=4,
            h=4,
            sort_order=99,
        )
        db.add(legacy_pie)
        db.add(copy_w)
        db.add(user_w)
        db.commit()
        pie_id = legacy_pie.id
        copy_id = copy_w.id
        user_w_id = user_w.id

        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )
        db.expire_all()

        seed_default_dashboards(
            db,
            crm_main.DashboardDashboard,
            crm_main.DashboardTab,
            crm_main.DashboardWidget,
        )
        db.expire_all()

        specs = _roster_margin_preset_specs(None)
        for spec in specs:
            matches = (
                db.query(crm_main.DashboardWidget)
                .filter(
                    crm_main.DashboardWidget.tab_id == tab.id,
                    crm_main.DashboardWidget.title == spec["title"],
                    crm_main.DashboardWidget.widget_type == spec["widget_type"],
                    crm_main.DashboardWidget.source_key == spec["source_key"],
                )
                .all()
            )
            assert len(matches) == 1, spec

        bar_quote = db.query(crm_main.DashboardWidget).filter_by(id=bar_quote_id).one()
        assert bar_quote.w == 4 and bar_quote.h == 5
        synced = json.loads(bar_quote.config_json or "{}")
        assert synced["data_labels"] is False
        assert synced["color"] == "purple"
        assert synced["limit"] == 99

        single_client = db.query(crm_main.DashboardWidget).filter_by(id=single_client_id).one()
        assert json.loads(single_client.config_json or "{}")["client_id"] == 424242

        gm_bar = (
            db.query(crm_main.DashboardWidget)
            .filter(
                crm_main.DashboardWidget.tab_id == tab.id,
                crm_main.DashboardWidget.title == "各客户 GM$",
                crm_main.DashboardWidget.widget_type == "bar",
            )
            .one()
        )
        assert gm_bar.h == 5

        pie = db.query(crm_main.DashboardWidget).filter_by(id=pie_id).one()
        copy_row = db.query(crm_main.DashboardWidget).filter_by(id=copy_id).one()
        assert pie.y == 0
        assert copy_row.y == 5

        assert db.query(crm_main.DashboardWidget).filter_by(id=user_w_id).count() == 1
        assert db.query(crm_main.DashboardWidget).filter_by(id=pie_id).count() == 1
        assert db.query(crm_main.DashboardWidget).filter_by(id=copy_id).count() == 1
    finally:
        db.close()


def test_legacy_widget_without_style_still_renders(client, admin_auth):
    """Widgets created before style fields existed must still query without error."""
    headers = {**_admin_headers(admin_auth), "Content-Type": "application/json"}
    import main as crm_main

    dash_id, tab_id = _make_tab(client, headers, "Legacy Dash")
    # Write a widget straight to the DB with a minimal pre-style config_json.
    db = crm_main.SessionLocal()
    try:
        w = crm_main.DashboardWidget(
            tab_id=tab_id,
            title="Legacy",
            widget_type="bar",
            source_key="opportunities",
            config_json='{"metric": "count", "group_by": "stage"}',
            x=0, y=0, w=6, h=4, sort_order=0,
        )
        db.add(w)
        db.commit()
        widget_id = w.id
    finally:
        db.close()

    r = client.get(f"/api/dashboard-widgets/{widget_id}/data", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert data["kind"] == "series"
    assert "total" in data
    client.delete(f"/api/dashboards/{dash_id}", headers=headers)
