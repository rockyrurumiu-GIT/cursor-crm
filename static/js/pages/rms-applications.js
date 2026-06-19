/**
 * RMS applications tab (Phase R3-A split).
 */
(function (global) {
  "use strict";

  function createApplicationsState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var rmsRequest = deps.rmsRequest;
    var toast = deps.toast;
    var candidatesState = deps.candidatesState;
    var displaySalary = deps.displaySalary;
    var formatRmsDate = deps.formatRmsDate;
    var scheduleCandidatesTableColumnFit = deps.scheduleCandidatesTableColumnFit;
    var loadCandidates = deps.loadCandidates;
    var loadDeliveryReview = deps.loadDeliveryReview;
    var Labels = deps.Labels || {};
    var jobs = deps.jobs;
    var appCandidateName = deps.appCandidateName || function () { return ""; };
    var appClientName = deps.appClientName || function () { return ""; };
    var appJobTitle = deps.appJobTitle || function () { return ""; };
    var appJobLocation = deps.appJobLocation || function () { return ""; };
    var appRecommenderLabel = deps.appRecommenderLabel || function () { return ""; };
    var appDeliveryLabel = deps.appDeliveryLabel || function () { return ""; };

    var parseDateOnly = Labels.parseDateOnly || function () { return null; };
    var statusMatchesFilter = Labels.statusMatchesFilter || function () { return true; };
    var jobById = Labels.jobById || function () { return null; };

    var applicationFilterPanelExpanded = ref(false);
    var applicationsScrollWrap = ref(null);
    var applicationsState = reactive({ loading: false, items: [], error: "" });
    var applicationsFilter = reactive({
      keyword: "",
      client_id: "",
      job_id: "",
      statuses: [],
      date_from: "",
      date_to: "",
      hide_roster_converted: false,
    });

    var applicationProgressOptions = (Labels.APPLICATION_PROGRESS_STATUSES || []).map(function (s) {
      return {
        value: s,
        label: Labels.progressLabel ? Labels.progressLabel(s) : s,
      };
    });

    function applicationProgressLabel(status) {
      return Labels.progressLabel ? Labels.progressLabel(status) : status;
    }

    var applicationStatusDropdownOpen = ref(false);
    var applicationStatusDraft = ref([]);
    var applicationStatusFilterSummary = computed(function () {
      var sel = applicationsFilter.statuses || [];
      if (!sel.length) return "招聘进展";
      if (sel.length === 1) return applicationProgressLabel(sel[0]);
      return "已选" + sel.length + "项";
    });

    var statusHistoryModal = ref(null);
    var statusHistoryLoading = ref(false);
    var statusHistoryError = ref("");
    var statusHistoryItems = ref([]);

    var applicationDetailModal = ref(null);
    var applicationDetailFailNote = ref("");
    var applicationDetailLoading = ref(false);

    function resolveApplicationClientId(app) {
      if (app && app.client_id != null && app.client_id !== "") return Number(app.client_id);
      var jobList = jobs && jobs.jobsState ? jobs.jobsState.items : [];
      var job = app && app.job_id != null && app.job_id !== "" ? jobById(jobList, app.job_id) : null;
      if (job && job.client_id != null && job.client_id !== "") return Number(job.client_id);
      return null;
    }

    function matchesApplicationKeyword(app, keyword) {
      var q = (keyword || "").trim().toLowerCase();
      if (!q) return true;
      var haystack = [
        appCandidateName(app),
        appClientName(app),
        appJobTitle(app),
        appJobLocation(app),
        appRecommenderLabel(app),
        appDeliveryLabel(app),
      ].join(" ").toLowerCase();
      return haystack.indexOf(q) !== -1;
    }

    var filteredApplications = computed(function () {
      var rows = applicationsState.items.slice();
      if (applicationsFilter.hide_roster_converted) {
        rows = rows.filter(function (a) {
          return !a.converted_to_roster_entry_id;
        });
      }
      if (applicationsFilter.client_id !== "" && applicationsFilter.client_id != null) {
        var wantClient = Number(applicationsFilter.client_id);
        rows = rows.filter(function (a) {
          return resolveApplicationClientId(a) === wantClient;
        });
      }
      if (applicationsFilter.job_id !== "" && applicationsFilter.job_id != null) {
        var wantJob = Number(applicationsFilter.job_id);
        rows = rows.filter(function (a) {
          return Number(a.job_id) === wantJob;
        });
      }
      if ((applicationsFilter.statuses || []).length) {
        var selectedStatuses = applicationsFilter.statuses;
        rows = rows.filter(function (a) {
          return statusMatchesFilter(a.status, selectedStatuses);
        });
      }
      var from = parseDateOnly(applicationsFilter.date_from);
      var to = parseDateOnly(applicationsFilter.date_to);
      if (from || to) {
        rows = rows.filter(function (a) {
          var recDate = parseDateOnly(a.recommended_at);
          if (from && (!recDate || recDate < from)) return false;
          if (to && (!recDate || recDate > to)) return false;
          return true;
        });
      }
      var keyword = applicationsFilter.keyword;
      if ((keyword || "").trim()) {
        rows = rows.filter(function (a) {
          return matchesApplicationKeyword(a, keyword);
        });
      }
      return rows;
    });

    function resetApplicationFilter() {
      applicationsFilter.keyword = "";
      applicationsFilter.client_id = "";
      applicationsFilter.job_id = "";
      applicationsFilter.statuses.splice(0, applicationsFilter.statuses.length);
      applicationStatusDraft.value = [];
      applicationStatusDropdownOpen.value = false;
      applicationsFilter.date_from = "";
      applicationsFilter.date_to = "";
      applicationsFilter.hide_roster_converted = false;
    }

    function toggleApplicationStatusDropdown() {
      if (!applicationStatusDropdownOpen.value) {
        applicationStatusDraft.value = (applicationsFilter.statuses || []).slice();
      }
      applicationStatusDropdownOpen.value = !applicationStatusDropdownOpen.value;
    }

    function toggleApplicationStatusDraft(value) {
      var list = applicationStatusDraft.value;
      var idx = list.indexOf(value);
      if (idx >= 0) list.splice(idx, 1);
      else list.push(value);
    }

    function clearApplicationStatusDraft() {
      applicationStatusDraft.value = [];
    }

    function applyApplicationStatusFilter() {
      var next = applicationStatusDraft.value.slice();
      applicationsFilter.statuses.splice(0, applicationsFilter.statuses.length);
      next.forEach(function (v) {
        applicationsFilter.statuses.push(v);
      });
      applicationStatusDropdownOpen.value = false;
    }

    function candidateForApp(a) {
      if (!a || a.candidate_id == null || a.candidate_id === "") return null;
      var cid = Number(a.candidate_id);
      return candidatesState.items.find(function (c) {
        return Number(c.id) === cid;
      }) || null;
    }

    function appCandidateAge(a) {
      var c = candidateForApp(a);
      return c && c.age ? c.age : "—";
    }

    function appCandidateWorkYears(a) {
      var c = candidateForApp(a);
      return c && c.work_years ? c.work_years : "—";
    }

    function appCandidateCurrentSalary(a) {
      var c = candidateForApp(a);
      return c ? displaySalary(c.current_salary) : "—";
    }

    function appCandidateExpectedSalary(a) {
      var c = candidateForApp(a);
      return c ? displaySalary(c.expected_salary) : "—";
    }

    function appCandidateAvailableDate(a) {
      var c = candidateForApp(a);
      return c ? formatRmsDate(c.available_date) : "—";
    }

    function appCandidateEducation(a) {
      var c = candidateForApp(a);
      return c && c.education_level ? c.education_level : "—";
    }

    function resumeViewUrlById(resumeId) {
      if (resumeId == null || resumeId === "") return "#";
      return "/api/rms/resumes/" + resumeId + "/view";
    }

    function resumeCanViewByName(fileName) {
      return /\.(pdf|txt|rtf)$/i.test(String(fileName || ""));
    }

    async function loadApplications() {
      applicationsState.loading = true;
      applicationsState.error = "";
      try {
        var r = await rmsRequest("GET", "/api/rms/applications");
        if (!r.ok) {
          applicationsState.items = [];
          applicationsState.error = r.message;
          return;
        }
        applicationsState.items = Array.isArray(r.data) ? r.data : [];
      } finally {
        applicationsState.loading = false;
        scheduleCandidatesTableColumnFit();
      }
    }

    function deliveryReviewFailNoteFromHistory(items) {
      if (!Array.isArray(items)) return "";
      for (var i = 0; i < items.length; i++) {
        var h = items[i];
        if (h && h.reason === "delivery_review_failed") {
          return String(h.note || "").trim();
        }
      }
      return "";
    }

    async function openApplicationDetailModal(app) {
      if (!app) return;
      applicationDetailModal.value = app;
      applicationDetailFailNote.value = "";
      applicationDetailLoading.value = false;
      var dr = String(app.delivery_review_status == null ? "" : app.delivery_review_status).trim();
      var needsFailNote = dr === "failed" || app.status === "internal_screen_failed";
      if (!needsFailNote || app.id == null) return;
      applicationDetailLoading.value = true;
      var r = await rmsRequest("GET", "/api/rms/applications/" + app.id + "/status-history");
      applicationDetailLoading.value = false;
      if (r.ok) {
        applicationDetailFailNote.value = deliveryReviewFailNoteFromHistory(r.data);
      }
    }

    function closeApplicationDetailModal() {
      applicationDetailModal.value = null;
      applicationDetailFailNote.value = "";
      applicationDetailLoading.value = false;
    }

    function closeStatusHistoryModal() {
      statusHistoryModal.value = null;
      statusHistoryLoading.value = false;
      statusHistoryError.value = "";
      statusHistoryItems.value = [];
    }

    async function openStatusHistoryModal(app) {
      if (!app || app.id == null) return;
      statusHistoryModal.value = app;
      statusHistoryLoading.value = true;
      statusHistoryError.value = "";
      statusHistoryItems.value = [];
      var r = await rmsRequest("GET", "/api/rms/applications/" + app.id + "/status-history");
      statusHistoryLoading.value = false;
      if (!r.ok) {
        statusHistoryError.value = r.message || "加载状态历史失败";
        return;
      }
      statusHistoryItems.value = Array.isArray(r.data) ? r.data : [];
    }

    async function removeApplication(row) {
      var base = "/api/rms/applications/" + row.id;
      var r = await rmsRequest("DELETE", base);
      if (!r.ok && r.status === 405) {
        r = await rmsRequest("POST", base + "/delete");
      }
      if (!r.ok) {
        toast(r.message, true);
        return;
      }
      toast("已删除推荐记录", false);
      await Promise.all([loadApplications(), loadCandidates(), loadDeliveryReview()]);
    }

    function scrollApplicationsToTop() {
      var el = applicationsScrollWrap.value;
      if (el) el.scrollTop = 0;
    }

    return {
      applicationFilterPanelExpanded: applicationFilterPanelExpanded,
      applicationsScrollWrap: applicationsScrollWrap,
      scrollApplicationsToTop: scrollApplicationsToTop,
      applicationsState: applicationsState,
      applicationsFilter: applicationsFilter,
      applicationProgressOptions: applicationProgressOptions,
      applicationStatusDropdownOpen: applicationStatusDropdownOpen,
      applicationStatusDraft: applicationStatusDraft,
      applicationStatusFilterSummary: applicationStatusFilterSummary,
      toggleApplicationStatusDropdown: toggleApplicationStatusDropdown,
      toggleApplicationStatusDraft: toggleApplicationStatusDraft,
      clearApplicationStatusDraft: clearApplicationStatusDraft,
      applyApplicationStatusFilter: applyApplicationStatusFilter,
      filteredApplications: filteredApplications,
      resetApplicationFilter: resetApplicationFilter,
      applicationDetailModal: applicationDetailModal,
      applicationDetailFailNote: applicationDetailFailNote,
      applicationDetailLoading: applicationDetailLoading,
      statusHistoryModal: statusHistoryModal,
      statusHistoryLoading: statusHistoryLoading,
      statusHistoryError: statusHistoryError,
      statusHistoryItems: statusHistoryItems,
      loadApplications: loadApplications,
      openApplicationDetailModal: openApplicationDetailModal,
      closeApplicationDetailModal: closeApplicationDetailModal,
      openStatusHistoryModal: openStatusHistoryModal,
      closeStatusHistoryModal: closeStatusHistoryModal,
      removeApplication: removeApplication,
      appCandidateAge: appCandidateAge,
      appCandidateWorkYears: appCandidateWorkYears,
      appCandidateCurrentSalary: appCandidateCurrentSalary,
      appCandidateExpectedSalary: appCandidateExpectedSalary,
      appCandidateAvailableDate: appCandidateAvailableDate,
      appCandidateEducation: appCandidateEducation,
      resumeViewUrlById: resumeViewUrlById,
      resumeCanViewByName: resumeCanViewByName,
    };
  }

  global.CrmRmsApplications = {
    createApplicationsState: createApplicationsState,
  };
})(typeof window !== "undefined" ? window : globalThis);
