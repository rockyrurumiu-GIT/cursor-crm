"""Contract upload, numbering, expiry status, and API tests."""
from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pytest

from phase2_core import compute_contract_expiry_status, contract_to_dict
from services.contract_numbering import extract_client_abbr, generate_contract_no
from tests.helpers import auth_header

_MIN_PDF = b"%PDF-1.4\n% contract test\n"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def headers(admin_auth):
    user, pwd = admin_auth
    return auth_header(user, pwd)


@pytest.fixture(autouse=True)
def _bootstrap(client, headers):
    client.post("/api/auth/legacy-bootstrap", headers=headers)


def _create_client(client, headers, name: str) -> int:
    r = client.post(
        "/api/clients",
        headers=headers,
        data={
            "name": name,
            "industry": "IT",
            "owner": "admin",
            "scale": "50",
            "phase": "active",
            "source": "test",
            "description": "contract test",
        },
    )
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _upload_contract(
    client,
    headers,
    *,
    client_id: int,
    contract_type: str = "msa",
    title: str = "测试合同",
    expires_at: str = "",
    end_date: str = "",
    contract_no: str = "",
    remarks: str = "",
    filename: str = "contract.pdf",
):
    data = {
        "title": title,
        "client_id": str(client_id),
        "contract_type": contract_type,
    }
    if expires_at:
        data["expires_at"] = expires_at
    if end_date:
        data["end_date"] = end_date
    if contract_no:
        data["contract_no"] = contract_no
    if remarks:
        data["remarks"] = remarks
    return client.post(
        "/api/contracts",
        headers=headers,
        data=data,
        files={"file": (filename, io.BytesIO(_MIN_PDF), "application/pdf")},
    )


class TestContractNumberingUnit:
    def test_extract_client_abbr(self):
        assert extract_client_abbr("蛮啾 MJ") == "MJ"
        assert extract_client_abbr("中诺通讯 ZNTX") == "ZNTX"
        assert extract_client_abbr("纯中文客户") == ""

    def test_generate_msa_and_nda(self):
        import main as crm_main

        db = crm_main.SessionLocal()
        try:
            no_msa = generate_contract_no(
                db,
                crm_main.Contract,
                client_id=1,
                client_name="蛮啾 MJ",
                contract_type="msa",
                year=2026,
            )
            assert no_msa == "TRM-MSA-MJ-2026"
            no_nda = generate_contract_no(
                db,
                crm_main.Contract,
                client_id=1,
                client_name="蛮啾 MJ",
                contract_type="nda",
                year=2026,
            )
            assert no_nda == "TRM-NDA-MJ-2026"
        finally:
            db.close()

    def test_sow_sequence_by_client_id(self, client, headers):
        import main as crm_main

        cid_a = _create_client(client, headers, f"ContractSeqA_{id(self)}")
        cid_b = _create_client(client, headers, f"ContractSeqB_{id(self)}")
        db = crm_main.SessionLocal()
        try:
            first_a = generate_contract_no(
                db,
                crm_main.Contract,
                client_id=cid_a,
                client_name="蛮啾 MJ",
                contract_type="sow",
                year=2026,
            )
            db.add(
                crm_main.Contract(
                    client_id=cid_a,
                    contract_no=first_a,
                    contract_type="sow",
                    title="seed",
                )
            )
            db.commit()
            second_a = generate_contract_no(
                db,
                crm_main.Contract,
                client_id=cid_a,
                client_name="蛮啾 MJ",
                contract_type="sow",
                year=2026,
            )
            first_b = generate_contract_no(
                db,
                crm_main.Contract,
                client_id=cid_b,
                client_name="其他 MJ",
                contract_type="sow",
                year=2026,
            )
            assert first_a == "TRM-SOW-MJ-2026-01"
            assert second_a == "TRM-SOW-MJ-2026-02"
            assert first_b == "TRM-SOW-MJ-2026-01"
        finally:
            db.close()


class TestContractExpiryStatus:
    def test_status_boundaries(self):
        today = date(2026, 6, 22)
        assert compute_contract_expiry_status("", today=today) == "active"
        assert compute_contract_expiry_status("2026-06-21", today=today) == "expired"
        assert compute_contract_expiry_status("2026-06-22", today=today) == "expiring"
        assert compute_contract_expiry_status("2026-07-22", today=today) == "expiring"
        assert compute_contract_expiry_status("2026-07-23", today=today) == "active"


