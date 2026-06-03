/**
 * RMS module page (Phase 2.5 frontend MVP).
 * Requires: Vue 3 CDN, crm-api.js (optional crm-toast.js).
 */
(function () {
  "use strict";

  /** Keep in sync with schemas/rms.py ALLOWED_TRANSITIONS */
  const ALLOWED_TRANSITIONS = {
    recommended: ["screening", "rejected", "withdrawn"],
    screening: ["interview", "rejected", "withdrawn"],
    interview: ["offer", "rejected", "withdrawn"],
    offer: ["hired", "rejected", "withdrawn"],
    hired: [],
    rejected: [],
    withdrawn: [],
  };

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

  const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;

  createApp({
    setup() {
      const activeTab = ref("jobs");
      const me = ref({ user: { id: null }, permissions: [] });

      const jobsState = reactive({ loading: false, items: [], error: "" });
      const candidatesState = reactive({ loading: false, items: [], error: "" });
      const applicationsState = reactive({ loading: false, items: [], error: "" });

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
      const applicationForm = reactive({
        job_id: "",
        candidate_id: "",
        resume_id: "",
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

      const modalTitle = computed(function () {
        if (modal.value === "job") {
          if (jobModalMode.value === "view") return "岗位详情";
          if (jobModalMode.value === "edit") return "修改岗位";
          return "新建岗位";
        }
        if (modal.value === "candidate") {
          return candidateModalMode.value === "edit" ? "修改候选人" : "新建候选人";
        }
        if (modal.value === "application") return "新建推荐";
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

      function transitionsFor(status) {
        return ALLOWED_TRANSITIONS[status] || [];
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

      async function openJobDetail(row) {
        modalError.value = "";
        jobModalMode.value = "view";
        editingJobId.value = row.id;
        modal.value = "job";
        resetJobForm();
        fillJobFormFromRow(row);
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

      function openApplicationModal() {
        modalError.value = "";
        applicationForm.job_id = "";
        applicationForm.candidate_id = "";
        applicationForm.resume_id = "";
        modal.value = "application";
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
        } else if (modal.value === "application") {
          if (applicationForm.job_id === "" || applicationForm.job_id == null) {
            modalError.value = "请选择岗位";
            modalSaving.value = false;
            return;
          }
          if (applicationForm.candidate_id === "" || applicationForm.candidate_id == null) {
            modalError.value = "请选择或填写候选人";
            modalSaving.value = false;
            return;
          }
          const body = {
            job_id: Number(applicationForm.job_id),
            candidate_id: Number(applicationForm.candidate_id),
          };
          r = await rmsRequest("POST", "/api/rms/applications", body);
          if (r.ok) await loadApplications();
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

      async function transitionStatus(applicationId, toStatus) {
        const r = await rmsRequest("POST", "/api/rms/applications/" + applicationId + "/status", {
          to_status: toStatus,
          reason: "",
          note: "",
        });
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        toast("状态已更新为 " + toStatus, false);
        await loadApplications();
      }

      watch(activeTab, function (tab) {
        if (tab === "candidates") {
          scheduleCandidatesTableColumnFit();
        }
      });

      onMounted(async function () {
        await Promise.all([
          loadMe(),
          loadJobs(),
          loadCandidates(),
          loadApplications(),
          loadJobFormOptions(),
        ]);
        if (activeTab.value === "candidates") {
          scheduleCandidatesTableColumnFit();
        }
      });

      return {
        activeTab,
        jobsState,
        candidatesState,
        applicationsState,
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
        applicationForm,
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
        transitionsFor,
        openJobModal,
        openJobDetail,
        openJobEdit,
        removeJob,
        openCandidateModal,
        openCandidateEdit,
        removeCandidate,
        openApplicationModal,
        closeModal,
        submitModal,
        transitionStatus,
      };
    },
  }).mount("#rms-app");
})();
