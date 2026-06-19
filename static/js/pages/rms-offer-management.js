/**
 * RMS Offer management tab & approval form (Phase 6B).
 */
(function (global) {
  "use strict";

  var OFFER_STATUS_FILTER_OPTIONS = [
    { value: "pending", label: "审批中" },
    { value: "approved", label: "已通过" },
    { value: "offer_dropped", label: "弃offer" },
    { value: "onboarding_lost", label: "在途流失" },
  ];

  function createOfferManagementState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var activeTab = deps.activeTab;
    var me = deps.me;
    var rmsRequest = deps.rmsRequest;
    var toast = deps.toast;
    var loadApplications = deps.loadApplications;
    var offerApprovalModal = ref(null);
    var offerApprovalForm = reactive({
      full_name: "",
      contact_info: "",
      customer_name: "",
      work_location: "",
      position_title: "",
      monthly_quote_tax: "",
      quote_tax_unit: "",
      pre_tax_salary: "",
      probation_days: "",
      probation_discount_months: "",
      gm_amount: "",
      gm_pct: "",
      planned_onboard_date: "",
    });
    var offerApprovalSaving = ref(false);
    var offerApprovalError = ref("");
    var offerActionSaving = ref(false);
    var Labels = deps.Labels || {};
    var parseDateOnly = Labels.parseDateOnly || function (str) {
      var s = String(str || "").trim();
      if (!s) return null;
      var m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
      if (!m) return null;
      return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    };

    var offerState = reactive({
      items: [],
      loading: false,
      error: "",
      statusFilter: "",
    });
    var offerFilterPanelExpanded = ref(false);
    var offerScrollWrap = ref(null);
    var offerFilter = reactive({
      keyword: "",
      probation: "",
      gmAmount: "",
      gmPct: "",
      onboardDateFrom: "",
      onboardDateTo: "",
    });

    function resetOfferApprovalForm() {
      var keys = Object.keys(offerApprovalForm);
      for (var i = 0; i < keys.length; i++) {
        offerApprovalForm[keys[i]] = "";
      }
    }

    function formatOfferMoney(val) {
      var raw = normalizeOfferAmountText(val);
      if (!raw) return "";
      if (!/^-?\d+(\.\d+)?$/.test(raw)) return String(val == null ? "" : val).trim();
      var n = Number(raw);
      if (!Number.isFinite(n)) return String(val == null ? "" : val).trim();
      return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
    }

    function formatOfferGmPct(val) {
      var s = String(val == null ? "" : val).trim().replace(/\uff05/g, "%");
      if (!s) return "";
      if (/%\s*$/.test(s)) return s.replace(/\s+$/, "");
      return s + "%";
    }

    function stripOfferGmPct(val) {
      return String(val == null ? "" : val).trim().replace(/%/g, "").replace(/\uff05/g, "").trim();
    }

    function applyOfferApprovalFormDisplayFormats() {
      offerApprovalForm.monthly_quote_tax = formatOfferMoney(offerApprovalForm.monthly_quote_tax);
      offerApprovalForm.pre_tax_salary = formatOfferMoney(offerApprovalForm.pre_tax_salary);
      offerApprovalForm.gm_amount = formatOfferMoney(offerApprovalForm.gm_amount);
      offerApprovalForm.gm_pct = formatOfferGmPct(offerApprovalForm.gm_pct);
    }

    function onOfferApprovalMoneyInput(field) {
      if (field === "monthly_quote_tax" || field === "pre_tax_salary") {
        clearOfferGmCalcFields();
      }
    }

    function onOfferApprovalMoneyChange(field) {
      formatOfferApprovalMoneyField(field);
    }

    function formatOfferApprovalMoneyField(field) {
      if (!offerApprovalForm[field]) return;
      offerApprovalForm[field] = formatOfferMoney(offerApprovalForm[field]);
    }

    function appendGmCalcQueryPart(parts, key, val) {
      var s = String(val == null ? "" : val).trim();
      if (!s) return;
      parts.push(key + "=" + encodeURIComponent(s));
    }

    function normalizeOfferAmountText(val) {
      return String(val || "").replace(/[,¥￥\s\u00a0]/g, "").trim();
    }

    function normalizeMoneyValue(v) {
      var s = String(v == null ? "" : v).replace(/[￥¥,\s]/g, "").trim();
      var n = Number(s);
      return Number.isFinite(n) ? n : null;
    }

    function parseProbationDays(val) {
      var s = String(val == null ? "" : val).trim();
      if (!s) return 0;
      var n = Number(s.replace(/[^\d.-]/g, ""));
      return Number.isFinite(n) ? n : 0;
    }

    function parseGmPctNumber(val) {
      var s = stripOfferGmPct(val);
      if (!s) return null;
      var n = Number(s);
      return Number.isFinite(n) ? n : null;
    }

    function matchesOfferKeyword(row, keyword) {
      var q = String(keyword || "").trim().toLowerCase();
      if (!q) return true;
      var haystack = [
        row.candidate_name,
        row.client_name,
        row.job_title,
        row.status_label,
        row.current_approval_node_label,
        row.pending_approver_label,
        row.recommended_by_label,
        row.created_by_label,
        row.reason,
      ].join(" ").toLowerCase();
      return haystack.indexOf(q) !== -1;
    }

    var filteredOfferRecords = computed(function () {
      var rows = offerState.items.slice();
      if (offerFilter.probation === "yes") {
        rows = rows.filter(function (row) {
          return parseProbationDays(row.probation_days) !== 0;
        });
      } else if (offerFilter.probation === "no") {
        rows = rows.filter(function (row) {
          return parseProbationDays(row.probation_days) === 0;
        });
      }
      if (offerFilter.gmAmount === "gte3000") {
        rows = rows.filter(function (row) {
          var n = normalizeMoneyValue(row.gm_amount);
          return n != null && n >= 3000;
        });
      } else if (offerFilter.gmAmount === "lt3000") {
        rows = rows.filter(function (row) {
          var n = normalizeMoneyValue(row.gm_amount);
          return n != null && n < 3000;
        });
      }
      if (offerFilter.gmPct === "gte15") {
        rows = rows.filter(function (row) {
          var n = parseGmPctNumber(row.gm_pct);
          return n != null && n >= 15;
        });
      } else if (offerFilter.gmPct === "lt15") {
        rows = rows.filter(function (row) {
          var n = parseGmPctNumber(row.gm_pct);
          return n != null && n < 15;
        });
      }
      var from = parseDateOnly(offerFilter.onboardDateFrom);
      var to = parseDateOnly(offerFilter.onboardDateTo);
      if (from || to) {
        rows = rows.filter(function (row) {
          var onboardDate = parseDateOnly(row.planned_onboard_date);
          if (from && (!onboardDate || onboardDate < from)) return false;
          if (to && (!onboardDate || onboardDate > to)) return false;
          return true;
        });
      }
      if (String(offerFilter.keyword || "").trim()) {
        rows = rows.filter(function (row) {
          return matchesOfferKeyword(row, offerFilter.keyword);
        });
      }
      return rows;
    });

    function resetOfferFilter() {
      offerState.statusFilter = "";
      offerFilter.keyword = "";
      offerFilter.probation = "";
      offerFilter.gmAmount = "";
      offerFilter.gmPct = "";
      offerFilter.onboardDateFrom = "";
      offerFilter.onboardDateTo = "";
      loadOfferRecords();
    }

    function scrollOffersToTop() {
      var el = offerScrollWrap.value;
      if (el) el.scrollTop = 0;
    }

    function moneySame(a, b) {
      var x = normalizeMoneyValue(a);
      var y = normalizeMoneyValue(b);
      if (x == null || y == null) return false;
      return Math.abs(x - y) < 0.01;
    }

    function handleOfferGmCalcMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (!offerApprovalModal.value) return;
      var data = event.data || {};
      if (data.type !== "rms_offer_gm_calc_result") return;
      var unitOk = String(data.quote_tax_unit || "") === String(offerApprovalForm.quote_tax_unit || "");
      var quoteOk = moneySame(data.monthly_quote_tax, offerApprovalForm.monthly_quote_tax);
      var salaryOk = moneySame(data.pre_tax_salary, offerApprovalForm.pre_tax_salary);
      if (!unitOk || !quoteOk || !salaryOk) {
        return;
      }
      offerApprovalForm.gm_amount = formatOfferMoney(data.gm_amount);
      offerApprovalForm.gm_pct = formatOfferGmPct(data.gm_pct);
      applyOfferApprovalFormDisplayFormats();
    }

    function clearOfferGmCalcFields() {
      offerApprovalForm.gm_amount = "";
      offerApprovalForm.gm_pct = "";
    }

    function openOfferGmCalculator() {
      if (!offerApprovalModal.value) return;
      var parts = ["return_to=offer_approval"];
      appendGmCalcQueryPart(parts, "quote_tax_unit", offerApprovalForm.quote_tax_unit);
      appendGmCalcQueryPart(parts, "monthly_quote_tax", normalizeOfferAmountText(offerApprovalForm.monthly_quote_tax));
      appendGmCalcQueryPart(parts, "pre_tax_salary", normalizeOfferAmountText(offerApprovalForm.pre_tax_salary));
      appendGmCalcQueryPart(parts, "full_name", offerApprovalForm.full_name);
      appendGmCalcQueryPart(parts, "work_location", offerApprovalForm.work_location);
      appendGmCalcQueryPart(parts, "position", offerApprovalForm.position_title);
      window.open("/tools/calc?" + parts.join("&"), "_blank");
    }

    function formatOfferListMoney(val) {
      var formatted = formatOfferMoney(val);
      return formatted || "—";
    }

    function formatOfferListGmPct(val) {
      var formatted = formatOfferGmPct(val);
      return formatted || "—";
    }

    function formatOfferRowQuote(row) {
      if (!row) return "—";
      var amt = formatOfferMoney(row.monthly_quote_tax);
      var unit = String(row.quote_tax_unit || "").trim();
      if (amt) {
        return unit ? amt + " (" + unit + ")" : amt;
      }
      var legacy = String(row.quote_tax_display || "").trim();
      if (!legacy) return "—";
      var legacyMatch = legacy.match(/^([\d.,]+)\s*(.+)$/);
      if (legacyMatch) {
        var legacyAmt = formatOfferMoney(legacyMatch[1]);
        var legacyUnit = String(legacyMatch[2] || "").trim();
        if (legacyAmt && legacyUnit) return legacyAmt + " (" + legacyUnit + ")";
        if (legacyAmt) return legacyAmt;
      }
      return legacy;
    }

    function refreshNotificationsIfAny() {
      if (typeof global.crmRefreshNotifications === "function") {
        global.crmRefreshNotifications();
      }
    }

    async function loadOfferRecords() {
      offerState.loading = true;
      offerState.error = "";
      try {
        var q = offerState.statusFilter ? "?status=" + encodeURIComponent(offerState.statusFilter) : "";
        var r = await rmsRequest("GET", "/api/rms/offers" + q);
        if (!r.ok) {
          offerState.error = r.message || "加载失败";
          offerState.items = [];
          return;
        }
        offerState.items = Array.isArray(r.data) ? r.data : [];
      } finally {
        offerState.loading = false;
      }
    }

    function currentMeUserId() {
      if (!me.value) return null;
      if (me.value.user && me.value.user.id != null) return Number(me.value.user.id);
      if (me.value.user_id != null) return Number(me.value.user_id);
      return null;
    }

    function canApproveOfferRow(row) {
      if (!row || row.status !== "pending") return false;
      if (row.can_approve === true) return true;
      if (row.can_approve === false) return false;
      var uid = currentMeUserId();
      if (uid == null) return false;
      return Number(row.pending_approver_user_id) === uid;
    }

    async function openOfferApprovalModal(appRow) {
      if (!appRow || appRow.id == null) return;
      offerApprovalError.value = "";
      resetOfferApprovalForm();
      offerApprovalModal.value = { application_id: appRow.id, app: appRow };
      var r = await rmsRequest("GET", "/api/rms/applications/" + appRow.id + "/offer-approval-draft");
      if (!r.ok) {
        offerApprovalError.value = r.message || "加载表单失败";
        return;
      }
      var payload = (r.data && r.data.offer_payload) || {};
      Object.keys(offerApprovalForm).forEach(function (k) {
        if (payload[k] != null) offerApprovalForm[k] = String(payload[k]);
      });
      applyOfferApprovalFormDisplayFormats();
      window.addEventListener("message", handleOfferGmCalcMessage);
    }

    function closeOfferApprovalModal() {
      window.removeEventListener("message", handleOfferGmCalcMessage);
      offerApprovalModal.value = null;
      offerApprovalError.value = "";
      resetOfferApprovalForm();
    }

    async function submitOfferApproval() {
      if (!offerApprovalModal.value) return;
      var required = [
        ["quote_tax_unit", "报价（含税）"],
        ["monthly_quote_tax", "报价（含税）"],
        ["pre_tax_salary", "税前工资"],
        ["probation_days", "试工期"],
        ["probation_discount_months", "折扣月数"],
        ["gm_amount", "GM$"],
        ["gm_pct", "GM%"],
        ["planned_onboard_date", "计划入职日期"],
      ];
      for (var i = 0; i < required.length; i++) {
        if (!String(offerApprovalForm[required[i][0]] || "").trim()) {
          if (required[i][0] === "gm_amount" || required[i][0] === "gm_pct") {
            toast("请使用毛利测算器填写 " + required[i][1], true);
          } else {
            toast(required[i][1] + " 必填", true);
          }
          return;
        }
      }
      offerApprovalSaving.value = true;
      offerApprovalError.value = "";
      try {
        var body = {};
        Object.keys(offerApprovalForm).forEach(function (k) {
          body[k] = offerApprovalForm[k];
        });
        body.monthly_quote_tax = normalizeOfferAmountText(body.monthly_quote_tax);
        body.pre_tax_salary = normalizeOfferAmountText(body.pre_tax_salary);
        body.gm_amount = normalizeOfferAmountText(body.gm_amount);
        body.gm_pct = stripOfferGmPct(body.gm_pct);
        var appId = offerApprovalModal.value.application_id;
        var r = await rmsRequest("POST", "/api/rms/applications/" + appId + "/offer-approval", body);
        if (!r.ok) {
          offerApprovalError.value = r.message || "提交失败";
          return;
        }
        toast("Offer 审批已发起", false);
        closeOfferApprovalModal();
        await Promise.all([loadApplications(), loadOfferRecords()]);
        refreshNotificationsIfAny();
      } finally {
        offerApprovalSaving.value = false;
      }
    }

    async function approveOfferRecord(row, comment) {
      if (!row || row.id == null) return;
      offerActionSaving.value = true;
      try {
        var r = await rmsRequest("POST", "/api/rms/offers/" + row.id + "/approve", { comment: comment || "" });
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        toast("已通过", false);
        await Promise.all([loadApplications(), loadOfferRecords()]);
        refreshNotificationsIfAny();
      } finally {
        offerActionSaving.value = false;
      }
    }

    async function rejectOfferRecord(row, reason) {
      if (!row || row.id == null) return;
      offerActionSaving.value = true;
      try {
        var r = await rmsRequest("POST", "/api/rms/offers/" + row.id + "/reject", { reason: reason });
        if (!r.ok) {
          toast(r.message, true);
          return;
        }
        toast("已驳回", false);
        await Promise.all([loadApplications(), loadOfferRecords()]);
        refreshNotificationsIfAny();
      } finally {
        offerActionSaving.value = false;
      }
    }

    async function openOfferApproveModal(row) {
      if (typeof global.crmConfirmActionDialog !== "function") {
        toast("确认对话框不可用", true);
        return;
      }
      var result = await global.crmConfirmActionDialog({
        title: "审批通过",
        lines: [{ label: "候选人", value: row.candidate_name || "—" }],
        fields: [{ type: "textarea", name: "comment", label: "审批意见", placeholder: "可选" }],
        confirmText: "通过",
        cancelText: "取消",
        zIndex: 120,
      });
      if (!result || !result.ok) return;
      await approveOfferRecord(row, (result.values && result.values.comment) || "");
    }

    async function openOfferRejectModal(row) {
      if (typeof global.crmConfirmActionDialog !== "function") {
        toast("确认对话框不可用", true);
        return;
      }
      var result = await global.crmConfirmActionDialog({
        title: "驳回 Offer 审批",
        lines: [{ label: "候选人", value: row.candidate_name || "—" }],
        fields: [{
          type: "textarea",
          name: "reason",
          label: "驳回原因",
          placeholder: "必填",
        }],
        confirmText: "驳回",
        cancelText: "取消",
        zIndex: 120,
      });
      if (!result || !result.ok) return;
      var reason = String((result.values && result.values.reason) || "").trim();
      if (!reason) {
        toast("驳回原因必填", true);
        return;
      }
      await rejectOfferRecord(row, reason);
    }

    async function openDropOfferModal(appRow) {
      if (!appRow || appRow.id == null) return;
      if (typeof global.crmConfirmActionDialog !== "function") {
        toast("确认对话框不可用", true);
        return;
      }
      var result = await global.crmConfirmActionDialog({
        title: "弃offer",
        lines: [
          { label: "候选人", value: deps.appCandidateName ? deps.appCandidateName(appRow) : "" },
          { label: "岗位", value: deps.appJobTitle ? deps.appJobTitle(appRow) : "" },
        ],
        fields: [{
          type: "textarea",
          name: "reason",
          label: "弃offer原因",
          required: true,
          placeholder: "必填",
        }],
        confirmText: "确认",
        cancelText: "取消",
        zIndex: 120,
      });
      if (!result || !result.ok) return;
      var reason = String((result.values && result.values.reason) || "").trim();
      if (!reason) {
        toast("弃offer原因必填", true);
        return;
      }
      var r = await rmsRequest("POST", "/api/rms/applications/" + appRow.id + "/drop-offer", { reason: reason });
      if (!r.ok) {
        toast(r.message, true);
        return;
      }
      toast("已弃offer", false);
      await Promise.all([loadApplications(), loadOfferRecords()]);
    }

    async function openTransitLostModal(appRow) {
      if (!appRow || appRow.id == null) return;
      if (typeof global.crmConfirmActionDialog !== "function") {
        toast("确认对话框不可用", true);
        return;
      }
      var result = await global.crmConfirmActionDialog({
        title: "在途流失",
        lines: [
          { label: "候选人", value: deps.appCandidateName ? deps.appCandidateName(appRow) : "" },
          { label: "岗位", value: deps.appJobTitle ? deps.appJobTitle(appRow) : "" },
        ],
        fields: [{
          type: "textarea",
          name: "reason",
          label: "在途流失原因",
          required: true,
          placeholder: "必填",
        }],
        confirmText: "确认",
        cancelText: "取消",
        zIndex: 120,
      });
      if (!result || !result.ok) return;
      var reason = String((result.values && result.values.reason) || "").trim();
      if (!reason) {
        toast("在途流失原因必填", true);
        return;
      }
      var r = await rmsRequest("POST", "/api/rms/applications/" + appRow.id + "/transit-lost", { reason: reason });
      if (!r.ok) {
        toast(r.message, true);
        return;
      }
      toast("已标记在途流失", false);
      await Promise.all([loadApplications(), loadOfferRecords()]);
    }

    function resolveOfferFromUrl() {
      var params = new URLSearchParams(window.location.search);
      if (params.get("offer")) return Number(params.get("offer"));
      var hash = String(window.location.hash || "");
      var m = hash.match(/[?&]offer=(\d+)/);
      if (!m) return null;
      return Number(m[1]);
    }

    return {
      offerFilterPanelExpanded: offerFilterPanelExpanded,
      offerScrollWrap: offerScrollWrap,
      scrollOffersToTop: scrollOffersToTop,
      offerState: offerState,
      offerFilter: offerFilter,
      filteredOfferRecords: filteredOfferRecords,
      resetOfferFilter: resetOfferFilter,
      offerStatusFilterOptions: OFFER_STATUS_FILTER_OPTIONS,
      offerApprovalModal: offerApprovalModal,
      offerApprovalForm: offerApprovalForm,
      offerApprovalSaving: offerApprovalSaving,
      offerApprovalError: offerApprovalError,
      offerActionSaving: offerActionSaving,
      loadOfferRecords: loadOfferRecords,
      openOfferApprovalModal: openOfferApprovalModal,
      closeOfferApprovalModal: closeOfferApprovalModal,
      submitOfferApproval: submitOfferApproval,
      canApproveOfferRow: canApproveOfferRow,
      openOfferApproveModal: openOfferApproveModal,
      openOfferRejectModal: openOfferRejectModal,
      openDropOfferModal: openDropOfferModal,
      openTransitLostModal: openTransitLostModal,
      resolveOfferFromUrl: resolveOfferFromUrl,
      openOfferGmCalculator: openOfferGmCalculator,
      clearOfferGmCalcFields: clearOfferGmCalcFields,
      onOfferApprovalMoneyInput: onOfferApprovalMoneyInput,
      onOfferApprovalMoneyChange: onOfferApprovalMoneyChange,
      formatOfferApprovalMoneyField: formatOfferApprovalMoneyField,
      formatOfferMoney: formatOfferMoney,
      formatOfferGmPct: formatOfferGmPct,
      formatOfferListMoney: formatOfferListMoney,
      formatOfferListGmPct: formatOfferListGmPct,
      formatOfferRowQuote: formatOfferRowQuote,
    };
  }

  global.CrmRmsOfferManagement = {
    createOfferManagementState: createOfferManagementState,
  };
})(typeof window !== "undefined" ? window : globalThis);
