"""RMS: recommend existing candidate via POST /api/rms/applications."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.test_rms_phase2_mvp import (
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _trial_job_and_candidate,
)


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


def _count_candidates(engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT COUNT(*) FROM rms_candidates")).scalar() or 0)


def test_recommend_existing_candidate_creates_application_only(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, job_id, cand_id, client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, uniq
    )
    before = _count_candidates(rms_engine)

    r = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id, "resume_id": None},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["candidate_id"] == cand_id
    assert body["job_id"] == job_id
    assert body["client_id"] == client_id
    assert _count_candidates(rms_engine) == before


def test_recommend_existing_candidate_duplicate_409(client_rbac, admin_auth, rms_engine, uniq):
    login, job_id, cand_id, _ = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, uniq
    )
    first = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert first.status_code == 200

    before = _count_candidates(rms_engine)
    dup = client_rbac.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert dup.status_code == 409
    assert "该岗位已存在该候选人的推荐记录" in dup.json().get("detail", "")
    assert _count_candidates(rms_engine) == before
