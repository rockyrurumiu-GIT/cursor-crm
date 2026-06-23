"""Delivery employee files — labor contract upload and auto-numbering."""
from __future__ import annotations

import importlib
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.helpers import auth_header
from tests.test_roster_throme_staff_no import _full_payload

_MIN_PDF = b"%PDF-1.4\n% labor contract test\n"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def headers(admin_auth):
    user, pwd = admin_auth
    return auth_header(user, pwd)


@pytest.fixture(autouse=True)
def _bootstrap(client, headers):
    client.post("/api/auth/legacy-bootstrap", headers=headers)


def _create_client(client: TestClient, headers: dict, name: str | None = None) -> int:
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/clients",
        headers=headers,
        data={
            "name": name or f"劳动合同客户_{suffix}",
            "industry": "IT",
            "owner": "admin",
            "scale": "50",
            "phase": "active",
            "source": "test",
            "description": "labor contract test",
        },
    )
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _create_roster_entry(
    client: TestClient,
    headers: dict,
    client_id: int,
    *,
    full_name: str,
    contact_info: str,
) -> dict:
    r = client.post(
        f"/api/clients/{client_id}/roster",
        headers={**headers, "Content-Type": "application/json"},
        json=_full_payload(full_name=full_name, contact_info=contact_info),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _upload_labor_contract(
    client: TestClient,
    headers: dict,
    client_id: int,
    *,
    full_name: str,
    contact_info: str,
    sign_date: str = "2026-06-23",
    valid_until: str = "",
    confirm: int = 0,
    filename: str = "contract.pdf",
    extra_data: dict | None = None,
):
    data = {
        "status": "draft",
        "document_type": "劳动合同",
        "employee_full_name": full_name,
        "employee_contact_info": contact_info,
        "contract_sign_date": sign_date,
        "contract_valid_until": valid_until,
        "confirm_same_year_renewal": str(confirm),
    }
    if extra_data:
        data.update(extra_data)
    return client.post(
        f"/api/clients/{client_id}/delivery/employee-files",
        headers=headers,
        files=[("files", (filename, _MIN_PDF, "application/pdf"))],
        data=data,
    )


def _upload_other_file(client: TestClient, headers: dict, client_id: int):
    return client.post(
        f"/api/clients/{client_id}/delivery/employee-files",
        headers=headers,
        files=[("files", ("other.pdf", _MIN_PDF, "application/pdf"))],
        data={"status": "draft", "document_type": "其他"},
    )


def _count_employee_files(engine, client_id: int) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT COUNT(*) FROM delivery_employee_files WHERE client_id = :cid"),
                {"cid": client_id},
            ).scalar()
            or 0
        )


def _count_labor_contracts_with_no(engine, client_id: int, labor_no: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM delivery_employee_files "
                    "WHERE client_id = :cid AND labor_contract_no = :no"
                ),
                {"cid": client_id, "no": labor_no},
            ).scalar()
            or 0
        )


def _count_files_on_disk(client_id: int) -> int:
    import main as crm_main

    rel = f"employee_files/client_{client_id}"
    abs_dir = Path(crm_main.UPLOAD_DIR) / rel.replace("/", os.sep)
    if not abs_dir.is_dir():
        return 0
    return sum(1 for p in abs_dir.iterdir() if p.is_file())


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


