"""RMS Plan 34: frontend shell HTML markers and JS asset checks."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from auth.permissions import ROLE_DELIVERY
from tests.test_rms_phase0_permissions import _create_user, _login

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client_rbac(_test_env, monkeypatch):
    monkeypatch.setenv("CRM_AUTH_MODE", "rbac")
    import main as crm_main

    importlib.reload(crm_main)
    with TestClient(crm_main.app) as c:
        yield c


def test_rms_frontend_js_assets_exist():
    labels = REPO_ROOT / "static/js/pages/rms-application-labels.js"
    report = REPO_ROOT / "static/js/pages/rms-candidate-report.js"
    rms = REPO_ROOT / "static/js/pages/rms.js"
    assert labels.is_file(), "missing rms-application-labels.js"
    assert report.is_file(), "missing rms-candidate-report.js"
    assert rms.is_file(), "missing rms.js"

    labels_src = labels.read_text(encoding="utf-8")
    report_src = report.read_text(encoding="utf-8")
    rms_src = rms.read_text(encoding="utf-8")

    assert "parseCandidateReportDraft" in report_src
    for sym in (
        "reportForm",
        "reportResumeFile",
        "submitCandidateReport",
        "onReportResumeChange",
    ):
        assert sym in rms_src or sym in report_src, f"missing symbol: {sym}"


def test_rms_page_shell_markers(client_rbac, admin_auth):
    suffix = os.getpid()
    delivery_user = f"rms_fe_delivery_{suffix}"
    _create_user(client_rbac, admin_auth, delivery_user, [ROLE_DELIVERY])
    login = _login(client_rbac, delivery_user, "pass1234")
    assert login.status_code == 200

    page = client_rbac.get("/rms", cookies=login.cookies)
    assert page.status_code == 200
    html = page.text

    assert 'id="rms-app"' in html
    assert "招聘（RMS）" in html

    assert 'data-rms-tab="jobs"' in html
    assert 'data-rms-tab="candidates"' in html
    assert 'data-rms-tab="applications"' in html
    assert 'data-rms-tab="deliveryReview"' in html
    assert ">岗位</" in html or ">岗位<" in html
    assert ">候选人</" in html or ">候选人<" in html
    assert ">推荐</" in html or ">推荐<" in html
    assert "交付内审" in html
    assert "推荐候选人" in html

    assert "data-rms-error" in html
    assert "data-rms-empty" in html
    assert "rms-sticky-serial" in html
    assert "rms-candidate-sticky-name" in html
    assert "rms-jobs-table" in html
    assert "rms-candidates-table" in html
    assert ">应聘岗位</th>" in html
    assert html.index(">邮箱/微信</th>") < html.index(">应聘岗位</th>")
    assert "rms-candidates-scroll" in html
    assert "rms-candidates-frame" in html
    assert ">阅读</a>" in html
    assert ">下载</a>" in html
    assert "resumeViewUrl" in html
    assert "resumeCanView" in html
    assert ">年限</th>" in html
    assert "crm-sticky-right-op" in html
    assert "maritalOptions" in html or "未婚" in html
    assert "rms-jobs-scroll-fill" in html
    assert "crm-table" in html
    assert "/static/js/pages/rms-application-labels.js" in html
    assert "/static/js/pages/rms-candidate-report.js" in html
    assert "/static/js/pages/rms.js" in html
    assert "接收状态" in html
    assert "招聘进展" in html
    assert "保护期状态" in html

    assert "Plan 34" in html
    assert "占位" not in html
    assert "正在建设" not in html
    assert "Phase 2：API MVP 已接入" not in html
    assert "Phase 0" not in html
