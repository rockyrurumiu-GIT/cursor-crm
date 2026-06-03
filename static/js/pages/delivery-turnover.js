/**
 * Delivery Turnover page logic.
 * Extracted from templates/pages/delivery_turnover.html (Phase 27).
 * Requires: Vue 3 CDN loaded before this script.
 */

const { createApp, ref, onMounted, computed, reactive, watch } = Vue;

function defaultDashboardAnalysisPeriod() {
    const today = new Date();
    const firstThis = new Date(today.getFullYear(), today.getMonth(), 1);
    const endLast = new Date(firstThis.getTime() - 86400000);
    const startLast = new Date(endLast.getFullYear(), endLast.getMonth(), 1);
    const iso = (d) => d.toISOString().slice(0, 10);
    return { start: iso(startLast), end: iso(endLast) };
}

function normalizeDate(raw) {
    const s = String(raw || '').trim();
    if (!s) return null;
    const m = s.match(/(\d{4})\D?(\d{1,2})\D?(\d{1,2})/);
    if (!m) return null;
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    const d = parseInt(m[3], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
    const dt = new Date(y, mo - 1, d);
    return Number.isNaN(dt.getTime()) ? null : dt;
}

/** 解析花名册行 id；避免 id 为 0 时被 `|| null` 误判为「新增」模式 */
function parseRosterRowId(row) {
    const raw = row?.id;
    if (raw == null || raw === '') return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
}

function computeTenure(entryDate, resignDate) {
    const start = normalizeDate(entryDate);
    if (!start) return '';
    const end = normalizeDate(resignDate) || new Date();
    const diffMs = end.getTime() - start.getTime();
    if (diffMs < 0) return '';
    const days = Math.floor(diffMs / (24 * 60 * 60 * 1000));
    return `${days}天`;
}

/** 司龄天数（与 computeTenure 同口径），用于筛选 */
function tenureDays(row) {
    const start = normalizeDate(row.entry_date);
    if (!start) return null;
    const end = normalizeDate(row.company_resign_date) || new Date();
    const diffMs = end.getTime() - start.getTime();
    if (diffMs < 0) return null;
    return Math.floor(diffMs / (24 * 60 * 60 * 1000));
}

/** 与后端 _separation_detail_label 一致，用于看板悬停名单标签 */
function separationDetailLabel(raw) {
    const s = String(raw || '');
    if (s.includes('转出')) return '转出';
    if (s.includes('被动')) return '被动';
    if (s.includes('主动')) return '主动';
    return '未标注';
}

function normalizeOnboardingItemsForTooltip(arr) {
    if (!Array.isArray(arr) || !arr.length) return [];
    return arr
        .map((x) => {
            if (x != null && typeof x === 'object' && !Array.isArray(x)) {
                const detail = String(x.detail ?? x.text ?? '').trim();
                if (!detail) return null;
                return { detail, separation: '' };
            }
            const s = String(x).trim();
            if (!s) return null;
            return { detail: s, separation: '' };
        })
        .filter(Boolean);
}

const TURNOVER_ONBOARD_PLACEHOLDER = '（暂无名单：请点「应用」刷新看板，或确认入职时间已填写）';

createApp({
    setup() {
        const rows = ref([]);
        const showOnlyChecked = ref(false);
        const checkedRowIds = reactive({});
        const loading = ref(true);
        const fileInput = ref(null);
        const showLogs = ref(false);
        const logsLoading = ref(false);
        const logs = ref([]);
        const showDashboard = ref(false);
        const dashLoading = ref(false);
        const dashError = ref('');
        const dashData = ref(null);
        const dashScope = ref('department');
        const dashBusinessKey = ref('');
        const dashTrendMonths = ref(12);
        const dashPeriodStart = ref('');
        const dashPeriodEnd = ref('');
        const businessOptions = ref([]);

        const turnoverDashTT = reactive({
            visible: false,
            x: 12,
            y: 12,
            title: '',
            items: [],
            hovering: false,
            hideTimer: null,
        });
        const clearTurnoverDashTTHide = () => {
            if (turnoverDashTT.hideTimer != null) {
                window.clearTimeout(turnoverDashTT.hideTimer);
                turnoverDashTT.hideTimer = null;
            }
        };
        const showTurnoverDashTT = (ev, title, items, opts) => {
            const useOnboarding = opts && opts.onboarding;
            const normalized = useOnboarding
                ? normalizeOnboardingItemsForTooltip(items)
                : normalizeDepartureItemsForTooltip(items);
            if (!normalized.length) return;
            clearTurnoverDashTTHide();
            turnoverDashTT.title = title || '';
            turnoverDashTT.items = normalized;
            turnoverDashTT.visible = true;
            moveTurnoverDashTT(ev);
        };
        const moveTurnoverDashTT = (ev) => {
            if (!turnoverDashTT.visible) return;
            const pad = 14;
            let x = ev.clientX + pad;
            let y = ev.clientY + pad;
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const estW = 340;
            const estH = 300;
            if (x + estW > vw - 8) x = Math.max(8, ev.clientX - estW - pad);
            if (y + estH > vh - 8) y = Math.max(8, ev.clientY - estH - pad);
            turnoverDashTT.x = x;
            turnoverDashTT.y = y;
        };
        const hideTurnoverDashTT = () => {
            clearTurnoverDashTTHide();
            turnoverDashTT.hideTimer = window.setTimeout(() => {
                if (turnoverDashTT.hovering) return;
                turnoverDashTT.visible = false;
                turnoverDashTT.items = [];
                turnoverDashTT.title = '';
                turnoverDashTT.hideTimer = null;
            }, 120);
        };
        const onTurnoverDashTTEnter = () => {
            turnoverDashTT.hovering = true;
            clearTurnoverDashTTHide();
        };
        const onTurnoverDashTTLeave = () => {
            turnoverDashTT.hovering = false;
            hideTurnoverDashTT();
        };

        const showAddModal = ref(false);
        const addSaving = ref(false);
        const addFormReadonly = ref(false);
        const editingId = ref(null);
        const addForm = reactive({
            full_name: '',
            contact_info: '',
            customer_name: '',
            work_location: '',
            position_title: '',
            business_line: '',
            entry_date: '',
            monthly_quote_tax: '',
            pre_tax_salary: '',
            gms: '',
            gm_pct: '',
            employee_plus1: '',
            project_release_date: '',
            company_resign_date: '',
            zntx_separation_type: '',
            leave_reason: '',
            delivery_communication: '',
            business_action: '',
            bp_involved: '',
            zntx_compensation_amount: '',
        });
        const filters = reactive({
            fullName: '',
            positionTitle: '',
            workLocation: '',
            customerName: '',
            resignDateStart: '',
            resignDateEnd: '',
            tenureDaysMax: '',
            separationType: '',
            hasCompensationOnly: false,
        });
        const uniqueOptions = (key, fallbackKey) => {
            const set = new Set();
            rows.value.forEach((r) => {
                const raw = fallbackKey != null ? (r[key] || r[fallbackKey]) : r[key];
                const v = String(raw || '').trim();
                if (v) set.add(v);
            });
            return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'));
        };
        const positionTitleOptions = computed(() => uniqueOptions('position_title'));
        const workLocationOptions = computed(() => uniqueOptions('work_location'));
        const customerNameOptions = computed(() => uniqueOptions('customer_name', 'business_line'));
        const separationTypeOptions = computed(() => uniqueOptions('zntx_separation_type'));
        const hasActiveFilters = computed(() => {
            if (String(filters.fullName || '').trim()) return true;
            if (filters.positionTitle) return true;
            if (filters.workLocation) return true;
            if (filters.customerName) return true;
            if (String(filters.resignDateStart || '').trim()) return true;
            if (String(filters.resignDateEnd || '').trim()) return true;
            if (String(filters.tenureDaysMax ?? '').trim() !== '') return true;
            if (filters.separationType) return true;
            if (filters.hasCompensationOnly) return true;
            return false;
        });
        const applyRowFilters = (list) => {
            let out = list;
            const nameQ = String(filters.fullName || '').trim().toLowerCase();
            if (nameQ) {
                out = out.filter((row) => String(row.full_name || '').toLowerCase().includes(nameQ));
            }
            const ci = (v) => String(v || '').trim().toLowerCase();
            if (filters.positionTitle) {
                out = out.filter((row) => ci(row.position_title) === ci(filters.positionTitle));
            }
            if (filters.workLocation) {
                out = out.filter((row) => ci(row.work_location) === ci(filters.workLocation));
            }
            if (filters.customerName) {
                out = out.filter((row) => {
                    const disp = String(row.customer_name || row.business_line || '').trim();
                    return ci(disp) === ci(filters.customerName);
                });
            }
            const rs = String(filters.resignDateStart || '').trim();
            const re = String(filters.resignDateEnd || '').trim();
            if (rs || re) {
                const startMs = rs ? new Date(`${rs}T00:00:00`).getTime() : null;
                const endMs = re ? new Date(`${re}T23:59:59.999`).getTime() : null;
                out = out.filter((row) => {
                    const dt = normalizeDate(row.company_resign_date);
                    if (!dt || Number.isNaN(dt.getTime())) return false;
                    const t = dt.getTime();
                    if (startMs != null && Number.isFinite(startMs) && t < startMs) return false;
                    if (endMs != null && Number.isFinite(endMs) && t > endMs) return false;
                    return true;
                });
            }
            const tenureRaw = String(filters.tenureDaysMax ?? '').trim();
            if (tenureRaw !== '') {
                const maxDays = parseInt(tenureRaw, 10);
                if (Number.isFinite(maxDays)) {
                    out = out.filter((row) => {
                        const d = tenureDays(row);
                        return d !== null && d < maxDays;
                    });
                }
            }
            if (filters.separationType) {
                out = out.filter((row) => String(row.zntx_separation_type || '') === filters.separationType);
            }
            if (filters.hasCompensationOnly) {
                out = out.filter((row) => {
                    const n = parseAmount(row.zntx_compensation_amount);
                    return Number.isFinite(n) && n > 0;
                });
            }
            return out;
        };
        const clearFilters = () => {
            filters.fullName = '';
            filters.positionTitle = '';
            filters.workLocation = '';
            filters.customerName = '';
            filters.resignDateStart = '';
            filters.resignDateEnd = '';
            filters.tenureDaysMax = '';
            filters.separationType = '';
            filters.hasCompensationOnly = false;
        };
        const parseAmount = (raw) => {
            const s = String(raw || '').replace(/[¥￥,\s\u00a0]/g, '').trim();
            if (!s) return NaN;
            const n = parseFloat(s);
            return Number.isFinite(n) ? n : NaN;
        };
        const TURNOVER_AMOUNT_FIELD_KEYS = new Set([
            'monthly_quote_tax', 'pre_tax_salary', 'gms', 'zntx_compensation_amount',
        ]);
        const normalizeAmountText = (raw) => String(raw || '').replace(/[¥￥,\s\u00a0]/g, '').trim();
        const formatAmountThousandsInput = (raw) => {
            const digits = normalizeAmountText(raw);
            if (!digits) return '';
            const n = Number(digits);
            if (!Number.isFinite(n)) return String(raw || '');
            return n.toLocaleString('zh-CN', { maximumFractionDigits: 0, minimumFractionDigits: 0 });
        };
        const onAmountFieldInput = (key, e) => {
            addForm[key] = formatAmountThousandsInput(e && e.target ? e.target.value : '');
        };
        const formatAmount = (value) => {
            if (!Number.isFinite(value)) return '';
            return `¥${Math.round(value).toLocaleString('zh-CN')}`;
        };
        const isRowChecked = (rowId) => !!checkedRowIds[String(rowId)];
        const setRowChecked = (rowId, checked) => {
            checkedRowIds[String(rowId)] = !!checked;
        };
        const syncCheckedRows = (nextRows) => {
            const validIds = new Set((Array.isArray(nextRows) ? nextRows : []).map((row) => String(row.id)));
            Object.keys(checkedRowIds).forEach((id) => {
                if (!validIds.has(id)) delete checkedRowIds[id];
            });
            validIds.forEach((id) => {
                if (typeof checkedRowIds[id] !== 'boolean') checkedRowIds[id] = false;
            });
        };
        const checkedCount = computed(() => rows.value.filter((row) => isRowChecked(row.id)).length);
        const filteredRows = computed(() => {
            let list = applyRowFilters(rows.value);
            if (showOnlyChecked.value) {
                list = list.filter((row) => isRowChecked(row.id));
            }
            return list;
        });
        const displayCountHint = computed(() => {
            const n = filteredRows.value.length;
            const total = rows.value.length;
            if (!total) return '';
            const onlyChecked = showOnlyChecked.value;
            const filtered = hasActiveFilters.value;
            if (onlyChecked && filtered && n !== total) return `（勾选且筛选后 ${n} 条）`;
            if (onlyChecked) return `（勾选显示 ${n} 条）`;
            if (filtered && n !== total) return `（筛选后 ${n} 条）`;
            return '';
        });
        const emptyStateText = computed(() => {
            if (showOnlyChecked.value) {
                if (!checkedCount.value) return '暂无勾选条目';
                return hasActiveFilters.value ? '暂无符合筛选条件的勾选条目' : '暂无符合「只显示勾选」的条目';
            }
            if (hasActiveFilters.value) return '暂无符合筛选条件的数据';
            return '暂无数据';
        });
        const toggleShowCheckedOnly = () => {
            showOnlyChecked.value = !showOnlyChecked.value;
        };
        const totalCompensation = computed(() => filteredRows.value.reduce((sum, row) => {
            const n = parseAmount(row.zntx_compensation_amount);
            return sum + (Number.isFinite(n) ? n : 0);
        }, 0));
        const totalQuote = computed(() => filteredRows.value.reduce((sum, row) => {
            const n = parseAmount(row.monthly_quote_tax);
            return sum + (Number.isFinite(n) ? n : 0);
        }, 0));
        const totalProfit = computed(() => filteredRows.value.reduce((sum, row) => {
            const n = parseAmount(row.gms);
            return sum + (Number.isFinite(n) ? n : 0);
        }, 0));
        const totalProfitRate = computed(() => {
            if (!totalQuote.value) return '-';
            return `${((totalProfit.value / totalQuote.value) * 100).toFixed(2)}%`;
        });
        const addTenurePreview = computed(() => computeTenure(addForm.entry_date, addForm.company_resign_date));

        /** 趋势表内各月离职人数之和（作「离职占比」固定分母，各行相同） */
        const dashTrendMonthlyDepartureGrandTotal = () => {
            const list = dashData.value?.monthly_trend;
            if (!Array.isArray(list) || !list.length) return 0;
            return list.reduce((acc, r) => acc + Number(r?.departures ?? 0), 0);
        };
        /** 当月离职数 / 表内离职合计（占比%）；分母为整表合计，不随行递进 */
        const dashTrendRollingShareText = (row, index) => {
            const num = Number(row?.departures ?? 0);
            const den = dashTrendMonthlyDepartureGrandTotal();
            if (!den) return '0%（期内无离职）';
            const pct = ((num / den) * 100).toFixed(2);
            return `${num} / ${den}（${pct}%）`;
        };
        /** 各月离职率：分母为 0 且无离职时后端已给 0.0，此处兼容旧数据 */
        const monthlyRateCell = (row) => {
            if (row == null) return '—';
            const rp = row.rate_pct;
            if (rp != null && rp !== '') return `${rp}%`;
            if (Number(row.departures ?? 0) === 0) return '0%';
            return '—';
        };
        /** 占表内离职合计的比例，用于渐变条宽度（0–100） */
        const dashTrendRollingShareBarStyle = (row, index) => {
            const num = Number(row?.departures ?? 0);
            const den = dashTrendMonthlyDepartureGrandTotal();
            if (!den) return null;
            const w = Math.min(100, Math.max(0, (num / den) * 100));
            return { width: `${w}%` };
        };
        const dashTenureBarPct = (count) => {
            if (!dashData.value) return '0%';
            const buckets = dashData.value.tenure_buckets || [];
            let max = 0;
            buckets.forEach((t) => {
                if (t.count > max) max = t.count;
            });
            const base = max > 0 ? max : 1;
            return `${Math.min(100, (count / base) * 100)}%`;
        };
        /** 花名册整体「按业务」条：宽度相对本表最大离职数 */
        const dashBusinessBarPct = (departures) => {
            const list = dashData.value?.by_business;
            if (!Array.isArray(list) || !list.length) return '0%';
            let max = 0;
            list.forEach((b) => {
                const n = Number(b?.departures ?? 0);
                if (n > max) max = n;
            });
            const base = max > 0 ? max : 1;
            return `${Math.min(100, (Number(departures) / base) * 100)}%`;
        };

        /** 与当前看板范围一致：整体=全部离职池行；单一业务=按 client_id 过滤 */
        const dashboardContextRosterRows = () => {
            const all = Array.isArray(rows.value) ? rows.value : [];
            if (dashScope.value !== 'business') return all;
            const k = String(dashBusinessKey.value ?? '').trim();
            const opt = businessOptions.value.find((b) => String(b.short_key ?? '').trim() === k);
            const bid = opt && opt.client_id != null ? opt.client_id : null;
            // 未解析到 client 时不能用全量 rows 回退，否则单一业务格子里会混入其他客户的离职名单
            if (bid == null) return [];
            return all.filter((r) => Number(r.client_id) === Number(bid));
        };
        const _lineFromRosterRow = (row) => {
            const nm = String(row.full_name || '').trim() || '（无姓名）';
            const dt = normalizeDate(row.company_resign_date);
            let ymd = String(row.company_resign_date || '').trim() || '—';
            if (dt && !Number.isNaN(dt.getTime())) {
                ymd = `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
            }
            const cust = String(row.customer_name || row.business_line || '').trim();
            const suf = cust ? ` · ${cust}` : '';
            const detail = `${nm} · 离职日 ${ymd}${suf}`;
            return { detail, separation: separationDetailLabel(row.zntx_separation_type) };
        };
        const buildDepartureLinesFromRosterRows = (year, month) => {
            const y = Number(year);
            const m = Number(month);
            if (!Number.isFinite(y) || !Number.isFinite(m)) return [];
            const start = new Date(y, m - 1, 1);
            const end = new Date(y, m, 0, 23, 59, 59, 999);
            const out = [];
            dashboardContextRosterRows().forEach((row) => {
                const dt = normalizeDate(row.company_resign_date);
                if (!dt || dt < start || dt > end) return;
                out.push(_lineFromRosterRow(row));
            });
            out.sort((a, b) => a.detail.localeCompare(b.detail, 'zh-CN'));
            return out;
        };
        const buildDepartureLinesFromRosterRange = (isoStart, isoEnd) => {
            const d0 = normalizeDate(isoStart);
            const d1 = normalizeDate(isoEnd);
            if (!d0 || !d1) return [];
            const startMs = new Date(d0.getFullYear(), d0.getMonth(), d0.getDate()).getTime();
            const endMs = new Date(d1.getFullYear(), d1.getMonth(), d1.getDate(), 23, 59, 59, 999).getTime();
            const out = [];
            dashboardContextRosterRows().forEach((row) => {
                const dt = normalizeDate(row.company_resign_date);
                if (!dt) return;
                const t = dt.getTime();
                if (t < startMs || t > endMs) return;
                out.push(_lineFromRosterRow(row));
            });
            out.sort((a, b) => a.detail.localeCompare(b.detail, 'zh-CN'));
            return out;
        };
        const TURNOVER_DASH_PLACEHOLDER = '（暂无名单：请点「应用」刷新看板，或确认离职日期已填写）';
        const TURNOVER_BDEP_PLACEHOLDER = '（暂无名单：请点「应用」刷新看板，或确认「离职类型」含业务离职）';
        const normalizeDepartureItemsForTooltip = (arr) => {
            if (!Array.isArray(arr) || !arr.length) return [];
            return arr
                .map((x) => {
                    if (x != null && typeof x === 'object' && !Array.isArray(x)) {
                        const detail = String(x.detail ?? x.text ?? '').trim();
                        let separation = String(x.separation ?? '').trim();
                        if (!detail) return null;
                        if (detail.startsWith('（暂无')) return { detail, separation: '' };
                        if (!separation) separation = '未标注';
                        return { detail, separation };
                    }
                    const s = String(x).trim();
                    if (!s) return null;
                    if (s.startsWith('（暂无')) return { detail: s, separation: '' };
                    return { detail: s, separation: '未标注' };
                })
                .filter(Boolean);
        };
        const turnoverDepartureLinesForTooltip = (row) => {
            const direct = row?.departure_details;
            if (Array.isArray(direct) && direct.length) {
                return normalizeDepartureItemsForTooltip(direct.slice());
            }
            if (row?.year != null && row?.month != null) {
                const fb = buildDepartureLinesFromRosterRows(row.year, row.month);
                if (fb.length) return normalizeDepartureItemsForTooltip(fb);
            }
            if (Number(row?.departures) > 0) {
                return normalizeDepartureItemsForTooltip([TURNOVER_DASH_PLACEHOLDER]);
            }
            return [];
        };
        const analysisPeriodTooltipLines = () => {
            const ap = dashData.value?.analysis_period;
            if (!ap) return [];
            const direct = ap.departure_details;
            if (Array.isArray(direct) && direct.length) {
                return normalizeDepartureItemsForTooltip(direct.slice());
            }
            const fb = buildDepartureLinesFromRosterRange(ap.start, ap.end);
            if (fb.length) return normalizeDepartureItemsForTooltip(fb);
            if (Number(ap.departures) > 0) {
                return normalizeDepartureItemsForTooltip([TURNOVER_DASH_PLACEHOLDER]);
            }
            return [];
        };
        const turnoverOnboardingLinesForTooltip = (row) => {
            const direct = row?.onboarding_details;
            if (Array.isArray(direct) && direct.length) {
                return direct.slice();
            }
            if (Number(row?.onboardings) > 0) {
                return [TURNOVER_ONBOARD_PLACEHOLDER];
            }
            return [];
        };
        const analysisPeriodOnboardingTooltipLines = () => {
            const ap = dashData.value?.analysis_period;
            if (!ap) return [];
            const direct = ap.onboarding_details;
            if (Array.isArray(direct) && direct.length) {
                return direct.slice();
            }
            if (Number(ap.onboardings) > 0) {
                return [TURNOVER_ONBOARD_PLACEHOLDER];
            }
            return [];
        };
        const turnoverBusinessDepLinesForTooltip = (row) => {
            const direct = row?.business_departure_details;
            if (Array.isArray(direct) && direct.length) {
                return normalizeDepartureItemsForTooltip(direct.slice());
            }
            if (Number(row?.business_departures) > 0) {
                return normalizeDepartureItemsForTooltip([TURNOVER_BDEP_PLACEHOLDER]);
            }
            return [];
        };
        const isTurnoverDashPlaceholderOnly = (lines) =>
            Array.isArray(lines)
            && lines.length === 1
            && String(lines[0]?.detail ?? lines[0] ?? '') === TURNOVER_DASH_PLACEHOLDER;
        const isTurnoverOnboardPlaceholderOnly = (lines) =>
            Array.isArray(lines)
            && lines.length === 1
            && String(lines[0]?.detail ?? lines[0] ?? '') === TURNOVER_ONBOARD_PLACEHOLDER;
        const isTurnoverBdepPlaceholderOnly = (lines) =>
            Array.isArray(lines)
            && lines.length === 1
            && String(lines[0]?.detail ?? lines[0] ?? '') === TURNOVER_BDEP_PLACEHOLDER;
        const showTurnoverDashTTForMonthRow = (ev, row) => {
            const lines = turnoverDepartureLinesForTooltip(row);
            if (!lines.length) return;
            const n = isTurnoverDashPlaceholderOnly(lines) ? Number(row.departures) || 0 : lines.length;
            showTurnoverDashTT(ev, `${row.month_label} · 离职 ${n} 人`, lines);
        };
        const showTurnoverDashTTForOnboardMonth = (ev, row) => {
            const lines = turnoverOnboardingLinesForTooltip(row);
            if (!lines.length) return;
            const n = isTurnoverOnboardPlaceholderOnly(lines) ? Number(row.onboardings) || 0 : lines.length;
            showTurnoverDashTT(ev, `${row.month_label} · 入职 ${n} 人`, lines, { onboarding: true });
        };
        const showTurnoverDashTTForMonthBusinessDep = (ev, row) => {
            const lines = turnoverBusinessDepLinesForTooltip(row);
            if (!lines.length) return;
            const n = isTurnoverBdepPlaceholderOnly(lines) ? Number(row.business_departures) || 0 : lines.length;
            showTurnoverDashTT(ev, `${row.month_label} · 业务离职 ${n} 人`, lines);
        };
        const showTurnoverDashTTForAnalysisPeriod = (ev) => {
            const lines = analysisPeriodTooltipLines();
            if (!lines.length) return;
            const ap = dashData.value?.analysis_period;
            const n = isTurnoverDashPlaceholderOnly(lines) ? Number(ap?.departures) || 0 : lines.length;
            showTurnoverDashTT(ev, `分析期内离职 ${n} 人`, lines);
        };
        const showTurnoverDashTTForAnalysisOnboarding = (ev) => {
            const lines = analysisPeriodOnboardingTooltipLines();
            if (!lines.length) return;
            const ap = dashData.value?.analysis_period;
            const n = isTurnoverOnboardPlaceholderOnly(lines) ? Number(ap?.onboardings) || 0 : lines.length;
            showTurnoverDashTT(ev, `分析期内入职 ${n} 人`, lines, { onboarding: true });
        };

        const loadDashboard = async () => {
            dashLoading.value = true;
            dashError.value = '';
            try {
                await loadRows();
                const params = new URLSearchParams();
                params.set('scope', dashScope.value);
                if (dashScope.value === 'business' && dashBusinessKey.value) {
                    params.set('business_key', dashBusinessKey.value);
                }
                params.set('trend_months', String(dashTrendMonths.value));
                if (dashPeriodStart.value) params.set('period_start', dashPeriodStart.value);
                if (dashPeriodEnd.value) params.set('period_end', dashPeriodEnd.value);
                const r = await fetch(`/api/roster/turnover/dashboard?${params.toString()}`, {
                    headers: window.crmAuthHeader(),
                });
                if (!r.ok) {
                    let msg = `加载失败（HTTP ${r.status}）`;
                    try {
                        const err = await r.json();
                        if (typeof err.detail === 'string') msg = err.detail;
                    } catch (e) {}
                    dashError.value = msg;
                    dashData.value = null;
                    return;
                }
                const j = await r.json();
                /** 兼容旧版 API 未带 separation.transfer 时，转出「占比」在 0 人、期内有离职时补 0%。占比分母为同期总离职数。 */
                if (j && j.separation && typeof j.separation === 'object') {
                    const depN = j.analysis_period && Number(j.analysis_period.departures);
                    const canShare = Number.isFinite(depN) && depN > 0;
                    if (j.separation.transfer == null) {
                        j.separation.transfer = { count: 0, rate_pct: canShare ? 0 : null };
                    } else if (
                        j.separation.transfer.count === 0
                        && j.separation.transfer.rate_pct == null
                        && canShare
                    ) {
                        j.separation.transfer.rate_pct = 0;
                    }
                }
                dashData.value = j;
                if (Array.isArray(j.business_options) && j.business_options.length) {
                    businessOptions.value = j.business_options;
                    const keys = new Set(j.business_options.map((b) => b.short_key));
                    if (!dashBusinessKey.value || !keys.has(dashBusinessKey.value)) {
                        dashBusinessKey.value = j.business_options[0].short_key;
                    }
                }
            } catch (e) {
                dashError.value = '网络错误';
                dashData.value = null;
            } finally {
                dashLoading.value = false;
            }
        };
        const openDashboard = () => {
            const { start, end } = defaultDashboardAnalysisPeriod();
            dashPeriodStart.value = start;
            dashPeriodEnd.value = end;
            showDashboard.value = true;
            loadDashboard();
        };
        const resetDashboardFilters = () => {
            dashScope.value = 'department';
            dashTrendMonths.value = 12;
            const { start, end } = defaultDashboardAnalysisPeriod();
            dashPeriodStart.value = start;
            dashPeriodEnd.value = end;
            if (Array.isArray(businessOptions.value) && businessOptions.value.length) {
                dashBusinessKey.value = businessOptions.value[0].short_key;
            } else {
                dashBusinessKey.value = '';
            }
            loadDashboard();
        };
        const closeDashboard = () => {
            showDashboard.value = false;
            clearTurnoverDashTTHide();
            turnoverDashTT.visible = false;
            turnoverDashTT.items = [];
            turnoverDashTT.title = '';
            turnoverDashTT.hovering = false;
        };
        const onDashScopeChange = () => {
            if (dashScope.value === 'business' && businessOptions.value.length && !dashBusinessKey.value) {
                dashBusinessKey.value = businessOptions.value[0].short_key;
            }
        };

        const loadRows = async () => {
            loading.value = true;
            try {
                const r = await fetch('/api/roster/turnover', { headers: window.crmAuthHeader() });
                const list = r.ok ? await r.json() : [];
                const normalized = Array.isArray(list) ? list.map((row) => ({
                    ...row,
                    tenure: computeTenure(row.entry_date, row.company_resign_date),
                    delivery_communication: String(row.delivery_communication || '').trim(),
                    business_action: String(row.business_action || '').trim(),
                    bp_involved: String(row.bp_involved || '').trim(),
                })) : [];
                rows.value = normalized;
                syncCheckedRows(normalized);
            } finally {
                loading.value = false;
            }
        };

        watch(rows, (v) => syncCheckedRows(v), { deep: true });

        const resetAddForm = () => {
            Object.assign(addForm, {
                full_name: '',
                contact_info: '',
                customer_name: '',
                work_location: '',
                position_title: '',
                business_line: '',
                entry_date: '',
                monthly_quote_tax: '',
                pre_tax_salary: '',
                gms: '',
                gm_pct: '',
                employee_plus1: '',
                project_release_date: '',
                company_resign_date: '',
                zntx_separation_type: '',
                leave_reason: '',
                delivery_communication: '',
                business_action: '',
                bp_involved: '',
                zntx_compensation_amount: '',
            });
        };
        const openAddForm = () => {
            resetAddForm();
            editingId.value = null;
            addFormReadonly.value = false;
            showAddModal.value = true;
        };
        const fillAddFormFromRow = (row) => {
            Object.assign(addForm, {
                full_name: String(row.full_name || ''),
                contact_info: String(row.contact_info || ''),
                customer_name: String(row.customer_name || ''),
                work_location: String(row.work_location || ''),
                position_title: String(row.position_title || ''),
                business_line: String(row.business_line || ''),
                entry_date: String(row.entry_date || ''),
                monthly_quote_tax: formatAmountThousandsInput(row.monthly_quote_tax),
                pre_tax_salary: formatAmountThousandsInput(row.pre_tax_salary),
                gms: formatAmountThousandsInput(row.gms),
                gm_pct: String(row.gm_pct || ''),
                employee_plus1: String(row.employee_plus1 || ''),
                project_release_date: String(row.project_release_date || ''),
                company_resign_date: String(row.company_resign_date || ''),
                zntx_separation_type: String(row.zntx_separation_type || ''),
                leave_reason: String(row.leave_reason || ''),
                delivery_communication: String(row.delivery_communication || ''),
                business_action: String(row.business_action || ''),
                bp_involved: String(row.bp_involved || ''),
                zntx_compensation_amount: formatAmountThousandsInput(row.zntx_compensation_amount),
            });
        };
        const openDetail = (row) => {
            fillAddFormFromRow(row);
            editingId.value = parseRosterRowId(row);
            addFormReadonly.value = true;
            showAddModal.value = true;
        };
        const openEdit = (row) => {
            fillAddFormFromRow(row);
            editingId.value = parseRosterRowId(row);
            addFormReadonly.value = false;
            showAddModal.value = true;
        };
        const closeAddForm = () => {
            showAddModal.value = false;
            addFormReadonly.value = false;
            editingId.value = null;
        };
        const saveAddForm = async () => {
            if (addFormReadonly.value) return;
            const required = [
                ['full_name', '姓名'],
                ['contact_info', '联系方式'],
                ['customer_name', '客户'],
                ['work_location', '工作地'],
                ['position_title', '岗位'],
                ['business_line', '项目'],
                ['entry_date', '入职时间'],
                ['monthly_quote_tax', '报价'],
                ['pre_tax_salary', '薪资'],
                ['gms', 'GM$'],
                ['gm_pct', 'GM%'],
            ];
            const missing = required.filter(([key]) => !String(addForm[key] || '').trim()).map(([, label]) => label);
            if (missing.length) {
                alert(`请补全必填项：${missing.join('、')}`);
                return;
            }
            addSaving.value = true;
            try {
                const payload = {
                    ...addForm,
                    employment_status: (String(addForm.company_resign_date || '').trim() || String(addForm.leave_reason || '').trim() || String(addForm.zntx_separation_type || '').trim())
                        ? '离职'
                        : '在职',
                };
                TURNOVER_AMOUNT_FIELD_KEYS.forEach((key) => {
                    payload[key] = normalizeAmountText(payload[key]);
                });
                const isEdit = editingId.value != null;
                const r = await fetch(isEdit ? `/api/roster/${editingId.value}` : '/api/roster', {
                    method: isEdit ? 'PUT' : 'POST',
                    headers: { ...window.crmAuthHeader(), 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!r.ok) {
                    let msg = `保存失败（HTTP ${r.status}）`;
                    try {
                        const err = await r.json();
                        if (typeof err.detail === 'string') msg = err.detail;
                    } catch (err) {}
                    alert(msg);
                    return;
                }
                closeAddForm();
                await loadRows();
            } finally {
                addSaving.value = false;
            }
        };
        const removeRow = async (row) => {
            const r = await fetch(`/api/roster/${row.id}`, { method: 'DELETE', headers: window.crmAuthHeader() });
            if (!r.ok) {
                alert('删除失败');
                return;
            }
            await loadRows();
        };
        const triggerImport = () => {
            if (fileInput.value) fileInput.value.click();
        };
        const onImportFile = async (e) => {
            const f = e.target.files && e.target.files[0];
            if (!f) return;
            const token = window.prompt('该操作会先备份并清空「离职档案池」，再导入新 CSV（不会删除在职花名册）。\n请输入 CONFIRM 继续：', '');
            if (token == null) {
                e.target.value = '';
                return;
            }
            const fd = new FormData();
            fd.append('file', f);
            fd.append('confirm', token);
            const r = await fetch('/api/roster/turnover/import', {
                method: 'POST',
                headers: window.crmAuthHeader(),
                body: fd,
            });
            e.target.value = '';
            if (!r.ok) {
                let msg = `导入失败（HTTP ${r.status}）`;
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') msg = err.detail;
                } catch (err) {}
                alert(msg);
                return;
            }
            const j = await r.json();
            const lines = [
                '导入完成',
                `备份文件：${j.backup_file || '无（原数据为空）'}`,
                `导入成功：${j.imported || 0} 行`,
                `跳过重复：${j.skipped_duplicates || 0} 行`,
                `跳过空行：${j.skipped_empty || 0} 行`,
                `识别表头：${j.matched_headers_count || 0} 列`,
            ];
            const unmatchedHeaders = Array.isArray(j.unmatched_headers) ? j.unmatched_headers : [];
            if (unmatchedHeaders.length) {
                lines.push('');
                lines.push(`未识别表头（${unmatchedHeaders.length}）：${unmatchedHeaders.join('、')}`);
            }
            const details = Array.isArray(j.skipped_details) ? j.skipped_details : [];
            if (details.length) {
                lines.push('');
                lines.push('跳过明细（最多前8条）：');
                details.slice(0, 8).forEach((item, idx) => {
                    const serial = String(item && item.serial_no != null ? item.serial_no : `第${idx + 1}条`);
                    const reason = String(item && item.reason != null ? item.reason : '');
                    const contact = String(item && item.contact_info != null ? item.contact_info : '').trim();
                    const contactPart = contact ? `，联系方式：${contact}` : '';
                    lines.push(`${idx + 1}. ${serial}（${reason}${contactPart}）`);
                });
                if (details.length > 8) {
                    lines.push(`...其余 ${details.length - 8} 条请查看日志`);
                }
            }
            alert(lines.join('\n'));
            await loadRows();
        };
        const exportCsv = async () => {
            const r = await fetch('/api/roster/turnover/export', { headers: window.crmAuthHeader() });
            if (!r.ok) {
                alert('导出失败');
                return;
            }
            const disposition = r.headers.get('Content-Disposition') || '';
            const blob = await r.blob();
            window.crmDownloadBlob(blob, disposition, `离职率分析_离职档案_${Date.now()}.csv`);
        };
        const loadLogs = async () => {
            logsLoading.value = true;
            try {
                const r = await fetch('/api/roster/logs', { headers: window.crmAuthHeader() });
                logs.value = r.ok ? await r.json() : [];
            } finally {
                logsLoading.value = false;
            }
        };
        const openLogs = async () => {
            showLogs.value = true;
            await loadLogs();
        };
        const closeLogs = () => {
            showLogs.value = false;
        };
        const formatDate = (ds) => {
            if (!ds) return '-';
            const t = new Date(ds);
            return Number.isNaN(t.getTime()) ? String(ds) : t.toLocaleString();
        };
        const restoreLatestBackup = async () => {
            const ok = window.confirm('将使用「最近一次离职档案备份」覆盖当前离职池，是否继续？（不影响在职花名册）');
            if (!ok) return;
            const r = await fetch('/api/roster/turnover/restore/latest', {
                method: 'POST',
                headers: window.crmAuthHeader(),
            });
            if (!r.ok) {
                let msg = '回滚失败';
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') msg = err.detail;
                } catch (e) {}
                alert(msg);
                return;
            }
            const j = await r.json();
            alert(`已从备份 ${j.backup_file} 回滚，清空 ${j.cleared_existing || 0} 行，恢复 ${j.restored_rows || 0} 行`);
            await loadRows();
            if (showLogs.value) await loadLogs();
        };

        onMounted(async () => {
            await loadRows();
            window.crmScheduleTableColumnResize?.();
        });
        return {
            rows, filteredRows, loading,
            filters, positionTitleOptions, workLocationOptions, customerNameOptions, separationTypeOptions,
            clearFilters,
            showOnlyChecked, displayCountHint, emptyStateText,
            isRowChecked, setRowChecked, toggleShowCheckedOnly,
            totalCompensation, totalQuote, totalProfit, totalProfitRate, formatAmount, parseAmount,
            fileInput, triggerImport, onImportFile, exportCsv, restoreLatestBackup,
            showDashboard, dashLoading, dashError, dashData, dashScope, dashBusinessKey, dashTrendMonths,
            dashPeriodStart, dashPeriodEnd, businessOptions,
            turnoverDashTT,
            showTurnoverDashTT, showTurnoverDashTTForMonthRow, showTurnoverDashTTForOnboardMonth, showTurnoverDashTTForMonthBusinessDep, showTurnoverDashTTForAnalysisPeriod, showTurnoverDashTTForAnalysisOnboarding,
            moveTurnoverDashTT, hideTurnoverDashTT, onTurnoverDashTTEnter, onTurnoverDashTTLeave,
            openDashboard, closeDashboard, loadDashboard, resetDashboardFilters, onDashScopeChange, dashTrendRollingShareText, dashTrendRollingShareBarStyle, monthlyRateCell, dashTenureBarPct, dashBusinessBarPct,
            turnoverDepartureLinesForTooltip, analysisPeriodTooltipLines,
            showAddModal, addForm, addSaving, addFormReadonly, editingId, addTenurePreview, openAddForm, closeAddForm, saveAddForm, onAmountFieldInput,
            openDetail, openEdit, removeRow,
            showLogs, logsLoading, logs, openLogs, closeLogs, formatDate,
        };
    }
}).mount('#delivery-turnover-app');
