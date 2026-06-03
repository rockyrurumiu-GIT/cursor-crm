"""RBAC API coverage: RESTRICTED user gets 403 per business module."""
from __future__ import annotations

import importlib
import os

import pytest
from starlette.testclient import TestClient

from tests.helpers import auth_header


@pytest.fixture(scope="module")
def client_rbac(_test_env):
    import os as _os

    _os.environ["CRM_AUTH_MODE"] = "rbac"
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _create_restricted(client, admin_user: str, admin_pwd: str, suffix: str):
    headers = {**auth_header(admin_user, admin_pwd), "Content-Type": "application/json"}
    username = f"rbac_mod_{suffix}"
    r = client.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": username,
            "password": "restricted1",
            "display_name": "R",
            "role_codes": ["RESTRICTED"],
        },
    )
    if r.status_code == 400 and "已存在" in r.text:
        return username, "restricted1"
    assert r.status_code == 200, r.text
    return username, "restricted1"


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture(scope="module")
def restricted_session(client_rbac, admin_auth):
    user, pwd = admin_auth
    suffix = f"mods_{os.getpid()}"
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    created = client_rbac.post(
        "/api/clients",
        headers=auth_header(user, pwd),
        data={
            "name": f"RBAC Mod Client {suffix}",
            "industry": "IT",
            "owner": user,
            "scale": "M",
            "phase": "active",
            "description": "rbac test",
        },
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    _create_restricted(client_rbac, user, pwd, suffix)
    login = _login(client_rbac, f"rbac_mod_{suffix}", "restricted1")
    assert login.status_code == 200
    return client_rbac, login.cookies, cid


def _assert_forbidden(resp, code: str):
    assert resp.status_code == 403, resp.text
    assert code in resp.json().get("detail", "")


@pytest.mark.parametrize(
    "read_path,read_perm,write_method,write_path,write_perm,write_json",
    [
        (
            "/api/opportunities",
            "crm.opportunities.read",
            "post",
            "/api/opportunities",
            "crm.opportunities.write",
            lambda cid: {"client_id": cid, "name": "Blocked Opp", "stage": "initial"},
        ),
        (
            "/api/contacts",
            "crm.contacts.read",
            "post",
            "/api/contacts",
            "crm.contacts.write",
            lambda cid: {"client_id": cid, "name": "Blocked Contact"},
        ),
        (
            "/api/customer-visits",
            "crm.visits.read",
            "post",
            "/api/customer-visits",
            "crm.visits.write",
            lambda cid: {
                "client_id": cid,
                "week_period": "2026w21",
                "region": "SZ",
                "city": "SZ",
                "visit_purpose": "test",
            },
        ),
        (
            None,
            "delivery.roster.read",
            "post",
            None,
            "delivery.roster.write",
            lambda cid: {"full_name": "Blocked"},
        ),
        (
            None,
            "delivery.pipeline.read",
            "post",
            None,
            "delivery.pipeline.write",
            lambda cid: {"period": "2026-05", "position": "Dev", "region": "SZ"},
        ),
        (
            None,
            "delivery.handbook.read",
            "patch",
            None,
            "delivery.handbook.write",
            lambda cid: {"version_label": "x"},
        ),
        (
            None,
            "delivery.interviews.read",
            "post",
            None,
            "delivery.interviews.write",
            lambda cid: {"candidate_name": "Blocked"},
        ),
        (
            "/api/delivery/settlement",
            "delivery.settlement.read",
            "post",
            "/api/delivery/settlement",
            "delivery.settlement.write",
            lambda _cid: {"customer_name": "X", "fee_month": "2026-05", "amount": "1"},
        ),
        (
            "/api/handoff/config",
            "delivery.handoff.read",
            "post",
            None,
            "delivery.handoff.write",
            lambda _cid: {},
        ),
        (
            "/api/rms/jobs",
            "rms.jobs.read",
            "post",
            "/api/rms/jobs",
            "rms.jobs.write",
            lambda cid: {
                "client_id": cid,
                "title": "Blocked RMS Job",
                "owner_user_id": 1,
            },
        ),
        (
            "/api/rms/candidates",
            "rms.candidates.read",
            "post",
            "/api/rms/candidates",
            "rms.candidates.write",
            lambda _cid: {"name": "Blocked RMS Cand"},
        ),
        (
            "/api/rms/applications",
            "rms.applications.read",
            "post",
            "/api/rms/applications",
            "rms.applications.write",
            lambda _cid: {"job_id": 1, "candidate_id": 1},
        ),
    ],
)
def test_restricted_module_forbidden(
    restricted_session,
    read_path,
    read_perm,
    write_method,
    write_path,
    write_perm,
    write_json,
):
    client, cookies, cid = restricted_session
    if read_path is None:
        if "roster" in read_perm:
            read_path = f"/api/clients/{cid}/roster"
        elif "pipeline" in read_perm:
            read_path = f"/api/clients/{cid}/delivery/pipeline"
        elif "handbook" in read_perm:
            read_path = f"/api/clients/{cid}/delivery/handbooks"
        elif "interviews" in read_perm:
            read_path = f"/api/clients/{cid}/delivery/interviews"
    _assert_forbidden(client.get(read_path, cookies=cookies), read_perm)

    if write_path is None:
        if "roster" in write_perm:
            write_path = f"/api/clients/{cid}/roster"
        elif "pipeline" in write_perm:
            write_path = f"/api/clients/{cid}/delivery/pipeline"
        elif "handbook" in write_perm:
            write_path = f"/api/clients/{cid}/delivery/handbooks/999999"
        elif "interviews" in write_perm:
            write_path = f"/api/clients/{cid}/delivery/interviews"
        elif "handoff" in write_perm:
            write_path = f"/api/clients/{cid}/handoffs"
    body = write_json(cid)
    if write_method == "post":
        r = client.post(write_path, cookies=cookies, json=body)
    else:
        r = client.patch(write_path, cookies=cookies, json=body)
    _assert_forbidden(r, write_perm)
