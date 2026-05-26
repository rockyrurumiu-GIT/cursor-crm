"""Smoke tests for delivery handbook routes (Phase 5D)."""
from __future__ import annotations

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
            data={"name": "测试客户_Handbook", "industry": "IT", "owner": "admin",
                  "scale": "50", "phase": "active", "source": "test", "description": "smoke test"},
        )


def _get_first_client_id(client: TestClient, headers: dict) -> int:
    r = client.get("/api/clients", headers=headers)
    assert r.status_code == 200
    clients = r.json()
    assert len(clients) > 0, "No clients in DB for handbook test"
    return clients[0]["id"]


class TestHandbookList:
    def test_list(self, client, headers):
        cid = _get_first_client_id(client, headers)
        r = client.get(f"/api/clients/{cid}/delivery/handbooks", headers=headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestHandbookUpload:
    def test_upload_pdf(self, client, headers):
        cid = _get_first_client_id(client, headers)
        fake_pdf = b"%PDF-1.4 fake content for smoke test"
        r = client.post(
            f"/api/clients/{cid}/delivery/handbooks",
            headers=headers,
            files=[("files", ("test_handbook.pdf", fake_pdf, "application/pdf"))],
            data={
                "version_label": "v1",
                "status": "draft",
                "tags": "测试标签",
                "permission_departments": "技术部",
                "permission_levels": "3",
            },
        )
        assert r.status_code == 200
        result = r.json()
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["original_filename"] == "test_handbook.pdf"
        assert result[0]["media_kind"] == "pdf"


class TestHandbookSyncFTS:
    def test_sync_fts_returns_200(self, client, headers):
        r = client.post("/api/delivery/handbooks/sync-fts-indexed", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "synced" in data


class TestHandbookSearch:
    def test_search_returns_200(self, client, headers):
        r = client.get("/api/delivery/handbooks/search", params={"q": "测试"}, headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "query" in data
        assert "results" in data

    def test_search_empty_query_400(self, client, headers):
        r = client.get("/api/delivery/handbooks/search", params={"q": ""}, headers=headers)
        assert r.status_code == 400
