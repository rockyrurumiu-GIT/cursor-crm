/**
 * Delivery detail pipeline module (Phase 5E Step 3).
 */
(function () {
    'use strict';


const PIPELINE_FIELDS = [
    { key: 'resume_time', label: '简历时间', type: 'date' },
    { key: 'date', label: '日期', type: 'period' },
    { key: 'position', label: '岗位' },
    { key: 'full_name', label: '姓名' },
    { key: 'domain', label: '领域' },
    { key: 'years_experience', label: '年限' },
    { key: 'region', label: '地域' },
    { key: 'phone', label: '电话' },
    { key: 'education', label: '学历' },
    { key: 'recruiter', label: '招聘' },
    {
        key: 'resume_screening',
        label: '简历筛选',
        type: 'select',
        options: ['内筛不通过', '友商重复', '待反馈', '通过', '不通过', '需求满足', '需求暂停'],
    },
    { key: 'interviewed', label: '是否面试', type: 'select', options: ['是', '放弃', '约面'] },
    { key: 'interview_time', label: '面试时间', type: 'date' },
    { key: 'interviewer', label: '面试官' },
    { key: 'result', label: '面试结果', type: 'select', options: ['通过', '不通过', '待定'] },
    { key: 'got_offer', label: '是否拿offer', type: 'select', options: ['是', '否'] },
    { key: 'onboarding_time', label: '入职时间', type: 'date' },
    { key: 'onboarded', label: '是否入职' },
    { key: 'status_note', label: '情况', type: 'textarea' },
];
const PIPELINE_BATCH_OPERATION_TYPES = [
    { key: 'resume_screening', label: '简历筛选状态' },
    { key: 'interviewed', label: '是否面试状态' },
    { key: 'result', label: '面试结果状态' },
    { key: 'got_offer', label: '是否拿offer状态' },
];
const PIPELINE_PERIOD_MONTHS = Array.from({ length: 12 }, (_, idx) => idx + 1);
const PIPELINE_PERIOD_WEEKS = ['W1', 'W2', 'W3', 'W4'];
const PIPELINE_PERIOD_ROW_HEIGHT = 36;
const PIPELINE_REQUIRED_KEYS = new Set([
    'resume_time',
    'date',
    'full_name',
    'domain',
    'years_experience',
    'region',
    'phone',
    'education',
    'recruiter',
]);
const PIPELINE_TEXTAREA_KEYS = new Set(['status_note']);
const PIPELINE_COMPACT_FIELDS = PIPELINE_FIELDS.filter((f) => !PIPELINE_TEXTAREA_KEYS.has(f.key));
const PIPELINE_TEXTAREA_FIELDS = PIPELINE_FIELDS.filter((f) => PIPELINE_TEXTAREA_KEYS.has(f.key));
const PIPELINE_DATE_FIELD_KEYS = new Set(
    PIPELINE_FIELDS.filter((f) => f.type === 'date').map((f) => f.key)
);
function emptyPipelineForm() {
    const f = {};
    PIPELINE_FIELDS.forEach((x) => { f[x.key] = ''; });
    f.serial_no = '';
    return f;
}
function parsePeriodForSort(raw) {
    const s = String(raw || '').trim().toLowerCase();
    let m = s.match(/^(\d{1,2})\s*m\s*(\d{1,2})\s*w$/);
    if (m) return { month: parseInt(m[1], 10), week: parseInt(m[2], 10) };
    m = s.match(/^(\d{1,2})\s*w\s*(\d{1,2})$/);
    if (m) return { month: parseInt(m[1], 10), week: parseInt(m[2], 10) };
    return { month: -1, week: -1 };
}
function pipelinePeriodValue(month, weekLabel) {
    const m = Number(month || 0);
    const weekNo = String(weekLabel || '').replace(/[^0-9]/g, '');
    if (!m || !weekNo) return '';
    return `${m}W${weekNo}`;
}
function pipelinePeriodDisplay(raw) {
    const parsed = parsePeriodForSort(raw);
    if (parsed.month >= 1 && parsed.week >= 1) {
        return `${parsed.month}W${parsed.week}`;
    }
    return String(raw || '').trim();
}
function pipelinePeriodPanelStyle(month) {
    const safeMonth = Math.max(1, Math.min(12, Number(month || 1) || 1));
    return { top: `${(safeMonth - 1) * PIPELINE_PERIOD_ROW_HEIGHT}px` };
}
function emptyPipelineFilter() {
    return {
        date: '',
        position: '',
        full_name: '',
        region: '',
        recruiter: '',
        resume_screening: [],
        interviewed: '',
        result: '',
        got_offer: '',
        onboarded: '',
    };
}

    function createPipelineState(deps) {
        const {
            ref,
            reactive,
            computed,
            clientId,
            moduleKey,
            normalizeDateForInput,
            readApiErrorMessage,
            authHeader,
            fuzzyMatch,
            uniqueSorted,
        } = deps;
        const hdr = () => (typeof authHeader === 'function' ? authHeader() : window.crmAuthHeader());


        const returnToInsight = ref(false);
        const pipelineRows = ref([]);
        const checkedPipelineRowIds = reactive({});
        const showOnlyCheckedPipeline = ref(false);
        const showPipelineBatchModal = ref(false);
        const pipelineBatchOperationType = ref('');
        const pipelineBatchOperationValue = ref('');
        const pipelineFilter = reactive(emptyPipelineFilter());
        const resumeScreeningDropdownOpen = ref(false);
        const resumeScreeningFilterRef = ref(null);
        const pipelineFilterPeriodPickerRef = ref(null);
        const pipelineFilterPeriodDropdownOpen = ref(false);
        const pipelineFilterPeriodHoverMonth = ref(1);
        const pipelinePeriodPickerRef = ref(null);
        const pipelinePeriodDropdownOpen = ref(false);
        const pipelinePeriodHoverMonth = ref(1);
        const resumeScreeningSummary = computed(() => {
            const selected = Array.isArray(pipelineFilter.resume_screening) ? pipelineFilter.resume_screening : [];
            if (!selected.length) return '全部';
            if (selected.length === 1) return selected[0];
            return `已选${selected.length}项`;
        });
        const toggleResumeScreeningDropdown = () => {
            resumeScreeningDropdownOpen.value = !resumeScreeningDropdownOpen.value;
        };
        const toggleResumeScreeningOption = (value) => {
            const selected = Array.isArray(pipelineFilter.resume_screening) ? pipelineFilter.resume_screening : [];
            const idx = selected.indexOf(value);
            if (idx >= 0) {
                selected.splice(idx, 1);
            } else {
                selected.push(value);
            }
        };
        const clearResumeScreeningOption = () => {
            pipelineFilter.resume_screening = [];
        };
        const pipelineDateOptions = computed(() => {
            const set = new Set();
            pipelineRows.value.forEach((row) => {
                const n = normalizeDateForInput(row.date != null ? String(row.date) : '', false);
                if (n) set.add(n);
            });
            return [...set].sort((a, b) => b.localeCompare(a));
        });
        const pipelineSelectOptions = computed(() => ({
            region: uniqueSorted(pipelineRows.value, 'region'),
            recruiter: uniqueSorted(pipelineRows.value, 'recruiter'),
            resume_screening: uniqueSorted(pipelineRows.value, 'resume_screening'),
            interviewed: uniqueSorted(pipelineRows.value, 'interviewed'),
            result: uniqueSorted(pipelineRows.value, 'result'),
            got_offer: uniqueSorted(pipelineRows.value, 'got_offer'),
        }));
        const isPipelineRowChecked = (rowId) => !!checkedPipelineRowIds[String(rowId)];
        const setPipelineRowChecked = (rowId, checked) => {
            checkedPipelineRowIds[String(rowId)] = !!checked;
        };
        const syncCheckedPipelineRows = (nextRows) => {
            const validIds = new Set((Array.isArray(nextRows) ? nextRows : []).map((row) => String(row.id)));
            Object.keys(checkedPipelineRowIds).forEach((id) => {
                if (!validIds.has(id)) delete checkedPipelineRowIds[id];
            });
            validIds.forEach((id) => {
                if (typeof checkedPipelineRowIds[id] !== 'boolean') checkedPipelineRowIds[id] = false;
            });
        };
        const checkedPipelineCount = computed(() => pipelineRows.value.filter((row) => isPipelineRowChecked(row.id)).length);
        const pipelineBatchValueOptions = computed(() => {
            const key = String(pipelineBatchOperationType.value || '').trim();
            if (!key) return [];
            const field = PIPELINE_FIELDS.find((f) => f.key === key);
            if (!field || !Array.isArray(field.options)) return [];
            return field.options.slice();
        });
        const filteredPipelineRows = computed(() => {
            const f = pipelineFilter;
            return pipelineRows.value.filter((row) => {
                if (f.date) {
                    const n = normalizeDateForInput(row.date != null ? String(row.date) : '', false);
                    if (n !== f.date) return false;
                }
                if (!fuzzyMatch(row.position, f.position)) return false;
                if (!fuzzyMatch(row.full_name, f.full_name)) return false;
                if (f.region && String(row.region || '').trim() !== f.region) return false;
                if (f.recruiter && String(row.recruiter || '').trim() !== f.recruiter) return false;
                if (Array.isArray(f.resume_screening) && f.resume_screening.length) {
                    const screeningValue = String(row.resume_screening || '').trim();
                    if (!f.resume_screening.includes(screeningValue)) return false;
                }
                if (f.interviewed && String(row.interviewed || '').trim() !== f.interviewed) return false;
                if (f.result && String(row.result || '').trim() !== f.result) return false;
                if (f.got_offer && String(row.got_offer || '').trim() !== f.got_offer) return false;
                if (!fuzzyMatch(row.onboarded, f.onboarded)) return false;
                if (showOnlyCheckedPipeline.value && !isPipelineRowChecked(row.id)) return false;
                return true;
            });
        });
        const resetPipelineFilter = () => {
            Object.assign(pipelineFilter, emptyPipelineFilter());
            resumeScreeningDropdownOpen.value = false;
            pipelineFilterPeriodHoverMonth.value = 1;
            pipelineFilterPeriodDropdownOpen.value = false;
        };
        const openPipelineBatchModal = () => {
            if (!checkedPipelineCount.value) {
                alert('请先勾选要批量操作的条目');
                return;
            }
            showPipelineBatchModal.value = true;
        };
        const toggleShowOnlyCheckedPipeline = () => {
            showOnlyCheckedPipeline.value = !showOnlyCheckedPipeline.value;
        };
        const closePipelineBatchModal = () => {
            showPipelineBatchModal.value = false;
            pipelineBatchOperationType.value = '';
            pipelineBatchOperationValue.value = '';
        };
        const applyPipelineBatchOperation = async () => {
            const key = String(pipelineBatchOperationType.value || '').trim();
            const value = String(pipelineBatchOperationValue.value || '').trim();
            if (!key) {
                alert('请先选择操作类型');
                return;
            }
            if (!value) {
                alert('请选择目标状态');
                return;
            }
            if (!pipelineBatchValueOptions.value.includes(value)) {
                alert('目标状态无效，请重新选择');
                return;
            }
            const targets = pipelineRows.value.filter((row) => isPipelineRowChecked(row.id));
            if (!targets.length) {
                alert('未找到已勾选条目，请重新选择');
                return;
            }
            let successCount = 0;
            let failCount = 0;
            const failedDetails = [];
            for (const row of targets) {
                const payload = {};
                PIPELINE_FIELDS.forEach((f) => {
                    payload[f.key] = row[f.key] != null ? String(row[f.key]) : '';
                });
                payload.serial_no = row.serial_no != null ? String(row.serial_no) : '';
                payload[key] = value;
                const validationMsg = validatePipelinePayload(payload);
                if (validationMsg) {
                    failCount += 1;
                    failedDetails.push(`${row.full_name || `ID ${row.id}`}: ${validationMsg}`);
                    continue;
                }
                const r = await fetch(`/api/delivery/pipeline/row/${row.id}`, {
                    method: 'PUT',
                    headers: { ...hdr(), 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                if (!r.ok) {
                    failCount += 1;
                    const errMsg = await readApiErrorMessage(r, `保存失败（HTTP ${r.status}）`);
                    failedDetails.push(`${row.full_name || `ID ${row.id}`}: ${errMsg}`);
                    continue;
                }
                successCount += 1;
            }
            await loadPipelineRows();
            closePipelineBatchModal();
            const lines = [`批量操作完成：成功 ${successCount} 条，失败 ${failCount} 条`];
            if (failedDetails.length) {
                lines.push('');
                lines.push('失败明细（最多前5条）：');
                failedDetails.slice(0, 5).forEach((line, idx) => lines.push(`${idx + 1}. ${line}`));
                if (failedDetails.length > 5) {
                    lines.push(`...其余 ${failedDetails.length - 5} 条失败未展开`);
                }
            }
            alert(lines.join('\n'));
        };
        const pipelineScrollWrap = ref(null);
        const pipelineFileInput = ref(null);
        const showPipelineForm = ref(false);
        const pipelineEditingId = ref(null);
        const pipelineFormReadonly = ref(false);
        const pipelineForm = reactive(emptyPipelineForm());
        const showPipelineLogs = ref(false);
        const pipelineLogsLoading = ref(false);
        const pipelineLogs = ref([]);
        const loadPipelineRows = async () => {
            if (moduleKey !== 'pipeline') return;
            const r = await fetch(`/api/clients/${clientId}/delivery/pipeline`, { headers: hdr() });
            const list = r.ok ? await r.json() : [];
            pipelineRows.value = Array.isArray(list) ? list.slice().sort((a, b) => {
                const pa = parsePeriodForSort(a.date);
                const pb = parsePeriodForSort(b.date);
                if (pb.month !== pa.month) return pb.month - pa.month;
                if (pb.week !== pa.week) return pb.week - pa.week;
                return Number(b.id || 0) - Number(a.id || 0);
            }) : [];
            syncCheckedPipelineRows(pipelineRows.value);
        };
        const openPipelineAdd = () => {
            pipelineEditingId.value = null;
            pipelineFormReadonly.value = false;
            Object.assign(pipelineForm, emptyPipelineForm());
            pipelineForm.serial_no = String(pipelineRows.value.length + 1);
            pipelinePeriodHoverMonth.value = 1;
            pipelinePeriodDropdownOpen.value = false;
            showPipelineForm.value = true;
        };
        const openPipelineEdit = (row) => {
            pipelineEditingId.value = row.id;
            pipelineFormReadonly.value = false;
            PIPELINE_FIELDS.forEach((f) => {
                const raw = row[f.key] != null ? String(row[f.key]) : '';
                pipelineForm[f.key] = PIPELINE_DATE_FIELD_KEYS.has(f.key)
                    ? normalizeDateForInput(raw, false)
                    : raw;
            });
            pipelineForm.serial_no = row.serial_no != null ? String(row.serial_no) : '';
            const parsedPeriod = parsePeriodForSort(pipelineForm.date);
            pipelinePeriodHoverMonth.value = parsedPeriod.month >= 1 ? parsedPeriod.month : 1;
            pipelinePeriodDropdownOpen.value = false;
            showPipelineForm.value = true;
        };
        const openPipelineDetail = (row) => {
            openPipelineEdit(row);
            pipelineFormReadonly.value = true;
        };
        const togglePipelinePeriodDropdown = () => {
            if (pipelineFormReadonly.value) return;
            const parsedPeriod = parsePeriodForSort(pipelineForm.date);
            if (parsedPeriod.month >= 1) {
                pipelinePeriodHoverMonth.value = parsedPeriod.month;
            } else if (!pipelinePeriodHoverMonth.value) {
                pipelinePeriodHoverMonth.value = 1;
            }
            pipelinePeriodDropdownOpen.value = !pipelinePeriodDropdownOpen.value;
        };
        const setPipelinePeriodHoverMonth = (month) => {
            pipelinePeriodHoverMonth.value = Number(month || 1) || 1;
        };
        const selectPipelinePeriod = (month, weekLabel) => {
            pipelineForm.date = pipelinePeriodValue(month, weekLabel);
            pipelinePeriodHoverMonth.value = Number(month || 1) || 1;
            pipelinePeriodDropdownOpen.value = false;
        };
        const clearPipelinePeriodField = () => {
            pipelineForm.date = '';
            pipelinePeriodDropdownOpen.value = false;
        };
        const togglePipelineFilterPeriodDropdown = () => {
            const parsedPeriod = parsePeriodForSort(pipelineFilter.date);
            if (parsedPeriod.month >= 1) {
                pipelineFilterPeriodHoverMonth.value = parsedPeriod.month;
            } else if (!pipelineFilterPeriodHoverMonth.value) {
                pipelineFilterPeriodHoverMonth.value = 1;
            }
            pipelineFilterPeriodDropdownOpen.value = !pipelineFilterPeriodDropdownOpen.value;
        };
        const setPipelineFilterPeriodHoverMonth = (month) => {
            pipelineFilterPeriodHoverMonth.value = Number(month || 1) || 1;
        };
        const selectPipelineFilterPeriod = (month, weekLabel) => {
            pipelineFilter.date = pipelinePeriodValue(month, weekLabel);
            pipelineFilterPeriodHoverMonth.value = Number(month || 1) || 1;
            pipelineFilterPeriodDropdownOpen.value = false;
        };
        const clearPipelineFilterPeriod = () => {
            pipelineFilter.date = '';
            pipelineFilterPeriodDropdownOpen.value = false;
        };
        const pipelineFieldRequired = (key) => PIPELINE_REQUIRED_KEYS.has(key);
        const pipelineFieldOptions = (field) => {
            const base = Array.isArray(field && field.options) ? field.options.slice() : [];
            const current = String(pipelineForm[field && field.key] || '').trim();
            if (current && !base.includes(current)) {
                base.unshift(current);
            }
            return base;
        };
        const validatePipelinePayload = (payload) => {
            const interviewed = String(payload.interviewed || '').trim();
            const interviewTime = String(payload.interview_time || '').trim();
            const result = String(payload.result || '').trim();
            const gotOffer = String(payload.got_offer || '').trim();
            const onboardingTime = String(payload.onboarding_time || '').trim();
            const onboarded = String(payload.onboarded || '').trim();
            const hasOnboardingSignal = Boolean(onboardingTime) || onboarded.includes('已入职') || onboarded.includes('待入职');

            if (interviewed && !['是', '放弃', '约面'].includes(interviewed)) {
                return '“是否面试”只能填写“是”“放弃”“约面”。';
            }
            if (result && !['通过', '不通过', '待定', '放弃面试', '待面ing'].includes(result)) {
                return '“面试结果”只能填写“通过”“不通过”“待定”。';
            }
            if (gotOffer && !['是', '否'].includes(gotOffer)) {
                return '“是否拿offer”只能填写“是”或“否”。';
            }
            if (interviewed === '是' && !interviewTime) {
                return '“是否面试”为“是”时，必须填写“面试时间”。';
            }
            if (gotOffer && result !== '通过') {
                return '已填写“是否拿offer”时，“面试结果”必须为“通过”。';
            }
            if (hasOnboardingSignal && !gotOffer) {
                return '已填写“入职时间”或将“是否入职”改为“X月已入职/待入职”时，必须填写“是否拿offer”。';
            }
            if (hasOnboardingSignal && result !== '通过') {
                return '已填写“入职时间”或已标记待入职/已入职时，“面试结果”必须为“通过”。';
            }
            if (hasOnboardingSignal && gotOffer === '否') {
                return '已填写“入职时间”或已标记待入职/已入职时，“是否拿offer”不能为“否”。';
            }
            return '';
        };
        const savePipelineForm = async (goInsightAfterSave = false) => {
            if (pipelineFormReadonly.value) return;
            const payload = {};
            PIPELINE_FIELDS.forEach((f) => { payload[f.key] = pipelineForm[f.key]; });
            payload.serial_no = pipelineForm.serial_no != null ? String(pipelineForm.serial_no) : '';
            const validationMsg = validatePipelinePayload(payload);
            if (validationMsg) {
                alert(validationMsg);
                return;
            }
            const url = pipelineEditingId.value
                ? `/api/delivery/pipeline/row/${pipelineEditingId.value}`
                : `/api/clients/${clientId}/delivery/pipeline`;
            const method = pipelineEditingId.value ? 'PUT' : 'POST';
            const r = await fetch(url, {
                method,
                headers: { ...hdr(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!r.ok) {
                const msg = await readApiErrorMessage(r, `保存失败（HTTP ${r.status}）`);
                alert(msg);
                return;
            }
            if (goInsightAfterSave && returnToInsight.value) {
                window.location.href = `/delivery/pipeline/${clientId}/insight`;
                return;
            }
            showPipelineForm.value = false;
            pipelineFormReadonly.value = false;
            await loadPipelineRows();
        };
        const removePipelineRow = async (row) => {
            const ok = await window.crmConfirmDeleteDialog({
                title: '确认删除记录',
                targetText: `将删除候选人：${row.full_name || '未命名'}`,
                hint: '删除后将从当前客户交付管道列表移除。',
            });
            if (!ok) return;
            const r = await fetch(`/api/delivery/pipeline/row/${row.id}`, { method: 'DELETE', headers: hdr() });
            if (!r.ok) {
                alert('删除失败');
                return;
            }
            await loadPipelineRows();
        };
        const triggerPipelineImport = () => {
            if (pipelineFileInput.value) pipelineFileInput.value.click();
        };
        const onPipelineImportFile = async (e) => {
            const f = e.target.files && e.target.files[0];
            if (!f) return;
            const token = window.prompt('该操作会先备份并清空当前客户管道数据，再导入新 CSV。\n请输入 CONFIRM 继续：', '');
            if (token == null) {
                e.target.value = '';
                return;
            }
            const fd = new FormData();
            fd.append('client_id', String(clientId));
            fd.append('file', f);
            fd.append('confirm', token);
            const r = await fetch('/api/delivery/pipeline/import', {
                method: 'POST',
                headers: hdr(),
                body: fd,
            });
            e.target.value = '';
            if (!r.ok) {
                let msg = '导入失败';
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
                j.backup_file ? `备份文件：${j.backup_file}` : '备份文件：无（原数据为空）',
                `清空旧数据：${j.cleared_existing || 0} 行`,
                `CSV 总行数：${j.total_rows || 0} 行`,
                `导入成功：${j.imported || 0} 行`,
                `跳过空行：${j.skipped_empty_rows || 0} 行`,
            ];
            if (j.matched_columns_count) {
                lines.push(`匹配字段数：${j.matched_columns_count} 列`);
            }
            if (Array.isArray(j.skipped_empty_row_numbers_preview) && j.skipped_empty_row_numbers_preview.length) {
                lines.push(`跳过行号（预览）：${j.skipped_empty_row_numbers_preview.join('、')}`);
                if (j.skipped_empty_row_numbers_truncated) {
                    lines.push('（仅展示前20条跳过行号）');
                }
            }
            alert(lines.join('\n'));
            await loadPipelineRows();
        };
        const exportPipelineCsv = async () => {
            const r = await fetch(`/api/clients/${clientId}/delivery/pipeline/export`, { headers: hdr() });
            if (!r.ok) {
                alert('导出失败');
                return;
            }
            const disposition = r.headers.get('Content-Disposition') || '';
            const blob = await r.blob();
            window.crmDownloadBlob(blob, disposition, `管道数据_${Date.now()}.csv`);
        };
        const openPipelineLogs = async () => {
            showPipelineLogs.value = true;
            pipelineLogsLoading.value = true;
            try {
                const r = await fetch(`/api/clients/${clientId}/delivery/pipeline/logs`, { headers: hdr() });
                pipelineLogs.value = r.ok ? await r.json() : [];
            } finally {
                pipelineLogsLoading.value = false;
            }
        };
        const restorePipelineLatestBackup = async () => {
            const ok = window.confirm('将使用“最近一次管道数据备份”覆盖当前客户管道数据，是否继续？');
            if (!ok) return;
            const r = await fetch(`/api/clients/${clientId}/delivery/pipeline/restore/latest`, {
                method: 'POST',
                headers: hdr(),
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
            await loadPipelineRows();
            await openPipelineLogs();
        };
        const clearPipelineDateField = (key) => {
            pipelineForm[key] = '';
        };
        function rootContainsTarget(root, target) {
            if (!root || !target) return false;
            const nodes = Array.isArray(root) ? root : [root];
            return nodes.some((node) => {
                const el = node && node.$el ? node.$el : node;
                return !!(el && typeof el.contains === 'function' && el.contains(target));
            });
        }
        function closeDropdownsForTarget(target) {
            const root = resumeScreeningFilterRef.value;
            if (resumeScreeningDropdownOpen.value && root && !rootContainsTarget(root, target)) {
                resumeScreeningDropdownOpen.value = false;
            }
            const pipelineFilterPeriodRoot = pipelineFilterPeriodPickerRef.value;
            if (pipelineFilterPeriodDropdownOpen.value && pipelineFilterPeriodRoot && !rootContainsTarget(pipelineFilterPeriodRoot, target)) {
                pipelineFilterPeriodDropdownOpen.value = false;
            }
            const pipelinePeriodRoot = pipelinePeriodPickerRef.value;
            if (pipelinePeriodDropdownOpen.value && pipelinePeriodRoot && !rootContainsTarget(pipelinePeriodRoot, target)) {
                pipelinePeriodDropdownOpen.value = false;
            }
        }
        function openPipelineEditByQuery() {
            const params = new URLSearchParams(window.location.search);
            const editIdRaw = params.get('edit_row_id');
            returnToInsight.value = params.get('return_to_insight') === '1';
            if (!editIdRaw) return;
            const editId = parseInt(editIdRaw, 10);
            if (!Number.isFinite(editId)) return;
            const target = pipelineRows.value.find((x) => Number(x.id) === editId);
            if (!target) return;
            openPipelineEdit(target);
        }
        function scrollToTopPipeline() {
            if (moduleKey === 'pipeline' && pipelineScrollWrap.value && typeof pipelineScrollWrap.value.scrollTo === 'function') {
                pipelineScrollWrap.value.scrollTo({ top: 0, behavior: 'smooth' });
                return true;
            }
            return false;
        }

        return {
            loadPipelineRows,
            pipelineRows,
            pipelineFilter,
            pipelineDateOptions,
            pipelineSelectOptions,
            filteredPipelineRows,
            resetPipelineFilter,
            resumeScreeningDropdownOpen,
            resumeScreeningFilterRef,
            resumeScreeningSummary,
            pipelineFilterPeriodPickerRef,
            pipelineFilterPeriodDropdownOpen,
            pipelineFilterPeriodHoverMonth,
            togglePipelineFilterPeriodDropdown,
            setPipelineFilterPeriodHoverMonth,
            selectPipelineFilterPeriod,
            clearPipelineFilterPeriod,
            toggleResumeScreeningDropdown,
            toggleResumeScreeningOption,
            clearResumeScreeningOption,
            PIPELINE_BATCH_OPERATION_TYPES,
            showPipelineBatchModal,
            pipelineBatchOperationType,
            pipelineBatchOperationValue,
            pipelineBatchValueOptions,
            checkedPipelineCount,
            openPipelineBatchModal,
            closePipelineBatchModal,
            applyPipelineBatchOperation,
            showOnlyCheckedPipeline,
            toggleShowOnlyCheckedPipeline,
            isPipelineRowChecked,
            setPipelineRowChecked,
            pipelineFields: PIPELINE_FIELDS,
            pipelineCompactFields: PIPELINE_COMPACT_FIELDS,
            pipelineTextareaFields: PIPELINE_TEXTAREA_FIELDS,
            pipelineFieldRequired,
            pipelineFieldOptions,
            pipelineFileInput,
            pipelineScrollWrap,
            PIPELINE_PERIOD_MONTHS,
            PIPELINE_PERIOD_WEEKS,
            pipelinePeriodPickerRef,
            pipelinePeriodDropdownOpen,
            pipelinePeriodHoverMonth,
            pipelinePeriodValue,
            pipelinePeriodDisplay,
            pipelinePeriodPanelStyle,
            togglePipelinePeriodDropdown,
            setPipelinePeriodHoverMonth,
            selectPipelinePeriod,
            clearPipelinePeriodField,
            showPipelineForm,
            pipelineEditingId,
            pipelineFormReadonly,
            pipelineForm,
            returnToInsight,
            openPipelineDetail,
            showPipelineLogs,
            pipelineLogsLoading,
            pipelineLogs,
            openPipelineAdd,
            openPipelineEdit,
            savePipelineForm,
            removePipelineRow,
            triggerPipelineImport,
            onPipelineImportFile,
            exportPipelineCsv,
            openPipelineLogs,
            restorePipelineLatestBackup,
            clearPipelineDateField,
            closeDropdownsForTarget,
            openPipelineEditByQuery,
            scrollToTopPipeline,
        };
    }

    window.CrmDeliveryDetailPipeline = {
        createPipelineState,
        PIPELINE_FIELDS,
        PIPELINE_COMPACT_FIELDS,
        PIPELINE_TEXTAREA_FIELDS,
        PIPELINE_PERIOD_MONTHS,
        PIPELINE_PERIOD_WEEKS,
        PIPELINE_BATCH_OPERATION_TYPES,
    };
})();
