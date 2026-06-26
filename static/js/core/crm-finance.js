(function (global) {
  "use strict";

  var DEFAULT_MONTHLY_BILLABLE_DAYS = 20.67;
  var DEFAULT_DAILY_BILLABLE_HOURS = 8;

  var UNIT_ALIASES = {
    monthly: "monthly",
    month: "monthly",
    "\u4eba\u6708": "monthly",
    daily: "daily",
    day: "daily",
    "\u4eba\u5929": "daily",
    hourly: "hourly",
    hour: "hourly",
    "\u4eba\u65f6": "hourly",
  };

  function normalizeMoney(value) {
    if (value === null || value === undefined) return 0;
    var n = Number(String(value).replace(/,/g, "").replace(/[¥￥%\s\u00a0]/g, "").trim());
    return Number.isFinite(n) ? n : 0;
  }

  function normalizeQuoteUnit(unit) {
    var raw = String(unit || "").trim();
    if (!raw) return "monthly";
    var lower = raw.toLowerCase();
    if (UNIT_ALIASES[lower]) return UNIT_ALIASES[lower];
    if (UNIT_ALIASES[raw]) return UNIT_ALIASES[raw];
    return "monthly";
  }

  function quoteUnitLabel(unit) {
    var u = normalizeQuoteUnit(unit);
    if (u === "daily") return "\u5929\u62a5\u4ef7";
    if (u === "hourly") return "\u65f6\u62a5\u4ef7";
    return "\u6708\u62a5\u4ef7";
  }

  function offerTaxUnitFromQuoteUnit(unit) {
    var u = normalizeQuoteUnit(unit);
    if (u === "daily") return "\u4eba\u5929";
    if (u === "hourly") return "\u4eba\u65f6";
    return "\u4eba\u6708";
  }

  function quoteUnitFromOfferTaxUnit(unit) {
    return normalizeQuoteUnit(unit);
  }

  function billingNumber(value, fallback) {
    var n = normalizeMoney(value);
    return n > 0 ? n : fallback;
  }

  function standardMonthlyQuoteTax(unit, quoteValue, monthlyBillingDays, dailyHours) {
    var quote = normalizeMoney(quoteValue);
    if (quote <= 0) return 0;
    var days = billingNumber(monthlyBillingDays, DEFAULT_MONTHLY_BILLABLE_DAYS);
    var hours = billingNumber(dailyHours, DEFAULT_DAILY_BILLABLE_HOURS);
    var u = normalizeQuoteUnit(unit);
    if (u === "daily") return quote * days;
    if (u === "hourly") return quote * hours * days;
    return quote;
  }

  function quoteCoefficient(unit, quoteValue, preTaxSalary, monthlyBillingDays, dailyHours) {
    var monthlyQuote = standardMonthlyQuoteTax(unit, quoteValue, monthlyBillingDays, dailyHours);
    var salary = normalizeMoney(preTaxSalary);
    if (!monthlyQuote || !salary) return "";
    return (monthlyQuote / salary).toFixed(2);
  }

  function formatQuoteCoefficient(value) {
    var n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return "\u2014";
    return n.toFixed(2);
  }

  global.CrmFinance = {
    DEFAULT_MONTHLY_BILLABLE_DAYS: DEFAULT_MONTHLY_BILLABLE_DAYS,
    DEFAULT_DAILY_BILLABLE_HOURS: DEFAULT_DAILY_BILLABLE_HOURS,
    normalizeMoney: normalizeMoney,
    normalizeQuoteUnit: normalizeQuoteUnit,
    quoteUnitLabel: quoteUnitLabel,
    offerTaxUnitFromQuoteUnit: offerTaxUnitFromQuoteUnit,
    quoteUnitFromOfferTaxUnit: quoteUnitFromOfferTaxUnit,
    standardMonthlyQuoteTax: standardMonthlyQuoteTax,
    quoteCoefficient: quoteCoefficient,
    formatQuoteCoefficient: formatQuoteCoefficient,
  };
})(window);
