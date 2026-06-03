"""Data scope integration tests (02.5)."""
from __future__ import annotations

import importlib
import os

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.data_scope import apply_client_scope, get_effective_data_scope, merge_scope_types
from auth.data_scope_catalog import (
    RESOURCE_CRM_CLIENT,
    SCOPE_ALL,
    SCOPE_ASSIGNED,
    SCOPE_DEPT,
    SCOPE_NONE,
)
from auth.service import AuthContext
from tests.helpers import auth_header


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


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


def test_migration_004_applied(client):
    import main as crm_main

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id = '004_permission_datascope.sql'")
        ).fetchone()
    assert row is not None


def test_scope_merge_unit():
    assert merge_scope_types("none", "self") == "self"
    assert merge_scope_types("assigned", "dept") == "dept"


def test_viewer_cannot_set_role_data_scopes(client_rbac, admin_auth):
    suffix = os.getpid()
    _create_user(client_rbac, admin_auth, f"viewer_ds_{suffix}", ["VIEWER"])
    login = _login(client_rbac, f"viewer_ds_{suffix}", "pass1234")
    import main as crm_main

    with crm_main.engine.connect() as conn:
        rid = conn.execute(text("SELECT id FROM sys_role WHERE code = 'SALES'")).fetchone()[0]
    r = client_rbac.put(
        f"/api/system/roles/{rid}/data-scopes",
        cookies=login.cookies,
        json={"scopes": [{"resource_code": "crm.client", "action": "read", "scope_type": "all"}]},
    )
    assert r.status_code == 403


def test_sales_users_see_only_own_clients(client_rbac, admin_auth):
    suffix = os.getpid()
    sales_a = f"sales_a_{suffix}"
    sales_b = f"sales_b_{suffix}"
    uid_a = _create_user(client_rbac, admin_auth, sales_a, ["SALES"])
    uid_b = _create_user(client_rbac, admin_auth, sales_b, ["SALES"])
    admin_user, admin_pwd = admin_auth
    headers = auth_header(admin_user, admin_pwd)

    c1 = client_rbac.post(
        "/api/clients",
        headers=headers,
        data={
            "name": f"客户A_{suffix}",
            "industry": "IT",
            "owner": sales_a,
            "scale": "100",
            "phase": "初步接触",
            "description": "d",
        },
    )
    assert c1.status_code == 200, c1.text
    client_a_id = c1.json()["id"]

    c2 = client_rbac.post(
        "/api/clients",
        headers=headers,
        data={
            "name": f"客户B_{suffix}",
            "industry": "IT",
            "owner": sales_b,
            "scale": "100",
            "phase": "初步接触",
            "description": "d",
        },
    )
    assert c2.status_code == 200, c2.text
    client_b_id = c2.json()["id"]

    import main as crm_main

    _set_client_owner(crm_main.engine, client_a_id, uid_a)
    _set_client_owner(crm_main.engine, client_b_id, uid_b)

    login_a = _login(client_rbac, sales_a, "pass1234")
    listed = client_rbac.get("/api/clients", cookies=login_a.cookies).json()
    ids = {x["id"] for x in listed}
    assert client_a_id in ids
    assert client_b_id not in ids

    detail_b = client_rbac.get(f"/api/clients/{client_b_id}", cookies=login_a.cookies)
    assert detail_b.status_code == 404

    brief_b = client_rbac.get(f"/api/clients/{client_b_id}/brief", cookies=login_a.cookies)
    assert brief_b.status_code == 404


def test_super_admin_sees_all_clients(client_rbac, admin_auth):
    login = _login(client_rbac, admin_auth[0], admin_auth[1])
    r = client_rbac.get("/api/clients", cookies=login.cookies)
    assert r.status_code == 200


def test_delivery_settlement_scoped_by_delivery_owner(client_rbac, admin_auth):
    suffix = os.getpid()
    delivery_a = f"delivery_a_{suffix}"
    delivery_b = f"delivery_b_{suffix}"
    uid_a = _create_user(client_rbac, admin_auth, delivery_a, ["DELIVERY"])
    uid_b = _create_user(client_rbac, admin_auth, delivery_b, ["DELIVERY"])
    admin_user, admin_pwd = admin_auth
    headers = auth_header(admin_user, admin_pwd)

    c1 = client_rbac.post(
        "/api/clients",
        headers=headers,
        data={
            "name": f"交付客户A_{suffix}",
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
            "name": f"交付客户B_{suffix}",
            "industry": "IT",
            "owner": "admin",
            "scale": "100",
            "phase": "成交",
            "description": "d",
        },
    )
    assert c1.status_code == 200 and c2.status_code == 200
    cid_a, cid_b = c1.json()["id"], c2.json()["id"]
    import main as crm_main

    _set_client_owner(crm_main.engine, cid_a, uid_a, delivery_owner_user_id=uid_a)
    _set_client_owner(crm_main.engine, cid_b, uid_b, delivery_owner_user_id=uid_b)

    with crm_main.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO delivery_settlement_entries (client_id, customer_name, serial_no) "
                "VALUES (:c1, 'A', '1'), (:c2, 'B', '2')"
            ),
            {"c1": cid_a, "c2": cid_b},
        )

    login_a = _login(client_rbac, delivery_a, "pass1234")
    rows = client_rbac.get("/api/delivery/settlement", cookies=login_a.cookies).json()
    client_ids = {int(r.get("client_id") or 0) for r in rows}
    assert cid_a in client_ids
    assert cid_b not in client_ids