class TestLaborContractUpload:
    def test_first_upload_generates_number(self, client, headers):
        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="张三", contact_info="13800000001"
        )
        throme = roster["throme_staff_no"]
        r = _upload_labor_contract(
            client, headers, cid, full_name="张三", contact_info="13800000001"
        )
        assert r.status_code == 200, r.text
        body = r.json()[0]
        assert body["document_type"] == "劳动合同"
        assert body["employee_full_name"] == "张三"
        assert body["employee_contact_info"] == "13800000001"
        assert body["roster_entry_id"] == roster["id"]
        assert body["throme_staff_no"] == throme
        assert body["labor_contract_no"] == f"TRM-LC-{throme}-2026-01"
        assert body["contract_sign_date"] == "2026-06-23"
        assert body["contract_valid_until"] == ""

    def test_upload_persists_contract_valid_until(self, client, headers):
        cid = _create_client(client, headers)
        _create_roster_entry(
            client, headers, cid, full_name="王五", contact_info="13800000099"
        )
        r = _upload_labor_contract(
            client,
            headers,
            cid,
            full_name="王五",
            contact_info="13800000099",
            valid_until="2028-12-31",
        )
        assert r.status_code == 200, r.text
        assert r.json()[0]["contract_valid_until"] == "2028-12-31"

    def test_same_year_second_without_confirm_returns_409(self, client, headers):
        import main as crm_main

        cid = _create_client(client, headers)
        _create_roster_entry(client, headers, cid, full_name="李四", contact_info="13800000002")
        first = _upload_labor_contract(
            client, headers, cid, full_name="李四", contact_info="13800000002"
        )
        assert first.status_code == 200
        count_before = _count_employee_files(crm_main.engine, cid)
        disk_before = _count_files_on_disk(cid)

        second = _upload_labor_contract(
            client, headers, cid, full_name="李四", contact_info="13800000002", filename="c2.pdf"
        )
        assert second.status_code == 409
        detail = second.json()["detail"]
        assert detail["code"] == "same_year_labor_contract_exists"
        assert "是否为同年续约" in detail["message"]
        assert _count_employee_files(crm_main.engine, cid) == count_before
        assert _count_files_on_disk(cid) == disk_before

    def test_same_year_second_with_confirm_generates_02(self, client, headers):
        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="王五", contact_info="13800000003"
        )
        throme = roster["throme_staff_no"]
        assert _upload_labor_contract(
            client, headers, cid, full_name="王五", contact_info="13800000003"
        ).status_code == 200
        r = _upload_labor_contract(
            client,
            headers,
            cid,
            full_name="王五",
            contact_info="13800000003",
            confirm=1,
            filename="renewal.pdf",
        )
        assert r.status_code == 200, r.text
        assert r.json()[0]["labor_contract_no"] == f"TRM-LC-{throme}-2026-02"

    def test_different_year_starts_at_01(self, client, headers):
        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="赵六", contact_info="13800000004"
        )
        throme = roster["throme_staff_no"]
        assert _upload_labor_contract(
            client,
            headers,
            cid,
            full_name="赵六",
            contact_info="13800000004",
            sign_date="2026-01-01",
        ).status_code == 200
        r = _upload_labor_contract(
            client,
            headers,
            cid,
            full_name="赵六",
            contact_info="13800000004",
            sign_date="2027-01-01",
            confirm=0,
            filename="2027.pdf",
        )
        assert r.status_code == 200, r.text
        assert r.json()[0]["labor_contract_no"] == f"TRM-LC-{throme}-2027-01"

    def test_name_phone_mismatch(self, client, headers):
        cid = _create_client(client, headers)
        _create_roster_entry(client, headers, cid, full_name="真实姓名", contact_info="13800000005")
        r = _upload_labor_contract(
            client, headers, cid, full_name="错误姓名", contact_info="13800000005"
        )
        assert r.status_code == 409
        assert "未匹配到花名册员工" in r.json()["detail"]

    def test_multiple_roster_matches_via_sql(self, client, headers):
        import main as crm_main

        cid = _create_client(client, headers)
        name = "重复员工"
        phone = "13800000006"
        with crm_main.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO roster_entries (
                        client_id, full_name, contact_info, employment_status, throme_staff_no
                    ) VALUES
                    (:cid, :name, :phone, '在职', ''),
                    (:cid, :name, :phone, '在职', '')
                    """
                ),
                {"cid": cid, "name": name, "phone": phone},
            )
        r = _upload_labor_contract(client, headers, cid, full_name=name, contact_info=phone)
        assert r.status_code == 409
        assert "匹配到多个花名册员工" in r.json()["detail"]

    def test_missing_throme_staff_no(self, client, headers):
        import main as crm_main

        cid = _create_client(client, headers)
        name = "无工号员工"
        phone = "13800000007"
        with crm_main.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO roster_entries (
                        client_id, full_name, contact_info, employment_status, throme_staff_no
                    ) VALUES (:cid, :name, :phone, '在职', '')
                    """
                ),
                {"cid": cid, "name": name, "phone": phone},
            )
        r = _upload_labor_contract(client, headers, cid, full_name=name, contact_info=phone)
        assert r.status_code == 409
        assert "缺少索摩工号" in r.json()["detail"]

    def test_non_labor_upload_without_name_phone(self, client, headers):
        cid = _create_client(client, headers)
        r = _upload_other_file(client, headers, cid)
        assert r.status_code == 200, r.text
        body = r.json()[0]
        assert body.get("document_type") == "其他"
        assert not body.get("employee_full_name")
        assert not body.get("labor_contract_no")

    def test_forged_throme_and_labor_no_ignored(self, client, headers):
        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="伪造测试", contact_info="13800000008"
        )
        throme = roster["throme_staff_no"]
        r = _upload_labor_contract(
            client,
            headers,
            cid,
            full_name="伪造测试",
            contact_info="13800000008",
            extra_data={
                "throme_staff_no": "FAKE999",
                "labor_contract_no": "TRM-LC-FAKE999-2026-99",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()[0]
        assert body["throme_staff_no"] == throme
        assert body["labor_contract_no"] == f"TRM-LC-{throme}-2026-01"

    def test_multi_file_labor_contract_rejected(self, client, headers):
        cid = _create_client(client, headers)
        _create_roster_entry(client, headers, cid, full_name="多文件", contact_info="13800000009")
        r = client.post(
            f"/api/clients/{cid}/delivery/employee-files",
            headers=headers,
            files=[
                ("files", ("a.pdf", _MIN_PDF, "application/pdf")),
                ("files", ("b.pdf", _MIN_PDF, "application/pdf")),
            ],
            data={
                "document_type": "劳动合同",
                "employee_full_name": "多文件",
                "employee_contact_info": "13800000009",
            },
        )
        assert r.status_code == 400
        assert "每次只能上传 1 个文件" in r.json()["detail"]

    def test_deprecated_contract_preserves_number_sequence(self, client, headers):
        import main as crm_main

        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="作废测试", contact_info="13800000010"
        )
        throme = roster["throme_staff_no"]
        first = _upload_labor_contract(
            client, headers, cid, full_name="作废测试", contact_info="13800000010",
            extra_data={"status": "published"},
        )
        assert first.status_code == 200
        row_id = first.json()[0]["id"]
        labor_no_01 = f"TRM-LC-{throme}-2026-01"

        del_r = client.delete(
            f"/api/clients/{cid}/delivery/employee-files/{row_id}",
            headers=headers,
        )
        assert del_r.status_code == 200
        assert _count_labor_contracts_with_no(crm_main.engine, cid, labor_no_01) == 1

        with crm_main.engine.connect() as conn:
            status = conn.execute(
                text("SELECT status FROM delivery_employee_files WHERE id = :id"),
                {"id": row_id},
            ).scalar()
        assert status == "deprecated"

        second = _upload_labor_contract(
            client,
            headers,
            cid,
            full_name="作废测试",
            contact_info="13800000010",
            confirm=1,
            filename="after_void.pdf",
        )
        assert second.status_code == 200, second.text
        assert second.json()[0]["labor_contract_no"] == f"TRM-LC-{throme}-2026-02"

    def test_draft_labor_contract_hard_delete_frees_number(self, client, headers):
        import main as crm_main

        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="草稿误传", contact_info="13800000011"
        )
        throme = roster["throme_staff_no"]
        labor_no_01 = f"TRM-LC-{throme}-2026-01"
        first = _upload_labor_contract(
            client, headers, cid, full_name="草稿误传", contact_info="13800000011"
        )
        assert first.status_code == 200
        assert first.json()[0]["labor_contract_no"] == labor_no_01
        row_id = first.json()[0]["id"]

        del_r = client.delete(
            f"/api/clients/{cid}/delivery/employee-files/{row_id}",
            headers=headers,
        )
        assert del_r.status_code == 200
        assert _count_labor_contracts_with_no(crm_main.engine, cid, labor_no_01) == 0

        second = _upload_labor_contract(
            client, headers, cid, full_name="草稿误传", contact_info="13800000011",
            filename="correct.pdf",
        )
        assert second.status_code == 200, second.text
        assert second.json()[0]["labor_contract_no"] == labor_no_01

    def test_draft_labor_contract_can_be_published(self, client, headers):
        cid = _create_client(client, headers)
        roster = _create_roster_entry(
            client, headers, cid, full_name="发布测试", contact_info="13800000012"
        )
        upload = _upload_labor_contract(
            client, headers, cid, full_name="发布测试", contact_info="13800000012"
        )
        assert upload.status_code == 200
        row_id = upload.json()[0]["id"]
        assert upload.json()[0]["status"] == "draft"

        patch_r = client.patch(
            f"/api/clients/{cid}/delivery/employee-files/{row_id}",
            headers={**headers, "Content-Type": "application/json"},
            json={"status": "published"},
        )
        assert patch_r.status_code == 200, patch_r.text
        assert patch_r.json()["status"] == "published"


