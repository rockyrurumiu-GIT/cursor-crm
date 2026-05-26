"""Smoke tests for delivery roster routes (Phase 5A-2)."""
from __future__ import annotations

import io

import pytest
from starlette.testclient import TestClient

from tests.helpers import auth_header


@pytest.fixture
def headers(admin_auth):
    user, pwd = admin_auth
    return auth_header(user, pwd)


@pytest.fixture(autouse=True)
def _ensure_bootstrap(client, headers):
    """Bootstrap admin + ensure at least one client exists."""
    client.post("/api/auth/legacy-bootstrap", headers=headers)
    r = client.get("/api/clients", headers=headers)
    if r.status_code == 200 and len(r.json()) == 0:
        client.post(
            "/api/clients",
            headers=headers,
            data={"name": "测试客户_Roster", "industry": "IT", "owner": "admin",
                  "scale": "50", "phase": "active", "source": "test", "description": "smoke test"},
        )


def _get_first_client_id(client: TestClient, headers: dict) -> int:
    r = client.get("/api/clients", headers=headers)
    assert r.status_code == 200
    clients = r.json()
    assert len(clients) > 0, "No clients in DB for roster test"
    return clients[0]["id"]


class TestRosterList:
    def test_list_all(self, client, headers):
        r = client.get("/api/roster", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_by_client(self, client, headers):
        cid = _get_first_client_id(client, headers)
        r = client.get(f"/api/clients/{cid}/roster", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestRosterWrite:
    def _full_payload(self, extra=None):
        base = {
            "full_name": "测试员工_Smoke",
            "contact_info": "13900001111",
            "customer_name": "测试客户_Roster",
            "position_title": "工程师",
            "employment_status": "在职",
            "work_location": "北京",
            "business_line": "测试线",
            "entry_date": "2025-01-01",
            "monthly_quote_tax": "10000",
            "pre_tax_salary": "8000",
            "gms": "2000",
            "gm_pct": "20%",
        }
        if extra:
            base.update(extra)
        return base

    def test_create_row_client(self, client, headers):
        cid = _get_first_client_id(client, headers)
        payload = self._full_payload()
        r = client.post(
            f"/api/clients/{cid}/roster",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["full_name"] == "测试员工_Smoke"
        assert data["id"] > 0

    def test_delete_row(self, client, headers):
        cid = _get_first_client_id(client, headers)
        create = client.post(
            f"/api/clients/{cid}/roster",
            headers={**headers, "Content-Type": "application/json"},
            json=self._full_payload({"full_name": "待删除_Smoke", "contact_info": "13900009999"}),
        )
        assert create.status_code == 200, create.text
        row_id = create.json()["id"]
        r = client.delete(f"/api/roster/{row_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"


class TestRosterImportConfirm:
    def test_import_requires_confirm(self, client, headers):
        cid = _get_first_client_id(client, headers)
        csv_content = "姓名,联系方式,岗位\n张三,13811112222,测试\n"
        files = {"file": ("roster.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        r = client.post(
            f"/api/clients/{cid}/roster/import",
            headers=headers,
            files=files,
            data={"confirm": ""},
        )
        assert r.status_code == 400
        assert "confirm" in r.json()["detail"].lower() or "确认" in r.json()["detail"]


class TestTurnoverDashboard:
    def test_dashboard_returns_200(self, client, headers):
        r = client.get("/api/roster/turnover/dashboard", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_turnover_list(self, client, headers):
        r = client.get("/api/roster/turnover", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)
