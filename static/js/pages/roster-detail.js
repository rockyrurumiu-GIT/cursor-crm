/**
 * Roster detail page logic.
 * Extracted from templates/pages/roster_detail.html (Phase 28).
 * Requires: Vue 3 CDN; window.__ROSTER_CLIENT_ID__ set in template before this script.
 */

const { createApp, ref, onMounted, reactive, computed, watch, nextTick } = Vue;
const CLIENT_ID = window.__ROSTER_CLIENT_ID__;
const IS_GLOBAL_ROSTER = !CLIENT_ID || Number(CLIENT_ID) === 0;
/** 与 GM 测算器一致：不含税月报价 = 含税月报价 ÷ 1.0672 */
const TAX_DIVISOR = 1.0672;
const THROME_STAFF_NO_FIELD = { key: 'throme_staff_no', label: '索摩工号' };
const STANDARD_FORM_FIELDS = [
    { key: 'serial_no', label: '序号' },
    { key: 'full_name', label: '姓名' },
    { key: 'employment_status', label: '在职情况' },
    { key: 'regularization_status', label: '转正' },
    THROME_STAFF_NO_FIELD,
    { key: 'contact_info', label: '联系方式' },
    { key: 'customer_name', label: '客户' },
    { key: 'work_location', label: '工作地' },
    { key: 'position_title', label: '岗位' },
    { key: 'business_line', label: '业务线' },
    { key: 'entry_date', label: '入职日期' },
    { key: 'regularization_date', label: '转正时间' },
    { key: 'monthly_quote_tax', label: '月报价(含税)' },
    { key: 'pre_tax_salary', label: '税前工资' },
    { key: 'salary_quote_ratio', label: '薪资报价比' },
    { key: 'gms', label: 'GM$' },
    { key: 'gm_pct', label: 'GM%' },
    { key: 'employee_plus1', label: '员工+1' },
    { key: 'zntx_onboarding_channel', label: '入职渠道' },
    { key: 'employee_plus2', label: '员工+2' },
    { key: 'interface_contact', label: '接口' },
    { key: 'project_release_date', label: '项目释放日期' },
    { key: 'company_resign_date', label: '公司离职日期' },
    { key: 'leave_reason', label: '离职或释放原因' },
    { key: 'remarks', label: '备注' },
];
/** 下列客户（及整体花名册）表格与表单不展示这三项，与中诺视图一致不占列 */
const HIDE_RELEASE_LEAVE_FIELD_KEYS = ['project_release_date', 'company_resign_date', 'leave_reason'];
/** 新增行时不展示、无需填写 */
const ROSTER_FORM_HIDDEN_FIELD_KEYS = new Set(['serial_no']);
const ROSTER_ADD_ONLY_HIDDEN_FIELD_KEYS = new Set(HIDE_RELEASE_LEAVE_FIELD_KEYS);
function standardFormFieldsWithoutReleaseLeave() {
    return STANDARD_FORM_FIELDS.filter((f) => !HIDE_RELEASE_LEAVE_FIELD_KEYS.includes(f.key));
}
const ZNTX_FORM_FIELDS = [
    { key: 'serial_no', label: '序号' },
    { key: 'full_name', label: '姓名' },
    { key: 'employment_status', label: '在职情况' },
    { key: 'regularization_status', label: '转正' },
    THROME_STAFF_NO_FIELD,
    { key: 'zntx_staff_no', label: '工号' },
    { key: 'contact_info', label: '联系方式' },
    { key: 'customer_name', label: '客户' },
    { key: 'work_location', label: '工作地' },
    { key: 'position_title', label: '岗位' },
    { key: 'business_line', label: '业务线' },
    { key: 'entry_date', label: '入职时间' },
    { key: 'regularization_date', label: '转正时间' },
    { key: 'monthly_quote_tax', label: '月报价(含税)' },
    { key: 'pre_tax_salary', label: '税前工资' },
    { key: 'salary_quote_ratio', label: '薪资报价比' },
    { key: 'gms', label: 'GM$' },
    { key: 'gm_pct', label: 'GM%' },
    { key: 'employee_plus1', label: '员工+1' },
    { key: 'zntx_onboarding_channel', label: '入职渠道' },
    { key: 'zntx_attendance_checkin', label: '打卡' },
    { key: 'employee_plus2', label: '员工+2' },
    { key: 'interface_contact', label: '接口' },
    { key: 'remarks', label: '备注' },
];
const DETAIL_TEXTAREA_KEYS = new Set(['remarks', 'leave_reason']);
const FORM_FIELDS = [
    ...STANDARD_FORM_FIELDS,
    { key: 'zntx_staff_no', label: '工号' },
    { key: 'zntx_attendance_checkin', label: '打卡' },
    { key: 'zntx_attendance_makeup', label: '补卡' },
    { key: 'zntx_separation_type', label: '离职类型' },
    { key: 'zntx_compensation_amount', label: '补偿金' },
];
const REQUIRED_FIELD_KEYS = new Set([
    'employment_status',
    'full_name',
    'contact_info',
    'customer_name',
    'work_location',
    'position_title',
    'business_line',
    'entry_date',
    'regularization_status',
    'monthly_quote_tax',
    'pre_tax_salary',
    'gms',
    'gm_pct',
]);
const DATE_FIELD_KEYS = new Set([
    'entry_date',
    'regularization_date',
    'project_release_date',
    'company_resign_date',
]);
function emptyForm() {
    const o = {};
    FORM_FIELDS.forEach((f) => { o[f.key] = ''; });
    o.zntx_onboarding_channel_other = '';
    o.regularization_status = '未转正';
    return o;
}
/** 从单元格文本解析金额（¥、千分位、空格等） */
function parseAmountCell(str) {
    if (str == null || str === '') return NaN;
    const s = String(str).replace(/[¥￥,\s\u00a0]/g, '').trim();
    if (s === '') return NaN;
    const n = parseFloat(s);
    return Number.isFinite(n) ? n : NaN;
}
function normalizeAmountText(str) {
    return String(str || '').replace(/[¥￥,\s\u00a0]/g, '').trim();
}
const ROSTER_AMOUNT_FIELD_KEYS = new Set(['monthly_quote_tax', 'pre_tax_salary', 'gms']);
const GM_CALC_OUTPUT_FIELD_KEYS = new Set(['gms', 'gm_pct']);
function formatAmountThousandsInput(raw) {
    const digits = normalizeAmountText(raw);
    if (!digits) return '';
    const n = Number(digits);
    if (!Number.isFinite(n)) return String(raw || '');
    return n.toLocaleString('zh-CN', { maximumFractionDigits: 0, minimumFractionDigits: 0 });
}
function isValidSalaryAmountInput(raw) {
    const normalized = normalizeAmountText(raw);
    return /^\d{4,6}$/.test(normalized);
}
/** 合计金额：四舍五入到元，不显示小数 */
function formatYuanInteger(n) {
    if (!Number.isFinite(n)) return '—';
    const r = Math.round(n);
    return '¥' + r.toLocaleString('zh-CN', { maximumFractionDigits: 0, minimumFractionDigits: 0 });
}
/** 表格单元格：可解析为数字时四舍五入到个位元展示，否则保留原文 */
function displayAmountInteger(str) {
    if (str == null || String(str).trim() === '') return '';
    const n = parseAmountCell(str);
    if (!Number.isFinite(n)) return String(str);
    return formatYuanInteger(n);
}
function displayRosterDate(str) {
    const s = String(str || '').trim();
    if (!s) return '';
    const m = s.match(/^(\d{4})\D(\d{1,2})\D(\d{1,2})$/);
    if (!m) return s;
    const y = m[1];
    const moNum = parseInt(m[2], 10);
    const dNum = parseInt(m[3], 10);
    if (!Number.isFinite(moNum) || !Number.isFinite(dNum)) return s;
    const mo = String(moNum).padStart(2, '0');
    const d = String(dNum).padStart(2, '0');
    return `${y}/${mo}/${d}`;
}
function todayInputDate() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}
function normalizeDateForInput(raw, fallbackTodayIfEmpty = false) {
    const s = String(raw || '').trim();
    if (!s) return fallbackTodayIfEmpty ? todayInputDate() : '';
    const m = s.match(/^(\d{4})\D?(\d{1,2})\D?(\d{1,2})$/);
    if (!m) return s;
    const y = m[1];
    const mo = String(parseInt(m[2], 10)).padStart(2, '0');
    const d = String(parseInt(m[3], 10)).padStart(2, '0');
    if (mo === 'NaN' || d === 'NaN') return s;
    return `${y}-${mo}-${d}`;
}
/** 与筛选条入职日期比较逻辑一致：可解析时返回 YYYYMMDD 整数，否则 null */
function rosterDateSortKey(raw) {
    const normalized = normalizeDateForInput(raw, false);
    if (!normalized) return null;
    const m = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return null;
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    const d = parseInt(m[3], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
    return y * 10000 + mo * 100 + d;
}
function rosterDateDiffDays(entryRaw, regRaw) {
    const entryKey = rosterDateSortKey(entryRaw);
    const regKey = rosterDateSortKey(regRaw);
    if (entryKey == null || regKey == null) return null;
    const toDate = (key) => {
        const y = Math.floor(key / 10000);
        const mo = Math.floor((key % 10000) / 100) - 1;
        const d = key % 100;
        return new Date(y, mo, d);
    };
    const ms = toDate(regKey).getTime() - toDate(entryKey).getTime();
    return Math.round(ms / 86400000);
}

function isValidGmPctInput(raw) {
    const s = String(raw || '').trim();
    if (!s) return true;
    const normalized = s.replace('％', '%');
    if (normalized.includes('%')) {
        return /^(100(?:\.0{1,2})?|[1-9]?\d(?:\.\d{1,2})?)%$/.test(normalized);
    }
    const n = parseFloat(normalized);
    return Number.isFinite(n) && n >= 0 && n <= 100;
}
/** GM% 展示/提交：数字部分自动补全 % 后缀 */
function formatGmPctWithSymbol(raw) {
    const s = String(raw || '').trim().replace(/％/g, '%');
    if (!s) return '';
    const digits = s.endsWith('%') ? s.slice(0, -1).trim() : s;
    if (!digits) return '';
    return digits + '%';
}
const GM_PCT_COMPLETE_RE = /^(100(?:\.0{1,2})?|[1-9]?\d(?:\.\d{1,2})?)$/;
const ONBOARDING_CHANNEL_OPTIONS = ['内部RMS', 'Boss', 'linkedin', '猎聘', '内推', '挂靠', '外协', '其他'];
const ONBOARDING_CHANNEL_LEGACY = { 平台: '内部RMS' };
function normalizeOnboardingChannelForForm(storedChannel) {
    const s = String(storedChannel || '').trim();
    if (!s) return '';
    if (ONBOARDING_CHANNEL_LEGACY[s]) return ONBOARDING_CHANNEL_LEGACY[s];
    return s;
}
function buildOnboardingChannelSelectOptions(currentChannel) {
    const options = [...ONBOARDING_CHANNEL_OPTIONS];
    const current = normalizeOnboardingChannelForForm(currentChannel);
    if (current && !options.includes(current)) {
        const otherIdx = options.indexOf('其他');
        if (otherIdx >= 0) options.splice(otherIdx, 0, current);
        else options.push(current);
    }
    return options;
}
/** 比率转百分比展示，与行内「79.55%」形式一致 */
function formatRatioAsPercent(ratio) {
    if (!Number.isFinite(ratio)) return '—';
    return (ratio * 100).toFixed(2) + '%';
}
const ROSTER_ADD_QUERY_KEYS = [
    'roster_add',
    'prefill_full_name',
    'prefill_position_title',
    'prefill_work_location',
    'from_calc',
    'prefill_monthly_quote_tax',
    'prefill_pre_tax_salary',
    'prefill_gms',
    'prefill_gm_pct',
];
const ROSTER_KEYWORD_SEARCH_FIELDS = [
    'full_name',
    'contact_info',
    'employment_status',
    'regularization_status',
    'customer_name',
    'work_location',
    'position_title',
    'business_line',
    'employee_plus1',
    'employee_plus2',
    'interface_contact',
    'zntx_staff_no',
    'zntx_onboarding_channel',
    'remarks',
];
function rowMatchesRosterKeyword(row, keyword) {
    const q = String(keyword || '').trim().toLowerCase();
    if (!q) return true;
    return ROSTER_KEYWORD_SEARCH_FIELDS.some((key) => String(row[key] || '').toLowerCase().includes(q));
}
const rosterDetailApp = createApp({
    setup() {
        const rows = ref([]);
        const brief = ref({ name: '', owner: '' });
        const loading = ref(true);
        const showOnlyChecked = ref(false);
        const filterPanelExpanded = ref(false);
        const rosterScrollWrap = ref(null);
        const checkedRowIds = reactive({});
        const showForm = ref(false);
        const editingId = ref(null);
        const formReadonly = ref(false);
        const calcFieldsLocked = ref(false);
        const form = reactive(emptyForm());
        watch(
            () => [form.monthly_quote_tax, form.pre_tax_salary],
            () => {
                if (formReadonly.value) return;
                const q = parseAmountCell(form.monthly_quote_tax);
                const p = parseAmountCell(form.pre_tax_salary);
                if (!Number.isFinite(q) || !Number.isFinite(p) || q <= 0) {
                    form.salary_quote_ratio = '';
                } else {
                    form.salary_quote_ratio = formatRatioAsPercent(p / q);
                }
            },
        );
        const fileInput = ref(null);
        const filters = reactive({
            keyword: '',
            customerName: '',
            workLocation: '',
            regularizationStatus: '',
            entryDateBefore: '',
            entryDateAfter: '',
            gmsBelow: '',
            gmPctBelow: '',
            positionTitle: '',
            preTaxSalaryAbove: '',
            preTaxSalaryBelow: '',
        });
        const showLogs = ref(false);
        const logsLoading = ref(false);
        const logs = ref([]);
        const showValidation = ref(false);
        const validationScope = ref('');
        const validationFindings = ref([]);
        const validationCopied = ref(false);
        const showRegReminder = ref(false);
        const regReminderFindings = ref([]);
        const regReminderCopied = ref(false);
        const regDetailRow = ref(null);
        const regularizingId = ref(null);
        const touchedFields = reactive({});
        const crmClients = ref([]);
        const authHeader = () => window.crmAuthHeader();
        const canUseGmCalc = computed(() => {
            return !!window.crmIsSuper || !!window.crmHasPermission?.('tools.gm_calc.read');
        });
        const canViewRosterLogs = computed(() => !!window.crmIsSuper);
        const rosterCustomerSelectOptions = computed(() => {
            const names = (crmClients.value || [])
                .map((c) => String(c && c.name != null ? c.name : '').trim())
                .filter(Boolean);
            const uniq = [...new Set(names)];
            uniq.sort((a, b) => a.localeCompare(b, 'zh-CN'));
            const cur = String(form.customer_name || '').trim();
            if (cur && !uniq.includes(cur)) {
                return [cur, ...uniq];
            }
            return uniq;
        });
        const isZNTX = computed(() => {
            if (IS_GLOBAL_ROSTER) return true;
            const raw = String(brief.value?.name || '')
                .replace(/\s+/g, '')
                .replace(/[（）()]/g, '');
            return raw.includes('中诺通讯');
        });
        /** 元枢/KPIT/日产/帷幄/华勤：不展示项目释放与离职相关三列（整体花名册沿用中诺式布局，本来就不含这三列） */
        const hideReleaseLeaveCols = computed(() => {
            const raw = String(brief.value?.name || '')
                .replace(/\s+/g, '')
                .replace(/[（）()]/g, '');
            const upper = raw.toUpperCase();
            return (
                raw.includes('元枢')
                || upper.includes('KPIT')
                || raw.includes('日产')
                || raw.includes('帷幄')
                || raw.includes('华勤')
            );
        });
        const showStdReleaseLeaveCols = computed(() => !isZNTX.value && !hideReleaseLeaveCols.value);
        const emptyRowColspan = computed(() => {
            if (isZNTX.value) return 24;
            return hideReleaseLeaveCols.value ? 22 : 25;
        });
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
        /** 标准布局表尾「备注」占位：有离职三列时为 colspan 4，隐藏三列时为 1 */
        const rosterFooterRemarkColspan = computed(() => (hideReleaseLeaveCols.value ? 1 : 4));
        const hasFieldData = (key) => rows.value.some((r) => String(r[key] || '').trim() !== '');
        const uniqueOptions = (key) => {
            const set = new Set();
            rows.value.forEach((r) => {
                const v = String(r[key] || '').trim();
                if (v) set.add(v);
            });
            return Array.from(set).sort((a, b) => a.localeCompare(b, 'zh-CN'));
        };
        const workLocationOptions = computed(() => uniqueOptions('work_location'));
        const customerNameOptions = computed(() => uniqueOptions('customer_name'));
        const positionTitleOptions = computed(() => uniqueOptions('position_title'));
        const tableFieldKeys = computed(() => {
            let fields;
            if (isZNTX.value) fields = ZNTX_FORM_FIELDS;
            else if (hideReleaseLeaveCols.value) fields = standardFormFieldsWithoutReleaseLeave();
            else fields = STANDARD_FORM_FIELDS;
            return new Set(fields.map((f) => f.key));
        });
        const FILTER_FIELD_MAP = {
            customerName: 'customer_name',
            workLocation: 'work_location',
            regularizationStatus: 'regularization_status',
            entryDateBefore: 'entry_date',
            entryDateAfter: 'entry_date',
            gmsBelow: 'gms',
            gmPctBelow: 'gm_pct',
            positionTitle: 'position_title',
            preTaxSalaryAbove: 'pre_tax_salary',
            preTaxSalaryBelow: 'pre_tax_salary',
        };
        const hasFilterField = (filterKey) => {
            if (filterKey === 'keyword') return true;
            if (filterKey === 'customerName') return IS_GLOBAL_ROSTER;
            const fieldKey = FILTER_FIELD_MAP[filterKey];
            if (!fieldKey) return false;
            return tableFieldKeys.value.has(fieldKey);
        };
        const filteredRows = computed(() => {
            const ci = (v) => String(v || '').trim().toLowerCase();
            return rows.value.filter((row) => {
                if (!rowMatchesRosterKeyword(row, filters.keyword)) return false;
                if (filters.workLocation && hasFieldData('work_location') && ci(row.work_location) !== ci(filters.workLocation)) return false;
                if (filters.regularizationStatus) {
                    const status = String(row.regularization_status || '未转正').trim();
                    if (status !== filters.regularizationStatus) return false;
                }
                if (filters.entryDateBefore) {
                    const toDateKey = (v) => {
                        const s = String(v || '').trim();
                        if (!s) return null;
                        const m = s.match(/(\d{4})\D?(\d{1,2})\D?(\d{1,2})/);
                        if (!m) return null;
                        const y = parseInt(m[1], 10);
                        const mo = parseInt(m[2], 10);
                        const d = parseInt(m[3], 10);
                        if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
                        return y * 10000 + mo * 100 + d;
                    };
                    const rowKey = toDateKey(row.entry_date);
                    const limitKey = toDateKey(filters.entryDateBefore);
                    if (limitKey && rowKey && !(rowKey < limitKey)) return false;
                    if (limitKey && !rowKey) return false;
                }
                if (filters.entryDateAfter) {
                    const toDateKey = (v) => {
                        const s = String(v || '').trim();
                        if (!s) return null;
                        const m = s.match(/(\d{4})\D?(\d{1,2})\D?(\d{1,2})/);
                        if (!m) return null;
                        const y = parseInt(m[1], 10);
                        const mo = parseInt(m[2], 10);
                        const d = parseInt(m[3], 10);
                        if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
                        return y * 10000 + mo * 100 + d;
                    };
                    const rowKey = toDateKey(row.entry_date);
                    const limitKey = toDateKey(filters.entryDateAfter);
                    if (limitKey && rowKey && !(rowKey > limitKey)) return false;
                    if (limitKey && !rowKey) return false;
                }
                if (String(filters.gmsBelow).trim() !== '') {
                    const limit = parseFloat(String(filters.gmsBelow));
                    const g = parseAmountCell(row.gms);
                    if (Number.isFinite(limit) && (!Number.isFinite(g) || !(g < limit))) return false;
                }
                if (String(filters.gmPctBelow).trim() !== '') {
                    const limit = parseFloat(String(filters.gmPctBelow));
                    const p = (() => {
                        const s0 = String(row.gm_pct || '').trim().replace('％', '%');
                        if (!s0) return NaN;
                        if (s0.includes('%')) {
                            const n = parseFloat(s0.replace('%', '').trim());
                            return Number.isFinite(n) ? n : NaN;
                        }
                        const n = parseFloat(s0);
                        if (!Number.isFinite(n)) return NaN;
                        return n <= 1 ? n * 100 : n;
                    })();
                    if (Number.isFinite(limit) && (!Number.isFinite(p) || !(p < limit))) return false;
                }
                if (String(filters.preTaxSalaryAbove).trim() !== '') {
                    const limit = parseFloat(String(filters.preTaxSalaryAbove));
                    const preSalary = parseAmountCell(row.pre_tax_salary);
                    if (Number.isFinite(limit) && (!Number.isFinite(preSalary) || !(preSalary > limit))) return false;
                }
                if (String(filters.preTaxSalaryBelow).trim() !== '') {
                    const limit = parseFloat(String(filters.preTaxSalaryBelow));
                    const preSalary = parseAmountCell(row.pre_tax_salary);
                    if (Number.isFinite(limit) && (!Number.isFinite(preSalary) || !(preSalary < limit))) return false;
                }
                if (filters.positionTitle && hasFieldData('position_title')) {
                    if (ci(row.position_title) !== ci(filters.positionTitle)) return false;
                }
                if (filters.customerName && IS_GLOBAL_ROSTER) {
                    if (ci(row.customer_name) !== ci(filters.customerName)) return false;
                }
                if (showOnlyChecked.value && !isRowChecked(row.id)) return false;
                return true;
            });
        });
        const pageSize = ref(10);
        const currentPage = ref(1);
        const totalPages = computed(() => Math.max(1, Math.ceil(filteredRows.value.length / pageSize.value)));
        const pagedRows = computed(() => {
            const start = (currentPage.value - 1) * pageSize.value;
            return filteredRows.value.slice(start, start + pageSize.value);
        });
        const pageNumbers = computed(() => {
            const total = totalPages.value;
            const max = 7;
            let start = Math.max(1, currentPage.value - 3);
            let end = Math.min(total, start + max - 1);
            start = Math.max(1, end - max + 1);
            const arr = [];
            for (let i = start; i <= end; i++) arr.push(i);
            return arr;
        });
        const goPage = (p) => {
            currentPage.value = Math.min(Math.max(1, p), totalPages.value);
        };
        watch([filters, showOnlyChecked], () => { currentPage.value = 1; }, { deep: true });
        watch(filteredRows, () => { if (currentPage.value > totalPages.value) currentPage.value = totalPages.value; });
        const emptyStateText = computed(() => {
            if (showOnlyChecked.value) return checkedCount.value ? '暂无符合筛选条件的勾选条目' : '暂无勾选条目';
            if (Object.values(filters).some((value) => String(value || '').trim() !== '')) return '暂无符合筛选条件的数据';
            if (IS_GLOBAL_ROSTER) return '暂无数据，可通过「导入 CSV」批量维护；新增员工请进入对应客户的花名册';
            return '暂无数据，请点击「新增行」或「导入 CSV」';
        });
        const rosterFooter = computed(() => {
            let sumQuote = 0;
            let sumPre = 0;
            let sumGm = 0;
            let countQuote = 0;
            let countPre = 0;
            let countGm = 0;
            for (const row of filteredRows.value) {
                const q = parseAmountCell(row.monthly_quote_tax);
                const p = parseAmountCell(row.pre_tax_salary);
                const g = parseAmountCell(row.gms);
                if (Number.isFinite(q)) {
                    sumQuote += q;
                    countQuote += 1;
                }
                if (Number.isFinite(p)) {
                    sumPre += p;
                    countPre += 1;
                }
                if (Number.isFinite(g)) {
                    sumGm += g;
                    countGm += 1;
                }
            }
            const rq = Math.round(sumQuote);
            const rp = Math.round(sumPre);
            const rg = Math.round(sumGm);
            const salaryRatio = rq > 0 ? rp / rq : NaN;
            const netQuoteTotal = rq / TAX_DIVISOR;
            const gmRatio = netQuoteTotal > 0 ? rg / netQuoteTotal : NaN;
            const avgQuote = countQuote > 0 ? sumQuote / countQuote : NaN;
            const avgPre = countPre > 0 ? sumPre / countPre : NaN;
            const avgGm = countGm > 0 ? sumGm / countGm : NaN;
            const avgSalaryRatio = Number.isFinite(avgQuote) && avgQuote > 0 ? avgPre / avgQuote : NaN;
            const netQuoteAvg = Number.isFinite(avgQuote) ? avgQuote / TAX_DIVISOR : NaN;
            const avgGmRatio = netQuoteAvg > 0 ? avgGm / netQuoteAvg : NaN;
            return {
                quote: formatYuanInteger(sumQuote),
                pre: formatYuanInteger(sumPre),
                salaryRatio: formatRatioAsPercent(salaryRatio),
                gms: formatYuanInteger(sumGm),
                gmPct: formatRatioAsPercent(gmRatio),
                avgQuote: formatYuanInteger(avgQuote),
                avgPre: formatYuanInteger(avgPre),
                avgSalaryRatio: formatRatioAsPercent(avgSalaryRatio),
                avgGms: formatYuanInteger(avgGm),
                avgGmPct: formatRatioAsPercent(avgGmRatio),
            };
        });
        const activeFormFields = computed(() => {
            if (isZNTX.value) return ZNTX_FORM_FIELDS;
            if (hideReleaseLeaveCols.value) return standardFormFieldsWithoutReleaseLeave();
            return STANDARD_FORM_FIELDS;
        });
        const detailCompactFields = computed(() => activeFormFields.value.filter((f) => !DETAIL_TEXTAREA_KEYS.has(f.key)));
        const detailTextareaFields = computed(() => activeFormFields.value.filter((f) => DETAIL_TEXTAREA_KEYS.has(f.key)));
        const formInputFields = computed(() => {
            let fields = activeFormFields.value.filter((f) => !ROSTER_FORM_HIDDEN_FIELD_KEYS.has(f.key));
            if (!editingId.value) {
                fields = fields.filter((f) => !ROSTER_ADD_ONLY_HIDDEN_FIELD_KEYS.has(f.key));
            }
            return fields;
        });
        const onboardingChannelSelectOptions = computed(() =>
            buildOnboardingChannelSelectOptions(form.zntx_onboarding_channel)
        );
        const formCompactFields = computed(() => formInputFields.value.filter((f) => !DETAIL_TEXTAREA_KEYS.has(f.key)));
        const formTextareaFields = computed(() => formInputFields.value.filter((f) => DETAIL_TEXTAREA_KEYS.has(f.key)));
        const requiredFieldLabelMap = computed(() => {
            const map = {};
            activeFormFields.value.forEach((f) => { map[f.key] = f.label; });
            return map;
        });
        const missingRequiredFields = computed(() => {
            const missing = [];
            REQUIRED_FIELD_KEYS.forEach((k) => {
                const v = form[k];
                if (v == null || String(v).trim() === '') {
                    missing.push(k);
                }
            });
            return missing;
        });
        const hasFormatErrors = computed(() => {
            const contact = String(form.contact_info || '').trim();
            if (contact && !/^\d{11}$/.test(contact)) return true;
            const quote = String(form.monthly_quote_tax || '').trim();
            if (quote && !isValidSalaryAmountInput(quote)) return true;
            const preSalary = String(form.pre_tax_salary || '').trim();
            if (preSalary && !isValidSalaryAmountInput(preSalary)) return true;
            const gmPct = String(form.gm_pct || '').trim();
            if (gmPct && !isValidGmPctInput(gmPct)) return true;
            return false;
        });
        const hasBlockingErrors = computed(() => {
            if (!editingId.value && missingRequiredFields.value.length) {
                return true;
            }
            return hasFormatErrors.value;
        });
        const isRequiredField = (key) => REQUIRED_FIELD_KEYS.has(key);
        const clearTouched = () => {
            FORM_FIELDS.forEach((f) => { touchedFields[f.key] = false; });
        };
        const markTouched = (key) => { touchedFields[key] = true; };
        const getFieldError = (key) => {
            const v = String(form[key] || '').trim();
            if (!touchedFields[key]) return '';
            if (!editingId.value && isRequiredField(key) && !v) {
                return '该字段为必填';
            }
            if (key === 'contact_info' && v && !/^\d{11}$/.test(v)) {
                return '联系方式必须为11位数字';
            }
            if (key === 'monthly_quote_tax' && v && !isValidSalaryAmountInput(v)) {
                return '月报价(含税)必须为4-6位数字（可带逗号）';
            }
            if (key === 'pre_tax_salary' && v && !isValidSalaryAmountInput(v)) {
                return '税前工资必须为4-6位数字（可带逗号）';
            }
            if (key === 'gm_pct' && v && !isValidGmPctInput(v)) {
                return 'GM%需为0-100（如 12、12.5、12% 或 12.5%）';
            }
            return '';
        };
        const fieldInputType = (key) => {
            if (key === 'entry_date' || key === 'regularization_date' || key === 'project_release_date' || key === 'company_resign_date') {
                return 'date';
            }
            return 'text';
        };
        const isAmountField = (key) => ROSTER_AMOUNT_FIELD_KEYS.has(key);
        const isGmPctField = (key) => key === 'gm_pct';
        const isGmCalcOutputField = (key) => GM_CALC_OUTPUT_FIELD_KEYS.has(key);
        const isCalcInputLockedField = (key) =>
            calcFieldsLocked.value && (key === 'monthly_quote_tax' || key === 'pre_tax_salary');
        const onAmountFieldInput = (key, e) => {
            form[key] = formatAmountThousandsInput(e && e.target ? e.target.value : '');
            markTouched(key);
        };
        const onGmPctFieldInput = (e) => {
            let v = String(e && e.target ? e.target.value : '').replace(/％/g, '%').replace(/%/g, '').trim();
            if (!v) {
                form.gm_pct = '';
            } else if (GM_PCT_COMPLETE_RE.test(v)) {
                form.gm_pct = v + '%';
            } else {
                form.gm_pct = v;
            }
            markTouched('gm_pct');
        };
        const onGmPctFieldBlur = () => {
            const v = String(form.gm_pct || '').trim();
            if (!v) return;
            if (!v.includes('%')) {
                form.gm_pct = formatGmPctWithSymbol(v);
            }
            markTouched('gm_pct');
        };
        const clearDateField = (key) => {
            form[key] = '';
            markTouched(key);
        };
        const validateBusinessFields = () => {
            const contact = String(form.contact_info || '').trim();
            if (contact && !/^\d{11}$/.test(contact)) {
                return '联系方式必须为11位数字';
            }
            const quote = String(form.monthly_quote_tax || '').trim();
            if (quote && !isValidSalaryAmountInput(quote)) {
                return '月报价(含税)必须为4-6位数字（可带逗号）';
            }
            const preSalary = String(form.pre_tax_salary || '').trim();
            if (preSalary && !isValidSalaryAmountInput(preSalary)) {
                return '税前工资必须为4-6位数字（可带逗号）';
            }
            const gmPct = String(form.gm_pct || '').trim();
            if (gmPct && !isValidGmPctInput(gmPct)) {
                return 'GM%需为0-100（如 12、12.5、12% 或 12.5%）';
            }
            return '';
        };
        const nextSerialNo = () => {
            if (!rows.value.length) return '1';
            const lastSerial = String(rows.value[rows.value.length - 1]?.serial_no ?? '').trim();
            const n = parseInt(lastSerial, 10);
            return Number.isFinite(n) ? String(n + 1) : '';
        };
        const loadBrief = () => {
            if (IS_GLOBAL_ROSTER) {
                brief.value = { name: '整体客户', owner: '' };
                return Promise.resolve();
            }
            return fetch(`/api/clients/${CLIENT_ID}/brief`, { headers: authHeader() })
                .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
                .then((d) => { brief.value = d; })
                .catch(() => { brief.value = { name: '客户不存在', owner: '' }; });
        };
        const loadCrmClients = () => {
            fetch('/api/clients', { headers: authHeader() })
                .then((r) => r.json())
                .then((d) => { crmClients.value = Array.isArray(d) ? d : []; })
                .catch(() => { crmClients.value = []; });
        };
        const loadRows = () => {
            loading.value = true;
            const url = IS_GLOBAL_ROSTER ? '/api/roster' : `/api/clients/${CLIENT_ID}/roster`;
            return fetch(url, { headers: authHeader() })
                .then((r) => r.json())
                .then((d) => {
                    rows.value = Array.isArray(d) ? d : [];
                    syncCheckedRows(rows.value);
                })
                .finally(() => { loading.value = false; });
        };
        const appendGmCalcQueryPart = (parts, key, val) => {
            const s = String(val == null ? '' : val).trim();
            if (!s) return;
            parts.push(`${key}=${encodeURIComponent(s)}`);
        };
        const resolveClientIdForGmCalc = () => {
            if (!IS_GLOBAL_ROSTER) {
                return CLIENT_ID || null;
            }
            if (editingId.value) {
                const row = rows.value.find((r) => Number(r.id) === Number(editingId.value));
                if (row?.client_id != null) return row.client_id;
            }
            const name = String(form.customer_name || '').trim();
            if (!name) return null;
            const client = (crmClients.value || []).find(
                (c) => String(c?.name || '').trim() === name,
            );
            return client?.id != null ? client.id : null;
        };
        const openRosterGmCalculatorFromRosterForm = () => {
            const targetClientId = resolveClientIdForGmCalc();
            if (!targetClientId) {
                alert(IS_GLOBAL_ROSTER ? '请先选择客户后再使用毛利测算器' : '无法打开毛利测算器');
                return;
            }
            const parts = ['return_to=roster', 'roster_add=1'];
            appendGmCalcQueryPart(parts, 'targetClientId', targetClientId);
            appendGmCalcQueryPart(parts, 'full_name', form.full_name);
            appendGmCalcQueryPart(parts, 'work_location', form.work_location);
            appendGmCalcQueryPart(parts, 'position', form.position_title);
            appendGmCalcQueryPart(parts, 'monthly_quote_tax', normalizeAmountText(form.monthly_quote_tax));
            appendGmCalcQueryPart(parts, 'pre_tax_salary', normalizeAmountText(form.pre_tax_salary));
            appendGmCalcQueryPart(parts, 'gms', normalizeAmountText(form.gms));
            appendGmCalcQueryPart(parts, 'gm_pct', form.gm_pct);
            window.open(`/tools/calc?${parts.join('&')}`, '_blank');
        };
        const openAdd = () => {
            if (IS_GLOBAL_ROSTER) return;
            editingId.value = null;
            formReadonly.value = false;
            calcFieldsLocked.value = false;
            Object.assign(form, emptyForm());
            clearTouched();
            const nextNo = nextSerialNo();
            if (nextNo) {
                form.serial_no = nextNo;
            }
            if (!IS_GLOBAL_ROSTER) {
                const cn = String(brief.value?.name || '').trim();
                if (cn && cn !== '客户不存在') {
                    form.customer_name = cn;
                }
            }
            showForm.value = true;
        };
        const openEdit = (row) => {
            editingId.value = row.id;
            formReadonly.value = false;
            FORM_FIELDS.forEach((f) => {
                const raw = row[f.key] != null ? String(row[f.key]) : '';
                if (f.key === 'zntx_onboarding_channel') return;
                if (DATE_FIELD_KEYS.has(f.key)) {
                    form[f.key] = normalizeDateForInput(raw, false);
                } else if (ROSTER_AMOUNT_FIELD_KEYS.has(f.key)) {
                    form[f.key] = formatAmountThousandsInput(raw);
                } else if (f.key === 'gm_pct') {
                    form[f.key] = formatGmPctWithSymbol(raw);
                } else {
                    form[f.key] = raw;
                }
            });
            form.zntx_onboarding_channel = normalizeOnboardingChannelForForm(row.zntx_onboarding_channel || '');
            form.zntx_onboarding_channel_other = '';
            clearTouched();
            showForm.value = true;
        };
        const openRosterDetail = (row) => {
            regDetailRow.value = row || null;
        };
        const canRegularizeRow = (row) => {
            if (!row) return false;
            const status = String(row.regularization_status || '未转正').trim();
            return status === '未转正';
        };
        const syncRosterRowInList = (updated) => {
            if (!updated || updated.id == null) return;
            const idx = rows.value.findIndex((r) => Number(r.id) === Number(updated.id));
            if (idx >= 0) {
                rows.value[idx] = updated;
            }
            if (regDetailRow.value && Number(regDetailRow.value.id) === Number(updated.id)) {
                regDetailRow.value = updated;
            }
            regReminderFindings.value = regReminderFindings.value
                .map((item) => (
                    item && Number(item.id) === Number(updated.id)
                        ? { ...item, row: updated }
                        : item
                ))
                .filter((item) => {
                    const status = String(item?.row?.regularization_status || '未转正').trim();
                    return status !== '已转正';
                });
        };
        const doRegularize = async (targetRow) => {
            const row = targetRow || regDetailRow.value;
            if (!row || !canRegularizeRow(row)) return;
            if (typeof window.crmConfirmActionDialog !== 'function') {
                alert('确认对话框不可用');
                return;
            }
            const result = await window.crmConfirmActionDialog({
                title: '确认转正',
                lines: [
                    { label: '姓名', value: row.full_name || '—' },
                    { label: '当前状态', value: row.regularization_status || '未转正' },
                ],
                hint: '确认后将把转正状态从「未转正」改为「已转正」。',
                confirmText: '确认转正',
                cancelText: '取消',
                zIndex: 120,
            });
            if (!result || !result.ok) return;
            regularizingId.value = row.id;
            try {
                const r = await fetch(`/api/roster/${row.id}`, {
                    method: 'PUT',
                    headers: { ...authHeader(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ regularization_status: '已转正' }),
                });
                if (!r.ok) {
                    let msg = '转正操作失败';
                    try {
                        const err = await r.json();
                        if (typeof err.detail === 'string') {
                            msg = err.detail;
                        }
                    } catch (e) { /* ignore */ }
                    alert(msg);
                    return;
                }
                const updated = await r.json();
                syncRosterRowInList(updated);
            } finally {
                regularizingId.value = null;
            }
        };
        const saveForm = async () => {
            if (formReadonly.value) return;
            if (!editingId.value && IS_GLOBAL_ROSTER) {
                alert('整体花名册不支持新增员工，请进入对应客户的花名册创建。');
                return;
            }
            if (!editingId.value && missingRequiredFields.value.length) {
                const missingLabels = missingRequiredFields.value.map((k) => requiredFieldLabelMap.value[k] || k);
                alert(`请先完整填写必填项：${missingLabels.join('、')}`);
                return;
            }
            const bizError = validateBusinessFields();
            if (bizError) {
                alert(bizError);
                return;
            }
            const payload = {};
            FORM_FIELDS.forEach((f) => {
                if (f.key === 'throme_staff_no') return;
                payload[f.key] = form[f.key];
            });
            payload.zntx_onboarding_channel = String(form.zntx_onboarding_channel || '').trim();
            // 提交前规范化金额文本，兼容用户输入千分位/货币符号
            payload.monthly_quote_tax = normalizeAmountText(payload.monthly_quote_tax);
            payload.pre_tax_salary = normalizeAmountText(payload.pre_tax_salary);
            payload.gms = normalizeAmountText(payload.gms);
            payload.gm_pct = formatGmPctWithSymbol(payload.gm_pct);
            const url = editingId.value
                ? `/api/roster/${editingId.value}`
                : (IS_GLOBAL_ROSTER ? '/api/roster' : `/api/clients/${CLIENT_ID}/roster`);
            const method = editingId.value ? 'PUT' : 'POST';
            const r = await fetch(url, {
                method,
                headers: { ...authHeader(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!r.ok) {
                let msg = '保存失败';
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') {
                        msg = err.detail;
                    } else if (Array.isArray(err.detail) && err.detail[0]?.msg) {
                        msg = err.detail.map((x) => x.msg).join('；');
                    }
                } catch (e) { /* ignore */ }
                alert(msg);
                return;
            }
            showForm.value = false;
            formReadonly.value = false;
            calcFieldsLocked.value = false;
            loadRows();
        };
        const doDelete = async (row) => {
            if (!row) return;
            if (typeof window.crmConfirmDeleteDialog !== 'function') {
                alert('确认对话框不可用');
                return;
            }
            const name = String(row.full_name || '').trim() || `#${row.id}`;
            let targetText = `将删除：${name}`;
            if (IS_GLOBAL_ROSTER) {
                const customer = String(row.customer_name || '').trim();
                if (customer) targetText = `将删除：${name}（${customer}）`;
            }
            const ok = await window.crmConfirmDeleteDialog({
                title: '确认删除记录',
                targetText,
                hint: '删除后将从当前花名册列表移除。',
            });
            if (!ok) return;
            const id = row.id;
            const r = await fetch(`/api/roster/${id}`, { method: 'DELETE', headers: authHeader() });
            if (r.ok) {
                loadRows();
            } else {
                alert('删除失败');
            }
        };
        const triggerImport = () => {
            if (fileInput.value) fileInput.value.click();
        };
        const onImportFile = async (e) => {
            const f = e.target.files && e.target.files[0];
            if (!f) return;
            const scopeLabel = IS_GLOBAL_ROSTER ? '整体花名册' : '当前客户花名册';
            const importHint = IS_GLOBAL_ROSTER
                ? '该操作会先全量备份，再仅清空整体「在职花名册」并导入（已离职档案保留不删）。'
                : `该操作会先备份${scopeLabel}全部行，再仅清空其中「在职池」并导入（该客户已离职档案保留）。`;
            const token = window.prompt(`${importHint}\n请输入 CONFIRM 继续：`, '');
            if (token == null) {
                e.target.value = '';
                return;
            }
            const fd = new FormData();
            fd.append('file', f);
            fd.append('confirm', token);
            const importUrl = IS_GLOBAL_ROSTER ? '/api/roster/import' : `/api/clients/${CLIENT_ID}/roster/import`;
            const r = await fetch(importUrl, { method: 'POST', headers: authHeader(), body: fd });
            e.target.value = '';
            if (!r.ok) {
                let msg = '导入失败，请检查 CSV 编码与表头';
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string' && err.detail.trim()) {
                        msg = `导入失败：${err.detail}`;
                    }
                } catch (e2) { /* ignore */ }
                alert(msg);
                return;
            }
            const j = await r.json();
            const cleared = j.cleared_existing != null ? j.cleared_existing : 0;
            const backupFile = j.backup_file || '';
            const imp = j.imported != null ? j.imported : 0;
            const skip = j.skipped_duplicates != null ? j.skipped_duplicates : 0;
            const skipTotal = j.skipped_total != null ? j.skipped_total : skip;
            const skipDetails = Array.isArray(j.skipped_details) ? j.skipped_details : [];
            let msg = `${backupFile ? `已备份到 ${backupFile}\n` : ''}已清空在职池 ${cleared} 行，成功导入 ${imp} 行`;
            if (skipTotal > 0) {
                msg += `\n共跳过 ${skipTotal} 行（其中联系方式重复 ${skip} 行）`;
                const lines = skipDetails.map((item) => {
                    const serial = (item && item.serial_no) ? item.serial_no : '-';
                    const reason = (item && item.reason) ? item.reason : '未知原因';
                    return `- 序列号 ${serial}：${reason}`;
                });
                if (lines.length) {
                    msg += `\n跳过明细：\n${lines.join('\n')}`;
                }
            }
            alert(msg);
            loadRows();
        };
        const canDeletePermission = (code) => !window.crmHasPermission || window.crmHasPermission(code);
        const exportCsv = async () => {
            const exportUrl = IS_GLOBAL_ROSTER ? '/api/roster/export' : `/api/clients/${CLIENT_ID}/roster/export`;
            const r = await fetch(exportUrl, { headers: authHeader() });
            if (!r.ok) {
                alert('导出失败');
                return;
            }
            const disposition = r.headers.get('Content-Disposition') || '';
            const blob = await r.blob();
            const fallbackName = IS_GLOBAL_ROSTER ? `整体花名册_${Date.now()}.csv` : `花名册_${CLIENT_ID}_${Date.now()}.csv`;
            window.crmDownloadBlob(blob, disposition, fallbackName);
        };
        const loadLogs = async () => {
            logsLoading.value = true;
            try {
                const logsUrl = IS_GLOBAL_ROSTER ? '/api/roster/logs' : `/api/clients/${CLIENT_ID}/details`;
                const r = await fetch(logsUrl, { headers: authHeader() });
                if (!r.ok) {
                    throw new Error('load logs failed');
                }
                const d = await r.json();
                logs.value = IS_GLOBAL_ROSTER ? (Array.isArray(d) ? d : []) : (Array.isArray(d.logs) ? d.logs : []);
            } catch (e) {
                logs.value = [];
                alert('日志加载失败');
            } finally {
                logsLoading.value = false;
            }
        };
        const openLogs = async () => {
            if (!canViewRosterLogs.value) return;
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
            const scopeLabel = IS_GLOBAL_ROSTER ? '整体花名册' : '当前客户花名册';
            const ok = window.confirm(`将使用“最近一次花名册备份”覆盖${scopeLabel}数据，是否继续？`);
            if (!ok) return;
            const restoreUrl = IS_GLOBAL_ROSTER ? '/api/roster/restore/latest' : `/api/clients/${CLIENT_ID}/roster/restore/latest`;
            const r = await fetch(restoreUrl, {
                method: 'POST',
                headers: authHeader(),
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
            await loadLogs();
        };
        const clearFilters = () => {
            filters.keyword = '';
            filters.customerName = '';
            filters.workLocation = '';
            filters.regularizationStatus = '';
            filters.entryDateBefore = '';
            filters.entryDateAfter = '';
            filters.gmsBelow = '';
            filters.gmPctBelow = '';
            filters.positionTitle = '';
            filters.preTaxSalaryAbove = '';
            filters.preTaxSalaryBelow = '';
        };
        function goBack() {
            if (window.history.length > 1) window.history.back();
            else window.location.href = '/customers/roster';
        }
        const toggleShowCheckedOnly = () => {
            showOnlyChecked.value = !showOnlyChecked.value;
        };
        const buildRosterValidationFindings = () => {
            const findings = [];
            const todayKey = rosterDateSortKey(todayInputDate());
            for (const row of filteredRows.value) {
                const name = String(row.full_name || '').trim() || `#${row.id}`;
                const customer = IS_GLOBAL_ROSTER ? String(row.customer_name || '').trim() : '';
                const status = String(row.employment_status || '').trim();
                if (status.includes('待入职')) {
                    const entryKey = rosterDateSortKey(row.entry_date);
                    if (entryKey != null && todayKey != null && entryKey < todayKey) {
                        const entryDisp = displayRosterDate(row.entry_date) || String(row.entry_date || '').trim() || '—';
                        findings.push({
                            id: row.id,
                            name,
                            customer,
                            category: '在职与入职日期',
                            issue: `在职情况含「待入职」，但入职日期 ${entryDisp} 早于当前日期`,
                            action: '请核对是否已入职，或调整在职情况/入职日期',
                        });
                    }
                }
                const entryKey2 = rosterDateSortKey(row.entry_date);
                const regKey = rosterDateSortKey(row.regularization_date);
                if (entryKey2 != null && regKey != null && regKey < entryKey2) {
                    const entryDisp = displayRosterDate(row.entry_date) || String(row.entry_date || '').trim() || '—';
                    const regDisp = displayRosterDate(row.regularization_date) || String(row.regularization_date || '').trim() || '—';
                    findings.push({
                        id: row.id,
                        name,
                        customer,
                        category: '转正与入职日期',
                        issue: `转正时间 ${regDisp} 早于入职日期 ${entryDisp}`,
                        action: '请核对转正时间或入职日期是否录入有误',
                    });
                }
            }
            return findings;
        };
        const buildRegularizationReminderFindings = () => {
            const findings = [];
            const today = todayInputDate();
            for (const row of rows.value) {
                const regStatus = String(row.regularization_status || '未转正').trim();
                if (regStatus === '已转正') continue;
                const days = rosterDateDiffDays(today, row.regularization_date);
                if (days == null || days >= 30) continue;
                const name = String(row.full_name || '').trim() || `#${row.id}`;
                const customer = String(row.customer_name || '').trim();
                findings.push({
                    id: row.id,
                    name,
                    customer,
                    businessLine: String(row.business_line || '').trim(),
                    regularizationDate: displayRosterDate(row.regularization_date) || String(row.regularization_date || '').trim() || '—',
                    days,
                    isOverdue: days < 0,
                    row,
                });
            }
            findings.sort((a, b) => a.days - b.days || a.name.localeCompare(b.name, 'zh-CN'));
            return findings;
        };
        const buildRegularizationReminderText = (findings) => {
            if (!findings.length) return '';
            const lines = ['【整体客户 · 转正提醒】', '转正日期距当前日期不足 30 天（负数表示已超过转正日期）'];
            findings.forEach((item, idx) => {
                const label = item.customer ? `${item.name}（${item.customer}）` : item.name;
                const biz = item.businessLine ? `，业务 ${item.businessLine}` : '';
                lines.push(`${idx + 1}. ${label}${biz}｜转正 ${item.regularizationDate}，剩余 ${item.days} 天`);
            });
            return lines.join('\n');
        };
        const buildRosterValidationText = (findings, scope) => {
            if (!findings.length) return '';
            const lines = [`【${scope} · 花名册校验】`, '矛盾或疑点条目'];
            findings.forEach((item, idx) => {
                const label = item.customer ? `${item.name}（${item.customer}）` : item.name;
                lines.push(`${idx + 1}. ${label}｜${item.issue}；${item.action}`);
            });
            lines.push('');
            lines.push('建议：在列表或详情中修正原始记录后保存，并再次点击「校验」复核。');
            return lines.join('\n');
        };
        const copyTextToClipboard = async (text) => {
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(text);
                    return true;
                }
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.setAttribute('readonly', '');
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                const ok = document.execCommand('copy');
                document.body.removeChild(ta);
                return ok;
            } catch (err) {
                return false;
            }
        };
        const closeValidation = () => {
            showValidation.value = false;
            validationCopied.value = false;
        };
        const closeRegularizationReminder = () => {
            showRegReminder.value = false;
            regReminderCopied.value = false;
        };
        const REG_DETAIL_WIDE_KEYS = new Set(['leave_reason']);
        const regDetailFields = computed(() =>
            activeFormFields.value.filter((f) => f.key !== 'serial_no')
        );
        const isWideDetailField = (key) => REG_DETAIL_WIDE_KEYS.has(key);
        const rosterDetailValue = (row, key) => {
            if (!row) return '—';
            const raw = row[key];
            if (raw == null || String(raw).trim() === '') return '—';
            if (DATE_FIELD_KEYS.has(key)) return displayRosterDate(raw) || String(raw);
            if (ROSTER_AMOUNT_FIELD_KEYS.has(key)) return displayAmountInteger(raw);
            return String(raw);
        };
        const openRegDetail = (finding) => {
            openRosterDetail(finding && finding.row ? finding.row : null);
        };
        const closeRegDetail = () => {
            regDetailRow.value = null;
        };
        const copyValidationResults = async () => {
            const text = buildRosterValidationText(validationFindings.value, validationScope.value);
            validationCopied.value = await copyTextToClipboard(text);
        };
        const copyRegularizationReminderResults = async () => {
            const text = buildRegularizationReminderText(regReminderFindings.value);
            regReminderCopied.value = await copyTextToClipboard(text);
        };
        const showRosterValidation = async () => {
            const scope = IS_GLOBAL_ROSTER ? '整体客户' : (String(brief.value?.name || '').trim() || '当前客户');
            const findings = buildRosterValidationFindings();
            validationScope.value = scope;
            validationFindings.value = findings;
            validationCopied.value = findings.length
                ? await copyTextToClipboard(buildRosterValidationText(findings, scope))
                : false;
            showValidation.value = true;
        };
        const showRegularizationReminder = async () => {
            const findings = buildRegularizationReminderFindings();
            if (!findings.length) {
                alert('暂无转正日期距当前日期不足 30 天的记录');
                return;
            }
            regReminderFindings.value = findings;
            regReminderCopied.value = await copyTextToClipboard(buildRegularizationReminderText(findings));
            showRegReminder.value = true;
        };
        const stripRosterAddQueryFromUrl = () => {
            try {
                const params = new URLSearchParams(window.location.search);
                if (!ROSTER_ADD_QUERY_KEYS.some((k) => params.has(k))) return;
                ROSTER_ADD_QUERY_KEYS.forEach((k) => params.delete(k));
                const qs = params.toString();
                const newUrl = window.location.pathname + (qs ? `?${qs}` : '') + (window.location.hash || '');
                window.history.replaceState(null, '', newUrl);
            } catch (e) { /* ignore */ }
        };
        const stripRowIdQueryFromUrl = () => {
            try {
                const params = new URLSearchParams(window.location.search);
                if (!params.has('row_id')) return;
                params.delete('row_id');
                const qs = params.toString();
                const newUrl = window.location.pathname + (qs ? `?${qs}` : '') + (window.location.hash || '');
                window.history.replaceState(null, '', newUrl);
            } catch (e) { /* ignore */ }
        };
        const applyRowIdFromQuery = async () => {
            if (IS_GLOBAL_ROSTER) return;
            try {
                const params = new URLSearchParams(window.location.search);
                const rowId = Number(params.get('row_id') || 0);
                if (!rowId) return;
                await nextTick();
                const row = rows.value.find((r) => Number(r.id) === rowId);
                if (row) openRosterDetail(row);
            } catch (e) {
                console.error('applyRowIdFromQuery failed:', e);
            } finally {
                stripRowIdQueryFromUrl();
            }
        };
        const applyRosterAddFromQuery = async () => {
            if (IS_GLOBAL_ROSTER) return;
            try {
                const params = new URLSearchParams(window.location.search);
                if (params.get('roster_add') !== '1') return;
                const rawName = params.get('prefill_full_name');
                const nameDecoded = rawName != null ? String(rawName).trim() : '';
                openAdd();
                if (nameDecoded) {
                    form.full_name = nameDecoded;
                }
                const positionRaw = params.get('prefill_position_title');
                if (positionRaw != null && String(positionRaw).trim() !== '') {
                    form.position_title = String(positionRaw).trim();
                }
                const workLocRaw = params.get('prefill_work_location');
                if (workLocRaw != null && String(workLocRaw).trim() !== '') {
                    form.work_location = String(workLocRaw).trim();
                }
                const quoteRaw = params.get('prefill_monthly_quote_tax');
                if (quoteRaw != null && String(quoteRaw).trim() !== '') {
                    form.monthly_quote_tax = formatAmountThousandsInput(quoteRaw);
                }
                const salaryRaw = params.get('prefill_pre_tax_salary');
                if (salaryRaw != null && String(salaryRaw).trim() !== '') {
                    form.pre_tax_salary = formatAmountThousandsInput(salaryRaw);
                }
                const gmsRaw = params.get('prefill_gms');
                if (gmsRaw != null && String(gmsRaw).trim() !== '') {
                    form.gms = formatAmountThousandsInput(gmsRaw);
                }
                const gmPctRaw = params.get('prefill_gm_pct');
                if (gmPctRaw != null && String(gmPctRaw).trim() !== '') {
                    form.gm_pct = formatGmPctWithSymbol(gmPctRaw);
                }
                if (params.get('from_calc') === '1') {
                    calcFieldsLocked.value = true;
                }
                await nextTick();
            } catch (e) {
                console.error('applyRosterAddFromQuery failed:', e);
            } finally {
                stripRosterAddQueryFromUrl();
            }
        };
        onMounted(async () => {
            await loadBrief();
            await loadRows();
            loadCrmClients();
            await applyRowIdFromQuery();
            await applyRosterAddFromQuery();
            window.crmScheduleTableColumnResize?.();
            nextTick(() => {
                const table = document.querySelector('.roster-table');
                if (!table) return;
                window.crmFitTableColumnsToContent?.(table);
                requestAnimationFrame(() => {
                    window.crmRefreshOpColumnWidths?.(document);
                });
            });
        });
        return {
            rows, filteredRows, pagedRows, currentPage, pageSize, totalPages, pageNumbers, goPage, filters, workLocationOptions, customerNameOptions, positionTitleOptions,
            brief, loading, showForm, editingId, form, formFields: activeFormFields, formCompactFields, formTextareaFields, detailCompactFields, detailTextareaFields,
            fileInput, rosterFooter, isZNTX, showStdReleaseLeaveCols, emptyRowColspan, rosterFooterRemarkColspan,
            showLogs, logsLoading, logs, showValidation, validationScope, validationFindings, validationCopied,
            showRegReminder, regReminderFindings, regReminderCopied,
            regDetailRow, regDetailFields, isWideDetailField, rosterDetailValue, openRegDetail, closeRegDetail,
            canRegularizeRow, doRegularize, regularizingId,
            missingRequiredFields, hasBlockingErrors, showOnlyChecked, filterPanelExpanded, rosterScrollWrap, goBack, emptyStateText,
            IS_GLOBAL_ROSTER,
            canViewRosterLogs,
            rosterCustomerSelectOptions,
            onboardingChannelSelectOptions,
            openAdd, openEdit, openRosterDetail, openRosterGmCalculatorFromRosterForm, formReadonly, calcFieldsLocked, canUseGmCalc, saveForm, doDelete, canDeletePermission,
            triggerImport, onImportFile, exportCsv, openLogs, closeLogs, formatDate, restoreLatestBackup, clearFilters, hasFilterField, isRequiredField, isAmountField, isGmPctField, isGmCalcOutputField, isCalcInputLockedField, onAmountFieldInput, onGmPctFieldInput, onGmPctFieldBlur, fieldInputType, markTouched, getFieldError,
            showRosterValidation, closeValidation, copyValidationResults,
            showRegularizationReminder, closeRegularizationReminder, copyRegularizationReminderResults,
            isRowChecked, setRowChecked, toggleShowCheckedOnly,
            clearDateField, displayAmountInteger, displayRosterDate,
        };
    },
});

function mountRosterDetailApp() {
    if (typeof Vue === 'undefined') { return false; }
    const root = document.getElementById('roster-detail-app');
    if (!root || root.__vue_app__) { return !!root?.__vue_app__; }
    const shell = document.getElementById('main-shell');
    if (shell && shell.classList.contains('hidden')) { return false; }
    rosterDetailApp.mount(root);
    root.setAttribute('data-roster-mounted', '1');
    return true;
}

function scheduleRosterMount() {
    if (mountRosterDetailApp()) { return; }
    let tries = 0;
    const timer = window.setInterval(function () {
        tries += 1;
        if (mountRosterDetailApp() || tries >= 50) {
            window.clearInterval(timer);
        }
    }, 100);
}

scheduleRosterMount();
window.addEventListener('crm-shell-ready', mountRosterDetailApp);
