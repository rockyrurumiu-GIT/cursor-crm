/**
 * RMS recruitment dashboard — Twenty-style editable widget boards.
 * Uses shared DashboardWidgetKit for CRM-style widget config capabilities.
 */
(function (global) {
  "use strict";

  var Core = global.CrmRmsDashboardCore || {};
  var RmsCore = global.CrmRmsCore || {};
  var MOUNT_ID = "rms-dashboard-app";
  var KIT = window.DashboardWidgetKit;
  var CHART_BLOCKS = {
    chart_pipeline: true,
    chart_history_pass: true,
    chart_recruiter: true,
    chart_client_job_stage_grouped: true,
    chart_client_job_stage_stacked: true,
    chart_client_job_stage_funnel: true,
    chart_pending_backlog: true,
    lifecycle_funnel: true,
    chart_lifecycle_pass_rate: true,
    chart_job_pending_backlog: true,
    chart_client_hired_ranking: true,
    chart_recruiter_recommend_vs_hired: true,
    chart_pipeline_dialysis: true,
  };

  var JOB_STAGE_CHART_COLORS = Core.JOB_STAGE_CHART_COLORS || {};
  var RMS_CHART_GRID_COLOR = Core.RMS_CHART_GRID_COLOR || "rgba(208, 215, 222, 0.45)";
  var RMS_CHART_TICK_COLOR = Core.RMS_CHART_TICK_COLOR || "#8c959f";
  var RMS_CHART_LABEL_COLOR = Core.RMS_CHART_LABEL_COLOR || "#24292f";
  var RMS_CHART_BAR_RADIUS = Core.RMS_CHART_BAR_RADIUS || 8;
  var RMS_CHART_BAR_THICKNESS = Core.RMS_CHART_BAR_THICKNESS || 28;
  var truncateJobLabel = Core.truncateJobLabel;
  var formatRmsDate = Core.formatRmsDate;
  var api = Core.api;
  var apiGet = Core.apiGet;
  var apiGetOptional = Core.apiGetOptional;
  var cloneFilters = Core.cloneFilters;
  var buildQuery = Core.buildQuery;
  var widgetBlock = Core.widgetBlock;
  var chartCanvasId = Core.chartCanvasId;
  var featuredPresetMountId = Core.featuredPresetMountId;
  var featuredLineMountId = Core.featuredLineMountId;
  var line1MountId = Core.line1MountId;
  var line1PresetMountId = Core.line1PresetMountId;
  var featuredBarMountId = Core.featuredBarMountId;
  var chartsAvailable = Core.chartsAvailable;
  var destroyChartKey = Core.destroyChartKey;
  var destroyAllCharts = Core.destroyAllCharts;
  var whiteTooltip = Core.whiteTooltip;
  var safeRenderChart = Core.safeRenderChart;
  var rmsShadeRamp = Core.rmsShadeRamp;
  var parsePassRate = Core.parsePassRate;
  var horizontalBarOptions = Core.horizontalBarOptions;
  var groupedBarOptions = Core.groupedBarOptions;

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

  if (!Core.api || !Core.horizontalBarOptions) {
    showMountError("RMS Dashboard Core 未加载，请刷新后重试。");
    return;
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
  var onUnmounted = Vue.onUnmounted;
  var onUpdated = Vue.onUpdated;
  var nextTick = Vue.nextTick;

  var chartInstances = Core.getChartInstances ? Core.getChartInstances() : {};
  var chartRenderBatchTimer = null;
  var widgetRefreshTimers = {};

  KIT.installChartPlugins(typeof Chart !== "undefined" ? Chart : undefined, typeof ChartDataLabels !== "undefined" ? ChartDataLabels : undefined);

  function initJobStageLossHintPopovers(rootEl) {
    var root = rootEl || document.getElementById(MOUNT_ID);
    if (!root || root.getAttribute("data-rms-job-stage-hint-inited")) return;
    root.setAttribute("data-rms-job-stage-hint-inited", "1");

    var popup = null;
    var activeWrap = null;

    function ensurePopup() {
      if (popup) return popup;
      popup = document.createElement("div");
      popup.className = "rms-job-stage-hint-popup";
      popup.setAttribute("role", "tooltip");
      popup.hidden = true;
      document.body.appendChild(popup);
      return popup;
    }

    function hidePopup() {
      activeWrap = null;
      if (!popup) return;
      popup.hidden = true;
    }

    function positionPopup(wrap) {
      var text = String(wrap.getAttribute("data-hint") || "").trim();
      if (!text) {
        hidePopup();
        return;
      }
      var box = ensurePopup();
      box.textContent = text;
      box.hidden = false;
      var rect = wrap.getBoundingClientRect();
      var gap = 6;
      box.style.left = "0px";
      box.style.top = "0px";
      var boxRect = box.getBoundingClientRect();
      var left = rect.left + rect.width / 2 - boxRect.width / 2;
      var top = rect.bottom + gap;
      var pad = 8;
      if (left < pad) left = pad;
      if (left + boxRect.width > window.innerWidth - pad) {
        left = Math.max(pad, window.innerWidth - pad - boxRect.width);
      }
      if (top + boxRect.height > window.innerHeight - pad) {
        top = rect.top - gap - boxRect.height;
      }
      box.style.left = left + "px";
      box.style.top = top + "px";
    }

    function showForWrap(wrap) {
      if (!wrap) return;
      activeWrap = wrap;
      positionPopup(wrap);
    }

    root.addEventListener("mouseover", function (e) {
      var wrap = e.target.closest && e.target.closest(".rms-job-stage-hint-wrap");
      if (wrap && root.contains(wrap)) showForWrap(wrap);
    });
    root.addEventListener("mouseout", function (e) {
      var wrap = e.target.closest && e.target.closest(".rms-job-stage-hint-wrap");
      if (!wrap) return;
      var rel = e.relatedTarget;
      if (rel && wrap.contains(rel)) return;
      hidePopup();
    });
    root.addEventListener("focusin", function (e) {
      var wrap = e.target.closest && e.target.closest(".rms-job-stage-hint-wrap");
      if (wrap && root.contains(wrap)) showForWrap(wrap);
    });
    root.addEventListener("focusout", function (e) {
      var wrap = e.target.closest && e.target.closest(".rms-job-stage-hint-wrap");
      if (!wrap) return;
      var rel = e.relatedTarget;
      if (rel && wrap.contains(rel)) return;
      hidePopup();
    });
    root.addEventListener("scroll", function () {
      if (activeWrap) positionPopup(activeWrap);
      else hidePopup();
    }, true);
    window.addEventListener("resize", hidePopup);
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
        var initialized = ref(false);
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
        var canDelete = ref(false);
        var editMode = ref(false);

        var activeDashboardId = ref(null);
        var activeTabId = ref(null);

        var showDashboardModal = ref(false);
        var showTabModal = ref(false);
        var dashboardForm = ref({ id: null, name: "", description: "" });
        var tabForm = ref({ name: "", rms_template: "overview" });
        var tabNameDrafts = ref({});
        var widgetTitleDrafts = ref({});

        var dragWidgetId = ref(null);
        var resizeWidgetId = ref(null);
        var activeWidgetId = ref(null);
        var dragState = null;
        var resizeState = null;

        var clientOptions = ref([]);
        var jobOptions = ref([]);
        var deliveryUserOptions = ref([]);
        var recruiterUserOptions = ref([]);
        var jobFilterDropdownOpen = ref(false);
        var jobFilterRef = ref(null);
        var jobIdsDraft = ref([]);
        var filterPanelExpanded = ref(false);

        var filters = reactive(cloneFilters());
        var appliedFilters = reactive(cloneFilters());

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

        var dragLayerItems = computed(function () {
          return displayItems.value.filter(function (item) { return !item.isExtra; });
        });

        var editableWidgets = computed(function () {
          var tab = activeTab.value;
          return (tab && tab.widgets) ? tab.widgets.slice() : [];
        });

        if (!global.CrmRmsDashboardMetrics || typeof global.CrmRmsDashboardMetrics.createDashboardMetrics !== "function") {
          showMountError("RMS Dashboard Metrics 未加载，请刷新后重试。");
          return {};
        }

        var metrics = global.CrmRmsDashboardMetrics.createDashboardMetrics({
          computed: computed,
          data: data,
          appliedFilters: appliedFilters,
          jobOptions: jobOptions,
          truncateJobLabel: truncateJobLabel,
        });

        var historicalStages = metrics.historicalStages;
        var clientJobStageSummary = metrics.clientJobStageSummary;
        var clientJobStageRows = metrics.clientJobStageRows;
        var clientJobStageTotal = metrics.clientJobStageTotal;
        var clientJobStagePeriodLabel = metrics.clientJobStagePeriodLabel;
        var lifecycleFunnel = metrics.lifecycleFunnel;
        var lifecycleRows = metrics.lifecycleRows;
        var resumeCount = metrics.resumeCount;
        var hiredCount = metrics.hiredCount;
        var resumeToHireRate = metrics.resumeToHireRate;
        var pendingBacklogRows = metrics.pendingBacklogRows;
        var jobPendingBacklogRows = metrics.jobPendingBacklogRows;
        var clientHiredRankingRows = metrics.clientHiredRankingRows;
        var recruiterRecommendVsHiredRows = metrics.recruiterRecommendVsHiredRows;
        var pipelineDialysisGrouped = metrics.pipelineDialysisGrouped;
        var pipelineDialysisHasData = metrics.pipelineDialysisHasData;
        var jobStageMetricText = metrics.jobStageMetricText;
        var jobStageMetricTitle = metrics.jobStageMetricTitle;
        var jobStageLossMetricCount = metrics.jobStageLossMetricCount;
        var jobStageLossNamesHint = metrics.jobStageLossNamesHint;
        var activeFilterSummary = metrics.activeFilterSummary;

        var clientJobStageListPageSize = (RmsCore.RMS_LIST_PAGE_SIZE || 8) + 2;
        var clientJobStagePagination = RmsCore.createListPagination
          ? RmsCore.createListPagination({
              ref: ref,
              computed: computed,
              watch: watch,
              filteredRows: clientJobStageRows,
              prefix: "clientJobStage",
              pageSize: clientJobStageListPageSize,
            })
          : {
              pagedRows: clientJobStageRows,
              clientJobStageCurrentPage: ref(1),
              clientJobStageTotalPages: computed(function () { return 1; }),
              clientJobStagePageNumbers: computed(function () { return [1]; }),
              clientJobStageGoPage: function () {},
              pageSize: clientJobStageListPageSize,
            };

        var filteredJobOptions = computed(function () {
          var jobs = jobOptions.value || [];
          var clientId = filters.client_id;
          if (clientId === "" || clientId == null) return jobs;
          var want = Number(clientId);
          if (!Number.isFinite(want)) return jobs;
          return jobs.filter(function (j) { return Number(j.client_id) === want; });
        });

        var cityOptions = computed(function () {
          var jobs = jobOptions.value || [];
          var seen = {};
          var out = [];
          jobs.forEach(function (j) {
            var loc = String(j.location || "").trim();
            if (!loc || seen[loc]) return;
            seen[loc] = true;
            out.push(loc);
          });
          out.sort(function (a, b) { return a.localeCompare(b, "zh-CN"); });
          return out;
        });

        var jobFilterSummary = computed(function () {
          var selected = jobFilterDropdownOpen.value
            ? jobIdsDraft.value
            : (Array.isArray(appliedFilters.job_ids) ? appliedFilters.job_ids : []);
          if (!selected.length) return "岗位";
          if (selected.length === 1) {
            var job = jobOptions.value.find(function (j) { return String(j.id) === String(selected[0]); });
            return job ? (job.title || ("岗位#" + job.id)) : String(selected[0]);
          }
          return "已选 " + selected.length + " 个岗位";
        });

        function toggleJobFilterDropdown() {
          if (!jobFilterDropdownOpen.value) {
            jobIdsDraft.value = (filters.job_ids || []).slice();
          }
          jobFilterDropdownOpen.value = !jobFilterDropdownOpen.value;
        }

        function toggleJobFilterDraft(jobId) {
          var list = jobIdsDraft.value;
          var id = String(jobId);
          var idx = list.indexOf(id);
          if (idx >= 0) {
            list.splice(idx, 1);
          } else {
            list.push(id);
          }
        }

        function clearJobFilterDraft() {
          jobIdsDraft.value = [];
        }

        function confirmJobFilter() {
          return applyFilters();
        }

        function jobFilterRootContains(target) {
          var root = jobFilterRef.value;
          if (!root || !target) return false;
          var nodes = Array.isArray(root) ? root : [root];
          return nodes.some(function (node) {
            var el = node && node.$el ? node.$el : node;
            return !!(el && typeof el.contains === "function" && el.contains(target));
          });
        }

        function applyFilterValues(target, src) {
          var next = cloneFilters(src);
          target.client_id = next.client_id;
          target.job_ids = next.job_ids.slice();
          target.job_ids_text = next.job_ids_text;
          target.delivery_user_id = next.delivery_user_id;
          target.recruiter_user_id = next.recruiter_user_id;
          target.city = next.city;
          target.date_from = next.date_from;
          target.date_to = next.date_to;
          target.include_zero_resume_jobs = !!next.include_zero_resume_jobs;
        }

        function syncDraftFromApplied() {
          applyFilterValues(filters, appliedFilters);
          jobIdsDraft.value = filters.job_ids.slice();
        }

        function syncAppliedFromDraft() {
          applyFilterValues(appliedFilters, filters);
        }

        function applyFilters() {
          filters.job_ids = jobIdsDraft.value.slice();
          jobFilterDropdownOpen.value = false;
          syncAppliedFromDraft();
          return Promise.all([loadDashboard(), reloadActiveTabData()]);
        }

        function cancelFilters() {
          jobFilterDropdownOpen.value = false;
          var empty = cloneFilters();
          applyFilterValues(filters, empty);
          applyFilterValues(appliedFilters, empty);
          jobIdsDraft.value = [];
          return Promise.all([loadDashboard(), reloadActiveTabData()]);
        }

        function rmsChartHasData(block) {
          if (!data.value) return false;
          if (block === "chart_pipeline") {
            return Array.isArray(data.value.pipeline_overview);
          }
          if (block === "chart_history_pass") {
            return historicalStages.value.length > 0;
          }
          if (block === "chart_recruiter") {
            return (data.value.recruiter_performance || []).length > 0;
          }
          if (block === "chart_client_job_stage_funnel") {
            return !!clientJobStageTotal.value;
          }
          if (
            block === "chart_client_job_stage_grouped"
            || block === "chart_client_job_stage_stacked"
          ) {
            return clientJobStageRows.value.length > 0;
          }
          if (block === "chart_pending_backlog") {
            return pendingBacklogRows.value.length > 0;
          }
          if (block === "lifecycle_funnel") {
            return lifecycleRows.value.length > 0;
          }
          if (block === "chart_lifecycle_pass_rate") {
            return lifecycleRows.value.some(function (r) {
              return r.pass_rate_value != null && r.key !== "resume";
            });
          }
          if (block === "chart_job_pending_backlog") {
            return jobPendingBacklogRows.value.length > 0;
          }
          if (block === "chart_client_hired_ranking") {
            return clientHiredRankingRows.value.length > 0;
          }
          if (block === "chart_recruiter_recommend_vs_hired") {
            return recruiterRecommendVsHiredRows.value.length > 0;
          }
          if (block === "chart_pipeline_dialysis") {
            return pipelineDialysisHasData("active") || pipelineDialysisHasData("loss");
          }
          return false;
        }

        var clientFieldLabel = computed(function () { return clientOptions.value.length ? "客户" : "客户ID"; });
        var jobFieldLabel = computed(function () { return filteredJobOptions.value.length ? "岗位" : "岗位ID"; });
        var deliveryFieldLabel = computed(function () { return deliveryUserOptions.value.length ? "交付" : "交付用户ID"; });
        var recruiterFieldLabel = computed(function () { return recruiterUserOptions.value.length ? "推荐人" : "推荐人用户ID"; });

        var RMS_DASHBOARD_API_BLOCKS = {
          filter: true,
          kpi_clients: true,
          kpi_jobs: true,
          kpi_hc: true,
          kpi_resume_count: true,
          kpi_hired_count: true,
          kpi_resume_to_hire_rate: true,
          chart_pipeline: true,
          filter_summary: true,
          chart_pending_backlog: true,
          lifecycle_funnel: true,
          chart_lifecycle_pass_rate: true,
          table_lifecycle_detail: true,
          chart_history_pass: true,
          table_history: true,
          chart_recruiter: true,
          chart_recruiter_recommend_vs_hired: true,
          chart_pipeline_dialysis: true,
          table_recruiter: true,
          chart_job_pending_backlog: true,
          chart_client_hired_ranking: true,
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

        function filterLayoutSavings(widgets, beforeY) {
          var savings = 0;
          if (!widgets || !widgets.length) return 0;
          widgets.forEach(function (widget) {
            if (widgetBlock(widget) !== "filter") return;
            var wy = Number(widget.y) || 0;
            var wh = Number(widget.h) || 3;
            if (wh > 1 && wy < beforeY) savings += wh - 1;
          });
          return savings;
        }

        function cardStyle(w) {
          var tab = activeTab.value;
          var widgets = (tab && tab.widgets) || [];
          var block = widgetBlock(w);
          var x = Math.max(0, Math.min(11, w.x || 0));
          var ww = Math.max(1, Math.min(12, w.w || 4));
          var y = Math.max(0, Number(w.y) || 0);
          var h = Math.max(1, w.h || 3);
          if (!editMode.value) {
            if (block === "filter") h = 1;
            else y = Math.max(0, y - filterLayoutSavings(widgets, y));
          }
          var style = {
            gridColumn: (x + 1) + " / span " + ww,
            gridRow: (y + 1) + " / span " + h,
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

        function pointerToGrid(grid, clientX, clientY, spanW, offsetX, offsetY) {
          var m = gridMetrics(grid);
          var cellW = m.colW + m.gap;
          var cellH = m.rowH + m.gap;
          var relX = clientX - (offsetX || 0) - m.rect.left;
          var relY = clientY - (offsetY || 0) - m.rect.top;
          var x = Math.floor(relX / cellW);
          var y = Math.floor(relY / cellH);
          x = Math.max(0, Math.min(11, x));
          x = Math.min(x, 12 - Math.max(1, spanW || 1));
          y = Math.max(0, y);
          return { x: x, y: y };
        }

        function dragPointerOffset(grid, widget, clientX, clientY) {
          var m = gridMetrics(grid);
          var cellW = m.colW + m.gap;
          var cellH = m.rowH + m.gap;
          return {
            offsetX: clientX - m.rect.left - (Number(widget.x) || 0) * cellW,
            offsetY: clientY - m.rect.top - (Number(widget.y) || 0) * cellH,
          };
        }

        function dragLayerStyle(item, index) {
          var w = item.widget;
          var style = cardStyle(w);
          var z = 100 + (index || 0);
          if (activeWidgetId.value === w.id) z += 500;
          if (dragWidgetId.value === w.id) z += 1000;
          style.zIndex = z;
          return style;
        }

        function scrollWidgetIntoView(widgetId) {
          if (widgetId == null) return;
          var el = document.querySelector('.dash-card[data-widget-id="' + widgetId + '"]');
          if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }

        function selectWidgetFromPicker(evt) {
          var raw = evt && evt.target ? evt.target.value : "";
          var id = raw === "" ? null : Number(raw);
          if (id == null || !Number.isFinite(id)) return;
          bringWidgetToFront(id);
          scrollWidgetIntoView(id);
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
          var pos = pointerToGrid(
            dragState.grid,
            evt.clientX,
            evt.clientY,
            dragState.w,
            dragState.offsetX,
            dragState.offsetY
          );
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

        function jobStageChartRows(limit) {
          var rows = clientJobStageRows.value || [];
          return rows.slice(0, limit || 12);
        }

        function jobStageChartTotal() {
          return clientJobStageTotal.value;
        }

        var Insp = global.CrmRmsDashboardInspector;
        if (!Insp || typeof Insp.createDashboardInspector !== "function") {
          showMountError("RMS Dashboard Inspector 未加载，请刷新后重试。");
          return {};
        }

        if (!global.CrmRmsDashboardCharts || typeof global.CrmRmsDashboardCharts.createDashboardCharts !== "function") {
          showMountError("RMS Dashboard Charts 未加载，请刷新后重试。");
          return {};
        }

        var charts = global.CrmRmsDashboardCharts.createDashboardCharts({
          Chart: global.Chart,
          KIT: KIT,
          chartInstances: chartInstances,
          destroyChartKey: destroyChartKey,
          safeRenderChart: safeRenderChart,
          chartsAvailable: chartsAvailable,
          chartCanvasId: chartCanvasId,
          widgetBlock: widgetBlock,
          whiteTooltip: whiteTooltip,
          horizontalBarOptions: horizontalBarOptions,
          groupedBarOptions: groupedBarOptions,
          rmsShadeRamp: rmsShadeRamp,
          parsePassRate: parsePassRate,
          truncateJobLabel: truncateJobLabel,
          featuredLineMountId: featuredLineMountId,
          featuredBarMountId: featuredBarMountId,
          RMS_CHART_GRID_COLOR: RMS_CHART_GRID_COLOR,
          RMS_CHART_TICK_COLOR: RMS_CHART_TICK_COLOR,
          RMS_CHART_BAR_RADIUS: RMS_CHART_BAR_RADIUS,
          JOB_STAGE_CHART_COLORS: JOB_STAGE_CHART_COLORS,
          RMS_PRESET_CHART_TYPES: Insp.RMS_PRESET_CHART_TYPES,
          rmsPresetStyle: Insp.rmsPresetStyle,
          applyPresetStyleRows: Insp.applyPresetStyleRows,
          paletteForStyle: Insp.paletteForStyle,
          presetBarColorsFromStyle: Insp.presetBarColorsFromStyle,
          presetStyleColorCfg: Insp.presetStyleColorCfg,
          presetRowValue: Insp.presetRowValue,
          data: data,
          widgetData: widgetData,
          activeTab: activeTab,
          historicalStages: historicalStages,
          lifecycleRows: lifecycleRows,
          pendingBacklogRows: pendingBacklogRows,
          jobPendingBacklogRows: jobPendingBacklogRows,
          clientHiredRankingRows: clientHiredRankingRows,
          recruiterRecommendVsHiredRows: recruiterRecommendVsHiredRows,
          pipelineDialysisGrouped: pipelineDialysisGrouped,
          jobStageChartRows: jobStageChartRows,
          jobStageChartTotal: jobStageChartTotal,
          nextTick: nextTick,
          isRmsFeaturedLinePreset: Insp.isRmsFeaturedLinePreset,
          isRmsLine1Preset: Insp.isRmsLine1Preset,
          isRmsFeaturedBarPreset: Insp.isRmsFeaturedBarPreset,
          line1MountId: line1MountId,
          appliedFilters: appliedFilters,
          line1PeriodLabel: Core.line1PeriodLabel,
        });
        var renderSingleWidget = charts.renderSingleWidget;
        var renderVisibleCharts = charts.renderVisibleCharts;
        var renderFeaturedPresetWidgets = charts.renderFeaturedPresetWidgets;
        var featuredPresetRerenderTimer = null;

        function scheduleFeaturedPresetRerender() {
          if (featuredPresetRerenderTimer) clearTimeout(featuredPresetRerenderTimer);
          featuredPresetRerenderTimer = setTimeout(function () {
            featuredPresetRerenderTimer = null;
            renderFeaturedPresetWidgets();
          }, 16);
        }

        function toggleIncludeZeroResumeJobs() {
          var next = !appliedFilters.include_zero_resume_jobs;
          filters.include_zero_resume_jobs = next;
          appliedFilters.include_zero_resume_jobs = next;
        }

        watch(function () { return appliedFilters.include_zero_resume_jobs; }, function () {
          nextTick(function () { renderVisibleCharts({ animate: false }); });
        });

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

        function onDragHandlePointerDown(item, evt) {
          if (!editMode.value || !canWrite.value || item.isExtra) return;
          if (evt.button !== 0) return;
          var w = item.widget;
          if (!w || w.id == null) return;
          bringWidgetToFront(w.id);
          var grid = document.querySelector(".dash-canvas-grid-wrap .dash-grid");
          if (!grid) return;
          evt.preventDefault();
          evt.stopPropagation();
          var offsets = dragPointerOffset(grid, w, evt.clientX, evt.clientY);
          dragState = {
            widgetId: w.id,
            w: w.w || 6,
            grid: grid,
            pointerId: evt.pointerId,
            offsetX: offsets.offsetX,
            offsetY: offsets.offsetY,
          };
          dragWidgetId.value = w.id;
          document.addEventListener("pointermove", onCardDragMove);
          document.addEventListener("pointerup", onCardDragEnd);
          document.addEventListener("pointercancel", onCardDragEnd);
        }

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
        function scheduleChartRenderBatch() {
          if (chartRenderBatchTimer) clearTimeout(chartRenderBatchTimer);
          chartRenderBatchTimer = setTimeout(function () {
            chartRenderBatchTimer = null;
            nextTick(function () { renderVisibleCharts({ animate: false }); });
          }, 48);
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
                return api("GET", "/api/rms/dashboard-widgets/" + widgetId + "/data" + buildQuery(appliedFilters))
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
          if (!widgets || !widgets.length) return Promise.resolve();
          var filterQs = buildQuery(appliedFilters);
          return Promise.all(widgets.map(function (w) {
            if (w.widget_type === "rms_block") return Promise.resolve();
            return api("GET", "/api/rms/dashboard-widgets/" + w.id + "/data" + filterQs)
              .then(function (d) {
                widgetData.value[w.id] = d;
                scheduleChartRenderBatch();
              })
              .catch(function () {
                widgetData.value[w.id] = { status: "error" };
              });
          }));
        }

        function reloadActiveTabData() {
          destroyAllCharts();
          widgetData.value = {};
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return Promise.resolve();
          var jobs = [];
          if (tabNeedsDashboardData.value) {
            jobs.push(loadDashboard());
          } else {
            data.value = null;
          }
          if (tabNeedsRosterData.value && !rosterCheck.value) {
            jobs.push(loadRosterCheck());
          }
          jobs.push(loadWidgetData(tab.widgets));
          return Promise.all(jobs);
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
          return apiGet("/api/rms/dashboard" + buildQuery(appliedFilters))
            .then(function (res) {
              data.value = res;
            })
            .catch(function (e) {
              error.value = e.message || String(e);
            })
            .finally(function () {
              loading.value = false;
            })
            .then(function () {
              return nextTick();
            })
            .then(function () {
              renderVisibleCharts({ animate: false });
            });
        }

        var inspector = Insp.createDashboardInspector({
          ref: ref,
          computed: computed,
          watch: watch,
          reactive: reactive,
          nextTick: nextTick,
          KIT: KIT,
          api: api,
          data: data,
          activeTab: activeTab,
          activeTabId: activeTabId,
          widgetData: widgetData,
          metadata: metadata,
          error: error,
          refreshWidgetChart: refreshWidgetChart,
          renderSingleWidget: renderSingleWidget,
          loadDashboard: loadDashboard,
          loadBoards: loadBoards,
          reloadActiveTabData: reloadActiveTabData,
          blankWidget: blankWidget,
          suggestNextLayout: suggestNextLayout,
          widgetBlock: widgetBlock,
          syncWidgetTitleDraftsFromTab: syncWidgetTitleDraftsFromTab,
        });

        function openDisplayItemPanel(item) {
          inspector.openWidgetPanel(item.widget);
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
          apiGetOptional("/api/rms/dashboard/filter-options").then(function (opts) {
            deliveryUserOptions.value = opts && Array.isArray(opts.delivery_users) ? opts.delivery_users : [];
            recruiterUserOptions.value = opts && Array.isArray(opts.recruiter_users) ? opts.recruiter_users : [];
          }).catch(function () {
            deliveryUserOptions.value = [];
            recruiterUserOptions.value = [];
          });
        }

        function loadRosterCheck() {
          rosterLoading.value = true;
          return apiGet(
            "/api/rms/applications/hired-roster-check" + buildQuery(appliedFilters)
          ).then(function (res) {
            rosterCheck.value = res;
          }).catch(function (e) {
            error.value = e.message || String(e);
          }).finally(function () {
            rosterLoading.value = false;
          });
        }

        function rosterConversionLabel(row) {
          if (!row) return "—";
          if (row.converted_to_roster_entry_id) return "已转入";
          if (row.roster_status === "matched") return "疑似已存在，未绑定";
          return "未转入";
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
        function syncTabNameDraftsFromDashboard() {
          var d = activeDashboard.value;
          var drafts = {};
          if (d && d.tabs) {
            d.tabs.forEach(function (t) { drafts[t.id] = t.name || ""; });
          }
          tabNameDrafts.value = drafts;
        }
        function bindTabLabelEl(tab) {
          return function (el) {
            if (!el) return;
            if (document.activeElement === el) return;
            var draft = tabNameDrafts.value[tab.id];
            el.textContent = draft != null ? draft : (tab.name || "");
          };
        }
        function onTabNameInput(tab, evt) {
          if (!tab || tab.id == null || !evt || !evt.target) return;
          tabNameDrafts.value[tab.id] = String(evt.target.textContent || "").replace(/\n/g, "");
        }
        function saveTabNameInline(tab, evt) {
          if (!tab || tab.id == null) return;
          if (evt && evt.target) {
            onTabNameInput(tab, evt);
          }
          var name = (tabNameDrafts.value[tab.id] != null ? String(tabNameDrafts.value[tab.id]) : "").trim();
          if (!name) {
            tabNameDrafts.value[tab.id] = tab.name || "";
            if (evt && evt.target) evt.target.textContent = tab.name || "";
            return;
          }
          if (name === (tab.name || "").trim()) return;
          api("PUT", "/api/rms/dashboard-tabs/" + tab.id, { name: name })
            .then(function () {
              tab.name = name;
            })
            .catch(function (e) {
              tabNameDrafts.value[tab.id] = tab.name || "";
              if (evt && evt.target) evt.target.textContent = tab.name || "";
              error.value = e.message || String(e);
            });
        }
        function flushTabNameDrafts() {
          var d = activeDashboard.value;
          if (!d || !d.tabs) return;
          d.tabs.forEach(function (t) { saveTabNameInline(t); });
        }
        function syncWidgetTitleDraftsFromTab() {
          var tab = activeTab.value;
          var drafts = {};
          if (tab && tab.widgets) {
            tab.widgets.forEach(function (w) { drafts[w.id] = w.title || ""; });
          }
          widgetTitleDrafts.value = drafts;
        }
        function syncWidgetTitleDraft(widget) {
          if (!widget || widget.id == null) return;
          widgetTitleDrafts.value[widget.id] = widget.title || "";
        }
        function saveWidgetTitleInline(widget) {
          if (!widget || widget.id == null) return;
          var draft = widgetTitleDrafts.value[widget.id];
          var title = (draft != null ? String(draft) : "").trim();
          if (!title) {
            widgetTitleDrafts.value[widget.id] = widget.title || "";
            return;
          }
          if (title === (widget.title || "").trim()) return;
          widget.title = title;
          persistWidgetLayout(widget).catch(function (e) {
            widgetTitleDrafts.value[widget.id] = widget.title || "";
            error.value = e.message || String(e);
          });
        }
        function flushWidgetTitleDrafts() {
          var tab = activeTab.value;
          if (!tab || !tab.widgets) return;
          tab.widgets.forEach(function (w) { saveWidgetTitleInline(w); });
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
            if (editMode.value) syncTabNameDraftsFromDashboard();
            return nextTick();
          }).then(function () {
            reloadActiveTabData();
          }).catch(function (e) {
            error.value = e.message || String(e);
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

        function lifecycleFunnelMetricFor(w) {
          var block = widgetBlock(w);
          if (block === "chart_lifecycle_pass_rate") return "pass_rate";
          var style = (w && w.config && w.config.style) || {};
          return style.metric || "count";
        }

        watch(activeTab, function () {
          reloadActiveTabData();
        });
        var chatbotWasVisibleBeforeEdit = ref(false);

        function syncChatbotForEditMode(on) {
          document.body.classList.toggle("rms-dashboard-edit-mode", !!on);
          var chatShell = document.getElementById("handbook-assistant");
          if (!chatShell) return;
          if (on) {
            chatbotWasVisibleBeforeEdit.value = !chatShell.classList.contains("hidden");
            if (window.crmHideHandbookAssistant) window.crmHideHandbookAssistant();
            return;
          }
          if (chatbotWasVisibleBeforeEdit.value) {
            chatShell.classList.remove("hidden");
            chatbotWasVisibleBeforeEdit.value = false;
          }
        }

        watch(editMode, function (on) {
          syncChatbotForEditMode(on);
          if (!on) {
            dragState = null;
            dragWidgetId.value = null;
            flushTabNameDrafts();
            activeWidgetId.value = null;
          } else if (canWrite.value) {
            syncTabNameDraftsFromDashboard();
          }
          destroyAllCharts();
          nextTick(function () { renderVisibleCharts({ animate: false }); });
        });

        watch(function () { return filters.client_id; }, function () {
          var prune = function (ids) {
            if (!Array.isArray(ids) || !ids.length) return [];
            var allowed = {};
            filteredJobOptions.value.forEach(function (j) { allowed[String(j.id)] = true; });
            return ids.filter(function (id) { return allowed[String(id)]; });
          };
          filters.job_ids = prune(filters.job_ids);
          jobIdsDraft.value = prune(jobIdsDraft.value);
        });

        onUpdated(function () {
          scheduleFeaturedPresetRerender();
        });

        onMounted(function () {
          var rootEl = document.getElementById(MOUNT_ID);
          initJobStageLossHintPopovers(rootEl);
          watch([initialized, loading], function () {
            if (rootEl) {
              rootEl.setAttribute("data-ready", (initialized.value && !loading.value) ? "1" : "0");
            }
          }, { immediate: true });

          document.addEventListener("click", function (evt) {
            if (!jobFilterDropdownOpen.value) return;
            if (!jobFilterRootContains(evt.target)) {
              jobFilterDropdownOpen.value = false;
            }
          });

          fetch("/api/me", {
            headers: window.crmAuthHeader ? window.crmAuthHeader() : {},
            credentials: "same-origin",
          }).then(function (r) { return r.json(); }).then(function (me) {
            var perms = me.permissions || [];
            canWrite.value = !!me.is_super || perms.indexOf("dashboard.write") >= 0;
            canDelete.value = !!me.is_super || perms.indexOf("dashboard.delete") >= 0;
          }).catch(function () {
            canWrite.value = false;
            canDelete.value = false;
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
              widget_types: ["number", "bar", "horizontal_bar", "pie", "line", "featured_line", "featured_bar", "roster_summary", "rms_block", "rich_text"],
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
            var maybe = reloadActiveTabData();
            if (maybe && typeof maybe.then === "function") {
              return maybe;
            }
            return null;
          }).finally(function () {
            initialized.value = true;
          });
          loadFilterOptions();
        });

        onUnmounted(function () {
          if (featuredPresetRerenderTimer) clearTimeout(featuredPresetRerenderTimer);
          syncChatbotForEditMode(false);
          document.body.classList.remove("rms-dashboard-edit-mode");
        });

        return Object.assign({
          loading: loading,
          initialized: initialized,
          rosterLoading: rosterLoading,
          error: error,
          data: data,
          rosterCheck: rosterCheck,
          filters: filters,
          appliedFilters: appliedFilters,
          applyFilters: applyFilters,
          cancelFilters: cancelFilters,
          toggleIncludeZeroResumeJobs: toggleIncludeZeroResumeJobs,
          dashboards: dashboards,
          metadata: metadata,
          widgetData: widgetData,
          rosterClients: rosterClients,
          activeDashboardId: activeDashboardId,
          activeTabId: activeTabId,
          activeDashboard: activeDashboard,
          activeTab: activeTab,
          displayItems: displayItems,
          dragLayerItems: dragLayerItems,
          editableWidgets: editableWidgets,
          editMode: editMode,
          canWrite: canWrite,
          canDelete: canDelete,
          dragWidgetId: dragWidgetId,
          resizeWidgetId: resizeWidgetId,
          activeWidgetId: activeWidgetId,
          dragLayerStyle: dragLayerStyle,
          onDragHandlePointerDown: onDragHandlePointerDown,
          selectWidgetFromPicker: selectWidgetFromPicker,
          onCardResizePointerDown: onCardResizePointerDown,
          showDashboardModal: showDashboardModal,
          showTabModal: showTabModal,
          dashboardForm: dashboardForm,
          tabForm: tabForm,
          tabNameDrafts: tabNameDrafts,
          widgetTitleDrafts: widgetTitleDrafts,
          clientOptions: clientOptions,
          jobOptions: jobOptions,
          filteredJobOptions: filteredJobOptions,
          cityOptions: cityOptions,
          deliveryUserOptions: deliveryUserOptions,
          recruiterUserOptions: recruiterUserOptions,
          jobFilterRef: jobFilterRef,
          jobFilterDropdownOpen: jobFilterDropdownOpen,
          jobIdsDraft: jobIdsDraft,
          filterPanelExpanded: filterPanelExpanded,
          jobFilterSummary: jobFilterSummary,
          toggleJobFilterDropdown: toggleJobFilterDropdown,
          toggleJobFilterDraft: toggleJobFilterDraft,
          clearJobFilterDraft: clearJobFilterDraft,
          confirmJobFilter: confirmJobFilter,
          rmsChartHasData: rmsChartHasData,
          clientFieldLabel: clientFieldLabel,
          jobFieldLabel: jobFieldLabel,
          deliveryFieldLabel: deliveryFieldLabel,
          recruiterFieldLabel: recruiterFieldLabel,
          historicalStages: historicalStages,
          lifecycleFunnel: lifecycleFunnel,
          lifecycleRows: lifecycleRows,
          resumeCount: resumeCount,
          hiredCount: hiredCount,
          resumeToHireRate: resumeToHireRate,
          clientJobStageRows: clientJobStageRows,
          clientJobStagePagedRows: clientJobStagePagination.pagedRows,
          clientJobStageCurrentPage: clientJobStagePagination.clientJobStageCurrentPage || clientJobStagePagination.currentPage,
          clientJobStageTotalPages: clientJobStagePagination.clientJobStageTotalPages || clientJobStagePagination.totalPages,
          clientJobStagePageNumbers: clientJobStagePagination.clientJobStagePageNumbers || clientJobStagePagination.pageNumbers,
          clientJobStageGoPage: clientJobStagePagination.clientJobStageGoPage || clientJobStagePagination.goPage,
          clientJobStagePageSize: clientJobStagePagination.pageSize,
          clientJobStageTotal: clientJobStageTotal,
          clientJobStagePeriodLabel: clientJobStagePeriodLabel,
          jobStageMetricText: jobStageMetricText,
          jobStageMetricTitle: jobStageMetricTitle,
          jobStageLossMetricCount: jobStageLossMetricCount,
          jobStageLossNamesHint: jobStageLossNamesHint,
          activeFilterSummary: activeFilterSummary,
          tabNeedsDashboardData: tabNeedsDashboardData,
          chartCanvasId: chartCanvasId,
          featuredPresetMountId: featuredPresetMountId,
          featuredLineMountId: featuredLineMountId,
          featuredBarMountId: featuredBarMountId,
          line1MountId: line1MountId,
          line1PresetMountId: line1PresetMountId,
          isRmsFeaturedLinePreset: Insp.isRmsFeaturedLinePreset,
          isRmsLine1Preset: Insp.isRmsLine1Preset,
          isRmsFeaturedBarPreset: Insp.isRmsFeaturedBarPreset,
          isRmsFeaturedChartPreset: Insp.isRmsFeaturedChartPreset,
          cardCanvasId: cardCanvasId,
          widgetBlock: widgetBlock,
          cardStyle: cardStyle,
          blockLabel: blockLabel,
          lifecycleFunnelMetricFor: lifecycleFunnelMetricFor,
          themeColor: themeColor,
          legendOf: legendOf,
          showLegend: showLegend,
          rosterTiles: rosterTiles,
          rosterScopeLabel: rosterScopeLabel,
          rosterHeadcount: rosterHeadcount,
          isRosterClientCard: isRosterClientCard,
          extraRenderLabel: extraRenderLabel,
          openDisplayItemPanel: openDisplayItemPanel,
          selectDashboard: selectDashboard,
          selectTab: selectTab,
          loadDashboard: loadDashboard,
          loadRosterCheck: loadRosterCheck,
          rosterConversionLabel: rosterConversionLabel,
          loadWidgetData: loadWidgetData,
          refreshWidgetChart: refreshWidgetChart,
          reloadActiveTabData: reloadActiveTabData,
          goRosterTab: goRosterTab,
          openDashboardModal: openDashboardModal,
          saveDashboard: saveDashboard,
          deleteActiveDashboard: deleteActiveDashboard,
          openTabModal: openTabModal,
          saveTabNameInline: saveTabNameInline,
          bindTabLabelEl: bindTabLabelEl,
          onTabNameInput: onTabNameInput,
          saveWidgetTitleInline: saveWidgetTitleInline,
          syncWidgetTitleDraft: syncWidgetTitleDraft,
          saveTab: saveTab,
          blankWidget: blankWidget,
          duplicateWidget: duplicateWidget,
          changeRosterClient: changeRosterClient,
          formatRmsDate: formatRmsDate,
          richTitle: richTitle,
          richBody: richBody,
        }, inspector);
      },
    }).mount("#" + MOUNT_ID);
  } catch (mountErr) {
    console.error("[rms-dashboard] mount failed:", mountErr);
    showMountError(mountErr && mountErr.message ? mountErr.message : String(mountErr));
  }
})(typeof window !== "undefined" ? window : globalThis);
