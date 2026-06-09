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


def _extract_rms_region(html: str, region: str) -> str:
    """Return inner HTML of first element with data-rms-region=region (best-effort)."""
    marker = f'data-rms-region="{region}"'
    start = html.find(marker)
    if start < 0:
        return ""
    tag_end = html.find(">", start)
    if tag_end < 0:
        return ""
    depth = 1
    pos = tag_end + 1
    while pos < len(html) and depth > 0:
        next_open = html.find("<section", pos)
        next_close = html.find("</section>", pos)
        if next_close < 0:
            break
        if 0 <= next_open < next_close:
            depth += 1
            pos = next_open + 8
        else:
            depth -= 1
            if depth == 0:
                return html[tag_end + 1 : next_close]
            pos = next_close + 10
    return html[start : start + 4000]


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
    assert "validateReportForm" in report_src
    assert "validateCandidateCreateForm" in report_src
    assert "fieldKeyForValidationMessage" in report_src
    assert "data-rms-report-field" in (REPO_ROOT / "templates/pages/rms_index.html").read_text(encoding="utf-8")
    assert "focusReportField" in rms_src
    assert "showValidationPrompt" in rms_src
    assert "到岗时间" in report_src
    assert '"phone"' in report_src
    assert 'phone: ""' in report_src
    assert "city: (form.location || \"\").trim()" in report_src
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
    for sym in (
        "isPipelineEligible",
        "isApplicationTerminal",
        "filterPipelineApplications",
        "progressOptionsForCorrection",
        "APPLICATION_PROGRESS_STATUSES",
    ):
        assert sym in labels_src, f"missing pipeline helper: {sym}"
    assert "progressOptions" in rms_src
    assert "filteredPipelineApplications" in rms_src
    assert "candidateFilter" in rms_src
    assert "filteredCandidates" in rms_src
    assert "crmEnsureRmsCandidatesTableColumns" in rms_src
    assert "prevLen === 0" in rms_src
    assert "resetCandidateFilter" in rms_src
    assert "suppressCandidateSearchWatch" in rms_src
    assert "candidateKeywordTimer" in rms_src
    assert "/api/rms/candidates?q=" in rms_src
    assert '"/api/rms/candidates/"' in rms_src or '"/api/rms/candidates/" + c.id' in rms_src
    assert "openCandidateDetail" in rms_src
    assert "closeCandidateDetail" in rms_src
    assert "latest_resume_parse_summary" in rms_src
    assert "encodeURIComponent(keyword)" in rms_src
    assert "await loadCandidates()" in rms_src
    filtered_candidates_start = rms_src.index("const filteredCandidates = computed")
    filtered_candidates_slice = rms_src[filtered_candidates_start : filtered_candidates_start + 800]
    assert "indexOf(name)" not in filtered_candidates_slice
    rms_html = (REPO_ROOT / "templates/pages/rms_index.html").read_text(encoding="utf-8")
    assert 'data-rms-region="candidates"' in rms_html
    assert 'data-rms-region="candidate-detail"' in rms_html
    assert "简历解析摘要" in rms_html
    assert "暂无简历解析结果" in rms_html
    assert "openCandidateDetail" in rms_html
    assert "candidateFilter.name" in rms_html
    assert "关键词" in rms_html
    assert "姓名/学校/专业/公司/简历关键词" in rms_html
    assert "暂无符合条件的候选人" in rms_html
    assert "openDeliveryReviewFailModal" in rms_html
    assert "reviewFailPromptOpen" in rms_html
    assert "reviewModalNote" not in rms_html
    assert "openDeliveryReviewFailModal" in rms_src
    assert "reviewFailPromptOpen" in rms_src
    assert "内审失败须填写理由" in rms_src
    assert "请说明内审未通过原因" in rms_src
    assert "userOptions.value" in rms_src
    assert "jobFormOptions.users" not in rms_src
    assert '"interview_scheduling"' not in labels_src
    assert "scheduling_interview" in labels_src
    assert "client_screen_duplicate" in labels_src
    assert '"重复"' in labels_src or "重复" in labels_src


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