class TestLaborContractDatascope:
    def test_upload_without_datascope_returns_404(self, client_rbac, admin_auth):
        import main as crm_main
        from auth.data_scope_catalog import RESOURCE_DELIVERY_EMPLOYEE_FILES, SCOPE_ASSIGNED
        from auth.permissions import ROLE_DELIVERY
        from tests.test_rms_phase2_mvp import _set_role_data_scope

        suffix = os.getpid()
        delivery_a = f"lc_scope_a_{suffix}"
        delivery_b = f"lc_scope_b_{suffix}"
        admin_user, admin_pwd = admin_auth
        headers = auth_header(admin_user, admin_pwd)

        uid_a = client_rbac.post(
            "/api/system/users",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "username": delivery_a,
                "password": "pass1234",
                "display_name": delivery_a,
                "role_codes": ["DELIVERY"],
            },
        ).json()["id"]
        uid_b = client_rbac.post(
            "/api/system/users",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "username": delivery_b,
                "password": "pass1234",
                "display_name": delivery_b,
                "role_codes": ["DELIVERY"],
            },
        ).json()["id"]

        c1 = client_rbac.post(
            "/api/clients",
            headers=headers,
            data={
                "name": f"LC客户A_{suffix}",
                "industry": "IT",
                "owner": "admin",
                "scale": "100",
                "phase": "成交",
                "description": "d",
            },
        )
        c2 = client_rbac.post(
            "/api/clients",
            headers=headers,
            data={
                "name": f"LC客户B_{suffix}",
                "industry": "IT",
                "owner": "admin",
                "scale": "100",
                "phase": "成交",
                "description": "d",
            },
        )
        assert c1.status_code == 200 and c2.status_code == 200
        cid_a, cid_b = c1.json()["id"], c2.json()["id"]

        with crm_main.engine.begin() as conn:
            conn.execute(
                text("UPDATE clients SET delivery_owner_user_id = :uid WHERE id = :cid"),
                {"uid": uid_a, "cid": cid_a},
            )
            conn.execute(
                text("UPDATE clients SET delivery_owner_user_id = :uid WHERE id = :cid"),
                {"uid": uid_b, "cid": cid_b},
            )

        _set_role_data_scope(
            crm_main.engine,
            ROLE_DELIVERY,
            RESOURCE_DELIVERY_EMPLOYEE_FILES,
            "write",
            SCOPE_ASSIGNED,
        )

        login_a = client_rbac.post(
            "/api/auth/login", json={"username": delivery_a, "password": "pass1234"}
        )
        cookies = login_a.cookies
        count_b_before = _count_employee_files(crm_main.engine, cid_b)

        cross = client_rbac.post(
            f"/api/clients/{cid_b}/delivery/employee-files",
            cookies=cookies,
            files=[("files", ("cross.pdf", _MIN_PDF, "application/pdf"))],
            data={
                "document_type": "劳动合同",
                "employee_full_name": "越权",
                "employee_contact_info": "13800000099",
            },
        )
        assert cross.status_code == 404
        assert _count_employee_files(crm_main.engine, cid_b) == count_b_before


class TestLaborContractFrontendStatic:
    def test_js_contains_renewal_flow(self):
        js = (ROOT / "static/js/pages/delivery-detail-employee-files.js").read_text(encoding="utf-8")
        for token in (
            "confirm_same_year_renewal",
            "same_year_labor_contract_exists",
            "该员工已在本年上传过合同，是否为同年续约？",
            "劳动合同每次只能上传 1 个文件",
        ):
            assert token in js

    def test_html_contains_labor_contract_fields(self):
        html = (ROOT / "templates/pages/delivery_detail.html").read_text(encoding="utf-8")
        for token in ("劳动合同", "员工姓名", "手机号", "合同签署日期", "合同有效期至", "isLaborContractUpload"):
            assert token in html
