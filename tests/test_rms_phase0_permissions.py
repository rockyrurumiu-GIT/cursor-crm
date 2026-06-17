"""RMS Phase 0: permission catalog, data scope seed, shell routes."""
from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth import service as auth_svc
from auth.data_scope_catalog import (
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_CANDIDATE,
    RESOURCE_RMS_JOB,
    RESOURCE_RMS_RESUME,
    RESOURCE_SCOPE_ANCHOR,
    SCOPE_ASSIGNED,
    SCOPE_DEPT,
    SCOPE_NONE,
    permission_to_resource,
)
from auth.permissions import (
    ALL_PERMISSION_CODES,
    NAV_SECTION_PERMISSIONS,
    ROLE_DEFAULT_PERMISSIONS,
    ROLE_DELIVERY,
    ROLE_SALES,
    ROLE_SUPER_ADMIN,
    ROLE_VIEWER,
)
from tests.helpers import auth_header

RMS_PERMISSION_CODES = frozenset({
    "rms.jobs.read",
    "rms.jobs.write",
    "rms.jobs.delete",
    "rms.candidates.read",
    "rms.candidates.write",
    "rms.candidates.delete",
    "rms.resumes.read",
    "rms.resumes.download",
    "rms.contacts.view",
    "rms.applications.read",
    "rms.applications.write",
    "rms.applications.delete",
    "rms.matching.run",
    "rms.analytics.read",
})


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


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


@pytest.fixture
def rms_engine(client_rbac):
    import main as crm_main

    return crm_main.engine


def _create_user(client, admin_auth, username: str, role_codes: list[str], password: str = "pass1234"):
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


def test_rms_permission_codes_registered():
    assert RMS_PERMISSION_CODES <= ALL_PERMISSION_CODES


def test_nav_section_rms_gate():
    assert NAV_SECTION_PERMISSIONS["rms"] == "rms.jobs.read"


def test_contacts_view_maps_to_candidate():
    assert permission_to_resource("rms.contacts.view") == RESOURCE_RMS_CANDIDATE


def test_matching_run_maps_to_job():
    assert permission_to_resource("rms.matching.run") == RESOURCE_RMS_JOB


def test_rms_application_anchor_inherits_client():
    anchor = RESOURCE_SCOPE_ANCHOR[RESOURCE_RMS_APPLICATION]
    assert anchor.inherit_via_client is True
    assert anchor.client_fk == "client_id"


def test_rms_job_anchor_inherits_client():
    anchor = RESOURCE_SCOPE_ANCHOR[RESOURCE_RMS_JOB]
    assert anchor.inherit_via_client is True
    assert anchor.client_fk == "client_id"


def test_role_default_permissions():
    assert RMS_PERMISSION_CODES <= ROLE_DEFAULT_PERMISSIONS[ROLE_SUPER_ADMIN]
    delivery_rms = ROLE_DEFAULT_PERMISSIONS[ROLE_DELIVERY] & RMS_PERMISSION_CODES
    assert delivery_rms == frozenset({
        "rms.jobs.read",
        "rms.applications.read",
        "rms.analytics.read",
    })
    assert not (ROLE_DEFAULT_PERMISSIONS[ROLE_SALES] & RMS_PERMISSION_CODES)
    assert not (ROLE_DEFAULT_PERMISSIONS[ROLE_VIEWER] & RMS_PERMISSION_CODES)


def test_viewer_scope_rows_skip_rms():
    rows = auth_svc._scope_rows_for_role(ROLE_VIEWER)
    assert not any(resource.startswith("rms.") for resource, _action in rows)


def test_delivery_scope_rows_include_rms_read_only():
    rows = auth_svc._scope_rows_for_role(ROLE_DELIVERY)
    assert rows[(RESOURCE_RMS_JOB, "read")] == SCOPE_ASSIGNED
    assert rows[(RESOURCE_RMS_APPLICATION, "read")] == SCOPE_ASSIGNED
    assert rows[(RESOURCE_RMS_JOB, "write")] == "none"


