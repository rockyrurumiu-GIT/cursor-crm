"""RMS Phase 6B: Offer approval workflow tests."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY, ROLE_SALES, ROLE_SUPER_ADMIN, ROLE_VIEWER
from tests.helpers import auth_header
from tests.test_rms_application_workflow import _create_recommended_application
from tests.test_rms_phase2_mvp import (
    RMS_MVP_PERMS,
    _create_user,
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _grant_role_permissions,
    _login,
    _revoke_role_permissions,
    _set_role_data_scope,
    _trial_job_and_candidate,
    _user_id,
)

OFFER_BODY = {
    "full_name": "测试候选人",
    "contact_info": "13800138000",
    "customer_name": "测试客户",
    "work_location": "上海",
    "position_title": "工程师",
    "monthly_quote_tax": "30000",
    "quote_tax_unit": "人月",
    "pre_tax_salary": "20000",
    "probation_days": "90",
    "probation_discount_months": "1",
    "gm_amount": "5000",
    "gm_pct": "15",
    "planned_onboard_date": "2026-07-01",
    "quote_confirm_attachment": "rms/offer_quotes/test/quote.png",
}


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


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def approvers_config(client_rbac, admin_auth):
    def _install(dept_uid: int, ops_uid: int, gm_uid: int):
        headers = {**auth_header(admin_auth[0], admin_auth[1]), "Content-Type": "application/json"}
        r = client_rbac.put(
            "/api/rms/offer-approval-config/default",
            headers=headers,
            json={
                "dept_superior_user_id": dept_uid,
                "ops_head_user_id": ops_uid,
                "gm_user_id": gm_uid,
            },
        )
        assert r.status_code == 200, r.text

    return _install


def _advance_to_pending_offer(client, login, app_id: int) -> None:
    client.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed"},
    )
    for st in (
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
    ):
        r = client.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": st},
        )
        assert r.status_code == 200, r.text


def _create_approver_users(client, admin_auth, uniq: str) -> tuple[int, int, int]:
    dept = f"offer_dept_{uniq}"
    ops = f"offer_ops_{uniq}"
    gm = f"offer_gm_{uniq}"
    dept_uid = _create_user(client, admin_auth, dept, [ROLE_VIEWER])
    ops_uid = _create_user(client, admin_auth, ops, [ROLE_VIEWER])
    gm_uid = _create_user(client, admin_auth, gm, [ROLE_VIEWER])
    return dept_uid, ops_uid, gm_uid


def _submit_offer(client, login, app_id: int, **overrides):
    body = dict(OFFER_BODY)
    body.update(overrides)
    return client.post(
        f"/api/rms/applications/{app_id}/offer-approval",
        cookies=login.cookies,
        json=body,
    )


def _approve_as(client, username: str, offer_id: int):
    login = _login(client, username)
    assert login.status_code == 200
    return client.post(
        f"/api/rms/offers/{offer_id}/approve",
        cookies=login.cookies,
        json={"comment": "ok"},
    )


def test_offer_approval_draft_returns_prefill(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"draft_{uniq}")
    _advance_to_pending_offer(client_rbac, login, app_id)

    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/offer-approval-draft",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    payload = r.json().get("offer_payload") or {}
    assert payload.get("full_name")
    assert payload.get("customer_name")
    assert payload.get("position_title")


def test_offer_approval_draft_denied_without_read(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"draft_ro_{uniq}")
    _advance_to_pending_offer(client_rbac, login, app_id)

    viewer = f"offer_draft_view_{uniq}"
    _create_user(client_rbac, admin_auth, viewer, [ROLE_VIEWER])
    _revoke_role_permissions(rms_engine, ROLE_VIEWER, ("rms.applications.read",))

    viewer_login = _login(client_rbac, viewer)
    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/offer-approval-draft",
        cookies=viewer_login.cookies,
    )
    assert r.status_code == 403


def test_gm_pct_15_generates_two_steps(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"o2_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    r = _submit_offer(client_rbac, login, app_id, gm_pct="15")
    assert r.status_code == 200, r.text
    offer_id = r.json()["id"]

    with rms_engine.connect() as conn:
        steps = conn.execute(
            text(
                "SELECT step_type FROM rms_offer_approval_steps WHERE offer_record_id = :oid ORDER BY step_order"
            ),
            {"oid": offer_id},
        ).fetchall()
    assert [s[0] for s in steps] == ["dept_superior", "ops_head"]


def test_gm_pct_below_15_generates_three_steps(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"o3_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    r = _submit_offer(client_rbac, login, app_id, gm_pct="14")
    assert r.status_code == 200, r.text
    offer_id = r.json()["id"]

    with rms_engine.connect() as conn:
        steps = conn.execute(
            text(
                "SELECT step_type FROM rms_offer_approval_steps WHERE offer_record_id = :oid ORDER BY step_order"
            ),
            {"oid": offer_id},
        ).fetchall()
    assert len(steps) == 3
    assert steps[-1][0] == "gm"


def test_submit_moves_application_to_offer_approval_pending(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"os_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    submitted = _submit_offer(client_rbac, login, app_id)
    assert submitted.status_code == 200, submitted.text
    offer = submitted.json()

    assert offer["quote_tax_display"] == "30,000 (人月)"
    assert offer["pending_approver_label"]
    assert dept_user in offer["pending_approver_label"]

    app = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()
    assert app["status"] == "offer_approval_pending"
    assert app["offer_current_approval_node_label"] == "部门上级审批中"
    assert dept_user in app["offer_pending_approver_label"]

    listed = client_rbac.get("/api/rms/offers?status=pending", cookies=login.cookies).json()
    row = next(o for o in listed if o["id"] == offer["id"])
    assert row["pending_approver_label"]
    assert dept_user in row["pending_approver_label"]


def test_submit_offer_requires_quote_confirm_attachment(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"att_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    body = dict(OFFER_BODY)
    body.pop("quote_confirm_attachment", None)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/offer-approval",
        cookies=login.cookies,
        json=body,
    )
    assert r.status_code == 400, r.text
    assert "客户报价确认" in r.json()["detail"]


_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def test_offer_quote_attachment_exposed_and_served(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"qa_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _grant_role_permissions(rms_engine, ROLE_VIEWER, ("rms.applications.read",))
    _advance_to_pending_offer(client_rbac, login, app_id)

    uploaded = client_rbac.post(
        f"/api/rms/applications/{app_id}/offer-quote-attachment",
        cookies=login.cookies,
        files={"file": ("quote.png", _PNG_1X1, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    rel_path = uploaded.json()["path"]

    offer_id = _submit_offer(client_rbac, login, app_id, quote_confirm_attachment=rel_path).json()["id"]

    dept_login = _login(client_rbac, dept_user)
    listed = client_rbac.get("/api/rms/offers?status=pending", cookies=dept_login.cookies).json()
    row = next(o for o in listed if o["id"] == offer_id)
    assert row["quote_confirm_attachment"] == rel_path
    assert row["quote_confirm_attachment_url"] == f"/api/rms/offers/{offer_id}/quote-attachment"

    served = client_rbac.get(row["quote_confirm_attachment_url"], cookies=dept_login.cookies)
    assert served.status_code == 200, served.text
    assert served.headers["content-type"] == "image/png"
    assert served.content == _PNG_1X1

    outsider = f"offer_qa_out_{uniq}"
    _create_user(client_rbac, admin_auth, outsider, [ROLE_VIEWER])
    out_login = _login(client_rbac, outsider)
    forbidden = client_rbac.get(row["quote_confirm_attachment_url"], cookies=out_login.cookies)
    assert forbidden.status_code == 403


def test_full_approval_moves_to_onboarding(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"full_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    ops_user = f"offer_ops_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    submitted = _submit_offer(client_rbac, login, app_id)
    offer_id = submitted.json()["id"]

    assert _approve_as(client_rbac, dept_user, offer_id).status_code == 200
    assert _approve_as(client_rbac, ops_user, offer_id).status_code == 200

    app = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()
    assert app["status"] == "onboarding"

    offers = client_rbac.get("/api/rms/offers?status=approved", cookies=login.cookies)
    assert offers.status_code == 200
    assert any(o["id"] == offer_id and o["status"] == "approved" for o in offers.json())


def test_reject_returns_to_pending_offer_not_in_offer_tab(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"rej_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]
    dept_login = _login(client_rbac, dept_user)
    rej = client_rbac.post(
        f"/api/rms/offers/{offer_id}/reject",
        cookies=dept_login.cookies,
        json={"reason": "薪资过高"},
    )
    assert rej.status_code == 200, rej.text

    app = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()
    assert app["status"] == "pending_offer"

    listed = client_rbac.get("/api/rms/offers", cookies=login.cookies).json()
    assert offer_id not in [o["id"] for o in listed]


def test_duplicate_pending_submission_blocked(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"dup_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    assert _submit_offer(client_rbac, login, app_id).status_code == 200
    dup = _submit_offer(client_rbac, login, app_id)
    assert dup.status_code in (400, 409)


def test_drop_offer_requires_reason(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"drop_{uniq}")
    _advance_to_pending_offer(client_rbac, login, app_id)

    bad = client_rbac.post(
        f"/api/rms/applications/{app_id}/drop-offer",
        cookies=login.cookies,
        json={"reason": ""},
    )
    assert bad.status_code == 400

    ok = client_rbac.post(
        f"/api/rms/applications/{app_id}/drop-offer",
        cookies=login.cookies,
        json={"reason": "候选人拒offer"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["application"]["status"] == "offer_dropped"

    listed = client_rbac.get("/api/rms/offers?status=offer_dropped", cookies=login.cookies).json()
    assert any(o["application_id"] == app_id for o in listed)


def test_transit_lost_requires_reason_and_onboarding_lost_record(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"tl_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]
    _approve_as(client_rbac, f"offer_dept_{uniq}", offer_id)
    _approve_as(client_rbac, f"offer_ops_{uniq}", offer_id)

    bad = client_rbac.post(
        f"/api/rms/applications/{app_id}/transit-lost",
        cookies=login.cookies,
        json={"reason": ""},
    )
    assert bad.status_code == 400

    ok = client_rbac.post(
        f"/api/rms/applications/{app_id}/transit-lost",
        cookies=login.cookies,
        json={"reason": "候选人放弃入职"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["application"]["status"] == "onboarding_lost"

    listed = client_rbac.get("/api/rms/offers?status=onboarding_lost", cookies=login.cookies).json()
    assert any(o["application_id"] == app_id and o["status"] == "onboarding_lost" for o in listed)


def test_non_approver_cannot_approve(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"na_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]

    outsider = f"offer_out_{uniq}"
    _create_user(client_rbac, admin_auth, outsider, [ROLE_DELIVERY])
    out_login = _login(client_rbac, outsider)
    r = client_rbac.post(
        f"/api/rms/offers/{offer_id}/approve",
        cookies=out_login.cookies,
        json={"comment": ""},
    )
    assert r.status_code == 403


def test_approver_without_write_can_approve(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"rw_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _revoke_role_permissions(rms_engine, ROLE_VIEWER, RMS_MVP_PERMS)
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]

    r = _approve_as(client_rbac, dept_user, offer_id)
    assert r.status_code == 200, r.text


def test_readonly_user_cannot_submit_offer(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    readonly = f"offer_ro_{uniq}"
    _create_user(client_rbac, admin_auth, readonly, [ROLE_VIEWER])
    _revoke_role_permissions(rms_engine, ROLE_VIEWER, ("rms.applications.write",))

    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"ro_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)

    ro_login = _login(client_rbac, readonly)
    r = _submit_offer(client_rbac, ro_login, app_id)
    assert r.status_code == 403


def test_missing_approver_config_fail_closed(client_rbac, admin_auth, rms_engine, uniq):
    from services.rms_offer_approval_config import OFFER_APPROVAL_CONFIG_INCOMPLETE

    with rms_engine.begin() as conn:
        conn.execute(text("DELETE FROM rms_offer_approval_configs"))

    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"miss_{uniq}")
    _advance_to_pending_offer(client_rbac, login, app_id)
    r = _submit_offer(client_rbac, login, app_id)
    assert r.status_code == 409
    assert r.json()["detail"] == OFFER_APPROVAL_CONFIG_INCOMPLETE


def test_correction_from_offer_approval_pending_blocked(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"corr_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    _submit_offer(client_rbac, login, app_id)

    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "onboarding", "mode": "correction", "note": "试图绕过"},
    )
    assert r.status_code == 400


def test_pending_offer_cannot_transition_to_onboarding(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"direct_{uniq}")
    _advance_to_pending_offer(client_rbac, login, app_id)

    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "onboarding"},
    )
    assert r.status_code == 400


def test_offer_record_created_by_tracks_submitter_not_recruiter(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    suffix = f"creator_{uniq}"
    login_del, job_id, cand_id, _cid = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    sales_user = f"rms2_app_s_{suffix}"
    sales_uid = _user_id(rms_engine, sales_user)
    delivery_uid = _user_id(rms_engine, f"rms2_app_d_{suffix}")
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    app_id = int(created.json()["id"])
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_by = :uid WHERE id = :id"),
            {"uid": sales_uid, "id": app_id},
        )
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login_del, app_id)
    r = _submit_offer(client_rbac, login_del, app_id)
    assert r.status_code == 200, r.text

    with rms_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                  r.id AS offer_record_id,
                  r.application_id,
                  r.created_by,
                  u.username AS applicant_username,
                  a.recommended_by,
                  ru.username AS recruiter_username
                FROM rms_offer_records r
                LEFT JOIN sys_user u ON u.id = r.created_by
                LEFT JOIN rms_applications a ON a.id = r.application_id
                LEFT JOIN sys_user ru ON ru.id = a.recommended_by
                WHERE r.application_id = :aid
                """
            ),
            {"aid": app_id},
        ).mappings().first()
    assert row is not None
    assert int(row["created_by"]) == delivery_uid
    assert int(row["recommended_by"]) == sales_uid
    assert row["applicant_username"] == f"rms2_app_d_{suffix}"
    assert row["recruiter_username"] == sales_user


