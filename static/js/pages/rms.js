/**
 * RMS module page (Phase 2.5 frontend MVP).
 * Requires: Vue 3 CDN, crm-api.js, rms-core.js, rms-jobs.js, rms-candidates.js, rms-applications.js, rms-pipeline.js (optional crm-toast.js).
 */
(function () {
  "use strict";

  const Labels = window.RmsApplicationLabels || {};
  const CandidateReport = window.RmsCandidateReport || {};
  const Core = window.CrmRmsCore || {};

  const rmsRequest = Core.rmsRequest ? Core.rmsRequest.bind(Core) : async function () {
    return { ok: false, status: 0, message: "CrmRmsCore 未加载" };
  };
  const authHeaders = Core.authHeaders ? Core.authHeaders.bind(Core) : function () { return {}; };
  const messageForStatus = Core.messageForStatus ? Core.messageForStatus.bind(Core) : function (s) { return String(s); };
  const workflowMessageForStatus = Core.workflowMessageForStatus ? Core.workflowMessageForStatus.bind(Core) : messageForStatus;
  const formatSalaryThousands = Core.formatSalaryThousands ? Core.formatSalaryThousands.bind(Core) : function (s) { return String(s || ""); };
  const stripSalaryCommas = Core.stripSalaryCommas ? Core.stripSalaryCommas.bind(Core) : function (s) { return String(s || ""); };
  const fuzzyMatch = Core.fuzzyMatch ? Core.fuzzyMatch.bind(Core) : function () { return true; };
  const showValidationPrompt = Core.showValidationPrompt ? Core.showValidationPrompt.bind(Core) : function (m) { return String(m || ""); };
  const showRmsBootError = Core.showRmsBootError ? Core.showRmsBootError.bind(Core) : function () {};

  const EDUCATION_OPTIONS = ["重本", "统本", "专科", "硕士", "留学生", "民教网", "其他"];
  const GENDER_OPTIONS = ["男", "女"];
  const SOURCE_OPTIONS = ["平台", "Boss", "linkedin", "猎聘", "内推", "挂靠", "外协", "其他"];
  const MARITAL_OPTIONS = ["未婚", "已婚"];
  const PHONE_RE = /^1\d{10}$/;

  const CANDIDATE_DUPLICATE_DETAIL = "人选已存在系统中";
  const CANDIDATE_DUPLICATE_PARSE_HINT = "系统中已存在该人选";

  function isCandidateDuplicateError(r) {
    return !!(r && r.status === 409 && String(r.detail || "") === CANDIDATE_DUPLICATE_DETAIL);
  }

  function userFacingRmsError(r) {
    if (!r) return "操作失败";
    const detail = String(r.detail || "").trim();
    if (
      detail &&
      (detail.indexOf("请填写") === 0 ||
        detail.indexOf("请选择") === 0 ||
        detail.indexOf("请") === 0 ||
        detail.indexOf("手机号") >= 0 ||
        detail === CANDIDATE_DUPLICATE_DETAIL)
    ) {
      return detail;
    }
    return r.message || "操作失败";
  }

  function showCandidateDuplicateDialog(message) {
    var text = String(message || "").trim() || CANDIDATE_DUPLICATE_DETAIL;
    return new Promise(function (resolve) {
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        document.removeEventListener("keydown", onKeyDown, true);
        if (overlay && overlay.parentNode) {
          overlay.parentNode.removeChild(overlay);
        }
        resolve();
      }
      function onKeyDown(e) {
        if (e.key !== "Escape") return;
        e.preventDefault();
        e.stopPropagation();
        finish();
      }
      var overlay = document.createElement("div");
      overlay.className = "crm-esc-modal fixed inset-0 bg-black/40 flex items-center justify-center p-4";
      overlay.style.zIndex = "10000";
      var panel = document.createElement("div");
      panel.className = "bg-white rounded-lg shadow-xl w-full max-w-md p-4 sm:p-5";
      var h3 = document.createElement("h3");
      h3.className = "font-semibold text-lg text-gray-800 mb-3";
      h3.textContent = text;
      var pTarget = document.createElement("p");
      pTarget.className = "text-sm text-gray-600 mb-4";
      pTarget.textContent = text;
      var actions = document.createElement("div");
      actions.className = "flex gap-2";
      var confirmBtn = document.createElement("button");
      confirmBtn.type = "button";
      confirmBtn.className =
        "flex-1 py-2 rounded-md bg-[#0969da] text-white text-sm font-medium hover:bg-[#0550ae]";
      confirmBtn.textContent = "确定";
      actions.appendChild(confirmBtn);
      panel.appendChild(h3);
      panel.appendChild(pTarget);
      panel.appendChild(actions);
      overlay.appendChild(panel);
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) finish();
      });
      confirmBtn.addEventListener("click", finish);
      document.addEventListener("keydown", onKeyDown, true);
      document.body.appendChild(overlay);
    });
  }

  if (typeof Vue === "undefined" || !Vue.createApp) {
    showRmsBootError("页面依赖 Vue 未能加载，请刷新后重试。");
    return;
  }

  const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;

  try {
  createApp({
    setup() {
      const activeTab = ref("jobs");
      const viewMode = ref(null);
      const me = ref({ user: { id: null }, permissions: [] });

      const deliveryReviewState = reactive({ loading: false, items: [], error: "" });
      const reviewModal = ref(null);
      const reviewFailPromptOpen = ref(false);
      const reviewModalSaving = ref(false);
      const reviewModalError = ref("");
      async function rmsRequestWorkflow(method, url, body, endpoint) {
        const r = await rmsRequest(method, url, body);
        if (!r.ok && r.status === 404) {
          return { ok: false, status: 404, message: workflowMessageForStatus(404, "", endpoint) };
        }
        return r;
      }
      const deliveryReviewApi = CandidateReport.createDeliveryReviewApi
        ? CandidateReport.createDeliveryReviewApi(function (method, url, body) {
            return rmsRequestWorkflow(method, url, body, "delivery-review");
          })
        : null;

      const modal = ref(null);
      const modalError = ref("");
      const modalSaving = ref(false);

      const jobs = window.CrmRmsJobs && window.CrmRmsJobs.createJobsState
        ? window.CrmRmsJobs.createJobsState({
            ref: ref,
            reactive: reactive,
            computed: computed,
            nextTick: nextTick,
            modal: modal,
            modalError: modalError,
            modalSaving: modalSaving,
            me: me,
            toast: toast,
          })
        : {};

      const canWriteJobs = computed(function () {
        return me.value.permissions.indexOf("rms.jobs.write") !== -1;
      });
      const canWriteCandidates = computed(function () {
        return me.value.permissions.indexOf("rms.candidates.write") !== -1;
      });
      const canWriteApplications = computed(function () {
        return me.value.permissions.indexOf("rms.applications.write") !== -1;
      });
      const canReadCandidates = computed(function () {
        return me.value.permissions.indexOf("rms.candidates.read") !== -1;
      });
      const canConvertToRoster = computed(function () {
        const perms = me.value.permissions || [];
        return perms.indexOf("rms.applications.write") !== -1 &&
          perms.indexOf("delivery.roster.write") !== -1;
      });

      const rosterConvertModal = ref(null);
      const rosterConvertSaving = ref(false);
      const rosterConvertError = ref("");
      const rosterConvertForm = reactive({
        employment_status: "在职",
        full_name: "",
        contact_info: "",
        customer_name: "",
        work_location: "",
        position_title: "",
        business_line: "",
        entry_date: "",
        monthly_quote_tax: "",
        pre_tax_salary: "",
        gms: "",
        gm_pct: "",
        salary_quote_ratio: "",
        zntx_onboarding_channel: "RMS",
        remarks: "",
      });

      function emptyRosterConvertForm() {
        rosterConvertForm.employment_status = "在职";
        rosterConvertForm.full_name = "";
        rosterConvertForm.contact_info = "";
        rosterConvertForm.customer_name = "";
        rosterConvertForm.work_location = "";
        rosterConvertForm.position_title = "";
        rosterConvertForm.business_line = "";
        rosterConvertForm.entry_date = "";
        rosterConvertForm.monthly_quote_tax = "";
        rosterConvertForm.pre_tax_salary = "";
        rosterConvertForm.gms = "";
        rosterConvertForm.gm_pct = "";
        rosterConvertForm.salary_quote_ratio = "";
        rosterConvertForm.zntx_onboarding_channel = "RMS";
        rosterConvertForm.remarks = "";
      }

      function normalizeRosterAmountText(val) {
        return String(val || "").replace(/[,¥￥\s\u00a0]/g, "").trim();
      }

      function formatGmPctSymbol(val) {
        var s = String(val || "").trim().replace(/\uff05/g, "%");
        if (!s) return "";
        if (s.indexOf("%") === s.length - 1) return s;
        return s + "%";
      }

      function validateRosterConvertClientForm() {
        var required = [
          ["employment_status", "在职情况"],
          ["full_name", "姓名"],
          ["contact_info", "联系方式"],
          ["customer_name", "客户"],
          ["work_location", "工作地"],
          ["position_title", "岗位"],
          ["business_line", "业务线"],
          ["entry_date", "入职时间"],
          ["monthly_quote_tax", "月报价(含税)"],
          ["pre_tax_salary", "税前工资"],
          ["gms", "GM$"],
          ["gm_pct", "GM%"],
        ];
        var missing = [];
        required.forEach(function (pair) {
          if (!String(rosterConvertForm[pair[0]] || "").trim()) missing.push(pair[1]);
        });
        if (missing.length) return "请先完整填写必填项：" + missing.join("、");
        var phone = String(rosterConvertForm.contact_info || "").trim();
        if (!/^\d{11}$/.test(phone)) return "联系方式必须为11位数字";
        return "";
      }

      function appendGmCalcQueryPart(parts, key, val) {
        var s = String(val == null ? "" : val).trim();
        if (!s) return;
        parts.push(key + "=" + encodeURIComponent(s));
      }

      function openRosterGmCalculatorFromRms() {
        if (!rosterConvertModal.value) return;
        var parts = ["return_to=roster", "roster_add=1"];
        appendGmCalcQueryPart(parts, "targetClientId", rosterConvertModal.value.clientId);
        appendGmCalcQueryPart(parts, "full_name", rosterConvertForm.full_name);
        appendGmCalcQueryPart(parts, "work_location", rosterConvertForm.work_location);
        appendGmCalcQueryPart(parts, "position", rosterConvertForm.position_title);
        appendGmCalcQueryPart(parts, "monthly_quote_tax", normalizeRosterAmountText(rosterConvertForm.monthly_quote_tax));
        appendGmCalcQueryPart(parts, "pre_tax_salary", normalizeRosterAmountText(rosterConvertForm.pre_tax_salary));
        appendGmCalcQueryPart(parts, "gms", normalizeRosterAmountText(rosterConvertForm.gms));
        appendGmCalcQueryPart(parts, "gm_pct", rosterConvertForm.gm_pct);
        window.open("/tools/calc?" + parts.join("&"), "_blank");
      }

      async function openRosterConvertModal(appRow) {
        rosterConvertError.value = "";
        rosterConvertSaving.value = false;
        emptyRosterConvertForm();
        rosterConvertModal.value = { applicationId: appRow.id, clientId: appRow.client_id };
        var r = await rmsRequest("GET", "/api/rms/applications/" + appRow.id + "/roster-draft");
        if (!r.ok) {
          rosterConvertError.value = r.message || "加载花名册草稿失败";
          return;
        }
        var data = r.data || {};
        var payload = data.roster_payload || {};
        if (data.client_id != null) {
          rosterConvertModal.value.clientId = data.client_id;
        }
        Object.keys(rosterConvertForm).forEach(function (key) {
          if (payload[key] != null) rosterConvertForm[key] = String(payload[key]);
        });
      }

      function closeRosterConvertModal() {
        rosterConvertModal.value = null;
        rosterConvertError.value = "";
        rosterConvertSaving.value = false;
      }

      function openConvertedRosterEntry(a) {
        if (!a || !a.client_id || !a.converted_to_roster_entry_id) return;
        window.location.href = "/customers/roster/" + a.client_id + "?row_id=" + a.converted_to_roster_entry_id;
      }

      async function submitRosterConvert() {
        if (!rosterConvertModal.value) return;
        var clientErr = validateRosterConvertClientForm();
        if (clientErr) {
          rosterConvertError.value = clientErr;
          return;
        }
        rosterConvertSaving.value = true;
        rosterConvertError.value = "";
        var payload = {};
        Object.keys(rosterConvertForm).forEach(function (key) {
          payload[key] = rosterConvertForm[key];
        });
        payload.monthly_quote_tax = normalizeRosterAmountText(payload.monthly_quote_tax);
        payload.pre_tax_salary = normalizeRosterAmountText(payload.pre_tax_salary);
        payload.gms = normalizeRosterAmountText(payload.gms);
        payload.gm_pct = formatGmPctSymbol(payload.gm_pct);
        var appId = rosterConvertModal.value.applicationId;
        var r = await rmsRequest("POST", "/api/rms/applications/" + appId + "/convert-to-roster", payload);
        rosterConvertSaving.value = false;
        if (!r.ok) {
          rosterConvertError.value = r.message || "转入花名册失败";
          return;
        }
        closeRosterConvertModal();
        toast("已成功转入花名册", false);
        await loadApplications();
      }

      const modalTitle = computed(function () {
        if (modal.value === "job") return jobs.jobModalTitle.value;
        if (modal.value === "candidate") return candidates.candidateModalTitle.value;
        return "";
      });

      const modalCloseLabel = computed(function () {
        if (modal.value === "job" && jobs.jobModalReadonly.value) return "关闭";
        return "取消";
      });

      const modalShowSave = computed(function () {
        if (!modal.value) return false;
        if (modal.value === "job") return jobs.jobModalShowSave.value;
        if (modal.value === "candidate") return candidates.candidateModalShowSave.value;
        return true;
      });

      const clientNameByIdMap = computed(function () {
        const m = {};
        jobs.clientOptions.value.forEach(function (c) {
          m[c.id] = c.name || "";
        });
        jobs.jobsState.items.forEach(function (j) {
          if (j.client_id != null && j.client_name) {
            m[j.client_id] = j.client_name;
          }
        });
        return m;
      });

      function clientNameById(clientId) {
        return clientNameByIdMap.value[clientId] || "";
      }

      const candidates = window.CrmRmsCandidates && window.CrmRmsCandidates.createCandidatesState
        ? window.CrmRmsCandidates.createCandidatesState({
            ref: ref,
            reactive: reactive,
            computed: computed,
            watch: watch,
            nextTick: nextTick,
            modal: modal,
            modalError: modalError,
            modalSaving: modalSaving,
            toast: toast,
            jobs: jobs,
            activeTab: activeTab,
            viewMode: viewMode,
            clientNameById: clientNameById,
            Labels: Labels,
            PHONE_RE: PHONE_RE,
            isCandidateDuplicateError: isCandidateDuplicateError,
            userFacingRmsError: userFacingRmsError,
            showCandidateDuplicateDialog: showCandidateDuplicateDialog,
          })
        : {};

      // HC-R2-11: shell internal lexical aliases
      const candidatesState = candidates.candidatesState;
      const loadCandidates = candidates.loadCandidates;
      const scheduleCandidatesTableColumnFit = candidates.scheduleCandidatesTableColumnFit;
      const labelCandidate = candidates.labelCandidate;
      const candidateNameById = candidates.candidateNameById;
      const displayCandidateContact = candidates.displayCandidateContact;
      const displaySalary = candidates.displaySalary;
      const resumeViewUrl = candidates.resumeViewUrl;
      const resumeCanView = candidates.resumeCanView;
      const candidateParseSummaryFields = candidates.candidateParseSummaryFields;
      const candidateParseSummaryEmpty = candidates.candidateParseSummaryEmpty;
      const candidateParseSummaryValue = candidates.candidateParseSummaryValue;

      function formatRmsDate(value) {
        return Labels.formatRmsDate ? Labels.formatRmsDate(value) : (value || "—");
      }

      function receiveLabel(status) {
        return Labels.receiveLabel ? Labels.receiveLabel(status) : status;
      }

      function deliveryReviewLabel(status) {
        return Labels.deliveryReviewLabel ? Labels.deliveryReviewLabel(status) : status;
      }

      function protectionLabel(status) {
        return Labels.deriveProtectionStatus ? Labels.deriveProtectionStatus(status) : "—";
      }

      function progressActionBtnClass(status) {
        return Labels.progressActionBtnClass
          ? Labels.progressActionBtnClass(status)
          : "rms-progress-btn rms-progress-btn--blue";
      }

      const appDisplay = Labels.createAppDisplayHelpers
        ? Labels.createAppDisplayHelpers({
            getJobs: function () { return jobs.jobsState.items; },
            getCandidates: function () { return candidatesState.items; },
            getUsers: function () { return jobs.userOptions.value; },
            clientNameById: clientNameById,
            labelJob: jobs.labelJob,
          })
        : {};
      const appCandidateName = appDisplay.appCandidateName || function () { return "—"; };
      const appClientName = appDisplay.appClientName || function () { return "—"; };
      const appJobTitle = appDisplay.appJobTitle || function () { return "—"; };
      const appJobLocation = appDisplay.appJobLocation || function () { return "—"; };
      const appDeliveryLabel = appDisplay.appDeliveryLabel || function () { return "—"; };
      const appRecommenderLabel = appDisplay.appRecommenderLabel || function () { return "—"; };

      async function loadMe() {
        try {
          const data = await window.crmApi.get("/api/me");
          me.value = data;
          if (jobs.applyDefaultOwnerFromMe) jobs.applyDefaultOwnerFromMe();
        } catch (e) {
          /* page still usable; owner_user_id manual */
        }
      }

      async function loadDeliveryReview() {
        try {
          if (deliveryReviewApi) {
            await deliveryReviewApi.loadDeliveryReview(deliveryReviewState);
          }
        } finally {
          if (activeTab.value === "deliveryReview") {
            scheduleCandidatesTableColumnFit();
          }
        }
      }

      function toast(msg, isError) {
        if (window.crmToast) {
          if (isError && window.crmToast.error) window.crmToast.error(msg);
          else if (window.crmToast.success) window.crmToast.success(msg);
          else window.crmToast.show(msg);
        } else {
          alert(msg);
        }
      }

      if (!window.CrmRmsApplications || typeof window.CrmRmsApplications.createApplicationsState !== "function") {
        showRmsBootError("RMS 推荐记录模块未加载，请刷新后重试。");
        return {};
      }
      const applications = window.CrmRmsApplications.createApplicationsState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        rmsRequest: rmsRequest,
        toast: toast,
        candidatesState: candidatesState,
        displaySalary: displaySalary,
        formatRmsDate: formatRmsDate,
        scheduleCandidatesTableColumnFit: scheduleCandidatesTableColumnFit,
        loadCandidates: loadCandidates,
        loadDeliveryReview: loadDeliveryReview,
      });
      const applicationsState = applications.applicationsState;
      const loadApplications = applications.loadApplications;
      if (!applicationsState || !loadApplications) {
        showRmsBootError("RMS 推荐记录状态初始化失败，请刷新后重试。");
        return {};
      }

      if (!window.CrmRmsPipeline || typeof window.CrmRmsPipeline.createPipelineState !== "function") {
        showRmsBootError("RMS Pipeline 模块未加载，请刷新后重试。");
        return {};
      }
      const pipeline = window.CrmRmsPipeline.createPipelineState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        Labels: Labels,
        rmsRequest: rmsRequest,
        toast: toast,
        jobs: jobs,
        applicationsState: applicationsState,
        candidatesState: candidatesState,
        loadApplications: loadApplications,
        clientNameById: clientNameById,
        appCandidateName: appCandidateName,
        appJobTitle: appJobTitle,
      });

      let report = null;
      if (!window.CrmRmsReport || typeof window.CrmRmsReport.createReportState !== "function") {
        showRmsBootError("RMS 推荐报告模块未加载，请刷新后重试。");
        return {};
      }
      report = window.CrmRmsReport.createReportState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        watch: watch,
        nextTick: nextTick,
        viewMode: viewMode,
        rmsRequest: rmsRequest,
        toast: toast,
        jobs: jobs,
        candidatesState: candidatesState,
        loadApplications: loadApplications,
        loadCandidates: loadCandidates,
        loadDeliveryReview: loadDeliveryReview,
        clientNameById: clientNameById,
        labelCandidate: labelCandidate,
        displayCandidateContact: displayCandidateContact,
        resumeViewUrl: resumeViewUrl,
        resumeCanView: resumeCanView,
        candidateParseSummaryFields: candidateParseSummaryFields,
        candidateParseSummaryEmpty: candidateParseSummaryEmpty,
        candidateParseSummaryValue: candidateParseSummaryValue,
        formatSalaryThousands: formatSalaryThousands,
        PHONE_RE: PHONE_RE,
        showCandidateDuplicateDialog: showCandidateDuplicateDialog,
        isCandidateDuplicateError: isCandidateDuplicateError,
        userFacingRmsError: userFacingRmsError,
      });

      const reportMode = report.reportMode;
      if (!reportMode) {
        showRmsBootError("RMS 推荐报告状态初始化失败，请刷新后重试。");
        return {};
      }

      const canRecommendExistingCandidate = computed(function () {
        return canWriteApplications.value && canReadCandidates.value;
      });
      const canSubmitCandidateReport = computed(function () {
        if (reportMode.value === "existing") {
          return canWriteApplications.value && canReadCandidates.value;
        }
        return canWriteApplications.value && canWriteCandidates.value;
      });

      function userOptionLabel(u) {
        const dn = (u.display_name || "").trim();
        const un = (u.username || "").trim();
        if (dn && un) return dn + " · " + un;
        return dn || un || String(u.id);
      }

      function openDeliveryReviewModal(app) {
        reviewModalError.value = "";
        reviewFailPromptOpen.value = false;
        reviewModalSaving.value = false;
        reviewModal.value = app;
      }

      function closeDeliveryReviewModal() {
        reviewModal.value = null;
        reviewFailPromptOpen.value = false;
        reviewModalError.value = "";
        if (activeTab.value === "deliveryReview") {
          scheduleCandidatesTableColumnFit();
        }
      }

      async function openDeliveryReviewFailModal() {
        if (!reviewModal.value) return;
        if (typeof window.crmConfirmActionDialog !== "function") {
          reviewModalError.value = "确认对话框不可用";
          return;
        }
        const app = reviewModal.value;
        reviewFailPromptOpen.value = true;
        let result;
        try {
          result = await window.crmConfirmActionDialog({
            title: "内审失败",
            lines: [
              { label: "候选人", value: appCandidateName(app) },
              { label: "岗位", value: appJobTitle(app) },
            ],
            hint: "须填写失败理由，至少 2 个字",
            fields: [{
              type: "textarea",
              name: "note",
              label: "失败理由",
              placeholder: "请说明内审未通过原因",
            }],
            confirmText: "确认失败",
            cancelText: "取消",
            confirmClass: "flex-1 py-2 rounded-md border border-red-300 text-red-700 text-sm font-medium hover:bg-red-50",
            zIndex: 200,
          });
        } finally {
          reviewFailPromptOpen.value = false;
        }
        if (!result || !result.ok) return;
        const note = String((result.values && result.values.note) || "").trim();
        if (note.length < 2) {
          toast("内审失败须填写理由", true);
          return;
        }
        await submitDeliveryReview("failed", note);
      }

      async function submitDeliveryReview(result, note) {
        if (!reviewModal.value || !deliveryReviewApi) return;
        const trimmedNote = String(note == null ? "" : note).trim();
        if (result === "failed" && trimmedNote.length < 2) {
          reviewModalError.value = "内审失败须填写理由";
          return;
        }
        reviewModalSaving.value = true;
        reviewModalError.value = "";
        const r = await deliveryReviewApi.submitDeliveryReview(reviewModal.value.id, result, trimmedNote);
        reviewModalSaving.value = false;
        if (!r.ok) {
          reviewModalError.value = r.message;
          return;
        }
        const warnMsg = r.data && r.data.message;
        if (warnMsg) {
          toast(warnMsg, true);
          closeDeliveryReviewModal();
          await Promise.all([loadDeliveryReview(), loadApplications()]);
          return;
        }
        toast(result === "passed" ? "内审通过" : "内审失败", false);
        closeDeliveryReviewModal();
        await Promise.all([loadDeliveryReview(), loadApplications()]);
      }

      function closeModal() {
        modal.value = null;
        modalError.value = "";
        if (jobs.resetJobModalState) jobs.resetJobModalState();
        if (candidates.resetCandidateModalState) candidates.resetCandidateModalState();
      }

      async function submitModal() {
        modalSaving.value = true;
        modalError.value = "";
        let r;
        try {
        if (modal.value === "job") {
          await jobs.submitJobModal();
          return;
        } else if (modal.value === "candidate") {
          await candidates.submitCandidateModal();
          return;
        } else {
          return;
        }
        } catch (err) {
          const msg = err && err.message ? err.message : String(err);
          setModalError("保存失败：" + msg);
        } finally {
          modalSaving.value = false;
        }
      }

      watch(activeTab, function (tab) {
        if (tab === "candidates" || tab === "applications" || tab === "deliveryReview" || tab === "pipeline") {
          scheduleCandidatesTableColumnFit();
        }
        if (tab === "deliveryReview") {
          loadDeliveryReview();
        }
      });

      onMounted(async function () {
        await Promise.all([
          loadMe(),
          jobs.loadJobs(),
          loadCandidates(),
          loadApplications(),
          loadDeliveryReview(),
          jobs.loadJobFormOptions(),
        ]);
        if (activeTab.value === "candidates") {
          scheduleCandidatesTableColumnFit();
        }
      });

      return {
        activeTab,
        viewMode,
        ...jobs,
        jobModalReadonly: jobs.jobModalReadonly,
        ...candidates,
        ...applications,
        deliveryReviewState,
        reviewModal,
        reviewFailPromptOpen,
        reviewModalSaving,
        reviewModalError,
        ...report,
        canWriteJobs,
        canWriteCandidates,
        canWriteApplications,
        canReadCandidates,
        canRecommendExistingCandidate,
        canSubmitCandidateReport,
        canConvertToRoster,
        rosterConvertModal,
        rosterConvertSaving,
        rosterConvertError,
        rosterConvertForm,
        openRosterConvertModal,
        closeRosterConvertModal,
        openRosterGmCalculatorFromRms,
        openConvertedRosterEntry,
        submitRosterConvert,
        modal,
        modalTitle,
        modalError,
        modalSaving,
        modalCloseLabel,
        modalShowSave,
        ...pipeline,
        educationOptions: EDUCATION_OPTIONS,
        genderOptions: GENDER_OPTIONS,
        sourceOptions: SOURCE_OPTIONS,
        maritalOptions: MARITAL_OPTIONS,
        formatRmsDate,
        receiveLabel,
        deliveryReviewLabel,
        protectionLabel,
        progressActionBtnClass,
        appCandidateName,
        appClientName,
        appJobTitle,
        appJobLocation,
        appDeliveryLabel,
        appRecommenderLabel,
        userOptionLabel,
        clientNameById,
        openDeliveryReviewModal,
        closeDeliveryReviewModal,
        openDeliveryReviewFailModal,
        submitDeliveryReview,
        closeModal,
        submitModal,
      };
    },
  }).mount("#rms-app");
  } catch (bootErr) {
    console.error("RMS mount failed:", bootErr);
    showRmsBootError(
      "招聘页面初始化失败：" + (bootErr && bootErr.message ? bootErr.message : String(bootErr))
    );
  }
})();
