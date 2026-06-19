"""RMS Phase 2: jobs, candidates, applications API MVP."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.data_scope_catalog import (
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_CANDIDATE,
    RESOURCE_RMS_JOB,
    RESOURCE_RMS_RESUME,
    SCOPE_ALL,
    SCOPE_ASSIGNED,
    SCOPE_DEPT_AND_CHILD,
    SCOPE_NONE,
    SCOPE_SELF,
)
from auth.permissions import ROLE_DELIVERY, ROLE_SALES, ROLE_VIEWER
from tests.helpers import auth_header

RMS_MVP_PERMS = (
    "rms.jobs.read",
    "rms.jobs.write",
    "rms.jobs.delete",
    "rms.candidates.read",
    "rms.candidates.write",
    "rms.candidates.delete",
    "rms.applications.read",
    "rms.applications.write",
    "rms.applications.delete",
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


def _revoke_role_permissions(engine, role_code: str, perm_codes: tuple[str, ...]) -> None:
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
                        "DELETE FROM sys_role_permission "
                        "WHERE role_id = :rid AND permission_id = :pid"
                    ),
                    {"rid": rid, "pid": pid},
                )


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


def _set_role_data_scope_by_id(
    engine, role_id: int, resource_code: str, action: str, scope_type: str
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM sys_role_data_scope "
                "WHERE role_id = :rid AND resource_code = :rc AND action = :act"
            ),
            {"rid": role_id, "rc": resource_code, "act": action},
        )
        conn.execute(
            text(
                "INSERT INTO sys_role_data_scope "
                "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                "VALUES (:rid, :rc, :act, :st, datetime('now'), datetime('now'))"
            ),
            {"rid": role_id, "rc": resource_code, "act": action, "st": scope_type},
        )


def _create_recruiter_role(
    client,
    admin_auth,
    engine,
    suffix: str,
    *,
    permission_codes: tuple[str, ...],
    read_scope: str,
    write_scope: str,
    delete_scope: str,
) -> str:
    user, pwd = admin_auth
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    created = client.post(
        "/api/system/roles",
        headers=headers,
        json={"name": f"招聘测试_{suffix}", "description": "RMS 推荐记录 read scope 测试"},
    )
    assert created.status_code == 200, created.text
    role_id = int(created.json()["id"])
    saved = client.put(
        f"/api/system/roles/{role_id}/permissions",
        headers=headers,
        json={"permission_codes": list(permission_codes)},
    )
    assert saved.status_code == 200, saved.text
    for action, scope in (
        ("read", read_scope),
        ("write", write_scope),
        ("delete", delete_scope),
    ):
        _set_role_data_scope_by_id(engine, role_id, RESOURCE_RMS_APPLICATION, action, scope)
    with engine.connect() as conn:
        role_code = conn.execute(
            text("SELECT code FROM sys_role WHERE id = :id"),
            {"id": role_id},
        ).scalar()
    assert role_code
    return str(role_code)


def _set_application_recommended_by(
    engine, application_id: int, recommended_by: int, *, delivery_review_status: str | None = None
) -> None:
    with engine.begin() as conn:
        if delivery_review_status is None:
            conn.execute(
                text("UPDATE rms_applications SET recommended_by = :uid WHERE id = :id"),
                {"uid": recommended_by, "id": application_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE rms_applications SET recommended_by = :uid, "
                    "delivery_review_status = :dr WHERE id = :id"
                ),
                {"uid": recommended_by, "dr": delivery_review_status, "id": application_id},
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
        "city": "上海",
        "current_salary": "15000",
        "expected_salary": "18000",
        "age": "28",
        "work_years": "5年",
        "email_wechat": "candidate@example.com",
        "available_date": "2026-06-08",
        "education_level": "统本",
        "source": "Boss",
        "school": "测试大学",
        "major": "计算机",
        "gender": "男",
        "marital_status": "未婚",
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
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "write", SCOPE_SELF)
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "delete", SCOPE_SELF)
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_APPLICATION, "write", SCOPE_ASSIGNED)
    _set_role_data_scope(engine, ROLE_DELIVERY, RESOURCE_RMS_APPLICATION, "delete", SCOPE_ASSIGNED)


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


def test_job_read_recruitment_dept_and_child_cross_team(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    parent_dept = 890000 + (int(suffix[:6], 16) % 10000)
    group1 = parent_dept + 1
    group2 = parent_dept + 2
    parent_path = f"ROOT/RECRUIT_PARENT_{parent_dept}"
    _ensure_dept(rms_engine, parent_dept, f"RecruitParent_{suffix}", path=parent_path)
    _ensure_dept(
        rms_engine,
        group1,
        f"RecruitG1_{suffix}",
        path=f"{parent_path}/G1_{group1}",
        parent_id=parent_dept,
    )
    _ensure_dept(
        rms_engine,
        group2,
        f"RecruitG2_{suffix}",
        path=f"{parent_path}/G2_{group2}",
        parent_id=parent_dept,
    )

    qianq = f"rms2_qianq_{suffix}"
    leiz = f"rms2_leiz_{suffix}"
    delivery = f"rms2_delct_{suffix}"
    sales = f"rms2_salct_{suffix}"
    qianq_uid = _create_user(client_rbac, admin_auth, qianq, [ROLE_DELIVERY])
    leiz_uid = _create_user(client_rbac, admin_auth, leiz, [ROLE_DELIVERY])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    _set_user_dept(rms_engine, qianq_uid, group1)
    _set_user_dept(rms_engine, leiz_uid, parent_dept)

    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "read", SCOPE_DEPT_AND_CHILD)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "write", SCOPE_NONE)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS CrossTeam {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=parent_dept)

    admin_user, admin_pwd = admin_auth
    job_r = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Qianq Job {suffix}",
            "owner_user_id": qianq_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    job_id = job_r.json()["id"]

    login_leiz = _login(client_rbac, leiz)
    jobs_r = client_rbac.get("/api/rms/jobs", cookies=login_leiz.cookies)
    assert jobs_r.status_code == 200, jobs_r.text
    assert job_id in {j["id"] for j in jobs_r.json()}

    patch_r = client_rbac.patch(
        f"/api/rms/jobs/{job_id}",
        cookies=login_leiz.cookies,
        json={"title": "Hacked"},
    )
    assert patch_r.status_code == 404


def test_cross_team_recruiter_can_recommend_to_visible_job_not_edit(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    parent_dept = 892000 + (int(suffix[:6], 16) % 10000)
    group1 = parent_dept + 1
    group2 = parent_dept + 2
    parent_path = f"ROOT/RECRUIT_REC_{parent_dept}"
    _ensure_dept(rms_engine, parent_dept, f"RecruitParentR_{suffix}", path=parent_path)
    _ensure_dept(
        rms_engine,
        group1,
        f"RecruitG1R_{suffix}",
        path=f"{parent_path}/G1_{group1}",
        parent_id=parent_dept,
    )
    _ensure_dept(
        rms_engine,
        group2,
        f"RecruitG2R_{suffix}",
        path=f"{parent_path}/G2_{group2}",
        parent_id=parent_dept,
    )

    qianq = f"rms2_qrec_{suffix}"
    leiz = f"rms2_lrec_{suffix}"
    delivery = f"rms2_drec_{suffix}"
    sales = f"rms2_srec_{suffix}"
    qianq_uid = _create_user(client_rbac, admin_auth, qianq, [ROLE_DELIVERY])
    leiz_uid = _create_user(client_rbac, admin_auth, leiz, [ROLE_DELIVERY])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    _set_user_dept(rms_engine, qianq_uid, group1)
    _set_user_dept(rms_engine, leiz_uid, parent_dept)

    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "read", SCOPE_DEPT_AND_CHILD)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "write", SCOPE_NONE)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Recommend {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=parent_dept)

    admin_user, admin_pwd = admin_auth
    job_r = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Qianq Recommend Job {suffix}",
            "owner_user_id": qianq_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    job_id = job_r.json()["id"]

    login_leiz = _login(client_rbac, leiz)
    jobs_r = client_rbac.get("/api/rms/jobs", cookies=login_leiz.cookies)
    assert jobs_r.status_code == 200, jobs_r.text
    assert job_id in {j["id"] for j in jobs_r.json()}

    cand_r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_leiz.cookies,
        json=_candidate_json(job_id, name=f"Rec Cand {suffix}"),
    )
    assert cand_r.status_code == 200, cand_r.text
    cand_id = cand_r.json()["id"]

    recommend_r = client_rbac.post(
        "/api/rms/applications",
        cookies=login_leiz.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert recommend_r.status_code == 200, recommend_r.text
    body = recommend_r.json()
    assert body["job_id"] == job_id
    assert body["candidate_id"] == cand_id
    assert body["recommended_by"] == leiz_uid

    patch_r = client_rbac.patch(
        f"/api/rms/jobs/{job_id}",
        cookies=login_leiz.cookies,
        json={"title": "Hacked"},
    )
    assert patch_r.status_code == 404


def test_cross_team_recommend_invisible_job_404(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    parent_dept = 893000 + (int(suffix[:6], 16) % 10000)
    group1 = parent_dept + 1
    group2 = parent_dept + 2
    parent_path = f"ROOT/RECRUIT_INV_{parent_dept}"
    _ensure_dept(rms_engine, parent_dept, f"RecruitParentI_{suffix}", path=parent_path)
    _ensure_dept(
        rms_engine,
        group1,
        f"RecruitG1I_{suffix}",
        path=f"{parent_path}/G1_{group1}",
        parent_id=parent_dept,
    )
    _ensure_dept(
        rms_engine,
        group2,
        f"RecruitG2I_{suffix}",
        path=f"{parent_path}/G2_{group2}",
        parent_id=parent_dept,
    )

    qianq = f"rms2_qinv_{suffix}"
    leiz = f"rms2_linv_{suffix}"
    delivery = f"rms2_dinv_{suffix}"
    sales = f"rms2_sinv_{suffix}"
    qianq_uid = _create_user(client_rbac, admin_auth, qianq, [ROLE_DELIVERY])
    leiz_uid = _create_user(client_rbac, admin_auth, leiz, [ROLE_DELIVERY])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    _set_user_dept(rms_engine, qianq_uid, group1)
    _set_user_dept(rms_engine, leiz_uid, group2)

    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "read", SCOPE_DEPT_AND_CHILD)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "write", SCOPE_NONE)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Invisible {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=group1)

    admin_user, admin_pwd = admin_auth
    job_r = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Qianq Invisible Job {suffix}",
            "owner_user_id": qianq_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    job_id = job_r.json()["id"]

    login_leiz = _login(client_rbac, leiz)
    jobs_r = client_rbac.get("/api/rms/jobs", cookies=login_leiz.cookies)
    assert jobs_r.status_code == 200, jobs_r.text
    assert job_id not in {j["id"] for j in jobs_r.json()}

    cand_r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_leiz.cookies,
        json=_candidate_json(job_id, name=f"Inv Cand {suffix}", target_job_id=None),
    )
    assert cand_r.status_code == 200, cand_r.text
    cand_id = cand_r.json()["id"]

    recommend_r = client_rbac.post(
        "/api/rms/applications",
        cookies=login_leiz.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert recommend_r.status_code == 404


def test_cross_team_recommend_closed_job_400(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    parent_dept = 894000 + (int(suffix[:6], 16) % 10000)
    group1 = parent_dept + 1
    parent_path = f"ROOT/RECRUIT_CLS_{parent_dept}"
    _ensure_dept(rms_engine, parent_dept, f"RecruitParentC_{suffix}", path=parent_path)
    _ensure_dept(
        rms_engine,
        group1,
        f"RecruitG1C_{suffix}",
        path=f"{parent_path}/G1_{group1}",
        parent_id=parent_dept,
    )

    qianq = f"rms2_qcls_{suffix}"
    leiz = f"rms2_lcls_{suffix}"
    delivery = f"rms2_dcls_{suffix}"
    sales = f"rms2_scls_{suffix}"
    qianq_uid = _create_user(client_rbac, admin_auth, qianq, [ROLE_DELIVERY])
    leiz_uid = _create_user(client_rbac, admin_auth, leiz, [ROLE_DELIVERY])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    _set_user_dept(rms_engine, qianq_uid, group1)
    _set_user_dept(rms_engine, leiz_uid, parent_dept)

    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "read", SCOPE_DEPT_AND_CHILD)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "write", SCOPE_NONE)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS Closed {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=parent_dept)

    admin_user, admin_pwd = admin_auth
    job_r = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Qianq Closed Job {suffix}",
            "owner_user_id": qianq_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    job_id = job_r.json()["id"]

    closed = client_rbac.patch(
        f"/api/rms/jobs/{job_id}",
        headers=auth_header(admin_user, admin_pwd),
        json={"status": "closed"},
    )
    assert closed.status_code == 200, closed.text

    login_leiz = _login(client_rbac, leiz)
    cand_r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_leiz.cookies,
        json=_candidate_json(job_id, name=f"Cls Cand {suffix}"),
    )
    assert cand_r.status_code == 400, cand_r.text
    assert "open" in cand_r.json().get("detail", "").lower()

    cand_r2 = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_leiz.cookies,
        json=_candidate_json(job_id, name=f"Cls Cand2 {suffix}", target_job_id=None),
    )
    assert cand_r2.status_code == 200, cand_r2.text
    cand_id = cand_r2.json()["id"]

    recommend_r = client_rbac.post(
        "/api/rms/applications",
        cookies=login_leiz.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert recommend_r.status_code == 400, recommend_r.text
    assert "open" in recommend_r.json().get("detail", "").lower()


def test_job_read_recruitment_dept_and_child_strict_subtree(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    parent_dept = 891000 + (int(suffix[:6], 16) % 10000)
    group1 = parent_dept + 1
    group2 = parent_dept + 2
    parent_path = f"ROOT/RECRUIT_STRICT_{parent_dept}"
    _ensure_dept(rms_engine, parent_dept, f"RecruitParentS_{suffix}", path=parent_path)
    _ensure_dept(
        rms_engine,
        group1,
        f"RecruitG1S_{suffix}",
        path=f"{parent_path}/G1_{group1}",
        parent_id=parent_dept,
    )
    _ensure_dept(
        rms_engine,
        group2,
        f"RecruitG2S_{suffix}",
        path=f"{parent_path}/G2_{group2}",
        parent_id=parent_dept,
    )

    qianq = f"rms2_qsq_{suffix}"
    leiz = f"rms2_lsz_{suffix}"
    delivery = f"rms2_dsz_{suffix}"
    sales = f"rms2_ssz_{suffix}"
    qianq_uid = _create_user(client_rbac, admin_auth, qianq, [ROLE_DELIVERY])
    leiz_uid = _create_user(client_rbac, admin_auth, leiz, [ROLE_DELIVERY])
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])
    _set_user_dept(rms_engine, qianq_uid, group1)
    _set_user_dept(rms_engine, leiz_uid, group2)

    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "read", SCOPE_DEPT_AND_CHILD)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_JOB, "write", SCOPE_NONE)

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS StrictSubtree {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)
    _set_client_recruitment(rms_engine, cid, recruitment_dept_id=group1)

    admin_user, admin_pwd = admin_auth
    job_r = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Qianq Strict {suffix}",
            "owner_user_id": qianq_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    job_id = job_r.json()["id"]

    login_leiz = _login(client_rbac, leiz)
    jobs_r = client_rbac.get("/api/rms/jobs", cookies=login_leiz.cookies)
    assert jobs_r.status_code == 200, jobs_r.text
    assert job_id not in {j["id"] for j in jobs_r.json()}


def test_job_read_delivery_client_scope_unchanged(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    delivery = f"rms2_dreg_{suffix}"
    recruit = f"rms2_rreg_{suffix}"
    sales = f"rms2_sreg_{suffix}"
    delivery_uid = _create_user(client_rbac, admin_auth, delivery, [ROLE_DELIVERY])
    recruit_uid = _create_user(client_rbac, admin_auth, recruit, [ROLE_DELIVERY])
    sales_uid = _create_user(client_rbac, admin_auth, sales, [ROLE_SALES])

    cid = _create_client_admin(client_rbac, admin_auth, f"RMS DelReg {suffix}")
    _set_client_owner(rms_engine, cid, sales_uid, delivery_owner_user_id=delivery_uid)

    admin_user, admin_pwd = admin_auth
    job_r = client_rbac.post(
        "/api/rms/jobs",
        headers=auth_header(admin_user, admin_pwd),
        json={
            "client_id": cid,
            "title": f"Recruit Owned Job {suffix}",
            "owner_user_id": recruit_uid,
        },
    )
    assert job_r.status_code == 200, job_r.text
    job_id = job_r.json()["id"]

    login_del = _login(client_rbac, delivery)
    jobs_r = client_rbac.get("/api/rms/jobs", cookies=login_del.cookies)
    assert jobs_r.status_code == 200, jobs_r.text
    assert job_id in {j["id"] for j in jobs_r.json()}


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


def _candidate_ids_from_list(body: list) -> set[int]:
    return {int(c["id"]) for c in body}


def test_candidate_search_by_name(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"srch_name_{suffix}")
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name="Alice", phone=_unique_phone()),
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    r = client_rbac.get("/api/rms/candidates?q=Alice", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert cid in _candidate_ids_from_list(r.json())


def test_candidate_search_by_school_or_major(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"srch_edu_{suffix}")
    school = f"清华特研学院_{suffix}"
    major = f"量子工程_{suffix}"
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name=f"EduCand_{suffix}", phone=_unique_phone(), school=school, major=major),
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    by_school = client_rbac.get(f"/api/rms/candidates?q={school}", cookies=login.cookies)
    assert by_school.status_code == 200, by_school.text
    assert cid in _candidate_ids_from_list(by_school.json())
    by_major = client_rbac.get(f"/api/rms/candidates?q={major}", cookies=login.cookies)
    assert by_major.status_code == 200, by_major.text
    assert cid in _candidate_ids_from_list(by_major.json())


def test_candidate_search_by_job_title(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"srch_job_{suffix}")
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name=f"JobCand_{suffix}", phone=_unique_phone()),
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]
    r = client_rbac.get(f"/api/rms/candidates?q=Job_{suffix}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert cid in _candidate_ids_from_list(r.json())


def test_candidate_search_by_client_name(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"srch_cli_{suffix}")
    with rms_engine.connect() as conn:
        cid = conn.execute(
            text("SELECT client_id FROM rms_jobs WHERE id = :id"),
            {"id": job_id},
        ).scalar()
    client_name = f"RMS Job srch_cli_{suffix}"
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(
            job_id,
            name=f"CliCand_{suffix}",
            phone=_unique_phone(),
            target_client_id=int(cid),
        ),
    )
    assert created.status_code == 200, created.text
    cand_id = created.json()["id"]
    r = client_rbac.get(f"/api/rms/candidates?q={client_name}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert cand_id in _candidate_ids_from_list(r.json())


def test_candidate_search_respects_visibility(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login_a, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"srch_vis_{suffix}")
    del_b = f"rms2_cdb_srch_{suffix}"
    _create_user(client_rbac, admin_auth, del_b, [ROLE_DELIVERY])
    created = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_a.cookies,
        json=_candidate_json(job_id, name="Hidden Bob", phone="13900139001"),
    )
    assert created.status_code == 200
    cand_id = created.json()["id"]
    login_b = _login(client_rbac, del_b)
    r = client_rbac.get("/api/rms/candidates?q=Hidden Bob", cookies=login_b.cookies)
    assert r.status_code == 200, r.text
    assert cand_id not in _candidate_ids_from_list(r.json())


def test_candidate_read_all_can_search_and_recommend_existing_candidate_with_boundaries(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    _grant_role_permissions(
        rms_engine,
        ROLE_DELIVERY,
        ("rms.resumes.read", "rms.contacts.view"),
    )
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "read", SCOPE_ALL)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "write", SCOPE_SELF)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "delete", SCOPE_SELF)
    _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_RESUME, "read", SCOPE_ALL)
    try:
        login_a, job_a_id = _delivery_open_job(
            client_rbac, rms_engine, admin_auth, f"pool_a_{suffix}"
        )
        login_b, job_b_id = _delivery_open_job(
            client_rbac, rms_engine, admin_auth, f"pool_b_{suffix}"
        )

        raw_phone = _unique_phone()
        raw_email = f"pool_{suffix}@example.com"
        raw_wechat = f"wx_pool_{suffix}"
        cand_name = f"PoolCand_{suffix}"
        client_rbac.cookies.clear()
        client_rbac.cookies.update(login_a.cookies)
        created = client_rbac.post(
            "/api/rms/candidates",
            json=_candidate_json(
                job_a_id,
                name=cand_name,
                phone=raw_phone,
                email=raw_email,
                wechat=raw_wechat,
                email_wechat=raw_email,
            ),
        )
        assert created.status_code == 200, created.text
        cand_id = created.json()["id"]

        upload = client_rbac.post(
            f"/api/rms/candidates/{cand_id}/resume",
            files={"file": ("resume.txt", b"candidate resume", "text/plain")},
        )
        assert upload.status_code == 200, upload.text
        resume_id = upload.json()["id"]

        client_rbac.cookies.clear()
        client_rbac.cookies.update(login_b.cookies)
        searched = client_rbac.get(f"/api/rms/candidates?q={cand_name}")
        assert searched.status_code == 200, searched.text
        assert cand_id in _candidate_ids_from_list(searched.json())
        visible_a = next(c for c in searched.json() if c["id"] == cand_id)
        assert visible_a["can_write"] is False
        assert visible_a["can_delete"] is False
        assert visible_a["can_download_resume"] is False

        detail = client_rbac.get(f"/api/rms/candidates/{cand_id}")
        assert detail.status_code == 200, detail.text
        detail_body = detail.json()
        assert detail_body["phone"] == raw_phone
        assert detail_body["email"] == raw_email
        assert detail_body["wechat"] == raw_wechat
        assert detail_body["can_write"] is False
        assert detail_body["can_delete"] is False
        assert detail_body["can_download_resume"] is False

        blocked_patch = client_rbac.patch(
            f"/api/rms/candidates/{cand_id}",
            json={"city": "BlockedCity"},
        )
        assert blocked_patch.status_code in (403, 404), blocked_patch.text

        blocked_delete = client_rbac.delete(f"/api/rms/candidates/{cand_id}")
        assert blocked_delete.status_code in (403, 404), blocked_delete.text

        own_name = f"PoolOwn_{suffix}"
        own_created = client_rbac.post(
            "/api/rms/candidates",
            json=_candidate_json(
                job_b_id,
                name=own_name,
                phone=_unique_phone(),
                email=f"pool_own_{suffix}@example.com",
                wechat=f"wx_pool_own_{suffix}",
                email_wechat=f"pool_own_{suffix}@example.com",
            ),
        )
        assert own_created.status_code == 200, own_created.text
        own_id = own_created.json()["id"]
        assert own_created.json()["can_write"] is True
        assert own_created.json()["can_delete"] is True
        assert own_created.json()["can_download_resume"] is False

        own_search = client_rbac.get(f"/api/rms/candidates?q={own_name}")
        assert own_search.status_code == 200, own_search.text
        visible_own = next(c for c in own_search.json() if c["id"] == own_id)
        assert visible_own["can_write"] is True
        assert visible_own["can_delete"] is True

        own_patch = client_rbac.patch(
            f"/api/rms/candidates/{own_id}",
            json={"city": "SelfEditableCity"},
        )
        assert own_patch.status_code == 200, own_patch.text
        assert own_patch.json()["city"] == "SelfEditableCity"

        own_upload = client_rbac.post(
            f"/api/rms/candidates/{own_id}/resume",
            files={"file": ("own_resume.txt", b"own candidate resume", "text/plain")},
        )
        assert own_upload.status_code == 200, own_upload.text
        own_resume_id = own_upload.json()["id"]

        viewed = client_rbac.get(f"/api/rms/resumes/{resume_id}/view")
        assert viewed.status_code == 200, viewed.text

        downloaded = client_rbac.get(f"/api/rms/resumes/{resume_id}/download")
        assert downloaded.status_code == 403, downloaded.text

        _grant_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.resumes.download",))

        detail_before_recommend = client_rbac.get(f"/api/rms/candidates/{cand_id}")
        assert detail_before_recommend.status_code == 200, detail_before_recommend.text
        assert detail_before_recommend.json()["can_download_resume"] is False
        still_forbidden = client_rbac.get(f"/api/rms/resumes/{resume_id}/download")
        assert still_forbidden.status_code == 403, still_forbidden.text

        own_detail = client_rbac.get(f"/api/rms/candidates/{own_id}")
        assert own_detail.status_code == 200, own_detail.text
        assert own_detail.json()["can_download_resume"] is True
        own_download = client_rbac.get(f"/api/rms/resumes/{own_resume_id}/download")
        assert own_download.status_code == 200, own_download.text

        recommended = client_rbac.post(
            "/api/rms/applications",
            json={"job_id": job_b_id, "candidate_id": cand_id},
        )
        assert recommended.status_code == 200, recommended.text
        assert recommended.json()["candidate_id"] == cand_id
        assert recommended.json()["job_id"] == job_b_id
        assert recommended.json()["resume_id"] is None

        detail_after_recommend = client_rbac.get(f"/api/rms/candidates/{cand_id}")
        assert detail_after_recommend.status_code == 200, detail_after_recommend.text
        assert detail_after_recommend.json()["can_download_resume"] is True
        recommended_download = client_rbac.get(f"/api/rms/resumes/{resume_id}/download")
        assert recommended_download.status_code == 200, recommended_download.text

        forbidden = client_rbac.post(
            "/api/rms/applications",
            json={"job_id": job_a_id, "candidate_id": cand_id, "resume_id": resume_id},
        )
        assert forbidden.status_code in (403, 404), forbidden.text

        own_delete = client_rbac.delete(f"/api/rms/candidates/{own_id}")
        assert own_delete.status_code == 200, own_delete.text
    finally:
        _set_role_data_scope(
            rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "read", SCOPE_ASSIGNED
        )
        _set_role_data_scope(
            rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "write", SCOPE_ASSIGNED
        )
        _set_role_data_scope(
            rms_engine, ROLE_DELIVERY, RESOURCE_RMS_CANDIDATE, "delete", SCOPE_ASSIGNED
        )
        _set_role_data_scope(rms_engine, ROLE_DELIVERY, RESOURCE_RMS_RESUME, "read", SCOPE_ASSIGNED)
        _revoke_role_permissions(
            rms_engine,
            ROLE_DELIVERY,
            ("rms.resumes.read", "rms.resumes.download", "rms.contacts.view"),
        )


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
    _revoke_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
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


def test_candidate_create_duplicate_name_phone_returns_409(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"dup_{suffix}")
    phone = _unique_phone()
    payload = _candidate_json(job_id, name=f"DupCand_{suffix}", phone=phone)

    first = client_rbac.post("/api/rms/candidates", cookies=login.cookies, json=payload)
    assert first.status_code == 200, first.text

    with rms_engine.connect() as conn:
        cand_count = conn.execute(text("SELECT COUNT(*) FROM rms_candidates")).scalar()

    dup = client_rbac.post("/api/rms/candidates", cookies=login.cookies, json=payload)
    assert dup.status_code == 409, dup.text
    assert dup.json().get("detail") == "人选已存在系统中"

    with rms_engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM rms_candidates")).scalar() == cand_count

    other_phone = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name=f"DupCand_{suffix}", phone=_unique_phone()),
    )
    assert other_phone.status_code == 200, other_phone.text

    other_name = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, name=f"Other_{suffix}", phone=phone),
    )
    assert other_name.status_code == 200, other_name.text


def test_candidate_create_requires_available_date(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"avail_{suffix}")
    r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=_candidate_json(job_id, available_date=""),
    )
    assert r.status_code == 400, r.text
    assert r.json().get("detail") == "请填写到岗时间"


def test_candidate_create_allows_missing_target_job(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, job_id = _delivery_open_job(client_rbac, rms_engine, admin_auth, f"nojob_{suffix}")
    payload = _candidate_json(job_id, name=f"NoJob_{suffix}", phone=_unique_phone())
    payload["target_job_id"] = None
    r = client_rbac.post(
        "/api/rms/candidates",
        cookies=login.cookies,
        json=payload,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("target_job_id") in (None, "")


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
    _grant_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
    try:
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
    finally:
        _revoke_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))


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

    cand_detail = client_rbac.get(
        f"/api/rms/candidates/{cand.json()['id']}",
        cookies=login_del.cookies,
    )
    assert cand_detail.status_code == 200, cand_detail.text
    assert cand_detail.json()["target_job_id"] == job_b.json()["id"]
    assert cand_detail.json()["target_client_id"] == cid_b


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


def test_status_duplicate_from_client_screen(client_rbac, admin_auth, rms_engine, uniq):
    suffix = uniq
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, suffix)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "client_screen_duplicate", "reason": "client duplicate"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "client_screen_duplicate"
    assert r.json()["current_stage"] == "client_screen_duplicate"


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


def _advance_to_onboarding(client, login, app_id, *, engine=None):
    client.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed"},
    )
    steps = [
        "scheduling_interview",
        "pending_first_interview",
        "first_interview_passed",
        "second_interview_passed",
        "pending_offer",
    ]
    for st in steps:
        r = client.post(
            f"/api/rms/applications/{app_id}/status",
            cookies=login.cookies,
            json={"to_status": st},
        )
        assert r.status_code == 200, r.text
    if engine is not None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE rms_applications SET status = 'onboarding', current_stage = 'onboarding' "
                    "WHERE id = :id"
                ),
                {"id": app_id},
            )


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
    _advance_to_onboarding(client_rbac, login, app_id, engine=rms_engine)
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


def test_application_read_scope_includes_own_recommendations(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    recruiter_role = _create_recruiter_role(
        client_rbac,
        admin_auth,
        rms_engine,
        suffix,
        permission_codes=(
            "rms.applications.read",
            "rms.applications.write",
            "rms.applications.delete",
        ),
        read_scope=SCOPE_ASSIGNED,
        write_scope=SCOPE_NONE,
        delete_scope=SCOPE_NONE,
    )
    a4 = f"rms2_rec_a4_{suffix}"
    other = f"rms2_rec_b_{suffix}"
    a4_uid = _create_user(client_rbac, admin_auth, a4, [recruiter_role])
    other_uid = _create_user(client_rbac, admin_auth, other, [recruiter_role])

    login_del, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"recscope_{suffix}"
    )
    passed = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert passed.status_code == 200, passed.text
    passed_id = int(passed.json()["id"])
    _set_application_recommended_by(
        rms_engine, passed_id, a4_uid, delivery_review_status="passed"
    )

    pending_cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_id, name=f"Pending {suffix}", phone=_unique_phone()),
    )
    assert pending_cand.status_code == 200, pending_cand.text
    pending = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": pending_cand.json()["id"]},
    )
    assert pending.status_code == 200, pending.text
    pending_id = int(pending.json()["id"])
    _set_application_recommended_by(
        rms_engine, pending_id, a4_uid, delivery_review_status="pending"
    )

    other_cand = client_rbac.post(
        "/api/rms/candidates",
        cookies=login_del.cookies,
        json=_candidate_json(job_id, name=f"Other {suffix}", phone=_unique_phone()),
    )
    assert other_cand.status_code == 200, other_cand.text
    foreign = client_rbac.post(
        "/api/rms/applications",
        cookies=login_del.cookies,
        json={"job_id": job_id, "candidate_id": other_cand.json()["id"]},
    )
    assert foreign.status_code == 200, foreign.text
    foreign_id = int(foreign.json()["id"])
    _set_application_recommended_by(rms_engine, foreign_id, other_uid)

    login_a4 = _login(client_rbac, a4)
    assert login_a4.status_code == 200

    listed = client_rbac.get("/api/rms/applications", cookies=login_a4.cookies)
    assert listed.status_code == 200, listed.text
    listed_ids = {int(row["id"]) for row in listed.json()}
    assert passed_id in listed_ids
    assert pending_id in listed_ids
    assert foreign_id not in listed_ids
    passed_row = next(row for row in listed.json() if int(row["id"]) == passed_id)
    assert passed_row["delivery_review_status"] == "passed"

    detail = client_rbac.get(f"/api/rms/applications/{passed_id}", cookies=login_a4.cookies)
    assert detail.status_code == 200, detail.text
    assert detail.json()["delivery_review_status"] == "passed"

    history = client_rbac.get(
        f"/api/rms/applications/{passed_id}/status-history",
        cookies=login_a4.cookies,
    )
    assert history.status_code == 200, history.text

    blocked = client_rbac.get(f"/api/rms/applications/{foreign_id}", cookies=login_a4.cookies)
    assert blocked.status_code == 404

    patch = client_rbac.patch(
        f"/api/rms/applications/{passed_id}",
        cookies=login_a4.cookies,
        json={"resume_id": None},
    )
    assert patch.status_code == 404

    status = client_rbac.post(
        f"/api/rms/applications/{passed_id}/status",
        cookies=login_a4.cookies,
        json={"to_status": "screening"},
    )
    assert status.status_code == 404

    deleted = client_rbac.delete(
        f"/api/rms/applications/{passed_id}",
        cookies=login_a4.cookies,
    )
    assert deleted.status_code == 404

    delivery_review = client_rbac.get(
        "/api/rms/applications/delivery-review",
        cookies=login_a4.cookies,
    )
    assert delivery_review.status_code == 200, delivery_review.text
    review_ids = {int(row["id"]) for row in delivery_review.json()}
    assert pending_id not in review_ids

    me = client_rbac.get("/api/me", cookies=login_a4.cookies)
    assert me.status_code == 200, me.text
    assert me.json().get("rms_delivery_ops_tabs") is False


def test_delivery_user_me_exposes_rms_delivery_ops_tabs(
    client_rbac, admin_auth, rms_engine, uniq
):
    suffix = uniq
    login_del, _ = _delivery_open_job(client_rbac, rms_engine, admin_auth, suffix)
    me = client_rbac.get("/api/me", cookies=login_del.cookies)
    assert me.status_code == 200, me.text
    assert me.json().get("rms_delivery_ops_tabs") is True
