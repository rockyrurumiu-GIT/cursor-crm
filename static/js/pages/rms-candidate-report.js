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
    "学校": "school",
    "专业": "major",
    "性别": "gender",
    "婚姻状况": "marital_status",
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
      { field: "source", label: "来源", value: (form.source || "").trim() },
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

  function _runRequiredChecks(form, extraChecks) {
    if (!form || !form.job_id) {
      return { ok: false, message: "请选择应聘岗位", field: "" };
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
    var normalized = form || {};
    return _runRequiredChecks(
      {
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
        school: normalized.school,
        major: normalized.major,
        gender: normalized.gender,
        marital_status: normalized.marital_status,
      },
      []
    );
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
      source: form.source || "",
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

  global.RmsCandidateReport = {
    emptyReportForm: emptyReportForm,
    fillFromJob: fillFromJob,
    applyDraftToForm: applyDraftToForm,
    clearAutoFilledFields: clearAutoFilledFields,
    countDraftFields: countDraftFields,
    formatFileSize: formatFileSize,
    validateReportForm: validateReportForm,
    validateCandidateCreateForm: validateCandidateCreateForm,
    fieldKeyForValidationMessage: fieldKeyForValidationMessage,
    parseCandidateReportDraft: parseCandidateReportDraft,
    submitCandidateReport: submitCandidateReport,
    createDeliveryReviewApi: createDeliveryReviewApi,
    PARSE_DRAFT_URL: PARSE_DRAFT_URL,
  };
})(typeof window !== "undefined" ? window : globalThis);
