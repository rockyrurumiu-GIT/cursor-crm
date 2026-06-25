/**
 * RMS jobs tab + job modal (Phase R1 split).
 */
(function (global) {
  "use strict";

  var Core = global.CrmRmsCore || {};

  var PRIORITY_OPTIONS = [
    { value: "high", label: "高" },
    { value: "medium", label: "中" },
    { value: "low", label: "低" },
  ];

  var STATUS_OPTIONS = [
    { value: "open", label: "open" },
    { value: "closed", label: "closed" },
    { value: "freeze", label: "freeze" },
  ];

  var PRIORITY_LABELS = { high: "高", medium: "中", low: "低" };
  var STATUS_LABELS = { open: "open", closed: "closed", freeze: "freeze" };

  function createJobsState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var watch = deps.watch;
    var nextTick = deps.nextTick;
    var modal = deps.modal;
    var modalError = deps.modalError;
    var modalSaving = deps.modalSaving;
    var me = deps.me;
    var toast = deps.toast;

    var rmsRequest = Core.rmsRequest;
    var stripJobSalaryCapInput = Core.stripJobSalaryCapInput;
    var jobSalaryCapInRange = Core.jobSalaryCapInRange;
    var formatJobSalaryCapDisplay = Core.formatJobSalaryCapDisplay;
    var JOB_SALARY_CAP_MIN = Core.JOB_SALARY_CAP_MIN;
    var JOB_SALARY_CAP_MAX = Core.JOB_SALARY_CAP_MAX;

    var jobsState = reactive({ loading: false, items: [], error: "" });
    var jobFilterPanelExpanded = ref(false);
    var jobsScrollWrap = ref(null);
    var jobFilter = reactive({
      title: "",
      client_id: "",
      priority: "",
      status: "",
    });
    var jobModalMode = ref("create");
    var editingJobId = ref(null);
    var jobDetailOpen = ref(false);
    var jobDetailRow = ref(null);
    var clientOptions = ref([]);
    var userOptions = ref([]);
    var jobFormOptionsError = ref("");
    var jobForm = reactive({
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

    var jobModalTitle = computed(function () {
      if (jobModalMode.value === "view") return "岗位详情";
      if (jobModalMode.value === "edit") return "修改岗位";
      return "新建岗位";
    });

    var jobModalReadonly = computed(function () {
      return modal.value === "job" && jobModalMode.value === "view";
    });

    var jobModalShowSave = computed(function () {
      if (modal.value !== "job") return false;
      return !jobModalReadonly.value;
    });

    var filteredJobs = computed(function () {
      var rows = jobsState.items.slice();
      var title = (jobFilter.title || "").trim().toLowerCase();
      if (title) {
        rows = rows.filter(function (j) {
          return String(j.title || "").toLowerCase().indexOf(title) !== -1;
        });
      }
      if (jobFilter.client_id !== "" && jobFilter.client_id != null) {
        var cid = Number(jobFilter.client_id);
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

    var rmsPageSize = Core.RMS_LIST_PAGE_SIZE || 8;

    var jobsPagination = Core.createListPagination
      ? Core.createListPagination({
          ref: ref,
          computed: computed,
          watch: watch,
          filteredRows: filteredJobs,
          prefix: "jobs",
          pageSize: rmsPageSize,
        })
      : {
          pagedRows: filteredJobs,
          jobsCurrentPage: ref(1),
          jobsTotalPages: computed(function () { return 1; }),
          jobsPageNumbers: computed(function () { return [1]; }),
          jobsGoPage: function () {},
          pageSize: Core.RMS_LIST_PAGE_SIZE || 8,
        };

    var jobTitleById = computed(function () {
      var m = {};
      jobsState.items.forEach(function (j) {
        m[j.id] = j.title || "";
      });
      return m;
    });

    var openJobs = computed(function () {
      return jobsState.items.filter(function (j) {
        return (j.status || "") === "open";
      });
    });

    function priorityLabel(value) {
      return PRIORITY_LABELS[value] || value || "—";
    }

    function statusLabel(value) {
      return STATUS_LABELS[value] || value || "—";
    }

    function labelJob(jobId) {
      var title = jobTitleById.value[jobId];
      return title ? title : "#" + jobId;
    }

    function scheduleJobsTableColumnFit() {
      nextTick(function () {
        var table = document.querySelector('table[data-table-id="rms-jobs"]');
        if (!table) return;
        if (typeof global.crmEnsureRmsJobsTableColumns === "function") {
          global.crmEnsureRmsJobsTableColumns(table);
        } else if (typeof global.crmScheduleTableColumnResize === "function") {
          delete table.dataset.colContentFit;
          global.crmScheduleTableColumnResize(table.closest("#rms-app") || document);
        }
      });
    }

    async function loadJobs() {
      jobsState.loading = true;
      jobsState.error = "";
      try {
        var r = await rmsRequest("GET", "/api/rms/jobs");
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

    function validateJobSalaryCap() {
      var digits = stripJobSalaryCapInput(jobForm.salary_cap);
      if (!digits) return "";
      var n = Number(digits);
      if (!jobSalaryCapInRange(n)) return null;
      return String(n);
    }

    function isBlankJobSelect(value) {
      return value === "" || value == null;
    }

    function validateJobForm() {
      if (jobModalMode.value !== "create") {
        return { ok: true, message: "" };
      }
      var checks = [
        { label: "岗位名称", value: (jobForm.title || "").trim() },
        {
          label: "客户",
          value: jobForm.client_id,
          test: function (v) {
            return !isBlankJobSelect(v);
          },
        },
        { label: "JD", value: (jobForm.job_description || "").trim() },
        { label: "薪资帽", value: stripJobSalaryCapInput(jobForm.salary_cap) },
        { label: "年限", value: (jobForm.years_required || "").trim() },
        { label: "城市", value: (jobForm.location || "").trim() },
        { label: "学历", value: (jobForm.education || "").trim() },
        { label: "加班/差旅", value: (jobForm.overtime_travel || "").trim() },
        {
          label: "招聘",
          value: jobForm.owner_user_id,
          test: function (v) {
            return !isBlankJobSelect(v);
          },
        },
        {
          label: "销售",
          value: jobForm.sales_owner_user_id,
          test: function (v) {
            return !isBlankJobSelect(v);
          },
        },
        {
          label: "交付",
          value: jobForm.delivery_owner_user_id,
          test: function (v) {
            return !isBlankJobSelect(v);
          },
        },
      ];
      var hc = Number(jobForm.headcount);
      if (!Number.isFinite(hc) || hc < 1) {
        return { ok: false, message: "请填写 HC数" };
      }
      for (var i = 0; i < checks.length; i++) {
        var c = checks[i];
        var pass = c.test ? c.test(c.value) : String(c.value || "").trim() !== "";
        if (!pass) {
          return { ok: false, message: "请填写" + c.label };
        }
      }
      return { ok: true, message: "" };
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

    function scrollJobsToTop() {
      var el = jobsScrollWrap.value;
      if (el) el.scrollTop = 0;
    }

    async function loadJobFormOptions() {
      jobFormOptionsError.value = "";
      clientOptions.value = [];
      userOptions.value = [];
      var clientsR = await rmsRequest("GET", "/api/clients");
      if (!clientsR.ok) {
        jobFormOptionsError.value =
          "无法加载客户列表：" + clientsR.message + "（需 crm.clients.read）";
      } else {
        clientOptions.value = Array.isArray(clientsR.data) ? clientsR.data : [];
      }
      var assignR = await rmsRequest("GET", "/api/clients/assign-options");
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
      var cid = jobForm.client_id;
      if (cid === "" || cid == null) return;
      var r = await rmsRequest("GET", "/api/clients/" + cid);
      if (!r.ok) return;
      var c = r.data || {};
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
      resetJobForm();
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

    async function openJobView(row) {
      if (!row) return;
      jobDetailRow.value = row;
      jobDetailOpen.value = true;
    }

    function closeJobDetail() {
      jobDetailOpen.value = false;
      jobDetailRow.value = null;
    }

    async function removeJob(row) {
      if (!row || row.id == null) return;
      var base = "/api/rms/jobs/" + row.id;
      var r = await rmsRequest("DELETE", base);
      if (!r.ok && r.status === 405) {
        r = await rmsRequest("POST", base + "/delete");
      }
      if (!r.ok) {
        toast(r.message, true);
        return;
      }
      toast("已删除岗位", false);
      await loadJobs();
    }

    function onJobSalaryCapInput() {
      jobForm.salary_cap = stripJobSalaryCapInput(jobForm.salary_cap).slice(0, 5);
    }

    function formatJobSalaryCapField() {
      jobForm.salary_cap = formatJobSalaryCapDisplay(jobForm.salary_cap);
    }

    function displayJobSalaryCap(value) {
      var formatted = formatJobSalaryCapDisplay(value);
      return formatted || "—";
    }

    function resetJobModalState() {
      jobModalMode.value = "create";
      editingJobId.value = null;
    }

    function applyDefaultOwnerFromMe() {
      if (me.value.user && me.value.user.id != null) {
        jobForm.owner_user_id = me.value.user.id;
      }
    }

    async function submitJobModal() {
      modalSaving.value = true;
      modalError.value = "";
      try {
        formatJobSalaryCapField();
        var formValidation = validateJobForm();
        if (!formValidation.ok) {
          modalError.value = formValidation.message;
          return;
        }
        var salaryCap = validateJobSalaryCap();
        if (salaryCap === null) {
          modalError.value =
            "薪资帽须为 " +
            JOB_SALARY_CAP_MIN.toLocaleString("zh-CN") +
            "–" +
            JOB_SALARY_CAP_MAX.toLocaleString("zh-CN") +
            " 的整数";
          return;
        }
        var body = buildJobBody();
        var r;
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
        if (!r.ok) {
          modalError.value = r.message || "保存失败";
          return;
        }
        await loadJobs();
        toast("保存成功", false);
        if (jobModalMode.value === "create") {
          resetJobForm();
        }
        modal.value = null;
        modalError.value = "";
        resetJobModalState();
      } catch (err) {
        var msg = err && err.message ? err.message : String(err);
        modalError.value = "保存失败：" + msg;
      } finally {
        modalSaving.value = false;
      }
    }

    return {
      jobsState: jobsState,
      jobFilterPanelExpanded: jobFilterPanelExpanded,
      jobsScrollWrap: jobsScrollWrap,
      jobFilter: jobFilter,
      jobModalMode: jobModalMode,
      editingJobId: editingJobId,
      clientOptions: clientOptions,
      userOptions: userOptions,
      jobFormOptionsError: jobFormOptionsError,
      jobForm: jobForm,
      jobModalTitle: jobModalTitle,
      jobModalReadonly: jobModalReadonly,
      jobModalShowSave: jobModalShowSave,
      filteredJobs: filteredJobs,
      pagedJobs: jobsPagination.pagedRows,
      jobsCurrentPage: jobsPagination.jobsCurrentPage || jobsPagination.currentPage,
      jobsTotalPages: jobsPagination.jobsTotalPages || jobsPagination.totalPages,
      jobsPageNumbers: jobsPagination.jobsPageNumbers || jobsPagination.pageNumbers,
      jobsGoPage: jobsPagination.jobsGoPage || jobsPagination.goPage,
      jobsPageSize: jobsPagination.pageSize,
      openJobs: openJobs,
      priorityOptions: PRIORITY_OPTIONS,
      statusOptions: STATUS_OPTIONS,
      priorityLabel: priorityLabel,
      statusLabel: statusLabel,
      labelJob: labelJob,
      loadJobs: loadJobs,
      loadJobFormOptions: loadJobFormOptions,
      resetJobForm: resetJobForm,
      resetJobFilter: resetJobFilter,
      scrollJobsToTop: scrollJobsToTop,
      onJobClientChange: onJobClientChange,
      openJobModal: openJobModal,
      openJobEdit: openJobEdit,
      openJobView: openJobView,
      jobDetailOpen: jobDetailOpen,
      jobDetailRow: jobDetailRow,
      closeJobDetail: closeJobDetail,
      removeJob: removeJob,
      onJobSalaryCapInput: onJobSalaryCapInput,
      formatJobSalaryCapField: formatJobSalaryCapField,
      displayJobSalaryCap: displayJobSalaryCap,
      resetJobModalState: resetJobModalState,
      submitJobModal: submitJobModal,
      applyDefaultOwnerFromMe: applyDefaultOwnerFromMe,
      scheduleJobsTableColumnFit: scheduleJobsTableColumnFit,
    };
  }

  global.CrmRmsJobs = {
    createJobsState: createJobsState,
  };
})(typeof window !== "undefined" ? window : globalThis);
