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

    var applicationsState = reactive({ loading: false, items: [], error: "" });
    var applicationsFilter = reactive({
      hired_unconverted_only: false,
    });

    var statusHistoryModal = ref(null);
    var statusHistoryLoading = ref(false);
    var statusHistoryError = ref("");
    var statusHistoryItems = ref([]);

    var applicationDetailModal = ref(null);
    var applicationDetailFailNote = ref("");
    var applicationDetailLoading = ref(false);

    var filteredApplications = computed(function () {
      var rows = applicationsState.items.slice();
      if (applicationsFilter.hired_unconverted_only) {
        rows = rows.filter(function (a) {
          return a.status === "hired" && !a.converted_to_roster_entry_id;
        });
      }
      return rows;
    });

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

    return {
      applicationsState: applicationsState,
      applicationsFilter: applicationsFilter,
      filteredApplications: filteredApplications,
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
