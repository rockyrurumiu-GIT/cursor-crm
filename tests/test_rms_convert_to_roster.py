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


def _seed_approved_offer(
    rms_engine,
    *,
    app_id: int,
    client_id: int,
    candidate_id: int,
    job_id: int,
    **overrides,
) -> None:
    vals = {
        "monthly_quote_tax": "10000",
        "pre_tax_salary": "8000",
        "gm_amount": "2000",
        "gm_pct": "20",
        "quote_tax_unit": "人月",
        "planned_onboard_date": "2026-06-15",
    }
    vals.update(overrides)
    with rms_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO rms_offer_records (
                    application_id, candidate_id, job_id, client_id, status,
                    current_approval_node, gm_pct, gm_amount, monthly_quote_tax,
                    quote_tax_unit, pre_tax_salary, probation_days, probation_discount_months,
                    planned_onboard_date, reason, form_json, created_at, updated_at
                ) VALUES (
                    :app_id, :candidate_id, :job_id, :client_id, 'approved',
                    '', :gm_pct, :gm_amount, :monthly_quote_tax,
                    :quote_tax_unit, :pre_tax_salary, '0', '0',
                    :planned_onboard_date, '', '{}', :now, :now
                )
                """
            ),
            {
                "app_id": app_id,
                "candidate_id": candidate_id,
                "job_id": job_id,
                "client_id": client_id,
                "now": "2026-06-18",
                **vals,
            },
        )


def _onboarding_application(client, rms_engine, admin_auth, uniq: str):
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
    _advance_to_onboarding(client, login, app_id, engine=rms_engine)
    _seed_approved_offer(
        rms_engine,
        app_id=app_id,
        client_id=client_id,
        candidate_id=cand_id,
        job_id=job_id,
    )
    cand = client.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies).json()
    client_row = client.get(f"/api/clients/{client_id}", cookies=login.cookies).json()
    job = client.get(f"/api/rms/jobs/{job_id}", cookies=login.cookies).json()
    return login, app_id, client_id, cand, client_row, job


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
    _advance_to_onboarding(client, login, app_id, engine=rms_engine)
    hired = client.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "hired", "hired_at": "2026-06-15"},
    )
    assert hired.status_code == 200, hired.text
    _seed_approved_offer(
        rms_engine,
        app_id=app_id,
        client_id=client_id,
        candidate_id=cand_id,
        job_id=job_id,
    )
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
        "regularization_status": "未转正",
        "quote_unit": "monthly",
        "quote_amount_tax": "10000",
        "monthly_billable_days": "20.67",
        "daily_billable_hours": "8",
        "pre_tax_salary": "8000",
        "gms": "2000",
        "gm_pct": "20%",
        "zntx_onboarding_channel": cand.get("source") or "Boss",
        "remarks": "测试转入",
    }
    base.update(overrides)
    return base


def test_onboarding_roster_draft_prefill(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, client_id, cand, client_row, job = _onboarding_application(
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
    payload = body["roster_payload"]
    assert payload["full_name"] == cand["name"]
    assert payload["entry_date"] == "2026-06-15"


def test_onboarding_convert_sets_hired_and_roster(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, client_id, cand, client_row, job = _onboarding_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}onb"
    )
    payload = _full_roster_payload(
        cand, client_row, job, contact_info=_unique_phone(f"{uniq}onb")
    )
    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    app = body["application"]
    assert app["status"] == "hired"
    assert app["current_stage"] == "hired"
    assert app["hired_at"][:10] == payload["entry_date"]
    assert app["converted_to_roster_entry_id"] == body["roster_entry"]["id"]

    with rms_engine.connect() as conn:
        hist = conn.execute(
            text(
                """
                SELECT from_status, to_status, reason
                FROM rms_application_status_history
                WHERE application_id = :id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"id": app_id},
        ).fetchone()
    assert hist is not None
    assert hist[0] == "onboarding"
    assert hist[1] == "hired"
    assert hist[2] == "transition"


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
    assert payload["regularization_status"] == "未转正"
    assert payload["zntx_onboarding_channel"] == (cand.get("source") or "")
    assert payload["monthly_quote_tax"] == "10000"
    assert payload["pre_tax_salary"] == "8000"
    assert payload["gms"] == "2000"
    assert payload["gm_pct"] == "20%"
    assert body["offer_financial_locked"] is True
    assert body["quote_tax_display"] == "10,000 (人月)"
    assert f"#{app_id}" in payload["remarks"]


