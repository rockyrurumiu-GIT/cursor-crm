/**
 * RMS module page (Phase 2.5 frontend MVP).
 * Requires: Vue 3 CDN, crm-api.js (optional crm-toast.js).
 */
(function () {
  "use strict";

  const Labels = window.RmsApplicationLabels || {};
  const CandidateReport = window.RmsCandidateReport || {};

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

  const PRIORITY_OPTIONS = [
    { value: "high", label: "高" },
    { value: "medium", label: "中" },
    { value: "low", label: "低" },
  ];

  const STATUS_OPTIONS = [
    { value: "open", label: "open" },
    { value: "closed", label: "closed" },
    { value: "freeze", label: "freeze" },
  ];

  const PRIORITY_LABELS = { high: "高", medium: "中", low: "低" };
  const STATUS_LABELS = { open: "open", closed: "closed", freeze: "freeze" };

  const EDUCATION_OPTIONS = ["重本", "统本", "专科", "硕士", "留学生", "民教网", "其他"];
  const GENDER_OPTIONS = ["男", "女"];
  const SOURCE_OPTIONS = ["平台", "Boss", "linkedin", "猎聘", "内推", "挂靠", "外协", "其他"];
  const MARITAL_OPTIONS = ["未婚", "已婚"];
  const PHONE_RE = /^1\d{10}$/;
  const JOB_SALARY_CAP_MIN = 1000;
  const JOB_SALARY_CAP_MAX = 99999;
  const REPORT_LOCAL_TEXT_PREVIEW_MAX = 2000;

  function stripSalaryCommas(s) {
    return String(s == null ? "" : s).replace(/,/g, "").trim();
  }

  function formatSalaryThousands(s) {
    const raw = stripSalaryCommas(s);
    if (!raw) return "";
    if (/[kK万千%]/.test(raw)) return raw;
    if (!/^-?\d+(\.\d+)?$/.test(raw)) return raw;
    const n = Number(raw);
    if (!Number.isFinite(n)) return raw;
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
  }

  function stripJobSalaryCapInput(s) {
    return String(s == null ? "" : s).replace(/\D/g, "");
  }

  function jobSalaryCapInRange(n) {
    return Number.isInteger(n) && n >= JOB_SALARY_CAP_MIN && n <= JOB_SALARY_CAP_MAX;
  }

  function formatJobSalaryCapDisplay(value) {
    const digits = stripJobSalaryCapInput(value);
    if (!digits) return "";
    const n = Number(digits);
    if (!Number.isFinite(n) || !jobSalaryCapInRange(n)) return digits;
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }

  function fuzzyMatch(haystack, needle) {
    const n = (needle || "").trim().toLowerCase();
    if (!n) return true;
    return String(haystack || "").toLowerCase().indexOf(n) !== -1;
  }

  function authHeaders() {
    return typeof window.crmAuthHeader === "function" ? window.crmAuthHeader() : {};
  }

  function formatDetail(detail) {
    if (detail == null || detail === "") return "";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map(function (x) {
          return typeof x === "object" && x && x.msg ? x.msg : String(x);
        })
        .join("; ");
    }
    return String(detail);
  }

  function messageForStatus(status, detail) {
    const d = formatDetail(detail);
    if (status === 403) return "无权限 (403)" + (d ? "：" + d : "");
    if (status === 404) return "记录不存在或不可见 (404)" + (d ? "：" + d : "");
    if (status === 409) return "重复推荐 (409)" + (d ? "：" + d : "");
    if (status === 400) return "请求无效 (400)" + (d ? "：" + d : "");
    if (status === 422) return "数据校验失败 (422)" + (d ? "：" + d : "");
    if (status === 405) {
      return "请求方法不被允许 (405)" + (d ? "：" + d : "（请重启后端服务，或当前环境不支持 DELETE）");
    }
    return "请求失败 (" + status + ")" + (d ? "：" + d : "");
  }

  function workflowMessageForStatus(status, detail, endpoint) {
    if (status === 404) {
      if (endpoint === "parse-draft") return "简历解析接口暂未接通";
      if (endpoint === "candidate-report") return "推荐上报接口暂未接通";
      if (endpoint === "delivery-review") return "交付内审接口暂未接通";
    }
    return messageForStatus(status, detail);
  }

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

  function showValidationPrompt(message) {
    const msg = String(message || "").trim() || "提交未成功，请检查必填项";
    try {
      toast(msg, true);
    } catch (e) {
      /* toast optional */
    }
    return msg;
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

  async function rmsRequest(method, url, body) {
    const headers = Object.assign({}, authHeaders());
    const opts = { method: method, headers: headers, credentials: "same-origin" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      const msg = e && e.message ? e.message : String(e);
      return {
        ok: false,
        status: 0,
        message: "无法连接服务，请确认后端已启动（" + msg + "）",
      };
    }
    let payload = null;
    const ct = resp.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      try {
        payload = await resp.json();
      } catch (e) {
        payload = null;
      }
    } else if (!resp.ok) {
      try {
        payload = { detail: await resp.text() };
      } catch (e2) {
        payload = null;
      }
    }
    if (!resp.ok) {
      const detail = payload && payload.detail != null ? payload.detail : "";
      return {
        ok: false,
        status: resp.status,
        detail: detail,
        message: messageForStatus(resp.status, detail),
      };
    }
    return { ok: true, data: payload };
  }

  function showRmsBootError(msg) {
    var el = document.getElementById("rms-app");
    if (!el) return;
    el.removeAttribute("v-cloak");
    if (el.querySelector("[data-rms-boot-error]")) return;
    var box = document.createElement("div");
    box.setAttribute("data-rms-boot-error", "1");
    box.className = "rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 mb-4";
    box.textContent = msg;
    el.insertBefore(box, el.firstChild);
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

      const jobsState = reactive({ loading: false, items: [], error: "" });
      const candidatesState = reactive({ loading: false, items: [], error: "" });
      const applicationsState = reactive({ loading: false, items: [], error: "" });
      const deliveryReviewState = reactive({ loading: false, items: [], error: "" });
      const reviewModal = ref(null);
      const reviewFailPromptOpen = ref(false);
      const reviewModalSaving = ref(false);
      const reviewModalError = ref("");
      const reportSaving = ref(false);
      const reportError = ref("");
      const reportResumeFile = ref(null);
      const reportResumeInput = ref(null);
      const reportResumeDraftStatus = ref("idle");
      const reportResumeDraftError = ref("");
      const reportResumePdfPreviewUrl = ref("");
      const reportResumeTextPreview = ref("");
      const reportResumeTextPreviewTruncated = ref(false);
      const reportResumePreviewText = ref("");
      const reportResumePreviewError = ref("");
      const reportResumePreviewWarning = ref("");
      const reportResumePreviewRawText = ref("");
      const reportResumePreviewLength = ref(0);
      const reportResumePreviewRawLength = ref(0);
      const reportShowRawExtractDebug = ref(
        typeof window !== "undefined" &&
          /(?:^|[?&])rms_debug=1(?:&|$)/.test(window.location.search || "")
      );
      const reportResumeDragging = ref(false);
      const reportAutoFilledFields = reactive({});
      const reportForm = reactive(CandidateReport.emptyReportForm ? CandidateReport.emptyReportForm() : {});

      let reportPageDragGuardOn = false;
      function onReportPageDragOver(ev) {
        ev.preventDefault();
      }
      function onReportPageDrop(ev) {
        ev.preventDefault();
      }
      function installReportPageDragGuard() {
        if (reportPageDragGuardOn) return;
        reportPageDragGuardOn = true;
        document.addEventListener("dragover", onReportPageDragOver);
        document.addEventListener("drop", onReportPageDrop);
      }
      function removeReportPageDragGuard() {
        if (!reportPageDragGuardOn) return;
        reportPageDragGuardOn = false;
        document.removeEventListener("dragover", onReportPageDragOver);
        document.removeEventListener("drop", onReportPageDrop);
      }
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
      const jobModalMode = ref("create");
      const editingJobId = ref(null);
      const candidateModalMode = ref("create");
      const editingCandidateId = ref(null);
      const editingCandidateResumeName = ref("");
      const jobFilterPanelExpanded = ref(true);
      const jobsScrollWrap = ref(null);
      const candidatesScrollWrap = ref(null);

      const jobFilter = reactive({
        title: "",
        client_id: "",
        priority: "",
        status: "",
      });

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

      const candidateFilter = reactive({
        name: "",
        client_id: "",
        job_id: "",
        city: "",
        source: "",
        education_level: "",
        date_from: "",
        date_to: "",
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

      const clientOptions = ref([]);
      const userOptions = ref([]);
      const jobFormOptionsError = ref("");

      const jobForm = reactive({
        client_id: "",
        title: "",
        priority: "medium",
        status: "open",
        job_description: "",
        headcount: 1,
        salary_cap: "",
        years_required: "",
        location: "",
        education: "",
        overtime_travel: "",
        department: "",
        interviewer: "",
        sales_owner_user_id: "",
        owner_user_id: "",
        delivery_owner_user_id: "",
        note: "",
        sales_owner_label: "",
        delivery_owner_label: "",
      });
      const candidateForm = reactive({
        name: "",
        age: "",
        work_years: "",
        phone: "",
        email_wechat: "",
        target_job_id: "",
        target_client_id: "",
        city: "",
        current_salary: "",
        expected_salary: "",
        available_date: "",
        education_level: "",
        school: "",
        major: "",
        gender: "",
        marital_status: "",
        source: "",
      });
      const candidateResumeFile = ref(null);
      const jobPickerQuery = ref("");
      const jobPickerOpen = ref(false);
      const clientPickerQuery = ref("");
      const clientPickerOpen = ref(false);
      const canWriteJobs = computed(function () {
        return me.value.permissions.indexOf("rms.jobs.write") !== -1;
      });
      const canWriteCandidates = computed(function () {
        return me.value.permissions.indexOf("rms.candidates.write") !== -1;
      });
      const canWriteApplications = computed(function () {
        return me.value.permissions.indexOf("rms.applications.write") !== -1;
      });

      const modalTitle = computed(function () {
        if (modal.value === "job") {
          if (jobModalMode.value === "view") return "岗位详情";
          if (jobModalMode.value === "edit") return "修改岗位";
          return "新建岗位";
        }
        if (modal.value === "candidate") {
          return candidateModalMode.value === "edit" ? "修改候选人" : "新建候选人";
        }
        return "";
      });

      const jobModalReadonly = computed(function () {
        return modal.value === "job" && jobModalMode.value === "view";
      });

      const modalCloseLabel = computed(function () {
        return jobModalReadonly.value ? "关闭" : "取消";
      });

      const modalShowSave = computed(function () {
        if (!modal.value) return false;
        if (modal.value === "job") return !jobModalReadonly.value;
        return true;
      });

      const filteredJobs = computed(function () {
        let rows = jobsState.items.slice();
        const title = (jobFilter.title || "").trim().toLowerCase();
        if (title) {
          rows = rows.filter(function (j) {
            return String(j.title || "").toLowerCase().indexOf(title) !== -1;
          });
        }
        if (jobFilter.client_id !== "" && jobFilter.client_id != null) {
          const cid = Number(jobFilter.client_id);
          rows = rows.filter(function (j) {
            return Number(j.client_id) === cid;
          });
        }
        if (jobFilter.priority) {
          rows = rows.filter(function (j) {
            return j.priority === jobFilter.priority;
          });
        }
        if (jobFilter.status) {
          rows = rows.filter(function (j) {
            return j.status === jobFilter.status;
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
          getJobs: function () { return jobsState.items; },
          getCandidates: function () { return candidatesState.items; },
          getUsers: function () { return userOptions.value; },
          clientNameById: clientNameById,
        });
        if (!appliedStatuses.length) return rows;
        return rows.filter(function (a) {
          return pipelineStatusMatches(a.status, appliedStatuses);
        });
      });

      const filteredCandidates = computed(function () {
        let rows = candidatesState.items.slice();
        const name = (candidateFilter.name || "").trim().toLowerCase();
        if (name) {
          rows = rows.filter(function (c) {
            return String(c.name || "").toLowerCase().indexOf(name) !== -1;
          });
        }
        if (candidateFilter.client_id !== "" && candidateFilter.client_id != null) {
          const cid = Number(candidateFilter.client_id);
          rows = rows.filter(function (c) {
            return Number(c.target_client_id) === cid;
          });
        }
        if (candidateFilter.job_id !== "" && candidateFilter.job_id != null) {
          const jid = Number(candidateFilter.job_id);
          rows = rows.filter(function (c) {
            return Number(c.target_job_id) === jid;
          });
        }
        const city = (candidateFilter.city || "").trim().toLowerCase();
        if (city) {
          rows = rows.filter(function (c) {
            return String(c.city || "").toLowerCase().indexOf(city) !== -1;
          });
        }
        if (candidateFilter.source) {
          rows = rows.filter(function (c) {
            return c.source === candidateFilter.source;
          });
        }
        if (candidateFilter.education_level) {
          rows = rows.filter(function (c) {
            return c.education_level === candidateFilter.education_level;
          });
        }
        const parseDateOnly = Labels.parseDateOnly || function () { return null; };
        const from = parseDateOnly(candidateFilter.date_from);
        const to = parseDateOnly(candidateFilter.date_to);
        if (from || to) {
          rows = rows.filter(function (c) {
            const recDate = parseDateOnly(c.recommended_at);
            if (from && (!recDate || recDate < from)) return false;
            if (to && (!recDate || recDate > to)) return false;
            return true;
          });
        }
        return rows;
      });

      const jobTitleById = computed(function () {
        const m = {};
        jobsState.items.forEach(function (j) {
          m[j.id] = j.title || "";
        });
        return m;
      });

      const candidateNameById = computed(function () {
        const m = {};
        candidatesState.items.forEach(function (c) {
          m[c.id] = c.name || "";
        });
        return m;
      });

      const clientNameByIdMap = computed(function () {
        const m = {};
        clientOptions.value.forEach(function (c) {
          m[c.id] = c.name || "";
        });
        jobsState.items.forEach(function (j) {
          if (j.client_id != null && j.client_name) {
            m[j.client_id] = j.client_name;
          }
        });
        return m;
      });

      function clientNameById(clientId) {
        return clientNameByIdMap.value[clientId] || "";
      }

      function priorityLabel(value) {
        return PRIORITY_LABELS[value] || value || "—";
      }

      function statusLabel(value) {
        return STATUS_LABELS[value] || value || "—";
      }

      function labelJob(jobId) {
        const title = jobTitleById.value[jobId];
        return title ? title : "#" + jobId;
      }

      function labelCandidate(candidateId) {
        const name = candidateNameById.value[candidateId];
        return name ? name : "#" + candidateId;
      }

      const openJobs = computed(function () {
        return jobsState.items.filter(function (j) {
          return (j.status || "") === "open";
        });
      });

      const filteredJobPickerOptions = computed(function () {
        const q = jobPickerQuery.value;
        return openJobs.value.filter(function (j) {
          const label = (j.title || "") + " " + (j.client_name || clientNameById(j.client_id) || "");
          return fuzzyMatch(label, q);
        });
      });

      const filteredClientPickerOptions = computed(function () {
        const q = clientPickerQuery.value;
        return clientOptions.value.filter(function (c) {
          return fuzzyMatch(c.name, q);
        });
      });

      const selectedJobPickerLabel = computed(function () {
        const id = candidateForm.target_job_id;
        if (id === "" || id == null) return "";
        const j = jobsState.items.find(function (x) {
          return Number(x.id) === Number(id);
        });
        if (j) {
          return (j.title || "—") + (j.client_name ? " · " + j.client_name : "");
        }
        return "#" + id;
      });

      const selectedClientPickerLabel = computed(function () {
        const id = candidateForm.target_client_id;
        if (id === "" || id == null) return "";
        const c = clientOptions.value.find(function (x) {
          return Number(x.id) === Number(id);
        });
        return c ? c.name || "#" + id : "#" + id;
      });

      function displayCandidateContact(c) {
        return (c.email_wechat || c.email || c.wechat || "—").trim() || "—";
      }

      function displayTargetJob(c) {
        return (c.target_job_title || "").trim() || (c.target_job_id ? "#" + c.target_job_id : "—");
      }

      function displayTargetClient(c) {
        return (c.target_client_name || "").trim() || (c.target_client_id ? "#" + c.target_client_id : "—");
      }

      function displaySalary(value) {
        const formatted = formatSalaryThousands(value);
        return formatted || "—";
      }

      function formatCandidateSalaryField(field) {
        candidateForm[field] = formatSalaryThousands(candidateForm[field]);
      }

      function formatReportSalaryField(field) {
        reportForm[field] = formatSalaryThousands(reportForm[field]);
      }

      function onJobSalaryCapInput() {
        jobForm.salary_cap = stripJobSalaryCapInput(jobForm.salary_cap).slice(0, 5);
      }

      function formatJobSalaryCapField() {
        jobForm.salary_cap = formatJobSalaryCapDisplay(jobForm.salary_cap);
      }

      function displayJobSalaryCap(value) {
        const formatted = formatJobSalaryCapDisplay(value);
        return formatted || "—";
      }

      function validateJobSalaryCap() {
        const digits = stripJobSalaryCapInput(jobForm.salary_cap);
        if (!digits) return "";
        const n = Number(digits);
        if (!jobSalaryCapInRange(n)) return null;
        return String(n);
      }

      function resumeViewUrl(c) {
        if (!c || c.resume_id == null || c.resume_id === "") return "#";
        return "/api/rms/resumes/" + c.resume_id + "/view";
      }

      function resumeDownloadUrl(c) {
        if (!c || c.resume_id == null || c.resume_id === "") return "#";
        return "/api/rms/resumes/" + c.resume_id + "/download";
      }

      function resumeCanView(c) {
        const name = String((c && c.resume_file_name) || "").toLowerCase();
        return /\.(pdf|txt|rtf)$/.test(name);
      }

      function selectJobPicker(job) {
        candidateForm.target_job_id = job.id;
        jobPickerQuery.value = job.title || "";
        jobPickerOpen.value = false;
      }

      function selectClientPicker(client) {
        candidateForm.target_client_id = client.id;
        clientPickerQuery.value = client.name || "";
        clientPickerOpen.value = false;
      }

      function onCandidateResumeChange(ev) {
        const f = ev.target && ev.target.files && ev.target.files[0];
        candidateResumeFile.value = f || null;
      }

      async function uploadCandidateResume(candidateId, file) {
        const fd = new FormData();
        fd.append("file", file);
        const headers = authHeaders();
        let resp;
        try {
          resp = await fetch("/api/rms/candidates/" + candidateId + "/resume", {
            method: "POST",
            headers: headers,
            body: fd,
            credentials: "same-origin",
          });
        } catch (e) {
          const msg = e && e.message ? e.message : String(e);
          return { ok: false, status: 0, message: "简历上传失败（" + msg + "）" };
        }
        let payload = null;
        const ct = resp.headers.get("content-type") || "";
        if (ct.indexOf("application/json") !== -1) {
          try {
            payload = await resp.json();
          } catch (e2) {
            payload = null;
          }
        }
        if (!resp.ok) {
          const detail = payload && payload.detail != null ? payload.detail : "";
          return { ok: false, status: resp.status, message: messageForStatus(resp.status, detail) };
        }
        return { ok: true, data: payload };
      }

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
          : "crm-op-btn-edit";
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
            getJobs: function () { return jobsState.items; },
            getCandidates: function () { return candidatesState.items; },
            getUsers: function () { return userOptions.value; },
            clientNameById: clientNameById,
            labelJob: labelJob,
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
          if (data.user && data.user.id != null) {
            jobForm.owner_user_id = data.user.id;
          }
        } catch (e) {
          /* page still usable; owner_user_id manual */
        }
      }

      function scheduleJobsTableColumnFit() {
        nextTick(function () {
          var table = document.querySelector("table[data-table-id=\"rms-jobs\"]");
          if (!table) return;
          if (typeof window.crmEnsureRmsJobsTableColumns === "function") {
            window.crmEnsureRmsJobsTableColumns(table);
          } else if (typeof window.crmScheduleTableColumnResize === "function") {
            delete table.dataset.colContentFit;
            window.crmScheduleTableColumnResize(table.closest("#rms-app") || document);
          }
        });
      }

      const RMS_LIST_TABLE_IDS = {
        candidates: "rms-candidates",
        applications: "rms-applications",
        deliveryReview: "rms-delivery-review",
        pipeline: "rms-pipeline",
      };

      function scheduleCandidatesTableColumnFit() {
        nextTick(function () {
          requestAnimationFrame(function () {
            var tableId = RMS_LIST_TABLE_IDS[activeTab.value];
            if (!tableId) return;
            var table = document.querySelector('table[data-table-id="' + tableId + '"]');
            if (!table) return;
            if (typeof window.crmFitTableColumnsToContent === "function") {
              window.crmFitTableColumnsToContent(table);
            } else if (typeof window.crmInitTableColumnResize === "function") {
              window.crmInitTableColumnResize(table);
            } else if (typeof window.crmScheduleTableColumnResize === "function") {
              delete table.dataset.colContentFit;
              window.crmScheduleTableColumnResize(table.closest("#rms-app") || document);
            }
          });
        });
      }

      async function loadJobs() {
        jobsState.loading = true;
        jobsState.error = "";
        try {
          const r = await rmsRequest("GET", "/api/rms/jobs");
          if (!r.ok) {
            jobsState.items = [];
            jobsState.error = r.message;
            return;
          }
          jobsState.items = Array.isArray(r.data) ? r.data : [];
        } finally {
          jobsState.loading = false;
          scheduleJobsTableColumnFit();
        }
      }

      async function loadCandidates() {
        candidatesState.loading = true;
        candidatesState.error = "";
        try {
          const r = await rmsRequest("GET", "/api/rms/candidates");
          if (!r.ok) {
            candidatesState.items = [];
            candidatesState.error = r.message;
            return;
          }
          candidatesState.items = Array.isArray(r.data) ? r.data : [];
        } finally {
          candidatesState.loading = false;
          scheduleCandidatesTableColumnFit();
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

      function userOptionLabel(u) {
        const dn = (u.display_name || "").trim();
        const un = (u.username || "").trim();
        if (dn && un) return dn + " · " + un;
        return dn || un || String(u.id);
      }

      function resetJobForm() {
        jobForm.client_id = "";
        jobForm.title = "";
        jobForm.priority = "medium";
        jobForm.status = "open";
        jobForm.job_description = "";
        jobForm.headcount = 1;
        jobForm.salary_cap = "";
        jobForm.years_required = "";
        jobForm.location = "";
        jobForm.education = "";
        jobForm.overtime_travel = "";
        jobForm.department = "";
        jobForm.interviewer = "";
        jobForm.sales_owner_user_id = "";
        jobForm.delivery_owner_user_id = "";
        jobForm.note = "";
        jobForm.sales_owner_label = "";
        jobForm.delivery_owner_label = "";
        jobForm.owner_user_id =
          me.value.user && me.value.user.id != null ? me.value.user.id : "";
      }

      function fillJobFormFromRow(j) {
        jobForm.client_id = j.client_id != null ? j.client_id : "";
        jobForm.title = j.title || "";
        jobForm.priority = j.priority || "medium";
        jobForm.status = j.status || "open";
        jobForm.job_description = j.job_description || "";
        jobForm.headcount = j.headcount != null ? j.headcount : 1;
        jobForm.salary_cap = formatJobSalaryCapDisplay(j.salary_cap || "");
        jobForm.years_required = j.years_required || "";
        jobForm.location = j.location || "";
        jobForm.education = j.education || "";
        jobForm.overtime_travel = j.overtime_travel || "";
        jobForm.department = j.department || "";
        jobForm.interviewer = j.interviewer || "";
        jobForm.note = j.note || "";
        jobForm.owner_user_id = j.owner_user_id != null ? j.owner_user_id : "";
        jobForm.sales_owner_user_id = j.sales_owner_user_id != null ? j.sales_owner_user_id : "";
        jobForm.delivery_owner_user_id =
          j.delivery_owner_user_id != null ? j.delivery_owner_user_id : "";
        jobForm.sales_owner_label = j.sales_owner_label || "";
        jobForm.delivery_owner_label = j.delivery_owner_label || "";
      }

      function buildJobBody() {
        return {
          client_id: Number(jobForm.client_id),
          title: jobForm.title || "",
          priority: jobForm.priority || "medium",
          status: jobForm.status || "open",
          job_description: jobForm.job_description || "",
          headcount: Number(jobForm.headcount) || 1,
          salary_cap: validateJobSalaryCap() || "",
          years_required: jobForm.years_required || "",
          location: jobForm.location || "",
          education: jobForm.education || "",
          overtime_travel: jobForm.overtime_travel || "",
          department: jobForm.department || "",
          interviewer: jobForm.interviewer || "",
          note: jobForm.note || "",
          owner_user_id: Number(jobForm.owner_user_id),
        };
      }

      function resetJobFilter() {
        jobFilter.title = "";
        jobFilter.client_id = "";
        jobFilter.priority = "";
        jobFilter.status = "";
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

      function resetCandidateFilter() {
        candidateFilter.name = "";
        candidateFilter.client_id = "";
        candidateFilter.job_id = "";
        candidateFilter.city = "";
        candidateFilter.source = "";
        candidateFilter.education_level = "";
        candidateFilter.date_from = "";
        candidateFilter.date_to = "";
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

      async function openStatusHistoryModal(app) {
        if (!app || app.id == null) return;
        statusHistoryModal.value = app;
        statusHistoryLoading.value = true;
        statusHistoryError.value = "";
        statusHistoryItems.value = [];
        const r = await rmsRequest("GET", "/api/rms/applications/" + app.id + "/status-history");
        statusHistoryLoading.value = false;
        if (!r.ok) {
          statusHistoryError.value = r.message;
          return;
        }
        statusHistoryItems.value = Array.isArray(r.data) ? r.data : [];
      }

      function closeStatusHistoryModal() {
        statusHistoryModal.value = null;
        statusHistoryLoading.value = false;
        statusHistoryError.value = "";
        statusHistoryItems.value = [];
      }

      function scrollJobsToTop() {
        const el = jobsScrollWrap.value;
        if (el) el.scrollTop = 0;
      }

      async function loadJobFormOptions() {
        jobFormOptionsError.value = "";
        clientOptions.value = [];
        userOptions.value = [];
        const clientsR = await rmsRequest("GET", "/api/clients");
        if (!clientsR.ok) {
          jobFormOptionsError.value =
            "无法加载客户列表：" + clientsR.message + "（需 crm.clients.read）";
        } else {
          clientOptions.value = Array.isArray(clientsR.data) ? clientsR.data : [];
        }
        const assignR = await rmsRequest("GET", "/api/clients/assign-options");
        if (!assignR.ok) {
          jobFormOptionsError.value =
            (jobFormOptionsError.value ? jobFormOptionsError.value + "；" : "") +
            "无法加载用户列表：" + assignR.message;
        } else {
          userOptions.value =
            assignR.data && Array.isArray(assignR.data.users) ? assignR.data.users : [];
        }
      }

      async function onJobClientChange() {
        const cid = jobForm.client_id;
        if (cid === "" || cid == null) return;
        const r = await rmsRequest("GET", "/api/clients/" + cid);
        if (!r.ok) return;
        const c = r.data || {};
        if (c.owner_user_id != null && c.owner_user_id !== "") {
          jobForm.sales_owner_user_id = c.owner_user_id;
        }
        if (c.delivery_owner_user_id != null && c.delivery_owner_user_id !== "") {
          jobForm.delivery_owner_user_id = c.delivery_owner_user_id;
        }
        if (c.recruitment_owner_user_id != null && c.recruitment_owner_user_id !== "") {
          jobForm.owner_user_id = c.recruitment_owner_user_id;
        }
      }

      async function openJobModal() {
        modalError.value = "";
        jobModalMode.value = "create";
        editingJobId.value = null;
        modal.value = "job";
        await loadJobFormOptions();
      }

      async function openJobEdit(row) {
        modalError.value = "";
        jobModalMode.value = "edit";
        editingJobId.value = row.id;
        modal.value = "job";
        resetJobForm();
        fillJobFormFromRow(row);
        await loadJobFormOptions();
      }

      function removeJob(row) {
        toast("岗位删除功能暂未开放", true);
      }

      function resetCandidateForm() {
        candidateForm.name = "";
        candidateForm.age = "";
        candidateForm.work_years = "";
        candidateForm.phone = "";
        candidateForm.email_wechat = "";
        candidateForm.target_job_id = "";
        candidateForm.target_client_id = "";
        candidateForm.city = "";
        candidateForm.current_salary = "";
        candidateForm.expected_salary = "";
        candidateForm.available_date = "";
        candidateForm.education_level = "";
        candidateForm.school = "";
        candidateForm.major = "";
        candidateForm.gender = "";
        candidateForm.marital_status = "";
        candidateForm.source = "";
        candidateResumeFile.value = null;
        editingCandidateResumeName.value = "";
        jobPickerQuery.value = "";
        clientPickerQuery.value = "";
        jobPickerOpen.value = false;
        clientPickerOpen.value = false;
      }

      function fillCandidateFormFromRow(c) {
        candidateForm.name = c.name || "";
        candidateForm.age = c.age || "";
        candidateForm.work_years = c.work_years || "";
        candidateForm.phone = c.phone || "";
        candidateForm.email_wechat = (c.email_wechat || c.email || c.wechat || "").trim();
        candidateForm.target_job_id = c.target_job_id != null ? c.target_job_id : "";
        candidateForm.target_client_id = c.target_client_id != null ? c.target_client_id : "";
        candidateForm.city = c.city || "";
        candidateForm.current_salary = formatSalaryThousands(c.current_salary || "");
        candidateForm.expected_salary = formatSalaryThousands(c.expected_salary || "");
        candidateForm.available_date = c.available_date || "";
        candidateForm.education_level = c.education_level || "";
        candidateForm.school = c.school || "";
        candidateForm.major = c.major || "";
        candidateForm.gender = c.gender || "";
        candidateForm.marital_status = c.marital_status || "";
        candidateForm.source = c.source || "";
        jobPickerQuery.value = displayTargetJob(c) === "—" ? "" : displayTargetJob(c);
        clientPickerQuery.value = displayTargetClient(c) === "—" ? "" : displayTargetClient(c);
        editingCandidateResumeName.value = (c.resume_file_name || "").trim();
      }

      function buildCandidateBody() {
        formatCandidateSalaryField("current_salary");
        formatCandidateSalaryField("expected_salary");
        return {
          name: candidateForm.name.trim(),
          age: (candidateForm.age || "").trim(),
          work_years: (candidateForm.work_years || "").trim(),
          phone: (candidateForm.phone || "").trim(),
          email_wechat: (candidateForm.email_wechat || "").trim(),
          target_job_id: Number(candidateForm.target_job_id),
          city: (candidateForm.city || "").trim(),
          current_salary: stripSalaryCommas(candidateForm.current_salary),
          expected_salary: stripSalaryCommas(candidateForm.expected_salary),
          available_date: candidateForm.available_date || "",
          education_level: candidateForm.education_level || "",
          school: (candidateForm.school || "").trim(),
          major: (candidateForm.major || "").trim(),
          gender: candidateForm.gender || "",
          marital_status: candidateForm.marital_status || "",
          source: candidateForm.source || "",
          target_client_id:
            candidateForm.target_client_id !== "" && candidateForm.target_client_id != null
              ? Number(candidateForm.target_client_id)
              : undefined,
        };
      }

      async function openCandidateModal() {
        modalError.value = "";
        candidateModalMode.value = "create";
        editingCandidateId.value = null;
        resetCandidateForm();
        modal.value = "candidate";
        if (!clientOptions.value.length) {
          await loadJobFormOptions();
        }
      }

      async function openCandidateEdit(row) {
        modalError.value = "";
        candidateModalMode.value = "edit";
        editingCandidateId.value = row.id;
        resetCandidateForm();
        fillCandidateFormFromRow(row);
        modal.value = "candidate";
        if (!clientOptions.value.length) {
          await loadJobFormOptions();
        }
      }

      async function removeCandidate(row) {
        const r = await rmsRequest("DELETE", "/api/rms/candidates/" + row.id);
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        toast("已删除", false);
        await loadCandidates();
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

      function reportResumeFileExt(file) {
        const name = (file && file.name) || "";
        const dot = name.lastIndexOf(".");
        return dot >= 0 ? name.slice(dot).toLowerCase() : "";
      }

      function revokeReportResumePdfPreview() {
        if (reportResumePdfPreviewUrl.value) {
          URL.revokeObjectURL(reportResumePdfPreviewUrl.value);
          reportResumePdfPreviewUrl.value = "";
        }
      }

      function clearReportFileMainPreview() {
        revokeReportResumePdfPreview();
        reportResumeTextPreview.value = "";
        reportResumeTextPreviewTruncated.value = false;
      }

      function clearReportRecognizedText() {
        reportResumePreviewText.value = "";
        reportResumePreviewError.value = "";
        reportResumePreviewWarning.value = "";
        reportResumePreviewRawText.value = "";
        reportResumePreviewLength.value = 0;
        reportResumePreviewRawLength.value = 0;
      }

      function setupReportFileMainPreview(file) {
        clearReportFileMainPreview();
        if (!file) return;
        const ext = reportResumeFileExt(file);
        if (ext === ".pdf") {
          reportResumePdfPreviewUrl.value = URL.createObjectURL(file);
          return;
        }
        if (ext === ".txt" || ext === ".rtf") {
          const reader = new FileReader();
          reader.onload = function () {
            const full = String(reader.result || "");
            reportResumeTextPreviewTruncated.value = full.length > REPORT_LOCAL_TEXT_PREVIEW_MAX;
            reportResumeTextPreview.value = full.slice(0, REPORT_LOCAL_TEXT_PREVIEW_MAX);
          };
          reader.onerror = function () {
            reportResumeTextPreview.value = "";
            reportResumeTextPreviewTruncated.value = false;
          };
          reader.readAsText(file);
        }
      }

      function resetReportDraftUi() {
        reportResumeDraftStatus.value = "idle";
        reportResumeDraftError.value = "";
        reportResumeDragging.value = false;
        clearReportFileMainPreview();
        clearReportRecognizedText();
        Object.keys(reportAutoFilledFields).forEach(function (k) {
          delete reportAutoFilledFields[k];
        });
      }

      function formatReportFileSize(bytes) {
        return CandidateReport.formatFileSize
          ? CandidateReport.formatFileSize(bytes)
          : String(bytes || 0);
      }

      function openCandidateReport(job) {
        reportError.value = "";
        reportSaving.value = false;
        reportResumeFile.value = null;
        resetReportDraftUi();
        Object.assign(
          reportForm,
          CandidateReport.emptyReportForm ? CandidateReport.emptyReportForm() : {}
        );
        if (CandidateReport.fillFromJob) {
          CandidateReport.fillFromJob(reportForm, job, clientNameById);
        }
        viewMode.value = "candidateReport";
        installReportPageDragGuard();
      }

      function closeCandidateReport() {
        removeReportPageDragGuard();
        viewMode.value = null;
        reportError.value = "";
        clearReportResumeFile();
      }

      function clearReportResumeFile() {
        if (CandidateReport.clearAutoFilledFields) {
          CandidateReport.clearAutoFilledFields(reportForm, reportAutoFilledFields);
        }
        reportResumeFile.value = null;
        reportResumeDraftStatus.value = "idle";
        reportResumeDraftError.value = "";
        reportResumeDragging.value = false;
        clearReportFileMainPreview();
        clearReportRecognizedText();
        if (reportResumeInput.value) reportResumeInput.value.value = "";
      }

      async function parseReportResumeDraft(file) {
        if (!file || !CandidateReport.parseCandidateReportDraft) return;
        reportResumeDraftStatus.value = "parsing";
        reportResumeDraftError.value = "";
        clearReportRecognizedText();
        if (CandidateReport.clearAutoFilledFields) {
          CandidateReport.clearAutoFilledFields(reportForm, reportAutoFilledFields);
        }
        const r = await CandidateReport.parseCandidateReportDraft(
          file,
          reportForm.job_id,
          authHeaders,
          function (status, detail) {
            return workflowMessageForStatus(status, detail, "parse-draft");
          }
        );
        if (!r.ok) {
          reportResumeDraftStatus.value = "error";
          reportResumeDraftError.value = r.message;
          reportResumePreviewError.value = r.message;
          return;
        }
        const data = r.data || {};
        const draft = data.draft_fields || {};
        const filled = CandidateReport.applyDraftToForm
          ? CandidateReport.applyDraftToForm(reportForm, draft, reportAutoFilledFields)
          : 0;
        formatReportSalaryField("current_salary");
        formatReportSalaryField("expected_salary");
        const n = CandidateReport.countDraftFields
          ? CandidateReport.countDraftFields(draft)
          : filled;
        if (n > 0 || filled > 0) {
          reportResumeDraftStatus.value = "ok";
        } else {
          reportResumeDraftStatus.value = "empty";
        }
        if (data.message) reportResumeDraftError.value = data.message;
        reportResumePreviewLength.value = Number(data.parsed_text_length) || 0;
        reportResumePreviewRawLength.value = Number(data.parsed_text_raw_length) || 0;
        reportResumePreviewWarning.value = String(data.extract_warning || "").trim();
        const preview = String(data.parsed_text || "").trim();
        const rawPreview = String(data.parsed_text_raw || "").trim();
        if (preview) {
          reportResumePreviewText.value = preview;
          reportResumePreviewError.value = "";
        } else if (data.message) {
          reportResumePreviewText.value = "";
          reportResumePreviewError.value = data.message;
        } else {
          reportResumePreviewText.value = "";
          reportResumePreviewError.value = "";
        }
        reportResumePreviewRawText.value = rawPreview;
        let parseDuplicate = data.duplicate_detected === true;
        if (!parseDuplicate && (reportForm.phone || "").trim()) {
          const dupR = await rmsRequest("POST", "/api/rms/candidates/check-duplicate", {
            name: (reportForm.name || "").trim(),
            phone: (reportForm.phone || "").trim(),
          });
          parseDuplicate = !!(dupR.ok && dupR.data && dupR.data.duplicate_detected === true);
        }
        if (parseDuplicate) {
          await showCandidateDuplicateDialog(CANDIDATE_DUPLICATE_PARSE_HINT);
        }
      }

      function onReportFilePicked(file) {
        if (!file) return;
        revokeReportResumePdfPreview();
        reportResumeFile.value = file;
        setupReportFileMainPreview(file);
        parseReportResumeDraft(file);
      }

      function onReportResumeChange(ev) {
        const f = ev.target && ev.target.files && ev.target.files[0];
        onReportFilePicked(f || null);
      }

      function onReportDrop(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        reportResumeDragging.value = false;
        const f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
        onReportFilePicked(f || null);
      }

      function onReportDragEnter(ev) {
        ev.preventDefault();
        reportResumeDragging.value = true;
      }

      function onReportDragLeave(ev) {
        ev.preventDefault();
        reportResumeDragging.value = false;
      }

      function focusReportField(field) {
        const key = String(field || "").trim();
        if (!key) return;
        nextTick(function () {
          const root = document.querySelector("[data-rms-report-form]");
          const host = root
            ? root.querySelector('[data-rms-report-field="' + key + '"]')
            : document.querySelector('[data-rms-report-field="' + key + '"]');
          if (!host) return;
          const focusable =
            host.matches && host.matches("input, select, textarea")
              ? host
              : host.querySelector
                ? host.querySelector("input, select, textarea")
                : null;
          if (host.scrollIntoView) {
            host.scrollIntoView({ block: "center", behavior: "smooth" });
          }
          if (focusable && focusable.focus) {
            focusable.focus({ preventScroll: true });
          }
        });
      }

      function focusCandidateModalField(field) {
        const key = String(field || "").trim();
        if (!key) return;
        const mapped = key === "location" ? "city" : key;
        nextTick(function () {
          const root = document.querySelector("[data-rms-candidate-form]");
          const host = root
            ? root.querySelector('[data-rms-candidate-field="' + mapped + '"]')
            : document.querySelector('[data-rms-candidate-field="' + mapped + '"]');
          if (!host) return;
          const focusable =
            host.matches && host.matches("input, select, textarea")
              ? host
              : host.querySelector
                ? host.querySelector("input, select, textarea")
                : null;
          if (host.scrollIntoView) {
            host.scrollIntoView({ block: "center", behavior: "smooth" });
          }
          if (focusable && focusable.focus) {
            focusable.focus({ preventScroll: true });
          }
        });
      }

      function resolveValidationField(message, field) {
        if (field) return field;
        return CandidateReport.fieldKeyForValidationMessage
          ? CandidateReport.fieldKeyForValidationMessage(message)
          : "";
      }

      function setReportError(message, field) {
        reportError.value = showValidationPrompt(message);
        focusReportField(resolveValidationField(message, field));
      }

      function setModalError(message, field) {
        modalError.value = showValidationPrompt(message);
        focusCandidateModalField(resolveValidationField(message, field));
      }

      async function submitCandidateReport() {
        reportSaving.value = true;
        reportError.value = "";
        try {
          const reportValidation = CandidateReport.validateReportForm
            ? CandidateReport.validateReportForm(reportForm)
            : { ok: true, message: "" };
          if (!reportValidation.ok) {
            setReportError(reportValidation.message, reportValidation.field);
            return;
          }
          const r = await CandidateReport.submitCandidateReport(
            reportForm,
            reportResumeFile.value,
            authHeaders,
            function (status, detail) {
              return workflowMessageForStatus(status, detail, "candidate-report");
            }
          );
          if (!r.ok) {
            if (isCandidateDuplicateError(r)) {
              await showCandidateDuplicateDialog();
              return;
            }
            setReportError(userFacingRmsError(r));
            return;
          }
          toast("推荐已提交", false);
          closeCandidateReport();
          await Promise.all([loadApplications(), loadCandidates(), loadDeliveryReview()]);
        } catch (err) {
          const msg = err && err.message ? err.message : String(err);
          setReportError("提交失败：" + msg);
        } finally {
          reportSaving.value = false;
        }
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
        jobModalMode.value = "create";
        editingJobId.value = null;
        candidateModalMode.value = "create";
        editingCandidateId.value = null;
        editingCandidateResumeName.value = "";
      }

      async function submitModal() {
        modalSaving.value = true;
        modalError.value = "";
        let r;
        try {
        if (modal.value === "job") {
          formatJobSalaryCapField();
          const salaryCap = validateJobSalaryCap();
          if (salaryCap === null) {
            modalError.value =
              "薪资帽须为 " +
              JOB_SALARY_CAP_MIN.toLocaleString("zh-CN") +
              "–" +
              JOB_SALARY_CAP_MAX.toLocaleString("zh-CN") +
              " 的整数";
            return;
          }
          const body = buildJobBody();
          if (jobModalMode.value === "create") {
            if (jobForm.sales_owner_user_id !== "" && jobForm.sales_owner_user_id != null) {
              body.sales_owner_user_id = Number(jobForm.sales_owner_user_id);
            }
            if (jobForm.delivery_owner_user_id !== "" && jobForm.delivery_owner_user_id != null) {
              body.delivery_owner_user_id = Number(jobForm.delivery_owner_user_id);
            }
            r = await rmsRequest("POST", "/api/rms/jobs", body);
          } else if (jobModalMode.value === "edit") {
            r = await rmsRequest("PATCH", "/api/rms/jobs/" + editingJobId.value, body);
          } else {
            return;
          }
          if (r.ok) await loadJobs();
        } else if (modal.value === "candidate") {
          const phone = (candidateForm.phone || "").trim();
          if (candidateModalMode.value === "create") {
            const createValidation = CandidateReport.validateCandidateCreateForm
              ? CandidateReport.validateCandidateCreateForm(candidateForm)
              : { ok: true, message: "" };
            if (!createValidation.ok) {
              setModalError(createValidation.message, createValidation.field);
              return;
            }
          } else {
            if (!(candidateForm.name || "").trim()) {
              setModalError("请填写姓名", "name");
              return;
            }
            if (!PHONE_RE.test(phone)) {
              setModalError("手机号须为11位数字且以1开头", "phone");
              return;
            }
            if (candidateForm.target_job_id === "" || candidateForm.target_job_id == null) {
              setModalError("请选择应聘岗位（须为 open 状态）", "target_job_id");
              return;
            }
          }
          const jobId = Number(candidateForm.target_job_id);
          const pickedJob = openJobs.value.find(function (j) {
            return Number(j.id) === jobId;
          });
          if (!pickedJob) {
            setModalError("应聘岗位不存在或不是 open 状态", "target_job_id");
            return;
          }
          const body = buildCandidateBody();
          body.phone = phone;
          if (candidateModalMode.value === "edit") {
            r = await rmsRequest("PATCH", "/api/rms/candidates/" + editingCandidateId.value, body);
            if (r.ok && candidateResumeFile.value) {
              const up = await uploadCandidateResume(editingCandidateId.value, candidateResumeFile.value);
              if (!up.ok) {
                modalError.value = up.message;
                await loadCandidates();
                return;
              }
            }
          } else {
            r = await rmsRequest("POST", "/api/rms/candidates", body);
            if (r.ok && candidateResumeFile.value && r.data && r.data.id) {
              const up = await uploadCandidateResume(r.data.id, candidateResumeFile.value);
              if (!up.ok) {
                modalError.value = up.message;
                await loadCandidates();
                return;
              }
            }
          }
          if (r.ok) await loadCandidates();
        } else {
          return;
        }
        if (!r.ok) {
          if (isCandidateDuplicateError(r)) {
            await showCandidateDuplicateDialog();
            return;
          }
          setModalError(userFacingRmsError(r));
          return;
        }
        toast("保存成功", false);
        if (modal.value === "job" && jobModalMode.value === "create") {
          resetJobForm();
        }
        closeModal();
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
          loadJobs(),
          loadCandidates(),
          loadApplications(),
          loadDeliveryReview(),
          loadJobFormOptions(),
        ]);
        if (activeTab.value === "candidates") {
          scheduleCandidatesTableColumnFit();
        }
      });

      return {
        activeTab,
        viewMode,
        jobsState,
        candidatesState,
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
        reportForm,
        reportSaving,
        reportError,
        reportResumeFile,
        reportResumeInput,
        reportResumeDraftStatus,
        reportResumeDraftError,
        reportResumePdfPreviewUrl,
        reportResumeTextPreview,
        reportResumeTextPreviewTruncated,
        reportResumePreviewText,
        reportResumePreviewError,
        reportResumePreviewWarning,
        reportResumePreviewRawText,
        reportResumePreviewLength,
        reportResumePreviewRawLength,
        reportShowRawExtractDebug,
        reportResumeDragging,
        formatReportFileSize,
        canWriteJobs,
        canWriteCandidates,
        canWriteApplications,
        modal,
        modalTitle,
        modalError,
        modalSaving,
        jobModalMode,
        candidateModalMode,
        editingCandidateId,
        editingCandidateResumeName,
        jobModalReadonly,
        modalCloseLabel,
        modalShowSave,
        jobFilterPanelExpanded,
        jobFilter,
        filteredJobs,
        pipelineFilter,
        pipelineStatusDropdownOpen,
        pipelineStatusDraft,
        pipelineStatusFilterSummary,
        togglePipelineStatusDropdown,
        togglePipelineStatusDraft,
        clearPipelineStatusDraft,
        applyPipelineStatusFilter,
        filteredPipelineApplications,
        candidateFilter,
        filteredCandidates,
        progressOptions,
        progressOptionsForCorrection,
        openCorrectionPickerModal,
        openProgressConfirmModal,
        submitProgressConfirm,
        jobsScrollWrap,
        candidatesScrollWrap,
        clientOptions,
        userOptions,
        jobFormOptionsError,
        jobForm,
        priorityOptions: PRIORITY_OPTIONS,
        statusOptions: STATUS_OPTIONS,
        candidateForm,
        candidateResumeFile,
        educationOptions: EDUCATION_OPTIONS,
        genderOptions: GENDER_OPTIONS,
        sourceOptions: SOURCE_OPTIONS,
        maritalOptions: MARITAL_OPTIONS,
        openJobs,
        jobPickerQuery,
        jobPickerOpen,
        clientPickerQuery,
        clientPickerOpen,
        filteredJobPickerOptions,
        filteredClientPickerOptions,
        selectedJobPickerLabel,
        selectedClientPickerLabel,
        displayCandidateContact,
        displayTargetJob,
        displayTargetClient,
        displaySalary,
        displayJobSalaryCap,
        formatCandidateSalaryField,
        formatReportSalaryField,
        onJobSalaryCapInput,
        formatJobSalaryCapField,
        resumeViewUrl,
        resumeDownloadUrl,
        resumeCanView,
        selectJobPicker,
        selectClientPicker,
        onCandidateResumeChange,
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
        onJobClientChange,
        clientNameById,
        priorityLabel,
        statusLabel,
        resetJobFilter,
        resetPipelineFilter,
        resetCandidateFilter,
        scrollJobsToTop,
        scheduleCandidatesTableColumnFit,
        labelJob,
        labelCandidate,
        openJobModal,
        openJobEdit,
        removeJob,
        openCandidateReport,
        closeCandidateReport,
        onReportResumeChange,
        onReportDrop,
        onReportDragEnter,
        onReportDragLeave,
        clearReportResumeFile,
        submitCandidateReport,
        openDeliveryReviewModal,
        closeDeliveryReviewModal,
        openDeliveryReviewFailModal,
        submitDeliveryReview,
        openCandidateModal,
        openCandidateEdit,
        removeCandidate,
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
