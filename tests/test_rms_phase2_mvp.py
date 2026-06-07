"""RMS Phase 2: jobs, candidates, applications API MVP."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.data_scope_catalog import RESOURCE_RMS_APPLICATION, RESOURCE_RMS_JOB, SCOPE_ASSIGNED
from auth.permissions import ROLE_DELIVERY, ROLE_SALES, ROLE_VIEWER
from tests.helpers import auth_header

RMS_MVP_PERMS = (
    "rms.jobs.read",
    "rms.jobs.write",
    "rms.candidates.read",
    "rms.candidates.write",
    "rms.applications.read",
    "rms.applications.write",
)


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _login(client, username: str, password: str = "pass1234"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_user(client, admin_auth, username: str, role_codes: list[str], password: str = "pass1234"):
    client.cookies.clear()
    user, pwd = admin_auth
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    r = client.post(
        "/api/system/users",
        headers=headers,
        json={
            "username": username,
            "password": password,
            "display_name": username,
            "role_codes": role_codes,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _user_id(engine, username: str) -> int:
    with engine.connect() as conn:
        uid = conn.execute(
            text("SELECT id FROM sys_user WHERE username = :u"),
            {"u": username},
        ).scalar()
    assert uid is not None
    return int(uid)


def _grant_role_permissions(engine, role_code: str, perm_codes: tuple[str, ...]) -> None:
    with engine.begin() as conn:
        rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = :c"),
            {"c": role_code},
        ).scalar()
        assert rid is not None
        for code in perm_codes:
            pid = conn.execute(
                text("SELECT id FROM sys_permission WHERE code = :c"),
                {"c": code},
            ).scalar()
            if pid:
                conn.execute(
                    text(
                        "INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id) "
                        "VALUES (:r, :p)"
                    ),
                    {"r": rid, "p": pid},
                )


def _set_role_data_scope(engine, role_code: str, resource_code: str, action: str, scope_type: str) -> None:
    with engine.begin() as conn:
        rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = :c"),
            {"c": role_code},
        ).scalar()
        conn.execute(
            text(
                "DELETE FROM sys_role_data_scope "
                "WHERE role_id = :rid AND resource_code = :rc AND action = :act"
            ),
            {"rid": rid, "rc": resource_code, "act": action},
        )
        conn.execute(
            text(
                "INSERT INTO sys_role_data_scope "
                "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                "VALUES (:rid, :rc, :act, :st, datetime('now'), datetime('now'))"
            ),
            {"rid": rid, "rc": resource_code, "act": action, "st": scope_type},
        )


def _create_client_admin(client, admin_auth, name: str) -> int:
    user, pwd = admin_auth
    r = client.post(
        "/api/clients",
        headers=auth_header(user, pwd),
        data={
            "name": name,
            "industry": "IT",
            "owner": user,
            "scale": "M",
            "phase": "active",
            "description": "rms phase2",
        },
    )
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _unique_phone() -> str:
    return "1" + str(1000000000 + uuid.uuid4().int % 9000000000)


def _candidate_json(job_id: int, **overrides) -> dict:
    payload = {
        "name": "Candidate",
        "phone": _unique_phone(),
        "target_job_id": job_id,
    }
    payload.update(overrides)
    return payload


def _delivery_open_job(client, engine, admin_auth, suffix: str):
    """Create client + open job; return (delivery_login, job_id)."""
    sales = f"rms2_s_{suffix}"
    delivery = f"rms2_d_{suffix}"
    sales_uid = _create_user(client, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client, admin_auth, delivery, [ROLE_DELIVERY])
    cid = _create_client_admin(client, admin_auth, f"RMS Job {suffix}")
    _set_client_owner(engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    admin_user, admin_pwd = admin_auth
    job_r = client.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Job {suffix}",
            "owner_user_id": sales_uid,
            "delivery_owner_user_id": delivery_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    login_del = _login(client, delivery)
    return login_del, job_r.json()["id"]


def _set_client_owner(engine, client_id: int, owner_user_id: int, delivery_owner_user_id: int | None = None):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE clients SET owner_user_id = :uid WHERE id = :cid"),
            {"uid": owner_user_id, "cid": client_id},
        )
        if delivery_owner_user_id is not None:
            conn.execute(
                text("UPDATE clients SET delivery_owner_user_id = :uid WHERE id = :cid"),
                {"uid": delivery_owner_user_id, "cid": client_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE clients SET delivery_owner_user_id = NULL, delivery_dept_id = NULL "
                    "WHERE id = :cid"
                ),
                {"cid": client_id},
            )


def _set_client_recruitment(
    engine,
    client_id: int,
    *,
    recruitment_dept_id: int | None = None,
    recruitment_owner_user_id: int | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE clients SET recruitment_dept_id = :did, recruitment_owner_user_id = :uid "
                "WHERE id = :cid"
            ),
            {"did": recruitment_dept_id, "uid": recruitment_owner_user_id, "cid": client_id},
        )


def _ensure_dept(engine, dept_id: int, name: str, *, path: str, parent_id: int | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT OR REPLACE INTO sys_dept "
                "(id, name, code, parent_id, path, dept_type, status, created_at, updated_at) "
                "VALUES (:id, :name, :code, :pid, :path, 'internal', 'active', datetime('now'), datetime('now'))"
            ),
            {
                "id": dept_id,
                "name": name,
                "code": f"DEPT{dept_id}",
                "pid": parent_id,
                "path": path,
            },
        )


def _set_user_dept(engine, user_id: int, dept_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sys_user_dept WHERE user_id = :uid"), {"uid": user_id})
        conn.execute(
            text(
                "INSERT INTO sys_user_dept (user_id, dept_id, is_primary, created_at) "
                "VALUES (:uid, :did, 1, datetime('now'))"
            ),
            {"uid": user_id, "did": dept_id},
        )


def _enable_sales_rms_jobs_write(engine):
    _grant_role_permissions(engine, ROLE_SALES, ("rms.jobs.read", "rms.jobs.write"))


def _enable_delivery_rms_mvp(engine):
    _grant_role_permissions(engine, ROLE_DELIVERY, RMS_MVP_PERMS)
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "read", SCOPE_ASSIGNED)
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "write", SCOPE_ASSIGNED)
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_APPLICATION, "write", SCOPE_ASSIGNED)


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def rms_engine(client_rbac):
    import main as crm_main

    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)
    return crm_main.engine


def test_first_job_via_trial_path_crm_visible(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    sales = f"rms2_sales_{suffix}"
    delivery = f"rms2_del_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Trial {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=None)

    login = _login(client_rbac, sales)
    assert login.status_code == 200
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login.cookies,
        json={
            "client_id": cid,
            "title": "Trial Job",
            "owner_user_id": sales_uid,
            "delivery_owner_user_id": delivery_uid,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client_id"] == cid
    assert body["title"] == "Trial Job"

    with rms_engine.connect() as conn:
        row = conn.execute(
            text("SELECT delivery_owner_user_id FROM clients WHERE id = :cid"),
            {"cid": cid},
        ).fetchone()
    assert row is not None
    assert int(row[0]) == delivery_uid


def test_first_job_blocked_without_crm_client_visibility(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    sales_a = f"rms2_sa_{suffix}"
    sales_b = f"rms2_sb_{suffix}"
    delivery = f"rms2_delb_{suffix}"
    uid_a = _create_user(client_rbac, admin_auth, sales_a, [ROLE_SALES])
    _create_user(client_rbac, admin_auth, sales_b, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Hidden {suffix}")
    _set_client_owner(rms_engine, cid, uid_a, delivery_owner_user_id=None)

    login_b = _login(client_rbac, sales_b)
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login_b.cookies,
        json={
            "client_id": cid,
            "title": "Blocked",
            "owner_user_id": uid_a,
            "delivery_owner_user_id": delivery_uid,
        },
    )
    assert r.status_code == 404


def test_first_job_blocked_without_delivery_owner_body(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    sales = f"rms2_snod_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    cid = _create_client_admin(client_rbac, admin_auth, f"RMS NoDel {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=None)

    login = _login(client_rbac, sales)
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login.cookies,
        json={"client_id": cid, "title": "X", "owner_user_id": sales_uid},
    )
    assert r.status_code == 400
    assert "delivery_owner_user_id" in r.json().get("detail", "")


def test_job_salary_cap_validation(client_rbac, admin_auth, rms_engine, uniq):
    login_del, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"cap_{uniq}")

    ok = client_rbac.patch(
        f"/api/rms/jobs/{job_id}",
        cookies=login_del.cookies,
        json={"salary_cap": "25,000"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["salary_cap"] == "25000"

    for bad in ("999", "100000", "30K"):
        r = client_rbac.patch(
            f"/api/rms/jobs/{job_id}",
            cookies=login_del.cookies,
            json={"salary_cap": bad},
        )
        assert r.status_code == 400, r.text


def test_create_job_forbidden_without_rms_jobs_write(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    viewer = f"rms2_viewer_{suffix}"
    _create_user(client_rbac, admin_auth, viewer, [ROLE_VIEWER])
    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Viewer {suffix}")

    login = _login(client_rbac, viewer)
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login.cookies,
        json={"client_id": cid, "title": "Nope", "owner_user_id": 1},
    )
    assert r.status_code == 403
    assert "rms.jobs.write" in r.json().get("detail", "")


def test_first_job_regular_path_after_delivery_owner_set(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    sales = f"rms2_sreg_{suffix}"
    delivery = f"rms2_dreg_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Regular {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=None)

    login_sales = _login(client_rbac, sales)
    first = client_rbac.post(
        "/api/rms/jobs",
        cookies=login_sales.cookies,
        json={
            "client_id": cid,
            "title": "First",
            "owner_user_id": sales_uid,
            "delivery_owner_user_id": delivery_uid,
        },
    )
    assert first.status_code == 200

    login_del = _login(client_rbac, delivery)
    second = client_rbac.post(
        "/api/rms/jobs",
        cookies=login_del.cookies,
        json={
            "client_id": cid,
            "title": "Second",
            "owner_user_id": delivery_uid,
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["title"] == "Second"


def test_create_job_recruitment_dept_regular_path(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    parent_dept = 880000 + (int(suffix[:6], 16) % 10000)
    child_dept = parent_dept + 1
    parent_path = f"ROOT/RECRUIT_{parent_dept}"
    child_path = f"{parent_path}/TEAM_{child_dept}"
    _ensure_dept(rms_engine, parent_dept, f"RecruitParent_{suffix}", path=parent_path)
    _ensure_dept(
        rms_engine,
        child_dept,
        f"RecruitChild_{suffix}",
        path=child_path,
        parent_id=parent_dept,
    )

    sales = f"rms2_rps_{suffix}"
    delivery = f"rms2_rpd_{suffix}"
    recruit = f"rms2_rpr_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    recruit_uid = _create_user(client_rbac, admin_auth, recruit, [ROLE_DELIVERY])
    _set_user_dept(rms_engine, recruit_uid, child_dept)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS RecDept {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=parent_dept)

    login = _login(client_rbac, recruit)
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login.cookies,
        json={
            "client_id": cid,
            "title": "Recruitment dept job",
            "owner_user_id": recruit_uid,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["client_id"] == cid


def test_create_job_recruitment_owner_trial_path(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    sales_a = f"rms2_rta_{suffix}"
    sales_b = f"rms2_rtb_{suffix}"
    delivery = f"rms2_rtd_{suffix}"
    recruit = f"rms2_rto_{suffix}"
    uid_a = _create_user(client_rbac, admin_auth, sales_a, [ROLE_SALES])
    _create_user(client_rbac, admin_auth, sales_b, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    recruit_uid = _create_user(client_rbac, admin_auth, recruit, [ROLE_DELIVERY])

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS RecOwner Trial {suffix}")
    _set_client_owner(rms_engine, cid, uid_a, delivery_owner_user_id=None)
    _set_client_recruitment(rms_engine, cid, recruitment_owner_user_id=recruit_uid)

    login = _login(client_rbac, recruit)
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login.cookies,
        json={
            "client_id": cid,
            "title": "Trial via recruitment owner",
            "owner_user_id": recruit_uid,
            "delivery_owner_user_id": delivery_uid,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Trial via recruitment owner"


def test_create_job_blocked_without_recruitment_or_delivery_scope(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    recruit_dept = 881000 + (int(suffix[:6], 16) % 10000)
    other_dept = recruit_dept + 1
    _ensure_dept(rms_engine, recruit_dept, f"RecruitOnly_{suffix}", path=f"ROOT/RECRUIT_{recruit_dept}")
    _ensure_dept(rms_engine, other_dept, f"OtherDept_{suffix}", path=f"ROOT/OTHER_{other_dept}")

    sales = f"rms2_blk_s_{suffix}"
    delivery = f"rms2_blk_d_{suffix}"
    outsider = f"rms2_blk_o_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    outsider_uid = _create_user(client_rbac, admin_auth, outsider, [ROLE_DELIVERY])
    _set_user_dept(rms_engine, outsider_uid, other_dept)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Blocked {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=recruit_dept)

    login = _login(client_rbac, outsider)
    r = client_rbac.post(
        "/api/rms/jobs",
        cookies=login.cookies,
        json={
            "client_id": cid,
            "title": "Should fail",
            "owner_user_id": outsider_uid,
        },
    )
    assert r.status_code == 404


def test_candidate_created_by_visible(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"vis_{suffix}")
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(
            job_id,
            name="Alice",
            email="alice@example.com",
            wechat="wx_alice",
            email_wechat="alice@example.com",
        ),
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    got = client_rbac.get(f"/api/rms/candidates/{cid}", cookies=login.cookies)
    assert got.status_code == 200
    assert got.json()["name"] == "Alice"


def test_candidate_hidden_when_not_creator_or_visible_application(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login_a, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"hid_{suffix}")
    del_b = f"rms2_cdb_{suffix}"
    _create_user(client_rbac, admin_auth, del_b, [ROLE_DELIVERY])
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_a.cookies,
        json=_candidate_json(job_id, name="Hidden Bob", phone="13900139000"),
    )
    assert created.status_code == 200
    cand_id = created.json()["id"]

    login_b = _login(client_rbac, del_b)
    hidden = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login_b.cookies)
    assert hidden.status_code == 404


def test_candidate_contact_masked_without_rms_contacts_view(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"mask_{suffix}")
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(
            job_id,
            name="Mask Me",
            email="mask@example.com",
            wechat="wxmask",
            email_wechat="mask@example.com",
        ),
    )
    assert created.status_code == 200
    body = created.json()
    assert "****" in body["phone"]
    assert "***" in body["email"]
    assert "***" in body["wechat"]


def test_candidate_create_rejects_invalid_phone(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"ph_{suffix}")
    r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, phone="12345"),
    )
    assert r.status_code == 400
    assert "手机号" in r.json().get("detail", "")


def test_candidate_create_rejects_non_open_job(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"cls_{suffix}")
    admin_user, admin_pwd = admin_auth
    closed = client_rbac.patch(
        f"/api/rms/jobs/{job_id}",
        headers=auth_header(admin_user, admin_pwd),
        json={"status": "closed"},
    )
    assert closed.status_code == 200, closed.text
    r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name="Late Cand", phone="13800138001"),
    )
    assert r.status_code == 400
    assert "open" in r.json().get("detail", "").lower()


def test_candidate_contact_visible_with_rms_contacts_view(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    import main as crm_main

    _grant_role_permissions(crm_main.engine, ROLE_DELIVERY, ("rms.contacts.view",))
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"cont_{suffix}")
    phone = "13800138088"
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(
            job_id,
            name="Clear",
            phone=phone,
            email="clear@example.com",
            wechat="wxclear",
            email_wechat="clear@example.com",
        ),
    )
    assert created.status_code == 200
    body = created.json()
    assert body["phone"] == phone
    assert body["email"] == "clear@example.com"
    assert body["wechat"] == "wxclear"


def _trial_job_and_candidate(client, engine, admin_auth, suffix: str):
    """Delivery-owned client with one job; returns cookies, job_id, candidate_id, client_id."""
    sales = f"rms2_app_s_{suffix}"
    delivery = f"rms2_app_d_{suffix}"
    sales_uid = _create_user(client, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client, admin_auth, delivery, [ROLE_DELIVERY])
    cid = _create_client_admin(client, admin_auth, f"RMS App {suffix}")
    _set_client_owner(engine, cid, sales_uid, delivery_owner_user_id=None)

    login_sales = _login(client, sales)
    job_r = client.post(
        "/api/rms/jobs",
        cookies=login_sales.cookies,
        json={
            "client_id": cid,
            "title": "App Job",
            "owner_user_id": sales_uid,
            "delivery_owner_user_id": delivery_uid,
        },
    )
    assert job_r.status_code == 200
    job_id = job_r.json()["id"]

    login_del = _login(client, delivery)
    cand_r = client.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_id, name=f"Cand {suffix}", phone="13700137000"),
    )
    assert cand_r.status_code == 200
    return login_del, job_id, cand_r.json()["id"], cid


def test_application_create_syncs_client_id_from_job(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id, cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    r = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["client_id"] == client_id
    assert r.json()["status"] == "recommended"


def test_job_recommendation_counts(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id, _, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, uniq
    )

    def _create_app(name: str) -> int:
        cand_r = client_rbac.post(
            "/api/rms/candidates",
            cookies=login.cookies,
            json=_candidate_json(job_id, name=name, phone=_unique_phone()),
        )
        assert cand_r.status_code == 200, cand_r.text
        app_r = client_rbac.post(
            "/api/rms/applications",
            cookies=login.cookies,
            json={"job_id": job_id, "candidate_id": cand_r.json()["id"]},
        )
        assert app_r.status_code == 200, app_r.text
        return int(app_r.json()["id"])

    _create_app("Active A")
    app_active_b = _create_app("Active B")
    app_pending_first = _create_app("Pending First")
    app_onboarding = _create_app("Onboarding")
    app_hired = _create_app("Hired")

    _set_application_status(rms_engine, app_active_b, "first_interview_passed")
    _set_application_status(rms_engine, app_pending_first, "pending_first_interview")
    _set_application_status(rms_engine, app_onboarding, "onboarding")
    _set_application_status(rms_engine, app_hired, "hired", hired_at="2026-01-01")

    jobs_r = client_rbac.get("/api/rms/jobs", cookies=login.cookies)
    assert jobs_r.status_code == 200, jobs_r.text
    job = next(j for j in jobs_r.json() if j["id"] == job_id)
    assert job["historical_recommendation_count"] == 5
    assert job["active_recommendation_count"] == 3

    job_detail = client_rbac.get(f"/api/rms/jobs/{job_id}", cookies=login.cookies)
    assert job_detail.status_code == 200, job_detail.text
    body = job_detail.json()
    assert body["historical_recommendation_count"] == 5
    assert body["active_recommendation_count"] == 3


def test_application_rejects_invisible_candidate(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login_a, job_id, _, _ = _trial_job_and_candidate(client_rbac, rms_engine, admin_auth, suffix)
    login_b, job_b_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"sec_{suffix}")
    secret = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_b.cookies,
        json=_candidate_json(job_b_id, name="Secret", phone="13600136000"),
    )
    assert secret.status_code == 200
    secret_id = secret.json()["id"]

    r = client_rbac.post(
        "/api/rms/applications",
        cookies=login_a.cookies,
        json={"job_id": job_id, "candidate_id": secret_id},
    )
    assert r.status_code == 404


def test_application_duplicate_returns_409(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    first = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert first.status_code == 200
    dup = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert dup.status_code == 409


def test_patch_application_rejects_forbidden_fields(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200
    app_id = created.json()["id"]
    bad = client_rbac.patch(
        f"/api/rms/applications/{app_id}",
        cookies=login.cookies,
        json={"status": "screening"},
    )
    assert bad.status_code == 400
    assert "status" in bad.json().get("detail", "")


def test_patch_application_recomputes_client_id_when_job_changes(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    sales = f"rms2_pjs_{suffix}"
    delivery = f"rms2_pjd_{suffix}"
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    cid_a = _create_client_admin(client_rbac, admin_auth, f"RMS A {suffix}")
    cid_b = _create_client_admin(client_rbac, admin_auth, f"RMS B {suffix}")
    _set_client_owner(rms_engine, cid_a, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_owner(rms_engine, cid_b, sales_uid, delivery_owner_user_id=delivery_uid)

    login_del = _login(client_rbac, delivery)
    job_a = client_rbac.post(
        "/api/rms/jobs",
        cookies=login_del.cookies,
        json={"client_id": cid_a, "title": "JA", "owner_user_id": delivery_uid},
    )
    job_b = client_rbac.post(
        "/api/rms/jobs",
        cookies=login_del.cookies,
        json={"client_id": cid_b, "title": "JB", "owner_user_id": delivery_uid},
    )
    assert job_a.status_code == 200 and job_b.status_code == 200
    cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_a.json()["id"], name="Patch Cand", phone="13500135000"),
    )
    assert cand.status_code == 200
    app = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_a.json()["id"], "candidate_id": cand.json()["id"]},
    )
    assert app.status_code == 200
    assert app.json()["client_id"] == cid_a

    patched = client_rbac.patch(
        f"/api/rms/applications/{app.json()['id']}",
        cookies=login_del.cookies,
        json={"job_id": job_b.json()["id"]},
    )
    assert patched.status_code == 200
    assert patched.json()["client_id"] == cid_b


def _app_for_status(client, engine, admin_auth, suffix: str):
    login, job_id, cand_id, _ = _trial_job_and_candidate(client, engine, admin_auth, suffix)
    created = client.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200
    app_id = created.json()["id"]
    review = client.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed"},
    )
    assert review.status_code == 200, review.text
    return login, app_id


def test_status_transition_writes_current_stage_and_activity(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, suffix)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview", "reason": "ok", "note": "n1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduling_interview"
    assert body["current_stage"] == "scheduling_interview"
    assert body["last_activity_at"]
    assert len(body["last_activity_at"]) == 10
    assert body["last_activity_at"][4] == "-" and body["last_activity_at"][7] == "-"
    assert "T" not in body["last_activity_at"]

    hist = client_rbac.get(
        f"/api/rms/applications/{app_id}/status-history",
        cookies=login.cookies,
    )
    assert hist.status_code == 200
    assert len(hist.json()) >= 1
    assert hist.json()[0]["to_status"] == "scheduling_interview"


def test_status_fail_from_client_screen(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, suffix)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "client_screen_failed", "reason": "no fit"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "client_screen_failed"


def test_status_terminal_no_transition(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, suffix)
    client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "client_screen_failed"},
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview"},
    )
    assert r.status_code == 400


def test_status_recommended_requires_delivery_review(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200
    app_id = created.json()["id"]
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "hired_at": "2026-06-01"},
    )
    assert r.status_code == 400


def test_legacy_screening_normalizes_to_pipeline(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    app_id = created.json()["id"]
    with rms_engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_applications SET status = 'screening', receive_status = 'accepted', "
                "delivery_review_status = 'passed' WHERE id = :id"
            ),
            {"id": app_id},
        )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "scheduling_interview"


def _set_application_status(engine, app_id: int, status: str, *, hired_at: str = ""):
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE rms_applications SET status = :status, current_stage = :status, "
                "hired_at = :hired_at WHERE id = :id"
            ),
            {"id": app_id, "status": status, "hired_at": hired_at},
        )


def _advance_to_onboarding(client, login, app_id):
    steps = [
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
        "onboarding",
    ]
    for st in steps:
        r = client.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": st},
        )
        assert r.status_code == 200, r.text


def test_status_transition_mode_blocks_skip(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "first_interview_passed", "mode": "transition"},
    )
    assert r.status_code == 400


def test_status_default_mode_unchanged(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview"},
    )
    assert r.status_code == 200, r.text


def test_status_correction_allows_backward(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview"},
    )
    client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "pending_first_interview"},
    )
    client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "first_interview_passed"},
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={
            "to_status": "pending_client_screen",
            "mode": "correction",
            "note": "退回修正",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_client_screen"
    hist = client_rbac.get(
        f"/api/rms/applications/{app_id}/status-history",
        cookies=login.cookies,
    )
    assert hist.status_code == 200
    assert hist.json()[0]["reason"] == "status_correction"
    assert hist.json()[0]["note"] == "退回修正"


def test_status_correction_rejects_short_note(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview", "mode": "correction", "note": "x"},
    )
    assert r.status_code == 400


def test_status_correction_rejects_rejected_target(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "rejected", "mode": "correction", "note": "不应允许"},
    )
    assert r.status_code == 400


def test_status_correction_requires_pipeline_eligible(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, suffix
    )
    created = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    app_id = created.json()["id"]
    _set_application_status(rms_engine, app_id, "pending_client_screen")
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview", "mode": "correction", "note": "未内审"},
    )
    assert r.status_code == 400


def test_status_correction_from_hired_clears_hired_at(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    _advance_to_onboarding(client_rbac, login, app_id)
    hired = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "hired_at": "2026-06-15"},
    )
    assert hired.status_code == 200, hired.text
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "onboarding", "mode": "correction", "note": "修正离入职"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "onboarding"
    assert r.json()["hired_at"] == ""


def test_status_invalid_mode(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "scheduling_interview", "mode": "foo"},
    )
    assert r.status_code == 422
