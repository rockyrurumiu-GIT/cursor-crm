/**
 * Dashboard builder page (Twenty-parity B: polish + slide-over config panel).
 * Requires: Vue 3 CDN, Chart.js 4.4.9, chartjs-plugin-datalabels 2.2.0, window.crmAuthHeader()
 */
(function () {
  "use strict";

  const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
  const chartInstances = {};
  const marginChartInstances = {};

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
    const r = chartResponsive();
    return {
      responsive: r.responsive,
      maintainAspectRatio: r.maintainAspectRatio,
      cutout: "74%",
      plugins: {
        legend: { display: false },
        datalabels: { display: false },
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
  const TYPE_LABELS = { number: "数字", bar: "柱状", pie: "环形", line: "折线", rich_text: "文本", iframe: "网页", roster_summary: "花名册概览" };
  const TYPE_ICONS = { number: "#", bar: "▮", pie: "◔", line: "📈", rich_text: "¶", iframe: "▭", roster_summary: "▦" };

  const MARGIN_DASHBOARD_NAME = "交付毛利总览";
  const MARGIN_PRESENT_SPEC_ORDER = ["quoteBar", "gmBar", "company", "client"];
  const MARGIN_PRESENT_SPECS = {
    quoteBar: {
      title: "各客户月报价(含税)",
      widget_type: "bar",
      source_key: "roster_entries",
      panelTitle: "各客户月报价(含税)",
      editTag: "总览使用：各客户月报价",
    },
    gmBar: {
      title: "各客户 GM$",
      widget_type: "bar",
      source_key: "roster_entries",
      panelTitle: "各客户 GM$",
      editTag: "总览使用：GM$ 环形 + GM$ 排名",
    },
    company: {
      title: "全公司毛利概览",
      widget_type: "roster_summary",
      source_key: "roster_entries",
      panelTitle: "毛利概览",
      editTag: "总览使用：毛利概览表",
    },
    client: {
      title: "单客户毛利概览",
      widget_type: "roster_summary",
      source_key: "roster_entries",
      panelTitle: "毛利概览",
      editTag: "总览使用：毛利概览表",
    },
  };

  const MARGIN_PRESET_EDIT_LAYOUT = {
    quoteBar: { gridColumn: "1 / 2", gridRow: "1 / 2" },
    gmBar: { gridColumn: "2 / 3", gridRow: "1 / 2" },
    company: { gridColumn: "1 / 2", gridRow: "2 / 3" },
    client: { gridColumn: "2 / 3", gridRow: "2 / 3" },
  };

  function matchMarginPresentSpec(w, spec) {
    return !!w && w.title === spec.title && w.widget_type === spec.widget_type && w.source_key === spec.source_key;
  }

  function findMarginWidget(tab, key) {
    if (!tab || !tab.widgets) return null;
    const spec = MARGIN_PRESENT_SPECS[key];
    if (!spec) return null;
    return tab.widgets.find(function (w) { return matchMarginPresentSpec(w, spec); }) || null;
  }

  function isMarginPresetWidget(w) {
    if (!w) return false;
    return MARGIN_PRESENT_SPEC_ORDER.some(function (key) {
      return matchMarginPresentSpec(w, MARGIN_PRESENT_SPECS[key]);
    });
  }

  function destroyMarginCharts() {
    Object.keys(marginChartInstances).forEach(function (k) {
      if (marginChartInstances[k]) marginChartInstances[k].destroy();
      delete marginChartInstances[k];
    });
  }

  function marginChartLayout() {
    return { responsive: true, maintainAspectRatio: false, animation: false };
  }

  function marginTooltip(labelFn) {
    return {
      backgroundColor: "#ffffff",
      titleColor: "#1f2328",
      bodyColor: "#6b7280",
      borderColor: "#e6e8eb",
      borderWidth: 1,
      padding: 10,
      callbacks: { label: labelFn },
    };
  }

  function marginSeriesLegend(data, limit, colorAt) {
    if (!data || data.kind !== "series" || data.status !== "ok") return [];
    const labels = data.labels || [];
    return labels.slice(0, limit).map(function (lab, i) {
      return { label: lab, color: colorAt(i) };
    });
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
      const editMode = ref(false);
      const dashMenuOpen = ref(false);
      const rosterClients = ref([]);

      const showDashboardModal = ref(false);
      const showTabModal = ref(false);
      const panelOpen = ref(false);
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
            filters: [], color: "green", color_shade: 2, sort: "value_desc",
            show_legend: true, show_value_center: true, data_labels: false, hide_empty: false,
            url: "", content: "", prefix: "", suffix: "",
            client_id: null, include_left: false,
          },
          x: 0, y: 0, w: 4, h: 4,
        };
      }

      const activeDashboard = computed(function () {
        return dashboards.value.find(function (d) { return d.id === activeDashboardId.value; }) || null;
      });
      const activeTab = computed(function () {
        if (!activeDashboard.value) return null;
        return activeDashboard.value.tabs.find(function (t) { return t.id === activeTabId.value; }) || null;
      });
      const tabIndex = computed(function () {
        if (!activeDashboard.value) return 0;
        const i = activeDashboard.value.tabs.findIndex(function (t) { return t.id === activeTabId.value; });
        return i < 0 ? 1 : i + 1;
      });

      const marginPresentMode = computed(function () {
        return !!activeDashboard.value
          && activeDashboard.value.name === MARGIN_DASHBOARD_NAME
          && !editMode.value;
      });

      const marginWidgets = computed(function () {
        const tab = activeTab.value;
        return {
          company: findMarginWidget(tab, "company"),
          client: findMarginWidget(tab, "client"),
          quoteBar: findMarginWidget(tab, "quoteBar"),
          gmBar: findMarginWidget(tab, "gmBar"),
        };
      });

      function marginWidgetDataState(w) {
        if (!w) return "missing";
        const d = widgetData.value[w.id];
        if (!d) return "loading";
        if (d.status === "forbidden") return "forbidden";
        if (d.status === "error") return "error";
        if (d.kind === "series" && d.status === "ok") return "ok";
        if (d.kind === "roster_summary") return "ok";
        return "loading";
      }

      const marginPanelQuoteState = computed(function () {
        return marginWidgetDataState(marginWidgets.value.quoteBar);
      });
      const marginPanelGmState = computed(function () {
        return marginWidgetDataState(marginWidgets.value.gmBar);
      });
      const marginPanelMetricsState = computed(function () {
        const mw = marginWidgets.value;
        if (!mw.company || !mw.client) return mw.company || mw.client ? "loading" : "missing";
        const cs = marginWidgetDataState(mw.company);
        const cl = marginWidgetDataState(mw.client);
        if (cs === "forbidden" || cl === "forbidden") return "forbidden";
        if (cs === "error" || cl === "error") return "error";
        if (cs === "ok" && cl === "ok") return "ok";
        return "loading";
      });

      const marginQuoteLegend = computed(function () {
        const w = marginWidgets.value.quoteBar;
        if (!w) return [];
        const d = widgetData.value[w.id];
        const n = (d && d.labels) ? d.labels.length : 0;
        const colors = shadeRamp(w.config || {}, n);
        return marginSeriesLegend(d, 5, function (i) { return colors[i]; });
      });

      const marginDonutLegend = computed(function () {
        const w = marginWidgets.value.gmBar;
        if (!w) return [];
        const d = widgetData.value[w.id];
        const n = (d && d.labels) ? d.labels.length : 0;
        const colors = shadeRamp(w.config || {}, n);
        return marginSeriesLegend(d, 5, function (i) { return colors[i]; });
      });

      const marginClientColumnLabel = computed(function () {
        const w = marginWidgets.value.client;
        if (!w) return "当前客户";
        const d = widgetData.value[w.id];
        if (d && d.kind === "roster_summary" && d.client_name) return d.client_name;
        return rosterScopeLabel(w) || "当前客户";
      });

      const marginMetricRows = computed(function () {
        const mw = marginWidgets.value;
        const cd = mw.company ? widgetData.value[mw.company.id] : null;
        const ld = mw.client ? widgetData.value[mw.client.id] : null;
        if (!cd || cd.kind !== "roster_summary" || !ld || ld.kind !== "roster_summary") return [];
        return [
          { label: "月报价", company: cd.revenue ? cd.revenue.display : "—", client: ld.revenue ? ld.revenue.display : "—" },
          { label: "税前工资", company: cd.salary ? cd.salary.display : "—", client: ld.salary ? ld.salary.display : "—" },
          { label: "GM$", company: cd.gms ? cd.gms.display : "—", client: ld.gms ? ld.gms.display : "—" },
          { label: "GM%", company: cd.gm_pct ? cd.gm_pct.display : "—", client: ld.gm_pct ? ld.gm_pct.display : "—" },
        ];
      });

      const marginPanelLabels = computed(function () {
        const specs = MARGIN_PRESENT_SPECS;
        const mw = marginWidgets.value;
        const gmTitle = specs.gmBar.title;
        return {
          quote: {
            title: specs.quoteBar.panelTitle,
            hint: "配色与编辑态「" + specs.quoteBar.title + "」一致",
          },
          gmDonut: {
            title: gmTitle + "（环形）",
            hint: "配色来自「" + gmTitle + "」柱图（非历史 pie）",
          },
          gmHbar: {
            title: gmTitle + "（排名）",
            hint: "配色来自「" + gmTitle + "」柱图",
          },
          metrics: {
            title: specs.company.panelTitle,
            hint: "数据来自「" + specs.company.title + "」「" + specs.client.title + "」",
          },
        };
      });

      const marginDashboardEditLayout = computed(function () {
        return !!activeDashboard.value
          && activeDashboard.value.name === MARGIN_DASHBOARD_NAME
          && editMode.value;
      });

      const marginPresetWidgets = computed(function () {
        const tab = activeTab.value;
        if (!tab || !tab.widgets) return [];
        return MARGIN_PRESENT_SPEC_ORDER.map(function (key) {
          const spec = MARGIN_PRESENT_SPECS[key];
          return {
            key: key,
            spec: spec,
            widget: findMarginWidget(tab, key),
            editTag: spec.editTag,
          };
        });
      });

      const marginExtraWidgets = computed(function () {
        const tab = activeTab.value;
        if (!tab || !tab.widgets) return [];
        return tab.widgets.filter(function (w) { return !isMarginPresetWidget(w); });
      });

      const marginPresetEditCards = computed(function () {
        return marginPresetWidgets.value.map(function (item) {
          return {
            key: item.key,
            w: item.widget,
            title: item.widget ? item.widget.title : item.spec.title,
            editTag: item.editTag,
            style: marginPresetEditCardStyle(item.key),
          };
        });
      });

      const marginExtraEditCards = computed(function () {
        return marginExtraWidgets.value.map(function (w, idx) {
          return {
            key: String(w.id),
            w: w,
            title: w.title,
            style: marginExtraEditCardStyle(idx),
          };
        });
      });

      function marginPresetEditCardStyle(key) {
        const layout = MARGIN_PRESET_EDIT_LAYOUT[key] || { gridColumn: "1 / 2", gridRow: "1 / 2" };
        return {
          gridColumn: layout.gridColumn,
          gridRow: layout.gridRow,
          minHeight: "320px",
          height: "320px",
        };
      }

      function marginExtraEditCardStyle(index) {
        const col = (index % 2) + 1;
        const row = Math.floor(index / 2) + 1;
        return {
          gridColumn: col + " / " + (col + 1),
          gridRow: row + " / " + (row + 1),
          minHeight: "320px",
          height: "320px",
        };
      }

      const needsDataSource = computed(function () {
        return ["number", "bar", "pie", "line"].indexOf(widgetForm.value.widget_type) >= 0;
      });
      const needsField = computed(function () {
        return ["sum", "avg", "min", "max"].indexOf(widgetForm.value.config.metric) >= 0;
      });
      const needsGroupBy = computed(function () {
        return ["bar", "pie", "line"].indexOf(widgetForm.value.widget_type) >= 0;
      });
      const isChart = computed(function () {
        return ["bar", "pie", "line"].indexOf(widgetForm.value.widget_type) >= 0;
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
      }

      function closeColorPicker() { colorPickerOpen.value = false; }

      // Line charts require a date_group group_by; keep frontend honest by forcing line type for datetime groups.
      watch(function () { return [widgetForm.value.widget_type, widgetForm.value.config.group_by]; }, function () {
        if (isDateGroup.value && widgetForm.value.widget_type !== "line") {
          // allow but default to month grouping
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
        const colors = shadeRamp(w.config || {}, (d.labels || []).length);
        return (d.labels || []).map(function (lab, i) {
          return { label: lab, value: (d.values || [])[i], color: colors[i] };
        });
      }

      function destroyCharts() {
        destroyMarginCharts();
        Object.keys(chartInstances).forEach(function (k) {
          if (chartInstances[k]) chartInstances[k].destroy();
          delete chartInstances[k];
        });
      }

      function renderMarginCharts() {
        if (!marginPresentMode.value) return;
        destroyMarginCharts();
        const mw = marginWidgets.value;
        const quoteData = mw.quoteBar ? widgetData.value[mw.quoteBar.id] : null;
        const gmData = mw.gmBar ? widgetData.value[mw.gmBar.id] : null;
        const layout = marginChartLayout();

        if (quoteData && quoteData.status === "ok" && quoteData.kind === "series" && mw.quoteBar) {
          const canvas = document.getElementById("margin-revenue-bar");
          if (canvas && typeof Chart !== "undefined") {
            const prefix = quoteData.prefix || "";
            const quoteValues = quoteData.values || [];
            const quoteCfg = mw.quoteBar.config || {};
            const barColors = shadeRamp(quoteCfg, quoteValues.length);
            const barHover = shadeHover(quoteCfg);
            marginChartInstances.revenueBar = new Chart(canvas, {
              type: "bar",
              data: {
                labels: quoteData.labels || [],
                datasets: [{
                  data: quoteValues,
                  backgroundColor: barColors,
                  hoverBackgroundColor: barHover,
                  borderRadius: 6,
                  categoryPercentage: 0.65,
                  barPercentage: 0.85,
                }],
              },
              options: {
                responsive: layout.responsive,
                maintainAspectRatio: layout.maintainAspectRatio,
                animation: layout.animation,
                plugins: {
                  legend: { display: false },
                  datalabels: { display: false },
                  tooltip: marginTooltip(function (c) { return prefix + fmtNum(c.parsed.y); }),
                },
                scales: {
                  x: { grid: { display: false }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 }, maxRotation: 0 } },
                  y: { beginAtZero: true, grid: { color: "#f2f3f5" }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
                },
              },
            });
          }
        }

        if (gmData && gmData.status === "ok" && gmData.kind === "series" && mw.gmBar) {
          const labels = gmData.labels || [];
          const values = gmData.values || [];
          const prefix = gmData.prefix || "";
          const gmCfg = mw.gmBar.config || {};
          const donutColors = shadeRamp(gmCfg, labels.length);
          const topN = 6;
          const hLabels = labels.slice(0, topN);
          const hValues = values.slice(0, topN);
          const hColors = shadeRamp(gmCfg, hValues.length);

          const donutCanvas = document.getElementById("margin-gm-donut");
          if (donutCanvas && typeof Chart !== "undefined") {
            marginChartInstances.gmDonut = new Chart(donutCanvas, {
              type: "doughnut",
              data: {
                labels: labels,
                datasets: [{
                  data: values,
                  backgroundColor: donutColors,
                  borderColor: "#fff",
                  borderWidth: 2,
                }],
              },
              options: {
                responsive: layout.responsive,
                maintainAspectRatio: layout.maintainAspectRatio,
                animation: layout.animation,
                cutout: "68%",
                plugins: {
                  legend: { display: false },
                  datalabels: { display: false },
                  centerTotal: { display: true, text: prefix + fmtNum(gmData.total) },
                  tooltip: marginTooltip(function (c) { return c.label + ": " + prefix + fmtNum(c.parsed); }),
                },
              },
            });
          }

          const hCanvas = document.getElementById("margin-gm-hbar");
          if (hCanvas && typeof Chart !== "undefined") {
            marginChartInstances.gmHbar = new Chart(hCanvas, {
              type: "bar",
              data: {
                labels: hLabels,
                datasets: [{ data: hValues, backgroundColor: hColors, borderRadius: 6, barPercentage: 0.72 }],
              },
              options: {
                responsive: layout.responsive,
                maintainAspectRatio: layout.maintainAspectRatio,
                animation: layout.animation,
                indexAxis: "y",
                plugins: {
                  legend: { display: false },
                  datalabels: { display: false },
                  tooltip: marginTooltip(function (c) { return prefix + fmtNum(c.parsed.x); }),
                },
                scales: {
                  x: { beginAtZero: true, grid: { color: "#f2f3f5" }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
                  y: { grid: { display: false }, border: { display: false }, ticks: { color: "#8f949b", font: { size: 10 } } },
                },
              },
            });
          }
        }
      }

      function renderChart(w, data) {
        if (!data || data.status !== "ok" || data.kind !== "series") return;
        const canvas = document.getElementById("chart-" + w.id);
        if (!canvas || typeof Chart === "undefined") return;
        if (chartInstances[w.id]) { chartInstances[w.id].destroy(); delete chartInstances[w.id]; }

        const cfg = w.config || {};
        const labels = data.labels || [];
        const values = data.values || [];
        const prefix = data.prefix || "";
        const pal = widgetPalette(cfg);
        const accent = pal[selectedShade(cfg)];

        if (w.widget_type === "pie") {
          chartInstances[w.id] = new Chart(canvas, {
            type: "doughnut",
            data: {
              labels: labels,
              datasets: [{
                data: values,
                backgroundColor: shadeRamp(cfg, labels.length),
                borderColor: "#fff",
                borderWidth: 2,
              }],
            },
            options: doughnutChartOptions(cfg, prefix, prefix + fmtNum(data.total)),
          });
          return;
        }

        if (w.widget_type === "bar") {
          chartInstances[w.id] = new Chart(canvas, {
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

        chartInstances[w.id] = new Chart(canvas, {
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

      function renderVisibleCharts() {
        if (marginPresentMode.value) {
          renderMarginCharts();
          return;
        }
        const tab = activeTab.value;
        if (!tab || !tab.widgets) return;
        tab.widgets.forEach(function (w) {
          if (["bar", "pie", "line"].indexOf(w.widget_type) >= 0) {
            renderChart(w, widgetData.value[w.id]);
          }
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
      function stepDashboard(dir) {
        if (dashboards.value.length < 2) return;
        const idx = dashboards.value.findIndex(function (d) { return d.id === activeDashboardId.value; });
        const next = (idx + dir + dashboards.value.length) % dashboards.value.length;
        selectDashboard(dashboards.value[next].id);
      }
      function closeDashMenu() { dashMenuOpen.value = false; }

      watch(activeTab, function () { reloadActiveTabData(); });

      watch(marginPresentMode, function () {
        destroyCharts();
        nextTick(function () { renderVisibleCharts(); });
      });

      watch(editMode, function () {
        destroyCharts();
        nextTick(function () { renderVisibleCharts(); });
      });

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
      function deleteActiveDashboard() {
        if (!activeDashboardId.value || !confirm("确定删除此看板？其标签页与组件将一并删除。")) return;
        api("DELETE", "/api/dashboards/" + activeDashboardId.value).then(function () {
          activeDashboardId.value = null;
          activeTabId.value = null;
          return loadDashboards();
        }).catch(function (e) { alert(e.message); });
      }

      function openTabModal() { tabForm.value = { name: "" }; showTabModal.value = true; }
      function saveTab() {
        if (!activeDashboardId.value) return;
        api("POST", "/api/dashboards/" + activeDashboardId.value + "/tabs", tabForm.value)
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
            { filters: (w.config && w.config.filters) ? w.config.filters.map(function (f) { return Object.assign({}, f); }) : [] }
          );
          if (merged.color_shade === undefined || merged.color_shade === null) merged.color_shade = 2;
          if (!merged.color) merged.color = base.config.color;
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
        panelOpen.value = true;
      }
      function closePanel() { panelOpen.value = false; colorPickerOpen.value = false; }
      function addFilter() {
        widgetForm.value.config.filters.push({ field: "", op: "eq", value: "" });
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
          filters: (c.filters || []).filter(function (x) { return x.field; }),
          prefix: c.prefix || "", suffix: c.suffix || "",
        };
        // date_group path: backend rejects a datetime group_by and re-derives it
        // from created_at, so send group_by empty and let the date_group drive it.
        if (isDateGroup.value) { out.group_by = ""; out.date_group = c.date_group; }
        if (isChart.value) {
          out.color = c.color;
          out.color_shade = Number(c.color_shade);
          if (!Number.isFinite(out.color_shade) || out.color_shade < 0 || out.color_shade > 4) out.color_shade = 2;
          out.sort = c.sort;
          out.show_legend = !!c.show_legend;
          out.show_value_center = !!c.show_value_center;
          out.data_labels = !!c.data_labels;
          out.hide_empty = !!c.hide_empty;
        }
        return out;
      }

      function saveWidget() {
        if (!activeTabId.value) return;
        const f = widgetForm.value;
        const payload = {
          title: f.title, widget_type: f.widget_type, source_key: f.source_key,
          config: buildConfig(), x: f.x, y: f.y, w: f.w, h: f.h,
        };
        const p = f.id
          ? api("PUT", "/api/dashboard-widgets/" + f.id, payload)
          : api("POST", "/api/dashboard-tabs/" + activeTabId.value + "/widgets", payload);
        p.then(function () { panelOpen.value = false; return loadDashboards(); })
          .then(function () { reloadActiveTabData(); })
          .catch(function (e) { alert(e.message); });
      }

      function deleteWidget(id) {
        if (!confirm("确定删除此组件？")) return;
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
          config: Object.assign({}, w.config || {}),
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
            if (marginPresentMode.value) nextTick(function () { renderMarginCharts(); });
          })
          .catch(function (e) { alert(e.message); });
      }

      onMounted(function () {
        fetch("/api/me", { headers: window.crmAuthHeader ? window.crmAuthHeader() : {}, credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (me) {
            const perms = me.permissions || [];
            canWrite.value = perms.indexOf("dashboard.write") >= 0 || me.is_super;
          });
        api("GET", "/api/dashboard-metadata").then(function (m) { metadata.value = m; });
        api("GET", "/api/dashboard/roster-clients")
          .then(function (r) { rosterClients.value = (r && r.clients) || []; })
          .catch(function () { rosterClients.value = []; });
        loadDashboards();
      });

      return {
        dashboards, activeDashboardId, activeTabId, activeDashboard, activeTab, tabIndex,
        marginPresentMode, marginWidgets, marginPanelLabels,
        marginDashboardEditLayout, marginPresetWidgets, marginExtraWidgets,
        marginPresetEditCards, marginExtraEditCards,
        marginPresetEditCardStyle, marginExtraEditCardStyle, isMarginPresetWidget,
        marginPanelQuoteState, marginPanelGmState, marginPanelMetricsState,
        marginQuoteLegend, marginDonutLegend, marginMetricRows, marginClientColumnLabel,
        metadata, widgetData, canWrite, editMode, dashMenuOpen, rosterClients, rosterScope,
        showDashboardModal, showTabModal, panelOpen,
        dashboardForm, tabForm, widgetForm,
        needsDataSource, needsField, needsGroupBy, isChart, isDateGroup, isRosterSummary,
        sourceFields, numericFields, groupByFields,
        colorPickerOpen, colorSearch, filteredColorRows, selectedColorRowLabel,
        isColorSwatchActive, pickColor, closeColorPicker, widgetPalette, selectedShade,
        cardStyle, themeColor, swatchColor, sourceLabel, metricLabel, typeLabel, typeIcon,
        richTitle, richBody, showLegend, legendOf,
        rosterTiles, rosterScopeLabel, rosterHeadcount, isRosterClientCard,
        selectDashboard, stepDashboard, closeDashMenu,
        openDashboardModal, saveDashboard, deleteActiveDashboard,
        openTabModal, saveTab, openWidgetPanel, closePanel, addFilter, saveWidget, deleteWidget,
        duplicateWidget, changeRosterClient,
      };
    },
  }).mount("#page-app");
})();