def test_data_scope_matrix_rms_labels():
    matrix = auth_svc.build_data_scope_matrix([])
    labels = {row["resource_code"]: row["label"] for row in matrix["rows"]}
    assert labels[RESOURCE_RMS_JOB] == "招聘岗位"
    assert labels[RESOURCE_RMS_APPLICATION] == "推荐记录"
    assert labels[RESOURCE_RMS_CANDIDATE] == "候选人"
    assert labels[RESOURCE_RMS_RESUME] == "简历"


def test_seed_backfills_delivery_rms_read_scope(client_rbac, admin_auth):
    import main as crm_main
    from sqlalchemy.orm import Session

    with crm_main.engine.begin() as conn:
        rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = :c"),
            {"c": ROLE_DELIVERY},
        ).scalar()
        assert rid is not None
        conn.execute(
            text(
                "DELETE FROM sys_role_data_scope "
                "WHERE role_id = :rid AND resource_code LIKE 'rms.%'"
            ),
            {"rid": rid},
        )

    with Session(crm_main.engine) as db:
        role_ids = {
            str(row[1]): int(row[0])
            for row in db.execute(text("SELECT id, code FROM sys_role")).fetchall()
        }
        auth_svc.seed_role_data_scopes(db, role_ids)
        db.commit()

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT scope_type FROM sys_role_data_scope "
                "WHERE role_id = (SELECT id FROM sys_role WHERE code = :c) "
                "AND resource_code = :rc AND action = 'read'"
            ),
            {"c": ROLE_DELIVERY, "rc": RESOURCE_RMS_JOB},
        ).fetchone()
    assert row is not None
    assert row[0] == SCOPE_ASSIGNED


def test_seed_does_not_overwrite_existing_scope(client_rbac, admin_auth):
    import main as crm_main
    from sqlalchemy.orm import Session

    with crm_main.engine.begin() as conn:
        rid = conn.execute(
            text("SELECT id FROM sys_role WHERE code = :c"),
            {"c": ROLE_DELIVERY},
        ).scalar()
        conn.execute(
            text(
                "DELETE FROM sys_role_data_scope "
                "WHERE role_id = :rid AND resource_code = :rc AND action = 'read'"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_JOB},
        )
        conn.execute(
            text(
                "INSERT INTO sys_role_data_scope "
                "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                "VALUES (:rid, :rc, 'read', :st, datetime('now'), datetime('now'))"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_JOB, "st": SCOPE_DEPT},
        )

    with Session(crm_main.engine) as db:
        role_ids = {
            str(row[1]): int(row[0])
            for row in db.execute(text("SELECT id, code FROM sys_role")).fetchall()
        }
        auth_svc.seed_role_data_scopes(db, role_ids)
        db.commit()

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT scope_type FROM sys_role_data_scope "
                "WHERE role_id = (SELECT id FROM sys_role WHERE code = :c) "
                "AND resource_code = :rc AND action = 'read'"
            ),
            {"c": ROLE_DELIVERY, "rc": RESOURCE_RMS_JOB},
        ).fetchone()
    assert row is not None
    assert row[0] == SCOPE_DEPT


def test_get_rms_page_forbidden_without_perm(client_rbac, admin_auth, rms_engine):
    # Product default: SALES has no rms.jobs.read. Earlier RMS tests may grant it on the shared role row.
    _revoke_role_permissions(
        rms_engine,
        ROLE_SALES,
        ("rms.jobs.read", "rms.jobs.write"),
    )
    suffix = os.getpid()
    sales_user = f"rms_sales_{suffix}"
    _create_user(client_rbac, admin_auth, sales_user, [ROLE_SALES])
    login = _login(client_rbac, sales_user, "pass1234")
    assert login.status_code == 200
    page = client_rbac.get("/rms", cookies=login.cookies)
    assert page.status_code == 403


