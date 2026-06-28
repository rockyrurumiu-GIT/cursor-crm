/**
 * Shared dashboard widget helpers (charts, colors, config) for CRM + RMS dashboards.
 */
(function (global) {
  "use strict";

  var EXTRA_RENDER_LABELS = { doughnut: "环形图", horizontal_bar: "横向排名（柱图）" };
  var METRIC_LABELS = { count: "计数", sum: "求和", avg: "平均", min: "最小", max: "最大" };
  var CHART_WIDGET_TYPES = ["bar", "horizontal_bar", "pie", "line", "featured_line", "line_1", "featured_bar"];
  var LINE1_VALUE_MODES = ["sum", "latest", "average", "max"];
  var DATA_WIDGET_TYPES = ["number"].concat(CHART_WIDGET_TYPES);
  var TYPE_LABELS = {
    number: "数字", bar: "柱状", horizontal_bar: "横向排名", pie: "环形", line: "折线",
    featured_line: "重点折线", line_1: "折线1", featured_bar: "重点柱状",
    rich_text: "文本", iframe: "网页", roster_summary: "花名册概览", rms_block: "招聘预设",
  };
  var TYPE_ICONS = {
    number: "#", bar: "▮", horizontal_bar: "▤", pie: "◔", line: "📈",
    featured_line: "◉", line_1: "〽", featured_bar: "▮",
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

  var GROUPED_COMPOSITION_COLORS = ["#1e96e8", "#36c8e8", "#ffc04d", "#22c55e", "#a855f7", "#ef4444"];
  var GROUPED_COMPOSITION_MAX_SEGMENTS = 6;
  var GROUPED_COMPOSITION_OTHER_LABEL = "其他";

  function primarySortToLegacy(sort) {
    var map = {
      position_asc: "label_asc", position_desc: "label_desc",
      sum_asc: "value_asc", sum_desc: "value_desc", manual: "label_asc",
    };
    return map[sort] || sort;
  }

  function normalizeWidgetConfig(config) {
    var c = config || {};
    var aggregateField = c.aggregate_field != null ? c.aggregate_field : (c.field || "");
    aggregateField = String(aggregateField).trim();
    var primaryAxisField = c.primary_axis_field != null ? c.primary_axis_field : (c.group_by || "");
    primaryAxisField = String(primaryAxisField).trim();
    var dateGroup = String(c.date_group || "").trim();
    if (dateGroup && !primaryAxisField) primaryAxisField = String(c.group_by || "created_at").trim();
    var displayDataLabel = "display_data_label" in c ? !!c.display_data_label : !!c.data_labels;
    var displayLegend = "display_legend" in c ? !!c.display_legend : (c.show_legend !== false);
    var omitNull = "omit_null_values" in c ? !!c.omit_null_values : !!c.hide_empty;
    var primarySort = String(c.primary_axis_sort || c.sort || "position_asc").trim();
    primarySort = { value_asc: "sum_asc", value_desc: "sum_desc" }[primarySort] || primarySort;
    var rawOrder = c.primary_axis_order;
    var primaryAxisOrder = [];
    if (Array.isArray(rawOrder)) {
      rawOrder.forEach(function (item) {
        var s = String(item || "").trim();
        if (s) primaryAxisOrder.push(s);
      });
    }
    return {
      metric: String(c.metric || "count").trim(),
      aggregate_field: aggregateField,
      field: aggregateField,
      primary_axis_field: primaryAxisField,
      group_by: primaryAxisField,
      date_group: dateGroup,
      primary_axis_sort: primarySort,
      sort: primarySortToLegacy(primarySort),
      primary_axis_order: primaryAxisOrder,
      secondary_axis_field: String(c.secondary_axis_field || "").trim(),
      secondary_axis_sort: String(c.secondary_axis_sort || "label_asc").trim(),
      omit_null_values: omitNull,
      hide_empty: omitNull,
      range_min: c.range_min == null || c.range_min === "" ? "" : String(c.range_min).trim(),
      range_max: c.range_max == null || c.range_max === "" ? "" : String(c.range_max).trim(),
      group_mode: String(c.group_mode || "stacked").trim(),
      axis_name_display: String(c.axis_name_display || "none").trim(),
      display_data_label: displayDataLabel,
      data_labels: displayDataLabel,
      display_legend: displayLegend,
      show_legend: displayLegend,
      filters: Array.isArray(c.filters) ? c.filters.slice() : [],
      limit: c.limit != null ? c.limit : 20,
      prefix: String(c.prefix || ""),
      suffix: String(c.suffix || ""),
      color: String(c.color || "green").trim(),
      color_shade: c.color_shade != null ? c.color_shade : 2,
      show_value_center: c.show_value_center !== false,
      extra_views: Array.isArray(c.extra_views) ? c.extra_views.slice() : [],
      include_left: !!c.include_left,
      client_id: c.client_id,
      url: c.url, content: c.content, block: c.block,
      show_group_composition: c.show_group_composition !== false,
      line1_value_mode: (function () {
        var mode = String(c.line1_value_mode || "sum").trim();
        return LINE1_VALUE_MODES.indexOf(mode) >= 0 ? mode : "sum";
      })(),
      line1_x_axis_mode: String(c.line1_x_axis_mode || "all"),
      line1_range_label: String(c.line1_range_label || "Last 12 months"),
      line1_active_index: String(c.line1_active_index || "middle"),
      show_line1_range: c.show_line1_range !== false,
      show_line1_fullscreen: c.show_line1_fullscreen !== false,
      show_line1_grid: c.show_line1_grid !== false,
      highlight_item: (function () {
        var item = String(c.highlight_item || "").trim();
        if (item === "max" || item === "latest") return item;
        return "latest";
      })(),
      average_label: String(c.average_label || "Avg"),
      show_average_line: c.show_average_line !== false,
      show_tooltip: c.show_tooltip !== false,
      show_summary_legend: c.show_summary_legend !== false,
    };
  }

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
  function parseRange(v) {
    if (v == null || v === "") return undefined;
    var n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }

  function chartMotionOptions(base) {
    base = base || {};
    if (!base.animation) {
      base.animation = { duration: 420, easing: "easeOutQuart" };
    }
    if (!base.transitions) {
      base.transitions = {
        active: { animation: { duration: 420, easing: "easeOutQuart" } },
        resize: { animation: { duration: 0 } },
        show: {
          animations: {
            x: { duration: 0 },
            y: { duration: 0 },
            colors: { duration: 0 },
          },
        },
        hide: {
          animations: {
            x: { duration: 0 },
            y: { duration: 0 },
          },
        },
      };
    }
    return base;
  }

  function resolveChartType(w, opts) {
    var render = opts && opts.render ? opts.render : null;
    if (render === "doughnut" || (!render && w.widget_type === "pie")) return "doughnut";
    if (render === "horizontal_bar" || (!render && w.widget_type === "horizontal_bar")) return "bar";
    if (!render && w.widget_type === "bar") return "bar";
    if (!render && w.widget_type === "line") return "line";
    return null;
  }

  function resolveIndexAxis(w, opts) {
    var render = opts && opts.render ? opts.render : null;
    return (render === "horizontal_bar" || (!render && w.widget_type === "horizontal_bar")) ? "y" : undefined;
  }

  function canAnimateChartUpdate(chart, w, data, opts) {
    if (!chart || !chart.config || !data || data.status !== "ok") return false;
    if (opts && opts.forceRecreate) return false;
    if (data.kind === "grouped_series") {
      if (w.widget_type !== "bar" && w.widget_type !== "line" && w.widget_type !== "horizontal_bar") return false;
      return chart.config.type === "bar" || chart.config.type === "line";
    }
    if (data.kind !== "series") return false;
    var chartType = resolveChartType(w, opts);
    if (!chartType) return false;
    if (chartType === "doughnut") return chart.config.type === "doughnut";
    if (chartType === "line") return chart.config.type === "line";
    if (chart.config.type !== "bar") return false;
    var wantAxis = resolveIndexAxis(w, opts);
    var haveAxis = chart.options.indexAxis;
    return (wantAxis || undefined) === (haveAxis || undefined);
  }

  function colorsEqual(a, b) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i] !== b[i]) return false;
    }
    return true;
  }

  function applySeriesChartData(chart, w, data, opts) {
    opts = opts || {};
    var cfg = normalizeWidgetConfig(w.config || {});
    var labels = data.labels || [];
    var values = data.values || [];
    var chartType = resolveChartType(w, opts);
    if (!chartType) return false;
    if (chartType === "doughnut") {
      chart.data.labels = labels.slice();
      chart.data.datasets[0].data = values.slice();
      chart.data.datasets[0].backgroundColor = shadeRamp(cfg, labels.length);
      if (chart.options.plugins && chart.options.plugins.centerTotal) {
        chart.options.plugins.centerTotal.text = (data.prefix || "") + fmtNum(data.total);
      }
      return true;
    }
    var topN = opts.limit != null ? opts.limit : (cfg.limit != null ? cfg.limit : 6);
    if (resolveIndexAxis(w, opts) === "y") {
      chart.data.labels = labels.slice(0, topN);
      chart.data.datasets[0].data = values.slice(0, topN);
      var nextHColors = shadeRamp(cfg, Math.max(1, Math.min(topN, values.length)));
      var prevHColors = chart.data.datasets[0].backgroundColor;
      if (!colorsEqual(prevHColors, nextHColors)) {
        chart.data.datasets[0].backgroundColor = nextHColors;
      }
      return true;
    }
    chart.data.labels = labels.slice();
    chart.data.datasets[0].data = values.slice();
    if (chartType === "bar") {
      var nextColors = shadeRamp(cfg, values.length);
      var prevColors = chart.data.datasets[0].backgroundColor;
      if (!colorsEqual(prevColors, nextColors)) {
        chart.data.datasets[0].backgroundColor = nextColors;
      }
    }
    return true;
  }

  function applyGroupedChartData(chart, w, data) {
    var keys = data.keys || [];
    var rows = data.data || [];
    if (!chart.data.datasets || chart.data.datasets.length !== keys.length) return false;
    chart.data.labels = rows.map(function (r) { return r.label; });
    keys.forEach(function (key, i) {
      chart.data.datasets[i].label = key;
      chart.data.datasets[i].data = rows.map(function (r) { return r[key] || 0; });
    });
    return true;
  }
  function applyAxisNames(scales, cfg, data, widgetType) {
    var mode = (cfg.axis_name_display || "none").toLowerCase();
    var xTitle = data.xAxisLabel || "";
    var yTitle = data.yAxisLabel || "";
    if (mode === "x" || mode === "both") {
      if (widgetType === "horizontal_bar") {
        scales.y = scales.y || {};
        scales.y.title = { display: !!xTitle, text: xTitle, color: "#8f949b", font: { size: 11 } };
      } else {
        scales.x = scales.x || {};
        scales.x.title = { display: !!xTitle, text: xTitle, color: "#8f949b", font: { size: 11 } };
      }
    }
    if (mode === "y" || mode === "both") {
      if (widgetType === "horizontal_bar") {
        scales.x = scales.x || {};
        scales.x.title = { display: !!yTitle, text: yTitle, color: "#8f949b", font: { size: 11 } };
      } else {
        scales.y = scales.y || {};
        scales.y.title = { display: !!yTitle, text: yTitle, color: "#8f949b", font: { size: 11 } };
      }
    }
  }
  function applyRange(scales, cfg, widgetType) {
    var rmin = parseRange(cfg.range_min);
    var rmax = parseRange(cfg.range_max);
    if (widgetType === "horizontal_bar") {
      scales.x = scales.x || {};
      if (rmin != null) scales.x.min = rmin;
      if (rmax != null) scales.x.max = rmax;
    } else {
      scales.y = scales.y || {};
      if (rmin != null) scales.y.min = rmin;
      if (rmax != null) scales.y.max = rmax;
    }
  }
  function cartesianScales(xGrid) {
    return {
      x: { grid: xGrid, border: { display: false }, ticks: { font: { size: 10 }, color: "#b0b5bc", maxRotation: 0 } },
      y: { beginAtZero: true, grid: { color: "#f4f5f7" }, border: { display: false }, ticks: { font: { size: 10 }, color: "#b0b5bc", padding: 6 } },
    };
  }
  function doughnutChartOptions(cfg, prefix, totalText) {
    return chartMotionOptions({
      responsive: true, maintainAspectRatio: false, cutout: "74%",
      plugins: {
        legend: { display: false }, datalabels: { display: false },
        centerTotal: { display: cfg.show_value_center !== false, text: totalText },
        tooltip: whiteTooltip(function (c) { return c.label + ": " + prefix + fmtNum(c.parsed); }),
      },
    });
  }
  function barChartOptions(cfg, prefix, data, widgetType) {
    var scales = cartesianScales({ display: false });
    applyAxisNames(scales, cfg, data || {}, widgetType || "bar");
    applyRange(scales, cfg, widgetType || "bar");
    return chartMotionOptions({
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: cfg.display_data_label || cfg.data_labels ? 18 : 6 } },
      plugins: {
        legend: { display: !!(cfg.display_legend || cfg.show_legend) },
        datalabels: (cfg.display_data_label || cfg.data_labels)
          ? { display: true, anchor: "end", align: "end", clip: false, color: "#98a2b3", font: { size: 10, weight: "500" }, formatter: dataLabel(prefix) }
          : { display: false },
        tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.y); }),
      },
      scales: scales,
    });
  }
  function lineChartOptions(cfg, prefix, data, stacked) {
    var scales = cartesianScales({ color: "#f5f6f8" });
    if (stacked) {
      scales.x.stacked = true;
      scales.y.stacked = true;
    }
    applyAxisNames(scales, cfg, data || {}, "line");
    applyRange(scales, cfg, "line");
    return chartMotionOptions({
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      elements: { point: { hoverRadius: 6, hitRadius: 12 } },
      plugins: {
        legend: { display: !!(cfg.display_legend || cfg.show_legend) },
        datalabels: (cfg.display_data_label || cfg.data_labels)
          ? { display: true, align: "top", color: "#98a2b3", font: { size: 10 }, formatter: dataLabel(prefix) }
          : { display: false },
        tooltip: whiteTooltip(function (c) { return (c.dataset.label ? c.dataset.label + ": " : "") + prefix + fmtNum(c.parsed.y); }),
      },
      scales: scales,
    });
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
        metric: "count", aggregate_field: "", field: "",
        primary_axis_field: "", group_by: "", date_group: "",
        primary_axis_sort: "position_asc", sort: "label_asc",
        primary_axis_order: [],
        secondary_axis_field: "", secondary_axis_sort: "label_asc",
        omit_null_values: false, hide_empty: false,
        range_min: "", range_max: "",
        group_mode: "stacked", axis_name_display: "none",
        display_data_label: true, data_labels: true,
        display_legend: true, show_legend: true,
        filters: [], limit: 20, color: "green", color_shade: 2,
        show_value_center: true,
        url: "", content: "", prefix: "", suffix: "",
        client_id: null, include_left: false, block: "kpi_jobs",
        extra_views: [],
        show_group_composition: true,
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
    var c = normalizeWidgetConfig(f.config);
    var out = {
      metric: c.metric,
      aggregate_field: c.aggregate_field,
      primary_axis_field: c.primary_axis_field,
      date_group: c.date_group,
      primary_axis_sort: c.primary_axis_sort,
      sort: c.sort,
      primary_axis_order: c.primary_axis_order,
      secondary_axis_field: c.secondary_axis_field,
      secondary_axis_sort: c.secondary_axis_sort,
      omit_null_values: c.omit_null_values,
      range_min: c.range_min,
      range_max: c.range_max,
      group_mode: c.group_mode,
      axis_name_display: c.axis_name_display,
      display_data_label: c.display_data_label,
      display_legend: c.display_legend,
      filters: (c.filters || []).filter(function (x) { return x.field; }),
      prefix: c.prefix || "", suffix: c.suffix || "",
    };
    if (isChartFn && isChartFn()) {
      var lim = Number(c.limit);
      out.limit = Number.isFinite(lim) && lim >= 1 ? lim : 20;
      out.color = c.color;
      out.color_shade = Number(c.color_shade);
      if (!Number.isFinite(out.color_shade) || out.color_shade < 0 || out.color_shade > 4) out.color_shade = 2;
      out.extra_views = (c.extra_views || []).map(function (ev) {
        var row = { render: ev.render, x: Number(ev.x) || 0, y: Number(ev.y) || 0, w: Number(ev.w) || 4, h: Number(ev.h) || 4 };
        var t = (ev.title || "").trim();
        if (t) row.title = t;
        if (ev.render === "horizontal_bar" && ev.limit != null && ev.limit !== "") row.limit = Number(ev.limit);
        return row;
      });
      if (c.secondary_axis_field) {
        out.show_group_composition = c.show_group_composition !== false;
      }
      if (f.widget_type === "line_1") {
        var line1Mode = String(c.line1_value_mode || "sum").trim();
        out.line1_value_mode = LINE1_VALUE_MODES.indexOf(line1Mode) >= 0 ? line1Mode : "sum";
        out.line1_x_axis_mode = c.line1_x_axis_mode || "all";
        out.line1_range_label = c.line1_range_label || "Last 12 months";
        out.line1_active_index = c.line1_active_index || "middle";
        out.show_line1_range = c.show_line1_range !== false;
        out.show_line1_fullscreen = c.show_line1_fullscreen !== false;
        out.show_line1_grid = c.show_line1_grid !== false;
      } else if (f.widget_type === "featured_bar") {
        out.average_label = c.average_label || "Avg";
        out.show_average_line = c.show_average_line !== false;
        out.show_tooltip = c.show_tooltip !== false;
        out.show_summary_legend = c.show_summary_legend !== false;
        out.highlight_item = c.highlight_item === "max" ? "max" : "latest";
      }
    }
    return out;
  }

  function compositionStripeBackground(color) {
    var light = mixHex(color, "#ffffff", 0.18);
    var dark = mixHex(color, "#000000", 0.08);
    return "repeating-linear-gradient(-45deg, " + light + ", " + light + " 4px, " + dark + " 4px, " + dark + " 8px), linear-gradient(180deg, " + mixHex(color, "#ffffff", 0.12) + " 0%, " + color + " 100%)";
  }

  function buildGroupedCompositionModel(input) {
    input = input || {};
    var entries = [];
    if (Array.isArray(input.datasets) && input.datasets.length) {
      input.datasets.forEach(function (ds, i) {
        var label = String((ds && ds.label) || ("Series " + (i + 1)));
        var total = (ds.data || []).reduce(function (sum, v) { return sum + (Number(v) || 0); }, 0);
        entries.push({ key: label, label: label, total: total });
      });
    } else {
      var keys = input.keys || [];
      var rows = input.data || [];
      keys.forEach(function (key) {
        var total = rows.reduce(function (sum, row) { return sum + (Number(row[key]) || 0); }, 0);
        entries.push({ key: key, label: key, total: total });
      });
    }
    entries.sort(function (a, b) { return b.total - a.total; });
    var max = GROUPED_COMPOSITION_MAX_SEGMENTS;
    var visible = entries.slice(0, max);
    var rest = entries.slice(max);
    if (rest.length) {
      var otherTotal = rest.reduce(function (sum, item) { return sum + item.total; }, 0);
      visible.push({ key: GROUPED_COMPOSITION_OTHER_LABEL, label: GROUPED_COMPOSITION_OTHER_LABEL, total: otherTotal });
    }
    var grandTotal = visible.reduce(function (sum, item) { return sum + item.total; }, 0);
    return visible.map(function (item, idx) {
      var pct = grandTotal > 0 ? Math.round((item.total / grandTotal) * 100) : 0;
      return {
        key: item.key,
        label: item.label,
        total: item.total,
        pct: pct,
        color: GROUPED_COMPOSITION_COLORS[idx % GROUPED_COMPOSITION_COLORS.length],
      };
    });
  }

  function renderGroupedComposition(containerEl, model) {
    if (!containerEl || !model || !model.length) return null;
    var root = document.createElement("div");
    root.className = "bms-grouped-composition";

    var strip = document.createElement("div");
    strip.className = "bms-grouped-composition-strip";
    model.forEach(function (item) {
      if (item.total <= 0 && model.length > 1) return;
      var seg = document.createElement("span");
      seg.className = "bms-grouped-composition-segment";
      seg.style.flexGrow = String(Math.max(item.pct, item.total > 0 ? 1 : 0));
      seg.style.flexBasis = "0";
      seg.style.background = compositionStripeBackground(item.color);
      seg.title = item.label + " " + item.pct + "%";
      strip.appendChild(seg);
    });
    root.appendChild(strip);

    var legend = document.createElement("div");
    legend.className = "bms-grouped-composition-legend";
    model.forEach(function (item) {
      var row = document.createElement("div");
      row.className = "bms-grouped-composition-row";

      var swatch = document.createElement("span");
      swatch.className = "bms-grouped-composition-swatch";
      swatch.style.background = compositionStripeBackground(item.color);
      if (typeof swatch.setAttribute === "function") swatch.setAttribute("aria-hidden", "true");

      var label = document.createElement("span");
      label.className = "bms-grouped-composition-label";
      label.textContent = item.label;
      label.title = item.label;

      var valueEl = document.createElement("span");
      valueEl.className = "bms-grouped-composition-value";
      valueEl.textContent = item.pct + "%";

      row.appendChild(swatch);
      row.appendChild(label);
      row.appendChild(valueEl);
      legend.appendChild(row);
    });
    root.appendChild(legend);
    containerEl.appendChild(root);
    return root;
  }

  function clearGroupedComposition(containerEl) {
    if (!containerEl) return;
    var existing = containerEl.querySelector(".bms-grouped-composition");
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
  }

  function syncGroupedComposition(canvas, input, cfg) {
    if (!canvas) return;
    cfg = cfg || {};
    var mount = canvas.closest(".chart-area") || canvas.parentElement;
    if (!mount) return;
    clearGroupedComposition(mount);
    if (cfg.show_group_composition === false) return;
    var model = buildGroupedCompositionModel(input);
    if (!model.length) return;
    renderGroupedComposition(mount, model);
  }

  function renderGroupedChart(chartInstances, destroyChartKey, w, data, opts) {
    opts = opts || {};
    var canvasId = opts.canvasId || chartCanvasId(w, opts.viewIndex);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    var cfg = normalizeWidgetConfig(w.config || {});
    var existing = chartInstances[canvasId];
    if (opts.animate !== false && existing && canAnimateChartUpdate(existing, w, data, opts)) {
      if (applyGroupedChartData(existing, w, data)) {
        var stacked = cfg.group_mode === "stacked" && w.widget_type !== "line";
        if (existing.options.scales) {
          if (existing.options.scales.x) existing.options.scales.x.stacked = stacked;
          if (existing.options.scales.y) existing.options.scales.y.stacked = stacked;
        }
        existing.update("active");
        syncGroupedComposition(canvas, data, cfg);
        return;
      }
    }
    destroyChartKey(canvasId);
    clearGroupedComposition(canvas.closest(".chart-area") || canvas.parentElement);

    var prefix = data.prefix || "";
    var keys = data.keys || [];
    var rows = data.data || [];
    var labels = rows.map(function (r) { return r.label; });
    var stacked = cfg.group_mode === "stacked" && w.widget_type !== "line";
    var pal = widgetPalette(cfg);
    var accent = pal[selectedShade(cfg)];

    var datasets = keys.map(function (key, i) {
      return {
        label: key,
        data: rows.map(function (r) { return r[key] || 0; }),
        backgroundColor: pal[(i + 2) % pal.length],
        borderColor: w.widget_type === "line" ? pal[(i + 2) % pal.length] : undefined,
        borderRadius: w.widget_type === "bar" || w.widget_type === "horizontal_bar" || w.widget_type === "featured_bar" ? 6 : undefined,
        fill: w.widget_type === "line" ? false : undefined,
        tension: w.widget_type === "line" ? 0.25 : undefined,
        pointRadius: w.widget_type === "line" ? 2 : undefined,
        borderWidth: w.widget_type === "line" ? 2 : undefined,
        maxBarThickness: w.widget_type === "horizontal_bar" ? 28 : 44,
        categoryPercentage: w.widget_type === "horizontal_bar" ? 0.58 : 0.62,
        barPercentage: 0.55,
      };
    });

    if (w.widget_type === "horizontal_bar") {
      var scales = {
        x: { beginAtZero: true, stacked: stacked, grid: { color: "#f2f3f5" }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
        y: { stacked: stacked, grid: { display: false }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
      };
      applyAxisNames(scales, cfg, data, "horizontal_bar");
      applyRange(scales, cfg, "horizontal_bar");
      chartInstances[canvasId] = new Chart(canvas, {
        type: "bar",
        data: { labels: labels, datasets: datasets },
        options: chartMotionOptions({
          responsive: true, maintainAspectRatio: false, indexAxis: "y",
          plugins: {
            legend: { display: !!(cfg.display_legend || cfg.show_legend) },
            datalabels: (cfg.display_data_label || cfg.data_labels) ? { display: true, anchor: "end", align: "end", color: "#98a2b3", font: { size: 10 }, formatter: dataLabel(prefix) } : { display: false },
            tooltip: whiteTooltip(function (c) { return (c.dataset.label ? c.dataset.label + ": " : "") + prefix + fmtNum(c.parsed.x); }),
          },
          scales: scales,
        }),
      });
      syncGroupedComposition(canvas, data, cfg);
      return;
    }
    if (w.widget_type === "line") {
      chartInstances[canvasId] = new Chart(canvas, {
        type: "line",
        data: { labels: labels, datasets: datasets },
        options: lineChartOptions(cfg, prefix, data, false),
      });
      syncGroupedComposition(canvas, data, cfg);
      return;
    }
    var barScales = cartesianScales({ display: false });
    if (stacked) { barScales.x.stacked = true; barScales.y.stacked = true; }
    applyAxisNames(barScales, cfg, data, "bar");
    applyRange(barScales, cfg, "bar");
    chartInstances[canvasId] = new Chart(canvas, {
      type: "bar",
      data: { labels: labels, datasets: datasets },
      options: chartMotionOptions({
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: !!(cfg.display_legend || cfg.show_legend) },
          datalabels: (cfg.display_data_label || cfg.data_labels) ? { display: true, anchor: "end", align: "end", clip: false, color: "#98a2b3", font: { size: 10, weight: "500" }, formatter: dataLabel(prefix) } : { display: false },
          tooltip: whiteTooltip(function (c) { return (c.dataset.label ? c.dataset.label + ": " : "") + prefix + fmtNum(c.parsed.y); }),
        },
        scales: barScales,
      }),
    });
    syncGroupedComposition(canvas, data, cfg);
  }

  function renderCrmChart(chartInstances, destroyChartKey, w, data, opts) {
    opts = opts || {};
    if (!data || data.status !== "ok") return;
    if (data.kind === "grouped_series") {
      renderGroupedChart(chartInstances, destroyChartKey, w, data, opts);
      return;
    }
    if (data.kind !== "series") return;
    var canvasId = opts.canvasId || chartCanvasId(w, opts.viewIndex);
    var canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    var existing = chartInstances[canvasId];
    if (opts.animate !== false && existing && canAnimateChartUpdate(existing, w, data, opts)) {
      if (applySeriesChartData(existing, w, data, opts)) {
        existing.update("active");
        return;
      }
    }
    destroyChartKey(canvasId);

    var cfg = normalizeWidgetConfig(w.config || {});
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
      var hScales = {
        x: { beginAtZero: true, grid: { color: "#f2f3f5" }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
        y: { grid: { display: false }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
      };
      applyAxisNames(hScales, cfg, data, "horizontal_bar");
      applyRange(hScales, cfg, "horizontal_bar");
      chartInstances[canvasId] = new Chart(canvas, {
        type: "bar",
        data: {
          labels: labels.slice(0, topN),
          datasets: [{ data: values.slice(0, topN), backgroundColor: shadeRamp(cfg, topN), borderRadius: 6, categoryPercentage: 0.58, barPercentage: 0.55, maxBarThickness: 28 }],
        },
        options: chartMotionOptions({
          responsive: true, maintainAspectRatio: false, indexAxis: "y",
          plugins: {
            legend: { display: !!(cfg.display_legend || cfg.show_legend) },
            datalabels: (cfg.display_data_label || cfg.data_labels) ? { display: true, anchor: "end", align: "end", color: "#98a2b3", font: { size: 10 }, formatter: dataLabel(prefix) } : { display: false },
            tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.x); }),
          },
          scales: hScales,
        }),
      });
      return;
    }
    if (!render && w.widget_type === "bar") {
      chartInstances[canvasId] = new Chart(canvas, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [{ label: w.title, data: values, backgroundColor: shadeRamp(cfg, values.length), hoverBackgroundColor: shadeHover(cfg), borderRadius: 6, categoryPercentage: 0.62, barPercentage: 0.55, maxBarThickness: 44 }],
        },
        options: barChartOptions(cfg, prefix, data, "bar"),
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
        options: lineChartOptions(cfg, prefix, data, false),
      });
    }
  }

  function tagPillStyle(label) {
    var s = String(label || "");
    var hash = 0;
    for (var i = 0; i < s.length; i++) {
      hash = ((hash << 5) - hash + s.charCodeAt(i)) | 0;
    }
    var row = TWENTY_COLOR_ROWS[Math.abs(hash) % TWENTY_COLOR_ROWS.length];
    return {
      backgroundColor: mixHex(row.shades[2], "#ffffff", 0.84),
      color: row.shades[4],
    };
  }

  global.DashboardWidgetKit = {
    EXTRA_RENDER_LABELS: EXTRA_RENDER_LABELS,
    METRIC_LABELS: METRIC_LABELS,
    CHART_WIDGET_TYPES: CHART_WIDGET_TYPES,
    DATA_WIDGET_TYPES: DATA_WIDGET_TYPES,
    TYPE_LABELS: TYPE_LABELS,
    TYPE_ICONS: TYPE_ICONS,
    TWENTY_COLOR_ROWS: TWENTY_COLOR_ROWS,
    tagPillStyle: tagPillStyle,
    colorRowOf: colorRowOf,
    selectedShade: selectedShade,
    widgetPalette: widgetPalette,
    shadeRamp: shadeRamp,
    shadeHover: shadeHover,
    themeOf: themeOf,
    fmtNum: fmtNum,
    chartCanvasId: chartCanvasId,
    blankWidget: blankWidget,
    normalizeWidgetConfig: normalizeWidgetConfig,
    buildConfig: buildConfig,
    renderCrmChart: renderCrmChart,
    renderGroupedChart: renderGroupedChart,
    installChartPlugins: installChartPlugins,
    buildGroupedCompositionModel: buildGroupedCompositionModel,
    renderGroupedComposition: renderGroupedComposition,
    syncGroupedComposition: syncGroupedComposition,
    clearGroupedComposition: clearGroupedComposition,
    GROUPED_COMPOSITION_COLORS: GROUPED_COMPOSITION_COLORS,
    extraRenderLabel: function (render) { return EXTRA_RENDER_LABELS[render] || render; },
  };
})(window);
