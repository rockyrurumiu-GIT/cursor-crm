"""Dashboard builder module tests."""
from __future__ import annotations

import importlib
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
    assert "count" in data["metrics"]
    # Twenty-parity style metadata.
    assert "blue" in data["colors"]
    assert "value_desc" in data["sorts"]


def _make_tab(client, headers, name):
    r = client.post("/api/dashboards", headers=headers, json={"name": name})
    dash_id = r.json()["id"]
    r = client.post(f"/api/dashboards/{dash_id}/tabs", headers=headers, json={"name": "T"})
    return dash_id, r.json()["id"]


@pytest.mark.parametrize(
    "bad_config,detail_part",
    [
        ({"metric": "count", "group_by": "stage", "color": "rainbow"}, "未知配色"),
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
