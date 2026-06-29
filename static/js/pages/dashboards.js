/**
 * Dashboard builder page (Twenty-parity B: polish + slide-over config panel).
 * Requires: Vue 3 CDN, Chart.js 4.4.9, chartjs-plugin-datalabels 2.2.0, window.crmAuthHeader()
 */
(function () {
  "use strict";

  const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
  const KIT = window.DashboardWidgetKit;
  const chartInstances = {};
  let widgetAutosaveTimer = null;
  let widgetPersistInFlight = false;
  let widgetPersistQueued = false;

  const EXTRA_RENDER_LABELS = { doughnut: "环形图", horizontal_bar: "横向排名（柱图）" };

  // Low-saturation accent per color key. Keys match the backend whitelist; only the
  // rendered hex is muted (Twenty-style). `base` is the single accent for bar/line/number.
  const COLOR_THEMES = {
    blue:   { base: "#7B96B8" }, // dusty blue
    green:  { base: "#88A992" }, // sage
    orange: { base: "#D6A461" }, // amber
    red:    { base: "#CD9180" }, // terracotta
    purple: { base: "#9389AE" }, // mauve
    gray:   { base: "#9AA0A6" }, // warm gray
  };
  const DEFAULT_THEME = "blue";

  const FEATURED_DOUGHNUT_COLORS = ["#ef594d", "#ffe8bd", "#f8ddf3", "#eee7ff", "#e8e9ff", "#fbe6f5", "#f3edff"];

  function maxValueIndex(values) {
    let max = -Infinity;
    let idx = -1;
    (values || []).forEach(function (v, i) {
      const n = Number(v) || 0;
      if (n > max) {
        max = n;
        idx = i;
      }
    });
    return max > 0 ? idx : -1;
  }

  function labelColorIndex(label) {
    const s = String(label || "");
    let hash = 0;
    for (let i = 0; i < s.length; i++) {
      hash = ((hash << 5) - hash + s.charCodeAt(i)) | 0;
    }
    return Math.abs(hash);
  }

  function featuredDoughnutColors(values, labels) {
    values = values || [];
    labels = labels || [];
    const maxIdx = maxValueIndex(values);
    const soft = FEATURED_DOUGHNUT_COLORS.slice(1);
    return values.map(function (_v, i) {
      if (i === maxIdx) return FEATURED_DOUGHNUT_COLORS[0];
      const label = labels[i] != null ? String(labels[i]) : String(i);
      return soft[labelColorIndex(label) % soft.length];
    });
  }

  function featuredDoughnutDataset(values, labels) {
    values = values || [];
    labels = labels || [];
    const maxIdx = maxValueIndex(values);
    return {
      data: values,
      backgroundColor: featuredDoughnutColors(values, labels),
      borderColor: "#ffffff",
      borderWidth: 0,
      borderRadius: 14,
      spacing: 8,
      hoverOffset: 4,
      offset: values.map(function (_v, i) { return i === maxIdx ? 2 : 0; }),
    };
  }

  // Legacy multi-hue categorical — not used by chart widgets or margin present mode.
  const CATEGORICAL = ["#B4C4D8", "#C2D4C8", "#E8D4B0", "#E4C4BC", "#C9C0DC", "#D0D3D8", "#C5D0DE", "#DDD4C4"];

  function hexRgb(hex) {
    const m = (hex || "#000000").replace("#", "");
    return [
      parseInt(m.substring(0, 2), 16),
      parseInt(m.substring(2, 4), 16),
      parseInt(m.substring(4, 6), 16),
    ];
  }
  function rgbHex(r, g, b) {
    return "#" + [r, g, b].map(function (x) {
      return Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0");
    }).join("");
  }
  function mixHex(a, b, t) {
    const ar = hexRgb(a), br = hexRgb(b);
    return rgbHex(ar[0] + (br[0] - ar[0]) * t, ar[1] + (br[1] - ar[1]) * t, ar[2] + (br[2] - ar[2]) * t);
  }
  function buildHueShades(mid) {
    return [
      mixHex(mid, "#ffffff", 0.72),
      mixHex(mid, "#ffffff", 0.42),
      mid,
      mixHex(mid, "#000000", 0.14),
      mixHex(mid, "#000000", 0.3),
    ];
  }

  const TWENTY_HUE_BASES = [
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
  const TWENTY_COLOR_ROWS = TWENTY_HUE_BASES.map(function (t) {
    return { key: t[0], label: t[1], shades: buildHueShades(t[2]) };
  });

  function colorRowOf(key) {
    const k = String(key || DEFAULT_THEME).toLowerCase();
    const row = TWENTY_COLOR_ROWS.find(function (r) { return r.key === k; });
    return row || TWENTY_COLOR_ROWS.find(function (r) { return r.key === "blue"; });
  }

  function selectedShade(cfg) {
    const idx = Number(cfg && cfg.color_shade);
    if (!Number.isFinite(idx) || idx < 0 || idx > 4) return 2;
    return idx;
  }

  function widgetPalette(cfg) {
    return colorRowOf(cfg && cfg.color).shades.slice();
  }

  function shadeRamp(cfg, n) {
    const pal = widgetPalette(cfg);
    const order = [3, 2, 1, 0, 4];
    const out = [];
    for (let i = 0; i < n; i++) out.push(pal[order[i % order.length]]);
    return out;
  }

  function shadeHover(cfg) {
    return widgetPalette(cfg)[4];
  }

  function themeOf(cfgOrColor) {
    const cfg = typeof cfgOrColor === "string" ? { color: cfgOrColor, color_shade: 2 } : (cfgOrColor || {});
    const pal = widgetPalette(cfg);
    return { base: pal[selectedShade(cfg)] };
  }

  function fmtNum(v) {
    if (v == null) return "0";
    const n = Number(v);
    if (Number.isInteger(n)) return n.toLocaleString();
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  function hexA(hex, a) {
    const m = hex.replace("#", "");
    const r = parseInt(m.substring(0, 2), 16), g = parseInt(m.substring(2, 4), 16), b = parseInt(m.substring(4, 6), 16);
    return "rgba(" + r + "," + g + "," + b + "," + a + ")";
  }
  function dataLabel(prefix) {
    return function (v) {
      if (v == null || v === "" || Number(v) === 0) return "";
      return prefix + fmtNum(v);
    };
  }

  function chartResponsive() {
    return { responsive: true, maintainAspectRatio: false };
  }
  function whiteTooltip(labelFn) {
    return {
      backgroundColor: "#ffffff",
      titleColor: "#1f2328",
      bodyColor: "#6b7280",
      borderColor: "#e6e8eb",
      borderWidth: 1,
      padding: 12,
      usePointStyle: true,
      displayColors: true,
      titleFont: { size: 12, weight: "600" },
      bodyFont: { size: 11 },
      boxPadding: 4,
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
    const showLabels = !!(cfg.display_data_label || cfg.data_labels);
    const r = chartResponsive();
    return {
      responsive: r.responsive,
      maintainAspectRatio: r.maintainAspectRatio,
      cutout: "58%",
      rotation: -45,
      layout: { padding: { top: 18, right: 18, bottom: 18, left: 18 } },
      plugins: {
        legend: { display: false },
        datalabels: showLabels ? {
          display: function (c) { return Number(c.dataset.data[c.dataIndex] || 0) > 0; },
          color: function (c) { return c.dataIndex === maxValueIndex(c.dataset.data) ? "#ffffff" : "#111827"; },
          backgroundColor: function (c) { return c.dataIndex === maxValueIndex(c.dataset.data) ? "#050505" : null; },
          borderRadius: 7,
          padding: function (c) { return c.dataIndex === maxValueIndex(c.dataset.data) ? { top: 4, right: 7, bottom: 4, left: 7 } : 0; },
          font: function (c) { return { size: c.dataIndex === maxValueIndex(c.dataset.data) ? 11 : 10, weight: c.dataIndex === maxValueIndex(c.dataset.data) ? "600" : "500" }; },
          formatter: function (v) { return prefix + fmtNum(v); },
          anchor: "center",
          align: "center",
          clamp: true,
        } : { display: false },
        centerTotal: { display: cfg.show_value_center !== false, text: totalText },
        tooltip: whiteTooltip(function (c) { return c.label + ": " + prefix + fmtNum(c.parsed); }),
      },
    };
  }
  function barChartOptions(cfg, prefix) {
    const r = chartResponsive();
    return {
      responsive: r.responsive,
      maintainAspectRatio: r.maintainAspectRatio,
      layout: { padding: { top: cfg.data_labels ? 18 : 6 } },
      plugins: {
        legend: { display: false },
        datalabels: cfg.data_labels
          ? { display: true, anchor: "end", align: "end", clip: false, color: "#98a2b3", font: { size: 10, weight: 500 }, formatter: dataLabel(prefix) }
          : { display: false },
        tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.y); }),
      },
      scales: cartesianScales({ display: false }),
    };
  }
  function lineChartOptions(cfg, prefix) {
    const r = chartResponsive();
    return {
      responsive: r.responsive,
      maintainAspectRatio: r.maintainAspectRatio,
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

  // Register datalabels plugin globally (disabled by default per-chart).
  if (typeof Chart !== "undefined" && typeof ChartDataLabels !== "undefined") {
    Chart.register(ChartDataLabels);
    Chart.defaults.set("plugins.datalabels", { display: false });
  }

  // Center-total plugin for doughnut charts.
  const centerTotalPlugin = {
    id: "centerTotal",
    afterDraw: function (chart) {
      const opt = chart.options.plugins.centerTotal;
      if (!opt || !opt.display) return;
      const ctx = chart.ctx;
      const meta = chart.getDatasetMeta(0);
      if (!meta || !meta.data || !meta.data[0]) return;
      const x = meta.data[0].x, y = meta.data[0].y;
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
  if (typeof Chart !== "undefined") Chart.register(centerTotalPlugin);

  function api(method, url, body) {
    const opts = {
      method: method,
      headers: Object.assign({ "Content-Type": "application/json" }, window.crmAuthHeader ? window.crmAuthHeader() : {}),
      credentials: "same-origin",
    };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function (r) {
      if (!r.ok) return r.json().then(function (e) { throw new Error(e.detail || r.statusText); });
      return r.json();
    });
  }

  const METRIC_LABELS = { count: "计数", sum: "求和", avg: "平均", min: "最小", max: "最大" };
  const CHART_WIDGET_TYPES = ["bar", "horizontal_bar", "pie", "line", "featured_line", "line_1", "featured_bar", "grouped_1"];
  const DATA_WIDGET_TYPES = ["number"].concat(CHART_WIDGET_TYPES);
  const TYPE_LABELS = {
    number: "数字", bar: "柱状", horizontal_bar: "横向排名", pie: "环形", line: "折线",
    featured_line: "重点折线",
    line_1: "折线1",
    featured_bar: "重点柱状",
    grouped_1: "分组1",
    rich_text: "文本", iframe: "网页", roster_summary: "花名册概览",
  };
  const TYPE_ICONS = {
    number: "#", bar: "▮", horizontal_bar: "▤", pie: "◔", line: "📈",
    featured_line: "◉",
    line_1: "〽",
    featured_bar: "▮",
    grouped_1: "▥",
    rich_text: "¶", iframe: "▭", roster_summary: "▦",
  };

  function chartCanvasId(w, viewIndex) {
    if (viewIndex == null || viewIndex === undefined) return "chart-" + w.id;
    return "chart-" + w.id + "-ev-" + viewIndex;
  }

  function featuredChartMountId(w) {
    return "featured-line-" + w.id;
  }

  function line1MountId(w) {
    return "line1-" + w.id;
  }

  function featuredBarMountId(item) {
    return "featured-bar-" + item.widget.id;
  }

  function destroyChartKey(key) {
    if (chartInstances[key]) {
      chartInstances[key].destroy();
      delete chartInstances[key];
    }
  }

  function extraRenderLabel(render) {
    return EXTRA_RENDER_LABELS[render] || render;
  }

  createApp({
    directives: {
      "click-outside": {
        mounted(el, binding) {
          el._cob = function (e) { if (!el.contains(e.target)) binding.value(); };
          document.addEventListener("click", el._cob, true);
        },
        unmounted(el) { document.removeEventListener("click", el._cob, true); },
      },
    },
    setup: function () {
      const dashboards = ref([]);
      const activeDashboardId = ref(null);
      const activeTabId = ref(null);
      const metadata = ref({ sources: [], widget_types: [], metrics: [], date_groups: [], colors: [], sorts: [] });
      const widgetData = ref({});
      const canWrite = ref(false);
      const canDelete = ref(false);
      const editMode = ref(false);
      const rosterClients = ref([]);

      const showDashboardModal = ref(false);
      const showTabModal = ref(false);
      const panelOpen = ref(false);
      const panelAutosaveReady = ref(false);
      const panelUserEdited = ref(false);
      const colorPickerOpen = ref(false);
      const colorSearch = ref("");
      const dashboardForm = ref({ id: null, name: "", description: "" });
      const tabForm = ref({ name: "" });
      const rosterScope = ref("all"); // panel-only: 'all' | 'client'
      const widgetForm = ref(blankWidget());

      function blankWidget() {
        return {
          id: null,
          title: "新组件",
          widget_type: "number",
          source_key: "clients",
          config: {
            metric: "count", field: "", group_by: "", date_group: "month",
            filters: [], limit: 20, color: "green", color_shade: 2, sort: "value_desc",
            show_legend: true, show_value_center: true, data_labels: false, hide_empty: false,
            url: "", content: "", prefix: "", suffix: "",
            comparison_label: "较上期", average_label: "Avg",
            show_average_line: true, show_comparison: true, highlight_latest: true,
            featured_value_mode: "auto", show_point_values: false,
            line1_value_mode: "sum", line1_x_axis_mode: "all", line1_range_label: "Last 12 months",
            line1_active_index: "middle", show_line1_range: true, show_line1_fullscreen: true, show_line1_grid: true,
            show_tooltip: true,
            show_summary_legend: true,
            client_id: null, include_left: false,
            extra_views: [],
            primary_axis_field: "", secondary_axis_field: "", secondary_axis_sort: "label_asc",
            group_mode: "stacked", show_group_composition: true,
          },
          x: 0, y: 0, w: 6, h: 5,
        };
      }

      const activeDashboard = computed(function () {
        return dashboards.value.find(function (d) { return d.id === activeDashboardId.value; }) || null;
      });
      const activeTab = computed(function () {
        if (!activeDashboard.value) return null;
        return activeDashboard.value.tabs.find(function (t) { return t.id === activeTabId.value; }) || null;
      });
      const displayItems = computed(function () {
        const tab = activeTab.value;
        if (!tab || !tab.widgets) return [];
        const items = [];
        tab.widgets.forEach(function (w) {
          items.push({
            key: "p-" + w.id,
            kind: "primary",
            widget: w,
            viewIndex: null,
            title: w.title,
            style: cardStyle(w),
            isExtra: false,
          });
          const views = (w.config && w.config.extra_views) || [];
          views.forEach(function (ev, idx) {
            items.push({
              key: "e-" + w.id + "-" + idx,
              kind: "extra",
              widget: w,
              viewIndex: idx,
              extraView: ev,
              title: (ev.title || "").trim() || w.title,
              style: cardStyle(ev),
              isExtra: true,
            });
          });
        });
        return items;
      });

      const needsDataSource = computed(function () {
        return DATA_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
      });
      const needsField = computed(function () {
        return ["sum", "avg", "min", "max"].indexOf(widgetForm.value.config.metric) >= 0;
      });
      const needsGroupBy = computed(function () {
        return CHART_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
      });
      const isChart = computed(function () {
        return CHART_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
      });
      const isRosterSummary = computed(function () {
        return widgetForm.value.widget_type === "roster_summary";
      });
      const sourceFields = computed(function () {
        const src = metadata.value.sources.find(function (s) { return s.key === widgetForm.value.source_key; });
        return src ? src.fields : [];
      });
      const numericFields = computed(function () {
        return sourceFields.value.filter(function (f) { return f.kind === "numeric"; });
      });
      const groupByFields = computed(function () {
        return sourceFields.value.filter(function (f) { return f.kind === "text" || f.kind === "datetime"; });
      });
      const supportsSecondary = computed(function () {
        var t = widgetForm.value.widget_type;
        return ["bar", "horizontal_bar", "line", "featured_bar", "grouped_1"].indexOf(t) >= 0;
      });
      const secondaryAxisFields = computed(function () {
        return sourceFields.value.filter(function (f) { return f.kind === "text"; });
      });
      const isDateGroup = computed(function () {
        const f = sourceFields.value.find(function (x) { return x.key === widgetForm.value.config.group_by; });
        return needsGroupBy.value && f && f.kind === "datetime";
      });

      const filteredColorRows = computed(function () {
        const q = (colorSearch.value || "").trim().toLowerCase();
        if (!q) return TWENTY_COLOR_ROWS;
        return TWENTY_COLOR_ROWS.filter(function (r) {
          return r.label.toLowerCase().indexOf(q) >= 0 || r.key.indexOf(q) >= 0;
        });
      });

      const selectedColorRowLabel = computed(function () {
        const row = colorRowOf(widgetForm.value.config.color);
        const si = selectedShade(widgetForm.value.config);
        return row.label + " · " + (si + 1);
      });

      function isColorSwatchActive(row, shadeIndex) {
        return widgetForm.value.config.color === row.key && selectedShade(widgetForm.value.config) === shadeIndex;
      }

      function pickColor(key, shadeIndex) {
        widgetForm.value.config.color = key;
        widgetForm.value.config.color_shade = shadeIndex;
        flushPersistWidget();
      }

      function closeColorPicker() { colorPickerOpen.value = false; }

      function clearWidgetAutosaveTimer() {
        if (widgetAutosaveTimer) {
          clearTimeout(widgetAutosaveTimer);
          widgetAutosaveTimer = null;
        }
      }

      function canAutosaveWidget() {
        return panelAutosaveReady.value && panelOpen.value && activeTabId.value
          && (widgetForm.value.id || panelUserEdited.value);
      }

      function syncWidgetFormToTab() {
        var f = widgetForm.value;
        if (!f || !f.id) return;
        var tab = activeTab.value;
        if (!tab || !tab.widgets) return;
        var cfg = buildConfig();
        tab.widgets.forEach(function (w) {
          if (w.id !== f.id) return;
          w.title = f.title;
          w.widget_type = f.widget_type;
          w.source_key = f.source_key;
          w.config = cfg;
        });
      }

      function previewWidgetChartFromForm() {
        if (!widgetForm.value || !widgetForm.value.id || widgetForm.value.widget_type !== "line_1") return;
        syncWidgetFormToTab();
        var tab = activeTab.value;
        if (!tab || !tab.widgets) return;
        var w = tab.widgets.find(function (x) { return x.id === widgetForm.value.id; });
        var data = widgetData.value[widgetForm.value.id];
        if (w && data) renderSingleWidget(w);
      }

      function schedulePersistWidget(delayMs) {
        if (!canAutosaveWidget()) return;
        previewWidgetChartFromForm();
        clearWidgetAutosaveTimer();
        widgetAutosaveTimer = setTimeout(function () {
          widgetAutosaveTimer = null;
          flushPersistWidget();
        }, delayMs == null ? 420 : delayMs);
      }

      function flushPersistWidget() {
        clearWidgetAutosaveTimer();
        if (!canAutosaveWidget()) return Promise.resolve();
        if (widgetPersistInFlight) {
          widgetPersistQueued = true;
          return Promise.resolve();
        }
        widgetPersistInFlight = true;
        const f = widgetForm.value;
        const payload = {
          title: f.title,
          widget_type: f.widget_type,
          source_key: f.source_key,
          config: buildConfig(),
          x: f.x,
          y: f.y,
          w: f.w,
          h: f.h,
        };
        const isNew = !f.id;
        const req = isNew
          ? api("POST", "/api/dashboard-tabs/" + activeTabId.value + "/widgets", payload)
          : api("PUT", "/api/dashboard-widgets/" + f.id, payload);
        return req
          .then(function (res) {
            if (isNew && res && res.id) widgetForm.value.id = res.id;
            return loadDashboards();
          })
          .then(function () {
            reloadActiveTabData();
          })
          .catch(function (e) { alert(e.message); })
          .finally(function () {
            widgetPersistInFlight = false;
            if (widgetPersistQueued) {
              widgetPersistQueued = false;
              flushPersistWidget();
            }
          });
      }

      function selectWidgetType(t) {
        if (widgetForm.value.widget_type === t) return;
        panelUserEdited.value = true;
        widgetForm.value.widget_type = t;
        if (t === "featured_line") {
          var f = widgetForm.value;
          if (!f.title || f.title === "新组件") f.title = "统计趋势";
          var c = f.config;
          if (c.comparison_label === undefined || c.comparison_label === "") c.comparison_label = "较上期";
          if (c.average_label === undefined || c.average_label === "") c.average_label = "Avg";
          if (c.show_average_line === undefined) c.show_average_line = true;
          if (c.show_comparison === undefined) c.show_comparison = true;
          if (c.highlight_latest === undefined) c.highlight_latest = true;
          if (c.featured_value_mode === undefined || c.featured_value_mode === "") c.featured_value_mode = "auto";
          if (c.show_point_values === undefined) c.show_point_values = false;
        }
        if (t === "line_1") {
          var l1 = widgetForm.value;
          if (!l1.title || l1.title === "新组件") l1.title = "统计趋势";
          var lc = l1.config;
          if (lc.line1_value_mode === undefined || lc.line1_value_mode === "") lc.line1_value_mode = "sum";
          if (lc.line1_x_axis_mode === undefined || lc.line1_x_axis_mode === "") lc.line1_x_axis_mode = "all";
          if (lc.line1_range_label === undefined || lc.line1_range_label === "") lc.line1_range_label = "Last 12 months";
          if (lc.line1_active_index === undefined || lc.line1_active_index === "") lc.line1_active_index = "middle";
          if (lc.show_line1_range === undefined) lc.show_line1_range = true;
          if (lc.show_line1_fullscreen === undefined) lc.show_line1_fullscreen = true;
          if (lc.show_line1_grid === undefined) lc.show_line1_grid = true;
          if (lc.color === undefined || lc.color === "") lc.color = "green";
        }
        if (t === "featured_bar") {
          var fb = widgetForm.value;
          if (!fb.title || fb.title === "新组件") fb.title = "统计趋势";
          var fc = fb.config;
          if (fc.average_label === undefined || fc.average_label === "") fc.average_label = "Avg";
          if (fc.show_average_line === undefined) fc.show_average_line = true;
          if (fc.show_tooltip === undefined) fc.show_tooltip = true;
          if (fc.show_summary_legend === undefined) fc.show_summary_legend = true;
          if (fc.highlight_item === undefined || fc.highlight_item === "") fc.highlight_item = "latest";
          fc.extra_views = [];
        }
        if (t === "pie" || t === "number" || t === "featured_line" || t === "line_1") {
          widgetForm.value.config.secondary_axis_field = "";
          widgetForm.value.config.group_mode = "stacked";
        }
        flushPersistWidget();
      }

      // Datetime grouping uses date_group; keep line / featured_line / featured_bar on their types.
      watch(function () { return [widgetForm.value.widget_type, widgetForm.value.config.group_by]; }, function () {
        if (isDateGroup.value && ["line", "featured_line", "line_1", "featured_bar"].indexOf(widgetForm.value.widget_type) >= 0) {
          if (!widgetForm.value.config.date_group) widgetForm.value.config.date_group = "month";
        }
      });

      // roster_summary is locked to the roster data source.
      watch(function () { return widgetForm.value.widget_type; }, function (t) {
        if (t === "roster_summary") widgetForm.value.source_key = "roster_entries";
      });

      function cardStyle(w) {
        const x = Math.max(0, Math.min(11, w.x || 0));
        const ww = Math.max(1, Math.min(12, w.w || 4));
        return {
          gridColumn: (x + 1) + " / span " + ww,
          gridRow: ((w.y || 0) + 1) + " / span " + Math.max(1, w.h || 4),
        };
      }

      function themeColor(w) { return themeOf(w.config || {}).base; }
      function swatchColor(c) { return themeOf({ color: c, color_shade: 2 }).base; }

      // roster_summary card: 4 KPI tiles from the data payload.
      function rosterTiles(w) {
        const d = widgetData.value[w.id];
        if (!d || d.kind !== "roster_summary") return [];
        return [
          { label: "月报价合计", display: d.revenue ? d.revenue.display : "—", color: "#7B96B8" },
          { label: "税前工资合计", display: d.salary ? d.salary.display : "—", color: "#9389AE" },
          { label: "GM$", display: d.gms ? d.gms.display : "—", color: "#88A992" },
          { label: "GM%", display: d.gm_pct ? d.gm_pct.display : "—", color: "#D6A461" },
        ];
      }
      function rosterScopeLabel(w) {
        const d = widgetData.value[w.id];
        if (!d || d.kind !== "roster_summary") return "";
        if (d.scope === "client") return (d.client_name || "未知客户") + " · " + (d.headcount || 0) + " 人";
        return "全公司 · " + (d.headcount || 0) + " 人";
      }
      function rosterHeadcount(w) {
        const d = widgetData.value[w.id];
        return (d && d.kind === "roster_summary") ? (d.headcount || 0) + " 人" : "";
      }
      function isRosterClientCard(w) {
        return w.widget_type === "roster_summary" && (w.config || {}).client_id != null;
      }
      function sourceLabel(key) {
        const s = metadata.value.sources.find(function (x) { return x.key === key; });
        return s ? s.label : "";
      }
      // First line is the title only when the content has multiple lines.
      function richTitle(text) {
        const t = (text || "").trim();
        const nl = t.indexOf("\n");
        return nl < 0 ? "" : t.slice(0, nl).trim();
      }
      function richBody(text) {
        const t = (text || "").trim();
        const nl = t.indexOf("\n");
        return nl < 0 ? t : t.slice(nl + 1).trim();
      }
      function metricLabel(m) { return METRIC_LABELS[m] || m; }
      function typeLabel(t) { return TYPE_LABELS[t] || t; }
      function typeIcon(t) { return TYPE_ICONS[t] || "▢"; }
      function showLegend(w) { return (w.config || {}).show_legend !== false; }

      function legendOf(w) {
        const d = widgetData.value[w.id];
        if (!d || d.kind !== "series") return [];
        const labels = d.labels || [];
        const values = d.values || [];
        if (w.widget_type === "pie") {
          if (KIT.doughnutLegendEntries) return KIT.doughnutLegendEntries(labels, values);
          const colors = KIT.featuredDoughnutColors
            ? KIT.featuredDoughnutColors(values, labels)
            : featuredDoughnutColors(values, labels);
          return labels.map(function (lab, i) {
            return { label: lab, value: values[i], color: colors[i] };
          });
        }
        const colors = shadeRamp(w.config || {}, labels.length);
        return labels.map(function (lab, i) {
          return { label: lab, value: values[i], color: colors[i] };
        });
      }

      function destroyCharts() {
        Object.keys(chartInstances).forEach(function (k) {
          destroyChartKey(k);
        });
        document.querySelectorAll(".chart-area").forEach(function (el) {
          if (KIT && KIT.clearGroupedComposition) KIT.clearGroupedComposition(el);
        });
        document.querySelectorAll(".bms-featured-line-mount").forEach(function (el) {
          if (window.CrmFeaturedLineChartKit) window.CrmFeaturedLineChartKit.destroyFeaturedLine(el);
        });
        document.querySelectorAll(".bms-featured-bar-mount").forEach(function (el) {
          if (window.CrmFeaturedBarChartKit) window.CrmFeaturedBarChartKit.destroyFeaturedBarChart(el);
        });
        document.querySelectorAll(".bms-line1-mount").forEach(function (el) {
          if (window.CrmLine1ChartKit) window.CrmLine1ChartKit.destroy(el);
        });
      }

      function renderLine1Widget(w, data) {
        var mount = document.getElementById(line1MountId(w));
        if (!mount || !window.CrmLine1ChartKit) return;
        var cfg = KIT ? KIT.normalizeWidgetConfig(w.config || {}) : (w.config || {});
        var accent = themeOf(cfg).base;
        window.CrmLine1ChartKit.render(
          mount,
          Object.assign({}, w, { config: cfg }),
          data,
          { lineColor: accent }
        );
      }

      function toggleGroupMode(ev) {
        widgetForm.value.config.group_mode = ev.target.checked ? "stacked" : "grouped";
        flushPersistWidget();
      }

      function renderFeaturedLineWidget(w, data) {
        var mount = document.getElementById(featuredChartMountId(w));
        if (!mount || !window.CrmFeaturedLineChartKit) return;
        var accent = themeOf(w.config || {}).base;
        window.CrmFeaturedLineChartKit.renderFeaturedLine(mount, w, data, { lineColor: accent });
      }

      function renderFeaturedBarWidget(w, data) {
        var mount = document.getElementById("featured-bar-" + w.id);
        if (!mount || !window.CrmFeaturedBarChartKit) return;
        window.CrmFeaturedBarChartKit.renderFeaturedBarChart(mount, w, data);
      }

      function renderChart(w, data, opts) {
        opts = opts || {};
        if (!data || data.status !== "ok" || data.kind !== "series") return;
        const canvasId = opts.canvasId || chartCanvasId(w, opts.viewIndex);
        const canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === "undefined") return;
        destroyChartKey(canvasId);

        const cfg = w.config || {};
        const labels = data.labels || [];
        const values = data.values || [];
        const prefix = data.prefix || "";
        const pal = widgetPalette(cfg);
        const accent = pal[selectedShade(cfg)];
        const render = opts.render || null;

        if (render === "doughnut" || (!render && w.widget_type === "pie")) {
          chartInstances[canvasId] = new Chart(canvas, {
            type: "doughnut",
            data: {
              labels: labels,
              datasets: [featuredDoughnutDataset(values, labels)],
            },
            options: doughnutChartOptions(cfg, prefix, prefix + fmtNum(data.total)),
          });
          return;
        }

        if (render === "horizontal_bar" || (!render && w.widget_type === "horizontal_bar")) {
          const topN = opts.limit != null ? opts.limit : (cfg.limit != null ? cfg.limit : 6);
          const hLabels = labels.slice(0, topN);
          const hValues = values.slice(0, topN);
          chartInstances[canvasId] = new Chart(canvas, {
            type: "bar",
            data: {
              labels: hLabels,
              datasets: [{
                data: hValues,
                backgroundColor: shadeRamp(cfg, hValues.length),
                borderRadius: 6,
                barPercentage: 0.72,
              }],
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              indexAxis: "y",
              plugins: {
                legend: { display: false },
                datalabels: { display: false },
                tooltip: whiteTooltip(function (c) { return prefix + fmtNum(c.parsed.x); }),
              },
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
              datasets: [{
                label: w.title,
                data: values,
                backgroundColor: shadeRamp(cfg, values.length),
                hoverBackgroundColor: shadeHover(cfg),
                borderRadius: 6,
                categoryPercentage: 0.65,
                barPercentage: 0.85,
              }],
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
              datasets: [{
                label: w.title, data: values, borderColor: accent,
                backgroundColor: hexA(pal[0], 0.12), fill: true, tension: 0.25,
                pointRadius: 0, pointBackgroundColor: accent, borderWidth: 2,
              }],
            },
            options: lineChartOptions(cfg, prefix),
          });
        }
      }

      function renderVisibleCharts() {
        const tab = activeTab.value;
        if (!tab || !tab.widgets) return;
        tab.widgets.forEach(function (w) {
          renderSingleWidget(w);
        });
      }

      function renderSingleWidget(w, opts) {
        opts = opts || {};
        if (CHART_WIDGET_TYPES.indexOf(w.widget_type) < 0) return;
        const data = widgetData.value[w.id];
        if (!data) return;
        if (w.widget_type === "featured_line") {
          renderFeaturedLineWidget(w, data);
          return;
        }
        if (w.widget_type === "line_1") {
          renderLine1Widget(w, data);
          return;
        }
        if (w.widget_type === "featured_bar") {
          var secField = (w.config && w.config.secondary_axis_field) || "";
          if (secField && data.kind === "grouped_series" && KIT) {
            KIT.renderGroupedChart(chartInstances, destroyChartKey, w, data, {
              viewIndex: null,
              animate: opts.animate !== false,
            });
            return;
          }
          renderFeaturedBarWidget(w, data);
          return;
        }
        if (!KIT) return;
        KIT.renderCrmChart(chartInstances, destroyChartKey, w, data, {
          viewIndex: null,
          animate: opts.animate !== false,
        });
        const views = (w.config && w.config.extra_views) || [];
        views.forEach(function (ev, idx) {
          KIT.renderCrmChart(chartInstances, destroyChartKey, w, data, {
            render: ev.render,
            viewIndex: idx,
            canvasId: chartCanvasId(w, idx),
            limit: ev.limit != null ? ev.limit : 6,
            animate: opts.animate !== false,
          });
        });
      }

      function loadWidgetData(widgets) {
        if (!widgets || !widgets.length) return;
        widgets.forEach(function (w) {
          api("GET", "/api/dashboard-widgets/" + w.id + "/data").then(function (data) {
            widgetData.value[w.id] = data;
            nextTick(function () { renderVisibleCharts(); });
          }).catch(function () {
            widgetData.value[w.id] = { status: "error" };
          });
        });
      }

      function reloadActiveTabData() {
        destroyCharts();
        widgetData.value = {};
        const tab = activeTab.value;
        if (tab && tab.widgets) loadWidgetData(tab.widgets);
      }

      function loadDashboards() {
        return api("GET", "/api/dashboards").then(function (list) {
          dashboards.value = list;
          if (!activeDashboardId.value && list.length) {
            activeDashboardId.value = list[0].id;
          }
          const d = dashboards.value.find(function (x) { return x.id === activeDashboardId.value; });
          if (d && d.tabs.length && !d.tabs.some(function (t) { return t.id === activeTabId.value; })) {
            activeTabId.value = d.tabs[0].id;
          }
        });
      }

      function selectDashboard(id) {
        activeDashboardId.value = id;
        const d = dashboards.value.find(function (x) { return x.id === id; });
        activeTabId.value = (d && d.tabs.length) ? d.tabs[0].id : null;
      }
      watch(activeTab, function () { reloadActiveTabData(); });

      watch(editMode, function () {
        destroyCharts();
        nextTick(function () { renderVisibleCharts(); });
      });

      watch(rosterScope, function () {
        if (!panelAutosaveReady.value) return;
        panelUserEdited.value = true;
        schedulePersistWidget(0);
      });

      watch(
        widgetForm,
        function () {
          if (!panelAutosaveReady.value) return;
          panelUserEdited.value = true;
          schedulePersistWidget(420);
        },
        { deep: true }
      );

      function openDashboardModal() {
        dashboardForm.value = { id: null, name: "", description: "" };
        showDashboardModal.value = true;
      }
      function saveDashboard() {
        const f = dashboardForm.value;
        const p = f.id
          ? api("PUT", "/api/dashboards/" + f.id, { name: f.name, description: f.description })
          : api("POST", "/api/dashboards", { name: f.name, description: f.description });
        p.then(function (created) {
          showDashboardModal.value = false;
          if (!f.id && created && created.id) activeDashboardId.value = created.id;
          return loadDashboards();
        }).catch(function (e) { alert(e.message); });
      }
      async function deleteActiveDashboard() {
        if (!activeDashboardId.value) return;
        const ok = await window.crmConfirmDeleteDialog({
          title: "确认删除",
          targetText: "将删除当前看板及其标签页与组件",
          hint: "删除后不可恢复。",
        });
        if (!ok) return;
        api("DELETE", "/api/dashboards/" + activeDashboardId.value).then(function () {
          activeDashboardId.value = null;
          activeTabId.value = null;
          return loadDashboards();
        }).catch(function (e) { alert(e.message); });
      }

      async function deleteActiveTab() {
        if (!activeTabId.value || !activeDashboard.value) return;
        const tabs = activeDashboard.value.tabs || [];
        if (tabs.length <= 1) {
          alert("至少保留一个标签页");
          return;
        }
        const tab = tabs.find(function (t) { return t.id === activeTabId.value; });
        const tabName = tab ? String(tab.name || "").trim() || "未命名" : "当前标签页";
        const ok = await window.crmConfirmDeleteDialog({
          title: "确认删除",
          targetText: "将删除标签页「" + tabName + "」",
          hint: "该标签页下的组件也会一并删除，且不可恢复。",
        });
        if (!ok) return;
        const deletedId = activeTabId.value;
        const idx = tabs.findIndex(function (t) { return t.id === deletedId; });
        const fallbackTab = tabs[idx > 0 ? idx - 1 : idx + 1];
        api("DELETE", "/api/dashboard-tabs/" + deletedId).then(function () {
          destroyCharts();
          widgetData.value = {};
          showTabModal.value = false;
          return loadDashboards();
        }).then(function () {
          activeTabId.value = fallbackTab ? fallbackTab.id : null;
        }).catch(function (e) { alert(e.message); });
      }

      function openTabModal() {
        tabForm.value = { name: "" };
        showTabModal.value = true;
        nextTick(function () {
          var el = document.getElementById("dash-tab-name-input");
          if (el) el.focus();
        });
      }
      function saveTab() {
        if (!activeDashboardId.value) return;
        var name = String(tabForm.value.name || "").trim();
        if (!name) {
          alert("请输入标签页名称");
          nextTick(function () {
            var el = document.getElementById("dash-tab-name-input");
            if (el) el.focus();
          });
          return;
        }
        api("POST", "/api/dashboards/" + activeDashboardId.value + "/tabs", { name: name })
          .then(function () { showTabModal.value = false; return loadDashboards(); })
          .then(function () {
            const d = dashboards.value.find(function (x) { return x.id === activeDashboardId.value; });
            if (d && d.tabs.length) activeTabId.value = d.tabs[d.tabs.length - 1].id;
          })
          .catch(function (e) { alert(e.message); });
      }

      function openWidgetPanel(w) {
        if (w) {
          const base = blankWidget();
          const merged = Object.assign(
            base.config,
            w.config || {},
            {
              filters: (w.config && w.config.filters) ? w.config.filters.map(function (f) { return Object.assign({}, f); }) : [],
              extra_views: (w.config && w.config.extra_views)
                ? w.config.extra_views.map(function (ev) { return Object.assign({}, ev); })
                : [],
            }
          );
          if (merged.color_shade === undefined || merged.color_shade === null) merged.color_shade = 2;
          if (!merged.color) merged.color = base.config.color;
          if (w.widget_type === "featured_bar" && (!merged.highlight_item || merged.highlight_item === "")) {
            merged.highlight_item = "latest";
          }
          widgetForm.value = {
            id: w.id,
            title: w.title,
            widget_type: w.widget_type,
            source_key: w.source_key || "",
            config: merged,
            x: w.x, y: w.y, w: w.w, h: w.h,
          };
          rosterScope.value = (w.config && w.config.client_id != null) ? "client" : "all";
        } else {
          widgetForm.value = blankWidget();
          rosterScope.value = "all";
        }
        colorPickerOpen.value = false;
        panelUserEdited.value = !!w;
        panelAutosaveReady.value = false;
        panelOpen.value = true;
        nextTick(function () { panelAutosaveReady.value = true; });
      }
      function closePanel() {
        panelAutosaveReady.value = false;
        panelUserEdited.value = false;
        clearWidgetAutosaveTimer();
        panelOpen.value = false;
        colorPickerOpen.value = false;
      }
      function addFilter() {
        widgetForm.value.config.filters.push({ field: "", op: "eq", value: "" });
        schedulePersistWidget(420);
      }
      function removeFilter(idx) {
        widgetForm.value.config.filters.splice(idx, 1);
        flushPersistWidget();
      }
      function filterValuePlaceholder(flt) {
        flt = flt || {};
        if (flt.op === "in") {
          if (flt.field === "recommended_by") return "用户名，逗号分隔";
          return "逗号分隔";
        }
        if (flt.field === "recommended_by") return "用户名，如 qianq";
        return "值";
      }

      function blankExtraView() {
        return { render: "doughnut", x: 0, y: 0, w: 6, h: 6, limit: 6, title: "" };
      }

      function addExtraView() {
        if (!widgetForm.value.config.extra_views) widgetForm.value.config.extra_views = [];
        widgetForm.value.config.extra_views.push(blankExtraView());
        flushPersistWidget();
      }

      function removeExtraView(idx) {
        widgetForm.value.config.extra_views.splice(idx, 1);
        flushPersistWidget();
      }

      function buildConfig() {
        const f = widgetForm.value;
        const c = f.config;
        if (f.widget_type === "iframe") return { url: c.url };
        if (f.widget_type === "rich_text") return { content: c.content };
        if (f.widget_type === "roster_summary") {
          return {
            client_id: rosterScope.value === "client" ? (c.client_id || null) : null,
            include_left: !!c.include_left,
          };
        }
        const out = {
          metric: c.metric, field: c.field, group_by: c.group_by,
          primary_axis_field: c.group_by || c.primary_axis_field || "",
          filters: (c.filters || []).filter(function (x) { return x.field; }),
          prefix: c.prefix || "", suffix: c.suffix || "",
        };
        if (isChart.value) {
          out.secondary_axis_field = String(c.secondary_axis_field || "").trim();
          out.secondary_axis_sort = String(c.secondary_axis_sort || "label_asc").trim();
          out.group_mode = String(c.group_mode || "stacked").trim();
          if (out.secondary_axis_field) {
            out.show_group_composition = c.show_group_composition !== false;
          }
        }
        // date_group path: backend rejects a datetime group_by and re-derives it
        // from created_at, so send group_by empty and let the date_group drive it.
        if (isDateGroup.value) { out.group_by = ""; out.date_group = c.date_group; }
        if (isChart.value) {
          const lim = Number(c.limit);
          out.limit = Number.isFinite(lim) && lim >= 1 ? lim : 20;
          out.color = c.color;
          out.color_shade = Number(c.color_shade);
          if (!Number.isFinite(out.color_shade) || out.color_shade < 0 || out.color_shade > 4) out.color_shade = 2;
          out.sort = c.sort;
          out.show_legend = !!c.show_legend;
          out.show_value_center = !!c.show_value_center;
          out.data_labels = !!c.data_labels;
          out.hide_empty = !!c.hide_empty;
          if (f.widget_type === "featured_line") {
            out.comparison_label = c.comparison_label || "较上期";
            out.average_label = c.average_label || "Avg";
            out.show_average_line = c.show_average_line !== false;
            out.show_comparison = c.show_comparison !== false;
            out.highlight_latest = c.highlight_latest !== false;
            out.show_point_values = c.show_point_values === true;
            out.featured_value_mode = c.featured_value_mode || "auto";
          } else if (f.widget_type === "line_1") {
            out.line1_value_mode = c.line1_value_mode || "sum";
            out.line1_x_axis_mode = c.line1_x_axis_mode || "all";
            out.line1_range_label = c.line1_range_label || "Last 12 months";
            out.show_line1_range = c.show_line1_range !== false;
            out.show_line1_fullscreen = c.show_line1_fullscreen !== false;
            out.show_line1_grid = c.show_line1_grid !== false;
          } else if (f.widget_type === "featured_bar") {
            out.average_label = c.average_label || "Avg";
            out.show_average_line = c.show_average_line !== false;
            out.show_tooltip = c.show_tooltip !== false;
            out.show_summary_legend = c.show_summary_legend !== false;
            out.highlight_item = c.highlight_item === "max" ? "max" : "latest";
            out.featured_value_mode = c.featured_value_mode || "auto";
            out.show_point_values = c.show_point_values === true;
          } else {
            out.extra_views = (c.extra_views || []).map(function (ev) {
              const row = {
                render: ev.render,
                x: Number(ev.x) || 0,
                y: Number(ev.y) || 0,
                w: Number(ev.w) || 4,
                h: Number(ev.h) || 4,
              };
              const t = (ev.title || "").trim();
              if (t) row.title = t;
              if (ev.render === "horizontal_bar" && ev.limit != null && ev.limit !== "") {
                row.limit = Number(ev.limit);
              }
              return row;
            });
          }
        }
        return out;
      }

      async function deleteWidget(id) {
        const ok = await window.crmConfirmDeleteDialog({
          title: "确认删除",
          targetText: "将删除当前看板组件",
          hint: "删除后不可恢复。",
        });
        if (!ok) return;
        api("DELETE", "/api/dashboard-widgets/" + id)
          .then(function () { return loadDashboards(); })
          .then(function () { reloadActiveTabData(); })
          .catch(function (e) { alert(e.message); });
      }

      // Duplicate any widget (mainly to compare two single-client roster cards).
      function duplicateWidget(w) {
        if (!activeTabId.value) return;
        const payload = {
          title: w.title + " 副本",
          widget_type: w.widget_type,
          source_key: w.source_key || "",
          config: Object.assign({}, w.config || {}, {
            extra_views: (w.config && w.config.extra_views)
              ? w.config.extra_views.map(function (ev) { return Object.assign({}, ev); })
              : [],
          }),
          x: w.x, y: (w.y || 0) + (w.h || 4), w: w.w, h: w.h,
        };
        api("POST", "/api/dashboard-tabs/" + activeTabId.value + "/widgets", payload)
          .then(function () { return loadDashboards(); })
          .then(function () { reloadActiveTabData(); })
          .catch(function (e) { alert(e.message); });
      }

      // On-card client switch for a roster_summary card (write users): persist + re-query.
      function changeRosterClient(w, clientId) {
        const cid = clientId === "" || clientId == null ? null : Number(clientId);
        const payload = {
          title: w.title, widget_type: w.widget_type, source_key: w.source_key || "roster_entries",
          config: Object.assign({}, w.config || {}, { client_id: cid }),
          x: w.x, y: w.y, w: w.w, h: w.h,
        };
        api("PUT", "/api/dashboard-widgets/" + w.id, payload)
          .then(function () {
            w.config = payload.config; // local update so dropdown reflects selection
            return api("GET", "/api/dashboard-widgets/" + w.id + "/data");
          })
          .then(function (data) {
            widgetData.value[w.id] = data;
            nextTick(function () { renderVisibleCharts(); });
          })
          .catch(function (e) { alert(e.message); });
      }

      onMounted(function () {
        if (KIT && typeof Chart !== "undefined") {
          KIT.installChartPlugins(Chart, window.ChartDataLabels);
        }
        fetch("/api/me", { headers: window.crmAuthHeader ? window.crmAuthHeader() : {}, credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (me) {
            const perms = me.permissions || [];
            canWrite.value = perms.indexOf("dashboard.write") >= 0 || me.is_super;
            canDelete.value = perms.indexOf("dashboard.delete") >= 0 || me.is_super;
          });
        api("GET", "/api/dashboard-metadata").then(function (m) { metadata.value = m; });
        api("GET", "/api/dashboard/roster-clients")
          .then(function (r) { rosterClients.value = (r && r.clients) || []; })
          .catch(function () { rosterClients.value = []; });
        loadDashboards();
      });

      function cardCanvasId(item) {
        if (item.kind === "extra") return chartCanvasId(item.widget, item.viewIndex);
        return chartCanvasId(item.widget, null);
      }

      function openDisplayItemPanel(item) {
        openWidgetPanel(item.widget);
      }

      return {
        dashboards, activeDashboardId, activeTabId, activeDashboard, activeTab,
        displayItems, cardCanvasId, openDisplayItemPanel, extraRenderLabel,
        metadata, widgetData, canWrite, canDelete, editMode, rosterClients, rosterScope,
        showDashboardModal, showTabModal, panelOpen,
        dashboardForm, tabForm, widgetForm,
        needsDataSource, needsField, needsGroupBy, isChart, isDateGroup, isRosterSummary,
        supportsSecondary, secondaryAxisFields, toggleGroupMode,
        sourceFields, numericFields, groupByFields,
        colorPickerOpen, colorSearch, filteredColorRows, selectedColorRowLabel,
        isColorSwatchActive, pickColor, closeColorPicker, widgetPalette, selectedShade,
        cardStyle, themeColor, swatchColor, sourceLabel, metricLabel, typeLabel, typeIcon,
        richTitle, richBody, showLegend, legendOf, featuredChartMountId, line1MountId, featuredBarMountId,
        rosterTiles, rosterScopeLabel, rosterHeadcount, isRosterClientCard,
        selectDashboard,
        openDashboardModal, saveDashboard, deleteActiveDashboard, deleteActiveTab,
        openTabModal, saveTab, openWidgetPanel, closePanel, selectWidgetType,
        addFilter, removeFilter, filterValuePlaceholder, addExtraView, removeExtraView, deleteWidget,
        duplicateWidget, changeRosterClient,
      };
    },
  }).mount("#page-app");
})();
