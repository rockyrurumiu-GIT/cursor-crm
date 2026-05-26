"""Smoke tests for delivery interviews routes (Phase 5C)."""
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
    client.post("/api/auth/legacy-bootstrap", headers=headers)
    r = client.get("/api/clients", headers=headers)
    if r.status_code == 200 and len(r.json()) == 0:
        client.post(
            "/api/clients",
            headers=headers,
            data={"name": "测试客户_Interviews", "industry": "IT", "owner": "admin",
                  "scale": "50", "phase": "active", "source": "test", "description": "smoke test"},
        )


def _get_first_client_id(client: TestClient, headers: dict) -> int:
    r = client.get("/api/clients", headers=headers)
    assert r.status_code == 200
    clients = r.json()
    assert len(clients) > 0, "No clients in DB for interviews test"
    return clients[0]["id"]


class TestInterviewList:
    def test_list(self, client, headers):
        cid = _get_first_client_id(client, headers)
        r = client.get(f"/api/clients/{cid}/delivery/interviews", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestInterviewWrite:
    def test_create_row(self, client, headers):
        cid = _get_first_client_id(client, headers)
        payload = {
            "full_name": "张三_Interview_Smoke",
            "employment_status": "在职",
            "contact": "13800000001",
            "project_name": "项目A",
            "position": "工程师",
            "delivery_judgment": "该员工表现良好，交付质量稳定，沟通积极主动，值得肯定",
            "delivery_todos": "继续保持当前状态，定期反馈，做好项目交接",
        }
        r = client.post(
            f"/api/clients/{cid}/delivery/interviews",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["full_name"] == "张三_Interview_Smoke"
        assert data["id"] > 0


class TestInterviewImportConfirm:
    def test_import_requires_confirm(self, client, headers):
        cid = _get_first_client_id(client, headers)
        csv_content = "员工姓名,在职/离职,交付判断,交付待办事项\n李四,在职,这是一条足够长的交付判断文字用于测试,这是待办事项内容\n"
        files = {"file": ("interviews.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        r = client.post(
            f"/api/clients/{cid}/delivery/interviews/import",
            headers=headers,
            files=files,
            data={"confirm": ""},
        )
        assert r.status_code == 400
        assert "confirm" in r.json()["detail"].lower() or "确认" in r.json()["detail"]


class TestInterviewMarkLeft:
    def test_mark_employment_left(self, client, headers):
        cid = _get_first_client_id(client, headers)
        payload = {
            "full_name": "离职测试员工_Smoke",
            "employment_status": "在职",
            "contact": "13900000002",
            "project_name": "项目B",
            "position": "测试",
            "delivery_judgment": "该员工已确认离职，需要标记离职状态以便后续处理",
            "delivery_todos": "完成交接工作，确认项目状态",
        }
        create_r = client.post(
            f"/api/clients/{cid}/delivery/interviews",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        assert create_r.status_code == 200, create_r.text

        r = client.post(
            f"/api/clients/{cid}/delivery/interviews/mark-employment-left",
            headers={**headers, "Content-Type": "application/json"},
            json={"full_name": "离职测试员工_Smoke"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["updated"] >= 1
