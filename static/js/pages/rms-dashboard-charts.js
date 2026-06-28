/**
 * RMS Dashboard Chart.js rendering.
 * Chart options + render functions only. No fetch, no widget CRUD, no style inspector.
 */
(function (global) {
  "use strict";

  function createDashboardCharts(deps) {
    var Chart = deps.Chart;
    var KIT = deps.KIT;
    var chartInstances = deps.chartInstances;
    var destroyChartKey = deps.destroyChartKey;
    var safeRenderChart = deps.safeRenderChart;
    var chartsAvailable = deps.chartsAvailable;
    var chartCanvasId = deps.chartCanvasId;
    var widgetBlock = deps.widgetBlock;
    var whiteTooltip = deps.whiteTooltip;
    var horizontalBarOptions = deps.horizontalBarOptions;
    var groupedBarOptions = deps.groupedBarOptions;
    var rmsShadeRamp = deps.rmsShadeRamp;
    var parsePassRate = deps.parsePassRate;
    var truncateJobLabel = deps.truncateJobLabel;
    var featuredLineMountId = deps.featuredLineMountId;
    var featuredBarMountId = deps.featuredBarMountId;
    var line1MountId = deps.line1MountId;

    var RMS_CHART_GRID_COLOR = deps.RMS_CHART_GRID_COLOR;
    var RMS_CHART_TICK_COLOR = deps.RMS_CHART_TICK_COLOR;
    var RMS_CHART_BAR_RADIUS = deps.RMS_CHART_BAR_RADIUS;
    var JOB_STAGE_CHART_COLORS = deps.JOB_STAGE_CHART_COLORS;
    var RMS_PRESET_CHART_TYPES = deps.RMS_PRESET_CHART_TYPES;

    var rmsPresetStyle = deps.rmsPresetStyle;
    var applyPresetStyleRows = deps.applyPresetStyleRows;
    var paletteForStyle = deps.paletteForStyle;
    var presetBarColorsFromStyle = deps.presetBarColorsFromStyle;
    var presetStyleColorCfg = deps.presetStyleColorCfg;
    var presetRowValue = deps.presetRowValue;

    var data = deps.data;
    var widgetData = deps.widgetData;
    var activeTab = deps.activeTab;
    var appliedFilters = deps.appliedFilters;
    var line1PeriodLabel = deps.line1PeriodLabel;

    var historicalStages = deps.historicalStages;
    var lifecycleRows = deps.lifecycleRows;
    var pendingBacklogRows = deps.pendingBacklogRows;
    var jobPendingBacklogRows = deps.jobPendingBacklogRows;
    var clientHiredRankingRows = deps.clientHiredRankingRows;
    var recruiterRecommendVsHiredRows = deps.recruiterRecommendVsHiredRows;

    var jobStageChartRows = deps.jobStageChartRows;
    var jobStageChartTotal = deps.jobStageChartTotal;
    var nextTick = deps.nextTick;
    var isRmsFeaturedLinePreset = deps.isRmsFeaturedLinePreset;
    var isRmsLine1Preset = deps.isRmsLine1Preset;
    var isRmsFeaturedBarPreset = deps.isRmsFeaturedBarPreset;

    function mergeTooltipLabel(baseOptions, labelFn) {
      if (!labelFn) return baseOptions;
      var plugins = Object.assign({}, baseOptions.plugins);
      var tooltip = Object.assign({}, plugins.tooltip);
      var callbacks = Object.assign({}, tooltip.callbacks, {
        label: function (c) { return labelFn(c); },
      });
      plugins.tooltip = Object.assign({}, tooltip, { callbacks: callbacks });
      return Object.assign({}, baseOptions, { plugins: plugins });
    }

    function horizontalBarOptionsForStyle(prefix, suffix, style) {
      var opts = horizontalBarOptions(prefix, suffix);
      if (opts.scales && opts.scales.x && opts.scales.x.grid) {
        opts.scales.x.grid.display = style.show_grid !== false;
      }
      return opts;
    }

    function resolvePresetChartType(style) {
      var t = (style && style.chart_type) || "horizontal_bar";
      return RMS_PRESET_CHART_TYPES.indexOf(t) >= 0 ? t : "horizontal_bar";
    }

    function applyPresetStyleRowsForSeries(rows, style, opts) {
      opts = opts || {};
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

    function presetTooltipValue(prefix, suffix, parsed) {
      prefix = prefix != null ? String(prefix) : "";
      suffix = suffix != null ? String(suffix) : "";
      if (parsed == null || typeof parsed !== "object") {
        return prefix + String(parsed != null ? parsed : "") + suffix;
      }
      if (parsed.x != null && parsed.y == null) return prefix + String(parsed.x) + suffix;
      if (parsed.y != null) return prefix + String(parsed.y) + suffix;
      return prefix + String(parsed) + suffix;
    }

    function verticalBarOptionsForStyle(prefix, suffix, style) {
      prefix = prefix != null ? String(prefix) : "";
      suffix = suffix != null ? String(suffix) : "";
      return {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 250 },
        plugins: {
          legend: { display: false },
          datalabels: { display: false },
          tooltip: whiteTooltip(function (c) {
            return presetTooltipValue(prefix, suffix, c.parsed);
          }),
        },
        scales: {
          x: {
            grid: { display: false, drawBorder: false },
            border: { display: false },
            ticks: { color: RMS_CHART_TICK_COLOR, font: { size: 10 }, maxRotation: 45, minRotation: 0 },
          },
          y: {
            beginAtZero: true,
            grid: { color: RMS_CHART_GRID_COLOR, display: style.show_grid !== false, drawBorder: false },
            border: { display: false },
            ticks: { color: RMS_CHART_TICK_COLOR, font: { size: 10 }, precision: 0 },
          },
        },
      };
    }

    function lineChartOptionsForStyle(prefix, suffix, style, legend) {
      prefix = prefix != null ? String(prefix) : "";
      suffix = suffix != null ? String(suffix) : "";
      return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        animation: { duration: 250 },
        plugins: {
          legend: {
            display: !!legend,
            position: "bottom",
            labels: { boxWidth: 10, padding: 8, font: { size: 10 }, color: "#6b7280" },
          },
          datalabels: { display: false },
          tooltip: whiteTooltip(function (c) {
            var label = c.dataset.label ? c.dataset.label + ": " : "";
            return label + presetTooltipValue(prefix, suffix, c.parsed);
          }),
        },
        scales: {
          x: {
            grid: { color: RMS_CHART_GRID_COLOR, display: style.show_grid !== false, drawBorder: false },
            border: { display: false },
            ticks: { color: RMS_CHART_TICK_COLOR, font: { size: 10 } },
          },
          y: {
            beginAtZero: true,
            grid: { color: RMS_CHART_GRID_COLOR, display: style.show_grid !== false, drawBorder: false },
            border: { display: false },
            ticks: { color: RMS_CHART_TICK_COLOR, font: { size: 10 }, precision: 0 },
          },
        },
      };
    }

    function doughnutChartOptionsForStyle(prefix, suffix, totalText) {
      prefix = prefix != null ? String(prefix) : "";
      suffix = suffix != null ? String(suffix) : "";
      return {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "74%",
        animation: { duration: 250 },
        plugins: {
          legend: {
            display: true,
            position: "bottom",
            labels: { boxWidth: 10, padding: 8, font: { size: 10 }, color: "#6b7280" },
          },
          datalabels: { display: false },
          centerTotal: { display: true, text: totalText },
          tooltip: whiteTooltip(function (c) {
            return c.label + ": " + presetTooltipValue(prefix, suffix, c.parsed);
          }),
        },
      };
    }

    function groupedHorizontalBarOptionsForStyle(style, prefix, suffix) {
      prefix = prefix != null ? String(prefix) : "";
      suffix = suffix != null ? String(suffix) : "";
      return {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        animation: { duration: 250 },
        plugins: {
          legend: {
            display: true,
            position: "bottom",
            labels: { boxWidth: 10, padding: 8, font: { size: 10 }, color: "#6b7280" },
          },
          datalabels: { display: false },
          tooltip: whiteTooltip(function (c) {
            return c.dataset.label + ": " + presetTooltipValue(prefix, suffix, c.parsed);
          }),
        },
        scales: {
          x: {
            beginAtZero: true,
            grid: { color: RMS_CHART_GRID_COLOR, display: style.show_grid !== false, drawBorder: false },
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

    function applyPercentScaleToOptions(base, chartType) {
      if (!base || !base.scales) return base;
      var axisKey = chartType === "horizontal_bar" ? "x" : "y";
      var axis = base.scales[axisKey];
      if (!axis) return base;
      base.scales[axisKey] = Object.assign({}, axis, {
        min: 0,
        max: 100,
        ticks: Object.assign({}, axis.ticks || {}, {
          callback: function (value) { return value + "%"; },
        }),
      });
      return base;
    }

    function scheduleFeaturedPresetRender(fn) {
      var run = function () {
        if (typeof requestAnimationFrame === "function") {
          requestAnimationFrame(fn);
        } else {
          fn();
        }
      };
      if (typeof nextTick === "function") {
        nextTick(function () { nextTick(run); });
      } else {
        setTimeout(run, 0);
      }
    }

    function resetFeaturedMount(canvasId) {
      var mount = document.getElementById(canvasId + "-featured");
      if (!mount) return;
      if (global.CrmFeaturedLineChartKit) {
        global.CrmFeaturedLineChartKit.destroyFeaturedLine(mount);
      }
      if (global.CrmFeaturedBarChartKit) {
        global.CrmFeaturedBarChartKit.destroyFeaturedBarChart(mount);
      }
    }

    function resetLine1Mount(canvasId) {
      var mount = document.getElementById(canvasId + "-line1");
      if (!mount) return;
      if (global.CrmLine1ChartKit) global.CrmLine1ChartKit.destroy(mount);
    }

    function line1ConfigFromStyle(style, prefix, suffix, periodLabel) {
      return {
        prefix: prefix,
        suffix: suffix,
        line1_value_mode: style.line1_value_mode || "sum",
        line1_x_axis_mode: style.line1_x_axis_mode || "all",
        line1_range_label: periodLabel || style.line1_range_label || "全部",
        show_line1_range: style.show_line1_range !== false,
        show_line1_fullscreen: style.show_line1_fullscreen !== false,
        show_line1_grid: style.show_line1_grid !== false,
        color: style.color || "green",
        color_shade: style.color_shade != null ? style.color_shade : 2,
      };
    }

    function line1WidgetConfig(w) {
      var l1Cfg = KIT.normalizeWidgetConfig(w.config || {});
      if (typeof line1PeriodLabel === "function") {
        l1Cfg.line1_range_label = line1PeriodLabel(appliedFilters || {});
      }
      return l1Cfg;
    }

    function renderLine1PresetChart(canvasId, rows, style, opts) {
      opts = opts || {};
      if (!global.CrmLine1ChartKit) return;

      function paintLine1() {
        var mount = document.getElementById(canvasId + "-line1");
        if (!mount) return false;
        destroyChartKey(canvasId);
        resetLine1Mount(canvasId);
        var prefix = opts.prefix != null ? String(opts.prefix) : "";
        var suffix = opts.suffix != null ? String(opts.suffix) : "";
        var labels = rows.map(function (r) { return r.label; });
        var values = rows.map(presetRowValue);
        var total = values.reduce(function (sum, v) { return sum + v; }, 0);
        var palette = paletteForStyle(style);
        var accent = palette[KIT.selectedShade(presetStyleColorCfg(style))];
        var apiData = {
          status: rows.length ? "ok" : "empty",
          kind: "series",
          labels: labels,
          values: values,
          total: total,
          prefix: prefix,
          suffix: suffix,
        };
        var widget = {
          title: opts.title || "",
          config: line1ConfigFromStyle(
            style,
            prefix,
            suffix,
            typeof line1PeriodLabel === "function" ? line1PeriodLabel(appliedFilters || {}) : ""
          ),
        };
        global.CrmLine1ChartKit.render(mount, widget, apiData, { lineColor: accent });
        return true;
      }

      scheduleFeaturedPresetRender(function () {
        safeRenderChart(canvasId, function () {
          if (paintLine1()) return;
          scheduleFeaturedPresetRender(function () {
            safeRenderChart(canvasId, paintLine1);
          });
        });
      });
    }

    function renderFeaturedPresetChart(canvasId, rows, style, opts) {
      opts = opts || {};
      if (!global.CrmFeaturedLineChartKit) return;

      function paintFeaturedLine() {
        var mount = document.getElementById(canvasId + "-featured");
        if (!mount) return false;
        destroyChartKey(canvasId);
        resetFeaturedMount(canvasId);
        var prefix = opts.prefix != null ? String(opts.prefix) : "";
        var suffix = opts.suffix != null ? String(opts.suffix) : "";
        var labels = rows.map(function (r) { return r.label; });
        var values = rows.map(presetRowValue);
        var total = values.reduce(function (sum, v) { return sum + v; }, 0);
        var palette = paletteForStyle(style);
        var accent = palette[KIT.selectedShade(presetStyleColorCfg(style))];
        var apiData = {
          status: "ok",
          kind: "series",
          labels: labels,
          values: values,
          total: total,
          prefix: prefix,
          suffix: suffix,
        };
        var widget = {
          title: opts.title || "",
          config: {
            prefix: prefix,
            suffix: suffix,
            comparison_label: style.comparison_label || "较上期",
            average_label: style.average_label || "",
            show_average_line: style.show_average_line !== false,
            show_comparison: style.show_comparison !== false,
            highlight_latest: style.highlight_latest !== false,
            featured_value_mode: style.featured_value_mode || "auto",
            show_point_values: style.show_point_values === true,
            lifecycle_pass_rate: opts.blockKey === "chart_lifecycle_pass_rate"
              || (opts.blockKey === "lifecycle_funnel" && (style.metric || "count") === "pass_rate"),
          },
        };
        global.CrmFeaturedLineChartKit.renderFeaturedLine(mount, widget, apiData, { lineColor: accent });
        return true;
      }

      scheduleFeaturedPresetRender(function () {
        safeRenderChart(canvasId, function () {
          if (paintFeaturedLine()) return;
          scheduleFeaturedPresetRender(function () {
            safeRenderChart(canvasId, paintFeaturedLine);
          });
        });
      });
    }

    function applyFeaturedBarMountTheme(mount, style) {
      if (!mount || !style) return;
      var palette = paletteForStyle(style);
      var si = KIT.selectedShade(presetStyleColorCfg(style));
      var accent = palette[si];
      var dark = palette[4] || accent;
      var soft = palette[0] || accent;
      mount.style.setProperty("--featured-bar-blue", accent);
      mount.style.setProperty("--featured-bar-blue-dark", dark);
      mount.style.setProperty("--featured-bar-blue-soft", soft);
    }

    function renderFeaturedBarPresetChart(canvasId, rows, style, opts) {
      opts = opts || {};
      if (!global.CrmFeaturedBarChartKit) return;

      function paintFeaturedBar() {
        var mount = document.getElementById(canvasId + "-featured");
        if (!mount) return false;
        applyFeaturedBarMountTheme(mount, style);
        destroyChartKey(canvasId);
        resetFeaturedMount(canvasId);
        var prefix = opts.prefix != null ? String(opts.prefix) : "";
        var suffix = opts.suffix != null ? String(opts.suffix) : "";
        var labels = rows.map(function (r) { return r.label; });
        var values = rows.map(presetRowValue);
        var total = values.reduce(function (sum, v) { return sum + v; }, 0);
        var apiData = {
          status: "ok",
          kind: "series",
          labels: labels,
          values: values,
          total: total,
          prefix: prefix,
          suffix: suffix,
        };
        var widget = {
          title: opts.title || "",
          config: {
            prefix: prefix,
            suffix: suffix,
            average_label: style.average_label || "Avg",
            show_average_line: style.show_average_line !== false,
            show_tooltip: style.show_tooltip !== false,
            show_summary_legend: style.show_summary_legend !== false,
            highlight_item: style.highlight_item === "max" ? "max" : "latest",
          },
        };
        global.CrmFeaturedBarChartKit.renderFeaturedBarChart(mount, widget, apiData);
        return true;
      }

      scheduleFeaturedPresetRender(function () {
        safeRenderChart(canvasId, function () {
          if (paintFeaturedBar()) return;
          scheduleFeaturedPresetRender(function () {
            safeRenderChart(canvasId, paintFeaturedBar);
          });
        });
      });
    }

    function renderPresetSeriesChart(canvasId, rows, style, opts) {
      opts = opts || {};
      var prefix = opts.prefix != null ? String(opts.prefix) : "";
      var suffix = opts.suffix != null ? String(opts.suffix) : "";
      var chartType = resolvePresetChartType(style);
      if (chartType === "featured_line") {
        renderFeaturedPresetChart(canvasId, rows, style, opts);
        return;
      }
      if (chartType === "line_1") {
        renderLine1PresetChart(canvasId, rows, style, opts);
        return;
      }
      if (chartType === "featured_bar") {
        renderFeaturedBarPresetChart(canvasId, rows, style, opts);
        return;
      }
      resetFeaturedMount(canvasId);
      resetLine1Mount(canvasId);
      var radius = Number(style.bar_radius) || RMS_CHART_BAR_RADIUS;
      var palette = paletteForStyle(style);
      var accent = palette[KIT.selectedShade(presetStyleColorCfg(style))];
      var customTooltipLabel = opts.tooltipLabel;
      function finalizeOptions(base) {
        var out = base;
        if (opts.percentScale) out = applyPercentScaleToOptions(out, chartType);
        if (typeof customTooltipLabel === "function") {
          out = mergeTooltipLabel(out, function (c) {
            return customTooltipLabel(c, rows);
          });
        }
        return out;
      }
      safeRenderChart(canvasId, function () {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyChartKey(canvasId);
        if (!rows.length) return;
        var labels = rows.map(function (r) { return r.label; });
        var values = rows.map(presetRowValue);
        var colors = presetBarColorsFromStyle(style, rows.length);
        if (chartType === "pie") {
          var total = values.reduce(function (sum, v) { return sum + v; }, 0);
          chartInstances[canvasId] = new Chart(canvas, {
            type: "doughnut",
            data: {
              labels: labels,
              datasets: [{ data: values, backgroundColor: colors, borderColor: "#fff", borderWidth: 2 }],
            },
            options: finalizeOptions(doughnutChartOptionsForStyle(prefix, suffix, prefix + KIT.fmtNum(total) + suffix)),
          });
          return;
        }
        if (chartType === "line") {
          chartInstances[canvasId] = new Chart(canvas, {
            type: "line",
            data: {
              labels: labels,
              datasets: [{
                data: values,
                borderColor: accent,
                backgroundColor: accent + "1f",
                fill: true,
                tension: 0.25,
                pointRadius: 2,
                pointBackgroundColor: accent,
                borderWidth: 2,
              }],
            },
            options: finalizeOptions(lineChartOptionsForStyle(prefix, suffix, style, false)),
          });
          return;
        }
        if (chartType === "bar") {
          chartInstances[canvasId] = new Chart(canvas, {
            type: "bar",
            data: {
              labels: labels,
              datasets: [{
                data: values,
                backgroundColor: colors,
                borderRadius: radius,
                maxBarThickness: 44,
                barPercentage: 0.72,
                categoryPercentage: 0.68,
              }],
            },
            options: finalizeOptions(verticalBarOptionsForStyle(prefix, suffix, style)),
          });
          return;
        }
        chartInstances[canvasId] = new Chart(canvas, {
          type: "bar",
          data: {
            labels: labels,
            datasets: [{
              data: values,
              backgroundColor: colors,
              borderRadius: radius,
              maxBarThickness: 34,
              barPercentage: 0.72,
              categoryPercentage: 0.68,
            }],
          },
          options: finalizeOptions(horizontalBarOptionsForStyle(prefix, suffix, style)),
        });
      });
    }

    function groupedBarOptionsForStyle(style) {
      var opts = groupedBarOptions();
      if (opts.scales && opts.scales.y && opts.scales.y.grid) {
        opts.scales.y.grid.display = style.show_grid !== false;
        opts.scales.y.grid.color = RMS_CHART_GRID_COLOR;
      }
      return opts;
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

    function renderPipelineChart(canvasId, w) {
      if (!data.value) return;
      var block = "chart_pipeline";
      var style = rmsPresetStyle(w && w.config, block);
      var items = applyPresetStyleRows(
        (data.value.pipeline_overview || []).map(function (x) {
          return { label: x.label, count: x.count != null ? x.count : 0 };
        }),
        style
      );
      renderPresetSeriesChart(canvasId, items, style, { prefix: "", suffix: "" });
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
          options: horizontalBarOptions("", "%"),
        });
      });
    }

    function syncPresetGroupedComposition(canvas, datasets, cfg) {
      if (!canvas || !KIT || !KIT.syncGroupedComposition) return;
      KIT.syncGroupedComposition(canvas, { datasets: datasets }, cfg || { show_group_composition: true });
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
              { label: "一面通过", data: rows.map(function (r) { return r.first_interview_passed_count || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.passed, borderRadius: 4 },
              { label: "二面通过", data: rows.map(function (r) { return r.second_interview_passed_count || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.interviewed, borderRadius: 4 },
            ],
          },
          options: groupedBarOptions(),
        });
        syncPresetGroupedComposition(canvas, chartInstances[canvasId].data.datasets, { show_group_composition: true });
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
              { label: "约面中", data: rows.map(function (r) { return r.scheduling_interview_count || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.scheduling },
              { label: "待面试", data: rows.map(function (r) { return r.pending_interview || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.pendingInterview },
              { label: "一面通过", data: rows.map(function (r) { return r.first_interview_passed_count || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.passed },
              { label: "二面通过", data: rows.map(function (r) { return r.second_interview_passed_count || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.interviewed },
              { label: "放弃面试", data: rows.map(function (r) { return r.interview_abandoned || 0; }), backgroundColor: JOB_STAGE_CHART_COLORS.abandoned },
            ],
          },
          options: stackedHorizontalOptions(),
        });
        syncPresetGroupedComposition(canvas, chartInstances[canvasId].data.datasets, { show_group_composition: true });
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
          { label: "一面数", value: total.first_interview_count || 0, color: JOB_STAGE_CHART_COLORS.interviewed },
          { label: "一面通过", value: total.first_interview_passed_count || 0, color: JOB_STAGE_CHART_COLORS.passed },
          { label: "二面数", value: total.second_interview_count || 0, color: JOB_STAGE_CHART_COLORS.scheduling },
          { label: "二面通过", value: total.second_interview_passed_count || 0, color: JOB_STAGE_CHART_COLORS.client },
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

    function renderHorizontalCountChart(canvasId, rows, emptyLabel, style, w) {
      renderPresetSeriesChart(canvasId, rows, style, {
        prefix: emptyLabel || "",
        suffix: "",
        title: w && w.title,
      });
    }

    function renderPendingBacklogChart(canvasId, w) {
      var block = "chart_pending_backlog";
      var style = rmsPresetStyle(w && w.config, block);
      renderHorizontalCountChart(
        canvasId,
        applyPresetStyleRows(pendingBacklogRows.value, style),
        "人数",
        style,
        w
      );
    }

    function buildLifecyclePassRateRows() {
      return lifecycleRows.value
        .filter(function (r) { return r.key !== "resume" && r.pass_rate_value != null; })
        .map(function (r) {
          return {
            label: r.label,
            value: r.pass_rate_value != null ? r.pass_rate_value : 0,
            passed: r.passed,
            processed: r.processed,
          };
        });
    }

    function lifecyclePassRateTooltip(c, chartRows) {
      var row = chartRows[c.dataIndex];
      var pct = presetTooltipValue("", "%", c.parsed);
      if (!row) return pct;
      if (row.processed != null && row.processed > 0) {
        return row.label + ": " + pct + " (" + row.passed + "/" + row.processed + ")";
      }
      return row.label + ": " + pct;
    }

    function renderLifecycleFunnelChart(canvasId, w) {
      var block = "lifecycle_funnel";
      var style = rmsPresetStyle(w && w.config, block);
      if ((style.metric || "count") === "pass_rate") {
        renderLifecyclePassRateChart(canvasId, w, { blockKey: block, style: style });
        return;
      }
      var rows = lifecycleRows.value.map(function (r) {
          return {
            label: r.label,
            value: r.funnel_count != null ? r.funnel_count : 0,
            pass_rate: r.pass_rate,
          };
        });
      renderPresetSeriesChart(canvasId, applyPresetStyleRows(rows, style), style, {
        prefix: "",
        suffix: "",
        title: w && w.title,
        tooltipLabel: function (c, chartRows) {
          var row = chartRows[c.dataIndex];
          var count = presetTooltipValue("", "", c.parsed);
          if (!row || !row.pass_rate || row.pass_rate === "—") return count;
          return count + " (" + row.pass_rate + ")";
        },
      });
    }

    function renderLifecyclePassRateChart(canvasId, w, renderOpts) {
      renderOpts = renderOpts || {};
      var block = renderOpts.blockKey || "chart_lifecycle_pass_rate";
      var style = renderOpts.style || rmsPresetStyle(w && w.config, block);
      var rows = buildLifecyclePassRateRows();
      renderPresetSeriesChart(canvasId, applyPresetStyleRowsForSeries(rows, style, { blockKey: block, suffix: "%" }), style, {
        prefix: "",
        suffix: "%",
        title: w && w.title,
        percentScale: true,
        tooltipLabel: lifecyclePassRateTooltip,
        blockKey: block,
      });
    }

    function renderJobPendingBacklogChart(canvasId, w) {
      var block = "chart_job_pending_backlog";
      var style = rmsPresetStyle(w && w.config, block);
      renderHorizontalCountChart(
        canvasId,
        applyPresetStyleRows(jobPendingBacklogRows.value, style),
        "积压",
        style,
        w
      );
    }

    function renderClientHiredRankingChart(canvasId, w) {
      var block = "chart_client_hired_ranking";
      var style = rmsPresetStyle(w && w.config, block);
      renderHorizontalCountChart(
        canvasId,
        applyPresetStyleRows(clientHiredRankingRows.value, style),
        "入职",
        style,
        w
      );
    }

    function renderRecruiterRecommendVsHiredChart(canvasId, w) {
      var block = "chart_recruiter_recommend_vs_hired";
      var style = rmsPresetStyle(w && w.config, block);
      var chartType = resolvePresetChartType(style);
      if (chartType === "pie") chartType = "horizontal_bar";
      var compCfg = { show_group_composition: style.show_group_composition !== false };
      var palette = paletteForStyle(style);
      var si = KIT.selectedShade(presetStyleColorCfg(style));
      var radius = Number(style.bar_radius) || 6;
      safeRenderChart(canvasId, function () {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyChartKey(canvasId);
        var rows = applyPresetStyleRows(
          recruiterRecommendVsHiredRows.value.map(function (r) {
            return {
              recruiter_user_id: r.recruiter_user_id,
              recommended_count: r.recommended_count,
              hired_count: r.hired_count,
              hired_this_month: r.hired_this_month,
              label: r.recruiter_user_id != null ? "ID " + r.recruiter_user_id : "—",
              value: r.recommended_count != null ? r.recommended_count : 0,
            };
          }),
          style
        );
        if (!rows.length) return;
        var labels = rows.map(function (r) { return r.label; });
        var recommendData = rows.map(function (r) { return r.recommended_count != null ? r.recommended_count : 0; });
        var hiredData = rows.map(function (r) {
          return r.hired_count != null ? r.hired_count : (r.hired_this_month != null ? r.hired_this_month : 0);
        });
        if (chartType === "line") {
          chartInstances[canvasId] = new Chart(canvas, {
            type: "line",
            data: {
              labels: labels,
              datasets: [
                {
                  label: "推荐量",
                  data: recommendData,
                  borderColor: palette[si],
                  backgroundColor: palette[si] + "1f",
                  fill: false,
                  tension: 0.25,
                  pointRadius: 2,
                  borderWidth: 2,
                },
                {
                  label: "入职数",
                  data: hiredData,
                  borderColor: palette[(si + 2) % palette.length],
                  backgroundColor: palette[(si + 2) % palette.length] + "1f",
                  fill: false,
                  tension: 0.25,
                  pointRadius: 2,
                  borderWidth: 2,
                },
              ],
            },
            options: lineChartOptionsForStyle("", "", style, true),
          });
          syncPresetGroupedComposition(canvas, chartInstances[canvasId].data.datasets, compCfg);
          return;
        }
        if (chartType === "horizontal_bar") {
          chartInstances[canvasId] = new Chart(canvas, {
            type: "bar",
            data: {
              labels: labels,
              datasets: [
                {
                  label: "推荐量",
                  data: recommendData,
                  backgroundColor: palette[si],
                  borderRadius: radius,
                  barPercentage: 0.72,
                  categoryPercentage: 0.68,
                },
                {
                  label: "入职数",
                  data: hiredData,
                  backgroundColor: palette[(si + 2) % palette.length],
                  borderRadius: radius,
                  barPercentage: 0.72,
                  categoryPercentage: 0.68,
                },
              ],
            },
            options: groupedHorizontalBarOptionsForStyle(style, "", ""),
          });
          syncPresetGroupedComposition(canvas, chartInstances[canvasId].data.datasets, compCfg);
          return;
        }
        chartInstances[canvasId] = new Chart(canvas, {
          type: "bar",
          data: {
            labels: labels,
            datasets: [
              {
                label: "推荐量",
                data: recommendData,
                backgroundColor: palette[si],
                borderRadius: radius,
                barPercentage: 0.72,
                categoryPercentage: 0.68,
              },
              {
                label: "入职数",
                data: hiredData,
                backgroundColor: palette[(si + 2) % palette.length],
                borderRadius: radius,
                barPercentage: 0.72,
                categoryPercentage: 0.68,
              },
            ],
          },
          options: groupedBarOptionsForStyle(style),
        });
        syncPresetGroupedComposition(canvas, chartInstances[canvasId].data.datasets, compCfg);
      });
    }

    function renderSingleWidget(w, opts) {
      opts = opts || {};
      if (!chartsAvailable() || !w) return;
      var block = widgetBlock(w);
      var rmsId = chartCanvasId(w);

      if (block === "chart_pipeline") {
        renderPipelineChart(rmsId, w);
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
      if (block === "chart_pending_backlog") {
        renderPendingBacklogChart(rmsId, w);
        return;
      }
      if (block === "lifecycle_funnel") {
        renderLifecycleFunnelChart(rmsId, w);
        return;
      }
      if (block === "chart_lifecycle_pass_rate") {
        renderLifecyclePassRateChart(rmsId, w);
        return;
      }
      if (block === "chart_job_pending_backlog") {
        renderJobPendingBacklogChart(rmsId, w);
        return;
      }
      if (block === "chart_client_hired_ranking") {
        renderClientHiredRankingChart(rmsId, w);
        return;
      }
      if (block === "chart_recruiter_recommend_vs_hired") {
        renderRecruiterRecommendVsHiredChart(rmsId, w);
        return;
      }

      if (KIT.CHART_WIDGET_TYPES.indexOf(w.widget_type) >= 0) {
        var wd = widgetData.value[w.id];
        if (!wd) return;
        if (w.widget_type === "featured_line" && global.CrmFeaturedLineChartKit) {
          destroyChartKey(rmsId);
          var flMount = document.getElementById(featuredLineMountId(w));
          if (flMount && wd.status === "ok") {
            var flCfg = KIT.normalizeWidgetConfig(w.config || {});
            var flPal = KIT.widgetPalette(flCfg);
            var flAccent = flPal[KIT.selectedShade(flCfg)];
            global.CrmFeaturedLineChartKit.renderFeaturedLine(flMount, w, wd, { lineColor: flAccent });
          }
          return;
        }
        if (w.widget_type === "line_1" && global.CrmLine1ChartKit) {
          destroyChartKey(rmsId);
          var l1Mount = document.getElementById(line1MountId(w));
          if (l1Mount) {
            var l1Cfg = line1WidgetConfig(w);
            var l1Pal = KIT.widgetPalette(l1Cfg);
            var l1Accent = l1Pal[KIT.selectedShade(l1Cfg)];
            global.CrmLine1ChartKit.render(
              l1Mount,
              Object.assign({}, w, { config: l1Cfg }),
              wd || { status: "empty" },
              { lineColor: l1Accent }
            );
          }
          return;
        }
        if (w.widget_type === "featured_bar") {
          var secField = (w.config && w.config.secondary_axis_field) || "";
          if (secField) {
            var fbGroupedMount = document.getElementById(featuredBarMountId(w));
            if (fbGroupedMount && global.CrmFeaturedBarChartKit) {
              global.CrmFeaturedBarChartKit.destroyFeaturedBarChart(fbGroupedMount);
            }
            function paintFeaturedBarGrouped() {
              var canvasId = KIT.chartCanvasId(w);
              var canvas = document.getElementById(canvasId);
              if (!canvas || !wd || wd.status !== "ok" || wd.kind !== "grouped_series") return false;
              KIT.renderGroupedChart(chartInstances, destroyChartKey, w, wd, {
                viewIndex: null,
                animate: opts.animate !== false,
              });
              var chart = chartInstances[canvasId];
              if (chart && typeof chart.resize === "function") chart.resize();
              return !!chart;
            }
            scheduleFeaturedPresetRender(function () {
              if (paintFeaturedBarGrouped()) return;
              scheduleFeaturedPresetRender(paintFeaturedBarGrouped);
            });
            return;
          }
          destroyChartKey(KIT.chartCanvasId(w));
          if (global.CrmFeaturedBarChartKit && wd.status === "ok") {
            var fbMount = document.getElementById(featuredBarMountId(w));
            if (fbMount) {
              global.CrmFeaturedBarChartKit.renderFeaturedBarChart(fbMount, w, wd);
            }
          }
          return;
        }
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

    function renderFeaturedPresetWidgets() {
      if (!chartsAvailable()) return;
      var tab = activeTab.value;
      if (!tab || !tab.widgets) return;
      tab.widgets.forEach(function (w) {
        var isLine = typeof isRmsFeaturedLinePreset === "function" && isRmsFeaturedLinePreset(w);
        var isLine1 = typeof isRmsLine1Preset === "function" && isRmsLine1Preset(w);
        var isBar = typeof isRmsFeaturedBarPreset === "function" && isRmsFeaturedBarPreset(w);
        if (isLine || isLine1 || isBar) renderSingleWidget(w, { animate: false });
      });
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

    return {
      renderSingleWidget: renderSingleWidget,
      renderVisibleCharts: renderVisibleCharts,
      renderFeaturedPresetWidgets: renderFeaturedPresetWidgets,
      renderFeaturedLineWidgets: renderFeaturedPresetWidgets,
    };
  }

  global.CrmRmsDashboardCharts = {
    createDashboardCharts: createDashboardCharts,
  };
})(typeof window !== "undefined" ? window : globalThis);
