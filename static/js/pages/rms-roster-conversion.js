/**
 * RMS hired application → roster conversion modal (Phase R3-C split).
 */
(function (global) {
  "use strict";

  function createRosterConversionState(deps) {
    var ref = deps.ref;
    var reactive = deps.reactive;
    var computed = deps.computed;
    var watch = deps.watch;
    var rmsRequest = deps.rmsRequest;
    var toast = deps.toast;
    var loadApplications = deps.loadApplications;
    var hasPermission = deps.hasPermission || function () { return false; };
    var isSuper = deps.isSuper || { value: false };
    var CandidateReport = global.RmsCandidateReport || {};

    var rosterConvertModal = ref(null);
    var rosterConvertSaving = ref(false);
    var rosterConvertError = ref("");
    var rosterOfferFinancialLocked = ref(false);
    var rosterQuoteTaxDisplay = ref("");
    var canUseGmCalc = computed(function () {
      return !!isSuper.value || hasPermission("tools.gm_calc.read");
    });
    var rosterConvertForm = reactive({
      employment_status: "在职",
      full_name: "",
      contact_info: "",
      customer_name: "",
      work_location: "",
      position_title: "",
      business_line: "",
      entry_date: "",
      regularization_status: "未转正",
      regularization_date: "",
      quote_unit: "monthly",
      quote_amount_tax: "",
      monthly_billable_days: "20.67",
      daily_billable_hours: "8",
      monthly_quote_tax: "",
      pre_tax_salary: "",
      salary_quote_ratio: "",
      gms: "",
      gm_pct: "",
      employee_plus1: "",
      employee_plus2: "",
      interface_contact: "",
      zntx_onboarding_channel: "",
      zntx_onboarding_channel_other: "",
      remarks: "",
    });

    function resetRosterConvertForm() {
      rosterConvertForm.employment_status = "在职";
      rosterConvertForm.full_name = "";
      rosterConvertForm.contact_info = "";
      rosterConvertForm.customer_name = "";
      rosterConvertForm.work_location = "";
      rosterConvertForm.position_title = "";
      rosterConvertForm.business_line = "";
      rosterConvertForm.entry_date = "";
      rosterConvertForm.regularization_status = "未转正";
      rosterConvertForm.regularization_date = "";
      rosterConvertForm.quote_unit = "monthly";
      rosterConvertForm.quote_amount_tax = "";
      rosterConvertForm.monthly_billable_days = "20.67";
      rosterConvertForm.daily_billable_hours = "8";
      rosterConvertForm.monthly_quote_tax = "";
      rosterConvertForm.pre_tax_salary = "";
      rosterConvertForm.salary_quote_ratio = "";
      rosterConvertForm.gms = "";
      rosterConvertForm.gm_pct = "";
      rosterConvertForm.employee_plus1 = "";
      rosterConvertForm.employee_plus2 = "";
      rosterConvertForm.interface_contact = "";
      rosterConvertForm.zntx_onboarding_channel = "";
      rosterConvertForm.zntx_onboarding_channel_other = "";
      rosterConvertForm.remarks = "";
    }

    function applyOnboardingChannelToForm(storedChannel) {
      var parts = CandidateReport.resolveSourceForForm
        ? CandidateReport.resolveSourceForForm(storedChannel || "")
        : { source: storedChannel || "", source_other: "" };
      rosterConvertForm.zntx_onboarding_channel = parts.source;
      rosterConvertForm.zntx_onboarding_channel_other = parts.source_other;
    }

    function resolveOnboardingChannelForSave() {
      if (CandidateReport.resolveSourceForSave) {
        return CandidateReport.resolveSourceForSave(
          rosterConvertForm.zntx_onboarding_channel,
          rosterConvertForm.zntx_onboarding_channel_other
        );
      }
      return rosterConvertForm.zntx_onboarding_channel || "";
    }

    function normalizeRosterAmountText(val) {
      return String(val || "").replace(/[,¥￥\s\u00a0]/g, "").trim();
    }

    function formatRosterMoneyDisplay(val) {
      var raw = normalizeRosterAmountText(val);
      if (!raw) return "";
      var n = Number(raw);
      if (!Number.isFinite(n)) return String(val || "");
      if (Math.abs(n - Math.round(n)) < 1e-9) {
        return Math.round(n).toLocaleString("zh-CN");
      }
      return n.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    function formatRosterGmPctDisplay(val) {
      var s = String(val || "").trim().replace(/\uff05/g, "%");
      if (!s) return "";
      if (s.charAt(s.length - 1) === "%") return s;
      return s + "%";
    }

    function formatGmPctSymbol(val) {
      var s = String(val || "").trim().replace(/\uff05/g, "%");
      if (!s) return "";
      if (s.indexOf("%") === s.length - 1) return s;
      return s + "%";
    }

    function refreshRosterConvertQuoteCoefficient() {
      var Fin = global.CrmFinance;
      if (!Fin) return;
      rosterConvertForm.salary_quote_ratio = Fin.quoteCoefficient(
        rosterConvertForm.quote_unit,
        rosterConvertForm.quote_amount_tax,
        rosterConvertForm.pre_tax_salary,
        rosterConvertForm.monthly_billable_days,
        rosterConvertForm.daily_billable_hours
      );
    }

    if (watch) {
      watch(
        function () {
          return [
            rosterConvertForm.quote_unit,
            rosterConvertForm.quote_amount_tax,
            rosterConvertForm.monthly_billable_days,
            rosterConvertForm.daily_billable_hours,
            rosterConvertForm.pre_tax_salary,
          ];
        },
        function () {
          refreshRosterConvertQuoteCoefficient();
        }
      );
    }

    function validateRosterConvertForm() {
      var required = [
        ["employment_status", "在职情况"],
        ["full_name", "姓名"],
        ["contact_info", "联系方式"],
        ["customer_name", "客户"],
        ["work_location", "工作地"],
        ["position_title", "岗位"],
        ["business_line", "业务线"],
        ["entry_date", "入职时间"],
        ["regularization_status", "转正"],
        ["quote_amount_tax", "报价(含税)"],
        ["pre_tax_salary", "税前工资"],
        ["gms", "GM$"],
        ["gm_pct", "GM%"],
      ];
      var missing = [];
      required.forEach(function (pair) {
        if (!String(rosterConvertForm[pair[0]] || "").trim()) missing.push(pair[1]);
      });
      if (missing.length) return "请先完整填写必填项：" + missing.join("、");
      if (rosterConvertForm.zntx_onboarding_channel === "其他" &&
          !String(rosterConvertForm.zntx_onboarding_channel_other || "").trim()) {
        return "请填写具体入职渠道";
      }
      var phone = String(rosterConvertForm.contact_info || "").trim();
      if (!/^\d{11}$/.test(phone)) return "联系方式必须为11位数字";
      return "";
    }

    function appendGmCalcQueryPart(parts, key, val) {
      var s = String(val == null ? "" : val).trim();
      if (!s) return;
      parts.push(key + "=" + encodeURIComponent(s));
    }

    function openRosterGmCalculatorFromRms() {
      if (!rosterConvertModal.value) return;
      var Fin = global.CrmFinance || {};
      var parts = ["return_to=roster", "roster_add=1"];
      appendGmCalcQueryPart(parts, "targetClientId", rosterConvertModal.value.clientId);
      appendGmCalcQueryPart(parts, "full_name", rosterConvertForm.full_name);
      appendGmCalcQueryPart(parts, "work_location", rosterConvertForm.work_location);
      appendGmCalcQueryPart(parts, "position", rosterConvertForm.position_title);
      var quoteUnit = rosterConvertForm.quote_unit || "monthly";
      appendGmCalcQueryPart(parts, "quote_tax_unit", Fin.offerTaxUnitFromQuoteUnit ? Fin.offerTaxUnitFromQuoteUnit(quoteUnit) : "人月");
      appendGmCalcQueryPart(parts, "quote_amount_tax", normalizeRosterAmountText(rosterConvertForm.quote_amount_tax));
      appendGmCalcQueryPart(parts, "monthly_billable_days", rosterConvertForm.monthly_billable_days || "20.67");
      appendGmCalcQueryPart(parts, "daily_billable_hours", rosterConvertForm.daily_billable_hours || "8");
      var converted = Fin.standardMonthlyQuoteTax
        ? Fin.standardMonthlyQuoteTax(
          quoteUnit,
          rosterConvertForm.quote_amount_tax,
          rosterConvertForm.monthly_billable_days,
          rosterConvertForm.daily_billable_hours
        )
        : normalizeRosterAmountText(rosterConvertForm.quote_amount_tax);
      appendGmCalcQueryPart(parts, "monthly_quote_tax", String(Math.round(converted || 0)));
      appendGmCalcQueryPart(parts, "pre_tax_salary", normalizeRosterAmountText(rosterConvertForm.pre_tax_salary));
      appendGmCalcQueryPart(parts, "gms", normalizeRosterAmountText(rosterConvertForm.gms));
      appendGmCalcQueryPart(parts, "gm_pct", rosterConvertForm.gm_pct);
      window.open("/tools/calc?" + parts.join("&"), "_blank");
    }

    async function openRosterConvertModal(appRow, options) {
      var opts = options && typeof options === "object" ? options : {};
      rosterConvertError.value = "";
      rosterConvertSaving.value = false;
      rosterOfferFinancialLocked.value = false;
      rosterQuoteTaxDisplay.value = "";
      resetRosterConvertForm();
      rosterConvertModal.value = {
        applicationId: appRow.id,
        clientId: appRow.client_id,
        quoteTaxUnit: "",
        fromOnboarding: !!opts.fromOnboarding,
      };
      var r = await rmsRequest("GET", "/api/rms/applications/" + appRow.id + "/roster-draft");
      if (!r.ok) {
        rosterConvertError.value = r.message || "加载花名册草稿失败";
        return;
      }
      var data = r.data || {};
      var payload = data.roster_payload || {};
      if (data.client_id != null) {
        rosterConvertModal.value.clientId = data.client_id;
      }
      if (rosterConvertModal.value) {
        rosterConvertModal.value.quoteTaxUnit = String(data.quote_tax_unit || "").trim();
      }
      rosterOfferFinancialLocked.value = !!data.offer_financial_locked;
      rosterQuoteTaxDisplay.value = String(data.quote_tax_display || "").trim();
      Object.keys(rosterConvertForm).forEach(function (key) {
        if (key === "zntx_onboarding_channel" || key === "zntx_onboarding_channel_other") return;
        if (payload[key] != null) rosterConvertForm[key] = String(payload[key]);
      });
      applyOnboardingChannelToForm(payload.zntx_onboarding_channel);
      refreshRosterConvertQuoteCoefficient();
    }

    function closeRosterConvertModal() {
      rosterConvertModal.value = null;
      rosterConvertError.value = "";
      rosterConvertSaving.value = false;
      rosterOfferFinancialLocked.value = false;
      rosterQuoteTaxDisplay.value = "";
    }

    function openConvertedRosterEntry(a) {
      if (!a || !a.client_id || !a.converted_to_roster_entry_id) return;
      window.location.href = "/customers/roster/" + a.client_id + "?row_id=" + a.converted_to_roster_entry_id;
    }

    async function submitRosterConvert() {
      if (!rosterConvertModal.value) return;
      var clientErr = validateRosterConvertForm();
      if (clientErr) {
        rosterConvertError.value = clientErr;
        return;
      }
      rosterConvertSaving.value = true;
      rosterConvertError.value = "";
      var payload = {};
      Object.keys(rosterConvertForm).forEach(function (key) {
        if (key === "zntx_onboarding_channel" || key === "zntx_onboarding_channel_other") return;
        payload[key] = rosterConvertForm[key];
      });
      payload.zntx_onboarding_channel = resolveOnboardingChannelForSave();
      payload.quote_unit = global.CrmFinance
        ? global.CrmFinance.normalizeQuoteUnit(rosterConvertForm.quote_unit || "monthly")
        : (rosterConvertForm.quote_unit || "monthly");
      payload.quote_amount_tax = normalizeRosterAmountText(payload.quote_amount_tax);
      payload.monthly_billable_days = String(rosterConvertForm.monthly_billable_days || "20.67").trim();
      payload.daily_billable_hours = String(rosterConvertForm.daily_billable_hours || "8").trim();
      payload.pre_tax_salary = normalizeRosterAmountText(payload.pre_tax_salary);
      payload.gms = normalizeRosterAmountText(payload.gms);
      payload.gm_pct = formatGmPctSymbol(payload.gm_pct);
      var appId = rosterConvertModal.value.applicationId;
      var r = await rmsRequest("POST", "/api/rms/applications/" + appId + "/convert-to-roster", payload);
      rosterConvertSaving.value = false;
      if (!r.ok) {
        rosterConvertError.value = r.message || "转入花名册失败";
        return;
      }
      var successMsg = rosterConvertModal.value && rosterConvertModal.value.fromOnboarding
        ? "已成功入职并转入花名册"
        : "已成功转入花名册";
      closeRosterConvertModal();
      toast(successMsg, false);
      await loadApplications();
    }

    var rosterConvertModalTitle = computed(function () {
      if (!rosterConvertModal.value) return "转入花名册";
      return rosterConvertModal.value.fromOnboarding ? "已入职" : "转入花名册";
    });

    return {
      rosterConvertModal: rosterConvertModal,
      rosterConvertSaving: rosterConvertSaving,
      rosterConvertError: rosterConvertError,
      rosterConvertForm: rosterConvertForm,
      rosterOfferFinancialLocked: rosterOfferFinancialLocked,
      rosterQuoteTaxDisplay: rosterQuoteTaxDisplay,
      formatRosterMoneyDisplay: formatRosterMoneyDisplay,
      formatRosterGmPctDisplay: formatRosterGmPctDisplay,
      canUseGmCalc: canUseGmCalc,
      resetRosterConvertForm: resetRosterConvertForm,
      validateRosterConvertForm: validateRosterConvertForm,
      appendGmCalcQueryPart: appendGmCalcQueryPart,
      openRosterGmCalculatorFromRms: openRosterGmCalculatorFromRms,
      openRosterConvertModal: openRosterConvertModal,
      closeRosterConvertModal: closeRosterConvertModal,
      openConvertedRosterEntry: openConvertedRosterEntry,
      submitRosterConvert: submitRosterConvert,
      rosterConvertModalTitle: rosterConvertModalTitle,
    };
  }

  global.CrmRmsRosterConversion = {
    createRosterConversionState: createRosterConversionState,
  };
})(typeof window !== "undefined" ? window : globalThis);
