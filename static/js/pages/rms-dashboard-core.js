/**
 * RMS Dashboard core helpers.
 * Pure helpers only. No Vue state, no DOM mutation except chart cleanup.
 */
(function (global) {
  "use strict";

  var JOB_STAGE_CHART_COLORS = {
    pushed: "#7B96B8",
    internal: "#88A992",
    client: "#D6A461",
    interviewed: "#9389AE",
    passed: "#5B8A72",
    pendingClient: "#B4C4D8",
    scheduling: "#A8B8C8",
    pendingInterview: "#C2D4C8",
    abandoned: "#CD9180",
  };

  var RMS_CHART_GRID_COLOR = "rgba(208, 215, 222, 0.45)";
  var RMS_CHART_TICK_COLOR = "#8c959f";
  var RMS_CHART_LABEL_COLOR = "#24292f";
  var RMS_CHART_BAR_RADIUS = 8;
  var RMS_CHART_BAR_THICKNESS = 28;
  var RMS_PRESET_PALETTE = [
    "#8EA4C1",
    "#9AB39F",
    "#D2AA6A",
    "#C69383",
    "#9B93B7",
    "#A8B5C6",
    "#A3B8A8",
    "#D8C08A",
  ];

  var chartInstances = {};

  function getChartInstances() {
    return chartInstances;
  }

  function truncateJobLabel(title, maxLen) {
    var t = String(title || "").trim() || "—";
    maxLen = maxLen || 10;
    return t.length > maxLen ? t.slice(0, maxLen) + "…" : t;
  }

  function formatRmsDate(value) {
    if (value == null || value === "") return "—";
    var s = String(value).trim().slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : "—";
  }

  function api(method, path, body) {
    var opts = {
      method: method,
      credentials: "same-origin",
      headers: Object.assign({}, global.crmAuthHeader ? global.crmAuthHeader() : {}),
    };
    if (body != null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (text) {
          var detail = "";
          try {
            var b = JSON.parse(text || "{}");
            detail = b && b.detail ? b.detail : "";
          } catch (_) {
            detail = text || "";
          }
          throw new Error(detail || r.statusText || "请求失败");
        });
      }
      if (r.status === 204) return null;
      return r.json();
    });
  }

  function apiGet(path) {
    return api("GET", path);
  }

  function apiGetOptional(path) {
    return fetch(path, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) return null;
      return r.json();
    });
  }

  function cloneFilters(src) {
    src = src || {};
    return {
      client_id: src.client_id != null ? String(src.client_id) : "",
      job_ids: Array.isArray(src.job_ids) ? src.job_ids.map(String) : [],
      job_ids_text: src.job_ids_text != null ? String(src.job_ids_text) : "",
      delivery_user_id: src.delivery_user_id != null ? String(src.delivery_user_id) : "",
      recruiter_user_id: src.recruiter_user_id != null ? String(src.recruiter_user_id) : "",
      city: src.city != null ? String(src.city) : "",
      date_from: src.date_from != null ? String(src.date_from) : "",
      date_to: src.date_to != null ? String(src.date_to) : "",
      include_zero_resume_jobs: !!src.include_zero_resume_jobs,
    };
  }

  function buildQuery(filters) {
    var params = new URLSearchParams();
    Object.keys(filters).forEach(function (k) {
      if (k === "job_ids" || k === "job_ids_text") return;
      var v = filters[k];
      if (v !== "" && v != null) params.set(k, String(v));
    });
    var jobIds = filters.job_ids;
    if (Array.isArray(jobIds) && jobIds.length) {
      params.set("job_ids", jobIds.map(String).join(","));
    } else if (filters.job_ids_text) {
      var textIds = String(filters.job_ids_text).split(",").map(function (s) { return s.trim(); }).filter(Boolean);
      if (textIds.length) params.set("job_ids", textIds.join(","));
    }
    var qs = params.toString();
    return qs ? "?" + qs : "";
  }

  function widgetBlock(w) {
    if (!w) return "";
    if (w.widget_type === "rms_block") return (w.config && w.config.block) || "";
    return "";
  }

  function chartCanvasId(w) {
    return "rms-chart-" + w.id;
  }

  function chartsAvailable() {
    return typeof Chart !== "undefined";
  }

  function destroyChartKey(id) {
    if (chartInstances[id]) {
      chartInstances[id].destroy();
      delete chartInstances[id];
    }
  }

  function destroyAllCharts() {
    Object.keys(chartInstances).forEach(destroyChartKey);
  }

  function whiteTooltip(labelFn) {
    return {
      backgroundColor: "#ffffff",
      titleColor: "#1f2328",
      bodyColor: "#6b7280",
      borderColor: "#e6e8eb",
      borderWidth: 1,
      padding: 12,
      callbacks: { label: labelFn },
    };
  }

  function safeRenderChart(id, renderFn) {
    if (!chartsAvailable()) return;
    try {
      renderFn();
    } catch (chartErr) {
      console.warn("[rms-dashboard] chart render skipped (" + id + "):", chartErr);
    }
  }

  function rmsShadeRamp(n) {
    return RMS_PRESET_PALETTE.slice(0, Math.max(1, n)).concat();
  }

  function parsePassRate(rateStr) {
    if (!rateStr || rateStr === "—") return 0;
    var n = parseFloat(String(rateStr).replace("%", ""));
    return Number.isFinite(n) ? n : 0;
  }

  function horizontalBarOptions(prefix, suffix) {
    prefix = prefix != null ? String(prefix) : "";
    suffix = suffix != null ? String(suffix) : "";
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      animation: { duration: 250 },
      plugins: {
        legend: { display: false },
        datalabels: { display: false },
        tooltip: whiteTooltip(function (c) {
          return prefix + String(c.parsed.x) + suffix;
        }),
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: RMS_CHART_GRID_COLOR, drawBorder: false },
          border: { display: false },
          ticks: { color: RMS_CHART_TICK_COLOR, font: { size: 10 }, precision: 0 },
        },
        y: {
          grid: { display: false, drawBorder: false },
          border: { display: false },
          ticks: { color: RMS_CHART_TICK_COLOR, font: { size: 10 } },
        },
      },
    };
  }

  function groupedBarOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: { boxWidth: 10, padding: 8, font: { size: 10 }, color: "#6b7280" },
        },
        datalabels: { display: false },
        tooltip: whiteTooltip(function (c) {
          return c.dataset.label + ": " + String(c.parsed.y);
        }),
      },
      scales: {
        x: {
          grid: { display: false },
          border: { display: false },
          ticks: { color: "#8f949b", font: { size: 9 }, maxRotation: 45, minRotation: 0 },
        },
        y: {
          beginAtZero: true,
          grid: { color: "#f2f3f5" },
          border: { display: false },
          ticks: { color: "#8f949b", font: { size: 10 }, precision: 0 },
        },
      },
    };
  }

  global.CrmRmsDashboardCore = {
    JOB_STAGE_CHART_COLORS: JOB_STAGE_CHART_COLORS,
    RMS_CHART_GRID_COLOR: RMS_CHART_GRID_COLOR,
    RMS_CHART_TICK_COLOR: RMS_CHART_TICK_COLOR,
    RMS_CHART_LABEL_COLOR: RMS_CHART_LABEL_COLOR,
    RMS_CHART_BAR_RADIUS: RMS_CHART_BAR_RADIUS,
    RMS_CHART_BAR_THICKNESS: RMS_CHART_BAR_THICKNESS,
    RMS_PRESET_PALETTE: RMS_PRESET_PALETTE,

    getChartInstances: getChartInstances,
    truncateJobLabel: truncateJobLabel,
    formatRmsDate: formatRmsDate,
    api: api,
    apiGet: apiGet,
    apiGetOptional: apiGetOptional,
    cloneFilters: cloneFilters,
    buildQuery: buildQuery,
    widgetBlock: widgetBlock,
    chartCanvasId: chartCanvasId,
    chartsAvailable: chartsAvailable,
    destroyChartKey: destroyChartKey,
    destroyAllCharts: destroyAllCharts,
    whiteTooltip: whiteTooltip,
    safeRenderChart: safeRenderChart,
    rmsShadeRamp: rmsShadeRamp,
    parsePassRate: parsePassRate,
    horizontalBarOptions: horizontalBarOptions,
    groupedBarOptions: groupedBarOptions,
  };
})(typeof window !== "undefined" ? window : globalThis);
