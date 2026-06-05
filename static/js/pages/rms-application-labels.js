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
    scheduling_interview: "约面中",
    interview_scheduling_failed: "约面fail",
    pending_interview: "待面试",
    first_interview_passed: "一面通过",
    first_interview_failed: "一面fail",
    second_interview_passed: "二面通过",
    second_interview_failed: "二面fail",
    pending_offer: "待offer",
    offer_dropped: "drop offer",
    onboarding: "在途",
    onboarding_lost: "在途流失",
    hired: "已入职",
  };

  var LEGACY_PROGRESS_MAP = {
    recommended: "待内筛",
    screening: "待客筛",
    interview: "待面试",
    offer: "待offer",
    rejected: "已拒收",
    withdrawn: "已撤回",
  };

  var ALLOWED_PROGRESS_TRANSITIONS = {
    pending_internal_screen: ["internal_screen_failed", "pending_client_screen"],
    pending_client_screen: ["client_screen_failed", "scheduling_interview"],
    scheduling_interview: ["interview_scheduling_failed", "pending_interview"],
    pending_interview: ["first_interview_failed", "first_interview_passed"],
    first_interview_passed: ["second_interview_failed", "second_interview_passed"],
    second_interview_passed: ["pending_offer"],
    pending_offer: ["offer_dropped", "onboarding"],
    onboarding: ["onboarding_lost", "hired"],
  };

  var PROGRESS_TERMINAL = {
    internal_screen_failed: 1,
    client_screen_failed: 1,
    interview_scheduling_failed: 1,
    first_interview_failed: 1,
    second_interview_failed: 1,
    offer_dropped: 1,
    onboarding_lost: 1,
    hired: 1,
  };

  var PROTECTION_TERMINAL = {
    internal_screen_failed: 1,
    client_screen_failed: 1,
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
    return RECEIVE_STATUS_LABELS[status] || status || "—";
  }

  function deriveProtectionStatus(status) {
    if (PROTECTION_TERMINAL[status]) return "已终止";
    return "生效中";
  }

  function progressTransitionsFor(status) {
    return ALLOWED_PROGRESS_TRANSITIONS[status] || [];
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

  function userLabelById(users, userId) {
    if (userId == null || userId === "") return "—";
    var id = Number(userId);
    for (var i = 0; i < users.length; i++) {
      if (Number(users[i].id) === id) {
        var dn = (users[i].display_name || "").trim();
        var un = (users[i].username || "").trim();
        if (dn && un) return dn + " · " + un;
        return dn || un || String(id);
      }
    }
    return "#" + userId;
  }

  global.RmsApplicationLabels = {
    RECEIVE_STATUS_LABELS: RECEIVE_STATUS_LABELS,
    APPLICATION_PROGRESS_LABELS: APPLICATION_PROGRESS_LABELS,
    ALLOWED_PROGRESS_TRANSITIONS: ALLOWED_PROGRESS_TRANSITIONS,
    progressLabel: progressLabel,
    receiveLabel: receiveLabel,
    deriveProtectionStatus: deriveProtectionStatus,
    progressTransitionsFor: progressTransitionsFor,
    jobById: jobById,
    candidateById: candidateById,
    userLabelById: userLabelById,
    isProgressTerminal: function (status) {
      return !!PROGRESS_TERMINAL[status];
    },
  };
})(typeof window !== "undefined" ? window : globalThis);
