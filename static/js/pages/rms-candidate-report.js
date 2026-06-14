/**
 * RMS candidate report panel: multipart submit + server-side draft parse.
 */
(function (global) {
  "use strict";

  var PARSE_DRAFT_URL = "/api/rms/applications/candidate-report/parse-draft";
  var DRAFT_FORM_FIELDS = [
    "name",
    "age",
    "work_years",
    "phone",
    "email_wechat",
    "current_salary",
    "expected_salary",
    "education_level",
    "school",
    "major",
    "gender",
  ];

  function emptyReportForm() {
    return {
      job_id: "",
      client_id: "",
      client_name: "",
      job_title: "",
      location: "",
      recommendation_note: "",
      current_salary: "",
      expected_salary: "",
      name: "",
      age: "",
      work_years: "",
      phone: "",
      email_wechat: "",
      available_date: "",
      education_level: "",
      school: "",
      major: "",
      gender: "",
      marital_status: "",
      source: "",
      source_other: "",
    };
  }

  function fillFromJob(form, job, clientNameById) {
    if (!job) return;
    form.job_id = job.id;
    form.client_id = job.client_id != null ? job.client_id : "";
    form.client_name = job.client_name || (clientNameById && clientNameById(job.client_id)) || "";
    form.job_title = job.title || "";
    form.location = job.location || "";
  }

  function isEmptyVal(v) {
    return v == null || String(v).trim() === "";
  }

  function canAutoFillField(form, field, tracker) {
    var current = form[field];
    if (isEmptyVal(current)) return true;
    if (!tracker || tracker[field] === undefined) return false;
    return String(current) === String(tracker[field]);
  }

  function applyDraftToForm(form, draft, tracker) {
    if (!draft || !form) return 0;
    var filled = 0;
    DRAFT_FORM_FIELDS.forEach(function (field) {
      var val = draft[field];
      if (val == null || String(val).trim() === "") return;
      if (!canAutoFillField(form, field, tracker)) return;
      form[field] = String(val).trim();
      if (tracker) tracker[field] = form[field];
      filled += 1;
    });
    return filled;
  }

  function clearAutoFilledFields(form, tracker) {
    if (!form || !tracker) return;
    Object.keys(tracker).forEach(function (field) {
      if (String(form[field]) === String(tracker[field])) {
        form[field] = "";
      }
    });
    Object.keys(tracker).forEach(function (field) {
      delete tracker[field];
    });
  }

  function countDraftFields(draft) {
    if (!draft) return 0;
    var n = 0;
    DRAFT_FORM_FIELDS.forEach(function (f) {
      if (draft[f] != null && String(draft[f]).trim() !== "") n += 1;
    });
    return n;
  }

  function formatFileSize(bytes) {
    var n = Number(bytes);
    if (!Number.isFinite(n) || n <= 0) return "0 B";
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  var REPORT_PHONE_RE = /^1\d{10}$/;

  var SOURCE_LEGACY_ALIASES = { 平台: "内部RMS" };

  function isKnownSourcePreset(value) {
    var s = String(value || "").trim();
    if (!s || s === "其他") return false;
    if (SOURCE_LEGACY_ALIASES[s]) return true;
    return ["内部RMS", "Boss", "linkedin", "猎聘", "内推", "挂靠", "外协"].indexOf(s) >= 0;
  }

  function resolveSourceForForm(storedSource) {
    var s = String(storedSource || "").trim();
    if (!s) return { source: "", source_other: "" };
    if (SOURCE_LEGACY_ALIASES[s]) return { source: SOURCE_LEGACY_ALIASES[s], source_other: "" };
    if (isKnownSourcePreset(s)) return { source: s, source_other: "" };
    if (s === "其他") return { source: "其他", source_other: "" };
    return { source: "其他", source_other: s };
  }

  function resolveSourceForSave(source, sourceOther) {
    var sel = String(source || "").trim();
    if (!sel) return "";
    if (sel === "其他") return String(sourceOther || "").trim();
    return sel;
  }

  function stripSalaryValue(value) {
    return String(value == null ? "" : value).replace(/,/g, "").trim();
  }

  var REPORT_LABEL_TO_FIELD = {
    "推荐评语": "recommendation_note",
    "城市": "location",
    "当前薪资": "current_salary",
    "期望薪资": "expected_salary",
    "姓名": "name",
    "年龄": "age",
    "年限": "work_years",
    "手机号": "phone",
    "邮箱/微信": "email_wechat",
    "到岗时间": "available_date",
    "学历": "education_level",
    "来源": "source",
    "具体来源": "source_other",
    "学校": "school",
    "专业": "major",
    "性别": "gender",
    "婚姻状况": "marital_status",
    "简历": "resume",
  };

  function fieldKeyForValidationMessage(message) {
    var text = String(message || "").trim();
    var fillMatch = text.match(/^请填写(.+)$/);
    if (fillMatch) {
      return REPORT_LABEL_TO_FIELD[fillMatch[1]] || "";
    }
    if (text.indexOf("手机号") >= 0) {
      return "phone";
    }
    if (text.indexOf("简历") >= 0) {
      return "resume";
    }
    return "";
  }

  function _candidateFieldChecks(form, extraChecks) {
    var checks = [
      { field: "location", label: "城市", value: (form.location || form.city || "").trim() },
      { field: "current_salary", label: "当前薪资", value: stripSalaryValue(form.current_salary) },
      { field: "expected_salary", label: "期望薪资", value: stripSalaryValue(form.expected_salary) },
      { field: "name", label: "姓名", value: (form.name || "").trim() },
      { field: "age", label: "年龄", value: (form.age || "").trim() },
      { field: "work_years", label: "年限", value: (form.work_years || "").trim() },
      { field: "phone", label: "手机号", value: (form.phone || "").trim() },
      { field: "email_wechat", label: "邮箱/微信", value: (form.email_wechat || "").trim() },
      { field: "available_date", label: "到岗时间", value: (form.available_date || "").trim() },
      { field: "education_level", label: "学历", value: (form.education_level || "").trim() },
      {
        field: "source",
        label: "来源",
        value: resolveSourceForSave(form.source, form.source_other),
      },
      { field: "school", label: "学校", value: (form.school || "").trim() },
      { field: "major", label: "专业", value: (form.major || "").trim() },
      { field: "gender", label: "性别", value: (form.gender || "").trim() },
      { field: "marital_status", label: "婚姻状况", value: (form.marital_status || "").trim() },
    ];
    if (extraChecks && extraChecks.length) {
      checks = extraChecks.concat(checks);
    }
    return checks;
  }

  function _runRequiredChecks(form, extraChecks, options) {
    options = options || {};
    if (options.requireJob !== false) {
      if (!form || !form.job_id) {
        return { ok: false, message: "请选择应聘岗位", field: "" };
      }
    }
    if (String(form.source || "").trim() === "其他" && !String(form.source_other || "").trim()) {
      return { ok: false, message: "请填写具体来源", field: "source_other" };
    }
    var checks = _candidateFieldChecks(form, extraChecks);
    for (var i = 0; i < checks.length; i++) {
      if (!checks[i].value) {
        return {
          ok: false,
          message: "请填写" + checks[i].label,
          field: checks[i].field || "",
        };
      }
    }
    if (!REPORT_PHONE_RE.test((form.phone || "").trim())) {
      return { ok: false, message: "请填写有效的11位手机号", field: "phone" };
    }
    return { ok: true, message: "", field: "" };
  }

  function _normalizeCandidateModalForm(form) {
    var normalized = form || {};
    return {
      job_id: normalized.job_id || normalized.target_job_id,
      city: normalized.city,
      current_salary: normalized.current_salary,
      expected_salary: normalized.expected_salary,
      name: normalized.name,
      age: normalized.age,
      work_years: normalized.work_years,
      phone: normalized.phone,
      email_wechat: normalized.email_wechat,
      available_date: normalized.available_date,
      education_level: normalized.education_level,
      source: normalized.source,
      source_other: normalized.source_other,
      school: normalized.school,
      major: normalized.major,
      gender: normalized.gender,
      marital_status: normalized.marital_status,
    };
  }

  function validateCandidateModalForm(form, opts) {
    var options = opts || {};
    var result = _runRequiredChecks(_normalizeCandidateModalForm(form), [], { requireJob: false });
    if (!result.ok) return result;
    if (options.requireResume && !options.hasResumeFile && !options.hasExistingResume) {
      return { ok: false, message: "请上传简历", field: "resume" };
    }
    return { ok: true, message: "", field: "" };
  }

  function validateReportForm(form) {
    return _runRequiredChecks(form, [
      {
        field: "recommendation_note",
        label: "推荐评语",
        value: (form.recommendation_note || "").trim(),
      },
    ]);
  }

  function validateCandidateCreateForm(form) {
    return validateCandidateModalForm(form, {
      requireResume: false,
      hasResumeFile: false,
      hasExistingResume: false,
    });
  }

  function buildReportJson(form, stripSalaryCommas) {
    return {
      job_id: Number(form.job_id),
      client_id: Number(form.client_id),
      city: (form.location || "").trim(),
      recommendation_note: (form.recommendation_note || "").trim(),
      current_salary: stripSalaryCommas(form.current_salary),
      expected_salary: stripSalaryCommas(form.expected_salary),
      name: (form.name || "").trim(),
      age: (form.age || "").trim(),
      work_years: (form.work_years || "").trim(),
      phone: (form.phone || "").trim(),
      email_wechat: (form.email_wechat || "").trim(),
      available_date: form.available_date || "",
      education_level: form.education_level || "",
      school: (form.school || "").trim(),
      major: (form.major || "").trim(),
      gender: form.gender || "",
      marital_status: form.marital_status || "",
      source: resolveSourceForSave(form.source, form.source_other),
    };
  }

  async function parseCandidateReportDraft(file, jobId, authHeaders, messageForStatus) {
    if (!file) {
      return { ok: false, status: 0, message: "请选择简历文件" };
    }
    var fd = new FormData();
    fd.append("file", file);
    if (jobId != null && jobId !== "") fd.append("job_id", String(jobId));
    var headers = authHeaders();
    var resp;
    try {
      resp = await fetch(PARSE_DRAFT_URL, {
        method: "POST",
        headers: headers,
        body: fd,
        credentials: "same-origin",
      });
    } catch (e) {
      var msg = e && e.message ? e.message : String(e);
      return { ok: false, status: 0, message: "解析失败（" + msg + "）" };
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

  async function submitCandidateReport(form, file, authHeaders, messageForStatus) {
    var fd = new FormData();
    fd.append("report_json", JSON.stringify(buildReportJson(form, function (s) {
      return String(s == null ? "" : s).replace(/,/g, "").trim();
    })));
    if (file) fd.append("file", file);
    var headers = authHeaders();
    var resp;
    try {
      resp = await fetch("/api/rms/applications/candidate-report", {
        method: "POST",
        headers: headers,
        body: fd,
        credentials: "same-origin",
      });
    } catch (e) {
      var msg = e && e.message ? e.message : String(e);
      return { ok: false, status: 0, message: "提交失败（" + msg + "）" };
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
      return {
        ok: false,
        status: resp.status,
        detail: detail,
        message: messageForStatus(resp.status, detail),
      };
    }
    return { ok: true, data: payload };
  }

  function createDeliveryReviewApi(rmsRequest) {
    return {
      loadDeliveryReview: async function (state) {
        state.loading = true;
        state.error = "";
        try {
          var r = await rmsRequest("GET", "/api/rms/applications/delivery-review");
          if (!r.ok) {
            state.items = [];
            state.error = r.message;
            return;
          }
          state.items = Array.isArray(r.data) ? r.data : [];
        } finally {
          state.loading = false;
        }
      },
      submitDeliveryReview: async function (appId, result, note) {
        return rmsRequest("POST", "/api/rms/applications/" + appId + "/delivery-review", {
          result: result,
          note: String(note == null ? "" : note).trim(),
        });
      },
    };
  }

  function createReportState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var watch = deps.watch;
    var nextTick = deps.nextTick;
    var viewMode = deps.viewMode;
    var rmsRequest = deps.rmsRequest;
    var toast = deps.toast;
    var jobs = deps.jobs;
    var loadApplications = deps.loadApplications;
    var loadCandidates = deps.loadCandidates;
    var loadDeliveryReview = deps.loadDeliveryReview;
    var clientNameById = deps.clientNameById;
    var formatSalaryThousands = deps.formatSalaryThousands;
    var showCandidateDuplicateDialog = deps.showCandidateDuplicateDialog;
    var isCandidateDuplicateError = deps.isCandidateDuplicateError;
    var userFacingRmsError = deps.userFacingRmsError;

    var Core = global.CrmRmsCore || {};
    var ReportApi = global.RmsCandidateReport || {};
    var authHeaders = Core.authHeaders ? Core.authHeaders.bind(Core) : function () { return {}; };
    var workflowMessageForStatus = Core.workflowMessageForStatus
      ? Core.workflowMessageForStatus.bind(Core)
      : Core.messageForStatus
        ? Core.messageForStatus.bind(Core)
        : function (s) { return String(s); };
    var showValidationPrompt = Core.showValidationPrompt
      ? Core.showValidationPrompt.bind(Core)
      : function (m) { return String(m || ""); };
    var REPORT_LOCAL_TEXT_PREVIEW_MAX = Core.REPORT_LOCAL_TEXT_PREVIEW_MAX || 2000;
    var CANDIDATE_DUPLICATE_PARSE_HINT = "系统中已存在该人选";

    var reportSaving = ref(false);
    var reportError = ref("");
    var reportResumeFile = ref(null);
    var reportResumeInput = ref(null);
    var reportResumeDraftStatus = ref("idle");
    var reportResumeDraftError = ref("");
    var reportResumePdfPreviewUrl = ref("");
    var reportResumeTextPreview = ref("");
    var reportResumeTextPreviewTruncated = ref(false);
    var reportResumePreviewText = ref("");
    var reportResumePreviewError = ref("");
    var reportResumePreviewWarning = ref("");
    var reportResumePreviewRawText = ref("");
    var reportResumePreviewLength = ref(0);
    var reportResumePreviewRawLength = ref(0);
    var reportShowRawExtractDebug = ref(
      typeof global !== "undefined" &&
        /(?:^|[?&])rms_debug=1(?:&|$)/.test(
          (global.location && global.location.search) || ""
        )
    );
    var reportResumeDragging = ref(false);
    var reportAutoFilledFields = reactive({});
    var reportForm = reactive(
      ReportApi.emptyReportForm ? ReportApi.emptyReportForm() : {}
    );
    var reportMode = ref("new");
    var selectedExistingCandidate = ref(null);
    var existingCandidatePickerOpen = ref(false);
    var existingCandidatePickerQuery = ref("");
    var existingCandidatePickerItems = ref([]);
    var existingCandidatePickerLoading = ref(false);
    var existingCandidatePickerError = ref("");
    var existingCandidatePickerDetail = ref(null);
    var existingCandidatePickerDetailLoading = ref(false);
    var existingCandidateHoverCard = reactive({
      open: false,
      x: 0,
      y: 0,
      candidateId: null,
    });
    var existingCandidatePickerTimer = null;
    var existingCandidatePopoverHideTimer = null;
    var reportPageDragGuardOn = false;

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

    var existingCandidatePopoverStyle = computed(function () {
      var gap = 12;
      var width = 320;
      var height = 460;
      var viewportW = typeof global !== "undefined" ? global.innerWidth : 1920;
      var viewportH = typeof global !== "undefined" ? global.innerHeight : 1080;
      var left = existingCandidateHoverCard.x + gap;
      var top = existingCandidateHoverCard.y + gap;
      if (left + width > viewportW - 12) {
        left = existingCandidateHoverCard.x - width - gap;
      }
      if (top + height > viewportH - 12) {
        top = viewportH - height - 12;
      }
      if (top < 12) top = 12;
      if (left < 12) left = 12;
      return { left: left + "px", top: top + "px" };
    });

    function formatReportSalaryField(field) {
      reportForm[field] = formatSalaryThousands(reportForm[field]);
    }

    function reportResumeFileExt(file) {
      var name = (file && file.name) || "";
      var dot = name.lastIndexOf(".");
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
      var ext = reportResumeFileExt(file);
      if (ext === ".pdf") {
        reportResumePdfPreviewUrl.value = URL.createObjectURL(file);
        return;
      }
      if (ext === ".txt" || ext === ".rtf") {
        var reader = new FileReader();
        reader.onload = function () {
          var full = String(reader.result || "");
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
      return ReportApi.formatFileSize
        ? ReportApi.formatFileSize(bytes)
        : String(bytes || 0);
    }

    function hideExistingCandidatePopover() {
      if (existingCandidatePopoverHideTimer) {
        clearTimeout(existingCandidatePopoverHideTimer);
        existingCandidatePopoverHideTimer = null;
      }
      existingCandidateHoverCard.open = false;
      existingCandidateHoverCard.candidateId = null;
      existingCandidatePickerDetail.value = null;
      existingCandidatePickerDetailLoading.value = false;
    }

    function keepExistingCandidatePopover() {
      if (existingCandidatePopoverHideTimer) {
        clearTimeout(existingCandidatePopoverHideTimer);
        existingCandidatePopoverHideTimer = null;
      }
    }

    function scheduleHideExistingCandidatePopover() {
      keepExistingCandidatePopover();
      existingCandidatePopoverHideTimer = setTimeout(function () {
        existingCandidatePopoverHideTimer = null;
        hideExistingCandidatePopover();
      }, 150);
    }

    function moveExistingCandidatePopover(event) {
      if (!event) return;
      existingCandidateHoverCard.x = event.clientX;
      existingCandidateHoverCard.y = event.clientY;
    }

    async function showExistingCandidatePopover(c, event) {
      if (!c || c.id == null) return;
      keepExistingCandidatePopover();
      existingCandidateHoverCard.open = true;
      existingCandidateHoverCard.candidateId = c.id;
      moveExistingCandidatePopover(event);
      if (
        existingCandidatePickerDetail.value &&
        Number(existingCandidatePickerDetail.value.id) === Number(c.id)
      ) {
        return;
      }
      await showExistingCandidatePickerDetail(c);
    }

    function resetExistingCandidatePickerState() {
      hideExistingCandidatePopover();
      existingCandidatePickerOpen.value = false;
      existingCandidatePickerQuery.value = "";
      existingCandidatePickerItems.value = [];
      existingCandidatePickerLoading.value = false;
      existingCandidatePickerError.value = "";
      if (existingCandidatePickerTimer) {
        clearTimeout(existingCandidatePickerTimer);
        existingCandidatePickerTimer = null;
      }
    }

    function resetExistingCandidateReportState() {
      reportMode.value = "new";
      selectedExistingCandidate.value = null;
      resetExistingCandidatePickerState();
    }

    function fillReportFormFromCandidate(detail) {
      if (!detail) return;
      reportForm.name = detail.name || "";
      reportForm.age = detail.age || "";
      reportForm.work_years = detail.work_years || "";
      reportForm.phone = detail.phone || "";
      reportForm.email_wechat = String(
        detail.email_wechat || detail.email || detail.wechat || ""
      ).trim();
      reportForm.current_salary = formatSalaryThousands(detail.current_salary || "");
      reportForm.expected_salary = formatSalaryThousands(detail.expected_salary || "");
      reportForm.available_date = detail.available_date || "";
      reportForm.education_level = detail.education_level || "";
      reportForm.school = detail.school || "";
      reportForm.major = detail.major || "";
      reportForm.gender = detail.gender || "";
      reportForm.marital_status = detail.marital_status || "";
      var sourceParts = resolveSourceForForm(detail.source || "");
      reportForm.source = sourceParts.source;
      reportForm.source_other = sourceParts.source_other;
      var detailCity = String(detail.city || "").trim();
      if (detailCity) {
        reportForm.location = detailCity;
      }
    }

    function clearSelectedExistingCandidate() {
      var jobId = reportForm.job_id;
      var job = jobs.jobsState.items.find(function (j) {
        return Number(j.id) === Number(jobId);
      });
      reportMode.value = "new";
      selectedExistingCandidate.value = null;
      Object.assign(
        reportForm,
        ReportApi.emptyReportForm ? ReportApi.emptyReportForm() : {}
      );
      if (job && ReportApi.fillFromJob) {
        ReportApi.fillFromJob(reportForm, job, clientNameById);
      }
    }

    async function searchExistingCandidates() {
      existingCandidatePickerError.value = "";
      var keyword = (existingCandidatePickerQuery.value || "").trim();
      if (!keyword) {
        existingCandidatePickerItems.value = [];
        existingCandidatePickerLoading.value = false;
        return;
      }
      existingCandidatePickerLoading.value = true;
      try {
        var path = "/api/rms/candidates?q=" + encodeURIComponent(keyword);
        var r = await rmsRequest("GET", path);
        if (!r.ok) {
          existingCandidatePickerItems.value = [];
          existingCandidatePickerError.value = r.message;
          return;
        }
        existingCandidatePickerItems.value = Array.isArray(r.data) ? r.data : [];
      } finally {
        existingCandidatePickerLoading.value = false;
      }
    }

    function openExistingCandidatePicker() {
      existingCandidatePickerOpen.value = true;
      existingCandidatePickerQuery.value = "";
      existingCandidatePickerItems.value = [];
      existingCandidatePickerError.value = "";
      existingCandidatePickerDetail.value = null;
    }

    function closeExistingCandidatePicker() {
      hideExistingCandidatePopover();
      existingCandidatePickerOpen.value = false;
      if (existingCandidatePickerTimer) {
        clearTimeout(existingCandidatePickerTimer);
        existingCandidatePickerTimer = null;
      }
    }

    async function showExistingCandidatePickerDetail(c) {
      if (!c || c.id == null) return;
      existingCandidatePickerDetailLoading.value = true;
      existingCandidatePickerDetail.value = null;
      var r = await rmsRequest("GET", "/api/rms/candidates/" + c.id);
      existingCandidatePickerDetailLoading.value = false;
      if (!r.ok) {
        existingCandidatePickerError.value = r.message || ("请求失败（" + r.status + "）");
        return;
      }
      existingCandidatePickerDetail.value = r.data;
    }

    async function selectExistingCandidateForReport(c) {
      if (!c || c.id == null) return;
      hideExistingCandidatePopover();
      closeExistingCandidatePicker();
      reportMode.value = "existing";
      selectedExistingCandidate.value = {
        id: c.id,
        name: c.name || "",
        resume_id: c.resume_id != null ? c.resume_id : null,
        resume_file_name: c.resume_file_name || "",
        latest_resume_parse_summary: c.latest_resume_parse_summary || {},
      };
      clearReportResumeFile();
      var r = await rmsRequest("GET", "/api/rms/candidates/" + c.id);
      if (r.ok && r.data) {
        selectedExistingCandidate.value = Object.assign({}, selectedExistingCandidate.value, r.data);
        fillReportFormFromCandidate(r.data);
      }
    }

    function openCandidateReport(job) {
      reportError.value = "";
      reportSaving.value = false;
      reportResumeFile.value = null;
      resetReportDraftUi();
      resetExistingCandidateReportState();
      Object.assign(
        reportForm,
        ReportApi.emptyReportForm ? ReportApi.emptyReportForm() : {}
      );
      if (ReportApi.fillFromJob) {
        ReportApi.fillFromJob(reportForm, job, clientNameById);
      }
      viewMode.value = "candidateReport";
      installReportPageDragGuard();
    }

    function closeCandidateReport() {
      removeReportPageDragGuard();
      viewMode.value = null;
      reportError.value = "";
      clearReportResumeFile();
      resetExistingCandidateReportState();
    }

    function clearReportResumeFile() {
      if (ReportApi.clearAutoFilledFields) {
        ReportApi.clearAutoFilledFields(reportForm, reportAutoFilledFields);
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
      if (!file || !ReportApi.parseCandidateReportDraft) return;
      reportResumeDraftStatus.value = "parsing";
      reportResumeDraftError.value = "";
      clearReportRecognizedText();
      if (ReportApi.clearAutoFilledFields) {
        ReportApi.clearAutoFilledFields(reportForm, reportAutoFilledFields);
      }
      var r = await ReportApi.parseCandidateReportDraft(
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
      var data = r.data || {};
      var draft = data.draft_fields || {};
      var filled = ReportApi.applyDraftToForm
        ? ReportApi.applyDraftToForm(reportForm, draft, reportAutoFilledFields)
        : 0;
      formatReportSalaryField("current_salary");
      formatReportSalaryField("expected_salary");
      var n = ReportApi.countDraftFields
        ? ReportApi.countDraftFields(draft)
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
      var preview = String(data.parsed_text || "").trim();
      var rawPreview = String(data.parsed_text_raw || "").trim();
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
      var parseDuplicate = data.duplicate_detected === true;
      if (!parseDuplicate && (reportForm.phone || "").trim()) {
        var dupR = await rmsRequest("POST", "/api/rms/candidates/check-duplicate", {
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
      if (reportMode.value === "existing") {
        clearSelectedExistingCandidate();
      }
      revokeReportResumePdfPreview();
      reportResumeFile.value = file;
      setupReportFileMainPreview(file);
      parseReportResumeDraft(file);
    }

    function onReportResumeChange(ev) {
      var f = ev.target && ev.target.files && ev.target.files[0];
      onReportFilePicked(f || null);
    }

    function onReportDrop(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      reportResumeDragging.value = false;
      var f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0];
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
      var key = String(field || "").trim();
      if (!key) return;
      nextTick(function () {
        var root = document.querySelector("[data-rms-report-form]");
        var host = root
          ? root.querySelector('[data-rms-report-field="' + key + '"]')
          : document.querySelector('[data-rms-report-field="' + key + '"]');
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

    function resolveValidationField(message, field) {
      if (field) return field;
      return ReportApi.fieldKeyForValidationMessage
        ? ReportApi.fieldKeyForValidationMessage(message)
        : "";
    }

    function setReportError(message, field) {
      reportError.value = showValidationPrompt(message);
      focusReportField(resolveValidationField(message, field));
    }

    async function submitCandidateReport() {
      reportSaving.value = true;
      reportError.value = "";
      try {
        if (reportMode.value === "existing") {
          if (!selectedExistingCandidate.value || selectedExistingCandidate.value.id == null) {
            setReportError("请选择库内候选人");
            return;
          }
          if (!reportForm.job_id) {
            setReportError("请选择应聘岗位");
            return;
          }
          var body = {
            job_id: Number(reportForm.job_id),
            candidate_id: Number(selectedExistingCandidate.value.id),
            resume_id:
              selectedExistingCandidate.value.resume_id != null
                ? selectedExistingCandidate.value.resume_id
                : null,
          };
          var existingR = await rmsRequest("POST", "/api/rms/applications", body);
          if (!existingR.ok) {
            setReportError(userFacingRmsError(existingR));
            return;
          }
          toast("已推荐库内候选人", false);
          closeCandidateReport();
          await Promise.all([
            loadApplications(),
            loadCandidates(),
            loadDeliveryReview(),
          ]);
          return;
        }
        var reportValidation = ReportApi.validateReportForm
          ? ReportApi.validateReportForm(reportForm)
          : { ok: true, message: "" };
        if (!reportValidation.ok) {
          setReportError(reportValidation.message, reportValidation.field);
          return;
        }
        var submitR = await ReportApi.submitCandidateReport(
          reportForm,
          reportResumeFile.value,
          authHeaders,
          function (status, detail) {
            return workflowMessageForStatus(status, detail, "candidate-report");
          }
        );
        if (!submitR.ok) {
          if (isCandidateDuplicateError(submitR)) {
            await showCandidateDuplicateDialog();
            return;
          }
          setReportError(userFacingRmsError(submitR));
          return;
        }
        toast("推荐已提交", false);
        closeCandidateReport();
        await Promise.all([
          loadApplications(),
          loadCandidates(),
          loadDeliveryReview(),
        ]);
      } catch (err) {
        var msg = err && err.message ? err.message : String(err);
        setReportError("提交失败：" + msg);
      } finally {
        reportSaving.value = false;
      }
    }

    watch(
      function () {
        return existingCandidatePickerQuery.value;
      },
      function () {
        if (!existingCandidatePickerOpen.value) return;
        if (existingCandidatePickerTimer) clearTimeout(existingCandidatePickerTimer);
        existingCandidatePickerTimer = setTimeout(function () {
          existingCandidatePickerTimer = null;
          searchExistingCandidates();
        }, 300);
      }
    );

    return {
      reportForm: reportForm,
      reportSaving: reportSaving,
      reportError: reportError,
      reportResumeFile: reportResumeFile,
      reportResumeInput: reportResumeInput,
      reportResumeDraftStatus: reportResumeDraftStatus,
      reportResumeDraftError: reportResumeDraftError,
      reportResumePdfPreviewUrl: reportResumePdfPreviewUrl,
      reportResumeTextPreview: reportResumeTextPreview,
      reportResumeTextPreviewTruncated: reportResumeTextPreviewTruncated,
      reportResumePreviewText: reportResumePreviewText,
      reportResumePreviewError: reportResumePreviewError,
      reportResumePreviewWarning: reportResumePreviewWarning,
      reportResumePreviewRawText: reportResumePreviewRawText,
      reportResumePreviewLength: reportResumePreviewLength,
      reportResumePreviewRawLength: reportResumePreviewRawLength,
      reportShowRawExtractDebug: reportShowRawExtractDebug,
      reportResumeDragging: reportResumeDragging,
      formatReportFileSize: formatReportFileSize,
      reportMode: reportMode,
      selectedExistingCandidate: selectedExistingCandidate,
      existingCandidatePickerOpen: existingCandidatePickerOpen,
      existingCandidatePickerQuery: existingCandidatePickerQuery,
      existingCandidatePickerItems: existingCandidatePickerItems,
      existingCandidatePickerLoading: existingCandidatePickerLoading,
      existingCandidatePickerError: existingCandidatePickerError,
      existingCandidatePickerDetail: existingCandidatePickerDetail,
      existingCandidatePickerDetailLoading: existingCandidatePickerDetailLoading,
      existingCandidateHoverCard: existingCandidateHoverCard,
      existingCandidatePopoverStyle: existingCandidatePopoverStyle,
      openExistingCandidatePicker: openExistingCandidatePicker,
      closeExistingCandidatePicker: closeExistingCandidatePicker,
      showExistingCandidatePopover: showExistingCandidatePopover,
      moveExistingCandidatePopover: moveExistingCandidatePopover,
      scheduleHideExistingCandidatePopover: scheduleHideExistingCandidatePopover,
      keepExistingCandidatePopover: keepExistingCandidatePopover,
      hideExistingCandidatePopover: hideExistingCandidatePopover,
      selectExistingCandidateForReport: selectExistingCandidateForReport,
      clearSelectedExistingCandidate: clearSelectedExistingCandidate,
      formatReportSalaryField: formatReportSalaryField,
      openCandidateReport: openCandidateReport,
      closeCandidateReport: closeCandidateReport,
      onReportResumeChange: onReportResumeChange,
      onReportDrop: onReportDrop,
      onReportDragEnter: onReportDragEnter,
      onReportDragLeave: onReportDragLeave,
      clearReportResumeFile: clearReportResumeFile,
      submitCandidateReport: submitCandidateReport,
    };
  }

  global.RmsCandidateReport = {
    emptyReportForm: emptyReportForm,
    fillFromJob: fillFromJob,
    applyDraftToForm: applyDraftToForm,
    clearAutoFilledFields: clearAutoFilledFields,
    countDraftFields: countDraftFields,
    formatFileSize: formatFileSize,
    validateReportForm: validateReportForm,
    validateCandidateCreateForm: validateCandidateCreateForm,
    validateCandidateModalForm: validateCandidateModalForm,
    fieldKeyForValidationMessage: fieldKeyForValidationMessage,
    resolveSourceForForm: resolveSourceForForm,
    resolveSourceForSave: resolveSourceForSave,
    parseCandidateReportDraft: parseCandidateReportDraft,
    submitCandidateReport: submitCandidateReport,
    createDeliveryReviewApi: createDeliveryReviewApi,
    PARSE_DRAFT_URL: PARSE_DRAFT_URL,
  };

  global.CrmRmsReport = Object.assign(global.CrmRmsReport || {}, {
    createReportState: createReportState,
  });
})(typeof window !== "undefined" ? window : globalThis);
