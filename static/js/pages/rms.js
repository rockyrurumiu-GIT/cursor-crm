/**
 * RMS module page (Phase 2.5 frontend MVP).
 * Requires: Vue 3 CDN, crm-api.js, rms-core.js, rms-jobs.js, rms-candidates.js (optional crm-toast.js).
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

  function pipelineStatusMatches(appStatus, selectedStatuses) {
    if (Labels.statusMatchesFilter) {
      return Labels.statusMatchesFilter(appStatus, selectedStatuses);
    }
    const selected = Array.isArray(selectedStatuses) ? selectedStatuses : [];
    if (!selected.length) return true;
    const raw = String(appStatus == null ? "" : appStatus).trim();
    let normalized = raw;
    if (Labels.filterProgressStatus) {
      normalized = Labels.filterProgressStatus(raw);
    } else if (raw === "recommended") {
      normalized = "pending_internal_screen";
    } else if (raw === "screening") {
      normalized = "pending_client_screen";
    } else if (raw === "interview") {
      normalized = "pending_first_interview";
    } else if (raw === "offer") {
      normalized = "pending_offer";
    }
    for (let i = 0; i < selected.length; i++) {
      const want = String(selected[i] == null ? "" : selected[i]).trim();
      if (want && (raw === want || normalized === want)) return true;
    }
    return false;
  }

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

      const applicationsState = reactive({ loading: false, items: [], error: "" });
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

      const pipelineFilter = reactive({
        client_id: "",
        job_id: "",
        city: "",
        delivery: "",
        recommender: "",
        statuses: [],
        activeOnly: true,
        date_from: "",
        date_to: "",
      });

      const applicationsFilter = reactive({
        hired_unconverted_only: false,
      });

      const statusHistoryModal = ref(null);
      const statusHistoryLoading = ref(false);
      const statusHistoryError = ref("");
      const statusHistoryItems = ref([]);

      const applicationDetailModal = ref(null);
      const applicationDetailFailNote = ref("");
      const applicationDetailLoading = ref(false);

      const progressOptions = (Labels.APPLICATION_PROGRESS_STATUSES || []).map(function (s) {
        return { value: s, label: Labels.progressLabel ? Labels.progressLabel(s) : s };
      });
      const pipelineStatusDropdownOpen = ref(false);
      const pipelineStatusDraft = ref([]);
      const pipelineStatusFilterSummary = computed(function () {
        const sel = pipelineFilter.statuses || [];
        if (!sel.length) return "全部";
        if (sel.length === 1) return progressLabel(sel[0]);
        return "已选" + sel.length + "项";
      });

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

      const filteredApplications = computed(function () {
        var rows = applicationsState.items.slice();
        if (applicationsFilter.hired_unconverted_only) {
          rows = rows.filter(function (a) {
            return a.status === "hired" && !a.converted_to_roster_entry_id;
          });
        }
        return rows;
      });

      const filteredPipelineApplications = computed(function () {
        if (!Labels.filterPipelineApplications) return [];
        const appliedStatuses = (pipelineFilter.statuses || []).slice();
        const rows = Labels.filterPipelineApplications(applicationsState.items, {
          filters: {
            client_id: pipelineFilter.client_id,
            job_id: pipelineFilter.job_id,
            city: pipelineFilter.city,
            delivery: pipelineFilter.delivery,
            recommender: pipelineFilter.recommender,
            statuses: [],
            activeOnly: appliedStatuses.length ? false : pipelineFilter.activeOnly,
            date_from: pipelineFilter.date_from,
            date_to: pipelineFilter.date_to,
          },
          getJobs: function () { return jobs.jobsState.items; },
          getCandidates: function () { return candidatesState.items; },
          getUsers: function () { return jobs.userOptions.value; },
          clientNameById: clientNameById,
        });
        if (!appliedStatuses.length) return rows;
        return rows.filter(function (a) {
          return pipelineStatusMatches(a.status, appliedStatuses);
        });
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

      function progressLabel(status) {
        return Labels.progressLabel ? Labels.progressLabel(status) : status;
      }

      function formatRmsDate(value) {
        return Labels.formatRmsDate ? Labels.formatRmsDate(value) : (value || "—");
      }

      function receiveLabel(status) {
        return Labels.receiveLabel ? Labels.receiveLabel(status) : status;
      }

      function deliveryReviewLabel(status) {
        return Labels.deliveryReviewLabel ? Labels.deliveryReviewLabel(status) : status;
      }

      function todayDateStr() {
        const d = new Date();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return d.getFullYear() + "-" + m + "-" + day;
      }

      const hiredAtDates = reactive({});

      function protectionLabel(status) {
        return Labels.deriveProtectionStatus ? Labels.deriveProtectionStatus(status) : "—";
      }

      function progressTransitionsFor(status) {
        return Labels.progressTransitionsFor ? Labels.progressTransitionsFor(status) : [];
      }

      function progressActionBtnClass(status) {
        return Labels.progressActionBtnClass
          ? Labels.progressActionBtnClass(status)
          : "rms-progress-btn rms-progress-btn--blue";
      }

      function progressOptionsForCorrection(currentStatus) {
        return Labels.progressOptionsForCorrection
          ? Labels.progressOptionsForCorrection(currentStatus)
          : [];
      }

      function normalizeProgressStatus(status) {
        return Labels.normalizeProgressStatus
          ? Labels.normalizeProgressStatus(status)
          : String(status || "").trim();
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

      function candidateForApp(a) {
        if (!a || a.candidate_id == null || a.candidate_id === "") return null;
        const cid = Number(a.candidate_id);
        return candidatesState.items.find(function (c) {
          return Number(c.id) === cid;
        }) || null;
      }

      function appCandidateAge(a) {
        const c = candidateForApp(a);
        return (c && c.age) ? c.age : "—";
      }

      function appCandidateWorkYears(a) {
        const c = candidateForApp(a);
        return (c && c.work_years) ? c.work_years : "—";
      }

      function appCandidateCurrentSalary(a) {
        const c = candidateForApp(a);
        return c ? displaySalary(c.current_salary) : "—";
      }

      function appCandidateExpectedSalary(a) {
        const c = candidateForApp(a);
        return c ? displaySalary(c.expected_salary) : "—";
      }

      function appCandidateAvailableDate(a) {
        const c = candidateForApp(a);
        return c ? formatRmsDate(c.available_date) : "—";
      }

      function appCandidateEducation(a) {
        const c = candidateForApp(a);
        return (c && c.education_level) ? c.education_level : "—";
      }

      function resumeViewUrlById(resumeId) {
        if (resumeId == null || resumeId === "") return "#";
        return "/api/rms/resumes/" + resumeId + "/view";
      }

      function resumeCanViewByName(fileName) {
        return /\.(pdf|txt|rtf)$/i.test(String(fileName || ""));
      }

      async function loadMe() {
        try {
          const data = await window.crmApi.get("/api/me");
          me.value = data;
          if (jobs.applyDefaultOwnerFromMe) jobs.applyDefaultOwnerFromMe();
        } catch (e) {
          /* page still usable; owner_user_id manual */
        }
      }

      async function loadApplications() {
        applicationsState.loading = true;
        applicationsState.error = "";
        try {
          const r = await rmsRequest("GET", "/api/rms/applications");
          if (!r.ok) {
            applicationsState.items = [];
            applicationsState.error = r.message;
            return;
          }
          applicationsState.items = Array.isArray(r.data) ? r.data : [];
        } finally {
          applicationsState.loading = false;
          scheduleCandidatesTableColumnFit();
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

      function resetPipelineFilter() {
        pipelineFilter.client_id = "";
        pipelineFilter.job_id = "";
        pipelineFilter.city = "";
        pipelineFilter.delivery = "";
        pipelineFilter.recommender = "";
        pipelineFilter.statuses.splice(0, pipelineFilter.statuses.length);
        pipelineStatusDraft.value = [];
        pipelineFilter.activeOnly = true;
        pipelineStatusDropdownOpen.value = false;
        pipelineFilter.date_from = "";
        pipelineFilter.date_to = "";
      }

      function togglePipelineStatusDropdown() {
        if (!pipelineStatusDropdownOpen.value) {
          pipelineStatusDraft.value = (pipelineFilter.statuses || []).slice();
        }
        pipelineStatusDropdownOpen.value = !pipelineStatusDropdownOpen.value;
      }

      function togglePipelineStatusDraft(value) {
        const list = pipelineStatusDraft.value;
        const idx = list.indexOf(value);
        if (idx >= 0) list.splice(idx, 1);
        else list.push(value);
      }

      function clearPipelineStatusDraft() {
        pipelineStatusDraft.value = [];
      }

      function applyPipelineStatusFilter() {
        const next = pipelineStatusDraft.value.slice();
        pipelineFilter.statuses.splice(0, pipelineFilter.statuses.length);
        next.forEach(function (v) {
          pipelineFilter.statuses.push(v);
        });
        pipelineStatusDropdownOpen.value = false;
      }

      function deliveryReviewFailNoteFromHistory(items) {
        if (!Array.isArray(items)) return "";
        for (let i = 0; i < items.length; i++) {
          const h = items[i];
          if (h && h.reason === "delivery_review_failed") {
            return String(h.note || "").trim();
          }
        }
        return "";
      }

      async function openApplicationDetailModal(app) {
        if (!app) return;
        applicationDetailModal.value = app;
        applicationDetailFailNote.value = "";
        applicationDetailLoading.value = false;
        const dr = String(app.delivery_review_status == null ? "" : app.delivery_review_status).trim();
        const needsFailNote = dr === "failed" || app.status === "internal_screen_failed";
        if (!needsFailNote || app.id == null) return;
        applicationDetailLoading.value = true;
        const r = await rmsRequest("GET", "/api/rms/applications/" + app.id + "/status-history");
        applicationDetailLoading.value = false;
        if (r.ok) {
          applicationDetailFailNote.value = deliveryReviewFailNoteFromHistory(r.data);
        }
      }

      function closeApplicationDetailModal() {
        applicationDetailModal.value = null;
        applicationDetailFailNote.value = "";
        applicationDetailLoading.value = false;
      }

      function closeStatusHistoryModal() {
        statusHistoryModal.value = null;
        statusHistoryLoading.value = false;
        statusHistoryError.value = "";
        statusHistoryItems.value = [];
      }

      async function openStatusHistoryModal(app) {
        if (!app || app.id == null) return;
        statusHistoryModal.value = app;
        statusHistoryLoading.value = true;
        statusHistoryError.value = "";
        statusHistoryItems.value = [];
        const r = await rmsRequest("GET", "/api/rms/applications/" + app.id + "/status-history");
        statusHistoryLoading.value = false;
        if (!r.ok) {
          statusHistoryError.value = r.message || "加载状态历史失败";
          return;
        }
        statusHistoryItems.value = Array.isArray(r.data) ? r.data : [];
      }

      async function removeApplication(row) {
        const base = "/api/rms/applications/" + row.id;
        let r = await rmsRequest("DELETE", base);
        if (!r.ok && r.status === 405) {
          r = await rmsRequest("POST", base + "/delete");
        }
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        toast("已删除推荐记录", false);
        await Promise.all([loadApplications(), loadCandidates(), loadDeliveryReview()]);
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

      function hiredAtFor(appId) {
        const id = String(appId);
        if (!hiredAtDates[id]) hiredAtDates[id] = todayDateStr();
        return hiredAtDates[id];
      }

      function setHiredAtFor(appId, value) {
        hiredAtDates[String(appId)] = value;
      }

      async function submitProgressConfirm(applicationId, toStatus, mode, formValues) {
        formValues = formValues || {};
        const note = String(formValues.note || "").trim();
        if (mode === "correction" && note.length < 2) {
          toast("状态修正备注至少 2 个字", true);
          return;
        }
        const body = { to_status: toStatus, mode: mode, note: note };
        if (toStatus === "hired") {
          const dateVal = String(formValues.hired_at || todayDateStr()).trim();
          if (!dateVal) {
            toast("请填写入职时间", true);
            return;
          }
          body.hired_at = dateVal;
        }
        const r = await rmsRequest("POST", "/api/rms/applications/" + applicationId + "/status", body);
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        const data = r.data || {};
        if (data.roster_check && data.roster_check.message) {
          const st = data.roster_check.status;
          const isWarn = st === "missing" || st === "date_mismatch" || st === "ambiguous";
          toast(data.roster_check.message, isWarn);
        } else {
          toast("招聘进展已更新为 " + progressLabel(toStatus), false);
        }
        delete hiredAtDates[String(applicationId)];
        await loadApplications();
      }

      async function openProgressConfirmModal(app, targetStatus, mode) {
        if (!app || app.id == null || !targetStatus) return;
        if (typeof window.crmConfirmActionDialog !== "function") {
          toast("确认对话框不可用", true);
          return;
        }
        const lines = [
          { label: "候选人", value: appCandidateName(app) },
          { label: "岗位", value: appJobTitle(app) },
          { label: "当前状态", value: progressLabel(app.status) },
          { label: "目标状态", value: progressLabel(targetStatus) },
          { label: "操作类型", value: mode === "correction" ? "状态修正" : "正常推进" },
        ];
        let hint = "";
        if (app.status === "hired" && targetStatus !== "hired") {
          hint = "确认后将清空入职时间。";
        }
        const fields = [{
          type: "textarea",
          name: "note",
          label: "备注/原因",
          placeholder: mode === "correction" ? "必填，至少 2 个字" : "可选",
        }];
        if (targetStatus === "hired") {
          fields.push({
            type: "date",
            name: "hired_at",
            label: "入职时间",
            value: hiredAtFor(app.id),
          });
        }
        const result = await window.crmConfirmActionDialog({
          title: "确认变更招聘进展",
          lines: lines,
          hint: hint,
          fields: fields,
          confirmText: "确认",
          cancelText: "取消",
          zIndex: 120,
        });
        if (!result || !result.ok) return;
        await submitProgressConfirm(app.id, targetStatus, mode, result.values || {});
      }

      async function openCorrectionPickerModal(app) {
        if (!app || app.id == null) return;
        if (typeof window.crmConfirmActionDialog !== "function") {
          toast("确认对话框不可用", true);
          return;
        }
        const options = progressOptionsForCorrection(app.status);
        if (!options.length) {
          toast("暂无可选目标状态", true);
          return;
        }
        let hint = "";
        if (normalizeProgressStatus(app.status) === "hired") {
          hint = "若目标不是已入职，确认后将清空入职时间。";
        }
        const result = await window.crmConfirmActionDialog({
          title: "修改招聘进展",
          lines: [
            { label: "候选人", value: appCandidateName(app) },
            { label: "岗位", value: appJobTitle(app) },
            { label: "当前状态", value: progressLabel(app.status) },
            { label: "操作类型", value: "状态修正" },
          ],
          fields: [{
            type: "select",
            name: "to_status",
            label: "目标招聘进展",
            placeholder: "请选择",
            options: options,
          }],
          hint: hint,
          confirmText: "下一步",
          cancelText: "取消",
          zIndex: 120,
        });
        if (!result || !result.ok) return;
        const target = String((result.values && result.values.to_status) || "").trim();
        if (!target) {
          toast("请选择目标状态", true);
          return;
        }
        await openProgressConfirmModal(app, target, "correction");
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
        applicationsState,
        deliveryReviewState,
        reviewModal,
        reviewFailPromptOpen,
        reviewModalSaving,
        reviewModalError,
        statusHistoryModal,
        statusHistoryLoading,
        statusHistoryError,
        statusHistoryItems,
        applicationDetailModal,
        applicationDetailFailNote,
        applicationDetailLoading,
        openApplicationDetailModal,
        closeApplicationDetailModal,
        openStatusHistoryModal,
        closeStatusHistoryModal,
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
        applicationsFilter,
        filteredApplications,
        pipelineFilter,
        pipelineStatusDropdownOpen,
        pipelineStatusDraft,
        pipelineStatusFilterSummary,
        togglePipelineStatusDropdown,
        togglePipelineStatusDraft,
        clearPipelineStatusDraft,
        applyPipelineStatusFilter,
        filteredPipelineApplications,
        progressOptions,
        progressOptionsForCorrection,
        openCorrectionPickerModal,
        openProgressConfirmModal,
        submitProgressConfirm,
        educationOptions: EDUCATION_OPTIONS,
        genderOptions: GENDER_OPTIONS,
        sourceOptions: SOURCE_OPTIONS,
        maritalOptions: MARITAL_OPTIONS,
        progressLabel,
        formatRmsDate,
        receiveLabel,
        deliveryReviewLabel,
        protectionLabel,
        progressTransitionsFor,
        progressActionBtnClass,
        hiredAtFor,
        setHiredAtFor,
        appCandidateName,
        appClientName,
        appJobTitle,
        appJobLocation,
        appDeliveryLabel,
        appRecommenderLabel,
        appCandidateAge,
        appCandidateWorkYears,
        appCandidateCurrentSalary,
        appCandidateExpectedSalary,
        appCandidateAvailableDate,
        appCandidateEducation,
        resumeViewUrlById,
        resumeCanViewByName,
        userOptionLabel,
        clientNameById,
        resetPipelineFilter,
        openDeliveryReviewModal,
        closeDeliveryReviewModal,
        openDeliveryReviewFailModal,
        submitDeliveryReview,
        removeApplication,
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
