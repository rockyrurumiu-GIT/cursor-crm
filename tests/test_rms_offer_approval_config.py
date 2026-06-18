"""RMS Phase 6B-0: Offer approval config API and resolver tests."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY, ROLE_VIEWER
from fastapi import HTTPException
from services.rms_offer_approval_config import (
    OFFER_APPROVAL_CONFIG_INCOMPLETE,
    resolve_offer_approvers,
)
from tests.helpers import auth_header
from tests.test_rms_phase2_mvp import _create_user, _login

CONFIG_URL = "/api/rms/offer-approval-config"


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


@pytest.fixture
def crm_main(client_rbac):
    import main as crm_main

    return crm_main


def _admin_headers(admin_auth):
    user, pwd = admin_auth
    return {**auth_header(user, pwd), "Content-Type": "application/json"}


def _seed_default(
    client,
    admin_auth,
    dept_uid: int | None,
    ops_uid: int | None,
    gm_uid: int | None = None,
):
    body = {
        "dept_superior_user_id": dept_uid,
        "ops_head_user_id": ops_uid,
        "gm_user_id": gm_uid,
    }
    r = client.put(
        f"{CONFIG_URL}/default",
        headers=_admin_headers(admin_auth),
        json=body,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _create_approver_users(client, admin_auth, uniq: str) -> tuple[int, int, int]:
    dept = f"oac_dept_{uniq}"
    ops = f"oac_ops_{uniq}"
    gm = f"oac_gm_{uniq}"
    dept_uid = _create_user(client, admin_auth, dept, [ROLE_VIEWER])
    ops_uid = _create_user(client, admin_auth, ops, [ROLE_VIEWER])
    gm_uid = _create_user(client, admin_auth, gm, [ROLE_VIEWER])
    return dept_uid, ops_uid, gm_uid


def _create_dept(client, admin_auth, code: str, name: str) -> int:
    r = client.post(
        "/api/system/depts",
        headers=_admin_headers(admin_auth),
        json={"code": code, "name": name, "parent_id": None, "dept_type": "delivery"},
    )
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def test_admin_can_read_config(client_rbac, admin_auth, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)

    r = client_rbac.get(CONFIG_URL, headers=_admin_headers(admin_auth))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["default"]["dept_superior_user_id"] == dept_uid
    assert data["default"]["ops_head_user_id"] == ops_uid
    assert data["default"]["gm_user_id"] == gm_uid


def test_viewer_cannot_read_config(client_rbac, admin_auth, uniq):
    viewer = f"oac_view_{uniq}"
    _create_user(client_rbac, admin_auth, viewer, [ROLE_VIEWER])
    login = _login(client_rbac, viewer)
    assert login.status_code == 200

    r = client_rbac.get(CONFIG_URL, cookies=login.cookies)
    assert r.status_code == 403


def test_save_default_config(client_rbac, admin_auth, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    saved = _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)
    assert saved["scope_key"] == "default"
    assert saved["dept_superior_user_id"] == dept_uid


def test_save_dept_override(client_rbac, admin_auth, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)
    dept_id = _create_dept(client_rbac, admin_auth, f"d_{uniq}", f"部门{uniq}")

    alt_superior = _create_user(client_rbac, admin_auth, f"oac_alt_{uniq}", [ROLE_VIEWER])
    r = client_rbac.put(
        f"{CONFIG_URL}/depts/{dept_id}",
        headers=_admin_headers(admin_auth),
        json={
            "dept_superior_user_id": alt_superior,
            "ops_head_user_id": None,
            "gm_user_id": None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["dept_id"] == dept_id
    assert r.json()["dept_superior_user_id"] == alt_superior


def test_dept_override_fallback_to_default(client_rbac, admin_auth, crm_main, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)
    dept_id = _create_dept(client_rbac, admin_auth, f"fb_{uniq}", f"回退{uniq}")

    applicant = f"oac_applicant_{uniq}"
    applicant_uid = _create_user(client_rbac, admin_auth, applicant, [ROLE_DELIVERY])
    client_rbac.put(
        f"/api/system/users/{applicant_uid}/depts",
        headers=_admin_headers(admin_auth),
        json={"dept_ids": [dept_id], "primary_dept_id": dept_id},
    )

    alt_superior = _create_user(client_rbac, admin_auth, f"oac_alt2_{uniq}", [ROLE_VIEWER])
    client_rbac.put(
        f"{CONFIG_URL}/depts/{dept_id}",
        headers=_admin_headers(admin_auth),
        json={
            "dept_superior_user_id": alt_superior,
            "ops_head_user_id": None,
            "gm_user_id": None,
        },
    )

    with crm_main.engine.connect() as conn:
        db = crm_main.SessionLocal()
        try:
            steps = resolve_offer_approvers(
                db,
                applicant_uid,
                "15",
                RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
            )
        finally:
            db.close()

    assert len(steps) == 2
    assert steps[0].approver_user_id == alt_superior
    assert steps[1].approver_user_id == ops_uid


def test_gm_pct_15_returns_two_steps(client_rbac, admin_auth, crm_main, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)

    db = crm_main.SessionLocal()
    try:
        steps = resolve_offer_approvers(
            db,
            dept_uid,
            "15",
            RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
        )
    finally:
        db.close()

    assert len(steps) == 2
    assert [s.step_type for s in steps] == ["dept_superior", "ops_head"]


def test_gm_pct_below_15_returns_three_steps(client_rbac, admin_auth, crm_main, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)

    db = crm_main.SessionLocal()
    try:
        steps = resolve_offer_approvers(
            db,
            dept_uid,
            "14",
            RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
        )
    finally:
        db.close()

    assert len(steps) == 3
    assert steps[-1].step_type == "gm"


def test_missing_dept_superior_fail_closed(client_rbac, admin_auth, crm_main, uniq):
    _, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, None, ops_uid, gm_uid)

    db = crm_main.SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            resolve_offer_approvers(
                db,
                ops_uid,
                "15",
                RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
            )
    finally:
        db.close()

    assert exc.value.status_code == 409
    assert exc.value.detail == OFFER_APPROVAL_CONFIG_INCOMPLETE


def test_missing_ops_head_fail_closed(client_rbac, admin_auth, crm_main, uniq):
    dept_uid, _, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, None, gm_uid)

    db = crm_main.SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            resolve_offer_approvers(
                db,
                dept_uid,
                "15",
                RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
            )
    finally:
        db.close()

    assert exc.value.status_code == 409


def test_low_gm_missing_gm_fail_closed(client_rbac, admin_auth, crm_main, uniq):
    dept_uid, ops_uid, _ = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, None)

    db = crm_main.SessionLocal()
    try:
        with pytest.raises(HTTPException) as exc:
            resolve_offer_approvers(
                db,
                dept_uid,
                "10",
                RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
            )
    finally:
        db.close()

    assert exc.value.status_code == 409
    assert exc.value.detail == OFFER_APPROVAL_CONFIG_INCOMPLETE


def test_delete_dept_override_restores_default(client_rbac, admin_auth, crm_main, uniq):
    dept_uid, ops_uid, gm_uid = _create_approver_users(client_rbac, admin_auth, uniq)
    _seed_default(client_rbac, admin_auth, dept_uid, ops_uid, gm_uid)
    dept_id = _create_dept(client_rbac, admin_auth, f"del_{uniq}", f"删除{uniq}")

    applicant = f"oac_app2_{uniq}"
    applicant_uid = _create_user(client_rbac, admin_auth, applicant, [ROLE_DELIVERY])
    client_rbac.put(
        f"/api/system/users/{applicant_uid}/depts",
        headers=_admin_headers(admin_auth),
        json={"dept_ids": [dept_id], "primary_dept_id": dept_id},
    )

    alt_superior = _create_user(client_rbac, admin_auth, f"oac_alt3_{uniq}", [ROLE_VIEWER])
    client_rbac.put(
        f"{CONFIG_URL}/depts/{dept_id}",
        headers=_admin_headers(admin_auth),
        json={"dept_superior_user_id": alt_superior, "ops_head_user_id": None, "gm_user_id": None},
    )

    deleted = client_rbac.delete(
        f"{CONFIG_URL}/depts/{dept_id}",
        headers=_admin_headers(admin_auth),
    )
    assert deleted.status_code == 200, deleted.text

    db = crm_main.SessionLocal()
    try:
        steps = resolve_offer_approvers(
            db,
            applicant_uid,
            "15",
            RmsOfferApprovalConfig=crm_main.RMS_MODELS["RmsOfferApprovalConfig"],
        )
    finally:
        db.close()

    assert steps[0].approver_user_id == dept_uid

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM rms_offer_approval_configs WHERE dept_id = :did"),
            {"did": dept_id},
        ).fetchone()
    assert row is None
