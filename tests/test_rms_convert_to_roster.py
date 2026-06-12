"""RMS hired application → roster conversion (Phase 5A)."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from tests.test_rms_phase2_mvp import (
    _advance_to_onboarding,
    _app_for_status,
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
def crm_main(_test_env):
    import main as crm_main

    importlib.reload(crm_main)
    return crm_main


@pytest.fixture
def rms_engine(client_rbac):
    import main as crm_main

    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)
    return crm_main.engine


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


def _unique_phone(seed: str) -> str:
    core = f"{abs(hash(seed)):08d}"[-8:]
    return f"138{core}"


def _hired_application(client, rms_engine, admin_auth, uniq: str):
    login, job_id, cand_id, client_id = _trial_job_and_candidate(
        client, rms_engine, admin_auth, uniq
    )
    created = client.post(
        "/api/rms/applications",
        cookies=login.cookies,
        json={"job_id": job_id, "candidate_id": cand_id},
    )
    assert created.status_code == 200, created.text
    app_id = created.json()["id"]
    review = client.post(
        f"/api/rms/applications/{app_id}/delivery-review",
        cookies=login.cookies,
        json={"result": "passed"},
    )
    assert review.status_code == 200, review.text
    _advance_to_onboarding(client, login, app_id)
    hired = client.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "hired_at": "2026-06-15"},
    )
    assert hired.status_code == 200, hired.text
    cand = client.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies).json()
    client_row = client.get(f"/api/clients/{client_id}", cookies=login.cookies).json()
    job = client.get(f"/api/rms/jobs/{job_id}", cookies=login.cookies).json()
    return login, app_id, client_id, cand, client_row, job


def _full_roster_payload(cand, client_row, job, **overrides):
    base = {
        "employment_status": "在职",
        "full_name": cand.get("name") or "测试员工",
        "contact_info": "13700137000",
        "customer_name": client_row.get("name") or "测试客户",
        "work_location": job.get("location") or "上海",
        "position_title": job.get("title") or "工程师",
        "business_line": "测试线",
        "entry_date": "2026-06-15",
        "monthly_quote_tax": "10000",
        "pre_tax_salary": "8000",
        "gms": "2000",
        "gm_pct": "20%",
        "zntx_onboarding_channel": "RMS",
        "remarks": "测试转入",
    }
    base.update(overrides)
    return base


def test_non_hired_roster_draft_returns_400(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/roster-draft",
        cookies=login.cookies,
    )
    assert r.status_code == 400


def test_non_hired_convert_returns_400(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id = _app_for_status(client_rbac, rms_engine, admin_auth, uniq)
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json={"full_name": "x"},
    )
    assert r.status_code == 400


def test_hired_roster_draft_prefill(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, client_id, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, uniq
    )
    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/roster-draft",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["application_id"] == app_id
    assert body["client_id"] == client_id
    assert body["converted_to_roster_entry_id"] is None
    payload = body["roster_payload"]
    assert payload["full_name"] == cand["name"]
    assert payload["contact_info"] == "13700137000"
    assert payload["customer_name"] == client_row["name"]
    assert payload["position_title"] == job["title"]
    assert payload["work_location"] == (job.get("location") or "")
    assert payload["entry_date"] == "2026-06-15"
    assert payload["employment_status"] == "在职"
    assert payload["zntx_onboarding_channel"] == "RMS"
    assert f"#{app_id}" in payload["remarks"]


def test_convert_missing_required_fields_400(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, _cid, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, uniq
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json={
            "full_name": cand["name"],
            "contact_info": cand["phone"],
            "customer_name": client_row["name"],
        },
    )
    assert r.status_code == 400


def test_convert_duplicate_contact_409(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, client_id, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}dup"
    )
    payload = _full_roster_payload(cand, client_row, job)
    existing = client_rbac.post(
        f"/api/clients/{client_id}/roster",
        cookies=login.cookies,
        json=payload,
    )
    assert existing.status_code == 200, existing.text
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert r.status_code == 409


def test_convert_success_writes_roster_and_application(client_rbac, admin_auth, rms_engine, uniq):
    from schemas.rms import utc_date_str

    login, app_id, client_id, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}ok"
    )
    before_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies).json()
    before_count = len(before_apps)
    roster_before = client_rbac.get(
        f"/api/clients/{client_id}/roster", cookies=login.cookies
    ).json()
    payload = _full_roster_payload(
        cand, client_row, job, contact_info=_unique_phone(f"{uniq}ok")
    )

    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["roster_entry"]["full_name"] == payload["full_name"]
    assert body["application"]["converted_to_roster_entry_id"] == body["roster_entry"]["id"]
    assert body["application"]["converted_to_roster_at"] == utc_date_str()
    assert body["application"]["converted_to_roster_by"] is not None

    roster_after = client_rbac.get(
        f"/api/clients/{client_id}/roster", cookies=login.cookies
    ).json()
    assert len(roster_after) == len(roster_before) + 1
    after_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies).json()
    assert len(after_apps) == before_count


def test_convert_already_converted_409(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, _cid, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}tw"
    )
    payload = _full_roster_payload(
        cand, client_row, job, contact_info=_unique_phone(f"{uniq}tw")
    )
    first = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert first.status_code == 200, first.text
    second = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert second.status_code == 409
    draft = client_rbac.get(
        f"/api/rms/applications/{app_id}/roster-draft",
        cookies=login.cookies,
    )
    assert draft.status_code == 409


def test_migration_011_columns(crm_main):
    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT migration_id FROM schema_migrations "
                "WHERE migration_id = '011_rms_application_roster_conversion.sql'"
            )
        ).fetchone()
        assert row is not None
        cols = {
            r[1]
            for r in conn.execute(text("PRAGMA table_info(rms_applications)")).fetchall()
        }
    for col in (
        "converted_to_roster_entry_id",
        "converted_to_roster_at",
        "converted_to_roster_by",
    ):
        assert col in cols
    RmsApplication = crm_main.RMS_MODELS["RmsApplication"]
    assert hasattr(RmsApplication, "converted_to_roster_entry_id")