def test_non_delivery_submitter_cannot_load_offer_draft(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    suffix = f"ndown_{uniq}"
    login_del, job_id, cand_id, _cid = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    sales_user = f"rms2_app_s_{suffix}"
    sales_uid = _user_id(rms_engine, sales_user)
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    app_id = int(created.json()["id"])
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_applications SET recommended_by = :uid WHERE id = :id"),
            {"uid": sales_uid, "id": app_id},
        )
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login_del, app_id)

    _grant_role_permissions(rms_engine, ROLE_SALES, ("rms.applications.read",))
    try:
        login_sales = _login(client_rbac, sales_user)
        assert login_sales.status_code == 200
        r = client_rbac.get(
            f"/api/rms/applications/{app_id}/offer-approval-draft",
            cookies=login_sales.cookies,
        )
        assert r.status_code == 403

        listed = client_rbac.get("/api/rms/applications", cookies=login_sales.cookies)
        assert listed.status_code == 200, listed.text
        found = next((a for a in listed.json() if a["id"] == app_id), None)
        assert found is not None
        assert found["can_submit_offer_approval"] is False
    finally:
        _revoke_role_permissions(rms_engine, ROLE_SALES, ("rms.applications.read",))


def test_can_act_as_offer_submitter_service_rules(
    client_rbac, admin_auth, rms_engine, uniq
):
    import main as crm_main
    from auth.service import AuthContext
    from services.rms_scope import can_act_as_offer_submitter

    suffix = f"auth_{uniq}"
    _login_del, _job_id, _cand_id, cid = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    sales_user = f"rms2_app_s_{suffix}"
    delivery_user = f"rms2_app_d_{suffix}"
    sales_uid = _user_id(rms_engine, sales_user)
    delivery_uid = _user_id(rms_engine, delivery_user)

    with rms_engine.connect() as conn:
        client_row = conn.execute(
            text("SELECT delivery_owner_user_id, delivery_dept_id FROM clients WHERE id = :cid"),
            {"cid": cid},
        ).mappings().first()

    delivery_ctx = AuthContext(
        username=delivery_user,
        user_id=delivery_uid,
        roles=[ROLE_DELIVERY],
        permissions=set(RMS_MVP_PERMS),
    )
    sales_ctx = AuthContext(
        username=sales_user,
        user_id=sales_uid,
        roles=[ROLE_SALES],
        permissions={"rms.applications.read", "rms.applications.write"},
    )
    delegate_ctx = AuthContext(
        username=sales_user,
        user_id=sales_uid,
        roles=[ROLE_SALES],
        permissions={"rms.applications.read", "rms.applications.write", "rms.offer_approval.submit"},
    )

    class _Client:
        delivery_owner_user_id = client_row["delivery_owner_user_id"]
        delivery_dept_id = client_row["delivery_dept_id"]

    stub_client = _Client()
    with crm_main.SessionLocal() as db:
        assert can_act_as_offer_submitter(db, delivery_ctx, stub_client) is True
        assert can_act_as_offer_submitter(db, sales_ctx, stub_client) is False
        assert can_act_as_offer_submitter(db, delegate_ctx, stub_client) is True