class TestContractSerialization:
    def test_handoff_project_type_label(self):
        class _Row:
            id = 1
            contract_type = "项目"
            contract_no = "SOW-abc-20260622"
            title = "交接合同"
            end_date = ""
            status = "draft"
            remarks = ""
            client_id = 1
            handoff_id = 1
            opportunity_id = None
            total_amount = ""
            start_date = ""
            sow_markdown = ""
            stored_path = ""
            file_name = ""
            file_size = 0
            created_at = None
            updated_at = None

        d = contract_to_dict(_Row(), "测试客户")
        assert d["contract_type_label"] == "项目"
        assert d["status"] == "active"
        assert d["status_label"] == "有效"


class TestContractsApi:
    def test_form_options(self, client, headers):
        _create_client(client, headers, f"ContractOpts_{id(self)} MJ")
        r = client.get("/api/contracts/form-options", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert "contract_types" in body
        assert "clients" in body
        assert body["statuses"] == [
            {"value": "active", "label": "有效"},
            {"value": "expiring", "label": "快到期"},
            {"value": "expired", "label": "过期"},
        ]
        assert any(c.get("sales_owner_name") for c in body["clients"])

    def test_upload_msa_auto_number_ignores_fake_no(self, client, headers):
        cid = _create_client(client, headers, f"测试客户 M{id(self)}")
        r = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="msa",
            expires_at="2027-12-31",
            contract_no="FAKE-NO-123",
            remarks="备注A",
        )
        assert r.status_code == 201, r.text
        body = r.json()
        suffix = str(id(self)).upper()
        assert body["contract_no"] == f"TRM-MSA-M{suffix}-2026"
        assert body["contract_type"] == "msa"
        assert body["contract_type_label"] == "甲方MSA"
        assert body["remarks"] == "备注A"
        assert body["status"] == "active"

    def test_upload_vendor_manual_no(self, client, headers):
        cid = _create_client(client, headers, f"ContractVendor_{id(self)}")
        r = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="vendor",
            expires_at="2027-12-31",
            contract_no="SUP-2026-001",
        )
        assert r.status_code == 201, r.text
        assert r.json()["contract_no"] == "SUP-2026-001"

    def test_vendor_duplicate_contract_no(self, client, headers):
        cid = _create_client(client, headers, f"ContractVendorDup_{id(self)}")
        first = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="vendor",
            expires_at="2027-12-31",
            contract_no="SUP-DUP-001",
        )
        assert first.status_code == 201
        second = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="vendor",
            expires_at="2027-12-31",
            contract_no="SUP-DUP-001",
            title="重复编号",
        )
        assert second.status_code == 400
        assert "合同编号已存在" in second.json()["detail"]

    def test_preview_contract_pdf(self, client, headers):
        cid = _create_client(client, headers, f"ContractPreview_{id(self)} MJ")
        up = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="nda",
            expires_at="2027-12-31",
        )
        assert up.status_code == 201
        contract_id = up.json()["id"]
        r = client.get(f"/api/contracts/{contract_id}/preview", headers=headers)
        assert r.status_code == 200
        assert "application/pdf" in (r.headers.get("content-type") or "")

    def test_upload_long_term_expiry(self, client, headers):
        cid = _create_client(client, headers, f"长期客户 L{id(self)}")
        r = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="nda",
            expires_at="",
        )
        assert r.status_code == 201, r.text
        assert r.json()["expires_at"] == ""
        assert r.json()["status"] == "active"

    def test_upload_end_date_compat(self, client, headers):
        cid = _create_client(client, headers, f"EndDate客户 N{id(self)}")
        r = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="nda",
            end_date="2027-06-30",
        )
        assert r.status_code == 201, r.text
        assert r.json()["expires_at"] == "2027-06-30"

    def test_upload_missing_abbr(self, client, headers):
        cid = _create_client(client, headers, "纯中文客户无缩写")
        r = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="msa",
            expires_at="2027-12-31",
        )
        assert r.status_code == 400
        assert "英文简写" in r.json()["detail"]

    def test_update_contract_metadata(self, client, headers):
        suffix = id(self)
        cid = _create_client(client, headers, f"Update客户 U{suffix}")
        up = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="nda",
            expires_at="2027-12-31",
            title="原名称",
            remarks="原备注",
        )
        assert up.status_code == 201
        contract_id = up.json()["id"]
        r = client.patch(
            f"/api/contracts/{contract_id}",
            headers=headers,
            data={
                "title": "蛮啾NDA",
                "client_id": str(cid),
                "contract_type": "nda",
                "expires_at": "",
                "remarks": "更新备注",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["title"] == "蛮啾NDA"
        assert body["expires_at"] == ""
        assert body["remarks"] == "更新备注"
        assert body["contract_no"] == up.json()["contract_no"]

    def test_delete_contract_upload(self, client, headers):
        suffix = id(self)
        cid = _create_client(client, headers, f"Delete客户 D{suffix}")
        up = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="nda",
            expires_at="2027-12-31",
            title="待删合同",
        )
        assert up.status_code == 201
        contract_id = up.json()["id"]
        r = client.delete(f"/api/contracts/{contract_id}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        listed = client.get("/api/contracts", headers=headers)
        assert listed.status_code == 200
        assert not any(row.get("id") == contract_id for row in listed.json())

    def test_delete_handoff_contract(self, client, headers):
        import main as crm_main

        suffix = id(self)
        cid = _create_client(client, headers, f"HandoffDel H{suffix}")
        db = crm_main.SessionLocal()
        try:
            row = crm_main.Contract(
                client_id=cid,
                handoff_id=999001,
                contract_no=f"SOW-H{suffix}-20260622",
                contract_type="项目",
                title=f"波克 交接 v{suffix}",
                sow_markdown="# test",
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            contract_id = int(row.id)
        finally:
            db.close()
        r = client.delete(f"/api/contracts/{contract_id}", headers=headers)
        assert r.status_code == 200, r.text
        got = client.get(f"/api/contracts/{contract_id}", headers=headers)
        assert got.status_code == 404

    def test_delete_contract_after_settlement_removed(self, client, headers):
        import main as crm_main

        suffix = id(self)
        cid = _create_client(client, headers, f"SettlementOrphan S{suffix}")
        db = crm_main.SessionLocal()
        try:
            contract = crm_main.Contract(
                client_id=cid,
                contract_no=f"SOW-S{suffix}-20260519",
                contract_type="项目",
                title=f"日产 交接 v{suffix}",
                sow_markdown="# sow",
            )
            db.add(contract)
            db.flush()
            milestone = crm_main.ContractMilestone(
                contract_id=contract.id,
                name="里程碑1",
                settlement_entry_id=999999,
            )
            db.add(milestone)
            db.commit()
            contract_id = int(contract.id)
        finally:
            db.close()
        r = client.delete(f"/api/contracts/{contract_id}", headers=headers)
        assert r.status_code == 200, r.text
        listed = client.get("/api/contracts", headers=headers)
        assert not any(row.get("id") == contract_id for row in listed.json())

    def test_list_status_filter_expiring(self, client, headers, monkeypatch):
        from phase2_core import compute_contract_expiry_status as real_fn

        cid = _create_client(client, headers, f"筛选客户 F{id(self)}")
        today = date(2026, 6, 22)
        expiring_day = (today + timedelta(days=10)).isoformat()
        active_day = (today + timedelta(days=60)).isoformat()
        monkeypatch.setattr(
            "phase2_core.compute_contract_expiry_status",
            lambda end_date, *, today=None: real_fn(end_date, today=today),
        )
        r1 = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="sow",
            expires_at=expiring_day,
            title="快到期合同",
        )
        assert r1.status_code == 201
        r2 = _upload_contract(
            client,
            headers,
            client_id=cid,
            contract_type="sow",
            expires_at=active_day,
            title="有效合同",
        )
        assert r2.status_code == 201
        listed = client.get("/api/contracts?status=expiring", headers=headers)
        assert listed.status_code == 200
        rows = listed.json()
        assert any(row.get("title") == "快到期合同" for row in rows)
        assert all(row.get("status") == "expiring" for row in rows)


class TestContractsFrontendStatic:
    def test_html_contains_upload_fields(self):
        html = (ROOT / "templates/pages/contracts_index.html").read_text(encoding="utf-8")
        for token in ("资料名称", "合同类型", "客户", "有效期", "备注", "上传合同"):
            assert token in html

    def test_js_contains_upload_fields(self):
        js = (ROOT / "static/js/pages/contracts.js").read_text(encoding="utf-8")
        for token in ("contract_type", "expires_at", "remarks", "formSalesOwner", "openEdit", "isEditMode"):
            assert token in js
