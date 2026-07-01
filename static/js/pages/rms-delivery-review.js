/**
 * RMS delivery review tab: list, modal, submit (Phase R3-C split).
 */
(function (global) {
  "use strict";

  function createDeliveryReviewState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var watch = deps.watch;
    var activeTab = deps.activeTab;
    var scheduleCandidatesTableColumnFit = deps.scheduleCandidatesTableColumnFit;
    var rmsRequest = deps.rmsRequest;
    var workflowMessageForStatus = deps.workflowMessageForStatus;
    var Labels = deps.Labels;
    var toast = deps.toast;
    var loadApplications = deps.loadApplications;
    var jobs = deps.jobs;
    var CandidateReport = deps.RmsCandidateReport || {};
    var appCandidateName = deps.appCandidateName || function () { return ""; };
    var appClientName = deps.appClientName || function () { return ""; };
    var appJobTitle = deps.appJobTitle || function () { return ""; };
    var Core = global.CrmRmsCore || {};

    var deliveryReviewState = reactive({ loading: false, items: [], error: "" });
    var deliveryReviewFilterPanelExpanded = ref(false);
    var deliveryReviewKeyword = ref("");
    var deliveryReviewFilter = reactive({
      recommended_by: "",
    });
    var deliveryReviewScrollWrap = ref(null);

    var deliveryReviewRecommenderFilterOptions = computed(function () {
      var users = jobs && jobs.userOptions ? jobs.userOptions.value : [];
      return Core.buildRecommenderFilterOptions
        ? Core.buildRecommenderFilterOptions(deliveryReviewState.items, users, function (a) { return a.recommended_by; })
        : [];
    });

    var filteredDeliveryReviewItems = computed(function () {
      var rows = deliveryReviewState.items.slice();
      if (deliveryReviewFilter.recommended_by !== "" && deliveryReviewFilter.recommended_by != null) {
        var wantRec = Number(deliveryReviewFilter.recommended_by);
        rows = rows.filter(function (a) {
          return Number(a.recommended_by) === wantRec;
        });
      }
      var q = (deliveryReviewKeyword.value || "").trim().toLowerCase();
      if (!q) return rows;
      return rows.filter(function (a) {
        var haystack = [
          appCandidateName(a),
          appClientName(a),
          appJobTitle(a),
          a.recommender_label,
        ].join(" ").toLowerCase();
        return haystack.indexOf(q) !== -1;
      });
    });

    var deliveryReviewPagination = Core.createListPagination
      ? Core.createListPagination({
          ref: ref,
          computed: computed,
          watch: watch,
          filteredRows: filteredDeliveryReviewItems,
          prefix: "deliveryReview",
          pageSize: Core.RMS_LIST_PAGE_SIZE || 8,
        })
      : {
          pagedRows: filteredDeliveryReviewItems,
          deliveryReviewCurrentPage: ref(1),
          deliveryReviewTotalPages: computed(function () { return 1; }),
          deliveryReviewPageNumbers: computed(function () { return [1]; }),
          deliveryReviewGoPage: function () {},
          pageSize: Core.RMS_LIST_PAGE_SIZE || 8,
        };

    function scrollDeliveryReviewToTop() {
      var el = deliveryReviewScrollWrap.value;
      if (el) el.scrollTop = 0;
    }

    function resetDeliveryReviewFilter() {
      deliveryReviewKeyword.value = "";
      deliveryReviewFilter.recommended_by = "";
    }

    var reviewModal = ref(null);
    var reviewFailPromptOpen = ref(false);
    var reviewModalSaving = ref(false);
    var reviewModalError = ref("");

    async function rmsRequestWorkflow(method, url, body, endpoint) {
      var r = await rmsRequest(method, url, body);
      if (!r.ok && r.status === 404) {
        return { ok: false, status: 404, message: workflowMessageForStatus(404, "", endpoint) };
      }
      return r;
    }

    var deliveryReviewApi = CandidateReport.createDeliveryReviewApi
      ? CandidateReport.createDeliveryReviewApi(function (method, url, body) {
          return rmsRequestWorkflow(method, url, body, "delivery-review");
        })
      : null;

    function receiveLabel(status) {
      return Labels.receiveLabel ? Labels.receiveLabel(status) : status;
    }

    function deliveryReviewLabel(status) {
      return Labels.deliveryReviewLabel ? Labels.deliveryReviewLabel(status) : status;
    }

    function protectionLabel(status) {
      return Labels.deriveProtectionStatus ? Labels.deriveProtectionStatus(status) : "—";
    }

    async function loadDeliveryReview() {
      try {
        if (deliveryReviewApi) {
          await deliveryReviewApi.loadDeliveryReview(deliveryReviewState);
        }
      } finally {
        if (activeTab.value === "deliveryReview") {
          scheduleCandidatesTableColumnFit();
        }
      }
    }

    function openDeliveryReviewModal(app) {
      reviewModalError.value = "";
      reviewFailPromptOpen.value = false;
      reviewModalSaving.value = false;
      reviewModal.value = app;
    }

    function closeDeliveryReviewModal() {
      reviewModal.value = null;
      reviewFailPromptOpen.value = false;
      reviewModalError.value = "";
      if (activeTab.value === "deliveryReview") {
        scheduleCandidatesTableColumnFit();
      }
    }

    async function submitDeliveryReview(result, note) {
      if (!reviewModal.value || !deliveryReviewApi) return;
      var trimmedNote = String(note == null ? "" : note).trim();
      if (result === "failed" && trimmedNote.length < 2) {
        reviewModalError.value = "内审失败须填写理由";
        return;
      }
      reviewModalSaving.value = true;
      reviewModalError.value = "";
      var r = await deliveryReviewApi.submitDeliveryReview(reviewModal.value.id, result, trimmedNote);
      reviewModalSaving.value = false;
      if (!r.ok) {
        reviewModalError.value = r.message;
        return;
      }
      var warnMsg = r.data && r.data.message;
      if (warnMsg) {
        toast(warnMsg, true);
        closeDeliveryReviewModal();
        await Promise.all([loadDeliveryReview(), loadApplications()]);
        return;
      }
      toast(result === "passed" ? "内审通过" : "内审失败", false);
      closeDeliveryReviewModal();
      await Promise.all([loadDeliveryReview(), loadApplications()]);
    }

    return {
      deliveryReviewState: deliveryReviewState,
      deliveryReviewFilterPanelExpanded: deliveryReviewFilterPanelExpanded,
      deliveryReviewKeyword: deliveryReviewKeyword,
      deliveryReviewFilter: deliveryReviewFilter,
      deliveryReviewRecommenderFilterOptions: deliveryReviewRecommenderFilterOptions,
      resetDeliveryReviewFilter: resetDeliveryReviewFilter,
      deliveryReviewScrollWrap: deliveryReviewScrollWrap,
      scrollDeliveryReviewToTop: scrollDeliveryReviewToTop,
      filteredDeliveryReviewItems: filteredDeliveryReviewItems,
      pagedDeliveryReviewItems: deliveryReviewPagination.pagedRows,
      deliveryReviewCurrentPage: deliveryReviewPagination.deliveryReviewCurrentPage || deliveryReviewPagination.currentPage,
      deliveryReviewTotalPages: deliveryReviewPagination.deliveryReviewTotalPages || deliveryReviewPagination.totalPages,
      deliveryReviewPageNumbers: deliveryReviewPagination.deliveryReviewPageNumbers || deliveryReviewPagination.pageNumbers,
      deliveryReviewGoPage: deliveryReviewPagination.deliveryReviewGoPage || deliveryReviewPagination.goPage,
      deliveryReviewPageSize: deliveryReviewPagination.pageSize,
      reviewModal: reviewModal,
      reviewFailPromptOpen: reviewFailPromptOpen,
      reviewModalSaving: reviewModalSaving,
      reviewModalError: reviewModalError,
      loadDeliveryReview: loadDeliveryReview,
      openDeliveryReviewModal: openDeliveryReviewModal,
      closeDeliveryReviewModal: closeDeliveryReviewModal,
      submitDeliveryReview: submitDeliveryReview,
      deliveryReviewLabel: deliveryReviewLabel,
      receiveLabel: receiveLabel,
      protectionLabel: protectionLabel,
    };
  }

  global.CrmRmsDeliveryReview = {
    createDeliveryReviewState: createDeliveryReviewState,
  };
})(typeof window !== "undefined" ? window : globalThis);
