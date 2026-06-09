"""RMS Phase 3C: candidate detail API + resume parse summary."""
from __future__ import annotations

import importlib
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY
from tests.test_rms_application_workflow import (
    _assert_contact_and_education_draft,
    _resume_with_contact_and_education,
)
from tests.test_rms_phase2_mvp import (
    _enable_delivery_rms_mvp,
    _enable_sales_rms_jobs_write,
    _grant_role_permissions,
    _revoke_role_permissions,
    _trial_job_and_candidate,
)

RAW_PHONE = "15988192434"
RAW_EMAIL = "15988192434@163.com"


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


@pytest.fixture
def uniq():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def rms_engine(client_rbac):
    import main as crm_main

    _enable_sales_rms_jobs_write(crm_main.engine)
    _enable_delivery_rms_mvp(crm_main.engine)
    return crm_main.engine


def test_get_candidate_returns_latest_resume_parse_summary(
    client_rbac, admin_auth, rms_engine, uniq
):
    _grant_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
    try:
        login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
            client_rbac, rms_engine, admin_auth, f"detail_summary_{uniq}"
        )
        txt = _resume_with_contact_and_education()
        upload = client_rbac.post(
            f"/api/rms/candidates/{cand_id}/resume",
            cookies=login.cookies,
            files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
        )
        assert upload.status_code == 200, upload.text

        r = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
        assert r.status_code == 200, r.text
        body = r.json()
        summary = body.get("latest_resume_parse_summary")
        assert isinstance(summary, dict)
        assert summary
        _assert_contact_and_education_draft(summary)
    finally:
        _revoke_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))


def test_get_candidate_no_resume_empty_summary(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"detail_no_resume_{uniq}"
    )
    r = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert r.json().get("latest_resume_parse_summary") == {}


def test_get_candidate_corrupt_parsed_json_no_500(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"detail_bad_json_{uniq}"
    )
    txt = _resume_with_contact_and_education()
    upload = client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    assert upload.status_code == 200, upload.text
    resume_id = upload.json()["id"]
    with rms_engine.begin() as conn:
        conn.execute(
            text("UPDATE rms_resumes SET parsed_json = :bad WHERE id = :id"),
            {"bad": "{not json", "id": resume_id},
        )

    r = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    assert r.json().get("latest_resume_parse_summary") == {}


def test_get_candidate_omits_parsed_text(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"detail_no_parsed_text_{uniq}"
    )
    txt = _resume_with_contact_and_education()
    client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    r = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "parsed_text" not in body
    assert "parsed_json" not in body


def test_list_candidates_omits_parse_summary(
    client_rbac, admin_auth, rms_engine, uniq
):
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"list_no_summary_{uniq}"
    )
    txt = _resume_with_contact_and_education()
    client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    listed = client_rbac.get("/api/rms/candidates", cookies=login.cookies)
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json() if item["id"] == cand_id)
    assert "latest_resume_parse_summary" not in row


def test_get_candidate_summary_contacts_masked(
    client_rbac, admin_auth, rms_engine, uniq
):
    _revoke_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
    login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
        client_rbac, rms_engine, admin_auth, f"detail_mask_{uniq}"
    )
    txt = _resume_with_contact_and_education()
    client_rbac.post(
        f"/api/rms/candidates/{cand_id}/resume",
        cookies=login.cookies,
        files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
    )
    r = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
    assert r.status_code == 200, r.text
    body = r.json()
    summary = body.get("latest_resume_parse_summary") or {}
    assert "****" in (summary.get("phone") or "")
    assert "***" in (summary.get("email_wechat") or "")
    raw = str(summary)
    assert RAW_PHONE not in raw
    assert RAW_EMAIL not in raw


def test_get_candidate_summary_contacts_visible(
    client_rbac, admin_auth, rms_engine, uniq
):
    _grant_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
    try:
        login, _job_id, cand_id, _client_id = _trial_job_and_candidate(
            client_rbac, rms_engine, admin_auth, f"detail_visible_{uniq}"
        )
        txt = _resume_with_contact_and_education()
        client_rbac.post(
            f"/api/rms/candidates/{cand_id}/resume",
            cookies=login.cookies,
            files={"file": ("resume.txt", txt.encode("utf-8"), "text/plain")},
        )
        r = client_rbac.get(f"/api/rms/candidates/{cand_id}", cookies=login.cookies)
        assert r.status_code == 200, r.text
        summary = r.json().get("latest_resume_parse_summary") or {}
        assert summary.get("phone") == RAW_PHONE
        assert summary.get("email_wechat") == RAW_EMAIL
    finally:
        _revoke_role_permissions(rms_engine, ROLE_DELIVERY, ("rms.contacts.view",))
