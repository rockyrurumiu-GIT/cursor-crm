"""Roster Throme staff number (索摩工号) — Phase 1."""
from __future__ import annotations

import importlib
import io
import re
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.helpers import auth_header
from tests.test_rms_convert_to_roster import (
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _full_roster_payload,
    _hired_application,
    _unique_phone,
)


_THROME_NO_RE = re.compile(r"^A1\d{4}$")


@pytest.fixture
def headers(admin_auth):
    user, pwd = admin_auth
    return auth_header(user, pwd)


@pytest.fixture(autouse=True)
def _ensure_bootstrap(client, headers):
    client.post("/api/auth/legacy-bootstrap", headers=headers)
    r = client.get("/api/clients", headers=headers)
    if r.status_code == 200 and len(r.json()) == 0:
        client.post(
            "/api/clients",
            headers=headers,
            data={
                "name": "测试客户_ThromeNo",
                "industry": "IT",
                "owner": "admin",
                "scale": "50",
                "phase": "active",
                "source": "test",
                "description": "throme staff no test",
            },
        )


def _get_first_client_id(client: TestClient, headers: dict) -> int:
    r = client.get("/api/clients", headers=headers)
    assert r.status_code == 200
    clients = r.json()
    assert len(clients) > 0
    return clients[0]["id"]


def _full_payload(**extra):
    base = {
        "full_name": "索摩工号测试",
        "contact_info": f"139{uuid.uuid4().int % 10**8:08d}",
        "customer_name": "测试客户_ThromeNo",
        "position_title": "工程师",
        "employment_status": "在职",
        "work_location": "北京",
        "business_line": "测试线",
        "entry_date": "2025-01-01",
        "regularization_status": "未转正",
        "monthly_quote_tax": "10000",
        "pre_tax_salary": "8000",
        "gms": "2000",
        "gm_pct": "20%",
    }
    base.update(extra)
    return base


def _reset_throme_sequence(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM roster_entries"))
        conn.execute(text("DELETE FROM roster_throme_staff_no_sequence"))
        conn.execute(
            text(
                "INSERT INTO roster_throme_staff_no_sequence (id, next_value) VALUES (1, 1)"
            )
        )


def test_migration_025_schema(client):
    import main as crm_main

    with crm_main.engine.connect() as conn:
        mig = conn.execute(
            text(
                "SELECT migration_id FROM schema_migrations "
                "WHERE migration_id = '025_roster_throme_staff_no.sql'"
            )
        ).fetchone()
        assert mig is not None
        idx = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='idx_roster_entries_throme_staff_no'"
            )
        ).fetchone()
        assert idx is not None
        seq = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='roster_throme_staff_no_sequence'"
            )
        ).fetchone()
        assert seq is not None
        cols = {
            r[1] for r in conn.execute(text("PRAGMA table_info(roster_entries)")).fetchall()
        }
        assert "throme_staff_no" in cols


def test_create_sequential_a10001_a10002(client, headers):
    import main as crm_main

    _reset_throme_sequence(crm_main.engine)
    cid = _get_first_client_id(client, headers)
    r1 = client.post(
        f"/api/clients/{cid}/roster",
        headers={**headers, "Content-Type": "application/json"},
        json=_full_payload(full_name="第一条", contact_info="13900001001"),
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["throme_staff_no"] == "A10001"

    r2 = client.post(
        f"/api/clients/{cid}/roster",
        headers={**headers, "Content-Type": "application/json"},
        json=_full_payload(full_name="第二条", contact_info="13900001002"),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["throme_staff_no"] == "A10002"


def test_create_ignores_client_supplied_throme_staff_no(client, headers):
    cid = _get_first_client_id(client, headers)
    r = client.post(
        f"/api/clients/{cid}/roster",
        headers={**headers, "Content-Type": "application/json"},
        json=_full_payload(
            full_name="防绕过",
            contact_info="13900001003",
            throme_staff_no="A19999",
        ),
    )
    assert r.status_code == 200, r.text
    assert r.json()["throme_staff_no"] != "A19999"
    assert _THROME_NO_RE.match(r.json()["throme_staff_no"])


def test_update_ignores_throme_staff_no(client, headers):
    cid = _get_first_client_id(client, headers)
    create = client.post(
        f"/api/clients/{cid}/roster",
        headers={**headers, "Content-Type": "application/json"},
        json=_full_payload(full_name="不可改", contact_info="13900001004"),
    )
    assert create.status_code == 200, create.text
    row = create.json()
    original = row["throme_staff_no"]
    assert _THROME_NO_RE.match(original)

    update = client.put(
        f"/api/roster/{row['id']}",
        headers={**headers, "Content-Type": "application/json"},
        json={**_full_payload(full_name="不可改", contact_info="13900001004"), "throme_staff_no": "A19999"},
    )
    assert update.status_code == 200, update.text
    assert update.json()["throme_staff_no"] == original


def test_legacy_row_throme_staff_no_empty(client, headers):
    import main as crm_main

    cid = _get_first_client_id(client, headers)
    with crm_main.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO roster_entries (
                    client_id, full_name, contact_info, employment_status, throme_staff_no
                ) VALUES (:cid, '历史员工', '13900001005', '在职', '')
                """
            ),
            {"cid": cid},
        )
    r = client.get(f"/api/clients/{cid}/roster", headers=headers)
    assert r.status_code == 200
    legacy = next((x for x in r.json() if x.get("contact_info") == "13900001005"), None)
    assert legacy is not None
    assert not str(legacy.get("throme_staff_no") or "").strip()


def test_csv_import_force_generates_throme_staff_no(client, headers):
    cid = _get_first_client_id(client, headers)
    csv_content = (
        "姓名,联系方式,岗位,在职情况,客户,工作地,业务线,入职日期,转正,"
        "月报价(含税),税前工资,GM$,GM%\n"
        "导入甲,13900001006,工程师,在职,测试客户_ThromeNo,北京,测试线,"
        "2025-01-01,未转正,10000,8000,2000,20%\n"
    )
    files = {"file": ("roster.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    r = client.post(
        f"/api/clients/{cid}/roster/import",
        headers=headers,
        files=files,
        data={"confirm": "CONFIRM"},
    )
    assert r.status_code == 200, r.text
    listed = client.get(f"/api/clients/{cid}/roster", headers=headers).json()
    imported = next((x for x in listed if x.get("contact_info") == "13900001006"), None)
    assert imported is not None
    assert imported["throme_staff_no"]
    assert _THROME_NO_RE.match(imported["throme_staff_no"])


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


def test_rms_convert_assigns_throme_staff_no(client_rbac, admin_auth, rms_engine):
    uniq = uuid.uuid4().hex[:8]
    login, app_id, client_id, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"throme{uniq}"
    )
    payload = _full_roster_payload(
        cand, client_row, job, contact_info=_unique_phone(f"throme{uniq}")
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert r.status_code == 200, r.text
    staff_no = r.json()["roster_entry"]["throme_staff_no"]
    assert staff_no
    assert _THROME_NO_RE.match(staff_no)
