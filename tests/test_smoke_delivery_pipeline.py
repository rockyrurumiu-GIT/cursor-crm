"""Smoke tests for delivery pipeline routes (Phase 5B)."""
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
            data={"name": "测试客户_Pipeline", "industry": "IT", "owner": "admin",
                  "scale": "50", "phase": "active", "source": "test", "description": "smoke test"},
        )


def _get_first_client_id(client: TestClient, headers: dict) -> int:
    r = client.get("/api/clients", headers=headers)
    assert r.status_code == 200
    clients = r.json()
    assert len(clients) > 0, "No clients in DB for pipeline test"
    return clients[0]["id"]


class TestPipelineList:
    def test_list(self, client, headers):
        cid = _get_first_client_id(client, headers)
        r = client.get(f"/api/clients/{cid}/delivery/pipeline", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestPipelineWrite:
    def test_create_row(self, client, headers):
        cid = _get_first_client_id(client, headers)
        payload = {
            "date": "5w1",
            "position": "测试岗位",
            "full_name": "张三_Smoke",
            "region": "北京",
            "resume_screening": "通过",
        }
        r = client.post(
            f"/api/clients/{cid}/delivery/pipeline",
            headers={**headers, "Content-Type": "application/json"},
            json=payload,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["full_name"] == "张三_Smoke"
        assert data["id"] > 0

    def test_delete_row(self, client, headers):
        cid = _get_first_client_id(client, headers)
        create = client.post(
            f"/api/clients/{cid}/delivery/pipeline",
            headers={**headers, "Content-Type": "application/json"},
            json={"date": "5w2", "position": "待删岗", "full_name": "待删_Smoke", "region": "上海"},
        )
        assert create.status_code == 200, create.text
        row_id = create.json()["id"]
        r = client.delete(f"/api/delivery/pipeline/row/{row_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"


class TestPipelineImportConfirm:
    def test_import_requires_confirm(self, client, headers):
        cid = _get_first_client_id(client, headers)
        csv_content = "日期,岗位,姓名,地域\n5w1,测试,李四,深圳\n"
        files = {"file": ("pipeline.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        r = client.post(
            f"/api/clients/{cid}/delivery/pipeline/import",
            headers=headers,
            files=files,
            data={"confirm": ""},
        )
        assert r.status_code == 400
        assert "confirm" in r.json()["detail"].lower() or "确认" in r.json()["detail"]


class TestPipelineInsight:
    def test_insight_returns_200(self, client, headers):
        cid = _get_first_client_id(client, headers)
        r = client.get(f"/api/clients/{cid}/delivery/pipeline/insight", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "rows" in data
        assert "anomalies" in data
