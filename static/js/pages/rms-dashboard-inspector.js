/**
 * RMS Dashboard widget inspector / right panel.
 * Style presets, picker UI, autosave, manual order. No Chart.js render, no loadDashboard impl.
 */
(function (global) {
  "use strict";

  var Core = global.CrmRmsDashboardCore || {};
  var KIT = global.DashboardWidgetKit;
  var RMS_CHART_BAR_RADIUS = Core.RMS_CHART_BAR_RADIUS || 8;

  var RMS_PRESET_STYLE_BLOCKS = {
    chart_pipeline: true,
    chart_pending_backlog: true,
    lifecycle_funnel: true,
    chart_lifecycle_pass_rate: true,
    chart_job_pending_backlog: true,
    chart_client_hired_ranking: true,
    chart_recruiter_recommend_vs_hired: true,
  };

  var RMS_PRESET_GROUPED_CHART_BLOCKS = {
    chart_recruiter_recommend_vs_hired: true,
  };

  var RMS_PRESET_CHART_TYPE_LABELS = {
    horizontal_bar: "横向排名",
    bar: "柱状",
    pie: "环形",
    line: "折线",
    featured_line: "重点折线",
    line_1: "折线1",
    featured_bar: "重点柱状",
  };

  var RMS_PRESET_CHART_TYPES = ["horizontal_bar", "bar", "pie", "line", "featured_line", "line_1", "featured_bar"];
  var RMS_PRESET_GROUPED_CHART_TYPES = ["horizontal_bar", "bar", "line"];

  var RMS_LEGACY_PALETTE_MAP = {
    green_3: { color: "green", color_shade: 2 },
    blue_3: { color: "blue", color_shade: 2 },
    orange_3: { color: "orange", color_shade: 2 },
    gray_3: { color: "gray", color_shade: 2 },
  };

  function isRmsPresetStyleBlock(block) {
    return !!RMS_PRESET_STYLE_BLOCKS[block];
  }

  function migrateLegacyPresetStyle(saved) {
    var out = Object.assign({}, saved || {});
    if (!out.color && out.palette && RMS_LEGACY_PALETTE_MAP[out.palette]) {
      out.color = RMS_LEGACY_PALETTE_MAP[out.palette].color;
      out.color_shade = RMS_LEGACY_PALETTE_MAP[out.palette].color_shade;
    }
    delete out.palette;
    return out;
  }

  function defaultRmsPresetStyle(block) {
    var style = {
      color: "green",
      color_shade: 2,
      sort: "value_desc",
      chart_type: "horizontal_bar",
      show_values: false,
      show_grid: true,
      bar_radius: RMS_CHART_BAR_RADIUS,
      max_items: 8,
      line1_value_mode: "sum",
      line1_range_label: "Last 12 months",
      line1_active_index: "middle",
      show_line1_range: true,
      show_line1_fullscreen: true,
      show_line1_grid: true,
      highlight_item: "latest",
    };
    if (block === "lifecycle_funnel") {
      style.sort = "original";
      style.max_items = 12;
      style.metric = "count";
    }
    if (block === "chart_lifecycle_pass_rate") {
      style.sort = "original";
      style.max_items = 12;
      style.chart_type = "line";
      style.metric = "pass_rate";
    }
    if (block === "chart_recruiter_recommend_vs_hired") {
      style.show_group_composition = true;
    }
    return style;
  }

  function isRmsPresetGroupedChartBlock(block) {
    return !!RMS_PRESET_GROUPED_CHART_BLOCKS[block];
  }

  function rmsPresetStyle(config, block) {
    var base = defaultRmsPresetStyle(block);
    var saved = (config && config.style && typeof config.style === "object") ? config.style : {};
    return Object.assign({}, base, migrateLegacyPresetStyle(saved));
  }

  function isRmsFeaturedLinePreset(widget) {
    if (!widget || widget.widget_type !== "rms_block") return false;
    var block = widget.config && widget.config.block;
    if (!isRmsPresetStyleBlock(block)) return false;
    return rmsPresetStyle(widget.config, block).chart_type === "featured_line";
  }

  function isRmsLine1Preset(widget) {
    if (!widget || widget.widget_type !== "rms_block") return false;
    var block = widget.config && widget.config.block;
    if (!isRmsPresetStyleBlock(block)) return false;
    return rmsPresetStyle(widget.config, block).chart_type === "line_1";
  }

  function isRmsFeaturedBarPreset(widget) {
    if (!widget || widget.widget_type !== "rms_block") return false;
    var block = widget.config && widget.config.block;
    if (!isRmsPresetStyleBlock(block)) return false;
    return rmsPresetStyle(widget.config, block).chart_type === "featured_bar";
  }

  function isRmsFeaturedChartPreset(widget) {
    return isRmsFeaturedLinePreset(widget) || isRmsLine1Preset(widget) || isRmsFeaturedBarPreset(widget);
  }

  function presetStyleColorCfg(style) {
    return {
      color: (style && style.color) || "green",
      color_shade: style && style.color_shade != null ? style.color_shade : 2,
    };
  }

  function paletteForStyle(style) {
    return KIT.widgetPalette(presetStyleColorCfg(style));
  }

  function presetBarColorsFromStyle(style, n) {
    return KIT.shadeRamp(presetStyleColorCfg(style), n);
  }

  function presetRowValue(row) {
    if (row && row.count != null) return Number(row.count) || 0;
    if (row && row.value != null) return Number(row.value) || 0;
    return 0;
  }

  function applyPresetStyleRows(rows, style) {
    var out = (rows || []).slice();
    if (style.sort === "value_asc") {
      out.sort(function (a, b) { return presetRowValue(a) - presetRowValue(b); });
    } else if (style.sort === "value_desc") {
      out.sort(function (a, b) { return presetRowValue(b) - presetRowValue(a); });
    }
    var max = Number(style.max_items || 0);
    if (max > 0) out = out.slice(0, max);
    return out;
  }

  function isLifecycleFunnelBlock(block) {
    return block === "lifecycle_funnel";
  }

  function isLifecyclePassRateBlock(block) {
    return block === "chart_lifecycle_pass_rate"
      || (block === "lifecycle_funnel");
  }

  function createDashboardInspector(deps) {
    var ref = deps.ref;
    var computed = deps.computed;
    var watch = deps.watch;
    var reactive = deps.reactive;
    var nextTick = deps.nextTick;
    var KIT = deps.KIT;
    var api = deps.api;
    var data = deps.data;
    var activeTab = deps.activeTab;
    var activeTabId = deps.activeTabId;
    var widgetData = deps.widgetData;
    var metadata = deps.metadata;
    var error = deps.error;
    var refreshWidgetChart = deps.refreshWidgetChart;
    var renderSingleWidget = deps.renderSingleWidget;
    var loadDashboard = deps.loadDashboard;
    var loadBoards = deps.loadBoards;
    var reloadActiveTabData = deps.reloadActiveTabData;
    var blankWidget = deps.blankWidget;
    var suggestNextLayout = deps.suggestNextLayout;
    var widgetBlock = deps.widgetBlock;
    var syncWidgetTitleDraftsFromTab = deps.syncWidgetTitleDraftsFromTab;

    var widgetAutosaveTimer = null;
    var widgetPersistInFlight = false;
    var widgetPersistQueued = false;
    var skipWidgetWatchPersist = 0;

    var panelOpen = ref(false);
    var panelAutosaveReady = ref(false);
    var panelUserEdited = ref(false);
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
    var widgetForm = ref(blankWidget());

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

    var isDataWidget = computed(function () {
      return KIT.DATA_WIDGET_TYPES.indexOf(widgetForm.value.widget_type) >= 0;
    });
    var chartTypePills = computed(function () {
      return ["bar", "horizontal_bar", "line", "pie", "featured_line", "line_1", "featured_bar", "number", "rms_block"];
    });
    var supportsSecondary = computed(function () {
      return ["bar", "horizontal_bar", "line", "featured_bar"].indexOf(widgetForm.value.widget_type) >= 0;
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

    var lifecycleFunnelMetric = computed(function () {
      var block = widgetForm.value.config && widgetForm.value.config.block;
      if (block === "chart_lifecycle_pass_rate") return "pass_rate";
      var style = widgetForm.value.config && widgetForm.value.config.style;
      return (style && style.metric) || "count";
    });

    var rmsPresetChartTypePills = computed(function () {
      var block = widgetForm.value.config && widgetForm.value.config.block;
      if (RMS_PRESET_GROUPED_CHART_BLOCKS[block]) return RMS_PRESET_GROUPED_CHART_TYPES.slice();
      return RMS_PRESET_CHART_TYPES.slice();
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
    var selectedPresetStyleColorLabel = computed(function () {
      var style = widgetForm.value.config && widgetForm.value.config.style;
      var row = KIT.colorRowOf(style && style.color);
      var si = KIT.selectedShade(presetStyleColorCfg(style || {}));
      return row.label + " · " + (si + 1);
    });

    function isColorSwatchActive(row, shadeIndex) {
      var cfg = widgetForm.value.config || {};
      return cfg.color === row.key && KIT.selectedShade(cfg) === shadeIndex;
    }
    function isPresetStyleColorSwatchActive(row, shadeIndex) {
      var style = widgetForm.value.config && widgetForm.value.config.style;
      var cfg = presetStyleColorCfg(style || {});
      return cfg.color === row.key && KIT.selectedShade(cfg) === shadeIndex;
    }
    function pickColor(key, shadeIndex) {
      if (!widgetForm.value.config) widgetForm.value.config = {};
      widgetForm.value.config.color = key;
      widgetForm.value.config.color_shade = shadeIndex;
      flushPersistWidget();
    }
    function pickPresetStyleColor(key, shadeIndex) {
      if (!widgetForm.value.config) widgetForm.value.config = {};
      if (!widgetForm.value.config.style) {
        widgetForm.value.config.style = defaultRmsPresetStyle(
          widgetForm.value.config.block || "chart_pipeline"
        );
      }
      widgetForm.value.config.style.color = key;
      widgetForm.value.config.style.color_shade = shadeIndex;
      panelUserEdited.value = true;
      flushPersistWidget();
    }
    function rmsPresetChartTypeLabel(chartType) {
      return RMS_PRESET_CHART_TYPE_LABELS[chartType] || chartType;
    }
    function selectPresetChartType(chartType) {
      if (!widgetForm.value.config) widgetForm.value.config = {};
      var block = widgetForm.value.config.block || "chart_pipeline";
      if (!widgetForm.value.config.style) {
        widgetForm.value.config.style = defaultRmsPresetStyle(block);
      }
      var allowed = RMS_PRESET_GROUPED_CHART_BLOCKS[block]
        ? RMS_PRESET_GROUPED_CHART_TYPES
        : RMS_PRESET_CHART_TYPES;
      if (allowed.indexOf(chartType) < 0) return;
      widgetForm.value.config.style.chart_type = chartType;
      if (chartType === "featured_line") {
        if (block === "chart_lifecycle_pass_rate") {
          widgetForm.value.config.style.sort = "original";
        }
        if (widgetForm.value.config.style.featured_value_mode === undefined
          || widgetForm.value.config.style.featured_value_mode === "") {
          widgetForm.value.config.style.featured_value_mode = "auto";
        }
        if (widgetForm.value.config.style.show_point_values === undefined) {
          widgetForm.value.config.style.show_point_values = false;
        }
      }
      if (chartType === "line_1") {
        var st = widgetForm.value.config.style;
        if (st.line1_value_mode === undefined || st.line1_value_mode === "") st.line1_value_mode = "sum";
        if (st.line1_range_label === undefined || st.line1_range_label === "") st.line1_range_label = "Last 12 months";
        if (st.line1_active_index === undefined || st.line1_active_index === "") st.line1_active_index = "middle";
        if (st.show_line1_range === undefined) st.show_line1_range = true;
        if (st.show_line1_fullscreen === undefined) st.show_line1_fullscreen = true;
        if (st.show_line1_grid === undefined) st.show_line1_grid = true;
      }
      if (chartType === "featured_bar") {
        if (block === "chart_lifecycle_pass_rate") {
          widgetForm.value.config.style.sort = "original";
        }
        if (widgetForm.value.config.style.average_label === undefined
          || widgetForm.value.config.style.average_label === "") {
          widgetForm.value.config.style.average_label = "Avg";
        }
        if (widgetForm.value.config.style.show_average_line === undefined) {
          widgetForm.value.config.style.show_average_line = true;
        }
        if (widgetForm.value.config.style.show_tooltip === undefined) {
          widgetForm.value.config.style.show_tooltip = true;
        }
        if (widgetForm.value.config.style.show_summary_legend === undefined) {
          widgetForm.value.config.style.show_summary_legend = true;
        }
        if (widgetForm.value.config.style.highlight_item === undefined
          || widgetForm.value.config.style.highlight_item === "") {
          widgetForm.value.config.style.highlight_item = "latest";
        }
        if (widgetForm.value.config.style.highlight_latest === undefined) {
          widgetForm.value.config.style.highlight_latest = true;
        }
      }
      panelUserEdited.value = true;
      syncWidgetFormToTab();
      var wid = widgetForm.value.id;
      if (wid != null) {
        refreshWidgetChart(wid, { animate: false });
      }
      flushPersistWidget();
    }
    function selectPresetMetric(metric) {
      if (!widgetForm.value.config) widgetForm.value.config = {};
      var block = widgetForm.value.config.block || "lifecycle_funnel";
      if (!isLifecycleFunnelBlock(block)) return;
      if (!widgetForm.value.config.style) {
        widgetForm.value.config.style = defaultRmsPresetStyle(block);
      }
      widgetForm.value.config.style.metric = metric === "pass_rate" ? "pass_rate" : "count";
      panelUserEdited.value = true;
      syncWidgetFormToTab();
      var wid = widgetForm.value.id;
      if (wid != null) {
        refreshWidgetChart(wid, { animate: false });
      }
      flushPersistWidget();
    }
    function closeColorPicker() {
      colorPickerOpen.value = false;
    }

    var RMS_BLOCK_LAYOUT_PRESETS = {
      filter: { w: 12, h: 1, title: "筛选" },
      kpi_clients: { w: 4, h: 3, title: "有需求客户数" },
      kpi_jobs: { w: 4, h: 3, title: "需求总数" },
      kpi_hc: { w: 4, h: 3, title: "HC 总数" },
      kpi_resume_count: { w: 4, h: 3, title: "简历数" },
      kpi_hired_count: { w: 4, h: 3, title: "入职数" },
      kpi_resume_to_hire_rate: { w: 4, h: 3, title: "百简历入职转化率" },
      chart_pipeline: { w: 8, h: 6, title: "招聘管道（活动态）" },
      chart_pending_backlog: { w: 4, h: 6, title: "待处理积压" },
      filter_summary: { w: 4, h: 6, title: "当前筛选" },
      lifecycle_funnel: { w: 12, h: 6, title: "招聘生命周期漏斗" },
      chart_lifecycle_pass_rate: { w: 12, h: 5, title: "五率通过率" },
      table_lifecycle_detail: { w: 12, h: 5, title: "生命周期明细" },
      chart_history_pass: { w: 12, h: 6, title: "阶段通过率" },
      table_history: { w: 12, h: 5, title: "阶段明细" },
      chart_recruiter: { w: 12, h: 6, title: "当月入职排名" },
      chart_recruiter_recommend_vs_hired: { w: 12, h: 6, title: "推荐量 vs 入职量" },
      table_recruiter: { w: 12, h: 6, title: "人效明细" },
      chart_job_pending_backlog: { w: 6, h: 6, title: "岗位待处理积压" },
      chart_client_hired_ranking: { w: 6, h: 6, title: "客户入职量排行" },
      table_client_job_stage: { w: 12, h: 7, title: "客户岗位阶段统计" },
      chart_client_job_stage_grouped: { w: 12, h: 7, title: "岗位阶段（分组柱）" },
      chart_client_job_stage_stacked: { w: 12, h: 7, title: "岗位阶段（堆叠柱）" },
      chart_client_job_stage_funnel: { w: 12, h: 6, title: "岗位阶段（漏斗）" },
    };

    function applyRmsBlockLayout(block) {
      var preset = RMS_BLOCK_LAYOUT_PRESETS[block];
      if (!preset || !widgetForm.value) return;
      widgetForm.value.w = preset.w;
      widgetForm.value.h = preset.h;
      if (preset.title) widgetForm.value.title = preset.title;
    }

    function scrollToWidget(widgetId) {
      if (widgetId == null) return;
      nextTick(function () {
        var el = document.querySelector('.dash-card[data-widget-id="' + widgetId + '"]');
        if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
    }

    function selectRmsBlock(block) {
      if (!block || !widgetForm.value) return;
      if (!widgetForm.value.config) widgetForm.value.config = {};
      widgetForm.value.config.block = block;
      if (isRmsPresetStyleBlock(block)) {
        widgetForm.value.config.style = rmsPresetStyle(widgetForm.value.config, block);
      } else if (widgetForm.value.config.style) {
        delete widgetForm.value.config.style;
      }
      panelUserEdited.value = true;
      applyRmsBlockLayout(block);
      flushPersistWidget().then(function () {
        if (widgetForm.value.id) scrollToWidget(widgetForm.value.id);
      });
    }

    function onRmsBlockChange() {
      var block = widgetForm.value.config && widgetForm.value.config.block;
      if (!block) return;
      selectRmsBlock(block);
    }

    function typeLabel(t) { return RMS_PRESET_CHART_TYPE_LABELS[t] || KIT.TYPE_LABELS[t] || t; }
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

    function clearWidgetAutosaveTimer() {
      if (widgetAutosaveTimer) {
        clearTimeout(widgetAutosaveTimer);
        widgetAutosaveTimer = null;
      }
    }
    function widgetFormCanPersist() {
      var f = widgetForm.value;
      if (!f) return false;
      if (f.widget_type === "rms_block") {
        return !!(f.config && f.config.block);
      }
      return true;
    }

    function canAutosaveWidget() {
      return panelAutosaveReady.value && panelOpen.value && activeTabId.value
        && (widgetForm.value.id || panelUserEdited.value)
        && widgetFormCanPersist();
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
    function syncWidgetFormToTab() {
      var f = widgetForm.value;
      if (!f || f.id == null) return;
      var tab = activeTab.value;
      if (!tab || !tab.widgets) return;
      for (var i = 0; i < tab.widgets.length; i++) {
        if (tab.widgets[i].id !== f.id) continue;
        tab.widgets[i].title = f.title;
        tab.widgets[i].widget_type = f.widget_type;
        tab.widgets[i].source_key = f.source_key || "";
        tab.widgets[i].config = buildConfig();
        tab.widgets[i].x = f.x;
        tab.widgets[i].y = f.y;
        tab.widgets[i].w = f.w;
        tab.widgets[i].h = f.h;
        break;
      }
    }

    function previewWidgetChartFromForm() {
      if (!widgetForm.value || !widgetForm.value.id) return;
      if (widgetForm.value.widget_type !== "line_1" && !isRmsLine1Preset(widgetForm.value)) return;
      syncWidgetFormToTab();
      var tab = activeTab.value;
      if (!tab || !tab.widgets) return;
      var w = tab.widgets.find(function (x) { return x.id === widgetForm.value.id; });
      var wd = widgetData.value[widgetForm.value.id];
      if (w && renderSingleWidget && (isRmsLine1Preset(w) || wd)) {
        renderSingleWidget(w, { animate: false });
        return;
      }
      if (refreshWidgetChart) refreshWidgetChart(widgetForm.value.id, { animate: false });
    }

    function buildConfig() {
      var f = widgetForm.value;
      if (f.widget_type === "rms_block") {
        var block = (f.config && f.config.block) || "kpi_jobs";
        var cfg = { block: block };
        if (isRmsPresetStyleBlock(block)) {
          cfg.style = rmsPresetStyle(f.config, block);
        }
        return cfg;
      }
      return KIT.buildConfig(
        f,
        rosterScope.value,
        function () { return isDateGroup.value; },
        function () { return isChart.value; }
      );
    }

    function flushPersistWidget(force) {
      clearWidgetAutosaveTimer();
      suppressWidgetWatchPersist();
      if (!force && !canAutosaveWidget()) return Promise.resolve();
      if (force && (!activeTabId.value || !widgetFormCanPersist())) return Promise.resolve();
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
        if (isRmsPresetStyleBlock(mergedCfg.block)) {
          mergedCfg.style = rmsPresetStyle(w.config || {}, mergedCfg.block);
        }
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
        widgetForm.value.config.block = "";
        widgetForm.value.title = "";
        widgetForm.value.x = next.x;
        widgetForm.value.y = next.y;
        rosterScope.value = "all";
      }
      colorSearch.value = "";
      colorPickerOpen.value = false;
      panelUserEdited.value = !!w;
      panelAutosaveReady.value = false;
      panelOpen.value = true;
      syncChatbotForPanel(true);
      nextTick(function () {
        panelAutosaveReady.value = true;
      });
    }
    function closePanel() {
      clearWidgetAutosaveTimer();
      var shouldFlush = panelAutosaveReady.value && panelUserEdited.value;
      if (shouldFlush) {
        syncWidgetFormToTab();
        flushPersistWidget(true);
      }
      panelAutosaveReady.value = false;
      panelUserEdited.value = false;
      panelView.value = "main";
      activePicker.value = null;
      panelOpen.value = false;
      colorPickerOpen.value = false;
      syncChatbotForPanel(false);
      if (typeof syncWidgetTitleDraftsFromTab === "function") syncWidgetTitleDraftsFromTab();
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
      syncWidgetFormToTab();
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
      if (t === "rms_block" && widgetForm.value.config.block) {
        applyRmsBlockLayout(widgetForm.value.config.block);
      }
      if (KIT.DATA_WIDGET_TYPES.indexOf(t) >= 0 && !widgetForm.value.source_key) {
        widgetForm.value.source_key = "rms_applications";
      }
      if (t === "roster_summary") {
        widgetForm.value.source_key = "roster_entries";
      }
      if (t === "pie" || t === "number" || t === "featured_line" || t === "line_1") {
        widgetForm.value.config.secondary_axis_field = "";
        widgetForm.value.config.group_mode = "stacked";
      }
      if (t === "line_1") {
        var lc = widgetForm.value.config;
        if (lc.line1_value_mode === undefined || lc.line1_value_mode === "") lc.line1_value_mode = "sum";
        if (lc.line1_x_axis_mode === undefined || lc.line1_x_axis_mode === "") lc.line1_x_axis_mode = "all";
        if (lc.line1_range_label === undefined || lc.line1_range_label === "") lc.line1_range_label = "Last 12 months";
        if (lc.line1_active_index === undefined || lc.line1_active_index === "") lc.line1_active_index = "middle";
        if (lc.show_line1_range === undefined) lc.show_line1_range = true;
        if (lc.show_line1_fullscreen === undefined) lc.show_line1_fullscreen = true;
        if (lc.show_line1_grid === undefined) lc.show_line1_grid = true;
        if (!widgetForm.value.title || widgetForm.value.title === "新组件") widgetForm.value.title = "统计趋势";
      }
      if (t === "featured_bar") {
        widgetForm.value.config.extra_views = [];
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

    return {
      widgetForm: widgetForm,
      openWidgetPanel: openWidgetPanel,
      closePanel: closePanel,
      flushPersistWidget: flushPersistWidget,
      deleteWidget: deleteWidget,
      selectRmsBlock: selectRmsBlock,
      onRmsBlockChange: onRmsBlockChange,
      selectPresetChartType: selectPresetChartType,
      selectPresetMetric: selectPresetMetric,
      isLifecycleFunnelBlock: isLifecycleFunnelBlock,
      lifecycleFunnelMetric: lifecycleFunnelMetric,
      rmsPresetChartTypeLabel: rmsPresetChartTypeLabel,
      defaultRmsPresetStyle: defaultRmsPresetStyle,
      rmsPresetStyle: rmsPresetStyle,
      applyPresetStyleRows: applyPresetStyleRows,
      paletteForStyle: paletteForStyle,
      presetBarColorsFromStyle: presetBarColorsFromStyle,
      presetStyleColorCfg: presetStyleColorCfg,
      presetRowValue: presetRowValue,
      isRmsPresetStyleBlock: isRmsPresetStyleBlock,
      isRmsPresetGroupedChartBlock: isRmsPresetGroupedChartBlock,
      panelOpen: panelOpen,
      panelView: panelView,
      activePicker: activePicker,
      rosterScope: rosterScope,
      colorPickerOpen: colorPickerOpen,
      colorSearch: colorSearch,
      manualOrderItems: manualOrderItems,
      manualOrderLoading: manualOrderLoading,
      buildConfig: buildConfig,
      selectWidgetType: selectWidgetType,
      addFilter: addFilter,
      removeFilter: removeFilter,
      addExtraView: addExtraView,
      removeExtraView: removeExtraView,
      needsDataSource: needsDataSource,
      isDataWidget: isDataWidget,
      chartTypePills: chartTypePills,
      supportsSecondary: supportsSecondary,
      needsField: needsField,
      needsGroupBy: needsGroupBy,
      isChart: isChart,
      isRosterSummary: isRosterSummary,
      isRmsBlock: isRmsBlock,
      rmsPresetChartTypePills: rmsPresetChartTypePills,
      sourceFields: sourceFields,
      numericFields: numericFields,
      groupByFields: groupByFields,
      primaryAxisFields: primaryAxisFields,
      isDateGroup: isDateGroup,
      pickerTitle: pickerTitle,
      pickerOptions: pickerOptions,
      filteredColorRows: filteredColorRows,
      selectedColorRowLabel: selectedColorRowLabel,
      selectedPresetStyleColorLabel: selectedPresetStyleColorLabel,
      isPresetStyleColorSwatchActive: isPresetStyleColorSwatchActive,
      pickPresetStyleColor: pickPresetStyleColor,
      isColorSwatchActive: isColorSwatchActive,
      pickColor: pickColor,
      closeColorPicker: closeColorPicker,
      typeLabel: typeLabel,
      typeIcon: typeIcon,
      sourceLabel: sourceLabel,
      metricLabel: metricLabel,
      fieldLabel: fieldLabel,
      primarySortLabel: primarySortLabel,
      secondarySortLabel: secondarySortLabel,
      axisNameDisplayLabel: axisNameDisplayLabel,
      widgetPalette: KIT.widgetPalette,
      selectedShade: KIT.selectedShade,
      openPicker: openPicker,
      openPrimarySort: openPrimarySort,
      onPickerSelect: onPickerSelect,
      openManualOrder: openManualOrder,
      backFromManualOrder: backFromManualOrder,
      onManualHandlePointerDown: onManualHandlePointerDown,
      manualOrderPillStyle: manualOrderPillStyle,
      manualOrderRowStyle: manualOrderRowStyle,
      manualDragGhostStyle: manualDragGhostStyle,
      manualDragIndex: manualDragIndex,
      manualDragGhostLabel: manualDragGhostLabel,
      manualDragGhostPillStyle: manualDragGhostPillStyle,
      applyPicker: applyPicker,
      toggleGroupMode: toggleGroupMode,
    };
  }

  global.CrmRmsDashboardInspector = {
    createDashboardInspector: createDashboardInspector,
    defaultRmsPresetStyle: defaultRmsPresetStyle,
    rmsPresetStyle: rmsPresetStyle,
    applyPresetStyleRows: applyPresetStyleRows,
    paletteForStyle: paletteForStyle,
    presetBarColorsFromStyle: presetBarColorsFromStyle,
    presetStyleColorCfg: presetStyleColorCfg,
    presetRowValue: presetRowValue,
    isRmsPresetStyleBlock: isRmsPresetStyleBlock,
    isRmsPresetGroupedChartBlock: isRmsPresetGroupedChartBlock,
    isRmsFeaturedLinePreset: isRmsFeaturedLinePreset,
    isRmsLine1Preset: isRmsLine1Preset,
    isRmsFeaturedBarPreset: isRmsFeaturedBarPreset,
    isRmsFeaturedChartPreset: isRmsFeaturedChartPreset,
    RMS_PRESET_CHART_TYPES: RMS_PRESET_CHART_TYPES,
  };
})(typeof window !== "undefined" ? window : globalThis);
