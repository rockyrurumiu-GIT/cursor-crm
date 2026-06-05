"""RMS Plan 34: frontend shell HTML markers and JS asset checks."""
from __future__ import annotations

import importlib
import os
import subprocess
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
    assert '"phone"' in report_src
    assert 'phone: ""' in report_src
    assert "form.email_wechat = String(draft.phone)" not in report_src
    for sym in (
        "reportForm",
        "reportResumeFile",
        "submitCandidateReport",
        "onReportResumeChange",
    ):
        assert sym in rms_src or sym in report_src, f"missing symbol: {sym}"

    assert "createAppDisplayHelpers" in labels_src
    assert "Labels.createAppDisplayHelpers" in rms_src
    for helper in (
        "appCandidateName",
        "appClientName",
        "appJobTitle",
        "appJobLocation",
        "appRecommenderLabel",
        "appDeliveryLabel",
    ):
        assert helper in labels_src, f"missing helper: {helper}"
    for fn in ("candidateById", "jobById", "userLabelById"):
        assert fn in labels_src, f"missing lookup fn in createAppDisplayHelpers: {fn}"


def test_create_app_display_helpers_behavior():
    labels = REPO_ROOT / "static/js/pages/rms-application-labels.js"
    script = f"""
const fs = require("fs");
eval(fs.readFileSync({str(labels)!r}, "utf8"));
const L = globalThis.RmsApplicationLabels;
const h = L.createAppDisplayHelpers({{
  getJobs: () => [{{
    id: 1,
    title: "后端工程师",
    location: "上海",
    client_id: 10,
    client_name: "ACME",
    delivery_owner_label: "王五 · wangwu",
  }}],
  getCandidates: () => [{{ id: 2, name: "张三" }}],
  getUsers: () => [
    {{ id: 3, display_name: "李四", username: "lisi" }},
    {{ id: 5, display_name: "赵六", username: "zhaoliu" }},
  ],
  clientNameById: (id) => (Number(id) === 10 ? "ACME" : ""),
  labelJob: (id) => "#" + id,
}});
const app = {{
  candidate_id: 2,
  job_id: 1,
  client_id: 10,
  recommended_by: 3,
}};
const checks = [
  ["appCandidateName", "张三"],
  ["appClientName", "ACME"],
  ["appJobTitle", "后端工程师"],
  ["appJobLocation", "上海"],
  ["appRecommenderLabel", "李四 · lisi"],
  ["appDeliveryLabel", "王五 · wangwu"],
];
for (const [name, want] of checks) {{
  const got = h[name](app);
  if (got !== want) {{
    console.error(name + ": got " + JSON.stringify(got) + " want " + JSON.stringify(want));
    process.exit(1);
  }}
}}
for (const [input, want] of [
  ["", "未接收"],
  [undefined, "未接收"],
  ["pending", "未接收"],
  [" ", "未接收"],
]) {{
  const got = L.receiveLabel(input);
  if (got !== want) {{
    console.error("receiveLabel(" + JSON.stringify(input) + "): got " + JSON.stringify(got) + " want " + JSON.stringify(want));
    process.exit(1);
  }}
}}
const missing = h.appCandidateName({{ candidate_id: 99, job_id: 1 }});
if (missing !== "#99") {{
  console.error("missing candidate: got " + JSON.stringify(missing));
  process.exit(1);
}}
const missingJob = h.appJobTitle({{ candidate_id: 2, job_id: 88 }});
if (missingJob !== "#88") {{
  console.error("missing job: got " + JSON.stringify(missingJob));
  process.exit(1);
}}
const hJobUserId = L.createAppDisplayHelpers({{
  getJobs: () => [{{ id: 2, delivery_owner_user_id: 5 }}],
  getUsers: () => [{{ id: 5, display_name: "赵六", username: "zhaoliu" }}],
}});
const fromJobUserId = hJobUserId.appDeliveryLabel({{ job_id: 2 }});
if (fromJobUserId !== "赵六 · zhaoliu") {{
  console.error("job delivery_owner_user_id: got " + JSON.stringify(fromJobUserId));
  process.exit(1);
}}
const fromAppUserId = h.appDeliveryLabel({{ delivery_owner_user_id: 3 }});
if (fromAppUserId !== "李四 · lisi") {{
  console.error("app delivery_owner_user_id: got " + JSON.stringify(fromAppUserId));
  process.exit(1);
}}
const noDelivery = h.appDeliveryLabel({{ candidate_id: 2, job_id: 99 }});
if (noDelivery !== "—") {{
  console.error("no delivery owner: got " + JSON.stringify(noDelivery));
  process.exit(1);
}}
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


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
