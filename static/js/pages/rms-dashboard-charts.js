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

    var historicalStages = deps.historicalStages;
    var lifecycleRows = deps.lifecycleRows;
    var pendingBacklogRows = deps.pendingBacklogRows;
    var jobPendingBacklogRows = deps.jobPendingBacklogRows;
    var clientHiredRankingRows = deps.clientHiredRankingRows;
    var recruiterRecommendVsHiredRows = deps.recruiterRecommendVsHiredRows;

    var jobStageChartRows = deps.jobStageChartRows;
    var jobStageChartTotal = deps.jobStageChartTotal;

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

    function renderPresetSeriesChart(canvasId, rows, style, opts) {
      opts = opts || {};
      var prefix = opts.prefix != null ? String(opts.prefix) : "";
      var suffix = opts.suffix != null ? String(opts.suffix) : "";
      var chartType = resolvePresetChartType(style);
      var radius = Number(style.bar_radius) || RMS_CHART_BAR_RADIUS;
      var palette = paletteForStyle(style);
      var accent = palette[KIT.selectedShade(presetStyleColorCfg(style))];
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
            options: doughnutChartOptionsForStyle(prefix, suffix, prefix + KIT.fmtNum(total) + suffix),
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
            options: lineChartOptionsForStyle(prefix, suffix, style, false),
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
            options: verticalBarOptionsForStyle(prefix, suffix, style),
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
          options: horizontalBarOptionsForStyle(prefix, suffix, style),
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

    function renderHorizontalCountChart(canvasId, rows, emptyLabel, style) {
      renderPresetSeriesChart(canvasId, rows, style, { prefix: emptyLabel || "", suffix: "" });
    }

    function renderPendingBacklogChart(canvasId, w) {
      var block = "chart_pending_backlog";
      var style = rmsPresetStyle(w && w.config, block);
      renderHorizontalCountChart(
        canvasId,
        applyPresetStyleRows(pendingBacklogRows.value, style),
        "人数",
        style
      );
    }

    function renderLifecycleFunnelChart(canvasId) {
      safeRenderChart(canvasId, function () {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyChartKey(canvasId);
        var rows = lifecycleRows.value.filter(function (r) { return r.key !== "resume"; });
        if (!rows.length) return;
        chartInstances[canvasId] = new Chart(canvas, {
          type: "bar",
          data: {
            labels: rows.map(function (r) { return r.label; }),
            datasets: [{
              data: rows.map(function (r) { return r.funnel_count || 0; }),
              backgroundColor: rmsShadeRamp(rows.length),
              borderRadius: 6,
              barPercentage: 0.72,
            }],
          },
          options: horizontalBarOptions("人数"),
        });
      });
    }

    function renderLifecyclePassRateChart(canvasId, w) {
      var block = "chart_lifecycle_pass_rate";
      var style = rmsPresetStyle(w && w.config, block);
      var rows = lifecycleRows.value
        .filter(function (r) { return r.key !== "resume" && r.pass_rate_value != null; })
        .map(function (r) {
          return {
            label: r.label,
            value: r.pass_rate_value != null ? r.pass_rate_value : 0,
          };
        });
      renderPresetSeriesChart(canvasId, applyPresetStyleRows(rows, style), style, { prefix: "", suffix: "%" });
    }

    function renderJobPendingBacklogChart(canvasId, w) {
      var block = "chart_job_pending_backlog";
      var style = rmsPresetStyle(w && w.config, block);
      renderHorizontalCountChart(
        canvasId,
        applyPresetStyleRows(jobPendingBacklogRows.value, style),
        "积压",
        style
      );
    }

    function renderClientHiredRankingChart(canvasId, w) {
      var block = "chart_client_hired_ranking";
      var style = rmsPresetStyle(w && w.config, block);
      renderHorizontalCountChart(
        canvasId,
        applyPresetStyleRows(clientHiredRankingRows.value, style),
        "入职",
        style
      );
    }

    function renderRecruiterRecommendVsHiredChart(canvasId, w) {
      var block = "chart_recruiter_recommend_vs_hired";
      var style = rmsPresetStyle(w && w.config, block);
      var chartType = resolvePresetChartType(style);
      if (chartType === "pie") chartType = "horizontal_bar";
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
        renderLifecycleFunnelChart(rmsId);
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

    return {
      renderSingleWidget: renderSingleWidget,
      renderVisibleCharts: renderVisibleCharts,
    };
  }

  global.CrmRmsDashboardCharts = {
    createDashboardCharts: createDashboardCharts,
  };
})(typeof window !== "undefined" ? window : globalThis);
