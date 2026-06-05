/**
 * RMS module page (Phase 2.5 frontend MVP).
 * Requires: Vue 3 CDN, crm-api.js (optional crm-toast.js).
 */
(function () {
  "use strict";

  const Labels = window.RmsApplicationLabels || {};
  const CandidateReport = window.RmsCandidateReport || {};

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
      return { ok: false, status: resp.status, message: messageForStatus(resp.status, detail) };
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
      const reviewModalSaving = ref(false);
      const reviewModalError = ref("");
      const reportSaving = ref(false);
      const reportError = ref("");
      const reportResumeFile = ref(null);
      const reportResumeInput = ref(null);
      const reportResumeDraftStatus = ref("idle");
      const reportResumeDraftError = ref("");
      const reportResumePreviewText = ref("");
      const reportResumePreviewError = ref("");
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

      function receiveLabel(status) {
        return Labels.receiveLabel ? Labels.receiveLabel(status) : status;
      }

      function protectionLabel(status) {
        return Labels.deriveProtectionStatus ? Labels.deriveProtectionStatus(status) : "—";
      }

      function progressTransitionsFor(status) {
        return Labels.progressTransitionsFor ? Labels.progressTransitionsFor(status) : [];
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

      function scheduleCandidatesTableColumnFit() {
        nextTick(function () {
          requestAnimationFrame(function () {
            var table = document.querySelector("table[data-table-id=\"rms-candidates\"]");
            if (!table || activeTab.value !== "candidates") return;
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
        }
      }

      async function loadDeliveryReview() {
        if (deliveryReviewApi) {
          await deliveryReviewApi.loadDeliveryReview(deliveryReviewState);
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
        jobForm.salary_cap = j.salary_cap || "";
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
          salary_cap: jobForm.salary_cap || "",
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
        resetJobForm();
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

      function clearReportResumePreview() {
        reportResumePreviewText.value = "";
        reportResumePreviewError.value = "";
      }

      function resetReportDraftUi() {
        reportResumeDraftStatus.value = "idle";
        reportResumeDraftError.value = "";
        reportResumeDragging.value = false;
        clearReportResumePreview();
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
        clearReportResumePreview();
        if (reportResumeInput.value) reportResumeInput.value.value = "";
      }

      async function parseReportResumeDraft(file) {
        if (!file || !CandidateReport.parseCandidateReportDraft) return;
        reportResumeDraftStatus.value = "parsing";
        reportResumeDraftError.value = "";
        clearReportResumePreview();
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
          reportResumePreviewText.value = "";
          reportResumePreviewError.value = r.message;
          return;
        }
        const data = r.data || {};
        const draft = data.draft_fields || {};
        const filled = CandidateReport.applyDraftToForm
          ? CandidateReport.applyDraftToForm(reportForm, draft, reportAutoFilledFields)
          : 0;
        const n = CandidateReport.countDraftFields
          ? CandidateReport.countDraftFields(draft)
          : filled;
        if (n > 0 || filled > 0) {
          reportResumeDraftStatus.value = "ok";
        } else {
          reportResumeDraftStatus.value = "empty";
        }
        if (data.message) reportResumeDraftError.value = data.message;
        const preview = String(data.parsed_text || "").trim();
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
      }

      function onReportFilePicked(file) {
        if (!file) return;
        reportResumeFile.value = file;
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

      async function submitCandidateReport() {
        reportSaving.value = true;
        reportError.value = "";
        if (!reportForm.job_id) {
          reportError.value = "请选择应聘岗位";
          reportSaving.value = false;
          return;
        }
        if (!(reportForm.recommendation_note || "").trim()) {
          reportError.value = "请填写推荐评语";
          reportSaving.value = false;
          return;
        }
        if (!(reportForm.name || "").trim()) {
          reportError.value = "请填写姓名";
          reportSaving.value = false;
          return;
        }
        const reportPhone = (reportForm.phone || "").trim();
        if (!PHONE_RE.test(reportPhone)) {
          reportError.value = "请填写有效的11位手机号";
          reportSaving.value = false;
          return;
        }
        if (!(reportForm.email_wechat || "").trim()) {
          reportError.value = "请填写邮箱/微信";
          reportSaving.value = false;
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
        reportSaving.value = false;
        if (!r.ok) {
          reportError.value = r.message;
          return;
        }
        toast("推荐已提交", false);
        closeCandidateReport();
        await Promise.all([loadApplications(), loadCandidates(), loadDeliveryReview()]);
      }

      function openDeliveryReviewModal(app) {
        reviewModalError.value = "";
        reviewModalSaving.value = false;
        reviewModal.value = app;
      }

      function closeDeliveryReviewModal() {
        reviewModal.value = null;
        reviewModalError.value = "";
      }

      async function submitDeliveryReview(result) {
        if (!reviewModal.value || !deliveryReviewApi) return;
        reviewModalSaving.value = true;
        reviewModalError.value = "";
        const r = await deliveryReviewApi.submitDeliveryReview(reviewModal.value.id, result);
        reviewModalSaving.value = false;
        if (!r.ok) {
          reviewModalError.value = r.message;
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
        if (modal.value === "job") {
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
            modalSaving.value = false;
            return;
          }
          if (r.ok) await loadJobs();
        } else if (modal.value === "candidate") {
          if (!(candidateForm.name || "").trim()) {
            modalError.value = "请填写姓名";
            modalSaving.value = false;
            return;
          }
          const phone = (candidateForm.phone || "").trim();
          if (!PHONE_RE.test(phone)) {
            modalError.value = "手机号须为11位数字且以1开头";
            modalSaving.value = false;
            return;
          }
          if (candidateForm.target_job_id === "" || candidateForm.target_job_id == null) {
            modalError.value = "请选择应聘岗位（须为 open 状态）";
            modalSaving.value = false;
            return;
          }
          const jobId = Number(candidateForm.target_job_id);
          const pickedJob = openJobs.value.find(function (j) {
            return Number(j.id) === jobId;
          });
          if (!pickedJob) {
            modalError.value = "应聘岗位不存在或不是 open 状态";
            modalSaving.value = false;
            return;
          }
          const body = buildCandidateBody();
          body.phone = phone;
          if (candidateModalMode.value === "edit") {
            r = await rmsRequest("PATCH", "/api/rms/candidates/" + editingCandidateId.value, body);
            if (r.ok && candidateResumeFile.value) {
              const up = await uploadCandidateResume(editingCandidateId.value, candidateResumeFile.value);
              if (!up.ok) {
                modalSaving.value = false;
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
                modalSaving.value = false;
                modalError.value = up.message;
                await loadCandidates();
                return;
              }
            }
          }
          if (r.ok) await loadCandidates();
        } else {
          modalSaving.value = false;
          return;
        }
        modalSaving.value = false;
        if (!r.ok) {
          modalError.value = r.message;
          return;
        }
        toast("保存成功", false);
        closeModal();
      }

      async function transitionProgress(applicationId, toStatus) {
        const r = await rmsRequest("POST", "/api/rms/applications/" + applicationId + "/progress", {
          to_status: toStatus,
        });
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        toast("招聘进展已更新为 " + progressLabel(toStatus), false);
        await loadApplications();
      }

      watch(activeTab, function (tab) {
        if (tab === "candidates") {
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
        reviewModalSaving,
        reviewModalError,
        reportForm,
        reportSaving,
        reportError,
        reportResumeFile,
        reportResumeInput,
        reportResumeDraftStatus,
        reportResumeDraftError,
        reportResumePreviewText,
        reportResumePreviewError,
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
        formatCandidateSalaryField,
        resumeViewUrl,
        resumeDownloadUrl,
        resumeCanView,
        selectJobPicker,
        selectClientPicker,
        onCandidateResumeChange,
        progressLabel,
        receiveLabel,
        protectionLabel,
        progressTransitionsFor,
        appCandidateName,
        appClientName,
        appJobTitle,
        appJobLocation,
        appDeliveryLabel,
        appRecommenderLabel,
        resumeViewUrlById,
        resumeCanViewByName,
        userOptionLabel,
        onJobClientChange,
        clientNameById,
        priorityLabel,
        statusLabel,
        resetJobFilter,
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
        submitDeliveryReview,
        openCandidateModal,
        openCandidateEdit,
        removeCandidate,
        closeModal,
        submitModal,
        transitionProgress,
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
