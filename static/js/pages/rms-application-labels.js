/**
 * RMS application workflow labels & helpers (Plan 34).
 * Keep in sync with schemas/rms.py APPLICATION_PROGRESS_* / RECEIVE_STATUSES.
 */
(function (global) {
  "use strict";

  var RECEIVE_STATUS_LABELS = {
    pending: "未接收",
    accepted: "已接收",
    rejected: "已拒收",
  };

  var APPLICATION_PROGRESS_LABELS = {
    pending_internal_screen: "待内筛",
    internal_screen_failed: "内筛fail",
    pending_client_screen: "待客筛",
    client_screen_failed: "客筛fail",
    client_screen_duplicate: "重复",
    scheduling_interview: "约面中",
    interview_scheduling_failed: "约面fail",
    pending_first_interview: "待一面",
    first_interview_passed: "一面通过",
    first_interview_failed: "一面fail",
    second_interview_passed: "二面通过",
    second_interview_failed: "二面fail",
    second_interview_abandoned: "二面弃面",
    final_interview_failed: "终面fail",
    final_interview_abandoned: "终面弃面",
    pending_offer: "待offer",
    offer_approval_pending: "Offer审批中",
    offer_dropped: "弃offer",
    onboarding: "在途",
    onboarding_lost: "在途流失",
    hired: "已入职",
  };

  var LEGACY_PROGRESS_MAP = {
    recommended: "待内筛",
    screening: "待客筛",
    interview: "待一面",
    offer: "待offer",
    rejected: "已拒收",
    withdrawn: "已撤回",
  };

  var ALLOWED_PROGRESS_TRANSITIONS = {
    pending_internal_screen: ["internal_screen_failed", "pending_client_screen"],
    pending_client_screen: ["client_screen_failed", "scheduling_interview", "client_screen_duplicate"],
    scheduling_interview: ["interview_scheduling_failed", "pending_first_interview"],
    pending_first_interview: ["first_interview_failed", "first_interview_passed"],
    first_interview_passed: ["second_interview_failed", "second_interview_passed", "second_interview_abandoned"],
    second_interview_passed: ["final_interview_failed", "pending_offer", "final_interview_abandoned"],
    pending_offer: [],
    offer_approval_pending: [],
    onboarding: ["hired"],
  };

  var LEGACY_STATUS_NORMALIZE = {
    screening: "pending_client_screen",
    interview: "pending_first_interview",
    offer: "pending_offer",
  };

  /** Keep in sync with schemas/rms.py APPLICATION_PROGRESS_STATUSES */
  var APPLICATION_PROGRESS_STATUSES = [
    "pending_internal_screen",
    "internal_screen_failed",
    "pending_client_screen",
    "client_screen_failed",
    "client_screen_duplicate",
    "scheduling_interview",
    "interview_scheduling_failed",
    "pending_first_interview",
    "first_interview_passed",
    "first_interview_failed",
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
    "final_interview_failed",
    "final_interview_abandoned",
    "pending_offer",
    "offer_approval_pending",
    "offer_dropped",
    "onboarding",
    "onboarding_lost",
    "hired",
  ];

  var PROGRESS_TERMINAL = {
    internal_screen_failed: 1,
    client_screen_failed: 1,
    client_screen_duplicate: 1,
    interview_scheduling_failed: 1,
    first_interview_failed: 1,
    second_interview_failed: 1,
    second_interview_abandoned: 1,
    final_interview_failed: 1,
    final_interview_abandoned: 1,
    offer_dropped: 1,
    onboarding_lost: 1,
    hired: 1,
  };

  var PROTECTION_TERMINAL = {
    internal_screen_failed: 1,
    client_screen_failed: 1,
    client_screen_duplicate: 1,
    second_interview_abandoned: 1,
    final_interview_abandoned: 1,
    offer_dropped: 1,
    onboarding_lost: 1,
    hired: 1,
    rejected: 1,
    withdrawn: 1,
  };

  function progressLabel(status) {
    var s = status || "";
    return APPLICATION_PROGRESS_LABELS[s] || LEGACY_PROGRESS_MAP[s] || s || "—";
  }

  function receiveLabel(status) {
    var s = status == null ? "" : String(status).trim();
    if (!s) s = "pending";
    return RECEIVE_STATUS_LABELS[s] || s || "—";
  }

  function deliveryReviewLabel(status) {
    var s = status == null ? "" : String(status).trim();
    if (!s) s = "pending";
    return DELIVERY_REVIEW_STATUS_LABELS[s] || s || "—";
  }

  function offerApprovalPendingHint(app) {
    if (!app || app.status !== "offer_approval_pending") return "";
    var node = String(app.offer_current_approval_node_label == null ? "" : app.offer_current_approval_node_label).trim();
    var approver = String(app.offer_pending_approver_label == null ? "" : app.offer_pending_approver_label).trim();
    if (node && approver) return node + " · " + approver;
    if (node || approver) return node || approver;
    return "暂无审批信息";
  }

  function deriveProtectionStatus(status) {
    if (PROTECTION_TERMINAL[status]) return "已终止";
    return "生效中";
  }

  function normalizeProgressStatus(status) {
    var s = status == null ? "" : String(status).trim();
    return LEGACY_STATUS_NORMALIZE[s] || s;
  }

  function filterProgressStatus(status) {
    var raw = status == null ? "" : String(status).trim();
    if (!raw) return "";
    if (raw === "recommended") return "pending_internal_screen";
    return normalizeProgressStatus(raw);
  }

  function statusMatchesFilter(appStatus, selectedStatuses) {
    if (!selectedStatuses.length) return true;
    var raw = appStatus == null ? "" : String(appStatus).trim();
    var normalized = filterProgressStatus(raw);
    for (var i = 0; i < selectedStatuses.length; i++) {
      var want = String(selectedStatuses[i] == null ? "" : selectedStatuses[i]).trim();
      if (!want) continue;
      if (raw === want || normalized === want) return true;
    }
    return false;
  }

  function progressTransitionsFor(status) {
    return ALLOWED_PROGRESS_TRANSITIONS[normalizeProgressStatus(status)] || [];
  }

  /** Pipeline「下一步操作」第三列：统一黑色文案按钮 */
  var PIPELINE_NEXT_OP_COL3 = {
    client_screen_duplicate: 1,
    second_interview_abandoned: 1,
    final_interview_abandoned: 1,
  };

  function progressActionBtnClass(targetStatus) {
    var s = targetStatus == null ? "" : String(targetStatus).trim();
    if (!s) return "rms-progress-btn rms-progress-btn--black";
    if (/_failed$/.test(s) || s === "offer_dropped" || s === "onboarding_lost") {
      return "rms-progress-btn rms-progress-btn--red";
    }
    if (PIPELINE_NEXT_OP_COL3[s] || /_abandoned$/.test(s)) {
      return "rms-progress-btn rms-progress-btn--black";
    }
    return "rms-progress-btn rms-progress-btn--blue";
  }

  function progressOptionsForCorrection(currentStatus) {
    var cur = normalizeProgressStatus(currentStatus);
    return APPLICATION_PROGRESS_STATUSES.filter(function (s) { return s !== cur; }).map(function (s) {
      return { value: s, label: progressLabel(s) };
    });
  }

  function isPipelineEligible(app) {
    if (!app) return false;
    var recv = app.receive_status == null ? "pending" : String(app.receive_status).trim();
    var dr = app.delivery_review_status == null ? "pending" : String(app.delivery_review_status).trim();
    return recv === "accepted" && dr === "passed";
  }

  function isApplicationTerminal(status) {
    var s = status == null ? "" : String(status).trim();
    return !!PROGRESS_TERMINAL[s] || s === "rejected" || s === "withdrawn";
  }

  /** Pipeline 列表是否展示该推荐（activeOnly 时仅活动态；否则含终态）。 */
  function isPipelineListRow(app, activeOnly) {
    if (!app) return false;
    if (isPipelineEligible(app)) {
      if (activeOnly && isApplicationTerminal(app.status)) return false;
      return true;
    }
    if (activeOnly) return false;
    return filterProgressStatus(app.status) === "internal_screen_failed";
  }

  function matchTextFilter(label, query) {
    var q = (query || "").trim().toLowerCase();
    if (!q) return true;
    return String(label || "").toLowerCase().indexOf(q) !== -1;
  }

  function parseDateOnly(str) {
    if (!str) return null;
    var s = String(str).trim().slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
    return s;
  }

  function formatRmsDate(str) {
    return parseDateOnly(str) || "—";
  }

  function resolveApplicationClientId(app, getJobs) {
    if (app && app.client_id != null && app.client_id !== "") return Number(app.client_id);
    var job = app && app.job_id != null && app.job_id !== "" ? jobById(getJobs(), app.job_id) : null;
    if (job && job.client_id != null && job.client_id !== "") return Number(job.client_id);
    return null;
  }

  function filterPipelineApplications(items, options) {
    options = options || {};
    var filters = options.filters || options;
    var getJobs = options.getJobs || function () { return []; };
    var getCandidates = options.getCandidates || function () { return []; };
    var getUsers = options.getUsers || function () { return []; };
    var clientNameById = options.clientNameById || function () { return ""; };
    var helpers = createAppDisplayHelpers({
      getJobs: getJobs,
      getCandidates: getCandidates,
      getUsers: getUsers,
      clientNameById: clientNameById,
    });
    var list = Array.isArray(items) ? items : [];
    var out = [];
    var activeOnly = filters.activeOnly !== false;
    for (var i = 0; i < list.length; i++) {
      var a = list[i];
      if (!isPipelineListRow(a, activeOnly)) continue;
      if (filters.client_id !== "" && filters.client_id != null) {
        var wantClient = Number(filters.client_id);
        var appClient = resolveApplicationClientId(a, getJobs);
        if (appClient !== wantClient) continue;
      }
      if (filters.job_id !== "" && filters.job_id != null) {
        if (Number(a.job_id) !== Number(filters.job_id)) continue;
      }
      var statusList = filters.statuses;
      if (!Array.isArray(statusList)) {
        statusList = filters.status !== "" && filters.status != null ? [filters.status] : [];
      }
      var selectedStatuses = [];
      for (var si = 0; si < statusList.length; si++) {
        var sv = String(statusList[si] == null ? "" : statusList[si]).trim();
        if (sv) selectedStatuses.push(sv);
      }
      if (selectedStatuses.length && !statusMatchesFilter(a.status, selectedStatuses)) continue;
      var recDate = parseDateOnly(a.recommended_at);
      var from = parseDateOnly(filters.date_from);
      var to = parseDateOnly(filters.date_to);
      if (from && (!recDate || recDate < from)) continue;
      if (to && (!recDate || recDate > to)) continue;
      if (!matchTextFilter(helpers.appJobLocation(a), filters.city)) continue;
      if (!matchTextFilter(helpers.appDeliveryLabel(a), filters.delivery)) continue;
      if (!matchTextFilter(helpers.appRecommenderLabel(a), filters.recommender)) continue;
      out.push(a);
    }
    return out;
  }

  function jobById(jobs, jobId) {
    var id = Number(jobId);
    for (var i = 0; i < jobs.length; i++) {
      if (Number(jobs[i].id) === id) return jobs[i];
    }
    return null;
  }

  function candidateById(candidates, candidateId) {
    var id = Number(candidateId);
    for (var i = 0; i < candidates.length; i++) {
      if (Number(candidates[i].id) === id) return candidates[i];
    }
    return null;
  }

  function textValue(value) {
    return String(value == null ? "" : value).trim();
  }

  function normalizeUserLabel(label) {
    var raw = textValue(label);
    if (!raw) return "";
    var sep = raw.indexOf(" · ");
    if (sep > 0) return raw.slice(0, sep).trim();
    return raw;
  }

  function userLabelById(users, userId) {
    if (userId == null || userId === "") return "—";
    var id = Number(userId);
    for (var i = 0; i < users.length; i++) {
      if (Number(users[i].id) === id) {
        var dn = textValue(users[i].display_name);
        var un = textValue(users[i].username);
        return dn || un || String(id);
      }
    }
    return "#" + userId;
  }

  var DELIVERY_REVIEW_STATUS_LABELS = {
    pending: "待内审",
    passed: "内审通过",
    failed: "内审失败",
  };

  function createAppDisplayHelpers(options) {
    options = options || {};
    var getJobs = options.getJobs || function () { return []; };
    var getCandidates = options.getCandidates || function () { return []; };
    var getUsers = options.getUsers || function () { return []; };
    var clientNameById = options.clientNameById || function () { return ""; };
    var labelJob = options.labelJob || function (id) { return "#" + id; };

    return {
      appCandidateName: function (a) {
        var direct = textValue(a && a.candidate_name);
        if (direct) return direct;
        if (!a || a.candidate_id == null || a.candidate_id === "") return "—";
        var c = candidateById(getCandidates(), a.candidate_id);
        var candidateName = textValue(c && c.name);
        if (candidateName) return candidateName;
        return "#" + a.candidate_id;
      },
      appClientName: function (a) {
        var direct = textValue(a && a.client_name);
        if (direct) return direct;
        var job = a && a.job_id != null && a.job_id !== "" ? jobById(getJobs(), a.job_id) : null;
        var jobClientName = textValue(job && job.client_name);
        if (jobClientName) return jobClientName;
        if (job && job.client_id != null && job.client_id !== "") {
          var fromJobClient = textValue(clientNameById(job.client_id));
          if (fromJobClient) return fromJobClient;
        }
        if (a && a.client_id != null && a.client_id !== "") {
          var fromClient = textValue(clientNameById(a.client_id));
          if (fromClient) return fromClient;
          return "#" + a.client_id;
        }
        return "—";
      },
      appJobTitle: function (a) {
        var direct = textValue(a && a.job_title);
        if (direct) return direct;
        if (!a || a.job_id == null || a.job_id === "") return "—";
        var job = jobById(getJobs(), a.job_id);
        var jobTitle = textValue(job && job.title);
        if (jobTitle) return jobTitle;
        var labeled = textValue(labelJob(a.job_id));
        return labeled || "—";
      },
      appJobLocation: function (a) {
        var direct = textValue(a && a.job_location);
        if (direct) return direct;
        if (!a || a.job_id == null || a.job_id === "") return "—";
        var job = jobById(getJobs(), a.job_id);
        var jobLocation = textValue(job && job.location);
        if (jobLocation) return jobLocation;
        return "—";
      },
      appRecommenderLabel: function (a) {
        var direct = normalizeUserLabel(a && a.recommended_by_name);
        if (direct) return direct;
        return userLabelById(getUsers(), a && a.recommended_by);
      },
      appDeliveryLabel: function (a) {
        var direct = normalizeUserLabel(a && a.delivery_owner_label);
        if (direct) return direct;

        var job = a && a.job_id != null && a.job_id !== "" ? jobById(getJobs(), a.job_id) : null;
        var jobDeliveryLabel = normalizeUserLabel(job && job.delivery_owner_label);
        if (jobDeliveryLabel) return jobDeliveryLabel;
        if (job && job.delivery_owner_user_id != null && job.delivery_owner_user_id !== "") {
          return userLabelById(getUsers(), job.delivery_owner_user_id);
        }
        if (a && a.delivery_owner_user_id != null && a.delivery_owner_user_id !== "") {
          return userLabelById(getUsers(), a.delivery_owner_user_id);
        }
        return "—";
      },
    };
  }

  global.RmsApplicationLabels = {
    RECEIVE_STATUS_LABELS: RECEIVE_STATUS_LABELS,
    DELIVERY_REVIEW_STATUS_LABELS: DELIVERY_REVIEW_STATUS_LABELS,
    APPLICATION_PROGRESS_LABELS: APPLICATION_PROGRESS_LABELS,
    APPLICATION_PROGRESS_STATUSES: APPLICATION_PROGRESS_STATUSES,
    ALLOWED_PROGRESS_TRANSITIONS: ALLOWED_PROGRESS_TRANSITIONS,
    progressLabel: progressLabel,
    receiveLabel: receiveLabel,
    deliveryReviewLabel: deliveryReviewLabel,
    offerApprovalPendingHint: offerApprovalPendingHint,
    deriveProtectionStatus: deriveProtectionStatus,
    progressTransitionsFor: progressTransitionsFor,
    progressActionBtnClass: progressActionBtnClass,
    progressOptionsForCorrection: progressOptionsForCorrection,
    normalizeProgressStatus: normalizeProgressStatus,
    parseDateOnly: parseDateOnly,
    formatRmsDate: formatRmsDate,
    jobById: jobById,
    candidateById: candidateById,
    userLabelById: userLabelById,
    createAppDisplayHelpers: createAppDisplayHelpers,
    isPipelineEligible: isPipelineEligible,
    isPipelineListRow: isPipelineListRow,
    isApplicationTerminal: isApplicationTerminal,
    filterPipelineApplications: filterPipelineApplications,
    filterProgressStatus: filterProgressStatus,
    statusMatchesFilter: statusMatchesFilter,
    isProgressTerminal: function (status) {
      return !!PROGRESS_TERMINAL[status];
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