def test_pipeline_label_helpers():
    labels = REPO_ROOT / "static/js/pages/rms-application-labels.js"
    script = f"""
const fs = require("fs");
eval(fs.readFileSync({str(labels)!r}, "utf8"));
const L = globalThis.RmsApplicationLabels;
const ok = {{ receive_status: "accepted", delivery_review_status: "passed", status: "pending_client_screen", job_id: 1, client_id: 10, recommended_at: "2026-06-01" }};
const fail = {{ receive_status: "pending", delivery_review_status: "failed", status: "internal_screen_failed" }};
if (!L.isPipelineEligible(ok)) {{ console.error("eligible failed"); process.exit(1); }}
if (L.isPipelineEligible(fail)) {{ console.error("ineligible passed"); process.exit(1); }}
if (L.deriveProtectionStatus("internal_screen_failed") !== "已终止") {{
  console.error("internal_screen_failed protection");
  process.exit(1);
}}
if (L.deriveProtectionStatus("pending_client_screen") !== "生效中") {{
  console.error("pending_client_screen protection");
  process.exit(1);
}}
if (!L.isApplicationTerminal("rejected")) {{ console.error("rejected not terminal"); process.exit(1); }}
if (!L.isApplicationTerminal("withdrawn")) {{ console.error("withdrawn not terminal"); process.exit(1); }}
if (L.isProgressTerminal("rejected")) {{ console.error("isProgressTerminal must not include rejected"); process.exit(1); }}
const h = L.createAppDisplayHelpers({{
  getJobs: () => [{{ id: 1, location: "上海", client_id: 10 }}],
  getCandidates: () => [{{ id: 2, name: "张三" }}],
  getUsers: () => [],
  clientNameById: () => "ACME",
}});
const rows = L.filterPipelineApplications([
  ok,
  fail,
  {{ receive_status: "accepted", delivery_review_status: "passed", status: "hired", job_id: 1, client_id: 10, recommended_at: "2026-06-02" }},
  {{ receive_status: "accepted", delivery_review_status: "passed", status: "rejected", job_id: 1, client_id: 10, recommended_at: "2026-06-03" }},
], {{
  filters: {{ activeOnly: true }},
  getJobs: () => [{{ id: 1, location: "上海", client_id: 10 }}],
  getCandidates: () => [],
  getUsers: () => [],
  clientNameById: () => "ACME",
}});
if (rows.length !== 1 || rows[0].status !== "pending_client_screen") {{
  console.error("activeOnly filter: got " + JSON.stringify(rows.map(r => r.status)));
  process.exit(1);
}}
const withTerminal = L.filterPipelineApplications([
  ok,
  {{ receive_status: "accepted", delivery_review_status: "passed", status: "hired", job_id: 1, client_id: 10, recommended_at: "2026-06-02" }},
], {{
  filters: {{ activeOnly: false }},
  getJobs: () => [{{ id: 1, location: "上海", client_id: 10 }}],
  getCandidates: () => [],
  getUsers: () => [],
  clientNameById: () => "ACME",
}});
const multiStatus = L.filterPipelineApplications([
  ok,
  {{ receive_status: "accepted", delivery_review_status: "passed", status: "first_interview_passed", job_id: 1, client_id: 10, recommended_at: "2026-06-04" }},
  {{ receive_status: "accepted", delivery_review_status: "passed", status: "hired", job_id: 1, client_id: 10, recommended_at: "2026-06-05" }},
], {{
  filters: {{ activeOnly: false, statuses: ["pending_client_screen", "first_interview_passed"] }},
  getJobs: () => [{{ id: 1, location: "上海", client_id: 10 }}],
  getCandidates: () => [],
  getUsers: () => [],
  clientNameById: () => "ACME",
}});
if (multiStatus.length !== 2) {{
  console.error("multi status: got " + JSON.stringify(multiStatus.map(r => r.status)));
  process.exit(1);
}}
const legacyScreen = L.filterPipelineApplications([
  {{ receive_status: "accepted", delivery_review_status: "passed", status: "screening", job_id: 1, client_id: 10, recommended_at: "2026-06-06" }},
], {{
  filters: {{ activeOnly: false, statuses: ["pending_client_screen"] }},
  getJobs: () => [{{ id: 1, location: "上海", client_id: 10 }}],
  getCandidates: () => [],
  getUsers: () => [],
  clientNameById: () => "ACME",
}});
if (legacyScreen.length !== 1) {{
  console.error("legacy screening alias: got " + legacyScreen.length);
  process.exit(1);
}}
if (withTerminal.length !== 2) {{
  console.error("include terminal: got " + withTerminal.length);
  process.exit(1);
}}
const opts = L.progressOptionsForCorrection("first_interview_passed");
if (opts.some(o => o.value === "rejected" || o.value === "withdrawn")) {{
  console.error("correction options must not include rejected/withdrawn");
  process.exit(1);
}}
if (!opts.some(o => o.value === "pending_client_screen")) {{
  console.error("correction options should allow backward target");
  process.exit(1);
}}
if (L.normalizeProgressStatus("screening") !== "pending_client_screen") {{
  console.error("legacy screening normalize failed");
  process.exit(1);
}}
var legacyOpts = L.progressOptionsForCorrection("screening");
if (legacyOpts.some(o => o.value === "pending_client_screen")) {{
  console.error("correction options should exclude normalized current status");
  process.exit(1);
}}
if (L.progressActionBtnClass("second_interview_failed") !== "rms-progress-btn rms-progress-btn--red") {{
  console.error("fail action should use red filled style");
  process.exit(1);
}}
if (L.progressActionBtnClass("second_interview_passed") !== "rms-progress-btn rms-progress-btn--blue") {{
  console.error("pass action should use blue filled style");
  process.exit(1);
}}
if (L.progressActionBtnClass("second_interview_abandoned") !== "rms-progress-btn rms-progress-btn--black") {{
  console.error("third-column abandon action should use black filled style");
  process.exit(1);
}}
if (L.progressActionBtnClass("final_interview_abandoned") !== "rms-progress-btn rms-progress-btn--black") {{
  console.error("final abandon third column should use black filled style");
  process.exit(1);
}}
const clientNext = L.progressTransitionsFor("pending_client_screen");
if (clientNext.indexOf("client_screen_duplicate") < 0) {{
  console.error("pending_client_screen should allow duplicate transition");
  process.exit(1);
}}
if (L.progressLabel("client_screen_duplicate") !== "重复") {{
  console.error("client_screen_duplicate label");
  process.exit(1);
}}
if (L.progressActionBtnClass("client_screen_duplicate") !== "rms-progress-btn rms-progress-btn--black") {{
  console.error("duplicate action should use black filled style");
  process.exit(1);
}}
if (clientNext[clientNext.length - 1] !== "client_screen_duplicate") {{
  console.error("duplicate transition should be last after scheduling_interview");
  process.exit(1);
}}
if (L.deriveProtectionStatus("client_screen_duplicate") !== "已终止") {{
  console.error("client_screen_duplicate protection");
  process.exit(1);
}}
if (!L.isApplicationTerminal("client_screen_duplicate")) {{
  console.error("client_screen_duplicate should be terminal");
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
    assert 'data-rms-tab="pipeline"' in html
    assert "招聘pipeline-候选人状态（交付）" in html
    assert ">岗位</" in html or ">岗位<" in html
    assert ">候选人</" in html or ">候选人<" in html
    assert ">推荐</" in html or ">推荐<" in html
    assert "活跃推荐数" in html
    assert "历史推荐数" in html
    assert "交付内审" in html
    dr_table_marker = (
        '<table class="crm-table rms-candidates-table" data-table-id="rms-delivery-review">'
    )
    dr_table_start = html.index(dr_table_marker)
    dr_slice = html[dr_table_start : dr_table_start + 4000]
    for col in (">年龄</th>", ">年限</th>", ">当前薪资</th>", ">期望薪资</th>", ">到岗时间</th>", ">学历</th>"):
        assert col in dr_slice, f"missing delivery review column {col}"
    assert ">简历</th>" not in dr_slice
    assert 'class="crm-op-btn-detail">简历</a>' in dr_slice
    assert "rms-delivery-review-op" in dr_slice
    assert "--rms-delivery-review-op-col-width" in html
    resize_js = (REPO_ROOT / "static/js/crm-table-resize.js").read_text(encoding="utf-8")
    assert "rms-delivery-review-op-col" in resize_js
    assert "RMS_DELIVERY_REVIEW_STORAGE_VERSION" in resize_js
    assert "ensureRmsCandidatesTableColumns" in resize_js
    assert "crmEnsureRmsCandidatesTableColumns" in resize_js
    assert "appCandidateAge" in (REPO_ROOT / "static/js/pages/rms.js").read_text(encoding="utf-8")
    assert "推荐候选人" in html

    assert "data-rms-error" in html
    assert "data-rms-empty" in html
    assert "rms-sticky-serial" in html
    assert "rms-sticky-title" in html
    assert "rms-col-manage" in html
    assert "rms-sticky-recommend" in html
    assert "rms-candidate-sticky-name" in html
    assert "rms-jobs-table" in html
    assert "rms-candidates-table" in html
    assert ">应聘岗位</th>" in html
    assert html.index(">邮箱/微信</th>") < html.index(">应聘岗位</th>")
    assert "rms-candidates-scroll" in html
    assert "rms-candidates-table-scroll" in html
    assert "rms-candidates-frame" in html
    assert ">阅读</a>" in html
    assert ">下载</a>" in html
    assert "resumeViewUrl" in html
    assert "resumeCanView" in html
    assert ">年限</th>" in html
    cand_region = _extract_rms_region(html, "candidates")
    assert cand_region, "candidates region not found"
    cand_table_start = html.index('data-table-id="rms-candidates"')
    cand_slice = html[cand_table_start : cand_table_start + 3000]
    assert cand_slice.index(">来源</th>") < cand_slice.index(">推荐时间</th>")
    assert cand_slice.index(">推荐时间</th>") < cand_slice.index(">简历</th>")
    assert ">详情</" in cand_region or "openCandidateDetail" in cand_region
    assert ">修改</button>" in cand_region
    assert "formatRmsDate(c.recommended_at)" in html
    assert "crm-sticky-right-op" in html
    assert "crm-right-drawer" in html
    assert "maritalOptions" in html or "未婚" in html
    assert "rms-jobs-scroll-fill" in html
    assert "crm-table" in html
    assert "/static/js/pages/rms-application-labels.js" in html
    assert "/static/js/pages/rms-candidate-report.js" in html
    assert "/static/js/pages/rms.js" in html
    assert "接收状态" in html
    assert "内审状态" in html
    assert "招聘进展" in html
    assert "保护期状态" in html
    assert "deliveryReviewLabel" in (REPO_ROOT / "static/js/pages/rms.js").read_text(encoding="utf-8")

    rms_js = (REPO_ROOT / "static/js/pages/rms.js").read_text(encoding="utf-8")
    assert "人选已存在系统中" in rms_js
    assert "系统中已存在该人选" in rms_js
    assert "duplicate_detected" in rms_js
    assert "/api/rms/candidates/check-duplicate" in rms_js
    assert "10000" in rms_js
    assert "showCandidateDuplicateDialog" in rms_js
    assert 'window.confirm("人选已存在系统中")' not in rms_js

    apps_region = _extract_rms_region(html, "applications")
    pipe_region = _extract_rms_region(html, "pipeline")
    assert apps_region, "applications region not found"
    assert pipe_region, "pipeline region not found"
    assert 'data-rms-action="progress-transition"' not in apps_region
    assert "transitionProgress" not in apps_region
    assert 'data-rms-action="progress-confirm-open"' in pipe_region
    assert 'data-rms-action="correction-picker-open"' in pipe_region
    assert "openCorrectionPickerModal" in pipe_region
    assert "修改状态/历史更改" in pipe_region
    assert ">修改</button>" in pipe_region
    assert ">历史</button>" in pipe_region
    assert "只看活动状态" in pipe_region
    rms_src = (REPO_ROOT / "static/js/pages/rms.js").read_text(encoding="utf-8")
    assert "openProgressConfirmModal" in rms_src
    assert "progressOptionsForCorrection" in rms_src
    assert 'data-rms-action="progress-transition"' not in pipe_region
    assert "transitionProgress" not in pipe_region
    assert "progressOptions" in pipe_region
    assert "pipelineStatusFilterSummary" in pipe_region
    assert "pipelineStatusDraft" in pipe_region
    assert "rms-pipeline-status-filter" in pipe_region
    assert "pipelineStatusFilterSummary" in rms_src
    assert "applyPipelineStatusFilter" in rms_src
    assert "pipelineStatusMatches" in rms_src
    labels_src = (REPO_ROOT / "static/js/pages/rms-application-labels.js").read_text(encoding="utf-8")
    assert "statusMatchesFilter" in labels_src
    assert ">确定</button>" in pipe_region
    base_html = (REPO_ROOT / "templates/base.html").read_text(encoding="utf-8")
    assert "crmConfirmActionDialog" in base_html
    assert "openApplicationDetailModal" in apps_region
    assert "内审失败原因" in html
    assert "applicationDetailFailNote" in html
    assert "deliveryReviewFailNoteFromHistory" in rms_src
    assert "openStatusHistoryModal" in apps_region
    assert "removeApplication" in apps_region
    assert "确认删除推荐记录" in apps_region

    assert "Plan 34" not in html
    assert "占位" not in html
    assert "正在建设" not in html
    assert "Phase 2：API MVP 已接入" not in html
    assert "Phase 0" not in html


def test_rms_dashboard_assets_and_nav():
    dash_js = REPO_ROOT / "static/js/pages/rms-dashboard.js"
    dash_html = REPO_ROOT / "templates/pages/rms_dashboard.html"
    nav = REPO_ROOT / "templates/partials/nav.html"
    assert dash_js.is_file()
    assert dash_html.is_file()
    assert "/rms/dashboard" in nav.read_text(encoding="utf-8")
    assert "rms.analytics.read" in nav.read_text(encoding="utf-8")


def test_rms_dashboard_twenty_shell():
    html = (REPO_ROOT / "templates/pages/rms_dashboard.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "static/js/pages/rms-dashboard.js").read_text(encoding="utf-8")

    for required in (
        "dash-root",
        "dash-top-bar",
        "dash-tw-tabs",
        "dash-page-tabs-row",
        "dash-canvas",
        "dash-grid",
        "dash-card",
        "num-value",
        "chart-canvas-wrap",
        "chartjs-plugin-datalabels",
        "需求总数",
        "有需求客户数",
        "HC 总数",
        "总览",
        "历史转化",
        "招聘人效",
        "花名册核对",
        "/static/js/pages/rms-dashboard.js",
        "rms-dashboard-twenty-12",
        "dashboard-widget-kit.js",
        "inspector-section",
        "inspector-row",
        "X 轴",
        "Y 轴",
        "Style",
        "轴名称",
        "堆叠条形图",
        "数据标签",
        "Legend",
        "来源",
        "过滤",
        "调整选项顺序",
        "附加展示",
        "新建看板",
        "编辑",
        "+ 组件",
        "card-actions",
        "icon-btn",
        "table_client_job_stage",
        ".rms-job-stage-table",
        "offer在谈",
        "弃offer",
        "在途数",
        "在途流失",
        "入职数",
        "metric-with-rate",
        "card-resize-handle",
        "chart_client_job_stage_grouped",
        "chart_client_job_stage_stacked",
        "chart_client_job_stage_funnel",
    ):
        assert required in html, f"missing {required!r} in rms_dashboard.html"

    for forbidden in (
        "rms-dash-card",
        "rms-dash-kpi",
        "container mx-auto",
        "crm-table",
        "crm-th",
        "open 岗位",
        "布局（栅格 12 列）",
    ):
        assert forbidden not in html, f"forbidden {forbidden!r} in rms_dashboard.html"

    for js_required in (
        "chartInstances",
        "destroyAllCharts",
        "loadDashboard",
        "showMountError",
        "displayItems",
        "openWidgetPanel",
        "DashboardWidgetKit",
        "reloadActiveTabData",
        "gridColumn",
        "panelView",
        "activePicker",
        "manual_order",
        "openManualOrder",
        "manualOrderRowStyle",
        "manualDragGhostStyle",
        "manualDragIndex",
        "primary_axis_order",
        "grouped_series",
        "normalizeWidgetConfig",
        "job_ids",
        "clientJobStageRows",
        "jobStageMetricText",
        "jobStageMetricTitle",
        "rms_block",
        "onCardResizePointerDown",
        "resizeWidgetId",
        "onRmsBlockChange",
        "selectRmsBlock",
        "flushPersistWidget",
        "renderClientJobStageGroupedChart",
        "renderClientJobStageStackedChart",
        "renderClientJobStageFunnelChart",
        "bringWidgetToFront",
        "activeWidgetId",
    ):
        assert js_required in js, f"missing {js_required!r} in rms-dashboard.js"

    for js_forbidden in (
        "entered - passed - failed",
        "entered-passed-failed",
        "rmsBarDatasetOptions",
    ):
        assert js_forbidden not in js, f"forbidden {js_forbidden!r} in rms-dashboard.js"

    subprocess.run(
        ["node", "--check", str(REPO_ROOT / "static/js/pages/rms-dashboard.js")],
        check=True,
        cwd=REPO_ROOT,
    )
    subprocess.run(
        ["node", "--check", str(REPO_ROOT / "static/js/shared/dashboard-widget-kit.js")],
        check=True,
        cwd=REPO_ROOT,
    )