def test_get_rms_page_ok_with_delivery_default(client_rbac, admin_auth):
    suffix = os.getpid()
    delivery_user = f"rms_delivery_{suffix}"
    _create_user(client_rbac, admin_auth, delivery_user, [ROLE_DELIVERY])
    login = _login(client_rbac, delivery_user, "pass1234")
    assert login.status_code == 200
    page = client_rbac.get("/rms", cookies=login.cookies)
    assert page.status_code == 200
    assert "招聘" in page.text

    health = client_rbac.get("/api/rms/health", cookies=login.cookies)
    assert health.status_code == 200
    assert health.json()["phase"] == 2


def test_seed_rbac_keeps_extra_permissions_on_builtin_role(client_rbac, admin_auth):
    """Restart seed must not wipe manually granted RMS perms on DELIVERY."""
    import main as crm_main
    from auth.permissions import ROLE_DELIVERY

    with crm_main.engine.connect() as conn:
        rid = int(
            conn.execute(
                text("SELECT id FROM sys_role WHERE code = :c"),
                {"c": ROLE_DELIVERY},
            ).fetchone()[0]
        )
        pid = conn.execute(
            text("SELECT id FROM sys_permission WHERE code = 'rms.candidates.read'"),
        ).fetchone()
        assert pid is not None
        conn.execute(
            text(
                "INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id) "
                "VALUES (:rid, :pid)"
            ),
            {"rid": rid, "pid": int(pid[0])},
        )
        conn.commit()

    db = crm_main.SessionLocal()
    try:
        auth_svc.seed_rbac_data(db, admin_username="admin", admin_password="unused")
        db.commit()
        perms = auth_svc._role_permission_codes(db, rid)
    finally:
        db.close()
    assert "rms.candidates.read" in perms


def test_custom_role_rms_permissions_persist_after_save(client_rbac, admin_auth):
    """RMS 权限码须能写入自定义角色；保存前自动补齐 sys_permission 行。"""
    user, pwd = admin_auth
    headers = {**auth_header(user, pwd), "Content-Type": "application/json"}
    suffix = os.getpid()
    role_name = f"招聘测试_{suffix}"
    created = client_rbac.post(
        "/api/system/roles",
        headers=headers,
        json={"name": role_name, "description": "RMS 权限保存测试"},
    )
    assert created.status_code == 200, created.text
    role_id = created.json()["id"]

    rms_codes = sorted(RMS_PERMISSION_CODES)
    saved = client_rbac.put(
        f"/api/system/roles/{role_id}/permissions",
        headers=headers,
        json={"permission_codes": rms_codes},
    )
    assert saved.status_code == 200, saved.text

    matrix = client_rbac.get(
        f"/api/system/permissions/matrix?role_id={role_id}",
        headers=headers,
    )
    assert matrix.status_code == 200
    granted = set()
    for mod in matrix.json().get("modules") or []:
        for row in mod.get("rows") or []:
            granted.update(row.get("codes") or [])
    assert RMS_PERMISSION_CODES <= granted


def test_matrix_selection_maps_rms_rows_to_codes():
    from auth.permission_catalog import _MATRIX_ROWS, permission_codes_from_matrix_selection

    selected = {}
    for row in _MATRIX_ROWS:
        if row.get("module") != "rms":
            continue
        selected[row["label"]] = {
            "read": bool(row.get("read")),
            "write": bool(row.get("write")),
            "delete": bool(row.get("delete")),
            "import_export": bool(row.get("import_export")),
            "approve": bool(row.get("approve")),
        }
    codes = set(permission_codes_from_matrix_selection(selected))
    assert RMS_PERMISSION_CODES <= codes