def test_notifications_readable_without_handoff_permission(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"ntf_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _revoke_role_permissions(rms_engine, ROLE_VIEWER, ("delivery.handoff.read",))
    _advance_to_pending_offer(client_rbac, login, app_id)
    _submit_offer(client_rbac, login, app_id)

    dept_login = _login(client_rbac, dept_user)
    r = client_rbac.get("/api/notifications", cookies=dept_login.cookies)
    assert r.status_code == 200, r.text
    items = r.json()
    assert items
    assert items[0].get("link_url")
    assert items[0].get("offer_record_id")
    assert items[0].get("application_id") == app_id


def test_notifications_username_isolation(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"iso_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    _submit_offer(client_rbac, login, app_id)

    outsider = f"offer_iso_out_{uniq}"
    _create_user(client_rbac, admin_auth, outsider, [ROLE_VIEWER])
    out_login = _login(client_rbac, outsider)
    listed = client_rbac.get("/api/notifications", cookies=out_login.cookies).json()
    assert all(n.get("type") != "rms_offer_pending" for n in listed)


def test_notifications_delete_single_and_all(client_rbac, admin_auth, rms_engine, uniq, approvers_config):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"del_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    _submit_offer(client_rbac, login, app_id)

    dept_login = _login(client_rbac, dept_user)
    items = client_rbac.get("/api/notifications", cookies=dept_login.cookies).json()
    assert items
    nid = items[0]["id"]

    r = client_rbac.delete(f"/api/notifications/{nid}", cookies=dept_login.cookies)
    assert r.status_code == 200, r.text
    remaining = client_rbac.get("/api/notifications", cookies=dept_login.cookies).json()
    assert all(n["id"] != nid for n in remaining)

    r_all = client_rbac.delete("/api/notifications", cookies=dept_login.cookies)
    assert r_all.status_code == 200, r_all.text
    assert client_rbac.get("/api/notifications", cookies=dept_login.cookies).json() == []


def test_pending_approver_lists_offer_without_application_read_scope(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    from auth.data_scope_catalog import RESOURCE_RMS_APPLICATION, SCOPE_NONE

    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"scope_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _grant_role_permissions(rms_engine, ROLE_VIEWER, ("rms.applications.read",))
    _set_role_data_scope(rms_engine, ROLE_VIEWER, RESOURCE_RMS_APPLICATION, "read", SCOPE_NONE)
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]

    dept_login = _login(client_rbac, dept_user)
    listed = client_rbac.get("/api/rms/offers?status=pending", cookies=dept_login.cookies)
    assert listed.status_code == 200, listed.text
    assert any(o["id"] == offer_id for o in listed.json())


def test_ops_cannot_see_or_approve_before_prior_step(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"turn_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    ops_user = f"offer_ops_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]

    ops_login = _login(client_rbac, ops_user)
    listed = client_rbac.get("/api/rms/offers?status=pending", cookies=ops_login.cookies)
    assert listed.status_code == 200, listed.text
    assert offer_id not in [o["id"] for o in listed.json()]
    assert _approve_as(client_rbac, ops_user, offer_id).status_code == 403

    assert _approve_as(client_rbac, dept_user, offer_id).status_code == 200

    listed_after = client_rbac.get("/api/rms/offers?status=pending", cookies=ops_login.cookies)
    assert listed_after.status_code == 200, listed.text
    row = next(o for o in listed_after.json() if o["id"] == offer_id)
    assert row["can_approve"] is True
    assert row["current_approval_node"] == "ops_head"
    assert _approve_as(client_rbac, ops_user, offer_id).status_code == 200


def test_submitter_sees_pending_offer_without_approve_permission(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"sub_{uniq}")
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id).json()["id"]

    listed = client_rbac.get("/api/rms/offers?status=pending", cookies=login.cookies)
    assert listed.status_code == 200, listed.text
    row = next(o for o in listed.json() if o["id"] == offer_id)
    assert row["can_approve"] is False
    assert row["current_approval_node"] == "dept_superior"


def test_super_admin_prior_approver_cannot_approve_later_gm_step(
    client_rbac, admin_auth, rms_engine, uniq, approvers_config
):
    login, app_id = _create_recommended_application(client_rbac, admin_auth, rms_engine, f"gm_{uniq}")
    dept_user = f"offer_dept_{uniq}"
    ops_user = f"offer_ops_{uniq}"
    gm_user = f"offer_gm_{uniq}"
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    approvers_config(dept_uid, ops_uid, gm_uid)
    with rms_engine.begin() as conn:
        super_rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = :c"),
            {"c": ROLE_SUPER_ADMIN},
        ).scalar()
        conn.execute(
            text("INSERT OR IGNORE INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"),
            {"uid": ops_uid, "rid": super_rid},
        )
    _advance_to_pending_offer(client_rbac, login, app_id)
    offer_id = _submit_offer(client_rbac, login, app_id, gm_pct="13.76").json()["id"]

    assert _approve_as(client_rbac, dept_user, offer_id).status_code == 200
    assert _approve_as(client_rbac, ops_user, offer_id).status_code == 200

    ops_login = _login(client_rbac, ops_user)
    listed = client_rbac.get("/api/rms/offers?status=pending", cookies=ops_login.cookies)
    assert listed.status_code == 200, listed.text
    row = next(o for o in listed.json() if o["id"] == offer_id)
    assert row["current_approval_node"] == "gm"
    assert row["can_approve"] is False
    assert _approve_as(client_rbac, ops_user, offer_id).status_code == 403

    assert _approve_as(client_rbac, gm_user, offer_id).status_code == 200
    app = client_rbac.get(f"/api/rms/applications/{app_id}", cookies=login.cookies).json()
    assert app["status"] == "onboarding"
