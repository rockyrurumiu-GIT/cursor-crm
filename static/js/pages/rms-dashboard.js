/**
 * RMS recruitment dashboard — Twenty-style editable widget boards.
 * Uses shared DashboardWidgetKit for CRM-style widget config capabilities.
 */
(function () {
  "use strict";

  var MOUNT_ID = "rms-dashboard-app";
  var KIT = window.DashboardWidgetKit;
  var CHART_BLOCKS = {
    chart_pipeline: true,
    chart_history_pass: true,
    chart_recruiter: true,
  };

  function showMountError(msg) {
    var root = document.getElementById(MOUNT_ID);
    if (!root) return;
    var safe = String(msg || "未知错误")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    root.innerHTML =
      '<div class="state-msg state-forbidden" style="padding:2rem 1.25rem;text-align:center;">' +
      '<p style="font-weight:600;margin-bottom:0.5rem;color:#cf222e;">招聘 Dashboard 无法加载</p>' +
      '<p style="font-size:0.85rem;color:#57606a;">' + safe + "</p></div>";
  }

  if (typeof Vue === "undefined" || !Vue.createApp) {
    showMountError("Vue 未加载。请检查 Console / Network 中 vue.global.js 是否返回 200。");
    return;
  }
  if (!KIT) {
    showMountError("DashboardWidgetKit 未加载。请检查 /static/js/shared/dashboard-widget-kit.js。");
    return;
  }

  var createApp = Vue.createApp;
  var ref = Vue.ref;
  var reactive = Vue.reactive;
  var computed = Vue.computed;
  var watch = Vue.watch;
  var onMounted = Vue.onMounted;
  var nextTick = Vue.nextTick;

  var chartInstances = {};
  var widgetAutosaveTimer = null;
  var widgetPersistInFlight = false;
  var widgetPersistQueued = false;

  KIT.installChartPlugins(typeof Chart !== "undefined" ? Chart : undefined, typeof ChartDataLabels !== "undefined" ? ChartDataLabels : undefined);

  function formatRmsDate(value) {
    if (value == null || value === "") return "—";
    var s = String(value).trim().slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : "—";
  }

  function api(method, path, body) {
    var opts = {
      method: method,
      credentials: "same-origin",
      headers: Object.assign({}, window.crmAuthHeader ? window.crmAuthHeader() : {}),
    };
    if (body != null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (b) {
          throw new Error((b && b.detail) || r.statusText || "请求失败");
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

  function buildQuery(filters) {
    var params = new URLSearchParams();
    Object.keys(filters).forEach(function (k) {
      var v = filters[k];
      if (v !== "" && v != null) params.set(k, String(v));
    });
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
    return ["#7B96B8", "#88A992", "#D6A461", "#CD9180", "#9389AE", "#9AA0A6", "#B4C4D8", "#C2D4C8"].slice(0, Math.max(1, n)).concat();
  }

  function parsePassRate(rateStr) {
    if (!rateStr || rateStr === "—") return 0;
    var n = parseFloat(String(rateStr).replace("%", ""));
    return Number.isFinite(n) ? n : 0;
  }

  function horizontalBarOptions(prefix) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: "y",
      plugins: {
        legend: { display: false },
        datalabels: { display: false },
        tooltip: whiteTooltip(function (c) { return prefix + String(c.parsed.x); }),
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: "#f2f3f5" },
          border: { display: false },
          ticks: { color: "#8f949b", font: { size: 10 }, precision: 0 },
        },
        y: {
          grid: { display: false },
          border: { display: false },
          ticks: { color: "#8f949b", font: { size: 10 } },
        },
      },
    };
  }

  function richTitle(text) {
    var t = (text || "").trim();
    var nl = t.indexOf("\n");
    return nl < 0 ? "" : t.slice(0, nl).trim();
  }

  function richBody(text) {
    var t = (text || "").trim();
    var nl = t.indexOf("\n");
    return nl < 0 ? t : t.slice(nl + 1).trim();
  }

  try {
    createApp({
      directives: {
        "click-outside": {
          mounted: function (el, binding) {
            el._cob = function (e) {
              if (!el.contains(e.target) && typeof binding.value === "function") binding.value();
            };
            document.addEventListener("click", el._cob, true);
          },
          unmounted: function (el) {
            document.removeEventListener("click", el._cob, true);
          },
        },
      },
      setup: function () {
        var loading = ref(false);
        var rosterLoading = ref(false);
        var error = ref("");
        var data = ref(null);
        var rosterCheck = ref(null);
        var dashboards = ref([]);
        var metadata = ref({
          sources: [],
          widget_types: [],
          metrics: [],
          date_groups: [],
          colors: [],
          sorts: [],
          rms_blocks: [],
        });
        var widgetData = ref({});
        var rosterClients = ref([]);
        var canWrite = ref(false);
        var editMode = ref(false);

        var activeDashboardId = ref(null);
        var activeTabId = ref(null);

        var showDashboardModal = ref(false);
        var showTabModal = ref(false);
        var panelOpen = ref(false);
        var panelAutosaveReady = ref(false);
        var panelUserEdited = ref(false);
        var dashboardForm = ref({ id: null, name: "", description: "" });
        var tabForm = ref({ name: "", rms_template: "overview" });

        var colorPickerOpen = ref(false);
        var colorSearch = ref("");
        var rosterScope = ref("all");
        var widgetForm = ref(blankWidget());

        var clientOptions = ref([]);
        var jobOptions = ref([]);
        var userOptions = ref([]);

        var filters = reactive({
          client_id: "",
          job_id: "",
          priority: "",
          city: "",
          sales_user_id: "",
          delivery_user_id: "",
          recruiter_user_id: "",
          date_from: "",
          date_to: "",
        });

        function blankWidget() {
          var w = KIT.blankWidget({ widget_type: "number" });
          if (!w.config) w.config = {};
          if (!w.config.block) w.config.block = "kpi_jobs";
          if (!Array.isArray(w.config.filters)) w.config.filters = [];
          if (!Array.isArray(w.config.extra_views)) w.config.extra_views = [];
          if (!w.source_key) w.source_key = "clients";
          return w;
        }

        var activeDashboard = computed(function () {
          return dashboards.value.find(function (d) { return d.id === activeDashboardId.value; }) || null;
        });
        var activeTab = computed(function () {
          var d = activeDashboard.value;
          if (!d || !d.tabs) return null;
          return d.tabs.find(function (t) { return t.id === activeTabId.value; }) || null;
        });

        var displayItems = computed(function () {
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return [];
          var out = [];
          tab.widgets.forEach(function (w) {
            out.push({
              key: "p-" + w.id,
              kind: "primary",
              widget: w,
              title: w.title,
              style: cardStyle(w),
              block: widgetBlock(w),
              isExtra: false,
              extraView: null,
              viewIndex: null,
            });
            var views = (w.config && w.config.extra_views) || [];
            views.forEach(function (ev, idx) {
              out.push({
                key: "e-" + w.id + "-" + idx,
                kind: "extra",
                widget: w,
                title: (ev.title || "").trim() || w.title,
                style: cardStyle(ev),
                block: widgetBlock(w),
                isExtra: true,
                extraView: ev,
                viewIndex: idx,
              });
            });
          });
          return out;
        });

        var historicalStages = computed(function () {
          var hist = data.value && data.value.historical_overview;
          if (!hist || !hist.length) return [];
          return hist[0].stages || [];
        });

        var activeFilterSummary = computed(function () {
          var labels = {
            client_id: "客户ID",
            job_id: "岗位ID",
            priority: "优先级",
            city: "城市",
            sales_user_id: "销售用户ID",
            delivery_user_id: "交付用户ID",
            recruiter_user_id: "推荐人用户ID",
            date_from: "推荐日起",
            date_to: "推荐日止",
          };
          var out = [];
          Object.keys(labels).forEach(function (k) {
            var v = filters[k];
            if (v !== "" && v != null) out.push({ key: k, label: labels[k], value: String(v) });
          });
          return out;
        });

        var clientFieldLabel = computed(function () { return clientOptions.value.length ? "客户" : "客户ID"; });
        var jobFieldLabel = computed(function () { return jobOptions.value.length ? "岗位" : "岗位ID"; });
        var salesFieldLabel = computed(function () { return userOptions.value.length ? "销售" : "销售用户ID"; });
        var deliveryFieldLabel = computed(function () { return userOptions.value.length ? "交付" : "交付用户ID"; });
        var recruiterFieldLabel = computed(function () { return userOptions.value.length ? "推荐人" : "推荐人用户ID"; });

        var tabNeedsDashboardData = computed(function () {
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return false;
          return tab.widgets.some(function (w) {
            var b = widgetBlock(w);
            return !!(b && (b === "filter" || b.indexOf("roster_") !== 0));
          });
        });
        var tabNeedsRosterData = computed(function () {
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return false;
          return tab.widgets.some(function (w) {
            var b = widgetBlock(w);
            return b && b.indexOf("roster_") === 0;
          });
        });

        var needsDataSource = computed(function () {
          return KIT.DATA_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
        });
        var needsField = computed(function () {
          var metric = widgetForm.value.config && widgetForm.value.config.metric;
          return ["sum", "avg", "min", "max"].indexOf(metric) >= 0;
        });
        var needsGroupBy = computed(function () {
          return KIT.CHART_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
        });
        var isChart = computed(function () {
          return KIT.CHART_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
        });
        var isRosterSummary = computed(function () {
          return widgetForm.value.widget_type === "roster_summary";
        });
        var isRmsBlock = computed(function () {
          return widgetForm.value.widget_type === "rms_block";
        });

        var sourceFields = computed(function () {
          var src = (metadata.value.sources || []).find(function (s) { return s.key === widgetForm.value.source_key; });
          return src ? src.fields : [];
        });
        var numericFields = computed(function () {
          return sourceFields.value.filter(function (f) { return f.kind === "numeric"; });
        });
        var groupByFields = computed(function () {
          return sourceFields.value.filter(function (f) { return f.kind === "text" || f.kind === "datetime"; });
        });
        var isDateGroup = computed(function () {
          var f = sourceFields.value.find(function (x) { return x.key === (widgetForm.value.config && widgetForm.value.config.group_by); });
          return needsGroupBy.value && f && f.kind === "datetime";
        });

        var filteredColorRows = computed(function () {
          var q = (colorSearch.value || "").trim().toLowerCase();
          if (!q) return KIT.TWENTY_COLOR_ROWS;
          return KIT.TWENTY_COLOR_ROWS.filter(function (r) {
            return r.label.toLowerCase().indexOf(q) >= 0 || r.key.indexOf(q) >= 0;
          });
        });
        var selectedColorRowLabel = computed(function () {
          var row = KIT.colorRowOf(widgetForm.value.config && widgetForm.value.config.color);
          var si = KIT.selectedShade(widgetForm.value.config || {});
          return row.label + " · " + (si + 1);
        });

        function isColorSwatchActive(row, shadeIndex) {
          var cfg = widgetForm.value.config || {};
          return cfg.color === row.key && KIT.selectedShade(cfg) === shadeIndex;
        }
        function pickColor(key, shadeIndex) {
          if (!widgetForm.value.config) widgetForm.value.config = {};
          widgetForm.value.config.color = key;
          widgetForm.value.config.color_shade = shadeIndex;
          flushPersistWidget();
        }
        function closeColorPicker() {
          colorPickerOpen.value = false;
        }

        function cardStyle(w) {
          var x = Math.max(0, Math.min(11, w.x || 0));
          var ww = Math.max(1, Math.min(12, w.w || 4));
          return {
            gridColumn: (x + 1) + " / span " + ww,
            gridRow: ((w.y || 0) + 1) + " / span " + Math.max(1, w.h || 3),
          };
        }

        function typeLabel(t) { return KIT.TYPE_LABELS[t] || t; }
        function typeIcon(t) { return KIT.TYPE_ICONS[t] || "▢"; }
        function sourceLabel(key) {
          var s = (metadata.value.sources || []).find(function (x) { return x.key === key; });
          return s ? s.label : "";
        }
        function metricLabel(m) { return KIT.METRIC_LABELS[m] || m; }
        function extraRenderLabel(render) { return KIT.extraRenderLabel(render); }
        function themeColor(w) { return KIT.themeOf((w && w.config) || {}).base; }
        function showLegend(w) { return (w.config || {}).show_legend !== false; }
        function legendOf(w) {
          var d = widgetData.value[w.id];
          if (!d || d.kind !== "series") return [];
          var colors = KIT.shadeRamp(w.config || {}, (d.labels || []).length);
          return (d.labels || []).map(function (lab, i) {
            return { label: lab, value: (d.values || [])[i], color: colors[i] };
          });
        }
        function rosterTiles(w) {
          var d = widgetData.value[w.id];
          if (!d || d.kind !== "roster_summary") return [];
          return [
            { label: "月报价合计", display: d.revenue ? d.revenue.display : "—", color: "#7B96B8" },
            { label: "税前工资合计", display: d.salary ? d.salary.display : "—", color: "#9389AE" },
            { label: "GM$", display: d.gms ? d.gms.display : "—", color: "#88A992" },
            { label: "GM%", display: d.gm_pct ? d.gm_pct.display : "—", color: "#D6A461" },
          ];
        }
        function rosterScopeLabel(w) {
          var d = widgetData.value[w.id];
          if (!d || d.kind !== "roster_summary") return "";
          if (d.scope === "client") return (d.client_name || "未知客户") + " · " + (d.headcount || 0) + " 人";
          return "全公司 · " + (d.headcount || 0) + " 人";
        }
        function rosterHeadcount(w) {
          var d = widgetData.value[w.id];
          return d && d.kind === "roster_summary" ? (d.headcount || 0) + " 人" : "";
        }
        function isRosterClientCard(w) {
          return w.widget_type === "roster_summary" && (w.config || {}).client_id != null;
        }

        function cardCanvasId(item) {
          if (item && item.isExtra) return KIT.chartCanvasId(item.widget, item.viewIndex);
          return KIT.chartCanvasId(item.widget, null);
        }
        function openDisplayItemPanel(item) {
          openWidgetPanel(item.widget);
        }

        function renderPipelineChart(canvasId) {
          if (!data.value) return;
          safeRenderChart(canvasId, function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            destroyChartKey(canvasId);
            var items = data.value.pipeline_overview || [];
            chartInstances[canvasId] = new Chart(canvas, {
              type: "bar",
              data: {
                labels: items.map(function (x) { return x.label; }),
                datasets: [{
                  data: items.map(function (x) { return x.count; }),
                  backgroundColor: rmsShadeRamp(items.length),
                  borderRadius: 6,
                  barPercentage: 0.72,
                }],
              },
              options: horizontalBarOptions(""),
            });
          });
        }
        function renderHistoryChart(canvasId) {
          if (!data.value) return;
          safeRenderChart(canvasId, function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            destroyChartKey(canvasId);
            var stages = historicalStages.value.filter(function (s) { return s.stage !== "hired_summary"; });
            chartInstances[canvasId] = new Chart(canvas, {
              type: "bar",
              data: {
                labels: stages.map(function (s) { return s.label; }),
                datasets: [{
                  data: stages.map(function (s) { return parsePassRate(s.pass_rate); }),
                  backgroundColor: rmsShadeRamp(stages.length),
                  borderRadius: 6,
                  barPercentage: 0.72,
                }],
              },
              options: horizontalBarOptions("%"),
            });
          });
        }
        function renderRecruiterChart(canvasId) {
          if (!data.value) return;
          safeRenderChart(canvasId, function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            destroyChartKey(canvasId);
            var rows = (data.value.recruiter_performance || []).slice().sort(function (a, b) {
              return (b.hired_this_month || 0) - (a.hired_this_month || 0);
            }).slice(0, 10);
            chartInstances[canvasId] = new Chart(canvas, {
              type: "bar",
              data: {
                labels: rows.map(function (r) {
                  return r.recruiter_user_id != null ? "ID " + r.recruiter_user_id : "—";
                }),
                datasets: [{
                  data: rows.map(function (r) { return r.hired_this_month || 0; }),
                  backgroundColor: rmsShadeRamp(rows.length),
                  borderRadius: 6,
                  barPercentage: 0.72,
                }],
              },
              options: horizontalBarOptions(""),
            });
          });
        }

        function renderVisibleCharts() {
          if (!chartsAvailable()) return;
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return;

          tab.widgets.forEach(function (w) {
            var block = widgetBlock(w);
            var rmsId = chartCanvasId(w);

            if (block === "chart_pipeline") {
              renderPipelineChart(rmsId);
              return;
            }
            if (block === "chart_history_pass") {
              renderHistoryChart(rmsId);
              return;
            }
            if (block === "chart_recruiter") {
              renderRecruiterChart(rmsId);
              return;
            }

            if (KIT.CHART_WIDGET_TYPES.indexOf(w.widget_type) >= 0) {
              var wd = widgetData.value[w.id];
              if (!wd) return;
              KIT.renderCrmChart(chartInstances, destroyChartKey, w, wd, { viewIndex: null });
              var views = (w.config && w.config.extra_views) || [];
              views.forEach(function (ev, idx) {
                KIT.renderCrmChart(chartInstances, destroyChartKey, w, wd, {
                  render: ev.render,
                  viewIndex: idx,
                  canvasId: KIT.chartCanvasId(w, idx),
                  limit: ev.limit != null ? ev.limit : 6,
                });
              });
            }
          });
        }

        function loadWidgetData(widgets) {
          if (!widgets || !widgets.length) return;
          widgets.forEach(function (w) {
            if (w.widget_type === "rms_block") return;
            api("GET", "/api/rms/dashboard-widgets/" + w.id + "/data")
              .then(function (d) {
                widgetData.value[w.id] = d;
                nextTick(function () { renderVisibleCharts(); });
              })
              .catch(function () {
                widgetData.value[w.id] = { status: "error" };
              });
          });
        }

        function reloadActiveTabData() {
          destroyAllCharts();
          widgetData.value = {};
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return;
          if (tabNeedsDashboardData.value) {
            loadDashboard();
          } else {
            data.value = null;
          }
          if (tabNeedsRosterData.value && !rosterCheck.value) {
            loadRosterCheck();
          }
          loadWidgetData(tab.widgets);
        }

        function selectDashboard(id) {
          activeDashboardId.value = id;
          var d = dashboards.value.find(function (x) { return x.id === id; });
          activeTabId.value = d && d.tabs && d.tabs.length ? d.tabs[0].id : null;
        }

        function selectTab(id) {
          if (activeTabId.value === id) return;
          activeTabId.value = id;
        }

        function loadBoards() {
          return apiGet("/api/rms/dashboard-boards").then(function (list) {
            dashboards.value = Array.isArray(list) ? list : [];
            if (!activeDashboardId.value && dashboards.value.length) {
              activeDashboardId.value = dashboards.value[0].id;
            }
            var d = dashboards.value.find(function (x) { return x.id === activeDashboardId.value; });
            if (d && d.tabs && d.tabs.length) {
              if (!d.tabs.some(function (t) { return t.id === activeTabId.value; })) {
                activeTabId.value = d.tabs[0].id;
              }
            } else {
              activeTabId.value = null;
            }
          });
        }

        function loadDashboard() {
          loading.value = true;
          error.value = "";
          return apiGet("/api/rms/dashboard" + buildQuery(filters))
            .then(function (res) {
              data.value = res;
              return nextTick();
            })
            .then(function () {
              renderVisibleCharts();
            })
            .catch(function (e) {
              error.value = e.message || String(e);
            })
            .finally(function () {
              loading.value = false;
            });
        }

        function loadFilterOptions() {
          apiGetOptional("/api/clients").then(function (clients) {
            clientOptions.value = Array.isArray(clients) ? clients : [];
          }).catch(function () {
            clientOptions.value = [];
          });
          apiGetOptional("/api/rms/jobs").then(function (jobs) {
            jobOptions.value = Array.isArray(jobs) ? jobs : (jobs && jobs.items ? jobs.items : []);
          }).catch(function () {
            jobOptions.value = [];
          });
          apiGetOptional("/api/clients/assign-options").then(function (assign) {
            userOptions.value = assign && Array.isArray(assign.users) ? assign.users : [];
          }).catch(function () {
            userOptions.value = [];
          });
        }

        function loadRosterCheck() {
          rosterLoading.value = true;
          return apiGet(
            "/api/rms/applications/hired-roster-check" + buildQuery({
              client_id: filters.client_id,
              job_id: filters.job_id,
              recruiter_user_id: filters.recruiter_user_id,
              date_from: filters.date_from,
              date_to: filters.date_to,
            })
          ).then(function (res) {
            rosterCheck.value = res;
          }).catch(function (e) {
            error.value = e.message || String(e);
          }).finally(function () {
            rosterLoading.value = false;
          });
        }

        function findTabWithBlock(blockKey) {
          for (var i = 0; i < dashboards.value.length; i++) {
            var d = dashboards.value[i];
            if (!d.tabs) continue;
            for (var j = 0; j < d.tabs.length; j++) {
              var t = d.tabs[j];
              if (!t.widgets) continue;
              for (var k = 0; k < t.widgets.length; k++) {
                if (widgetBlock(t.widgets[k]) === blockKey) return t.id;
              }
            }
          }
          return null;
        }

        function goRosterTab() {
          var tabId = findTabWithBlock("roster_header") || findTabWithBlock("table_roster");
          if (!tabId) return;
          activeTabId.value = tabId;
          if (!rosterCheck.value) loadRosterCheck();
        }

        function openDashboardModal() {
          dashboardForm.value = { id: null, name: "", description: "" };
          showDashboardModal.value = true;
        }
        function saveDashboard() {
          var f = dashboardForm.value;
          api("POST", "/api/rms/dashboard-boards", {
            name: f.name,
            description: f.description,
          }).then(function (created) {
            showDashboardModal.value = false;
            if (created && created.id) activeDashboardId.value = created.id;
            return loadBoards();
          }).then(function () {
            reloadActiveTabData();
          }).catch(function (e) {
            error.value = e.message || String(e);
          });
        }
        function deleteActiveDashboard() {
          if (!activeDashboardId.value) return;
          window.crmConfirmDeleteDialog({
            title: "确认删除",
            targetText: "将删除当前看板及其标签页",
            hint: "删除后不可恢复。",
          }).then(function (ok) {
            if (!ok) return;
            return api("DELETE", "/api/rms/dashboard-boards/" + activeDashboardId.value).then(function () {
              activeDashboardId.value = null;
              activeTabId.value = null;
              return loadBoards();
            });
          }).catch(function (e) {
            if (e) error.value = e.message || String(e);
          });
        }

        function openTabModal() {
          tabForm.value = { name: "", rms_template: "overview" };
          showTabModal.value = true;
        }
        function saveTab() {
          if (!activeDashboardId.value) return;
          api("POST", "/api/rms/dashboard-boards/" + activeDashboardId.value + "/tabs", {
            name: tabForm.value.name,
            rms_template: tabForm.value.rms_template,
          }).then(function () {
            showTabModal.value = false;
            return loadBoards();
          }).then(function () {
            var d = dashboards.value.find(function (x) { return x.id === activeDashboardId.value; });
            if (d && d.tabs && d.tabs.length) activeTabId.value = d.tabs[d.tabs.length - 1].id;
            return nextTick();
          }).then(function () {
            reloadActiveTabData();
          }).catch(function (e) {
            error.value = e.message || String(e);
          });
        }

        function clearWidgetAutosaveTimer() {
          if (widgetAutosaveTimer) {
            clearTimeout(widgetAutosaveTimer);
            widgetAutosaveTimer = null;
          }
        }
        function canAutosaveWidget() {
          return panelAutosaveReady.value && panelOpen.value && activeTabId.value && (widgetForm.value.id || panelUserEdited.value);
        }
        function schedulePersistWidget(delayMs) {
          if (!canAutosaveWidget()) return;
          clearWidgetAutosaveTimer();
          widgetAutosaveTimer = setTimeout(function () {
            widgetAutosaveTimer = null;
            flushPersistWidget();
          }, delayMs == null ? 420 : delayMs);
        }
        function buildConfig() {
          return KIT.buildConfig(
            widgetForm.value,
            rosterScope.value,
            function () { return isDateGroup.value; },
            function () { return isChart.value; }
          );
        }

        function flushPersistWidget() {
          clearWidgetAutosaveTimer();
          if (!canAutosaveWidget()) return Promise.resolve();
          if (widgetPersistInFlight) {
            widgetPersistQueued = true;
            return Promise.resolve();
          }
          widgetPersistInFlight = true;
          var f = widgetForm.value;
          var payload = {
            title: f.title,
            widget_type: f.widget_type,
            source_key: f.source_key || "",
            config: buildConfig(),
            x: f.x,
            y: f.y,
            w: f.w,
            h: f.h,
          };
          var isNew = !f.id;
          var req = isNew
            ? api("POST", "/api/rms/dashboard-tabs/" + activeTabId.value + "/widgets", payload)
            : api("PUT", "/api/rms/dashboard-widgets/" + f.id, payload);
          return req
            .then(function (res) {
              if (isNew && res && res.id) widgetForm.value.id = res.id;
              return loadBoards();
            })
            .then(function () {
              reloadActiveTabData();
            })
            .catch(function (e) {
              error.value = e.message || String(e);
            })
            .finally(function () {
              widgetPersistInFlight = false;
              if (widgetPersistQueued) {
                widgetPersistQueued = false;
                flushPersistWidget();
              }
            });
        }

        function openWidgetPanel(w) {
          if (w) {
            var base = blankWidget();
            var mergedCfg = Object.assign(
              {},
              base.config || {},
              w.config || {},
              {
                filters: (w.config && w.config.filters) ? w.config.filters.map(function (f) { return Object.assign({}, f); }) : [],
                extra_views: (w.config && w.config.extra_views) ? w.config.extra_views.map(function (ev) { return Object.assign({}, ev); }) : [],
              }
            );
            if (!mergedCfg.block) mergedCfg.block = "kpi_jobs";
            if (!mergedCfg.color) mergedCfg.color = "green";
            if (mergedCfg.color_shade == null) mergedCfg.color_shade = 2;
            widgetForm.value = {
              id: w.id,
              title: w.title,
              widget_type: w.widget_type,
              source_key: w.source_key || "",
              config: mergedCfg,
              x: w.x,
              y: w.y,
              w: w.w,
              h: w.h,
            };
            rosterScope.value = mergedCfg.client_id != null ? "client" : "all";
          } else {
            widgetForm.value = blankWidget();
            rosterScope.value = "all";
          }
          colorSearch.value = "";
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
        function selectWidgetType(t) {
          if (widgetForm.value.widget_type === t) return;
          panelUserEdited.value = true;
          widgetForm.value.widget_type = t;
          if (!widgetForm.value.config) widgetForm.value.config = {};
          if (t === "rms_block" && !widgetForm.value.config.block) {
            widgetForm.value.config.block = "kpi_jobs";
          }
          if (t === "roster_summary") {
            widgetForm.value.source_key = "roster_entries";
          }
          flushPersistWidget();
        }
        function addFilter() {
          if (!widgetForm.value.config) widgetForm.value.config = {};
          if (!Array.isArray(widgetForm.value.config.filters)) widgetForm.value.config.filters = [];
          widgetForm.value.config.filters.push({ field: "", op: "eq", value: "" });
          schedulePersistWidget(420);
        }
        function removeFilter(idx) {
          if (!widgetForm.value.config || !Array.isArray(widgetForm.value.config.filters)) return;
          widgetForm.value.config.filters.splice(idx, 1);
          flushPersistWidget();
        }
        function addExtraView() {
          if (!widgetForm.value.config) widgetForm.value.config = {};
          if (!Array.isArray(widgetForm.value.config.extra_views)) widgetForm.value.config.extra_views = [];
          widgetForm.value.config.extra_views.push({ render: "doughnut", x: 0, y: 0, w: 6, h: 6, limit: 6, title: "" });
          flushPersistWidget();
        }
        function removeExtraView(idx) {
          if (!widgetForm.value.config || !Array.isArray(widgetForm.value.config.extra_views)) return;
          widgetForm.value.config.extra_views.splice(idx, 1);
          flushPersistWidget();
        }
        function deleteWidget(id) {
          window.crmConfirmDeleteDialog({
            title: "确认删除",
            targetText: "将删除当前组件",
            hint: "删除后不可恢复。",
          }).then(function (ok) {
            if (!ok) return;
            return api("DELETE", "/api/rms/dashboard-widgets/" + id)
              .then(function () { return loadBoards(); })
              .then(function () { reloadActiveTabData(); });
          }).catch(function (e) {
            if (e) error.value = e.message || String(e);
          });
        }
        function duplicateWidget(w) {
          if (!activeTabId.value) return;
          api("POST", "/api/rms/dashboard-tabs/" + activeTabId.value + "/widgets", {
            title: w.title + " 副本",
            widget_type: w.widget_type,
            source_key: w.source_key || "",
            config: Object.assign({}, w.config || {}, {
              filters: (w.config && w.config.filters) ? w.config.filters.map(function (f) { return Object.assign({}, f); }) : [],
              extra_views: (w.config && w.config.extra_views) ? w.config.extra_views.map(function (ev) { return Object.assign({}, ev); }) : [],
            }),
            x: Math.min(8, (w.x || 0) + 1),
            y: (w.y || 0) + (w.h || 3),
            w: w.w,
            h: w.h,
          }).then(function () {
            return loadBoards();
          }).then(function () {
            reloadActiveTabData();
          }).catch(function (e) {
            error.value = e.message || String(e);
          });
        }
        function changeRosterClient(w, clientId) {
          var cid = clientId === "" || clientId == null ? null : Number(clientId);
          var payload = {
            title: w.title,
            widget_type: w.widget_type,
            source_key: w.source_key || "roster_entries",
            config: Object.assign({}, w.config || {}, { client_id: cid }),
            x: w.x,
            y: w.y,
            w: w.w,
            h: w.h,
          };
          api("PUT", "/api/rms/dashboard-widgets/" + w.id, payload)
            .then(function () {
              w.config = payload.config;
              return api("GET", "/api/rms/dashboard-widgets/" + w.id + "/data");
            })
            .then(function (d) {
              widgetData.value[w.id] = d;
              nextTick(function () { renderVisibleCharts(); });
            })
            .catch(function (e) {
              error.value = e.message || String(e);
            });
        }

        function blockLabel(key) {
          var row = (metadata.value.rms_blocks || []).find(function (b) { return b.key === key; });
          return row ? row.label : key;
        }

        watch(activeTab, function () {
          reloadActiveTabData();
        });
        watch(editMode, function () {
          destroyAllCharts();
          nextTick(function () { renderVisibleCharts(); });
        });
        watch(rosterScope, function () {
          if (!panelAutosaveReady.value) return;
          panelUserEdited.value = true;
          schedulePersistWidget(0);
        });
        watch(widgetForm, function () {
          if (!panelAutosaveReady.value) return;
          panelUserEdited.value = true;
          schedulePersistWidget(420);
        }, { deep: true });
        watch(function () { return [widgetForm.value.widget_type, widgetForm.value.config && widgetForm.value.config.group_by]; }, function () {
          if (isDateGroup.value && !(widgetForm.value.config && widgetForm.value.config.date_group)) {
            widgetForm.value.config.date_group = "month";
          }
        });

        onMounted(function () {
          fetch("/api/me", {
            headers: window.crmAuthHeader ? window.crmAuthHeader() : {},
            credentials: "same-origin",
          }).then(function (r) { return r.json(); }).then(function (me) {
            var perms = me.permissions || [];
            canWrite.value = !!me.is_super || perms.indexOf("dashboard.write") >= 0;
          }).catch(function () {
            canWrite.value = false;
          });

          apiGet("/api/rms/dashboard-metadata").then(function (m) {
            metadata.value = Object.assign({
              sources: [],
              widget_types: [],
              metrics: [],
              date_groups: [],
              colors: [],
              sorts: [],
              rms_blocks: [],
            }, m || {});
          }).catch(function () {
            metadata.value = {
              sources: [],
              widget_types: ["number", "bar", "horizontal_bar", "pie", "line", "roster_summary", "rms_block", "rich_text"],
              metrics: [],
              date_groups: [],
              colors: [],
              sorts: [],
              rms_blocks: [],
            };
          });

          apiGet("/api/rms/dashboard/roster-clients").then(function (res) {
            rosterClients.value = res && Array.isArray(res.clients) ? res.clients : [];
          }).catch(function () {
            rosterClients.value = [];
          });

          loadBoards().then(function () {
            reloadActiveTabData();
          });
          loadFilterOptions();
        });

        return {
          loading,
          rosterLoading,
          error,
          data,
          rosterCheck,
          filters,
          dashboards,
          metadata,
          widgetData,
          rosterClients,
          rosterScope,
          colorPickerOpen,
          colorSearch,
          activeDashboardId,
          activeTabId,
          activeDashboard,
          activeTab,
          displayItems,
          editMode,
          canWrite,
          showDashboardModal,
          showTabModal,
          panelOpen,
          widgetForm,
          dashboardForm,
          tabForm,
          clientOptions,
          jobOptions,
          userOptions,
          clientFieldLabel,
          jobFieldLabel,
          salesFieldLabel,
          deliveryFieldLabel,
          recruiterFieldLabel,
          historicalStages,
          activeFilterSummary,
          tabNeedsDashboardData,
          chartCanvasId,
          cardCanvasId,
          widgetBlock,
          cardStyle,
          blockLabel,
          typeLabel,
          typeIcon,
          sourceLabel,
          metricLabel,
          themeColor,
          legendOf,
          showLegend,
          rosterTiles,
          rosterScopeLabel,
          rosterHeadcount,
          isRosterClientCard,
          extraRenderLabel,
          openDisplayItemPanel,
          selectDashboard,
          selectTab,
          loadDashboard,
          loadRosterCheck,
          loadWidgetData,
          reloadActiveTabData,
          goRosterTab,
          openDashboardModal,
          saveDashboard,
          deleteActiveDashboard,
          openTabModal,
          saveTab,
          blankWidget,
          buildConfig,
          openWidgetPanel,
          closePanel,
          selectWidgetType,
          addFilter,
          removeFilter,
          addExtraView,
          removeExtraView,
          flushPersistWidget,
          deleteWidget,
          duplicateWidget,
          changeRosterClient,
          formatRmsDate,
          richTitle,
          richBody,
          needsDataSource,
          needsField,
          needsGroupBy,
          isChart,
          isRosterSummary,
          isRmsBlock,
          sourceFields,
          numericFields,
          groupByFields,
          isDateGroup,
          filteredColorRows,
          selectedColorRowLabel,
          isColorSwatchActive,
          pickColor,
          closeColorPicker,
          widgetPalette: KIT.widgetPalette,
          selectedShade: KIT.selectedShade,
        };
      },
    }).mount("#" + MOUNT_ID);
  } catch (mountErr) {
    console.error("[rms-dashboard] mount failed:", mountErr);
    showMountError(mountErr && mountErr.message ? mountErr.message : String(mountErr));
  }
})();
