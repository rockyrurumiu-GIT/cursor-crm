/**
 * Delivery detail settlement module (Phase 5E Step 2).
 * Keeps settlement state/logic isolated while preserving existing DOM bindings.
 */
(function () {
    'use strict';

    const SETTLEMENT_FIELDS = [
        { key: 'serial_no', label: '序号' },
        { key: 'progress_updated_at', label: '结算进度更新时间', type: 'date' },
        { key: 'customer_name', label: '客户' },
        { key: 'fee_month', label: '费用月份' },
        { key: 'chase_month', label: '追款月份' },
        { key: 'amount', label: '金额' },
        { key: 'internal_attendance_confirm', label: '内部确认考勤' },
        { key: 'client_confirm', label: '客户确认' },
        { key: 'invoiced', label: '是否开票' },
        { key: 'invoice_date', label: '开票日期', type: 'date' },
        { key: 'paid', label: '是否回款' },
        { key: 'expected_payment_date', label: '预计回款时间', type: 'date' },
        { key: 'actual_payment_date', label: '实际回款时间', type: 'date' },
        { key: 'payment_days', label: '回款天数' },
        { key: 'payment_cycle', label: '回款周期' },
        { key: 'payment_nature', label: '回款性质' },
        { key: 'po_no', label: 'PO单' },
        { key: 'invoice_no', label: '发票号' },
        { key: 'remarks', label: '备注', type: 'textarea' },
    ];
    const SETTLEMENT_TEXTAREA_KEYS = new Set(['remarks']);
    const SETTLEMENT_COMPACT_FIELDS = SETTLEMENT_FIELDS.filter((f) => !SETTLEMENT_TEXTAREA_KEYS.has(f.key));
    const SETTLEMENT_TEXTAREA_FIELDS = SETTLEMENT_FIELDS.filter((f) => SETTLEMENT_TEXTAREA_KEYS.has(f.key));
    const SETTLEMENT_DATE_FIELD_KEYS = new Set(
        SETTLEMENT_FIELDS.filter((f) => f.type === 'date').map((f) => f.key)
    );

    function emptySettlementForm() {
        const f = {};
        SETTLEMENT_FIELDS.forEach((x) => { f[x.key] = ''; });
        return f;
    }
    function formatSettlementAmount(raw) {
        const s = String(raw == null ? '' : raw).replace(/[¥￥,\s\u00a0]/g, '').trim();
        if (!s) return '';
        const n = Number(s);
        if (!Number.isFinite(n)) return String(raw || '');
        return `¥${Math.round(n).toLocaleString('zh-CN')}`;
    }

    function settlementReminderLabel(row) {
        const customer = String(row && row.customer_name != null ? row.customer_name : '').trim() || '客户';
        const feeMonth = String(row && row.fee_month != null ? row.fee_month : '').trim() || '-';
        const amount = String(row && row.amount != null ? row.amount : '').trim() || '-';
        return `${customer}｜${feeMonth}｜${amount}`;
    }

    function buildSettlementReminderText(rows, pageClientName, todayDate, normalizeDateForInput, diffDaysFromDate) {
        const followUpItems = [];
        const overdueItems = [];
        (Array.isArray(rows) ? rows : []).forEach((row) => {
            const expectedDate = normalizeDateForInput(row && row.expected_payment_date != null ? String(row.expected_payment_date) : '', false);
            if (!expectedDate) return;
            const actualDate = normalizeDateForInput(row && row.actual_payment_date != null ? String(row.actual_payment_date) : '', false);
            const paid = String(row && row.paid != null ? row.paid : '').trim();
            if (actualDate || paid === '是') return;
            const overdueDays = diffDaysFromDate(expectedDate, todayDate);
            if (overdueDays <= 0) return;
            const label = settlementReminderLabel(row);
            if (overdueDays <= 7) {
                followUpItems.push(label);
            } else {
                overdueItems.push(label);
            }
        });
        if (!followUpItems.length && !overdueItems.length) return '';
        const lines = [`【${String(pageClientName || '客户').trim() || '客户'} - 结算回款提示】`];
        if (followUpItems.length) {
            lines.push('催付');
            followUpItems.forEach((item, idx) => {
                lines.push(`${idx + 1}. ${item}`);
            });
        }
        if (overdueItems.length) {
            lines.push('超期AR');
            overdueItems.forEach((item, idx) => {
                lines.push(`${idx + 1}. ${item}`);
            });
        }
        return lines.join('\n');
    }

    function createSettlementState(deps) {
        const {
            ref,
            reactive,
            moduleKey,
            clientId,
            clientName,
            normalizeDateForInput,
            diffDaysFromDate,
            todayInputDate,
            readApiErrorMessage,
            api,
            download,
        } = deps;

        const settlementRows = ref([]);
        const showForm = ref(false);
        const editingId = ref(null);
        const settlementFormReadonly = ref(false);
        const form = reactive(emptySettlementForm());

        async function loadSettlementRows() {
            if (moduleKey !== 'settlement') return;
            try {
                const all = await api.get('/api/delivery/settlement');
                const cid = Number(clientId);
                settlementRows.value = Array.isArray(all)
                    ? all.filter((row) => Number(row.client_id) === cid)
                    : [];
            } catch (_) {
                settlementRows.value = [];
            }
        }

        async function showSettlementReminders() {
            const text = buildSettlementReminderText(
                settlementRows.value,
                clientName.value,
                todayInputDate(),
                normalizeDateForInput,
                diffDaysFromDate
            );
            if (!text) {
                alert('当前没有需要提示的回款记录');
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
            } catch (_) {
                copied = false;
            }
            alert(copied ? `${text}\n\n提示结果已复制` : text);
        }

        function openAdd() {
            editingId.value = null;
            settlementFormReadonly.value = false;
            Object.assign(form, emptySettlementForm());
            form.customer_name = clientName.value;
            form.serial_no = String(settlementRows.value.length + 1);
            showForm.value = true;
        }

        function openEdit(row) {
            editingId.value = row.id;
            settlementFormReadonly.value = false;
            SETTLEMENT_FIELDS.forEach((f) => {
                const raw = row[f.key] != null ? String(row[f.key]) : '';
                form[f.key] = SETTLEMENT_DATE_FIELD_KEYS.has(f.key)
                    ? normalizeDateForInput(raw, false)
                    : raw;
            });
            showForm.value = true;
        }

        function openSettlementDetail(row) {
            openEdit(row);
            settlementFormReadonly.value = true;
        }

        async function saveForm() {
            if (settlementFormReadonly.value) return;
            const payload = {};
            SETTLEMENT_FIELDS.forEach((f) => { payload[f.key] = form[f.key]; });
            const url = editingId.value
                ? `/api/delivery/settlement/row/${editingId.value}`
                : '/api/delivery/settlement';
            const method = editingId.value ? 'PUT' : 'POST';
            try {
                if (method === 'PUT') {
                    await api.put(url, payload);
                } else {
                    await api.post(url, payload);
                }
            } catch (err) {
                const fallback = '保存失败';
                const msg = err && err.message ? String(err.message) : fallback;
                alert(msg || fallback);
                return;
            }
            showForm.value = false;
            settlementFormReadonly.value = false;
            await loadSettlementRows();
        }

        async function removeRow(row) {
            var ok = await window.crmConfirmDeleteDialog({
                title: '确认删除记录',
                targetText: '将删除当前结算记录',
                hint: '删除后将从当前客户结算列表移除。',
            });
            if (!ok) return;
            try {
                await api.del(`/api/delivery/settlement/row/${row.id}`);
            } catch (err) {
                const fallback = '删除失败';
                const msg = err && err.message ? String(err.message) : fallback;
                alert(msg || fallback);
                return;
            }
            await loadSettlementRows();
        }

        function clearSettlementDateField(key) {
            form[key] = '';
        }

        return {
            settlementRows,
            settlementFields: SETTLEMENT_FIELDS,
            settlementCompactFields: SETTLEMENT_COMPACT_FIELDS,
            settlementTextareaFields: SETTLEMENT_TEXTAREA_FIELDS,
            showSettlementReminders,
            showForm,
            editingId,
            settlementFormReadonly,
            form,
            loadSettlementRows,
            openAdd,
            openEdit,
            openSettlementDetail,
            saveForm,
            removeRow,
            clearSettlementDateField,
            settlementReminderLabel,
            buildSettlementReminderText,
            readApiErrorMessage,
            download,
            formatSettlementAmount,
        };
    }

    window.CrmDeliveryDetailSettlement = {
        createSettlementState,
        SETTLEMENT_FIELDS,
        SETTLEMENT_COMPACT_FIELDS,
        SETTLEMENT_TEXTAREA_FIELDS,
    };
})();
