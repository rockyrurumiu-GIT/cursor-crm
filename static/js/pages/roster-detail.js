/**
 * Roster detail page logic.
 * Extracted from templates/pages/roster_detail.html (Phase 28).
 * Requires: Vue 3 CDN; window.__ROSTER_CLIENT_ID__ set in template before this script.
 */

const { createApp, ref, onMounted, reactive, computed, watch, nextTick } = Vue;
const CLIENT_ID = window.__ROSTER_CLIENT_ID__;
const IS_GLOBAL_ROSTER = !CLIENT_ID || Number(CLIENT_ID) === 0;
const STANDARD_FORM_FIELDS = [
    { key: 'serial_no', label: '序号' },
    { key: 'full_name', label: '姓名' },
    { key: 'employment_status', label: '在职情况' },
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
    { key: 'employee_plus2', label: '员工+2' },
    { key: 'interface_contact', label: '接口' },
    { key: 'project_release_date', label: '项目释放日期' },
    { key: 'company_resign_date', label: '公司离职日期' },
    { key: 'leave_reason', label: '离职或释放原因' },
    { key: 'remarks', label: '备注' },
];
/** 下列客户（及整体花名册）表格与表单不展示这三项，与中诺视图一致不占列 */
const HIDE_RELEASE_LEAVE_FIELD_KEYS = ['project_release_date', 'company_resign_date', 'leave_reason'];
function standardFormFieldsWithoutReleaseLeave() {
    return STANDARD_FORM_FIELDS.filter((f) => !HIDE_RELEASE_LEAVE_FIELD_KEYS.includes(f.key));
}
const ZNTX_FORM_FIELDS = [
    { key: 'serial_no', label: '序号' },
    { key: 'full_name', label: '姓名' },
    { key: 'employment_status', label: '在职情况' },
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
    { key: 'zntx_onboarding_channel', label: '入职渠道' },
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
function rosterValidationRowLabel(row) {
    const name = String(row.full_name || '').trim() || `#${row.id}`;
    if (IS_GLOBAL_ROSTER) {
        const c = String(row.customer_name || '').trim();
        return c ? `${name}（${c}）` : name;
    }
    return name;
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
/** 比率转百分比展示，与行内「79.55%」形式一致 */
function formatRatioAsPercent(ratio) {
    if (!Number.isFinite(ratio)) return '—';
    return (ratio * 100).toFixed(2) + '%';
}
const rosterDetailApp = createApp({
    setup() {
        const rows = ref([]);
        const brief = ref({ name: '', owner: '' });
        const loading = ref(true);
        const showOnlyChecked = ref(false);
        const checkedRowIds = reactive({});
        const showForm = ref(false);
        const editingId = ref(null);
        const formReadonly = ref(false);
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
        const showDel = ref(false);
        const delRow = ref(null);
        const fileInput = ref(null);
        const filters = reactive({
            employmentStatus: '',
            workLocation: '',
            customerName: '',
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
        const touchedFields = reactive({});
        const crmClients = ref([]);
        const authHeader = () => window.crmAuthHeader();
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
            if (isZNTX.value) return 23;
            return hideReleaseLeaveCols.value ? 20 : 23;
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
        const employmentStatusOptions = computed(() => uniqueOptions('employment_status'));
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
            employmentStatus: 'employment_status',
            workLocation: 'work_location',
            customerName: 'customer_name',
            entryDateBefore: 'entry_date',
            entryDateAfter: 'entry_date',
            gmsBelow: 'gms',
            gmPctBelow: 'gm_pct',
            positionTitle: 'position_title',
            preTaxSalaryAbove: 'pre_tax_salary',
            preTaxSalaryBelow: 'pre_tax_salary',
        };
        const hasFilterField = (filterKey) => {
            const fieldKey = FILTER_FIELD_MAP[filterKey];
            if (!fieldKey) return false;
            return tableFieldKeys.value.has(fieldKey);
        };
        const filteredRows = computed(() => {
            const ci = (v) => String(v || '').trim().toLowerCase();
            return rows.value.filter((row) => {
                if (filters.employmentStatus && String(row.employment_status || '') !== filters.employmentStatus) return false;
                if (filters.workLocation && hasFieldData('work_location') && ci(row.work_location) !== ci(filters.workLocation)) return false;
                if (filters.customerName && hasFieldData('customer_name') && ci(row.customer_name) !== ci(filters.customerName)) return false;
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
                if (showOnlyChecked.value && !isRowChecked(row.id)) return false;
                return true;
            });
        });
        const displayCountHint = computed(() => {
            if (showOnlyChecked.value) return `（勾选显示 ${filteredRows.value.length} 条）`;
            if (filteredRows.value.length !== rows.value.length) return `（筛选后 ${filteredRows.value.length} 条）`;
            return '';
        });
        const emptyStateText = computed(() => {
            if (showOnlyChecked.value) return checkedCount.value ? '暂无符合筛选条件的勾选条目' : '暂无勾选条目';
            if (Object.values(filters).some((value) => String(value || '').trim() !== '')) return '暂无符合筛选条件的数据';
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
            const gmRatio = rq > 0 ? rg / rq : NaN;
            const avgQuote = countQuote > 0 ? sumQuote / countQuote : NaN;
            const avgPre = countPre > 0 ? sumPre / countPre : NaN;
            const avgGm = countGm > 0 ? sumGm / countGm : NaN;
            const avgSalaryRatio = Number.isFinite(avgQuote) && avgQuote > 0 ? avgPre / avgQuote : NaN;
            const avgGmRatio = Number.isFinite(avgQuote) && avgQuote > 0 ? avgGm / avgQuote : NaN;
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
        const onAmountFieldInput = (key, e) => {
            form[key] = formatAmountThousandsInput(e && e.target ? e.target.value : '');
            markTouched(key);
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
        const openAdd = () => {
            editingId.value = null;
            formReadonly.value = false;
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
                if (DATE_FIELD_KEYS.has(f.key)) {
                    form[f.key] = normalizeDateForInput(raw, false);
                } else if (ROSTER_AMOUNT_FIELD_KEYS.has(f.key)) {
                    form[f.key] = formatAmountThousandsInput(raw);
                } else {
                    form[f.key] = raw;
                }
            });
            clearTouched();
            showForm.value = true;
        };
        const openRosterDetail = (row) => {
            openEdit(row);
            formReadonly.value = true;
        };
        const saveForm = async () => {
            if (formReadonly.value) return;
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
            FORM_FIELDS.forEach((f) => { payload[f.key] = form[f.key]; });
            // 提交前规范化金额文本，兼容用户输入千分位/货币符号
            payload.monthly_quote_tax = normalizeAmountText(payload.monthly_quote_tax);
            payload.pre_tax_salary = normalizeAmountText(payload.pre_tax_salary);
            payload.gms = normalizeAmountText(payload.gms);
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
            loadRows();
        };
        const confirmDelete = (row) => {
            delRow.value = row;
            showDel.value = true;
        };
        const cancelDelete = () => {
            showDel.value = false;
            delRow.value = null;
        };
        const doDelete = async () => {
            if (!delRow.value) return;
            const id = delRow.value.id;
            const r = await fetch(`/api/roster/${id}`, { method: 'DELETE', headers: authHeader() });
            if (r.ok) {
                cancelDelete();
                loadRows();
            } else {
                alert('删除失败');
                cancelDelete();
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
            filters.employmentStatus = '';
            filters.workLocation = '';
            filters.customerName = '';
            filters.entryDateBefore = '';
            filters.entryDateAfter = '';
            filters.gmsBelow = '';
            filters.gmPctBelow = '';
            filters.positionTitle = '';
            filters.preTaxSalaryAbove = '';
            filters.preTaxSalaryBelow = '';
        };
        const toggleShowCheckedOnly = () => {
            showOnlyChecked.value = !showOnlyChecked.value;
        };
        const buildRosterValidationText = () => {
            const scope = IS_GLOBAL_ROSTER ? '整体客户' : (String(brief.value?.name || '').trim() || '当前客户');
            const lines = [`【${scope} · 花名册校验】`];
            const todayKey = rosterDateSortKey(todayInputDate());
            const findings = [];
            for (const row of filteredRows.value) {
                const status = String(row.employment_status || '').trim();
                if (status.includes('待入职')) {
                    const entryKey = rosterDateSortKey(row.entry_date);
                    if (entryKey != null && todayKey != null && entryKey < todayKey) {
                        const entryDisp = displayRosterDate(row.entry_date) || String(row.entry_date || '').trim() || '—';
                        findings.push(`${rosterValidationRowLabel(row)}｜在职情况含「待入职」，但入职日期 ${entryDisp} 早于当前日期；请核对是否已入职或调整在职情况`);
                    }
                }
                const entryKey2 = rosterDateSortKey(row.entry_date);
                const regKey = rosterDateSortKey(row.regularization_date);
                if (entryKey2 != null && regKey != null && regKey < entryKey2) {
                    const entryDisp = displayRosterDate(row.entry_date) || String(row.entry_date || '').trim() || '—';
                    const regDisp = displayRosterDate(row.regularization_date) || String(row.regularization_date || '').trim() || '—';
                    findings.push(`${rosterValidationRowLabel(row)}｜转正时间 ${regDisp} 早于入职日期 ${entryDisp}`);
                }
            }
            if (!findings.length) return '';
            lines.push('矛盾或疑点条目');
            findings.forEach((text, idx) => lines.push(`${idx + 1}. ${text}`));
            lines.push('');
            lines.push('建议：在列表或详情中修正原始记录后保存，并再次点击「校验」复核。');
            return lines.join('\n');
        };
        const showRosterValidation = async () => {
            const text = buildRosterValidationText();
            if (!text) {
                alert('当前筛选范围内暂无校验问题');
                return;
            }
            let copied = false;
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(text);
                    copied = true;
                } else {
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.setAttribute('readonly', '');
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.focus();
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                    copied = true;
                }
            } catch (err) {
                copied = false;
            }
            alert(copied ? `${text}\n\n校验结果已复制` : text);
        };
        const stripRosterAddQueryFromUrl = () => {
            try {
                const params = new URLSearchParams(window.location.search);
                if (!params.has('roster_add') && !params.has('prefill_full_name')) return;
                params.delete('roster_add');
                params.delete('prefill_full_name');
                const qs = params.toString();
                const newUrl = window.location.pathname + (qs ? `?${qs}` : '') + (window.location.hash || '');
                window.history.replaceState(null, '', newUrl);
            } catch (e) { /* ignore */ }
        };
        const applyRosterAddFromQuery = () => {
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
            } finally {
                stripRosterAddQueryFromUrl();
            }
        };
        onMounted(async () => {
            await loadBrief();
            await loadRows();
            loadCrmClients();
            applyRosterAddFromQuery();
            window.crmScheduleTableColumnResize?.();
            nextTick(() => {
                const table = document.querySelector('.roster-table');
                if (table) window.crmFitTableColumnsToContent?.(table);
            });
        });
        return {
            rows, filteredRows, filters, employmentStatusOptions, workLocationOptions, customerNameOptions, positionTitleOptions,
            brief, loading, showForm, editingId, form, formFields: activeFormFields, detailCompactFields, detailTextareaFields,
            showDel, fileInput, rosterFooter, isZNTX, showStdReleaseLeaveCols, emptyRowColspan, rosterFooterRemarkColspan,
            showLogs, logsLoading, logs, missingRequiredFields, hasBlockingErrors, showOnlyChecked, displayCountHint, emptyStateText,
            IS_GLOBAL_ROSTER,
            rosterCustomerSelectOptions,
            openAdd, openEdit, openRosterDetail, formReadonly, saveForm, confirmDelete, cancelDelete, doDelete,
            triggerImport, onImportFile, exportCsv, openLogs, closeLogs, formatDate, restoreLatestBackup, clearFilters, hasFilterField, isRequiredField, isAmountField, onAmountFieldInput, fieldInputType, markTouched, getFieldError,
            showRosterValidation,
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