def test_hired_roster_draft_converts_day_quote_to_monthly(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, client_id, cand, _client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}day"
    )
    with rms_engine.begin() as conn:
        conn.execute(text("DELETE FROM rms_offer_records WHERE application_id = :id"), {"id": app_id})
    _seed_approved_offer(
        rms_engine,
        app_id=app_id,
        client_id=client_id,
        candidate_id=cand["id"],
        job_id=job["id"],
        monthly_quote_tax="1000",
        quote_tax_unit="人天",
    )
    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/roster-draft",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    payload = r.json()["roster_payload"]
    assert payload["monthly_quote_tax"] == "20670"
    assert payload["quote_amount_tax"] == "1000"
    assert payload["quote_unit"] == "daily"
    assert r.json()["quote_tax_display"] == "1,000 (人天)"


def test_hired_roster_draft_converts_hour_quote_to_monthly(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, client_id, cand, _client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}hour"
    )
    with rms_engine.begin() as conn:
        conn.execute(text("DELETE FROM rms_offer_records WHERE application_id = :id"), {"id": app_id})
    _seed_approved_offer(
        rms_engine,
        app_id=app_id,
        client_id=client_id,
        candidate_id=cand["id"],
        job_id=job["id"],
        monthly_quote_tax="100",
        quote_tax_unit="人时",
    )
    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/roster-draft",
        cookies=login.cookies,
    )
    assert r.status_code == 200, r.text
    payload = r.json()["roster_payload"]
    assert payload["monthly_quote_tax"] == "16536"
    assert payload["quote_amount_tax"] == "100"
    assert payload["quote_unit"] == "hourly"
    assert r.json()["quote_tax_display"] == "100 (人时)"


def test_hired_roster_draft_without_offer_returns_400(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, _client_id, _cand, _client_row, _job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}no_offer"
    )
    with rms_engine.begin() as conn:
        conn.execute(text("DELETE FROM rms_offer_records WHERE application_id = :id"), {"id": app_id})
    r = client_rbac.get(
        f"/api/rms/applications/{app_id}/roster-draft",
        cookies=login.cookies,
    )
    assert r.status_code == 400
    assert "Offer" in r.json()["detail"]


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
    before = utc_date_str()

    r = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["roster_entry"]["full_name"] == payload["full_name"]
    assert body["roster_entry"]["monthly_quote_tax"] == "10000"
    assert body["roster_entry"]["salary_quote_ratio"] == "1.25"
    assert body["roster_entry"]["quote_coefficient"] == "1.25"
    assert body["roster_entry"]["pre_tax_salary"] == "8000"
    assert body["roster_entry"]["gms"] == "2000"
    assert body["roster_entry"]["gm_pct"] == "20%"
    assert body["application"]["converted_to_roster_entry_id"] == body["roster_entry"]["id"]
    assert body["application"]["converted_to_roster_at"][:10] >= before[:10]
    assert body["application"]["converted_to_roster_by"] is not None

    roster_after = client_rbac.get(
        f"/api/clients/{client_id}/roster", cookies=login.cookies
    ).json()
    assert len(roster_after) == len(roster_before) + 1
    after_apps = client_rbac.get("/api/rms/applications", cookies=login.cookies).json()
    assert len(after_apps) == before_count
    app = next(a for a in after_apps if a["id"] == app_id)
    assert app["converted_to_roster_entry_id"] == body["roster_entry"]["id"]
    assert app["converted_to_roster_at"]
    assert app["converted_to_roster_at"][:10] >= before[:10]
    assert app["converted_to_roster_by"] is not None


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


def test_converted_application_status_change_rejected(client_rbac, admin_auth, rms_engine, uniq):
    login, app_id, _client_id, cand, client_row, job = _hired_application(
        client_rbac, rms_engine, admin_auth, f"{uniq}lock"
    )
    payload = _full_roster_payload(
        cand, client_row, job, contact_info=_unique_phone(f"{uniq}lock")
    )
    converted = client_rbac.post(
        f"/api/rms/applications/{app_id}/convert-to-roster",
        cookies=login.cookies,
        json=payload,
    )
    assert converted.status_code == 200, converted.text

    correction = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "onboarding", "mode": "correction", "note": "试图回退"},
    )
    assert correction.status_code == 400
    assert "花名册" in correction.json()["detail"]

    transition = client_rbac.post(
        f"/api/rms/applications/{app_id}/status",
        cookies=login.cookies,
        json={"to_status": "onboarding", "mode": "transition"},
    )
    assert transition.status_code == 400
    assert "花名册" in transition.json()["detail"]


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
