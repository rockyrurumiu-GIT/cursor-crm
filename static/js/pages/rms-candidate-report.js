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
      return { ok: false, status: resp.status, message: messageForStatus(resp.status, detail) };
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
      submitDeliveryReview: async function (appId, result) {
        return rmsRequest("POST", "/api/rms/applications/" + appId + "/delivery-review", {
          result: result,
          note: "",
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
    parseCandidateReportDraft: parseCandidateReportDraft,
    submitCandidateReport: submitCandidateReport,
    createDeliveryReviewApi: createDeliveryReviewApi,
    PARSE_DRAFT_URL: PARSE_DRAFT_URL,
  };
})(typeof window !== "undefined" ? window : globalThis);