def test_permission_preview_api(client_rbac, admin_auth):
    suffix = os.getpid()
    uid = _create_user(client_rbac, admin_auth, f"preview_{suffix}", ["SALES"])
    admin_user, admin_pwd = admin_auth
    headers = auth_header(admin_user, admin_pwd)
    r = client_rbac.get(f"/api/system/users/{uid}/permission-preview", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "SALES" in body["roles"]
    assert body["data_scopes"]
    scope_map = {(x["resource_code"], x["action"]): x["scope_type"] for x in body["data_scopes"]}
    assert scope_map.get((RESOURCE_CRM_CLIENT, "read")) == SCOPE_ASSIGNED


def test_get_effective_data_scope_default_none():
    from auth.service import AuthContext

    ctx = AuthContext(username="x", user_id=1, roles=["RESTRICTED"], permissions=set())
    assert get_effective_data_scope(ctx, RESOURCE_CRM_CLIENT, "read") == SCOPE_NONE


def test_get_effective_data_scope_super_all():
    from auth.service import AuthContext

    ctx = AuthContext(username="admin", is_super=True)
    assert get_effective_data_scope(ctx, RESOURCE_CRM_CLIENT, "read") == SCOPE_ALL


def test_crm_client_dept_scope_matches_any_role_dept_column(client_rbac):
    """crm.client dept scope: owner / delivery / recruitment dept columns are OR-matched."""
    import main as crm_main
    from sqlalchemy.orm import sessionmaker

    suffix = os.getpid()
    other_dept = 970000 + (suffix % 1000)
    match_dept = other_dept + 1
    engine = crm_main.engine
    now = "2026-06-03T00:00:00Z"

    with engine.begin() as conn:
        for did, name in ((other_dept, f"其他部门_{suffix}"), (match_dept, f"匹配部门_{suffix}")):
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO sys_dept "
                    "(id, name, code, parent_id, path, dept_type, status, created_at, updated_at) "
                    "VALUES (:id, :name, :code, NULL, :path, 'internal', 'active', :at, :at)"
                ),
                {"id": did, "name": name, "code": f"D{did}", "path": f"/{did}/", "at": now},
            )

    Session = sessionmaker(bind=engine)
    db = Session()
    Client = crm_main.Client
    try:
        ctx = AuthContext(
            username="scope_tester",
            user_id=1,
            permissions={"crm.clients.read"},
            dept_ids=[match_dept],
            primary_dept_id=match_dept,
            role_data_scopes={(RESOURCE_CRM_CLIENT, "read"): SCOPE_DEPT},
        )

        def visible_ids():
            return {
                int(r[0])
                for r in apply_client_scope(
                    db.query(Client.id),
                    db,
                    ctx,
                    RESOURCE_CRM_CLIENT,
                    "read",
                    Client,
                ).all()
            }

        c_delivery = Client(
            name=f"交付部门可见_{suffix}",
            industry="IT",
            owner="admin",
            scale="100",
            phase="初步接触",
            description="d",
            owner_dept_id=other_dept,
            delivery_dept_id=match_dept,
        )
        c_recruitment = Client(
            name=f"招聘部门可见_{suffix}",
            industry="IT",
            owner="admin",
            scale="100",
            phase="初步接触",
            description="d",
            owner_dept_id=other_dept,
            recruitment_dept_id=match_dept,
        )
        c_hidden = Client(
            name=f"三部门均不可见_{suffix}",
            industry="IT",
            owner="admin",
            scale="100",
            phase="初步接触",
            description="d",
            owner_dept_id=other_dept,
            delivery_dept_id=other_dept,
            recruitment_dept_id=other_dept,
        )
        db.add_all([c_delivery, c_recruitment, c_hidden])
        db.commit()

        ids = visible_ids()
        assert c_delivery.id in ids
        assert c_recruitment.id in ids
        assert c_hidden.id not in ids
    finally:
        db.close()


def test_migration_006_recruitment_columns(client):
    import main as crm_main

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id = :id"),
            {"id": "006_client_recruitment_owner.sql"},
        ).fetchone()
        cols = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(clients)")).fetchall()
        }
    assert row is not None
    assert "recruitment_owner_user_id" in cols
    assert "recruitment_dept_id" in cols


def test_migration_006_skips_existing_columns_and_records_ledger(client):
    """Columns pre-exist (compat/create_all) but 006 not in ledger: runner must skip ADD COLUMN."""
    import main as crm_main

    from auth.migrate import run_all as run_schema_migrations

    mid = "006_client_recruitment_owner.sql"
    with crm_main.engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(clients)")).fetchall()}
        assert "recruitment_owner_user_id" in cols
        assert "recruitment_dept_id" in cols
        conn.execute(text("DELETE FROM schema_migrations WHERE migration_id = :id"), {"id": mid})

    run_schema_migrations(crm_main.engine)

    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT migration_id FROM schema_migrations WHERE migration_id = :id"),
            {"id": mid},
        ).fetchone()
        assert row is not None
        indexes = {str(r[1]) for r in conn.execute(text("PRAGMA index_list(clients)")).fetchall()}
    assert "idx_clients_recruitment_owner_user_id" in indexes
    assert "idx_clients_recruitment_dept_id" in indexes


def test_migration_006_idempotent_second_run(client):
    import main as crm_main

    from auth.migrate import run_all as run_schema_migrations

    run_schema_migrations(crm_main.engine)
    run_schema_migrations(crm_main.engine)
    with crm_main.engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = :id"),
            {"id": "006_client_recruitment_owner.sql"},
        ).scalar()
    assert int(count or 0) == 1
