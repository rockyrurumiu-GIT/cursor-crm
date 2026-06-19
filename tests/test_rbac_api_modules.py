"""RBAC API coverage: RESTRICTED user gets 403 per business module."""
from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.password import hash_password
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


def _create_user(client, admin_user: str, admin_pwd: str, username: str, role_codes: list[str], password: str):
    import main as crm_main

    salt_b64, hash_b64, iters = hash_password(password)
    with crm_main.engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM sys_user WHERE username = :u"), {"u": username}).fetchone()
        if row:
            uid = int(row[0])
            conn.execute(
                text(
                    "UPDATE sys_user SET password_hash = :h, password_salt = :s, "
                    "password_iters = :i, status = 'active', updated_at = datetime('now') "
                    "WHERE id = :uid"
                ),
                {"h": hash_b64, "s": salt_b64, "i": iters, "uid": uid},
            )
        else:
            conn.execute(
                text(
                    "INSERT INTO sys_user (username, display_name, password_hash, password_salt, "
                    "password_iters, status, session_version, created_at, updated_at) "
                    "VALUES (:u, :dn, :h, :s, :i, 'active', 0, datetime('now'), datetime('now'))"
                ),
                {"u": username, "dn": username, "h": hash_b64, "s": salt_b64, "i": iters},
            )
            uid = int(conn.execute(text("SELECT id FROM sys_user WHERE username = :u"), {"u": username}).fetchone()[0])
        for code in role_codes:
            rid = conn.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": code}).fetchone()
            assert rid is not None
            conn.execute(
                text("INSERT OR IGNORE INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"),
                {"uid": uid, "rid": int(rid[0])},
            )


def _create_role_with_permissions(
    role_code: str,
    permission_codes: list[str],
    data_scopes: list[tuple[str, str, str]] | None = None,
) -> None:
    import main as crm_main

    with crm_main.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR IGNORE INTO sys_role (code, name, description, is_builtin, created_at) "
                "VALUES (:code, :name, '', 0, datetime('now'))"
            ),
            {"code": role_code, "name": role_code},
        )
        rid = int(conn.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": role_code}).fetchone()[0])
        for perm in permission_codes:
            pid = conn.execute(text("SELECT id FROM sys_permission WHERE code = :p"), {"p": perm}).fetchone()
            assert pid is not None
            conn.execute(
                text("INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id) VALUES (:rid, :pid)"),
                {"rid": rid, "pid": int(pid[0])},
            )
        for resource_code, action, scope_type in data_scopes or []:
            conn.execute(
                text(
                    "INSERT OR REPLACE INTO sys_role_data_scope "
                    "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                    "VALUES (:rid, :rc, :act, :scope, datetime('now'), datetime('now'))"
                ),
                {"rid": rid, "rc": resource_code, "act": action, "scope": scope_type},
            )


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _insert_client(name: str, owner: str) -> int:
    import main as crm_main

    with crm_main.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clients (name, industry, owner, scale, phase, description, created_at) "
                "VALUES (:name, 'IT', :owner, 'M', '初步接触', 'rbac readonly test', datetime('now'))"
            ),
            {"name": name, "owner": owner},
        )
        return int(conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0])


def _insert_visit(client_id: int) -> None:
    import main as crm_main

    with crm_main.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO visits (client_id, date, location, content, created_at) "
                "VALUES (:cid, '2026-06-17', 'SZ', 'hidden visit', datetime('now'))"
            ),
            {"cid": client_id},
        )


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
            "delivery.employee_files.read",
            "patch",
            None,
            "delivery.employee_files.write",
            lambda cid: {"status": "published"},
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
        elif "employee_files" in read_perm:
            read_path = f"/api/clients/{cid}/delivery/employee-files"
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
        elif "employee_files" in write_perm:
            write_path = f"/api/clients/{cid}/delivery/employee-files/999999"
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