def test_matrix_rms_application_write_does_not_grant_delete():
    from auth.permission_catalog import permission_codes_from_matrix_selection

    codes = set(permission_codes_from_matrix_selection({
        "推荐记录": {
            "read": False,
            "write": True,
            "delete": False,
            "import_export": False,
            "approve": False,
        }
    }))
    assert "rms.applications.write" in codes
    assert "rms.applications.delete" not in codes


def test_delete_permission_backfill_runs_once(client_rbac, admin_auth):
    import main as crm_main

    role_code = f"DELETE_BACKFILL_{os.getpid()}"
    marker = auth_svc.DELETE_PERMISSION_BACKFILL_ID
    db = crm_main.SessionLocal()
    try:
        auth_svc.sync_permission_catalog_rows(db)
        db.execute(text("DELETE FROM schema_migrations WHERE migration_id = :id"), {"id": marker})
        db.execute(
            text(
                "INSERT INTO sys_role (code, name, description, is_builtin, created_at) "
                "VALUES (:code, :name, '', 0, datetime('now'))"
            ),
            {"code": role_code, "name": role_code},
        )
        rid = int(db.execute(text("SELECT id FROM sys_role WHERE code = :code"), {"code": role_code}).scalar())
        write_pid = int(db.execute(
            text("SELECT id FROM sys_permission WHERE code = 'rms.applications.write'")
        ).scalar())
        delete_pid = int(db.execute(
            text("SELECT id FROM sys_permission WHERE code = 'rms.applications.delete'")
        ).scalar())
        db.execute(
            text("INSERT INTO sys_role_permission (role_id, permission_id) VALUES (:rid, :pid)"),
            {"rid": rid, "pid": write_pid},
        )
        db.execute(
            text(
                "INSERT INTO sys_role_data_scope "
                "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                "VALUES (:rid, :rc, 'write', :st, datetime('now'), datetime('now'))"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_APPLICATION, "st": SCOPE_ASSIGNED},
        )
        db.execute(
            text(
                "INSERT INTO sys_role_data_scope "
                "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                "VALUES (:rid, :rc, 'delete', 'none', datetime('now'), datetime('now'))"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_APPLICATION},
        )

        auth_svc.backfill_delete_permissions_once(db)
        has_delete = db.execute(
            text(
                "SELECT 1 FROM sys_role_permission "
                "WHERE role_id = :rid AND permission_id = :pid"
            ),
            {"rid": rid, "pid": delete_pid},
        ).fetchone()
        delete_scope = db.execute(
            text(
                "SELECT scope_type FROM sys_role_data_scope "
                "WHERE role_id = :rid AND resource_code = :rc AND action = 'delete'"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_APPLICATION},
        ).scalar()
        assert has_delete is not None
        assert delete_scope == SCOPE_ASSIGNED

        db.execute(
            text(
                "DELETE FROM sys_role_permission "
                "WHERE role_id = :rid AND permission_id = :pid"
            ),
            {"rid": rid, "pid": delete_pid},
        )
        db.execute(
            text(
                "UPDATE sys_role_data_scope SET scope_type = 'none' "
                "WHERE role_id = :rid AND resource_code = :rc AND action = 'delete'"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_APPLICATION},
        )
        auth_svc.backfill_delete_permissions_once(db)
        has_delete_after_second_run = db.execute(
            text(
                "SELECT 1 FROM sys_role_permission "
                "WHERE role_id = :rid AND permission_id = :pid"
            ),
            {"rid": rid, "pid": delete_pid},
        ).fetchone()
        delete_scope_after_second_run = db.execute(
            text(
                "SELECT scope_type FROM sys_role_data_scope "
                "WHERE role_id = :rid AND resource_code = :rc AND action = 'delete'"
            ),
            {"rid": rid, "rc": RESOURCE_RMS_APPLICATION},
        ).scalar()
        assert has_delete_after_second_run is None
        assert delete_scope_after_second_run == SCOPE_NONE
    finally:
        db.rollback()
        db.close()
