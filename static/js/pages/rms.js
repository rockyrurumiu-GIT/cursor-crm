/**
 * RMS module page shell.
 * Requires: Vue 3 CDN, crm-api.js, rms-core.js, rms-application-labels.js,
 * rms-candidate-report.js, rms-jobs.js, rms-candidates.js,
 * rms-applications.js, rms-pipeline.js, rms-delivery-review.js,
 * rms-roster-conversion.js.
 */
(function () {
  "use strict";

  const Labels = window.RmsApplicationLabels || {};
  const Core = window.CrmRmsCore || {};

  const rmsRequest = Core.rmsRequest ? Core.rmsRequest.bind(Core) : async function () {
    return { ok: false, status: 0, message: "CrmRmsCore 未加载" };
  };
  const authHeaders = Core.authHeaders ? Core.authHeaders.bind(Core) : function () { return {}; };
  const messageForStatus = Core.messageForStatus ? Core.messageForStatus.bind(Core) : function (s) { return String(s); };
  const workflowMessageForStatus = Core.workflowMessageForStatus ? Core.workflowMessageForStatus.bind(Core) : messageForStatus;
  const formatSalaryThousands = Core.formatSalaryThousands ? Core.formatSalaryThousands.bind(Core) : function (s) { return String(s || ""); };
  const stripSalaryCommas = Core.stripSalaryCommas ? Core.stripSalaryCommas.bind(Core) : function (s) { return String(s || ""); };
  const fuzzyMatch = Core.fuzzyMatch ? Core.fuzzyMatch.bind(Core) : function () { return true; };
  const showValidationPrompt = Core.showValidationPrompt ? Core.showValidationPrompt.bind(Core) : function (m) { return String(m || ""); };
  const showRmsBootError = Core.showRmsBootError ? Core.showRmsBootError.bind(Core) : function () {};

  const EDUCATION_OPTIONS = ["重本", "统本", "专科", "硕士", "留学生", "民教网", "其他"];
  const GENDER_OPTIONS = ["男", "女"];
  const SOURCE_OPTIONS = ["内部RMS", "Boss", "linkedin", "猎聘", "内推", "挂靠", "外协", "其他"];
  const MARITAL_OPTIONS = ["未婚", "已婚"];
  const PHONE_RE = /^1\d{10}$/;

  const CANDIDATE_DUPLICATE_DETAIL = "人选已存在系统中";
  const CANDIDATE_DUPLICATE_PARSE_HINT = "系统中已存在该人选";

  function isCandidateDuplicateError(r) {
    return !!(r && r.status === 409 && String(r.detail || "") === CANDIDATE_DUPLICATE_DETAIL);
  }

  function userFacingRmsError(r) {
    if (!r) return "操作失败";
    const detail = String(r.detail || "").trim();
    if (
      detail &&
      (detail.indexOf("请填写") === 0 ||
        detail.indexOf("请选择") === 0 ||
        detail.indexOf("请") === 0 ||
        detail.indexOf("手机号") >= 0 ||
        detail === CANDIDATE_DUPLICATE_DETAIL)
    ) {
      return detail;
    }
    return r.message || "操作失败";
  }

  function showCandidateDuplicateDialog(message) {
    var text = String(message || "").trim() || CANDIDATE_DUPLICATE_DETAIL;
    return new Promise(function (resolve) {
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        document.removeEventListener("keydown", onKeyDown, true);
        if (overlay && overlay.parentNode) {
          overlay.parentNode.removeChild(overlay);
        }
        resolve();
      }
      function onKeyDown(e) {
        if (e.key !== "Escape") return;
        e.preventDefault();
        e.stopPropagation();
        finish();
      }
      var overlay = document.createElement("div");
      overlay.className = "crm-esc-modal fixed inset-0 bg-black/40 flex items-center justify-center p-4";
      overlay.style.zIndex = "10000";
      var panel = document.createElement("div");
      panel.className = "bg-white rounded-lg shadow-xl w-full max-w-md p-4 sm:p-5";
      var h3 = document.createElement("h3");
      h3.className = "font-semibold text-lg text-gray-800 mb-3";
      h3.textContent = text;
      var pTarget = document.createElement("p");
      pTarget.className = "text-sm text-gray-600 mb-4";
      pTarget.textContent = text;
      var actions = document.createElement("div");
      actions.className = "flex gap-2";
      var confirmBtn = document.createElement("button");
      confirmBtn.type = "button";
      confirmBtn.className =
        "flex-1 py-2 rounded-md bg-[#0969da] text-white text-sm font-medium hover:bg-[#0550ae]";
      confirmBtn.textContent = "确定";
      actions.appendChild(confirmBtn);
      panel.appendChild(h3);
      panel.appendChild(pTarget);
      panel.appendChild(actions);
      overlay.appendChild(panel);
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) finish();
      });
      confirmBtn.addEventListener("click", finish);
      document.addEventListener("keydown", onKeyDown, true);
      document.body.appendChild(overlay);
    });
  }

  if (typeof Vue === "undefined" || !Vue.createApp) {
    showRmsBootError("页面依赖 Vue 未能加载，请刷新后重试。");
    return;
  }

  const { createApp, ref, reactive, computed, watch, onMounted, nextTick } = Vue;

  try {
  createApp({
    setup() {
      const activeTab = ref("jobs");
      const viewMode = ref(null);
      const me = ref({ user: { id: null }, permissions: [] });

      const modal = ref(null);
      const modalError = ref("");
      const modalSaving = ref(false);
      const isSuper = computed(function () {
        const roles = me.value.roles || [];
        return !!me.value.is_super || roles.indexOf("SUPER_ADMIN") !== -1;
      });
      function hasPermission(code) {
        return (me.value.permissions || []).indexOf(code) !== -1;
      }

      const jobs = window.CrmRmsJobs && window.CrmRmsJobs.createJobsState
        ? window.CrmRmsJobs.createJobsState({
            ref: ref,
            reactive: reactive,
            computed: computed,
            nextTick: nextTick,
            modal: modal,
            modalError: modalError,
            modalSaving: modalSaving,
            me: me,
            toast: toast,
          })
        : {};

      const canWriteJobs = computed(function () {
        return hasPermission("rms.jobs.write");
      });
      const canDeleteJobs = computed(function () {
        return hasPermission("rms.jobs.delete");
      });
      const canWriteCandidates = computed(function () {
        return hasPermission("rms.candidates.write");
      });
      const canDeleteCandidates = computed(function () {
        return hasPermission("rms.candidates.delete");
      });
      const canWriteApplications = computed(function () {
        return hasPermission("rms.applications.write");
      });
      const canReadApplications = computed(function () {
        return hasPermission("rms.applications.read");
      });
      const canUseRmsDeliveryOpsTabs = computed(function () {
        if (me.value.rms_delivery_ops_tabs != null) {
          return !!me.value.rms_delivery_ops_tabs;
        }
        return isSuper.value || hasPermission("rms.applications.write");
      });
      const canDeleteApplications = computed(function () {
        return hasPermission("rms.applications.delete");
      });
      const canReadCandidates = computed(function () {
        return hasPermission("rms.candidates.read");
      });
      const canConvertToRoster = computed(function () {
        return hasPermission("rms.applications.write") && hasPermission("delivery.roster.write");
      });

      const modalTitle = computed(function () {
        if (modal.value === "job") return jobs.jobModalTitle.value;
        if (modal.value === "candidate") return candidates.candidateModalTitle.value;
        return "";
      });

      const modalCloseLabel = computed(function () {
        if (modal.value === "job" && jobs.jobModalReadonly.value) return "关闭";
        return "取消";
      });

      const modalShowSave = computed(function () {
        if (!modal.value) return false;
        if (modal.value === "job") return jobs.jobModalShowSave.value;
        if (modal.value === "candidate") return candidates.candidateModalShowSave.value;
        return true;
      });

      const clientNameByIdMap = computed(function () {
        const m = {};
        jobs.clientOptions.value.forEach(function (c) {
          m[c.id] = c.name || "";
        });
        jobs.jobsState.items.forEach(function (j) {
          if (j.client_id != null && j.client_name) {
            m[j.client_id] = j.client_name;
          }
        });
        return m;
      });

      function clientNameById(clientId) {
        return clientNameByIdMap.value[clientId] || "";
      }

      const candidates = window.CrmRmsCandidates && window.CrmRmsCandidates.createCandidatesState
        ? window.CrmRmsCandidates.createCandidatesState({
            ref: ref,
            reactive: reactive,
            computed: computed,
            watch: watch,
            nextTick: nextTick,
            modal: modal,
            modalError: modalError,
            modalSaving: modalSaving,
            toast: toast,
            jobs: jobs,
            activeTab: activeTab,
            viewMode: viewMode,
            clientNameById: clientNameById,
            Labels: Labels,
            PHONE_RE: PHONE_RE,
            isCandidateDuplicateError: isCandidateDuplicateError,
            userFacingRmsError: userFacingRmsError,
            showCandidateDuplicateDialog: showCandidateDuplicateDialog,
          })
        : {};

      // HC-R2-11: shell internal lexical aliases
      const candidatesState = candidates.candidatesState;
      const loadCandidates = candidates.loadCandidates;
      const scheduleCandidatesTableColumnFit = candidates.scheduleCandidatesTableColumnFit;
      const labelCandidate = candidates.labelCandidate;
      const candidateNameById = candidates.candidateNameById;
      const displayCandidateContact = candidates.displayCandidateContact;
      const displaySalary = candidates.displaySalary;
      const resumeViewUrl = candidates.resumeViewUrl;
      const resumeCanView = candidates.resumeCanView;
      const candidateParseSummaryFields = candidates.candidateParseSummaryFields;
      const candidateParseSummaryEmpty = candidates.candidateParseSummaryEmpty;
      const candidateParseSummaryValue = candidates.candidateParseSummaryValue;

      function formatRmsDate(value) {
        return Labels.formatRmsDate ? Labels.formatRmsDate(value) : (value || "—");
      }

      function progressActionBtnClass(status) {
        return Labels.progressActionBtnClass
          ? Labels.progressActionBtnClass(status)
          : "rms-progress-btn rms-progress-btn--blue";
      }

      function offerApprovalPendingHint(app) {
        if (!app || app.status !== "offer_approval_pending") return "";
        var node = String(app.offer_current_approval_node_label == null ? "" : app.offer_current_approval_node_label).trim();
        var approver = String(app.offer_pending_approver_label == null ? "" : app.offer_pending_approver_label).trim();
        if (node && approver) return node + " · " + approver;
        if (node || approver) return node || approver;
        return "暂无审批信息";
      }

      const appDisplay = Labels.createAppDisplayHelpers
        ? Labels.createAppDisplayHelpers({
            getJobs: function () { return jobs.jobsState.items; },
            getCandidates: function () { return candidatesState.items; },
            getUsers: function () { return jobs.userOptions.value; },
            clientNameById: clientNameById,
            labelJob: jobs.labelJob,
          })
        : {};
      const appCandidateName = appDisplay.appCandidateName || function () { return "—"; };
      const appClientName = appDisplay.appClientName || function () { return "—"; };
      const appJobTitle = appDisplay.appJobTitle || function () { return "—"; };
      const appJobLocation = appDisplay.appJobLocation || function () { return "—"; };
      const appDeliveryLabel = appDisplay.appDeliveryLabel || function () { return "—"; };
      const appRecommenderLabel = appDisplay.appRecommenderLabel || function () { return "—"; };

      async function loadMe() {
        try {
          const data = await window.crmApi.get("/api/me");
          me.value = data;
          if (jobs.applyDefaultOwnerFromMe) jobs.applyDefaultOwnerFromMe();
        } catch (e) {
          /* page still usable; owner_user_id manual */
        }
      }

      function toast(msg, isError) {
        if (window.crmToast) {
          if (isError && window.crmToast.error) window.crmToast.error(msg);
          else if (window.crmToast.success) window.crmToast.success(msg);
          else window.crmToast.show(msg);
        } else {
          alert(msg);
        }
      }

      var loadDeliveryReviewBridge = async function () {};

      if (!window.CrmRmsApplications || typeof window.CrmRmsApplications.createApplicationsState !== "function") {
        showRmsBootError("RMS 推荐记录模块未加载，请刷新后重试。");
        return {};
      }
      const applications = window.CrmRmsApplications.createApplicationsState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        rmsRequest: rmsRequest,
        toast: toast,
        Labels: Labels,
        jobs: jobs,
        candidatesState: candidatesState,
        displaySalary: displaySalary,
        formatRmsDate: formatRmsDate,
        scheduleCandidatesTableColumnFit: scheduleCandidatesTableColumnFit,
        loadCandidates: loadCandidates,
        loadDeliveryReview: function () { return loadDeliveryReviewBridge.apply(null, arguments); },
        appCandidateName: appCandidateName,
        appClientName: appClientName,
        appJobTitle: appJobTitle,
        appJobLocation: appJobLocation,
        appRecommenderLabel: appRecommenderLabel,
        appDeliveryLabel: appDeliveryLabel,
      });
      const applicationsState = applications.applicationsState;
      const loadApplications = applications.loadApplications;
      if (!applicationsState || !loadApplications) {
        showRmsBootError("RMS 推荐记录状态初始化失败，请刷新后重试。");
        return {};
      }

      if (!window.CrmRmsPipeline || typeof window.CrmRmsPipeline.createPipelineState !== "function") {
        showRmsBootError("RMS Pipeline 模块未加载，请刷新后重试。");
        return {};
      }
      const pipeline = window.CrmRmsPipeline.createPipelineState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        Labels: Labels,
        rmsRequest: rmsRequest,
        toast: toast,
        jobs: jobs,
        applicationsState: applicationsState,
        candidatesState: candidatesState,
        loadApplications: loadApplications,
        clientNameById: clientNameById,
        appCandidateName: appCandidateName,
        appJobTitle: appJobTitle,
      });

      if (!window.CrmRmsDeliveryReview || typeof window.CrmRmsDeliveryReview.createDeliveryReviewState !== "function") {
        showRmsBootError("RMS 交付内审模块未加载，请刷新后重试。");
        return {};
      }
      const deliveryReview = window.CrmRmsDeliveryReview.createDeliveryReviewState({
        ref: ref,
        reactive: reactive,
        activeTab: activeTab,
        scheduleCandidatesTableColumnFit: scheduleCandidatesTableColumnFit,
        rmsRequest: rmsRequest,
        workflowMessageForStatus: workflowMessageForStatus,
        Labels: Labels,
        toast: toast,
        loadApplications: loadApplications,
        RmsCandidateReport: window.RmsCandidateReport || {},
      });
      if (!deliveryReview.loadDeliveryReview) {
        showRmsBootError("RMS 交付内审状态初始化失败，请刷新后重试。");
        return {};
      }
      loadDeliveryReviewBridge = deliveryReview.loadDeliveryReview;

      if (!window.CrmRmsRosterConversion || typeof window.CrmRmsRosterConversion.createRosterConversionState !== "function") {
        showRmsBootError("RMS 转入花名册模块未加载，请刷新后重试。");
        return {};
      }
      const rosterConversion = window.CrmRmsRosterConversion.createRosterConversionState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        rmsRequest: rmsRequest,
        toast: toast,
        loadApplications: loadApplications,
        hasPermission: hasPermission,
        isSuper: isSuper,
      });
      if (!rosterConversion.submitRosterConvert) {
        showRmsBootError("RMS 转入花名册状态初始化失败，请刷新后重试。");
        return {};
      }

      if (!window.CrmRmsOfferManagement || typeof window.CrmRmsOfferManagement.createOfferManagementState !== "function") {
        showRmsBootError("RMS Offer 管理模块未加载，请刷新后重试。");
        return {};
      }
      const offerManagement = window.CrmRmsOfferManagement.createOfferManagementState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        Labels: Labels,
        activeTab: activeTab,
        me: me,
        rmsRequest: rmsRequest,
        toast: toast,
        loadApplications: loadApplications,
        scheduleCandidatesTableColumnFit: scheduleCandidatesTableColumnFit,
        appCandidateName: appCandidateName,
        appJobTitle: appJobTitle,
      });
      if (!offerManagement.loadOfferRecords) {
        showRmsBootError("RMS Offer 管理状态初始化失败，请刷新后重试。");
        return {};
      }

      let report = null;
      if (!window.CrmRmsReport || typeof window.CrmRmsReport.createReportState !== "function") {
        showRmsBootError("RMS 推荐报告模块未加载，请刷新后重试。");
        return {};
      }
      report = window.CrmRmsReport.createReportState({
        ref: ref,
        reactive: reactive,
        computed: computed,
        watch: watch,
        nextTick: nextTick,
        viewMode: viewMode,
        rmsRequest: rmsRequest,
        toast: toast,
        jobs: jobs,
        candidatesState: candidatesState,
        loadApplications: loadApplications,
        loadCandidates: loadCandidates,
        loadDeliveryReview: deliveryReview.loadDeliveryReview,
        clientNameById: clientNameById,
        labelCandidate: labelCandidate,
        displayCandidateContact: displayCandidateContact,
        resumeViewUrl: resumeViewUrl,
        resumeCanView: resumeCanView,
        candidateParseSummaryFields: candidateParseSummaryFields,
        candidateParseSummaryEmpty: candidateParseSummaryEmpty,
        candidateParseSummaryValue: candidateParseSummaryValue,
        formatSalaryThousands: formatSalaryThousands,
        stripSalaryCommas: stripSalaryCommas,
        PHONE_RE: PHONE_RE,
        showCandidateDuplicateDialog: showCandidateDuplicateDialog,
        isCandidateDuplicateError: isCandidateDuplicateError,
        userFacingRmsError: userFacingRmsError,
      });

      const reportMode = report.reportMode;
      if (!reportMode) {
        showRmsBootError("RMS 推荐报告状态初始化失败，请刷新后重试。");
        return {};
      }

      const canRecommendExistingCandidate = computed(function () {
        return canWriteApplications.value && canReadCandidates.value;
      });
      const canSubmitCandidateReport = computed(function () {
        if (reportMode.value === "existing") {
          return canWriteApplications.value && canReadCandidates.value;
        }
        return canWriteApplications.value && canWriteCandidates.value;
      });

      function userOptionLabel(u) {
        const dn = (u.display_name || "").trim();
        const un = (u.username || "").trim();
        return dn || un || String(u.id);
      }

      const reviewModal = deliveryReview.reviewModal;
      const reviewFailPromptOpen = deliveryReview.reviewFailPromptOpen;
      const reviewModalError = deliveryReview.reviewModalError;
      const submitDeliveryReview = deliveryReview.submitDeliveryReview;
      const loadDeliveryReview = deliveryReview.loadDeliveryReview;

      async function openDeliveryReviewFailModal() {
        if (!reviewModal.value) return;
        if (typeof window.crmConfirmActionDialog !== "function") {
          reviewModalError.value = "确认对话框不可用";
          return;
        }
        const app = reviewModal.value;
        reviewFailPromptOpen.value = true;
        let result;
        try {
          result = await window.crmConfirmActionDialog({
            title: "内审失败",
            lines: [
              { label: "候选人", value: appCandidateName(app) },
              { label: "岗位", value: appJobTitle(app) },
            ],
            hint: "须填写失败理由，至少 2 个字",
            fields: [{
              type: "textarea",
              name: "note",
              label: "失败理由",
              placeholder: "请说明内审未通过原因",
            }],
            confirmText: "确认失败",
            cancelText: "取消",
            confirmClass: "flex-1 py-2 rounded-md border border-red-300 text-red-700 text-sm font-medium hover:bg-red-50",
            zIndex: 200,
          });
        } finally {
          reviewFailPromptOpen.value = false;
        }
        if (!result || !result.ok) return;
        const note = String((result.values && result.values.note) || "").trim();
        if (note.length < 2) {
          toast("内审失败须填写理由", true);
          return;
        }
        await submitDeliveryReview("failed", note);
      }

      function closeModal() {
        modal.value = null;
        modalError.value = "";
        if (jobs.resetJobModalState) jobs.resetJobModalState();
        if (candidates.resetCandidateModalState) candidates.resetCandidateModalState();
      }

      async function submitModal() {
        modalSaving.value = true;
        modalError.value = "";
        let r;
        try {
        if (modal.value === "job") {
          await jobs.submitJobModal();
          return;
        } else if (modal.value === "candidate") {
          await candidates.submitCandidateModal();
          return;
        } else {
          return;
        }
        } catch (err) {
          const msg = err && err.message ? err.message : String(err);
          setModalError("保存失败：" + msg);
        } finally {
          modalSaving.value = false;
        }
      }

      var RMS_TAB_IDS = ["jobs", "candidates", "applications", "deliveryReview", "pipeline", "offerManagement"];

      function parseRmsOfferLink(linkUrl) {
        try {
          var url = new URL(String(linkUrl || ""), window.location.origin);
          var tab = url.searchParams.get("tab");
          var offerParam = url.searchParams.get("offer");
          if (!tab && url.hash) {
            var hashBody = url.hash.replace(/^#/, "");
            var hashParts = hashBody.split("?");
            tab = hashParts[0] || "";
            if (hashParts[1]) {
              var hashQuery = new URLSearchParams(hashParts[1]);
              if (!offerParam) offerParam = hashQuery.get("offer");
            }
          }
          return {
            tab: tab || "offerManagement",
            offerId: offerParam != null && offerParam !== "" ? Number(offerParam) : null,
          };
        } catch (e) {
          return { tab: "offerManagement", offerId: null };
        }
      }

      function applyRmsOfferNavigation(parsed) {
        if (!parsed) return;
        ensureAllowedActiveTab();
        if (parsed.tab && RMS_TAB_IDS.indexOf(parsed.tab) !== -1) {
          activeTab.value = parsed.tab;
        }
        if (activeTab.value === "offerManagement" && offerManagement.loadOfferRecords) {
          offerManagement.loadOfferRecords();
        }
      }

      window.crmRmsNavigateToOffer = function (linkUrl) {
        var parsed = parseRmsOfferLink(linkUrl);
        if (window.location.pathname.replace(/\/$/, "") !== "/rms") {
          return false;
        }
        var next = new URL(window.location.href);
        next.searchParams.set("tab", parsed.tab || "offerManagement");
        if (parsed.offerId) next.searchParams.set("offer", String(parsed.offerId));
        else next.searchParams.delete("offer");
        next.hash = "";
        history.replaceState(null, "", next.pathname + next.search);
        applyRmsOfferNavigation(parsed);
        return true;
      };

      function resolveInitialActiveTab() {
        var params = new URLSearchParams(window.location.search);
        var tabFromQuery = params.get("tab");
        if (tabFromQuery && RMS_TAB_IDS.indexOf(tabFromQuery) !== -1) {
          activeTab.value = tabFromQuery;
          return;
        }
        var hash = String(window.location.hash || "").replace(/^#/, "").trim();
        var base = hash.split("?")[0];
        if (RMS_TAB_IDS.indexOf(base) !== -1) {
          activeTab.value = base;
        }
      }

      function ensureAllowedActiveTab() {
        if (
          (activeTab.value === "deliveryReview" || activeTab.value === "pipeline") &&
          !canUseRmsDeliveryOpsTabs.value
        ) {
          activeTab.value = "applications";
        }
      }

      watch(canUseRmsDeliveryOpsTabs, function () {
        ensureAllowedActiveTab();
      });

      watch(activeTab, function (tab) {
        if (tab === "candidates" || tab === "applications" || tab === "deliveryReview" || tab === "pipeline" || tab === "offerManagement") {
          scheduleCandidatesTableColumnFit();
        }
        if (tab === "deliveryReview" && canUseRmsDeliveryOpsTabs.value) {
          loadDeliveryReview();
        }
        if (tab === "offerManagement") {
          offerManagement.loadOfferRecords();
        }
      });

      onMounted(async function () {
        resolveInitialActiveTab();
        await loadMe();
        ensureAllowedActiveTab();
        var mountTasks = [
          jobs.loadJobs(),
          loadCandidates(),
          loadApplications(),
          jobs.loadJobFormOptions(),
        ];
        if (canUseRmsDeliveryOpsTabs.value) {
          mountTasks.push(loadDeliveryReview());
        }
        mountTasks.push(offerManagement.loadOfferRecords());
        await Promise.all(mountTasks);
        var offerId = offerManagement.resolveOfferFromUrl();
        if (offerId) {
          activeTab.value = "offerManagement";
        }
        if (activeTab.value === "candidates") {
          scheduleCandidatesTableColumnFit();
        }
        window.addEventListener("popstate", function () {
          resolveInitialActiveTab();
          applyRmsOfferNavigation(parseRmsOfferLink(window.location.href));
        });
        if (Core.initOfferApprovalHintPopovers) {
          Core.initOfferApprovalHintPopovers();
        }
      });

      return {
        activeTab,
        viewMode,
        ...jobs,
        jobModalReadonly: jobs.jobModalReadonly,
        ...candidates,
        ...applications,
        ...report,
        canWriteJobs,
        canDeleteJobs,
        canWriteCandidates,
        canDeleteCandidates,
        canWriteApplications,
        canReadApplications,
        canUseRmsDeliveryOpsTabs,
        canDeleteApplications,
        canReadCandidates,
        canRecommendExistingCandidate,
        canSubmitCandidateReport,
        canConvertToRoster,
        modal,
        modalTitle,
        modalError,
        modalSaving,
        modalCloseLabel,
        modalShowSave,
        ...pipeline,
        pipelineRowIsTerminal: pipeline.pipelineRowIsTerminal || function (status) {
          return Labels.isApplicationTerminal ? Labels.isApplicationTerminal(status) : false;
        },
        ...deliveryReview,
        ...rosterConversion,
        ...offerManagement,
        educationOptions: EDUCATION_OPTIONS,
        genderOptions: GENDER_OPTIONS,
        sourceOptions: SOURCE_OPTIONS,
        maritalOptions: MARITAL_OPTIONS,
        formatRmsDate,
        progressActionBtnClass,
        offerApprovalPendingHint,
        appCandidateName,
        appClientName,
        appJobTitle,
        appJobLocation,
        appDeliveryLabel,
        appRecommenderLabel,
        userOptionLabel,
        clientNameById,
        openDeliveryReviewFailModal,
        closeModal,
        submitModal,
      };
    },
  }).mount("#rms-app");
  } catch (bootErr) {
    console.error("RMS mount failed:", bootErr);
    showRmsBootError(
      "招聘页面初始化失败：" + (bootErr && bootErr.message ? bootErr.message : String(bootErr))
    );
  }
})();