def test_client_readonly_user_cannot_open_or_call_write_surfaces(client_rbac, admin_auth):
    admin_user, admin_pwd = admin_auth
    suffix = f"client_ro_{os.getpid()}"
    viewer = f"client_ro_{suffix}"
    viewer_pwd = "readonly1"
    role_code = f"CLIENT_READ_ONLY_{os.getpid()}"
    _create_role_with_permissions(
        role_code,
        ["crm.clients.read"],
        [("crm.client", "read", "all")],
    )
    _create_user(client_rbac, admin_user, admin_pwd, viewer, [role_code], viewer_pwd)

    cid = _insert_client(f"Readonly Client {suffix}", admin_user)
    _insert_visit(cid)

    login = _login(client_rbac, viewer, viewer_pwd)
    assert login.status_code == 200, login.text
    cookies = login.cookies

    assert client_rbac.get("/customers", cookies=cookies).status_code == 200
    _assert_forbidden(client_rbac.get("/tools/calc", cookies=cookies), "tools.gm_calc.read")
    _assert_forbidden(client_rbac.get("/api/gm/insurance-locations", cookies=cookies), "tools.gm_calc.read")
    _assert_forbidden(client_rbac.get("/contacts/all", cookies=cookies), "crm.contacts.read")
    _assert_forbidden(client_rbac.get("/contacts/tags", cookies=cookies), "crm.contacts.read")
    _assert_forbidden(client_rbac.get("/contacts/import", cookies=cookies), "crm.contacts.read")
    _assert_forbidden(client_rbac.get("/customers/visits", cookies=cookies), "crm.visits.read")
    _assert_forbidden(client_rbac.get("/customers/new", cookies=cookies), "crm.clients.write")
    _assert_forbidden(client_rbac.get(f"/customers/{cid}/edit", cookies=cookies), "crm.clients.write")
    _assert_forbidden(client_rbac.get("/api/export/clients", cookies=cookies), "crm.clients.write")
    _assert_forbidden(client_rbac.get(f"/customers/{cid}/handoff", cookies=cookies), "delivery.handoff.read")
    _assert_forbidden(client_rbac.get("/customers/reviews", cookies=cookies), "delivery.handoff.review")
    details = client_rbac.get(f"/api/clients/{cid}/details", cookies=cookies)
    assert details.status_code == 200, details.text
    assert details.json()["visits"] == []

    post_resp = client_rbac.post(
        "/api/clients",
        cookies=cookies,
        data={
            "name": f"Blocked Client {suffix}",
            "industry": "IT",
            "owner": viewer,
            "scale": "S",
            "phase": "初步接触",
            "description": "blocked",
        },
    )
    _assert_forbidden(post_resp, "crm.clients.write")

    put_resp = client_rbac.put(
        f"/api/clients/{cid}",
        cookies=cookies,
        data={
            "name": f"Readonly Client {suffix}",
            "industry": "IT",
            "owner": admin_user,
            "scale": "M",
            "phase": "初步接触",
            "description": "blocked update",
        },
    )
    _assert_forbidden(put_resp, "crm.clients.write")

    delete_resp = client_rbac.delete(f"/api/clients/{cid}", cookies=cookies)
    _assert_forbidden(delete_resp, "crm.clients.delete")


def test_gm_calc_permission_allows_page_and_read_api(client_rbac, admin_auth):
    admin_user, admin_pwd = admin_auth
    suffix = f"gm_calc_{os.getpid()}"
    user = f"gm_calc_{suffix}"
    user_pwd = "gmcalc1"
    role_code = f"GM_CALC_READ_{os.getpid()}"
    _create_role_with_permissions(role_code, ["tools.gm_calc.read"])
    _create_user(client_rbac, admin_user, admin_pwd, user, [role_code], user_pwd)

    login = _login(client_rbac, user, user_pwd)
    assert login.status_code == 200, login.text
    cookies = login.cookies

    page = client_rbac.get("/tools/calc", cookies=cookies)
    assert page.status_code == 200, page.text
    api = client_rbac.get("/api/gm/insurance-locations", cookies=cookies)
    assert api.status_code == 200, api.text


def test_handoff_page_permissions_are_split_by_read_and_review(client_rbac, admin_auth):
    admin_user, admin_pwd = admin_auth
    suffix = f"handoff_page_{os.getpid()}"
    cid = _insert_client(f"Handoff Page Client {suffix}", admin_user)

    read_role = f"HANDOFF_READ_{os.getpid()}"
    read_user = f"handoff_read_{os.getpid()}"
    read_pwd = "handoffread1"
    _create_role_with_permissions(read_role, ["delivery.handoff.read"])
    _create_user(client_rbac, admin_user, admin_pwd, read_user, [read_role], read_pwd)
    read_login = _login(client_rbac, read_user, read_pwd)
    assert read_login.status_code == 200, read_login.text
    assert client_rbac.get(f"/customers/{cid}/handoff", cookies=read_login.cookies).status_code == 200
    _assert_forbidden(client_rbac.get("/customers/reviews", cookies=read_login.cookies), "delivery.handoff.review")

    review_role = f"HANDOFF_REVIEW_{os.getpid()}"
    review_user = f"handoff_review_{os.getpid()}"
    review_pwd = "handoffreview1"
    _create_role_with_permissions(review_role, ["delivery.handoff.review"])
    _create_user(client_rbac, admin_user, admin_pwd, review_user, [review_role], review_pwd)
    review_login = _login(client_rbac, review_user, review_pwd)
    assert review_login.status_code == 200, review_login.text
    assert client_rbac.get("/customers/reviews", cookies=review_login.cookies).status_code == 200
    _assert_forbidden(
        client_rbac.get(f"/customers/{cid}/handoff", cookies=review_login.cookies),
        "delivery.handoff.read",
    )
