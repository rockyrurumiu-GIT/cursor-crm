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
    chart_client_job_stage_grouped: true,
    chart_client_job_stage_stacked: true,
    chart_client_job_stage_funnel: true,
  };

  var JOB_STAGE_CHART_COLORS = {
    pushed: "#7B96B8",
    internal: "#88A992",
    client: "#D6A461",
    interviewed: "#9389AE",
    passed: "#5B8A72",
    pendingClient: "#B4C4D8",
    pendingInterview: "#C2D4C8",
    abandoned: "#CD9180",
  };

  function truncateJobLabel(title, maxLen) {
    var t = String(title || "").trim() || "—";
    maxLen = maxLen || 10;
    return t.length > maxLen ? t.slice(0, maxLen) + "…" : t;
  }

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
  var skipWidgetWatchPersist = 0;
  var chartRenderBatchTimer = null;
  var widgetRefreshTimers = {};

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
        var panelView = ref("main");
        var activePicker = ref(null);
        var manualOrderItems = ref([]);
        var manualOrderLoading = ref(false);
        var manualDragIndex = ref(null);
        var manualDragOverIndex = ref(null);
        var manualDragGhostLabel = ref("");
        var manualDragGhostPillStyle = ref({});
        var manualDragRowHeight = ref(36);
        var manualDragGhostPos = reactive({ x: 0, y: 0 });
        var manualDragState = null;
        var chatbotWasVisible = ref(false);
        var dragWidgetId = ref(null);
        var resizeWidgetId = ref(null);
        var activeWidgetId = ref(null);
        var dragState = null;
        var resizeState = null;
        var widgetForm = ref(blankWidget());

        var clientOptions = ref([]);
        var jobOptions = ref([]);
        var userOptions = ref([]);

        var filters = reactive({
          client_id: "",
          job_ids: [],
          job_ids_text: "",
          priority: "",
          city: "",
          sales_user_id: "",
          delivery_user_id: "",
          recruiter_user_id: "",
          date_from: "",
          date_to: "",
        });

        function blankWidget() {
          var w = KIT.blankWidget({ widget_type: "bar" });
          w.config = KIT.normalizeWidgetConfig(w.config || {});
          if (!w.config.block) w.config.block = "kpi_jobs";
          if (!Array.isArray(w.config.filters)) w.config.filters = [];
          if (!Array.isArray(w.config.extra_views)) w.config.extra_views = [];
          if (!w.source_key) w.source_key = "rms_applications";
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

        var clientJobStageSummary = computed(function () {
          return (data.value && data.value.client_job_stage_summary) || null;
        });
        var clientJobStageRows = computed(function () {
          var summary = clientJobStageSummary.value;
          return summary && summary.rows ? summary.rows : [];
        });
        var clientJobStageTotal = computed(function () {
          var summary = clientJobStageSummary.value;
          return summary && summary.total ? summary.total : null;
        });
        var clientJobStagePeriodLabel = computed(function () {
          var summary = clientJobStageSummary.value;
          return (summary && summary.period_label) || "全量";
        });

        var activeFilterSummary = computed(function () {
          var labels = {
            client_id: "客户ID",
            job_ids: "岗位",
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
            if (k === "job_ids") {
              if (!Array.isArray(v) || !v.length) return;
              var names = v.map(function (id) {
                var job = jobOptions.value.find(function (j) { return String(j.id) === String(id); });
                return job ? (job.title || ("岗位#" + job.id)) : String(id);
              });
              out.push({ key: k, label: labels[k], value: names.join("、") });
              return;
            }
            if (v !== "" && v != null) out.push({ key: k, label: labels[k], value: String(v) });
          });
          if ((!filters.job_ids || !filters.job_ids.length) && filters.job_ids_text) {
            out.push({ key: "job_ids_text", label: "岗位", value: String(filters.job_ids_text) });
          }
          return out;
        });

        var clientFieldLabel = computed(function () { return clientOptions.value.length ? "客户" : "客户ID"; });
        var jobFieldLabel = computed(function () { return jobOptions.value.length ? "岗位" : "岗位ID"; });
        var salesFieldLabel = computed(function () { return userOptions.value.length ? "销售" : "销售用户ID"; });
        var deliveryFieldLabel = computed(function () { return userOptions.value.length ? "交付" : "交付用户ID"; });
        var recruiterFieldLabel = computed(function () { return userOptions.value.length ? "推荐人" : "推荐人用户ID"; });

        var RMS_DASHBOARD_API_BLOCKS = {
          filter: true,
          kpi_clients: true,
          kpi_jobs: true,
          kpi_hc: true,
          chart_pipeline: true,
          filter_summary: true,
          chart_history_pass: true,
          table_history: true,
          chart_recruiter: true,
          table_recruiter: true,
          table_client_job_stage: true,
          chart_client_job_stage_grouped: true,
          chart_client_job_stage_stacked: true,
          chart_client_job_stage_funnel: true,
        };

        var tabNeedsDashboardData = computed(function () {
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return false;
          return tab.widgets.some(function (w) {
            var b = widgetBlock(w);
            return !!(b && RMS_DASHBOARD_API_BLOCKS[b]);
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

        var isDataWidget = computed(function () {
          return KIT.DATA_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
        });
        var chartTypePills = computed(function () {
          return ["bar", "horizontal_bar", "line", "pie", "number", "rms_block"];
        });
        var supportsSecondary = computed(function () {
          return ["bar", "horizontal_bar", "line"].indexOf(widgetForm.value.widget_type) >= 0;
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
        var primaryAxisFields = computed(function () {
          return sourceFields.value.filter(function (f) {
            return f.role === "dimension" || f.role === "datetime" || f.kind === "text" || f.kind === "datetime";
          });
        });
        var secondaryAxisFields = computed(function () {
          return sourceFields.value.filter(function (f) {
            return f.role === "dimension" || f.kind === "text";
          });
        });
        var groupByFields = computed(function () {
          return primaryAxisFields.value;
        });
        var isDateGroup = computed(function () {
          var key = widgetForm.value.config && (widgetForm.value.config.primary_axis_field || widgetForm.value.config.group_by);
          var f = sourceFields.value.find(function (x) { return x.key === key; });
          return needsGroupBy.value && f && (f.kind === "datetime" || f.role === "datetime");
        });

        var PRIMARY_AXIS_SORT_ORDER = [
          "position_asc", "position_desc",
          "label_asc", "label_desc",
          "sum_asc", "sum_desc",
          "manual",
        ];
        var PRIMARY_SORT_LABELS = {
          position_asc: "位置升序", position_desc: "位置降序",
          label_asc: "字母升序", label_desc: "字母降序",
          sum_asc: "金额升序", sum_desc: "金额降序",
          manual: "手动",
        };
        var AXIS_NAME_LABELS = { none: "不显示", x: "X 轴", y: "Y 轴", both: "两者" };

        var pickerTitle = computed(function () {
          var titles = {
            source: "来源", primary_axis: "X 轴字段", secondary_axis: "分组依据",
            metric: "聚合方式", aggregate_field: "数值字段", date_group: "时间粒度",
            primary_sort: "X 轴排序", secondary_sort: "分组排序",
            axis_name_display: "轴名称",
          };
          return titles[activePicker.value] || "选择";
        });

        var pickerOptions = computed(function () {
          var kind = activePicker.value;
          var cfg = widgetForm.value.config || {};
          if (kind === "source") {
            return (metadata.value.sources || []).map(function (s) {
              return { key: s.key, label: s.label, active: widgetForm.value.source_key === s.key };
            });
          }
          if (kind === "primary_axis") {
            return primaryAxisFields.value.map(function (f) {
              return { key: f.key, label: f.label, active: cfg.primary_axis_field === f.key };
            });
          }
          if (kind === "secondary_axis") {
            var opts = [{ key: "", label: "无", active: !cfg.secondary_axis_field }];
            secondaryAxisFields.value.forEach(function (f) {
              opts.push({ key: f.key, label: f.label, active: cfg.secondary_axis_field === f.key });
            });
            return opts;
          }
          if (kind === "metric") {
            return (metadata.value.metrics || []).map(function (m) {
              return { key: m, label: metricLabel(m), active: cfg.metric === m };
            });
          }
          if (kind === "aggregate_field") {
            return numericFields.value.map(function (f) {
              return { key: f.key, label: f.label, active: cfg.aggregate_field === f.key };
            });
          }
          if (kind === "date_group") {
            return (metadata.value.date_groups || ["day", "week", "month", "year"]).map(function (g) {
              return { key: g, label: g, active: cfg.date_group === g };
            });
          }
          if (kind === "primary_sort") {
            var sorts = metadata.value.primary_axis_sorts || PRIMARY_AXIS_SORT_ORDER;
            return sorts.map(function (s) {
              return {
                key: s,
                label: PRIMARY_SORT_LABELS[s] || s,
                active: cfg.primary_axis_sort === s,
                hasSubview: s === "manual",
              };
            });
          }
          if (kind === "secondary_sort") {
            return (metadata.value.secondary_axis_sorts || ["label_asc", "label_desc"]).map(function (s) {
              return { key: s, label: s === "label_desc" ? "标签降序" : "标签升序", active: cfg.secondary_axis_sort === s };
            });
          }
          if (kind === "axis_name_display") {
            return (metadata.value.axis_name_displays || ["none", "x", "y", "both"]).map(function (v) {
              return { key: v, label: AXIS_NAME_LABELS[v] || v, active: cfg.axis_name_display === v };
            });
          }
          return [];
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

        function bringWidgetToFront(widgetId) {
          if (widgetId == null) return;
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return;
          var idx = -1;
          for (var i = 0; i < tab.widgets.length; i++) {
            if (tab.widgets[i].id === widgetId) { idx = i; break; }
          }
          if (idx < 0) return;
          var moved = tab.widgets.splice(idx, 1)[0];
          tab.widgets.push(moved);
          activeWidgetId.value = widgetId;
        }

        function cardStyle(w) {
          var x = Math.max(0, Math.min(11, w.x || 0));
          var ww = Math.max(1, Math.min(12, w.w || 4));
          var style = {
            gridColumn: (x + 1) + " / span " + ww,
            gridRow: ((w.y || 0) + 1) + " / span " + Math.max(1, w.h || 3),
          };
          if (editMode.value && w.id != null) {
            if (dragWidgetId.value === w.id || resizeWidgetId.value === w.id) {
              style.zIndex = 20;
            } else if (activeWidgetId.value === w.id) {
              style.zIndex = 10;
            }
          }
          return style;
        }

        function suggestNextLayout(tab) {
          var widgets = (tab && tab.widgets) || [];
          var maxBottom = 0;
          widgets.forEach(function (w) {
            var bottom = (Number(w.y) || 0) + (Number(w.h) || 3);
            if (bottom > maxBottom) maxBottom = bottom;
          });
          return { x: 0, y: maxBottom, w: 6, h: 5 };
        }

        function gridMetrics(grid) {
          var rect = grid.getBoundingClientRect();
          var gap = 12;
          var rowH = 52;
          var colW = (rect.width - gap * 11) / 12;
          return { rect: rect, gap: gap, rowH: rowH, colW: colW };
        }

        function pointerToGrid(grid, clientX, clientY, spanW) {
          var m = gridMetrics(grid);
          var cellW = m.colW + m.gap;
          var cellH = m.rowH + m.gap;
          var relX = clientX - m.rect.left;
          var relY = clientY - m.rect.top;
          var x = Math.floor(relX / cellW);
          var y = Math.floor(relY / cellH);
          x = Math.max(0, Math.min(11, x));
          x = Math.min(x, 12 - Math.max(1, spanW || 1));
          y = Math.max(0, y);
          return { x: x, y: y };
        }

        function findWidgetById(id) {
          var tab = activeTab.value;
          if (!tab || !tab.widgets || id == null) return null;
          for (var i = 0; i < tab.widgets.length; i++) {
            if (tab.widgets[i].id === id) return tab.widgets[i];
          }
          return null;
        }

        function onCardDragMove(evt) {
          if (!dragState || evt.pointerId !== dragState.pointerId) return;
          var widget = findWidgetById(dragState.widgetId);
          if (!widget) return;
          var pos = pointerToGrid(dragState.grid, evt.clientX, evt.clientY, dragState.w);
          widget.x = pos.x;
          widget.y = pos.y;
        }

        function onCardDragEnd(evt) {
          if (!dragState || evt.pointerId !== dragState.pointerId) return;
          document.removeEventListener("pointermove", onCardDragMove);
          document.removeEventListener("pointerup", onCardDragEnd);
          document.removeEventListener("pointercancel", onCardDragEnd);
          var widget = findWidgetById(dragState.widgetId);
          var wid = dragState.widgetId;
          dragState = null;
          dragWidgetId.value = null;
          if (!widget || wid == null) return;
          api("PUT", "/api/rms/dashboard-widgets/" + wid, {
            title: widget.title,
            widget_type: widget.widget_type,
            source_key: widget.source_key || "",
            config: widget.config,
            x: widget.x,
            y: widget.y,
            w: widget.w,
            h: widget.h,
          }).then(function () {
            return loadBoards();
          }).catch(function (e) {
            error.value = e.message || String(e);
          });
        }

        var RMS_BLOCK_LAYOUT_PRESETS = {
          filter: { w: 12, h: 2, title: "筛选" },
          kpi_clients: { w: 4, h: 3, title: "有需求客户数" },
          kpi_jobs: { w: 4, h: 3, title: "需求总数" },
          kpi_hc: { w: 4, h: 3, title: "HC 总数" },
          chart_pipeline: { w: 8, h: 6, title: "招聘管道（活动态）" },
          filter_summary: { w: 4, h: 6, title: "当前筛选" },
          chart_history_pass: { w: 12, h: 6, title: "阶段通过率" },
          table_history: { w: 12, h: 5, title: "阶段明细" },
          chart_recruiter: { w: 12, h: 6, title: "当月入职排名" },
          table_recruiter: { w: 12, h: 6, title: "人效明细" },
          table_client_job_stage: { w: 12, h: 7, title: "客户岗位阶段统计" },
          chart_client_job_stage_grouped: { w: 12, h: 7, title: "岗位阶段（分组柱）" },
          chart_client_job_stage_stacked: { w: 12, h: 7, title: "岗位阶段（堆叠柱）" },
          chart_client_job_stage_funnel: { w: 12, h: 6, title: "岗位阶段（漏斗）" },
        };

        function jobStageChartRows(limit) {
          var summary = data.value && data.value.client_job_stage_summary;
          var rows = summary && summary.rows ? summary.rows : [];
          return rows.slice(0, limit || 12);
        }

        function jobStageChartTotal() {
          var summary = data.value && data.value.client_job_stage_summary;
          return summary && summary.total ? summary.total : null;
        }

        function applyRmsBlockLayout(block) {
          var preset = RMS_BLOCK_LAYOUT_PRESETS[block];
          if (!preset || !widgetForm.value) return;
          widgetForm.value.w = preset.w;
          widgetForm.value.h = preset.h;
          if (preset.title) widgetForm.value.title = preset.title;
        }

        function onRmsBlockChange() {
          var block = widgetForm.value.config && widgetForm.value.config.block;
          if (!block) return;
          panelUserEdited.value = true;
          applyRmsBlockLayout(block);
          flushPersistWidget().then(function () {
            if (widgetForm.value.id) scrollToWidget(widgetForm.value.id);
          });
        }

        function scrollToWidget(widgetId) {
          if (widgetId == null) return;
          nextTick(function () {
            var el = document.querySelector('.dash-card[data-widget-id="' + widgetId + '"]');
            if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
          });
        }

        function persistWidgetLayout(widget) {
          if (!widget || widget.id == null) return Promise.resolve();
          return api("PUT", "/api/rms/dashboard-widgets/" + widget.id, {
            title: widget.title,
            widget_type: widget.widget_type,
            source_key: widget.source_key || "",
            config: widget.config,
            x: widget.x,
            y: widget.y,
            w: widget.w,
            h: widget.h,
          }).catch(function (e) {
            error.value = e.message || String(e);
          });
        }

        function onCardResizeMove(evt) {
          if (!resizeState || evt.pointerId !== resizeState.pointerId) return;
          var widget = findWidgetById(resizeState.widgetId);
          if (!widget) return;
          var m = gridMetrics(resizeState.grid);
          var dx = evt.clientX - resizeState.startClientX;
          var dy = evt.clientY - resizeState.startClientY;
          var dw = Math.round(dx / (m.colW + m.gap));
          var dh = Math.round(dy / (m.rowH + m.gap));
          widget.w = Math.max(2, Math.min(12, resizeState.startW + dw));
          widget.h = Math.max(2, resizeState.startH + dh);
        }

        function onCardResizeEnd(evt) {
          if (!resizeState || evt.pointerId !== resizeState.pointerId) return;
          document.removeEventListener("pointermove", onCardResizeMove);
          document.removeEventListener("pointerup", onCardResizeEnd);
          document.removeEventListener("pointercancel", onCardResizeEnd);
          var widget = findWidgetById(resizeState.widgetId);
          var wid = resizeState.widgetId;
          resizeState = null;
          resizeWidgetId.value = null;
          if (!widget || wid == null) return;
          persistWidgetLayout(widget).then(function () {
            return refreshWidgetChart(wid, { animate: false });
          });
        }

        function onCardResizePointerDown(item, evt) {
          if (!editMode.value || !canWrite.value || item.isExtra) return;
          if (evt.button !== 0) return;
          var w = item.widget;
          if (!w || w.id == null) return;
          bringWidgetToFront(w.id);
          var grid = evt.currentTarget.closest(".dash-grid");
          if (!grid) return;
          evt.preventDefault();
          evt.stopPropagation();
          resizeState = {
            widgetId: w.id,
            grid: grid,
            pointerId: evt.pointerId,
            startW: w.w || 6,
            startH: w.h || 3,
            startClientX: evt.clientX,
            startClientY: evt.clientY,
          };
          resizeWidgetId.value = w.id;
          document.addEventListener("pointermove", onCardResizeMove);
          document.addEventListener("pointerup", onCardResizeEnd);
          document.addEventListener("pointercancel", onCardResizeEnd);
        }

        function onCardHeadPointerDown(item, evt) {
          if (!editMode.value || !canWrite.value || item.isExtra) return;
          if (evt.button !== 0) return;
          if (evt.target.closest(".card-actions")) return;
          if (evt.target.closest(".card-resize-handle")) return;
          var w = item.widget;
          if (!w || w.id == null) return;
          bringWidgetToFront(w.id);
          var grid = evt.currentTarget.closest(".dash-grid");
          if (!grid) return;
          evt.preventDefault();
          dragState = {
            widgetId: w.id,
            w: w.w || 6,
            grid: grid,
            pointerId: evt.pointerId,
          };
          dragWidgetId.value = w.id;
          document.addEventListener("pointermove", onCardDragMove);
          document.addEventListener("pointerup", onCardDragEnd);
          document.addEventListener("pointercancel", onCardDragEnd);
        }

        function typeLabel(t) { return KIT.TYPE_LABELS[t] || t; }
        function typeIcon(t) { return KIT.TYPE_ICONS[t] || "▢"; }
        function sourceLabel(key) {
          var s = (metadata.value.sources || []).find(function (x) { return x.key === key; });
          return s ? s.label : "";
        }
        function metricLabel(m) { return KIT.METRIC_LABELS[m] || m; }
        function fieldLabel(key) {
          if (!key) return "";
          var f = sourceFields.value.find(function (x) { return x.key === key; });
          return f ? f.label : key;
        }
        function primarySortLabel(s) { return PRIMARY_SORT_LABELS[s] || s; }
        function secondarySortLabel(s) { return s === "label_desc" ? "标签降序" : "标签升序"; }
        function axisNameDisplayLabel(v) { return AXIS_NAME_LABELS[v] || v; }
        function widgetPalette(cfg) { return KIT.widgetPalette(cfg); }
        function selectedShade(cfg) { return KIT.selectedShade(cfg); }
        function extraRenderLabel(render) { return KIT.extraRenderLabel(render); }
        function themeColor(w) { return KIT.themeOf((w && w.config) || {}).base; }
        function showLegend(w) { return (w.config || {}).show_legend !== false; }
        function legendOf(w) {
          var d = widgetData.value[w.id];
          if (!d) return [];
          if (d.kind === "grouped_series") {
            var keys = d.keys || [];
            return keys.map(function (k, i) {
              return { label: k, value: "", color: KIT.shadeRamp(w.config || {}, keys.length)[i] };
            });
          }
          if (d.kind !== "series") return [];
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

        function stackedHorizontalOptions() {
          return {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: {
              legend: {
                display: true,
                position: "bottom",
                labels: { boxWidth: 10, padding: 8, font: { size: 10 }, color: "#6b7280" },
              },
              datalabels: { display: false },
              tooltip: whiteTooltip(function (c) {
                return c.dataset.label + ": " + String(c.parsed.x);
              }),
            },
            scales: {
              x: {
                stacked: true,
                beginAtZero: true,
                grid: { color: "#f2f3f5" },
                border: { display: false },
                ticks: { color: "#8f949b", font: { size: 10 }, precision: 0 },
              },
              y: {
                stacked: true,
                grid: { display: false },
                border: { display: false },
                ticks: { color: "#8f949b", font: { size: 10 } },
              },
            },
          };
        }

        function renderClientJobStageGroupedChart(canvasId) {
          if (!data.value) return;
          safeRenderChart(canvasId, function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            destroyChartKey(canvasId);
            var rows = jobStageChartRows(8);
            if (!rows.length) return;
            var labels = rows.map(function (r) { return truncateJobLabel(r.job_title, 8); });
            chartInstances[canvasId] = new Chart(canvas, {
              type: "bar",
              data: {
                labels: labels,
                datasets: [
                  { label: "推送", data: rows.map(function (r) { return r.pushed_resume_count || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.pushed, borderRadius: 4 },
                  { label: "内筛通过", data: rows.map(function (r) { return r.internal_screen_passed || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.internal, borderRadius: 4 },
                  { label: "客筛通过", data: rows.map(function (r) { return r.client_screen_passed || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.client, borderRadius: 4 },
                  { label: "面试通过", data: rows.map(function (r) { return r.interview_passed || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.passed, borderRadius: 4 },
                ],
              },
              options: groupedBarOptions(),
            });
          });
        }

        function renderClientJobStageStackedChart(canvasId) {
          if (!data.value) return;
          safeRenderChart(canvasId, function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            destroyChartKey(canvasId);
            var rows = jobStageChartRows(8);
            if (!rows.length) return;
            var labels = rows.map(function (r) { return truncateJobLabel(r.job_title, 10); });
            chartInstances[canvasId] = new Chart(canvas, {
              type: "bar",
              data: {
                labels: labels,
                datasets: [
                  { label: "待客户筛选", data: rows.map(function (r) { return r.pending_client_screen || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.pendingClient },
                  { label: "待面试", data: rows.map(function (r) { return r.pending_interview || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.pendingInterview },
                  { label: "面试通过", data: rows.map(function (r) { return r.interview_passed || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.passed },
                  { label: "放弃面试", data: rows.map(function (r) { return r.interview_abandoned || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.abandoned },
                ],
              },
              options: stackedHorizontalOptions(),
            });
          });
        }

        function renderClientJobStageFunnelChart(canvasId) {
          if (!data.value) return;
          safeRenderChart(canvasId, function () {
            var canvas = document.getElementById(canvasId);
            if (!canvas) return;
            destroyChartKey(canvasId);
            var total = jobStageChartTotal();
            if (!total) return;
            var stages = [
              { label: "推送简历", value: total.pushed_resume_count || 0, color: JOB_STAGE_CHART_COLORS.pushed },
              { label: "内筛通过", value: total.internal_screen_passed || 0, color: JOB_STAGE_CHART_COLORS.internal },
              { label: "客筛通过", value: total.client_screen_passed || 0, color: JOB_STAGE_CHART_COLORS.client },
              { label: "已面试", value: total.interviewed || 0, color: JOB_STAGE_CHART_COLORS.interviewed },
              { label: "面试通过", value: total.interview_passed || 0, color: JOB_STAGE_CHART_COLORS.passed },
            ];
            chartInstances[canvasId] = new Chart(canvas, {
              type: "bar",
              data: {
                labels: stages.map(function (s) { return s.label; }),
                datasets: [{
                  data: stages.map(function (s) { return s.value; }),
                  backgroundColor: stages.map(function (s) { return s.color; }),
                  borderRadius: 6,
                  barPercentage: 0.65,
                }],
              },
              options: horizontalBarOptions(""),
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

        function renderSingleWidget(w, opts) {
          opts = opts || {};
          if (!chartsAvailable() || !w) return;
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
          if (block === "chart_client_job_stage_grouped") {
            renderClientJobStageGroupedChart(rmsId);
            return;
          }
          if (block === "chart_client_job_stage_stacked") {
            renderClientJobStageStackedChart(rmsId);
            return;
          }
          if (block === "chart_client_job_stage_funnel") {
            renderClientJobStageFunnelChart(rmsId);
            return;
          }

          if (KIT.CHART_WIDGET_TYPES.indexOf(w.widget_type) >= 0) {
            var wd = widgetData.value[w.id];
            if (!wd) return;
            var animate = opts.animate !== false;
            KIT.renderCrmChart(chartInstances, destroyChartKey, w, wd, { viewIndex: null, animate: animate });
            var views = (w.config && w.config.extra_views) || [];
            views.forEach(function (ev, idx) {
              KIT.renderCrmChart(chartInstances, destroyChartKey, w, wd, {
                render: ev.render,
                viewIndex: idx,
                canvasId: KIT.chartCanvasId(w, idx),
                limit: ev.limit != null ? ev.limit : 6,
                animate: animate,
              });
            });
          }
        }

        function renderVisibleCharts(opts) {
          opts = opts || {};
          if (!chartsAvailable()) return;
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return;

          tab.widgets.forEach(function (w) {
            renderSingleWidget(w, opts);
          });
        }

        function scheduleChartRenderBatch() {
          if (chartRenderBatchTimer) clearTimeout(chartRenderBatchTimer);
          chartRenderBatchTimer = setTimeout(function () {
            chartRenderBatchTimer = null;
            nextTick(function () { renderVisibleCharts({ animate: false }); });
          }, 48);
        }

        function syncActiveWidgetFromForm(res) {
          var f = widgetForm.value;
          var tab = activeTab.value;
          if (!tab) return;
          if (!tab.widgets) tab.widgets = [];
          var payload = {
            id: f.id || (res && res.id),
            title: f.title,
            widget_type: f.widget_type,
            source_key: f.source_key || "",
            config: buildConfig(),
            x: f.x,
            y: f.y,
            w: f.w,
            h: f.h,
          };
          if (res && typeof res === "object") {
            Object.assign(payload, {
              id: res.id != null ? res.id : payload.id,
              title: res.title != null ? res.title : payload.title,
              widget_type: res.widget_type != null ? res.widget_type : payload.widget_type,
              source_key: res.source_key != null ? res.source_key : payload.source_key,
              config: res.config != null ? res.config : payload.config,
              x: res.x != null ? res.x : payload.x,
              y: res.y != null ? res.y : payload.y,
              w: res.w != null ? res.w : payload.w,
              h: res.h != null ? res.h : payload.h,
            });
          }
          var idx = tab.widgets.findIndex(function (x) { return x.id === payload.id; });
          if (idx >= 0) {
            Object.assign(tab.widgets[idx], payload);
          } else if (payload.id) {
            tab.widgets.push(payload);
          }
        }

        function suppressWidgetWatchPersist() {
          skipWidgetWatchPersist += 1;
          nextTick(function () {
            skipWidgetWatchPersist -= 1;
          });
        }

        function refreshWidgetChart(widgetId, opts) {
          opts = opts || {};
          var tab = activeTab.value;
          if (!tab || !tab.widgets || !widgetId) return Promise.resolve();
          var w = tab.widgets.find(function (x) { return x.id === widgetId; });
          if (!w) return Promise.resolve();

          if (widgetRefreshTimers[widgetId]) {
            clearTimeout(widgetRefreshTimers[widgetId]);
          }

          return new Promise(function (resolve) {
            widgetRefreshTimers[widgetId] = setTimeout(function () {
              delete widgetRefreshTimers[widgetId];
              var run = function () {
                if (widgetBlock(w)) {
                  return loadDashboard().then(function () {
                    return nextTick();
                  }).then(function () {
                    renderSingleWidget(w, { animate: opts.animate !== false });
                  });
                }
                if (KIT.CHART_WIDGET_TYPES.indexOf(w.widget_type) < 0) return Promise.resolve();
                return api("GET", "/api/rms/dashboard-widgets/" + widgetId + "/data")
                  .then(function (d) {
                    widgetData.value[widgetId] = d;
                    return nextTick();
                  })
                  .then(function () {
                    renderSingleWidget(w, { animate: opts.animate !== false });
                  });
              };
              run().then(resolve).catch(resolve);
            }, 32);
          });
        }

        function loadWidgetData(widgets) {
          if (!widgets || !widgets.length) return;
          widgets.forEach(function (w) {
            if (w.widget_type === "rms_block") return;
            api("GET", "/api/rms/dashboard-widgets/" + w.id + "/data")
              .then(function (d) {
                widgetData.value[w.id] = d;
                scheduleChartRenderBatch();
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
              renderVisibleCharts({ animate: false });
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
          suppressWidgetWatchPersist();
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
              if (isNew && res && res.id) {
                skipWidgetWatchPersist += 1;
                widgetForm.value.id = res.id;
                skipWidgetWatchPersist -= 1;
              }
              syncActiveWidgetFromForm(res);
              var wid = widgetForm.value.id;
              if (!wid) return nextTick();
              return nextTick().then(function () {
                scrollToWidget(wid);
                return refreshWidgetChart(wid, { animate: !isNew });
              }).then(function () {
                if (isNew && widgetBlock(widgetForm.value)) {
                  return loadDashboard();
                }
              });
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

        function syncChatbotForPanel(open) {
          var chatShell = document.getElementById("handbook-assistant");
          if (!chatShell) return;
          if (open) {
            chatbotWasVisible.value = !chatShell.classList.contains("hidden");
            if (window.crmHideHandbookAssistant) window.crmHideHandbookAssistant();
            return;
          }
          if (chatbotWasVisible.value) {
            chatShell.classList.remove("hidden");
            chatbotWasVisible.value = false;
          }
        }

        function openWidgetPanel(w) {
          panelView.value = "main";
          activePicker.value = null;
          if (w) {
            var mergedCfg = KIT.normalizeWidgetConfig(Object.assign({}, w.config || {}, {
              filters: (w.config && w.config.filters) ? w.config.filters.map(function (f) { return Object.assign({}, f); }) : [],
              extra_views: (w.config && w.config.extra_views) ? w.config.extra_views.map(function (ev) { return Object.assign({}, ev); }) : [],
            }));
            if (!mergedCfg.block) mergedCfg.block = "kpi_jobs";
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
            var next = suggestNextLayout(activeTab.value);
            widgetForm.value = blankWidget();
            widgetForm.value.widget_type = "rms_block";
            widgetForm.value.source_key = "";
            widgetForm.value.config.block = "table_client_job_stage";
            widgetForm.value.title = "客户岗位阶段统计";
            widgetForm.value.x = next.x;
            widgetForm.value.y = next.y;
            applyRmsBlockLayout("table_client_job_stage");
            rosterScope.value = "all";
          }
          colorSearch.value = "";
          colorPickerOpen.value = false;
          panelUserEdited.value = !!w;
          panelAutosaveReady.value = false;
          panelOpen.value = true;
          syncChatbotForPanel(true);
          nextTick(function () { panelAutosaveReady.value = true; });
        }
        function closePanel() {
          panelAutosaveReady.value = false;
          panelUserEdited.value = false;
          panelView.value = "main";
          activePicker.value = null;
          clearWidgetAutosaveTimer();
          panelOpen.value = false;
          colorPickerOpen.value = false;
          syncChatbotForPanel(false);
        }
        function openPicker(kind) {
          activePicker.value = kind;
          panelView.value = "picker";
        }
        function openPrimarySort() {
          if (widgetForm.value.config && widgetForm.value.config.primary_axis_sort === "manual") {
            openManualOrder();
            return;
          }
          openPicker("primary_sort");
        }
        function onPickerSelect(opt) {
          if (activePicker.value === "primary_sort" && opt.key === "manual") {
            openManualOrder();
            return;
          }
          applyPicker(opt.key);
        }
        var manualOrderEntrySeq = 0;
        function manualOrderEntry(label) {
          manualOrderEntrySeq += 1;
          return { id: "mo-" + manualOrderEntrySeq, label: String(label) };
        }
        function manualOrderLabelsFromEntries(entries) {
          return (entries || []).map(function (e) { return e.label; });
        }
        function manualOrderEntriesFromLabels(labels) {
          return (labels || []).map(function (label) { return manualOrderEntry(label); });
        }
        function mergeManualOrderLabels(saved, dataLabels) {
          var seen = {};
          var merged = [];
          (saved || []).forEach(function (label) {
            var s = String(label || "").trim();
            if (!s || seen[s]) return;
            seen[s] = true;
            merged.push(s);
          });
          (dataLabels || []).forEach(function (label) {
            var s = String(label || "").trim();
            if (!s || seen[s]) return;
            seen[s] = true;
            merged.push(s);
          });
          return merged;
        }
        function loadManualOrderItems() {
          manualOrderLoading.value = true;
          var cfg = widgetForm.value.config || {};
          var saved = Array.isArray(cfg.primary_axis_order) ? cfg.primary_axis_order.slice() : [];
          var dataLabels = [];
          var wid = widgetForm.value.id;
          if (wid) {
            var cached = widgetData.value[wid];
            if (cached && Array.isArray(cached.labels)) {
              dataLabels = cached.labels.slice();
            }
            return api("GET", "/api/rms/dashboard-widgets/" + wid + "/data")
              .then(function (data) {
                if (data && Array.isArray(data.labels)) dataLabels = data.labels.slice();
              })
              .catch(function () {})
              .finally(function () {
                var merged = mergeManualOrderLabels(saved, dataLabels);
                manualOrderItems.value = manualOrderEntriesFromLabels(merged);
                if (!widgetForm.value.config) widgetForm.value.config = {};
                widgetForm.value.config.primary_axis_order = merged.slice();
                manualOrderLoading.value = false;
              });
          }
          var merged = mergeManualOrderLabels(saved, dataLabels);
          manualOrderItems.value = manualOrderEntriesFromLabels(merged);
          if (!widgetForm.value.config) widgetForm.value.config = {};
          widgetForm.value.config.primary_axis_order = merged.slice();
          manualOrderLoading.value = false;
          return Promise.resolve();
        }
        function openManualOrder() {
          if (!widgetForm.value.config) widgetForm.value.config = {};
          widgetForm.value.config.primary_axis_sort = "manual";
          widgetForm.value.config.sort = "label_asc";
          activePicker.value = "primary_sort";
          panelView.value = "manual_order";
          loadManualOrderItems();
        }
        function backFromManualOrder() {
          resetManualDrag();
          activePicker.value = "primary_sort";
          panelView.value = "picker";
        }
        function manualOrderPillStyle(label) {
          return KIT.tagPillStyle(label);
        }
        function manualDragGhostStyle() {
          return {
            left: manualDragGhostPos.x + "px",
            top: manualDragGhostPos.y + "px",
          };
        }
        function manualOrderRowStyle(idx) {
          if (manualDragIndex.value == null) return {};
          var from = manualDragIndex.value;
          var to = manualDragOverIndex.value;
          var h = manualDragRowHeight.value || 36;
          if (idx === from) return {};
          var ty = 0;
          if (from < to && idx > from && idx <= to) ty = -h;
          else if (from > to && idx >= to && idx < from) ty = h;
          if (!ty) return {};
          return { transform: "translateY(" + ty + "px)" };
        }
        function resetManualDrag() {
          manualDragState = null;
          manualDragIndex.value = null;
          manualDragOverIndex.value = null;
          manualDragGhostLabel.value = "";
          manualDragGhostPillStyle.value = {};
        }
        function commitManualReorder(fromIdx, toIdx) {
          if (fromIdx === toIdx) return;
          var items = manualOrderItems.value.slice();
          var moved = items.splice(fromIdx, 1)[0];
          items.splice(toIdx, 0, moved);
          manualOrderItems.value = items;
          var labels = manualOrderLabelsFromEntries(items);
          if (!widgetForm.value.config) widgetForm.value.config = {};
          widgetForm.value.config.primary_axis_order = labels;
          widgetForm.value.config.primary_axis_sort = "manual";
          widgetForm.value.config.sort = "label_asc";
        }
        function manualDropIndex(clientY) {
          var list = document.querySelector(".manual-order-list");
          if (!list) return manualDragIndex.value != null ? manualDragIndex.value : 0;
          var rows = list.querySelectorAll(".manual-order-row");
          if (!rows.length) return 0;
          for (var i = 0; i < rows.length; i++) {
            var rect = rows[i].getBoundingClientRect();
            if (clientY < rect.top + rect.height / 2) return i;
          }
          return rows.length - 1;
        }
        function onManualPointerMove(evt) {
          if (!manualDragState || evt.pointerId !== manualDragState.pointerId) return;
          manualDragGhostPos.x = evt.clientX - manualDragState.offsetX;
          manualDragGhostPos.y = evt.clientY - manualDragState.offsetY;
          var toIdx = manualDropIndex(evt.clientY);
          if (toIdx !== manualDragOverIndex.value) manualDragOverIndex.value = toIdx;
        }
        function onManualPointerEnd(evt) {
          if (!manualDragState || evt.pointerId !== manualDragState.pointerId) return;
          document.removeEventListener("pointermove", onManualPointerMove);
          document.removeEventListener("pointerup", onManualPointerEnd);
          document.removeEventListener("pointercancel", onManualPointerEnd);
          var fromIdx = manualDragState.fromIdx;
          var toIdx = manualDragOverIndex.value != null ? manualDragOverIndex.value : fromIdx;
          commitManualReorder(fromIdx, toIdx);
          resetManualDrag();
          flushPersistWidget();
        }
        function onManualHandlePointerDown(idx, ev) {
          if (ev.button !== 0) return;
          ev.preventDefault();
          var row = ev.target.closest(".manual-order-row");
          if (!row) return;
          var pill = row.querySelector(".manual-order-pill");
          if (!pill) return;
          var rowRect = row.getBoundingClientRect();
          var pillRect = pill.getBoundingClientRect();
          var list = row.closest(".manual-order-list");
          var gap = 0;
          if (list) gap = parseFloat(getComputedStyle(list).rowGap || getComputedStyle(list).gap || "0") || 0;
          manualDragRowHeight.value = rowRect.height + gap;
          manualDragState = {
            fromIdx: idx,
            pointerId: ev.pointerId,
            offsetX: ev.clientX - pillRect.left,
            offsetY: ev.clientY - pillRect.top,
          };
          manualDragIndex.value = idx;
          manualDragOverIndex.value = idx;
          manualDragGhostLabel.value = manualOrderItems.value[idx].label || "";
          manualDragGhostPillStyle.value = manualOrderPillStyle(manualDragGhostLabel.value);
          manualDragGhostPos.x = pillRect.left;
          manualDragGhostPos.y = pillRect.top;
          document.addEventListener("pointermove", onManualPointerMove);
          document.addEventListener("pointerup", onManualPointerEnd);
          document.addEventListener("pointercancel", onManualPointerEnd);
          if (ev.target.setPointerCapture) {
            try { ev.target.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
          }
        }
        function applyPicker(key) {
          if (!widgetForm.value.config) widgetForm.value.config = {};
          var cfg = widgetForm.value.config;
          var kind = activePicker.value;
          if (kind === "source") {
            if (key !== widgetForm.value.source_key) {
              widgetForm.value.source_key = key;
              cfg.primary_axis_field = "";
              cfg.group_by = "";
              cfg.secondary_axis_field = "";
              cfg.date_group = "";
              cfg.filters = [];
            }
          } else if (kind === "primary_axis") {
            cfg.primary_axis_field = key;
            cfg.group_by = key;
            var f = sourceFields.value.find(function (x) { return x.key === key; });
            if (f && (f.kind === "datetime" || f.role === "datetime") && !cfg.date_group) {
              cfg.date_group = "month";
            } else if (!f || (f.kind !== "datetime" && f.role !== "datetime")) {
              cfg.date_group = "";
            }
          } else if (kind === "secondary_axis") {
            cfg.secondary_axis_field = key;
          } else if (kind === "metric") {
            cfg.metric = key;
          } else if (kind === "aggregate_field") {
            cfg.aggregate_field = key;
            cfg.field = key;
          } else if (kind === "date_group") {
            cfg.date_group = key;
          } else if (kind === "primary_sort") {
            cfg.primary_axis_sort = key;
            cfg.sort = KIT.normalizeWidgetConfig(cfg).sort;
          } else if (kind === "secondary_sort") {
            cfg.secondary_axis_sort = key;
          } else if (kind === "axis_name_display") {
            cfg.axis_name_display = key;
          }
          panelView.value = "main";
          activePicker.value = null;
          flushPersistWidget();
        }
        function toggleGroupMode(ev) {
          if (!widgetForm.value.config) widgetForm.value.config = {};
          widgetForm.value.config.group_mode = ev.target.checked ? "stacked" : "grouped";
          flushPersistWidget();
        }
        function selectWidgetType(t) {
          if (widgetForm.value.widget_type === t) return;
          panelUserEdited.value = true;
          widgetForm.value.widget_type = t;
          if (!widgetForm.value.config) widgetForm.value.config = {};
          if (t === "rms_block") {
            if (!widgetForm.value.config.block) {
              widgetForm.value.config.block = "table_client_job_stage";
            }
            applyRmsBlockLayout(widgetForm.value.config.block);
          }
          if (t === "roster_summary") {
            widgetForm.value.source_key = "roster_entries";
          }
          if (t === "pie" || t === "number") {
            widgetForm.value.config.secondary_axis_field = "";
            widgetForm.value.config.group_mode = "stacked";
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
              return refreshWidgetChart(w.id, { animate: true });
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
        watch(editMode, function (on) {
          if (!on) activeWidgetId.value = null;
          destroyAllCharts();
          nextTick(function () { renderVisibleCharts({ animate: false }); });
        });
        watch(rosterScope, function () {
          if (!panelAutosaveReady.value) return;
          panelUserEdited.value = true;
          schedulePersistWidget(0);
        });
        watch(widgetForm, function () {
          if (!panelAutosaveReady.value) return;
          if (skipWidgetWatchPersist > 0) return;
          panelUserEdited.value = true;
          schedulePersistWidget(420);
        }, { deep: true });
        watch(function () {
          return widgetForm.value.config && (widgetForm.value.config.primary_axis_field || widgetForm.value.config.group_by);
        }, function () {
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
          dragWidgetId,
          resizeWidgetId,
          activeWidgetId,
          onCardHeadPointerDown,
          onCardResizePointerDown,
          onRmsBlockChange,
          showDashboardModal,
          showTabModal,
          panelOpen,
          panelView,
          activePicker,
          manualOrderItems,
          manualOrderLoading,
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
          clientJobStageRows,
          clientJobStageTotal,
          clientJobStagePeriodLabel,
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
          isDataWidget,
          chartTypePills,
          supportsSecondary,
          needsField,
          needsGroupBy,
          isChart,
          isRosterSummary,
          isRmsBlock,
          sourceFields,
          numericFields,
          groupByFields,
          primaryAxisFields,
          isDateGroup,
          pickerTitle,
          pickerOptions,
          filteredColorRows,
          selectedColorRowLabel,
          isColorSwatchActive,
          pickColor,
          closeColorPicker,
          fieldLabel,
          primarySortLabel,
          secondarySortLabel,
          axisNameDisplayLabel,
          widgetPalette,
          selectedShade,
          openPicker,
          openPrimarySort,
          onPickerSelect,
          openManualOrder,
          backFromManualOrder,
          onManualHandlePointerDown,
          manualOrderPillStyle,
          manualOrderRowStyle,
          manualDragGhostStyle,
          manualDragIndex,
          manualDragGhostLabel,
          manualDragGhostPillStyle,
          applyPicker,
          toggleGroupMode,
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
