/**
 * RMS candidates tab + candidate modal (Phase R2-A split).
 */
(function (global) {
  "use strict";

  var Core = global.CrmRmsCore || {};
  var CandidateReport = global.RmsCandidateReport || {};

  var RMS_LIST_TABLE_IDS = {
    candidates: "rms-candidates",
    applications: "rms-applications",
    deliveryReview: "rms-delivery-review",
    pipeline: "rms-pipeline",
  };

  function createCandidatesState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var watch = deps.watch;
    var nextTick = deps.nextTick;
    var modal = deps.modal;
    var modalError = deps.modalError;
    var modalSaving = deps.modalSaving;
    var toast = deps.toast;
    var jobs = deps.jobs;
    var activeTab = deps.activeTab;
    var viewMode = deps.viewMode;
    var clientNameById = deps.clientNameById;
    var Labels = deps.Labels || {};
    var PHONE_RE = deps.PHONE_RE;
    var isCandidateDuplicateError = deps.isCandidateDuplicateError;
    var userFacingRmsError = deps.userFacingRmsError;
    var showCandidateDuplicateDialog = deps.showCandidateDuplicateDialog;

    var rmsRequest = Core.rmsRequest;
    var authHeaders = Core.authHeaders;
    var messageForStatus = Core.messageForStatus;
    var fuzzyMatch = Core.fuzzyMatch;
    var formatSalaryThousands = Core.formatSalaryThousands;
    var stripSalaryCommas = Core.stripSalaryCommas;
    var showValidationPrompt = Core.showValidationPrompt;

    var candidatesState = reactive({ loading: false, items: [], error: "" });
    var candidatesScrollWrap = ref(null);
    var candidateFilter = reactive({
      name: "",
      client_id: "",
      job_id: "",
      city: "",
      source: "",
      education_level: "",
      date_from: "",
      date_to: "",
    });
    var candidateModalMode = ref("create");
    var editingCandidateId = ref(null);
    var editingCandidateResumeName = ref("");
    var candidateDetailOpen = ref(false);
    var candidateDetailRow = ref(null);
    var candidateDetailLoading = ref(false);
    var candidateDetailError = ref("");
    var candidateParseSummaryFields = [
      { key: "name", label: "姓名" },
      { key: "phone", label: "手机号" },
      { key: "email_wechat", label: "邮箱/微信" },
      { key: "email", label: "邮箱" },
      { key: "wechat", label: "微信" },
      { key: "age", label: "年龄" },
      { key: "work_years", label: "工作年限" },
      { key: "city", label: "城市" },
      { key: "current_company", label: "当前公司" },
      { key: "current_title", label: "当前职位" },
      { key: "gender", label: "性别" },
      { key: "marital_status", label: "婚姻状况" },
      { key: "source", label: "来源" },
      { key: "school", label: "学校" },
      { key: "major", label: "专业" },
      { key: "education_level", label: "学历" },
    ];
    var candidateForm = reactive({
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
    var candidateResumeFile = ref(null);
    var jobPickerQuery = ref("");
    var jobPickerOpen = ref(false);
    var clientPickerQuery = ref("");
    var clientPickerOpen = ref(false);

    var candidateKeywordTimer = null;
    var suppressCandidateSearchWatch = false;

    var candidateModalTitle = computed(function () {
      return candidateModalMode.value === "edit" ? "修改候选人" : "新建候选人";
    });

    var candidateModalShowSave = computed(function () {
      return modal.value === "candidate";
    });

    var filteredCandidates = computed(function () {
      var rows = candidatesState.items.slice();
      if (candidateFilter.client_id !== "" && candidateFilter.client_id != null) {
        var cid = Number(candidateFilter.client_id);
        rows = rows.filter(function (c) {
          return Number(c.target_client_id) === cid;
        });
      }
      if (candidateFilter.job_id !== "" && candidateFilter.job_id != null) {
        var jid = Number(candidateFilter.job_id);
        rows = rows.filter(function (c) {
          return Number(c.target_job_id) === jid;
        });
      }
      var city = (candidateFilter.city || "").trim().toLowerCase();
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
      var parseDateOnly = Labels.parseDateOnly || function () { return null; };
      var from = parseDateOnly(candidateFilter.date_from);
      var to = parseDateOnly(candidateFilter.date_to);
      if (from || to) {
        rows = rows.filter(function (c) {
          var recDate = parseDateOnly(c.recommended_at);
          if (from && (!recDate || recDate < from)) return false;
          if (to && (!recDate || recDate > to)) return false;
          return true;
        });
      }
      return rows;
    });

    var candidateNameById = computed(function () {
      var m = {};
      candidatesState.items.forEach(function (c) {
        m[c.id] = c.name || "";
      });
      return m;
    });

    var filteredJobPickerOptions = computed(function () {
      var q = jobPickerQuery.value;
      return jobs.openJobs.value.filter(function (j) {
        var label = (j.title || "") + " " + (j.client_name || clientNameById(j.client_id) || "");
        return fuzzyMatch(label, q);
      });
    });

    var filteredClientPickerOptions = computed(function () {
      var q = clientPickerQuery.value;
      return jobs.clientOptions.value.filter(function (c) {
        return fuzzyMatch(c.name, q);
      });
    });

    var selectedJobPickerLabel = computed(function () {
      var id = candidateForm.target_job_id;
      if (id === "" || id == null) return "";
      var j = jobs.jobsState.items.find(function (x) {
        return Number(x.id) === Number(id);
      });
      if (j) {
        return (j.title || "—") + (j.client_name ? " · " + j.client_name : "");
      }
      return "#" + id;
    });

    var selectedClientPickerLabel = computed(function () {
      var id = candidateForm.target_client_id;
      if (id === "" || id == null) return "";
      var c = jobs.clientOptions.value.find(function (x) {
        return Number(x.id) === Number(id);
      });
      return c ? c.name || "#" + id : "#" + id;
    });

    function labelCandidate(candidateId) {
      var name = candidateNameById.value[candidateId];
      return name ? name : "#" + candidateId;
    }

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
      var formatted = formatSalaryThousands(value);
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
      var name = String((c && c.resume_file_name) || "").toLowerCase();
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
      var f = ev.target && ev.target.files && ev.target.files[0];
      candidateResumeFile.value = f || null;
    }

    async function uploadCandidateResume(candidateId, file) {
      var fd = new FormData();
      fd.append("file", file);
      var headers = authHeaders();
      var resp;
      try {
        resp = await fetch("/api/rms/candidates/" + candidateId + "/resume", {
          method: "POST",
          headers: headers,
          body: fd,
          credentials: "same-origin",
        });
      } catch (e) {
        var msg = e && e.message ? e.message : String(e);
        return { ok: false, status: 0, message: "简历上传失败（" + msg + "）" };
      }
      var payload = null;
      var ct = resp.headers.get("content-type") || "";
      if (ct.indexOf("application/json") !== -1) {
        try {
          payload = await resp.json();
        } catch (e2) {
          payload = null;
        }
      }
      if (!resp.ok) {
        var detail = payload && payload.detail != null ? payload.detail : "";
        return { ok: false, status: resp.status, message: messageForStatus(resp.status, detail) };
      }
      return { ok: true, data: payload };
    }

    function scheduleCandidatesTableColumnFit() {
      nextTick(function () {
        requestAnimationFrame(function () {
          var tableId = RMS_LIST_TABLE_IDS[activeTab.value];
          if (!tableId) return;
          var table = document.querySelector('table[data-table-id="' + tableId + '"]');
          if (!table) return;
          if (tableId === "rms-candidates") {
            if (typeof global.crmEnsureRmsCandidatesTableColumns === "function") {
              global.crmEnsureRmsCandidatesTableColumns(table);
              return;
            }
          }
          if (tableId === "rms-pipeline") {
            if (typeof global.crmEnsureRmsPipelineTableColumns === "function") {
              global.crmEnsureRmsPipelineTableColumns(table);
              return;
            }
          }
          if (table.dataset.colResizeReady === "1") {
            if (typeof global.crmInitTableColumnResize === "function") {
              global.crmInitTableColumnResize(table);
              return;
            }
          }
          if (typeof global.crmFitTableColumnsToContent === "function") {
            global.crmFitTableColumnsToContent(table);
          } else if (typeof global.crmInitTableColumnResize === "function") {
            global.crmInitTableColumnResize(table);
          } else if (typeof global.crmScheduleTableColumnResize === "function") {
            delete table.dataset.colContentFit;
            global.crmScheduleTableColumnResize(table.closest("#rms-app") || document);
          }
        });
      });
    }

    async function loadCandidates() {
      candidatesState.loading = true;
      candidatesState.error = "";
      try {
        var keyword = (candidateFilter.name || "").trim();
        var path = keyword
          ? "/api/rms/candidates?q=" + encodeURIComponent(keyword)
          : "/api/rms/candidates";
        var r = await rmsRequest("GET", path);
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

    async function resetCandidateFilter() {
      if (candidateKeywordTimer) {
        clearTimeout(candidateKeywordTimer);
        candidateKeywordTimer = null;
      }
      suppressCandidateSearchWatch = true;
      candidateFilter.name = "";
      candidateFilter.client_id = "";
      candidateFilter.job_id = "";
      candidateFilter.city = "";
      candidateFilter.source = "";
      candidateFilter.education_level = "";
      candidateFilter.date_from = "";
      candidateFilter.date_to = "";
      await loadCandidates();
      suppressCandidateSearchWatch = false;
    }

    function candidateParseSummaryEmpty(row) {
      var summary = row && row.latest_resume_parse_summary;
      return !summary || !Object.keys(summary).length;
    }

    function candidateParseSummaryValue(row, key) {
      var summary = row && row.latest_resume_parse_summary;
      if (!summary) return "—";
      var val = String(summary[key] == null ? "" : summary[key]).trim();
      return val || "—";
    }

    async function openCandidateDetail(c) {
      if (!c || c.id == null) return;
      candidateDetailOpen.value = true;
      candidateDetailRow.value = null;
      candidateDetailLoading.value = true;
      candidateDetailError.value = "";
      var r = await rmsRequest("GET", "/api/rms/candidates/" + c.id);
      candidateDetailLoading.value = false;
      if (!r.ok) {
        candidateDetailError.value = r.message || ("请求失败（" + r.status + "）");
        return;
      }
      candidateDetailRow.value = r.data;
      if (global.crmSyncHeaderHeight) {
        requestAnimationFrame(function () { global.crmSyncHeaderHeight(); });
      }
    }

    function closeCandidateDetail() {
      candidateDetailOpen.value = false;
      candidateDetailRow.value = null;
      candidateDetailLoading.value = false;
      candidateDetailError.value = "";
      if (global.crmSyncHeaderHeight) {
        requestAnimationFrame(function () { global.crmSyncHeaderHeight(); });
      }
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

    function resolveValidationField(message, field) {
      if (field) return field;
      return CandidateReport.fieldKeyForValidationMessage
        ? CandidateReport.fieldKeyForValidationMessage(message)
        : "";
    }

    function focusCandidateModalField(field) {
      var key = String(field || "").trim();
      if (!key) return;
      var mapped = key === "location" ? "city" : key;
      nextTick(function () {
        var root = document.querySelector("[data-rms-candidate-form]");
        var host = root
          ? root.querySelector('[data-rms-candidate-field="' + mapped + '"]')
          : document.querySelector('[data-rms-candidate-field="' + mapped + '"]');
        if (!host) return;
        var focusable =
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

    function setModalError(message, field) {
      modalError.value = showValidationPrompt(message);
      focusCandidateModalField(resolveValidationField(message, field));
    }

    function resetCandidateModalState() {
      candidateModalMode.value = "create";
      editingCandidateId.value = null;
      editingCandidateResumeName.value = "";
    }

    async function openCandidateModal() {
      modalError.value = "";
      candidateModalMode.value = "create";
      editingCandidateId.value = null;
      resetCandidateForm();
      modal.value = "candidate";
      if (!jobs.clientOptions.value.length && jobs.loadJobFormOptions) {
        await jobs.loadJobFormOptions();
      }
    }

    async function openCandidateEdit(row) {
      modalError.value = "";
      candidateModalMode.value = "edit";
      editingCandidateId.value = row.id;
      resetCandidateForm();
      fillCandidateFormFromRow(row);
      modal.value = "candidate";
      if (!jobs.clientOptions.value.length && jobs.loadJobFormOptions) {
        await jobs.loadJobFormOptions();
      }
    }

    async function removeCandidate(row) {
      var r = await rmsRequest("DELETE", "/api/rms/candidates/" + row.id);
      if (!r.ok) {
        toast(r.message, true);
        return;
      }
      toast("已删除", false);
      await loadCandidates();
    }

    async function submitCandidateModal() {
      modalSaving.value = true;
      modalError.value = "";
      var r;
      try {
        var phone = (candidateForm.phone || "").trim();
        if (candidateModalMode.value === "create") {
          var createValidation = CandidateReport.validateCandidateCreateForm
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
        var jobId = Number(candidateForm.target_job_id);
        var pickedJob = jobs.openJobs.value.find(function (j) {
          return Number(j.id) === jobId;
        });
        if (!pickedJob) {
          setModalError("应聘岗位不存在或不是 open 状态", "target_job_id");
          return;
        }
        var body = buildCandidateBody();
        body.phone = phone;
        if (candidateModalMode.value === "edit") {
          r = await rmsRequest("PATCH", "/api/rms/candidates/" + editingCandidateId.value, body);
          if (r.ok && candidateResumeFile.value) {
            var up = await uploadCandidateResume(editingCandidateId.value, candidateResumeFile.value);
            if (!up.ok) {
              modalError.value = up.message;
              await loadCandidates();
              return;
            }
          }
        } else {
          r = await rmsRequest("POST", "/api/rms/candidates", body);
          if (r.ok && candidateResumeFile.value && r.data && r.data.id) {
            var up2 = await uploadCandidateResume(r.data.id, candidateResumeFile.value);
            if (!up2.ok) {
              modalError.value = up2.message;
              await loadCandidates();
              return;
            }
          }
        }
        if (r.ok) await loadCandidates();
        if (!r.ok) {
          if (isCandidateDuplicateError(r)) {
            await showCandidateDuplicateDialog();
            return;
          }
          setModalError(userFacingRmsError(r));
          return;
        }
        toast("保存成功", false);
        modal.value = null;
        modalError.value = "";
        resetCandidateModalState();
      } catch (err) {
        var msg = err && err.message ? err.message : String(err);
        setModalError("保存失败：" + msg);
      } finally {
        modalSaving.value = false;
      }
    }

    watch(
      function () {
        return candidateFilter.name;
      },
      function () {
        if (suppressCandidateSearchWatch) return;
        if (candidateKeywordTimer) clearTimeout(candidateKeywordTimer);
        candidateKeywordTimer = setTimeout(function () {
          candidateKeywordTimer = null;
          loadCandidates();
        }, 300);
      }
    );

    watch(
      function () {
        return filteredCandidates.value.length;
      },
      function (len, prevLen) {
        if (activeTab.value !== "candidates" || viewMode.value === "candidateReport") return;
        if (len > 0 && prevLen === 0) {
          scheduleCandidatesTableColumnFit();
        }
      }
    );

    return {
      candidatesState: candidatesState,
      candidatesScrollWrap: candidatesScrollWrap,
      candidateFilter: candidateFilter,
      candidateModalMode: candidateModalMode,
      editingCandidateId: editingCandidateId,
      editingCandidateResumeName: editingCandidateResumeName,
      candidateDetailOpen: candidateDetailOpen,
      candidateDetailRow: candidateDetailRow,
      candidateDetailLoading: candidateDetailLoading,
      candidateDetailError: candidateDetailError,
      candidateParseSummaryFields: candidateParseSummaryFields,
      candidateForm: candidateForm,
      candidateResumeFile: candidateResumeFile,
      jobPickerQuery: jobPickerQuery,
      jobPickerOpen: jobPickerOpen,
      clientPickerQuery: clientPickerQuery,
      clientPickerOpen: clientPickerOpen,
      candidateModalTitle: candidateModalTitle,
      candidateModalShowSave: candidateModalShowSave,
      filteredCandidates: filteredCandidates,
      candidateNameById: candidateNameById,
      filteredJobPickerOptions: filteredJobPickerOptions,
      filteredClientPickerOptions: filteredClientPickerOptions,
      selectedJobPickerLabel: selectedJobPickerLabel,
      selectedClientPickerLabel: selectedClientPickerLabel,
      labelCandidate: labelCandidate,
      displayCandidateContact: displayCandidateContact,
      displayTargetJob: displayTargetJob,
      displayTargetClient: displayTargetClient,
      displaySalary: displaySalary,
      formatCandidateSalaryField: formatCandidateSalaryField,
      resumeViewUrl: resumeViewUrl,
      resumeDownloadUrl: resumeDownloadUrl,
      resumeCanView: resumeCanView,
      selectJobPicker: selectJobPicker,
      selectClientPicker: selectClientPicker,
      onCandidateResumeChange: onCandidateResumeChange,
      scheduleCandidatesTableColumnFit: scheduleCandidatesTableColumnFit,
      loadCandidates: loadCandidates,
      resetCandidateFilter: resetCandidateFilter,
      candidateParseSummaryEmpty: candidateParseSummaryEmpty,
      candidateParseSummaryValue: candidateParseSummaryValue,
      openCandidateDetail: openCandidateDetail,
      closeCandidateDetail: closeCandidateDetail,
      openCandidateModal: openCandidateModal,
      openCandidateEdit: openCandidateEdit,
      removeCandidate: removeCandidate,
      submitCandidateModal: submitCandidateModal,
      resetCandidateModalState: resetCandidateModalState,
    };
  }

  global.CrmRmsCandidates = {
    createCandidatesState: createCandidatesState,
  };
})(typeof window !== "undefined" ? window : globalThis);
