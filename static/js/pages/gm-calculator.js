(function () {
    'use strict';

    const TAX_DIVISOR = 1.0672;
    /** Excel 年假：公司承担，月薪 / 21.75 * 5天 / 12月 */
    const MONTHLY_WORK_DAYS = 21.75;
    const ANNUAL_LEAVE_DAYS = 5;
    /** 2026 年均工作日系数（365 天 - 104 周末 - 13 法定假）/ 12 */
    const MONTHLY_WORK_DAYS_2026 = 20.67;
    /** 2026 年月均工时系数（20.67 工作日 × 8 小时/天） */
    const MONTHLY_HOURS_2026 = 165.36;
    const QUOTE_UNITS = { month: 'month', day: 'day', hour: 'hour', custom: 'custom' };

    function money(n) {
        if (!Number.isFinite(n)) return '—';
        return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function pct(n) {
        if (!Number.isFinite(n)) return '—';
        return (n * 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';
    }

    function num(v) {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
    }

    /** 解析带千分位/货币符号的输入 */
    function parseMoneyInput(str) {
        const raw = String(str == null ? '' : str).trim();
        if (!raw) return 0;
        const cleaned = raw.replace(/[^\d.-]/g, '');
        if (!cleaned || cleaned === '-' || cleaned === '.') return 0;
        const n = Number(cleaned);
        return Number.isFinite(n) ? n : 0;
    }

    /** 输入框展示用千分位（最多 2 位小数） */
    function formatMoneyInput(n) {
        const v = num(n);
        if (v === 0) return '0';
        return v.toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    const MONEY_FIELD_KEYS = [
        'quoteTaxIncluded',
        'salary',
        'bonusMonthly',
        'welfare',
        'laptop',
        'recruitment',
        'capital',
        'other',
        'socialBase',
        'housingBase',
    ];

    /** 解析百分比输入（去 %、千分位） */
    function parsePercentInput(str) {
        return parseMoneyInput(str);
    }

    /** 展示用百分比格式化 */
    function formatPercentInput(n, decimals) {
        const v = num(n);
        if (v === 0) return '0';
        return v.toLocaleString('zh-CN', {
            minimumFractionDigits: 0,
            maximumFractionDigits: decimals,
        });
    }

    function computeCustomSocialCost(base, ratePct) {
        return num(base) * num(ratePct) / 100;
    }

    function computeCustomHousingCost(base, ratePct) {
        return num(base) * num(ratePct) / 100;
    }

    function annualLeaveCost(salary) {
        const N = num(salary);
        if (N <= 0) return 0;
        return (N / MONTHLY_WORK_DAYS) * ANNUAL_LEAVE_DAYS / 12;
    }

    /** 将用户输入的含税报价换算为人月含税报价 L */
    function normalizeQuoteToMonthly(quoteRaw, quoteUnit, monthlyHours) {
        const raw = num(quoteRaw);
        if (raw <= 0) return 0;
        const unit = quoteUnit || QUOTE_UNITS.month;
        if (unit === QUOTE_UNITS.day) return raw * MONTHLY_WORK_DAYS_2026;
        if (unit === QUOTE_UNITS.hour) return raw * MONTHLY_HOURS_2026;
        if (unit === QUOTE_UNITS.custom) {
            const hours = num(monthlyHours);
            if (hours <= 0) return 0;
            return raw * hours;
        }
        return raw;
    }

    window.GmCalculatorCore = {
        TAX_DIVISOR,
        MONTHLY_WORK_DAYS,
        ANNUAL_LEAVE_DAYS,
        MONTHLY_WORK_DAYS_2026,
        MONTHLY_HOURS_2026,
        QUOTE_UNITS,
        annualLeaveCost,
        normalizeQuoteToMonthly,
        computeCustomSocialCost,
        computeCustomHousingCost,
        compute(input, rates) {
            const quoteRaw = num(input.quoteTaxIncluded);
            const quoteUnit = input.quoteUnit || QUOTE_UNITS.month;
            const monthlyHours = num(input.monthlyHours);
            const customInsurance = !!input.customInsurance;
            const socialBase = num(input.socialBase);
            const socialCompanyRate = num(input.socialCompanyRate);
            const housingBase = num(input.housingBase);
            const housingCompanyRate = num(input.housingCompanyRate);
            const L = normalizeQuoteToMonthly(quoteRaw, quoteUnit, monthlyHours);
            const M = L > 0 ? L / TAX_DIVISOR : 0;
            const salary = num(input.salary);
            const bonusMonthly = num(input.bonusMonthly);
            let social;
            let housing;
            if (customInsurance) {
                social = computeCustomSocialCost(socialBase, socialCompanyRate);
                housing = computeCustomHousingCost(housingBase, housingCompanyRate);
            } else {
                social = rates ? num(rates.social_insurance) : 0;
                housing = rates ? num(rates.housing_fund) : 0;
            }
            const annualLeave = annualLeaveCost(salary);
            const welfare = num(input.welfare);
            const laptop = num(input.laptop);
            const recruitment = num(input.recruitment);
            const capital = num(input.capital);
            const other = num(input.other);
            const Y =
                salary +
                bonusMonthly +
                social +
                housing +
                annualLeave +
                welfare +
                laptop +
                recruitment +
                capital +
                other;
            const Z = M - Y;
            const margin = M > 0 ? Z / M : null;
            return {
                quoteRaw,
                quoteUnit,
                monthlyHours,
                customInsurance,
                socialBase,
                socialCompanyRate,
                housingBase,
                housingCompanyRate,
                L,
                M,
                salary,
                bonusMonthly,
                social,
                housing,
                annualLeave,
                welfare,
                laptop,
                recruitment,
                capital,
                other,
                Y,
                Z,
                margin,
            };
        },
        money,
        pct,
        parseMoneyInput,
        parsePercentInput,
        formatMoneyInput,
        formatPercentInput,
        MONEY_FIELD_KEYS,
    };
})();
