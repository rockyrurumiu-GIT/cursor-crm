/**
 * Delivery Settlement page logic.
 * Extracted from templates/pages/delivery_settlement.html (Phase 25B).
 * Requires: Vue 3 CDN loaded before this script.
 */
const { createApp, ref, reactive, computed, onMounted, onUnmounted, watch } = Vue;
const FIELDS = [
    { key: 'serial_no', label: '序号', readonly: true },
    { key: 'progress_updated_at', label: '结算进度更新日期', type: 'date' },
    { key: 'customer_name', label: '客户', required: true },
    { key: 'fee_month', label: '费用月份', required: true },
    { key: 'chase_month', label: '追款月份' },
    { key: 'amount', label: '金额', required: true },
    { key: 'internal_attendance_confirm', label: '内部确认考勤', type: 'select', required: true, options: ['是', '否'] },
    { key: 'client_confirm', label: '客户确认', type: 'select', required: true, options: ['是', '否'] },
    { key: 'invoiced', label: '是否开票', type: 'select', required: true, options: ['是', '否'] },
    { key: 'invoice_date', label: '开票日期', type: 'date' },
    { key: 'paid', label: '是否回款', type: 'select', required: true, options: ['是', '否'] },
    { key: 'expected_payment_date', label: '预计回款时间', type: 'date' },
    { key: 'actual_payment_date', label: '实际回款时间', type: 'date' },
    { key: 'payment_days', label: '回款天数' },
    { key: 'payment_cycle', label: '回款周期', type: 'select', required: true, options: ['月度', '双月', '季度', '半年度'] },
    { key: 'payment_nature', label: '回款性质', type: 'select', options: ['增量回款', '存量回款'] },
    { key: 'po_no', label: 'PO单' },
    { key: 'invoice_no', label: '发票号' },
    { key: 'remarks', label: '备注', type: 'textarea' },
];
const DETAIL_TEXTAREA_KEYS = new Set(['remarks']);
const DETAIL_COMPACT_FIELDS = FIELDS.filter((f) => !DETAIL_TEXTAREA_KEYS.has(f.key));
const DETAIL_TEXTAREA_FIELDS = FIELDS.filter((f) => DETAIL_TEXTAREA_KEYS.has(f.key));
const DATE_FIELD_KEYS = new Set(
    FIELDS.filter((f) => f.type === 'date').map((f) => f.key)
);
function emptyForm() {
    const out = {};
    FIELDS.forEach((f) => { out[f.key] = ''; });
    return out;
}
function todayInputDate() {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}
function extractLooseDateParts(raw) {
    const s = String(raw || '').trim();
    if (!s) return null;
    let m = s.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (m) return [m[1], m[2], m[3]];
    m = s.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
    if (!m) return null;
    return [m[1], m[2], m[3]];
}
function normalizeDateForInput(raw, fallbackTodayIfEmpty = false) {
    const s = String(raw || '').trim();
    if (!s) return fallbackTodayIfEmpty ? todayInputDate() : '';
    const parts = extractLooseDateParts(s);
    if (!parts) return s;
    const y = parts[0];
    const mo = String(parseInt(parts[1], 10)).padStart(2, '0');
    const d = String(parseInt(parts[2], 10)).padStart(2, '0');
    if (mo === 'NaN' || d === 'NaN') return s;
    return `${y}-${mo}-${d}`;
}
function displayDateSlash(raw) {
    const s = String(raw || '').trim();
    if (!s) return '';
    const parts = extractLooseDateParts(s);
    if (!parts) return s;
    return `${parts[0]}/${parseInt(parts[1], 10)}/${parseInt(parts[2], 10)}`;
}
function dateKey(raw) {
    const s = String(raw || '').trim();
    if (!s) return null;
    const parts = extractLooseDateParts(s);
    if (!parts) return null;
    const y = parseInt(parts[0], 10);
    const mo = parseInt(parts[1], 10);
    const d = parseInt(parts[2], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
    return y * 10000 + mo * 100 + d;
}
function dateKeyNormalized(raw) {
    const trimmed = String(raw || '').trim();
    if (!trimmed) return null;
    const normalized = normalizeDateForInput(trimmed, false);
    if (!normalized) return null;
    let k = dateKey(normalized);
    if (k != null) return k;
    k = dateKey(trimmed);
    return k;
}
function paymentReminderLabel(row) {
    const customer = String(row && row.customer_name != null ? row.customer_name : '').trim() || '客户';
    const feeMonth = String(row && row.fee_month != null ? row.fee_month : '').trim() || '-';
    const amount = String(row && row.amount != null ? row.amount : '').trim() || '-';
    return `${customer}｜${feeMonth}｜${amount}`;
}
function endOfNextMonth(raw) {
    const s = normalizeDateForInput(raw, false);
    if (!s) return '';
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return '';
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo)) return '';
    const lastDay = new Date(y, mo + 1, 0);
    const outY = lastDay.getFullYear();
    const outM = String(lastDay.getMonth() + 1).padStart(2, '0');
    const outD = String(lastDay.getDate()).padStart(2, '0');
    return `${outY}-${outM}-${outD}`;
}
function addDays(raw, dayOffset) {
    const s = normalizeDateForInput(raw, false);
    if (!s) return '';
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return '';
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    const d = parseInt(m[3], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d) || !Number.isFinite(dayOffset)) return '';
    const date = new Date(y, mo - 1, d + dayOffset);
    const outY = date.getFullYear();
    const outM = String(date.getMonth() + 1).padStart(2, '0');
    const outD = String(date.getDate()).padStart(2, '0');
    return `${outY}-${outM}-${outD}`;
}
function endOfCurrentMonth(raw) {
    const s = normalizeDateForInput(raw, false);
    if (!s) return '';
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return '';
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo)) return '';
    const lastDay = new Date(y, mo, 0);
    const outY = lastDay.getFullYear();
    const outM = String(lastDay.getMonth() + 1).padStart(2, '0');
    const outD = String(lastDay.getDate()).padStart(2, '0');
    return `${outY}-${outM}-${outD}`;
}
function endOfMonthAfterOffset(raw, monthOffset) {
    const s = normalizeDateForInput(raw, false);
    if (!s) return '';
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!m) return '';
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(monthOffset)) return '';
    const lastDay = new Date(y, mo - 1 + monthOffset + 1, 0);
    const outY = lastDay.getFullYear();
    const outM = String(lastDay.getMonth() + 1).padStart(2, '0');
    const outD = String(lastDay.getDate()).padStart(2, '0');
    return `${outY}-${outM}-${outD}`;
}
createApp({
    setup() {
        const rows = ref([]);
        const customerFilterOpen = ref(false);
        const customerFilterRoot = ref(null);
        const filters = reactive({
            selectedCustomers: [],
            feeMonth: '',
            invoiced: '',
            paid: '',
            paymentCycle: '',
            expectedPaymentStart: '',
            expectedPaymentEnd: '',
        });
        const expectedPaymentFilterWarning = ref('');
        let lastInvalidExpectedPaymentStart = '';
        let lastInvalidExpectedPaymentEnd = '';
        const fileInput = ref(null);
        const showLogs = ref(false);
        const logsLoading = ref(false);
        const logs = ref([]);
        const showForm = ref(false);
        const editingId = ref(null);
        const formDetailReadonly = ref(false);
        const form = reactive(emptyForm());
        const fields = ref(FIELDS.map((f) => ({ ...f })));
        const customerNameText = computed(() => String(form.customer_name || '').trim());
        const isZhongNuoCustomer = computed(() => customerNameText.value.includes('中诺'));
        const isHuaqinCustomer = computed(() => customerNameText.value.includes('华勤'));
        const isKpitCustomer = computed(() => customerNameText.value.toUpperCase().includes('KPIT'));
        const isEnvisionCustomer = computed(() => customerNameText.value.includes('远景智能'));
        const isYuanshuCustomer = computed(() => customerNameText.value.includes('元枢'));
        const isWeiwodeCustomer = computed(() => customerNameText.value.includes('帷幄'));
        const isNissanCustomer = computed(() => customerNameText.value.includes('日产'));
        const hasErrors = computed(() => {
            const requiredKeys = ['customer_name', 'fee_month', 'amount', 'internal_attendance_confirm', 'client_confirm', 'invoiced', 'paid', 'payment_cycle'];
            return requiredKeys.some((k) => !String(form[k] || '').trim());
        });
        const settlementCustomerNames = computed(() => {
            const set = new Set();
            for (const row of rows.value) {
                const n = String(row.customer_name != null ? row.customer_name : '').trim();
                if (n) set.add(n);
            }
            return [...set].sort((a, b) => a.localeCompare(b, 'zh-CN'));
        });
        const customerFilterSelectAll = computed({
            get() {
                const all = settlementCustomerNames.value;
                if (!all.length) return false;
                const selSet = new Set(
                    (Array.isArray(filters.selectedCustomers) ? filters.selectedCustomers : [])
                        .map((s) => String(s || '').trim())
                        .filter(Boolean),
                );
                if (!selSet.size) return false;
                return all.every((name) => selSet.has(name));
            },
            set(checked) {
                if (checked) {
                    const all = settlementCustomerNames.value;
                    filters.selectedCustomers.splice(0, filters.selectedCustomers.length, ...all);
                } else {
                    filters.selectedCustomers.splice(0);
                }
            },
        });
        const customerFilterSummary = computed(() => {
            const names = filters.selectedCustomers;
            const n = Array.isArray(names) ? names.length : 0;
            if (!n) return '筛选客户';
            if (n === 1) return String(names[0] || '').trim() || '筛选客户';
            return `已选 ${n} 个客户`;
        });
        const filteredRows = computed(() => {
            const ci = (v) => String(v || '').toLowerCase();
            const startRaw = String(filters.expectedPaymentStart || '').trim();
            const endRaw = String(filters.expectedPaymentEnd || '').trim();
            const selectedNames = Array.isArray(filters.selectedCustomers) ? filters.selectedCustomers : [];
            const selectedSet =
                selectedNames.length > 0
                    ? new Set(selectedNames.map((s) => String(s || '').trim()).filter(Boolean))
                    : null;
            return rows.value.filter((row) => {
                if (selectedSet && selectedSet.size) {
                    const name = String(row.customer_name || '').trim();
                    if (!selectedSet.has(name)) return false;
                }
                if (filters.feeMonth && !ci(row.fee_month).includes(ci(filters.feeMonth))) return false;
                if (filters.invoiced && String(row.invoiced || '') !== filters.invoiced) return false;
                if (filters.paid && String(row.paid || '') !== filters.paid) return false;
                if (filters.paymentCycle && ci(row.payment_cycle) !== ci(filters.paymentCycle)) return false;
                if (startRaw) {
                    const startDate = dateKeyNormalized(startRaw);
                    if (startDate != null) {
                        const rowDate = dateKeyNormalized(row.expected_payment_date);
                        if (!rowDate || rowDate < startDate) return false;
                    }
                }
                if (endRaw) {
                    const endDate = dateKeyNormalized(endRaw);
                    if (endDate != null) {
                        const rowDate = dateKeyNormalized(row.expected_payment_date);
                        if (!rowDate || rowDate > endDate) return false;
                    }
                }
                return true;
            });
        });
        const parseAmount = (raw) => {
            if (raw == null) return NaN;
            const s = String(raw).replace(/[¥￥,\s\u00a0]/g, '').trim();
            if (!s) return NaN;
            const n = Number(s);
            return Number.isFinite(n) ? n : NaN;
        };
        const parseDateParts = (raw) => {
            const s = String(raw || '').trim();
            if (!s) return null;
            const m = s.match(/^(\d{4})\D?(\d{1,2})\D?(\d{1,2})$/);
            if (!m) return null;
            const y = parseInt(m[1], 10);
            const mo = parseInt(m[2], 10);
            const d = parseInt(m[3], 10);
            if (!Number.isFinite(y) || !Number.isFinite(mo) || !Number.isFinite(d)) return null;
            return { y, mo, d };
        };
        const calcDateDiffDays = (startRaw, endRaw) => {
            const start = parseDateParts(startRaw);
            const end = parseDateParts(endRaw);
            if (!start || !end) return null;
            const startTs = Date.UTC(start.y, start.mo - 1, start.d);
            const endTs = Date.UTC(end.y, end.mo - 1, end.d);
            return Math.round((endTs - startTs) / 86400000);
        };
        const buildPaymentReminderText = (sourceRows) => {
            const followUpItems = [];
            const overdueItems = [];
            const followUpAmountByCustomer = new Map();
            const overdueAmountByCustomer = new Map();
            const appendCustomerAmount = (targetMap, row) => {
                const customer = String(row && row.customer_name != null ? row.customer_name : '').trim() || '客户';
                const amount = parseAmount(row && row.amount != null ? row.amount : '');
                const prev = Number(targetMap.get(customer) || 0);
                targetMap.set(customer, prev + (Number.isFinite(amount) ? amount : 0));
            };
            const pushCustomerAmountSummary = (lines, title, amountMap) => {
                if (!(amountMap instanceof Map) || !amountMap.size) return;
                lines.push(`${title}金额汇总`);
                [...amountMap.entries()]
                    .sort((a, b) => a[0].localeCompare(b[0], 'zh-CN'))
                    .forEach(([customer, total], idx) => {
                        lines.push(`${idx + 1}. ${customer}｜¥${Number(total || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
                    });
            };
            (Array.isArray(sourceRows) ? sourceRows : []).forEach((row) => {
                const expectedDate = normalizeDateForInput(row && row.expected_payment_date != null ? String(row.expected_payment_date) : '', false);
                if (!expectedDate) return;
                const actualDate = normalizeDateForInput(row && row.actual_payment_date != null ? String(row.actual_payment_date) : '', false);
                const paid = String(row && row.paid != null ? row.paid : '').trim();
                if (actualDate || paid === '是') return;
                const overdueDays = calcDateDiffDays(expectedDate, todayInputDate());
                if (!Number.isFinite(overdueDays) || overdueDays <= 0) return;
                const label = paymentReminderLabel(row);
                if (overdueDays <= 7) {
                    followUpItems.push(label);
                    appendCustomerAmount(followUpAmountByCustomer, row);
                } else {
                    overdueItems.push(label);
                    appendCustomerAmount(overdueAmountByCustomer, row);
                }
            });
            if (!followUpItems.length && !overdueItems.length) return '';
            const lines = ['【结算回款提示】'];
            if (followUpItems.length) {
                lines.push('催付');
                followUpItems.forEach((item, idx) => {
                    lines.push(`${idx + 1}. ${item}`);
                });
                pushCustomerAmountSummary(lines, '催付', followUpAmountByCustomer);
            }
            if (overdueItems.length) {
                lines.push('超期AR');
                overdueItems.forEach((item, idx) => {
                    lines.push(`${idx + 1}. ${item}`);
                });
                pushCustomerAmountSummary(lines, '超期AR', overdueAmountByCustomer);
            }
            return lines.join('\n');
        };
        const displayAmountInteger = (raw) => {
            const n = parseAmount(raw);
            if (!Number.isFinite(n)) return String(raw || '');
            return `¥${n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        };
        const totalAmountDisplay = computed(() => {
            let sum = 0;
            for (const row of filteredRows.value) {
                const n = parseAmount(row.amount);
                if (Number.isFinite(n)) sum += n;
            }
            return `¥${sum.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        });
        const totalAmountAllDisplay = computed(() => {
            let sum = 0;
            for (const row of rows.value) {
                const n = parseAmount(row.amount);
                if (Number.isFinite(n)) sum += n;
            }
            return `¥${sum.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        });
        const loadRows = async () => {
            try {
                rows.value = await crmApi.get('/api/delivery/settlement');
            } catch (e) {
                rows.value = [];
                crmToast.error(e.message || '加载失败');
            }
        };
        const onDocClickCloseCustomerFilter = (e) => {
            if (!customerFilterOpen.value) return;
            const root = customerFilterRoot.value;
            if (root && !root.contains(e.target)) customerFilterOpen.value = false;
        };
        const triggerImport = () => {
            if (fileInput.value) fileInput.value.click();
        };
        const onImportFile = async (e) => {
            const f = e.target.files && e.target.files[0];
            if (!f) return;
            const token = window.prompt('该操作会先备份并清空现有结算回款数据，再导入新 CSV。\n请输入 CONFIRM 继续：', '');
            if (token == null) {
                e.target.value = '';
                return;
            }
            const fd = new FormData();
            fd.append('file', f);
            fd.append('confirm', token);
            let j;
            try {
                j = await crmApi.postForm('/api/delivery/settlement/import', fd);
            } catch (err) {
                e.target.value = '';
                crmToast.error(err.message || '导入失败');
                return;
            }
            e.target.value = '';
            const cleared = j.cleared_existing != null ? j.cleared_existing : 0;
            const backupFile = j.backup_file || '';
            const imported = j.imported != null ? j.imported : 0;
            const skipTotal = j.skipped_total != null ? j.skipped_total : 0;
            const skipDup = j.skipped_duplicates != null ? j.skipped_duplicates : 0;
            const skipDetails = Array.isArray(j.skipped_details) ? j.skipped_details : [];
            let msg = `${backupFile ? `已备份到 ${backupFile}\n` : ''}已清空 ${cleared} 行，导入成功：${imported} 行`;
            if (skipTotal > 0) {
                msg += `\n共跳过 ${skipTotal} 行（客户+费用月份+金额+备注重复 ${skipDup} 行）`;
                const lines = skipDetails.map((item) => `- ${item.serial_no || '-'}：${item.reason || '未知原因'}`);
                if (lines.length) msg += `\n跳过明细：\n${lines.join('\n')}`;
            }
            crmToast.success(`导入成功：${imported} 行`);
            if (skipTotal > 0) alert(msg);
            await loadRows();
        };
        const exportCsv = async () => {
            try {
                await crmDownload.download('/api/delivery/settlement/export', `结算回款_${Date.now()}.csv`);
            } catch (e) {
                crmToast.error(e.message || '导出失败');
            }
        };
        const openLogs = async () => {
            showLogs.value = true;
            logsLoading.value = true;
            try {
                logs.value = await crmApi.get('/api/delivery/settlement/logs');
            } catch (e) {
                logs.value = [];
                crmToast.error(e.message || '日志加载失败');
            } finally {
                logsLoading.value = false;
            }
        };
        const formatDate = (ds) => {
            if (!ds) return '-';
            const t = new Date(ds);
            return Number.isNaN(t.getTime()) ? String(ds) : t.toLocaleString();
        };
        const restoreLatestBackup = async () => {
            const ok = window.confirm('将使用"最近一次结算回款备份"覆盖当前数据，是否继续？');
            if (!ok) return;
            try {
                const j = await crmApi.post('/api/delivery/settlement/restore/latest', {});
                crmToast.success(`已从备份回滚，恢复 ${j.restored_rows || 0} 行`);
                await loadRows();
            } catch (e) {
                crmToast.error(e.message || '回滚失败');
            }
        };
        const clearFilters = () => {
            filters.selectedCustomers.splice(0);
            filters.feeMonth = '';
            filters.invoiced = '';
            filters.paid = '';
            filters.paymentCycle = '';
            filters.expectedPaymentStart = '';
            filters.expectedPaymentEnd = '';
        };
        const onExpectedPaymentFilterStartDateInput = (e) => {
            const el = e && e.target;
            const v = el && el.value != null ? String(el.value).trim() : '';
            filters.expectedPaymentStart = v;
        };
        const onExpectedPaymentFilterEndDateInput = (e) => {
            const el = e && e.target;
            const v = el && el.value != null ? String(el.value).trim() : '';
            filters.expectedPaymentEnd = v;
        };
        watch(
            () => rows.value,
            () => {
                const allowed = new Set(
                    rows.value
                        .map((r) => String(r.customer_name != null ? r.customer_name : '').trim())
                        .filter(Boolean),
                );
                const sel = filters.selectedCustomers;
                if (!Array.isArray(sel) || !sel.length) return;
                const next = sel.filter((s) => allowed.has(String(s || '').trim()));
                if (next.length !== sel.length) sel.splice(0, sel.length, ...next);
            },
            { deep: true },
        );
        watch(
            () => [String(filters.expectedPaymentStart || '').trim(), String(filters.expectedPaymentEnd || '').trim()],
            ([st, en]) => {
                const parts = [];
                if (st && dateKeyNormalized(st) == null) {
                    parts.push('「预计回款起点」日期无法识别，起点筛选未生效。');
                    if (lastInvalidExpectedPaymentStart !== st) {
                        console.warn('[结算回款] 预计回款起点无法解析:', st);
                        lastInvalidExpectedPaymentStart = st;
                    }
                } else {
                    lastInvalidExpectedPaymentStart = '';
                }
                if (en && dateKeyNormalized(en) == null) {
                    parts.push('「预计回款终点」日期无法识别，终点筛选未生效。');
                    if (lastInvalidExpectedPaymentEnd !== en) {
                        console.warn('[结算回款] 预计回款终点无法解析:', en);
                        lastInvalidExpectedPaymentEnd = en;
                    }
                } else {
                    lastInvalidExpectedPaymentEnd = '';
                }
                expectedPaymentFilterWarning.value = parts.join(' ');
            },
            { immediate: true },
        );
        const clearDateField = (key) => {
            form[key] = '';
        };
        const updateExpectedPaymentDateByRule = () => {
            if (editingId.value) return;
            const invoiceDate = String(form.invoice_date || '').trim();
            if (!invoiceDate) {
                form.expected_payment_date = '';
                return;
            }
            if (isZhongNuoCustomer.value) {
                const expectedDate = endOfNextMonth(invoiceDate);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
            if (isHuaqinCustomer.value) {
                const expectedDate = endOfMonthAfterOffset(invoiceDate, 2);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
            if (isKpitCustomer.value) {
                const expectedDate = addDays(invoiceDate, 90);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
            if (isEnvisionCustomer.value) {
                const expectedDate = endOfMonthAfterOffset(invoiceDate, 3);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
            if (isYuanshuCustomer.value) {
                const expectedDate = endOfCurrentMonth(invoiceDate);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
            if (isWeiwodeCustomer.value) {
                const expectedDate = addDays(invoiceDate, 30);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
            if (isNissanCustomer.value) {
                const expectedDate = addDays(invoiceDate, 60);
                if (expectedDate) form.expected_payment_date = expectedDate;
                return;
            }
        };
        const onSettlementFieldChange = (key) => {
            if (key === 'customer_name' || key === 'invoice_date') {
                updateExpectedPaymentDateByRule();
            }
        };
        const fillPaymentDaysByDates = async () => {
            const candidates = rows.value.filter((row) => {
                const daysEmpty = String(row.payment_days || '').trim() === '';
                const hasActual = String(row.actual_payment_date || '').trim() !== '';
                return daysEmpty && hasActual;
            });
            if (!candidates.length) {
                crmToast.info('没有需要统计的条目（回款天数为空且实际回款时间有值）');
                return;
            }
            const ok = window.confirm(`将为 ${candidates.length} 条记录自动计算并填写回款天数，是否继续？`);
            if (!ok) return;
            let updated = 0;
            let skipped = 0;
            let failed = 0;
            for (const row of candidates) {
                const diff = calcDateDiffDays(row.invoice_date, row.actual_payment_date);
                if (!Number.isFinite(diff)) {
                    skipped += 1;
                    continue;
                }
                const payload = {};
                FIELDS.forEach((f) => {
                    payload[f.key] = row[f.key] != null ? String(row[f.key]) : '';
                });
                payload.payment_days = String(diff);
                try {
                    await crmApi.put(`/api/delivery/settlement/row/${row.id}`, payload);
                    updated += 1;
                } catch (e) {
                    failed += 1;
                }
            }
            await loadRows();
            crmToast.success(`回款天数统计完成：更新 ${updated} 条，跳过 ${skipped} 条，失败 ${failed} 条`);
        };
        const showPaymentReminders = async () => {
            const text = buildPaymentReminderText(filteredRows.value);
            if (!text) {
                crmToast.info('当前没有需要提示的回款记录');
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
            if (copied) crmToast.success('提示结果已复制到剪贴板');
            alert(text);
        };
        const openAdd = () => {
            editingId.value = null;
            formDetailReadonly.value = false;
            Object.assign(form, emptyForm());
            form.serial_no = String(rows.value.length + 1);
            showForm.value = true;
        };
        const openEdit = (row) => {
            editingId.value = row.id;
            formDetailReadonly.value = false;
            FIELDS.forEach((f) => {
                const raw = row[f.key] != null ? String(row[f.key]) : '';
                form[f.key] = DATE_FIELD_KEYS.has(f.key)
                    ? normalizeDateForInput(raw, false)
                    : raw;
            });
            showForm.value = true;
        };
        const openDetail = (row) => {
            openEdit(row);
            formDetailReadonly.value = true;
        };
        const saveForm = async () => {
            if (formDetailReadonly.value) return;
            const payload = {};
            FIELDS.forEach((f) => { payload[f.key] = form[f.key]; });
            const url = editingId.value ? `/api/delivery/settlement/row/${editingId.value}` : '/api/delivery/settlement';
            try {
                if (editingId.value) {
                    await crmApi.put(url, payload);
                } else {
                    await crmApi.post(url, payload);
                }
            } catch (e) {
                crmToast.error(e.message || '保存失败');
                return;
            }
            showForm.value = false;
            formDetailReadonly.value = false;
            crmToast.success('保存成功');
            await loadRows();
        };
        const removeRow = async (row) => {
            try {
                await crmApi.del(`/api/delivery/settlement/row/${row.id}`);
                crmToast.success('已删除');
                await loadRows();
            } catch (e) {
                crmToast.error(e.message || '删除失败');
            }
        };
        const canDeletePermission = (code) => !window.crmHasPermission || window.crmHasPermission(code);
        onMounted(async () => {
            document.addEventListener('click', onDocClickCloseCustomerFilter);
            await loadRows();
            window.crmScheduleTableColumnResize?.();
        });
        onUnmounted(() => {
            document.removeEventListener('click', onDocClickCloseCustomerFilter);
        });
        return {
            rows, settlementCustomerNames, customerFilterSelectAll, customerFilterOpen, customerFilterRoot, customerFilterSummary,
            filters, filteredRows, fields, detailCompactFields: DETAIL_COMPACT_FIELDS, detailTextareaFields: DETAIL_TEXTAREA_FIELDS, fileInput, showLogs, logsLoading, logs,
            totalAmountDisplay, totalAmountAllDisplay,
            expectedPaymentFilterWarning, onExpectedPaymentFilterStartDateInput, onExpectedPaymentFilterEndDateInput,
            showForm, editingId, formDetailReadonly, form, hasErrors,
            openAdd, openEdit, openDetail, saveForm, removeRow, showPaymentReminders, canDeletePermission,
            triggerImport, onImportFile, exportCsv, restoreLatestBackup, openLogs, formatDate, clearFilters, clearDateField, fillPaymentDaysByDates, onSettlementFieldChange, displayAmountInteger, displayDateSlash,
        };
    }
}).mount('#delivery-settlement-app');
