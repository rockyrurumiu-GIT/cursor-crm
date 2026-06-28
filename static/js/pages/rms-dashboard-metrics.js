/**
 * RMS Dashboard derived metrics.
 * Vue computed helpers only. No fetch, no Chart.js, no DOM mutation.
 */
(function (global) {
  "use strict";

  var SUMMARY_METRIC_KEYS = [
    "pushed_resume_count",
    "internal_screen_passed",
    "duplicate_count",
    "pending_internal_screen",
    "pending_client_screen",
    "scheduling_interview_count",
    "client_screen_passed",
    "interview_abandoned",
    "pending_interview",
    "pending_second_interview",
    "pending_final_interview",
    "first_interview_count",
    "first_interview_passed_count",
    "second_interview_count",
    "second_interview_passed_count",
    "interviewed",
    "interview_passed",
    "pending_offer_count",
    "offer_accepted_count",
    "offer_dropped_count",
    "onboarding_count",
    "onboarding_lost_count",
    "hired_count",
    "pending_roster_conversion_count",
  ];
  var LOSS_METRIC_NAME_KEYS = [
    "interview_abandoned_names",
    "offer_dropped_names",
    "onboarding_lost_names",
  ];
  var JOB_STAGE_RATE_SPECS = [
    ["internal_screen_passed", "internal_screen_passed_rate", "pushed_resume_count"],
    ["duplicate_count", "duplicate_count_rate", "pushed_resume_count"],
    ["client_screen_passed", "client_screen_passed_rate", "internal_screen_passed"],
    ["interview_abandoned", "interview_abandoned_rate", "internal_screen_passed"],
    ["first_interview_passed_count", "first_interview_passed_rate", "first_interview_count"],
    ["second_interview_passed_count", "second_interview_passed_rate", "second_interview_count"],
    ["interview_passed", "interview_passed_rate", "interviewed"],
    ["offer_accepted_count", "offer_accepted_count_rate", "second_interview_passed_count"],
    ["offer_dropped_count", "offer_dropped_count_rate", "second_interview_passed_count"],
    ["onboarding_lost_count", "onboarding_lost_count_rate", "onboarding_count"],
  ];

  function jobStageRate(numerator, denominator) {
    if (denominator <= 0) return "—";
    return Math.round(100 * numerator / denominator) + "%";
  }

  function aggregateJobStageRows(rows) {
    if (!rows.length) return null;
    var total = { headcount: 0 };
    SUMMARY_METRIC_KEYS.forEach(function (key) { total[key] = 0; });
    LOSS_METRIC_NAME_KEYS.forEach(function (key) { total[key] = []; });
    rows.forEach(function (row) {
      total.headcount += row.headcount || 0;
      SUMMARY_METRIC_KEYS.forEach(function (key) {
        total[key] += row[key] || 0;
      });
      LOSS_METRIC_NAME_KEYS.forEach(function (key) {
        (row[key] || []).forEach(function (name) {
          if (name && total[key].indexOf(name) < 0) total[key].push(name);
        });
      });
    });
    JOB_STAGE_RATE_SPECS.forEach(function (spec) {
      total[spec[1]] = jobStageRate(total[spec[0]] || 0, total[spec[2]] || 0);
    });
    return total;
  }

  function isZeroResumeJobRow(row) {
    return !row || (row.pushed_resume_count || 0) === 0;
  }

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
      var rows = summary && summary.rows ? summary.rows : [];
      if (appliedFilters.include_zero_resume_jobs) return rows;
      return rows.filter(function (row) { return !isZeroResumeJobRow(row); });
    });
    var clientJobStageTotal = computed(function () {
      var summary = clientJobStageSummary.value;
      if (!summary) return null;
      if (appliedFilters.include_zero_resume_jobs) {
        return summary.total || null;
      }
      return aggregateJobStageRows(clientJobStageRows.value);
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

    var pipelineDialysisGrouped = computed(function () {
      return (data.value && data.value.pipeline_dialysis) || null;
    });

    function pipelineDialysisHasData(mode) {
      var pd = pipelineDialysisGrouped.value;
      if (!pd) return false;
      var slice = pd[mode || "active"];
      if (!slice || !slice.data || !slice.data.length) return false;
      var keys = slice.keys || [];
      return slice.data.some(function (row) {
        return keys.some(function (k) { return Number(row[k]) > 0; });
      });
    }

    function jobStageMetricText(row, countKey, rateKey) {
      if (!row) return "—";
      var count = row[countKey];
      if (count == null) count = 0;
      var rate = row[rateKey];
      if (!rate || rate === "—") return String(count);
      return String(count) + " (" + rate + ")";
    }

    function jobStageLossMetricCount(row, countKey) {
      if (!row) return 0;
      var count = row[countKey];
      return count == null ? 0 : count;
    }

    function jobStageLossNamesHint(row, namesKey) {
      if (!row) return "";
      var names = row[namesKey];
      if (!names || !names.length) return "暂无人员姓名";
      return names.join("\n");
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
      if (appliedFilters.include_zero_resume_jobs) {
        out.push({ key: "include_zero_resume_jobs", label: "岗位", value: "0简历岗位不隐藏" });
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
      pipelineDialysisGrouped: pipelineDialysisGrouped,
      pipelineDialysisHasData: pipelineDialysisHasData,
      jobStageMetricText: jobStageMetricText,
      jobStageMetricTitle: jobStageMetricTitle,
      jobStageLossMetricCount: jobStageLossMetricCount,
      jobStageLossNamesHint: jobStageLossNamesHint,
      activeFilterSummary: activeFilterSummary,
    };
  }

  global.CrmRmsDashboardMetrics = {
    createDashboardMetrics: createDashboardMetrics,
  };
})(typeof window !== "undefined" ? window : globalThis);
