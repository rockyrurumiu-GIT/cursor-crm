/**
 * RMS delivery review tab: list, modal, submit (Phase R3-C split).
 */
(function (global) {
  "use strict";

  function createDeliveryReviewState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var activeTab = deps.activeTab;
    var scheduleCandidatesTableColumnFit = deps.scheduleCandidatesTableColumnFit;
    var rmsRequest = deps.rmsRequest;
    var workflowMessageForStatus = deps.workflowMessageForStatus;
    var Labels = deps.Labels;
    var toast = deps.toast;
    var loadApplications = deps.loadApplications;
    var CandidateReport = deps.RmsCandidateReport || {};

    var deliveryReviewState = reactive({ loading: false, items: [], error: "" });
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
