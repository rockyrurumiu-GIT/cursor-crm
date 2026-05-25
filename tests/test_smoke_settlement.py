"""Smoke tests: settlement API paths (phase 01 engineering baseline)."""
from __future__ import annotations

from tests.helpers import auth_header

SETTLEMENT_PAYLOAD = {
    "customer_name": "Smoke测试客户",
    "fee_month": "2026-05",
    "amount": "1000.00",
    "internal_attendance_confirm": "是",
    "client_confirm": "是",
    "invoiced": "否",
    "paid": "否",
    "payment_cycle": "月度",
}


def test_settlement_list_requires_auth(client):
    assert client.get("/api/delivery/settlement").status_code == 401


def test_settlement_crud_row_paths(client, admin_auth):
    user, pwd = admin_auth
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}

    listed = client.get("/api/delivery/settlement", headers=auth_header(user, pwd))
    assert listed.status_code == 200
    before = len(listed.json())

    created = client.post("/api/delivery/settlement", headers=headers, json=SETTLEMENT_PAYLOAD)
    assert created.status_code == 200, created.text
    row = created.json()
    row_id = row["id"]
    assert row.get("customer_name") == SETTLEMENT_PAYLOAD["customer_name"]

    updated = client.put(
        f"/api/delivery/settlement/row/{row_id}",
        headers=headers,
        json={**SETTLEMENT_PAYLOAD, "amount": "2000.00"},
    )
    assert updated.status_code == 200
    assert updated.json().get("amount") == "2000.00"

    wrong_path = client.put(
        f"/api/delivery/settlement/{row_id}",
        headers=headers,
        json={**SETTLEMENT_PAYLOAD, "amount": "3000.00"},
    )
    assert wrong_path.status_code == 404

    deleted = client.delete(f"/api/delivery/settlement/row/{row_id}", headers=auth_header(user, pwd))
    assert deleted.status_code == 200

    after = client.get("/api/delivery/settlement", headers=auth_header(user, pwd))
    assert after.status_code == 200
    assert len(after.json()) == before
