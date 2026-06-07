/**
 * Shared dashboard widget helpers (charts, colors, config) for CRM + RMS dashboards.
 */
(function (global) {
  "use strict";

  var EXTRA_RENDER_LABELS = { doughnut: "环形图", horizontal_bar: "横向排名（柱图）" };
  var METRIC_LABELS = { count: "计数", sum: "求和", avg: "平均", min: "最小", max: "最大" };
  var CHART_WIDGET_TYPES = ["bar", "horizontal_bar", "pie", "line"];
  var DATA_WIDGET_TYPES = ["number"].concat(CHART_WIDGET_TYPES);
  var TYPE_LABELS = {
    number: "数字", bar: "柱状", horizontal_bar: "横向排名", pie: "环形", line: "折线",
    rich_text: "文本", iframe: "网页", roster_summary: "花名册概览", rms_block: "招聘预设",
  };
  var TYPE_ICONS = {
    number: "#", bar: "▮", horizontal_bar: "▤", pie: "◔", line: "📈",
    rich_text: "¶", iframe: "▭", roster_summary: "▦", rms_block: "▦",
  };

  var TWENTY_HUE_BASES = [
    ["red", "Red", "#ef9189"], ["ruby", "Ruby", "#e07a9a"], ["crimson", "Crimson", "#d96a7a"],
    ["tomato", "Tomato", "#e69345"], ["orange", "Orange", "#f6b66d"], ["amber", "Amber", "#e8c06a"],
    ["yellow", "Yellow", "#e6d56a"], ["lime", "Lime", "#b8d86a"], ["grass", "Grass", "#8ec78a"],
    ["green", "Green", "#63aa82"], ["jade", "Jade", "#5ab89a"], ["mint", "Mint", "#6bc4b8"],
    ["turquoise", "Turquoise", "#5ab8c4"], ["cyan", "Cyan", "#5ab0d8"], ["sky", "Sky", "#6aaee8"],
    ["blue", "Blue", "#6f8dde"], ["iris", "Iris", "#8a85de"], ["violet", "Violet", "#9875d1"],
    ["purple", "Purple", "#b99be8"], ["plum", "Plum", "#c49ad4"], ["pink", "Pink", "#e8a0c4"],
    ["bronze", "Bronze", "#c9a87a"], ["gold", "Gold", "#d6b860"], ["brown", "Brown", "#a88872"],
    ["gray", "Gray", "#8993a0"],
  ];

  function hexRgb(hex) {
    var m = (hex || "#000000").replace("#", "");
    return [parseInt(m.substring(0, 2), 16), parseInt(m.substring(2, 4), 16), parseInt(m.substring(4, 6), 16)];
  }
  function rgbHex(r, g, b) {
    return "#" + [r, g, b].map(function (x) {
      return Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0");
    }).join("");
  }
  function mixHex(a, b, t) {
    var ar = hexRgb(a), br = hexRgb(b);
    return rgbHex(ar[0] + (br[0] - ar[0]) * t, ar[1] + (br[1] - ar[1]) * t, ar[2] + (br[2] - ar[2]) * t);
  }
  function buildHueShades(mid) {
    return [mixHex(mid, "#ffffff", 0.72), mixHex(mid, "#ffffff", 0.42), mid, mixHex(mid, "#000000", 0.14), mixHex(mid, "#000000", 0.3)];
  }
  var TWENTY_COLOR_ROWS = TWENTY_HUE_BASES.map(function (t) {
    return { key: t[0], label: t[1], shades: buildHueShades(t[2]) };
  });

  function colorRowOf(key) {
    var k = String(key || "blue").toLowerCase();
    var row = TWENTY_COLOR_ROWS.find(function (r) { return r.key === k; });
    return row || TWENTY_COLOR_ROWS.find(function (r) { return r.key === "blue"; });
  }
  function selectedShade(cfg) {
    var idx = Number(cfg && cfg.color_shade);
    if (!Number.isFinite(idx) || idx < 0 || idx > 4) return 2;
    return idx;
  }
  function widgetPalette(cfg) { return colorRowOf(cfg && cfg.color).shades.slice(); }
  function shadeRamp(cfg, n) {
    var pal = widgetPalette(cfg);
    var order = [3, 2, 1, 0, 4];
    var out = [];
    for (var i = 0; i < n; i++) out.push(pal[order[i % order.length]]);
    return out;
  }
  function shadeHover(cfg) { return widgetPalette(cfg)[4]; }
  function themeOf(cfgOrColor) {
    var cfg = typeof cfgOrColor === "string" ? { color: cfgOrColor, color_shade: 2 } : (cfgOrColor || {});
    var pal = widgetPalette(cfg);
    return { base: pal[selectedShade(cfg)] };
  }
  function fmtNum(v) {
    if (v == null) return "0";
    var n = Number(v);
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  function hexA(hex, a) {
    var m = hex.replace("#", "");
    var r = parseInt(m.substring(0, 2), 16), g = parseInt(m.substring(2, 4), 16), b = parseInt(m.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + a + ")";
  }
  function dataLabel(prefix) {
    return function (v) {
      if (v == null || v === "" || Number(v) === 0) return "";
      return prefix + fmtNum(v);
    };
  }
  function whiteTooltip(labelFn) {
    return {
      backgroundColor: "#ffffff", titleColor: "#1f2328", bodyColor: "#6b7280",
      borderColor: "#e6e8eb", borderWidth: 1, padding: 12,
      callbacks: { label: labelFn },
    };
  }
  function cartesianScales(xGrid) {
    return {
      x: { grid: xGrid, border: { display: false }, ticks: { font: { size: 10 }, color: "#b0b5bc", maxRotation: 0 } },
      y: { beginAtZero: true, grid: { color: "#f4f5f7" }, border: { display: false }, ticks: { font: { size: 10 }, color: "#b0b5bc", padding: 6 } },
    };
  }
  function doughnutChartOptions(cfg, prefix, totalText) {
    return {
      responsive: true, maintainAspectRatio: false, cutout: "74%",
      plugins: {
        legend: { display: false }, datalabels: { display: false },
        centerTotal: { display: cfg.show_value_center !== false, text: totalText },
        tooltip: whiteTooltip(function (c) { return c.label + ": " + prefix + fmtNum(c.parsed); }),
      },
    };
  }
  function barChartOptions(cfg, prefix) {
    return {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: cfg.data_labels ? 18 : 6 } },
      plugins: {
        legend: { display: false },
        datalabels: cfg.data_labels
          ? { display: true, anchor: "end", align: "end", clip: false, color: "#98a2b3", font: { size: 10, weight: "500" }, formatter: dataLabel(prefix) }
          : { display: false },
        tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.y); }),
      },
      scales: cartesianScales({ display: false }),
    };
  }
  function lineChartOptions(cfg, prefix) {
    return {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      elements: { point: { hoverRadius: 6, hitRadius: 12 } },
      plugins: {
        legend: { display: false },
        datalabels: cfg.data_labels
          ? { display: true, align: "top", color: "#98a2b3", font: { size: 10 }, formatter: dataLabel(prefix) }
          : { display: false },
        tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.y); }),
      },
      scales: cartesianScales({ color: "#f5f6f8" }),
    };
  }

  var centerTotalPlugin = {
    id: "centerTotal",
    afterDraw: function (chart) {
      var opt = chart.options.plugins.centerTotal;
      if (!opt || !opt.display) return;
      var ctx = chart.ctx;
      var meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !meta.data[0]) return;
      var x = meta.data[0].x, y = meta.data[0].y;
      ctx.save();
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#1f2328";
      ctx.font = "600 22px system-ui, sans-serif";
      ctx.fillText(opt.text, x, y - 7);
      ctx.fillStyle = "#a8b0bd";
      ctx.font = "400 11px system-ui, sans-serif";
      ctx.fillText("总计", x, y + 15);
      ctx.restore();
    },
  };

  function installChartPlugins(Chart, ChartDataLabels) {
    if (typeof Chart === "undefined") return;
    try {
      if (ChartDataLabels) {
        Chart.register(ChartDataLabels);
        Chart.defaults.set("plugins.datalabels", { display: false });
      }
      Chart.register(centerTotalPlugin);
    } catch (e) {
      console.warn("[dashboard-widget-kit] chart plugin install skipped:", e);
    }
  }

  function chartCanvasId(w, viewIndex) {
    if (viewIndex == null || viewIndex === undefined) return "chart-" + w.id;
    return "chart-" + w.id + "-ev-" + viewIndex;
  }

  function blankWidget(defaults) {
    defaults = defaults || {};
    return {
      id: null,
      title: defaults.title || "新组件",
      widget_type: defaults.widget_type || "number",
      source_key: defaults.source_key || "clients",
      config: Object.assign({
        metric: "count", field: "", group_by: "", date_group: "month",
        filters: [], limit: 20, color: "green", color_shade: 2, sort: "value_desc",
        show_legend: true, show_value_center: true, data_labels: false, hide_empty: false,
        url: "", content: "", prefix: "", suffix: "",
        client_id: null, include_left: false, block: "kpi_jobs",
        extra_views: [],
      }, defaults.config || {}),
      x: defaults.x != null ? defaults.x : 0,
      y: defaults.y != null ? defaults.y : 0,
      w: defaults.w != null ? defaults.w : 6,
      h: defaults.h != null ? defaults.h : 5,
    };
  }

  function buildConfig(f, rosterScope, isDateGroupFn, isChartFn) {
    if (f.widget_type === "iframe") return { url: f.config.url };
    if (f.widget_type === "rich_text") return { content: f.config.content };
    if (f.widget_type === "rms_block") return { block: f.config.block || "kpi_jobs" };
    if (f.widget_type === "roster_summary") {
      return {
        client_id: rosterScope === "client" ? (f.config.client_id || null) : null,
        include_left: !!f.config.include_left,
      };
    }
    var c = f.config;
    var out = {
      metric: c.metric, field: c.field, group_by: c.group_by,
      filters: (c.filters || []).filter(function (x) { return x.field; }),
      prefix: c.prefix || "", suffix: c.suffix || "",
    };
    if (isDateGroupFn && isDateGroupFn()) { out.group_by = ""; out.date_group = c.date_group; }
    if (isChartFn && isChartFn()) {
      var lim = Number(c.limit);
      out.limit = Number.isFinite(lim) && lim >= 1 ? lim : 20;
      out.color = c.color;
      out.color_shade = Number(c.color_shade);
      if (!Number.isFinite(out.color_shade) || out.color_shade < 0 || out.color_shade > 4) out.color_shade = 2;
      out.sort = c.sort;
      out.show_legend = !!c.show_legend;
      out.show_value_center = !!c.show_value_center;
      out.data_labels = !!c.data_labels;
      out.hide_empty = !!c.hide_empty;
      out.extra_views = (c.extra_views || []).map(function (ev) {
        var row = { render: ev.render, x: Number(ev.x) || 0, y: Number(ev.y) || 0, w: Number(ev.w) || 4, h: Number(ev.h) || 4 };
        var t = (ev.title || "").trim();
        if (t) row.title = t;
        if (ev.render === "horizontal_bar" && ev.limit != null && ev.limit !== "") row.limit = Number(ev.limit);
        return row;
      });
    }
    return out;
  }

  function renderCrmChart(chartInstances, destroyChartKey, w, data, opts) {
    opts = opts || {};
    if (!data || data.status !== "ok" || data.kind !== "series") return;
    var canvasId = opts.canvasId || chartCanvasId(w, opts.viewIndex);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    destroyChartKey(canvasId);

    var cfg = w.config || {};
    var labels = data.labels || [];
    var values = data.values || [];
    var prefix = data.prefix || "";
    var pal = widgetPalette(cfg);
    var accent = pal[selectedShade(cfg)];
    var render = opts.render || null;

    if (render === "doughnut" || (!render && w.widget_type === "pie")) {
      chartInstances[canvasId] = new Chart(canvas, {
        type: "doughnut",
        data: { labels: labels, datasets: [{ data: values, backgroundColor: shadeRamp(cfg, labels.length), borderColor: "#fff", borderWidth: 2 }] },
        options: doughnutChartOptions(cfg, prefix, prefix + fmtNum(data.total)),
      });
      return;
    }
    if (render === "horizontal_bar" || (!render && w.widget_type === "horizontal_bar")) {
      var topN = opts.limit != null ? opts.limit : (cfg.limit != null ? cfg.limit : 6);
      chartInstances[canvasId] = new Chart(canvas, {
        type: "bar",
        data: {
          labels: labels.slice(0, topN),
          datasets: [{ data: values.slice(0, topN), backgroundColor: shadeRamp(cfg, topN), borderRadius: 6, barPercentage: 0.72 }],
        },
        options: {
          responsive: true, maintainAspectRatio: false, indexAxis: "y",
          plugins: { legend: { display: false }, datalabels: { display: false }, tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.x); }) },
          scales: {
            x: { beginAtZero: true, grid: { color: "#f2f3f5" }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
            y: { grid: { display: false }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
          },
        },
      });
      return;
    }
    if (!render && w.widget_type === "bar") {
      chartInstances[canvasId] = new Chart(canvas, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [{ label: w.title, data: values, backgroundColor: shadeRamp(cfg, values.length), hoverBackgroundColor: shadeHover(cfg), borderRadius: 6, categoryPercentage: 0.65, barPercentage: 0.85 }],
        },
        options: barChartOptions(cfg, prefix),
      });
      return;
    }
    if (!render && w.widget_type === "line") {
      chartInstances[canvasId] = new Chart(canvas, {
        type: "line",
        data: {
          labels: labels,
          datasets: [{ label: w.title, data: values, borderColor: accent, backgroundColor: hexA(pal[0], 0.12), fill: true, tension: 0.25, pointRadius: 0, pointBackgroundColor: accent, borderWidth: 2 }],
        },
        options: lineChartOptions(cfg, prefix),
      });
    }
  }

  global.DashboardWidgetKit = {
    EXTRA_RENDER_LABELS: EXTRA_RENDER_LABELS,
    METRIC_LABELS: METRIC_LABELS,
    CHART_WIDGET_TYPES: CHART_WIDGET_TYPES,
    DATA_WIDGET_TYPES: DATA_WIDGET_TYPES,
    TYPE_LABELS: TYPE_LABELS,
    TYPE_ICONS: TYPE_ICONS,
    TWENTY_COLOR_ROWS: TWENTY_COLOR_ROWS,
    colorRowOf: colorRowOf,
    selectedShade: selectedShade,
    widgetPalette: widgetPalette,
    shadeRamp: shadeRamp,
    shadeHover: shadeHover,
    themeOf: themeOf,
    fmtNum: fmtNum,
    chartCanvasId: chartCanvasId,
    blankWidget: blankWidget,
    buildConfig: buildConfig,
    renderCrmChart: renderCrmChart,
    installChartPlugins: installChartPlugins,
    extraRenderLabel: function (render) { return EXTRA_RENDER_LABELS[render] || render; },
  };
})(window);
