(function () {
    'use strict';

    const TAX_DIVISOR = 1.0672;
    /** Excel 年假：公司承担，月薪 / 21.75 * 5天 / 12月 */
    const MONTHLY_WORK_DAYS = 21.75;
    const ANNUAL_LEAVE_DAYS = 5;

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
    ];

    function annualLeaveCost(salary) {
        const N = num(salary);
        if (N <= 0) return 0;
        return (N / MONTHLY_WORK_DAYS) * ANNUAL_LEAVE_DAYS / 12;
    }

    window.GmCalculatorCore = {
        TAX_DIVISOR,
        MONTHLY_WORK_DAYS,
        ANNUAL_LEAVE_DAYS,
        annualLeaveCost,
        compute(input, rates) {
            const L = num(input.quoteTaxIncluded);
            const M = L > 0 ? L / TAX_DIVISOR : 0;
            const salary = num(input.salary);
            const bonusMonthly = num(input.bonusMonthly);
            const social = rates ? num(rates.social_insurance) : 0;
            const housing = rates ? num(rates.housing_fund) : 0;
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
        formatMoneyInput,
        MONEY_FIELD_KEYS,
    };
})();
