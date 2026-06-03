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
    return "请求失败 (" + status + ")" + (d ? "：" + d : "");
  }

  async function rmsRequest(method, url, body) {
    const headers = Object.assign({}, authHeaders());
    const opts = { method: method, headers: headers, credentials: "same-origin" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opts);
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

  const { createApp, ref, reactive, computed, onMounted } = Vue;

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

      const clientOptions = ref([]);
      const userOptions = ref([]);
      const jobFormOptionsError = ref("");

      const jobForm = reactive({
        client_id: "",
        title: "",
        job_description: "",
        sales_owner_user_id: "",
        owner_user_id: "",
        delivery_owner_user_id: "",
      });
      const candidateForm = reactive({
        name: "",
        phone: "",
        email: "",
        wechat: "",
        city: "",
        source: "",
      });
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
        if (modal.value === "job") return "新建岗位";
        if (modal.value === "candidate") return "新建候选人";
        if (modal.value === "application") return "新建推荐";
        return "";
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

      function labelJob(jobId) {
        const title = jobTitleById.value[jobId];
        return title ? title : "#" + jobId;
      }

      function labelCandidate(candidateId) {
        const name = candidateNameById.value[candidateId];
        return name ? name : "#" + candidateId;
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

      async function loadJobs() {
        jobsState.loading = true;
        jobsState.error = "";
        const r = await rmsRequest("GET", "/api/rms/jobs");
        jobsState.loading = false;
        if (!r.ok) {
          jobsState.items = [];
          jobsState.error = r.message;
          return;
        }
        jobsState.items = Array.isArray(r.data) ? r.data : [];
      }

      async function loadCandidates() {
        candidatesState.loading = true;
        candidatesState.error = "";
        const r = await rmsRequest("GET", "/api/rms/candidates");
        candidatesState.loading = false;
        if (!r.ok) {
          candidatesState.items = [];
          candidatesState.error = r.message;
          return;
        }
        candidatesState.items = Array.isArray(r.data) ? r.data : [];
      }

      async function loadApplications() {
        applicationsState.loading = true;
        applicationsState.error = "";
        const r = await rmsRequest("GET", "/api/rms/applications");
        applicationsState.loading = false;
        if (!r.ok) {
          applicationsState.items = [];
          applicationsState.error = r.message;
          return;
        }
        applicationsState.items = Array.isArray(r.data) ? r.data : [];
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
        jobForm.job_description = "";
        jobForm.sales_owner_user_id = "";
        jobForm.delivery_owner_user_id = "";
        jobForm.owner_user_id =
          me.value.user && me.value.user.id != null ? me.value.user.id : "";
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
      }

      async function openJobModal() {
        modalError.value = "";
        modal.value = "job";
        resetJobForm();
        await loadJobFormOptions();
      }

      function openCandidateModal() {
        modalError.value = "";
        modal.value = "candidate";
      }

      function openApplicationModal() {
        modalError.value = "";
        modal.value = "application";
      }

      function closeModal() {
        modal.value = null;
        modalError.value = "";
      }

      async function submitModal() {
        modalSaving.value = true;
        modalError.value = "";
        let r;
        if (modal.value === "job") {
          const body = {
            client_id: Number(jobForm.client_id),
            title: jobForm.title || "",
            job_description: jobForm.job_description || "",
            owner_user_id: Number(jobForm.owner_user_id),
          };
          if (jobForm.sales_owner_user_id !== "" && jobForm.sales_owner_user_id != null) {
            body.sales_owner_user_id = Number(jobForm.sales_owner_user_id);
          }
          if (jobForm.delivery_owner_user_id !== "" && jobForm.delivery_owner_user_id != null) {
            body.delivery_owner_user_id = Number(jobForm.delivery_owner_user_id);
          }
          r = await rmsRequest("POST", "/api/rms/jobs", body);
          if (r.ok) await loadJobs();
        } else if (modal.value === "candidate") {
          r = await rmsRequest("POST", "/api/rms/candidates", {
            name: candidateForm.name || "",
            phone: candidateForm.phone || "",
            email: candidateForm.email || "",
            wechat: candidateForm.wechat || "",
            city: candidateForm.city || "",
            source: candidateForm.source || "",
          });
          if (r.ok) await loadCandidates();
        } else if (modal.value === "application") {
          const body = {
            job_id: Number(applicationForm.job_id),
            candidate_id: Number(applicationForm.candidate_id),
          };
          if (applicationForm.resume_id !== "" && applicationForm.resume_id != null) {
            body.resume_id = Number(applicationForm.resume_id);
          }
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

      onMounted(async function () {
        await loadMe();
        await Promise.all([loadJobs(), loadCandidates(), loadApplications()]);
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
        clientOptions,
        userOptions,
        jobFormOptionsError,
        jobForm,
        candidateForm,
        applicationForm,
        userOptionLabel,
        onJobClientChange,
        labelJob,
        labelCandidate,
        transitionsFor,
        openJobModal,
        openCandidateModal,
        openApplicationModal,
        closeModal,
        submitModal,
        transitionStatus,
      };
    },
  }).mount("#rms-app");
})();
