"""Delivery org department helpers tests."""
from __future__ import annotations

import importlib

import pytest
from starlette.testclient import TestClient

from auth import delivery_nav as delivery_nav_mod
from auth.service import AuthContext
from tests.test_rms_phase2_mvp import _ensure_dept


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

    return crm_main.engine


def test_delivery_org_dept_match_by_name_and_path(rms_engine):
    dept_id = 994001
    _ensure_dept(rms_engine, dept_id, "华东交付部", path="ROOT/DELIVERY_EAST")
    child_id = dept_id + 1
    _ensure_dept(
        rms_engine,
        child_id,
        "交付一组",
        path="ROOT/DELIVERY_EAST/G1",
        parent_id=dept_id,
    )
    with rms_engine.connect() as conn:
        db = __import__("sqlalchemy.orm", fromlist=["Session"]).Session(bind=conn)
        try:
            ids = delivery_nav_mod.delivery_org_dept_ids(db)
            assert dept_id in ids
            assert child_id in ids
            ctx = AuthContext(username="u", user_id=1, dept_ids=[child_id], primary_dept_id=child_id)
            assert delivery_nav_mod.user_in_delivery_org_dept(db, ctx) is True
            other = AuthContext(username="o", user_id=2, dept_ids=[999999], primary_dept_id=999999)
            assert delivery_nav_mod.user_in_delivery_org_dept(db, other) is False
            super_ctx = AuthContext(username="admin", user_id=3, is_super=True, dept_ids=[child_id])
            assert delivery_nav_mod.user_in_delivery_org_dept(db, super_ctx) is False
        finally:
            db.close()
