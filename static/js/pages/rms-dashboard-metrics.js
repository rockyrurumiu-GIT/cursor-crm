/**
 * RMS Dashboard derived metrics.
 * Vue computed helpers only. No fetch, no Chart.js, no DOM mutation.
 */
(function (global) {
  "use strict";

  function createDashboardMetrics(deps) {
    var computed = deps.computed;
    var data = deps.data;
    var appliedFilters = deps.appliedFilters;
    var jobOptions = deps.jobOptions;
    var truncateJobLabel = deps.truncateJobLabel;

    function jobPendingTotal(row) {
      if (!row) return 0;
      return (
        (row.pending_internal_screen || 0)
        + (row.pending_client_screen || 0)
        + (row.scheduling_interview_count || 0)
        + (row.pending_interview || 0)
        + (row.pending_second_interview || 0)
        + (row.pending_final_interview || 0)
        + (row.pending_offer_count || 0)
        + (row.onboarding_count || 0)
        + (row.pending_roster_conversion_count || 0)
      );
    }

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

    var lifecycleFunnel = computed(function () {
      return (data.value && data.value.lifecycle_funnel) || null;
    });
    var lifecycleRows = computed(function () {
      var lf = lifecycleFunnel.value;
      return lf && lf.rows ? lf.rows : [];
    });
    var resumeCount = computed(function () {
      var lf = lifecycleFunnel.value;
      return lf ? (lf.base_count || 0) : 0;
    });
    var hiredCount = computed(function () {
      var lf = lifecycleFunnel.value;
      return lf ? (lf.hired_count || 0) : 0;
    });
    var resumeToHireRate = computed(function () {
      var lf = lifecycleFunnel.value;
      return (lf && lf.resume_to_hire_rate) || "—";
    });

    var pendingBacklogRows = computed(function () {
      var rows = (data.value && data.value.pipeline_overview) || [];
      var out = rows.map(function (p) {
        return { label: p.label || p.status, count: p.count || 0 };
      });
      var total = clientJobStageTotal.value;
      if (total && total.pending_roster_conversion_count) {
        out.push({ label: "待转花名册", count: total.pending_roster_conversion_count });
      }
      return out;
    });

    var jobPendingBacklogRows = computed(function () {
      return clientJobStageRows.value
        .map(function (r) {
          return {
            label: truncateJobLabel(r.job_title, 12),
            count: jobPendingTotal(r),
          };
        })
        .filter(function (r) { return r.count > 0; });
    });

    var clientHiredRankingRows = computed(function () {
      var byClient = {};
      clientJobStageRows.value.forEach(function (r) {
        var key = String(r.client_id || r.client_name || "—");
        if (!byClient[key]) {
          byClient[key] = { label: r.client_name || ("客户#" + r.client_id), count: 0 };
        }
        byClient[key].count += (r.hired_count || 0);
      });
      return Object.keys(byClient)
        .map(function (k) { return byClient[k]; })
        .filter(function (r) { return r.count > 0; });
    });

    var recruiterRecommendVsHiredRows = computed(function () {
      return (data.value && data.value.recruiter_performance) || [];
    });

    function jobStageMetricText(row, countKey, rateKey) {
      if (!row) return "—";
      var count = row[countKey];
      if (count == null) count = 0;
      var rate = row[rateKey];
      if (!rate || rate === "—") return String(count);
      return String(count) + " (" + rate + ")";
    }

    function jobStageMetricTitle(row, countKey, denomKey, label) {
      if (!row) return label;
      var count = row[countKey];
      if (count == null) count = 0;
      var denom = row[denomKey];
      if (denom == null) denom = 0;
      if (denom <= 0) return label + "：—";
      return label + "：" + count + "/" + denom;
    }

    var activeFilterSummary = computed(function () {
      var labels = {
        client_id: "客户ID",
        job_ids: "岗位",
        delivery_user_id: "交付用户ID",
        recruiter_user_id: "推荐人用户ID",
        city: "城市",
        date_from: "统计周期起",
        date_to: "统计周期止",
      };
      var out = [];
      Object.keys(labels).forEach(function (k) {
        var v = appliedFilters[k];
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
      if ((!appliedFilters.job_ids || !appliedFilters.job_ids.length) && appliedFilters.job_ids_text) {
        out.push({ key: "job_ids_text", label: "岗位", value: String(appliedFilters.job_ids_text) });
      }
      return out;
    });

    return {
      historicalStages: historicalStages,
      clientJobStageSummary: clientJobStageSummary,
      clientJobStageRows: clientJobStageRows,
      clientJobStageTotal: clientJobStageTotal,
      clientJobStagePeriodLabel: clientJobStagePeriodLabel,
      lifecycleFunnel: lifecycleFunnel,
      lifecycleRows: lifecycleRows,
      resumeCount: resumeCount,
      hiredCount: hiredCount,
      resumeToHireRate: resumeToHireRate,
      pendingBacklogRows: pendingBacklogRows,
      jobPendingBacklogRows: jobPendingBacklogRows,
      clientHiredRankingRows: clientHiredRankingRows,
      recruiterRecommendVsHiredRows: recruiterRecommendVsHiredRows,
      jobStageMetricText: jobStageMetricText,
      jobStageMetricTitle: jobStageMetricTitle,
      activeFilterSummary: activeFilterSummary,
    };
  }

  global.CrmRmsDashboardMetrics = {
    createDashboardMetrics: createDashboardMetrics,
  };
})(typeof window !== "undefined" ? window : globalThis);
