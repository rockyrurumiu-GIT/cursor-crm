/**
 * Dashboard builder page (Twenty-parity B: polish + slide-over config panel).
 * Requires: Vue 3 CDN, Chart.js 4.4.9, chartjs-plugin-datalabels 2.2.0, window.crmAuthHeader()
 */
(function () {
  "use strict";

  const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
  const chartInstances = {};

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

  // Soft categorical palette for pie/doughnut segments. Pie intentionally IGNORES the
  // widget `color` setting and always uses this multi-hue palette — categorical charts
  // should be multi-colored. `color` only affects bar / line / number accent. This is a
  // design choice, not a bug.
  const CATEGORICAL = ["#B4C4D8", "#C2D4C8", "#E8D4B0", "#E4C4BC", "#C9C0DC", "#D0D3D8", "#C5D0DE", "#DDD4C4"];

  function themeOf(color) {
    return COLOR_THEMES[color] || COLOR_THEMES[DEFAULT_THEME];
  }
  function paletteFor(color, n) {
    // Categorical (pie) palette — `color` arg is ignored by design (see CATEGORICAL note).
    const out = [];
    for (let i = 0; i < n; i++) out.push(CATEGORICAL[i % CATEGORICAL.length]);
    return out;
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
            filters: [], color: DEFAULT_THEME, sort: "value_desc",
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

      function themeColor(w) { return themeOf((w.config || {}).color).base; }
      function swatchColor(c) { return themeOf(c).base; }

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
        const colors = paletteFor((w.config || {}).color, (d.labels || []).length);
        return (d.labels || []).map(function (lab, i) {
          return { label: lab, value: (d.values || [])[i], color: colors[i] };
        });
      }

      function destroyCharts() {
        Object.keys(chartInstances).forEach(function (k) {
          if (chartInstances[k]) chartInstances[k].destroy();
          delete chartInstances[k];
        });
      }

      function renderChart(w, data) {
        if (!data || data.status !== "ok" || data.kind !== "series") return;
        const canvas = document.getElementById("chart-" + w.id);
        if (!canvas || typeof Chart === "undefined") return;
        if (chartInstances[w.id]) { chartInstances[w.id].destroy(); delete chartInstances[w.id]; }

        const cfg = w.config || {};
        const labels = data.labels || [];
        const values = data.values || [];
        const accent = themeOf(cfg.color).base;
        const prefix = data.prefix || "";

        if (w.widget_type === "pie") {
          chartInstances[w.id] = new Chart(canvas, {
            type: "doughnut",
            // Pie ignores cfg.color by design (CATEGORICAL note above).
            data: { labels: labels, datasets: [{ data: values, backgroundColor: paletteFor(cfg.color, labels.length), borderColor: "#fff", borderWidth: 2 }] },
            options: doughnutChartOptions(cfg, prefix, prefix + fmtNum(data.total)),
          });
          return;
        }

        if (w.widget_type === "bar") {
          chartInstances[w.id] = new Chart(canvas, {
            type: "bar",
            data: { labels: labels, datasets: [{ label: w.title, data: values, backgroundColor: accent, borderRadius: 4, categoryPercentage: 0.65, barPercentage: 0.85 }] },
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
              backgroundColor: hexA(accent, 0.08), fill: true, tension: 0.25,
              pointRadius: 0, pointBackgroundColor: accent, borderWidth: 2,
            }],
          },
          options: lineChartOptions(cfg, prefix),
        });
      }

      function loadWidgetData(widgets) {
        if (!widgets || !widgets.length) return;
        widgets.forEach(function (w) {
          api("GET", "/api/dashboard-widgets/" + w.id + "/data").then(function (data) {
            widgetData.value[w.id] = data;
            if (["bar", "pie", "line"].indexOf(w.widget_type) >= 0) {
              nextTick(function () { renderChart(w, data); });
            }
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
          widgetForm.value = {
            id: w.id,
            title: w.title,
            widget_type: w.widget_type,
            source_key: w.source_key || "",
            config: Object.assign(base.config, w.config || {}, { filters: (w.config && w.config.filters) ? w.config.filters.map(function (f) { return Object.assign({}, f); }) : [] }),
            x: w.x, y: w.y, w: w.w, h: w.h,
          };
          rosterScope.value = (w.config && w.config.client_id != null) ? "client" : "all";
        } else {
          widgetForm.value = blankWidget();
          rosterScope.value = "all";
        }
        panelOpen.value = true;
      }
      function closePanel() { panelOpen.value = false; }
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
          out.color = c.color; out.sort = c.sort;
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
          .then(function (data) { widgetData.value[w.id] = data; })
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
        metadata, widgetData, canWrite, editMode, dashMenuOpen, rosterClients, rosterScope,
        showDashboardModal, showTabModal, panelOpen,
        dashboardForm, tabForm, widgetForm,
        needsDataSource, needsField, needsGroupBy, isChart, isDateGroup, isRosterSummary,
        sourceFields, numericFields, groupByFields,
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
