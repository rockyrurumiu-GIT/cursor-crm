/**
 * RMS shared pure helpers (Phase R1 split).
 */
(function (global) {
  "use strict";

  var JOB_SALARY_CAP_MIN = 1000;
  var JOB_SALARY_CAP_MAX = 99999;
  var REPORT_LOCAL_TEXT_PREVIEW_MAX = 2000;

  function authHeaders() {
    return typeof global.crmAuthHeader === "function" ? global.crmAuthHeader() : {};
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
    var d = formatDetail(detail);
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

  function stripSalaryCommas(s) {
    return String(s == null ? "" : s).replace(/,/g, "").trim();
  }

  function formatSalaryThousands(s) {
    var raw = stripSalaryCommas(s);
    if (!raw) return "";
    if (/[kK万千%]/.test(raw)) return raw;
    if (!/^-?\d+(\.\d+)?$/.test(raw)) return raw;
    var n = Number(raw);
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
    var digits = stripJobSalaryCapInput(value);
    if (!digits) return "";
    var n = Number(digits);
    if (!Number.isFinite(n) || !jobSalaryCapInRange(n)) return digits;
    return n.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  }

  function fuzzyMatch(haystack, needle) {
    var n = (needle || "").trim().toLowerCase();
    if (!n) return true;
    return String(haystack || "").toLowerCase().indexOf(n) !== -1;
  }

  function coreToast(msg, isError) {
    if (global.crmToast) {
      if (isError && global.crmToast.error) global.crmToast.error(msg);
      else if (!isError && global.crmToast.success) global.crmToast.success(msg);
      else if (global.crmToast.show) global.crmToast.show(msg);
    } else {
      global.alert(msg);
    }
  }

  function showValidationPrompt(message) {
    var msg = String(message || "").trim() || "提交未成功，请检查必填项";
    try {
      coreToast(msg, true);
    } catch (e) {
      /* toast optional */
    }
    return msg;
  }

  function showRmsBootError(msg) {
    var el = global.document && global.document.getElementById("rms-app");
    if (!el) return;
    el.removeAttribute("v-cloak");
    if (el.querySelector("[data-rms-boot-error]")) return;
    var box = global.document.createElement("div");
    box.setAttribute("data-rms-boot-error", "1");
    box.className = "rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 mb-4";
    box.textContent = msg;
    el.insertBefore(box, el.firstChild);
  }

  async function rmsRequest(method, url, body) {
    var headers = Object.assign({}, authHeaders());
    var opts = { method: method, headers: headers, credentials: "same-origin" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    var resp;
    try {
      resp = await fetch(url, opts);
    } catch (e) {
      var connMsg = e && e.message ? e.message : String(e);
      return {
        ok: false,
        status: 0,
        message: "无法连接服务，请确认后端已启动（" + connMsg + "）",
      };
    }
    var payload = null;
    var ct = resp.headers.get("content-type") || "";
    if (ct.indexOf("application/json") !== -1) {
      try {
        payload = await resp.json();
      } catch (e2) {
        payload = null;
      }
    } else if (!resp.ok) {
      try {
        payload = { detail: await resp.text() };
      } catch (e3) {
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

  global.CrmRmsCore = {
    JOB_SALARY_CAP_MIN: JOB_SALARY_CAP_MIN,
    JOB_SALARY_CAP_MAX: JOB_SALARY_CAP_MAX,
    REPORT_LOCAL_TEXT_PREVIEW_MAX: REPORT_LOCAL_TEXT_PREVIEW_MAX,
    authHeaders: authHeaders,
    formatDetail: formatDetail,
    messageForStatus: messageForStatus,
    workflowMessageForStatus: workflowMessageForStatus,
    stripSalaryCommas: stripSalaryCommas,
    formatSalaryThousands: formatSalaryThousands,
    stripJobSalaryCapInput: stripJobSalaryCapInput,
    jobSalaryCapInRange: jobSalaryCapInRange,
    formatJobSalaryCapDisplay: formatJobSalaryCapDisplay,
    fuzzyMatch: fuzzyMatch,
    showValidationPrompt: showValidationPrompt,
    showRmsBootError: showRmsBootError,
    rmsRequest: rmsRequest,
  };
})(typeof window !== "undefined" ? window : globalThis);
