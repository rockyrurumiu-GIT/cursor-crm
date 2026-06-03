/**
 * Delivery detail interviews module (Phase 5E Step 4).
 */
(function () {
    'use strict';


const INTERVIEW_FIELDS = [
    { key: 'full_name', label: '员工姓名' },
    { key: 'employment_status', label: '在职/离职', type: 'select', options: ['在职', '离职'] },
    { key: 'contact', label: '联系方式' },
    { key: 'project_name', label: '所属项目' },
    { key: 'position', label: '岗位' },
    { key: 'employee_q1', label: '员工加1' },
    { key: 'onboarding_time', label: '入职时间', type: 'date' },
    { key: 'interview_date', label: '访谈时间', type: 'date' },
    { key: 'satisfaction', label: '满意度', type: 'select', options: ['差', '一般', '良好', '满意'] },
    { key: 'work_location', label: '工作地' },
    { key: 'hometown', label: '老家' },
    { key: 'followup_1d', label: '1 D', type: 'select', options: ['Y', 'N'] },
    { key: 'followup_7d', label: '7 D', type: 'select', options: ['Y', 'N'] },
    { key: 'followup_30d', label: '30 D', type: 'select', options: ['Y', 'N'] },
    { key: 'followup_90d', label: '90 D', type: 'select', options: ['Y', 'N'] },
    { key: 'delivery_judgment', label: '交付判断', type: 'textarea' },
    { key: 'employee_requests', label: '员工诉求', type: 'textarea' },
    { key: 'delivery_todos', label: '交付待办事项', type: 'textarea' },
];
const INTERVIEW_TEXTAREA_KEYS = new Set(['delivery_judgment', 'employee_requests', 'delivery_todos']);
const INTERVIEW_COMPACT_FIELDS = INTERVIEW_FIELDS.filter((f) => !INTERVIEW_TEXTAREA_KEYS.has(f.key));
const INTERVIEW_TEXTAREA_FIELDS = INTERVIEW_FIELDS.filter((f) => INTERVIEW_TEXTAREA_KEYS.has(f.key));
/** 员工访谈弹窗保存前必填（与业务约定一致） */
const INTERVIEW_REQUIRED_KEYS = new Set([
    'full_name',
    'employment_status',
    'contact',
    'position',
    'onboarding_time',
    'interview_date',
    'satisfaction',
    'delivery_judgment',
    'employee_requests',
    'delivery_todos',
    'work_location',
    'followup_1d',
    'followup_7d',
    'followup_30d',
    'followup_90d',
]);
const INTERVIEW_LABEL_BY_KEY = Object.fromEntries(INTERVIEW_FIELDS.map((x) => [x.key, x.label]));
function collectInterviewMissingRequiredKeys(form) {
    const missing = [];
    INTERVIEW_REQUIRED_KEYS.forEach((key) => {
        const v = form[key];
        const s = v != null ? String(v).trim() : '';
        if (!s) missing.push(key);
    });
    return missing;
}
const INTERVIEW_DATE_FIELD_KEYS = new Set(
    INTERVIEW_FIELDS.filter((f) => f.type === 'date').map((f) => f.key)
);

function emptyInterviewForm() {
    const f = {};
    INTERVIEW_FIELDS.forEach((x) => { f[x.key] = ''; });
    return f;
}
function flattenInterviewHintItems(hints) {
    const items = [];
    const pushItems = (list, issueType, actionLabel, jumpSuggestion, detailBuilder) => {
        (Array.isArray(list) ? list : []).forEach((item) => {
            items.push({
                issueType,
                name: item.name || '',
                detail: detailBuilder ? detailBuilder(item) : (item.text || ''),
                actionLabel,
                jumpSuggestion,
            });
        });
    };
    pushItems(hints.activeMissing, '在职·花名册有而访谈无', '新建访谈', '本页点击“新建访谈”补录', (item) => item.text || '');
    pushItems(hints.activeInterviewNotInRoster, '在职·访谈有而花名册无', '在职 / 已离职', '「在职」跳转花名册新建；「已离职」批量将访谈标为离职', (item) => item.text || '');
    pushItems(hints.pendingInInterview, '待入职异常', '去修改', '本页点击“去修改”更新访谈状态', (item) => item.text || '');
    pushItems(hints.leftOnRoster, '离职但花名册仍有记录', '去花名册', '进入花名册页更新在职状态', (item) => `${item.rosterStatus ? `花名册状态：${item.rosterStatus}；` : ''}${item.text || ''}`);
    pushItems(hints.overdueFollowups, '1D/7D/30D/90D 超期未完成', '新建访谈', '本页点击“新建访谈”完成补访谈', (item) => item.text || '');
    pushItems(hints.staleInterviewNeedNew, '180 天无访谈', '新建访谈', '本页点击“新建访谈”补最新记录', (item) => item.text || '');
    return items;
}
function buildInterviewHintCopyText(clientName, hints) {
    const items = flattenInterviewHintItems(hints);
    if (!items.length) return '';
    const lines = [`【${clientName || '客户'} - 员工访谈待处理】`];
    items.forEach((item, idx) => {
        lines.push(`${idx + 1}. ${item.name}｜${item.issueType}｜${item.detail}｜建议动作：${item.actionLabel}｜跳转建议：${item.jumpSuggestion}`);
    });
    return lines.join('\n');
}
function buildInterviewHintCsv(clientName, hints) {
    const items = flattenInterviewHintItems(hints);
    const rows = [
        ['客户', '员工姓名', '问题类型', '问题说明', '建议动作', '跳转建议'],
        ...items.map((item) => [clientName || '', item.name || '', item.issueType || '', item.detail || '', item.actionLabel || '', item.jumpSuggestion || '']),
    ];
    return rows.map((row) => row.map(csvCell).join(',')).join('\n');
}
/** 与花名册/访谈姓名比对：去空白、合并连续空白（与肉眼核对习惯一致） */
function normalizePersonName(raw) {
    return String(raw || '').trim().replace(/\s+/g, ' ');
}
/** 在职/离职列、花名册在职情况：按关键字归类 */
function classifyEmploymentStatus(raw) {
    const s = String(raw || '').trim();
    if (!s) return 'unknown';
    if (s.includes('待入职')) return 'pending';
    if (s.includes('离职')) return 'left';
    if (s.includes('在职')) return 'active';
    return 'unknown';
}
function emptyInterviewRosterHints() {
    return {
        activeMissing: [],
        activeInterviewNotInRoster: [],
        pendingInInterview: [],
        leftOnRoster: [],
        overdueFollowups: [],
        staleInterviewNeedNew: [],
    };
}
/** 消费 URL 中的 edit_row_id，避免刷新/再次进入同页时重复弹出修改窗口 */
function stripInterviewEditQueryFromUrl() {
    try {
        const params = new URLSearchParams(window.location.search);
        if (!params.has('edit_row_id')) return;
        params.delete('edit_row_id');
        const qs = params.toString();
        const newUrl = window.location.pathname + (qs ? `?${qs}` : '') + (window.location.hash || '');
        window.history.replaceState(null, '', newUrl);
    } catch (e) {
        /* ignore */
    }
}
function emptyInterviewFilter() {
    return {
        full_name: '',
        employment_status: '',
        position: [],
        employee_q1: [],
        onboarding_start: '',
        onboarding_end: '',
        satisfaction: [],
    };
}

    function createInterviewState(deps) {
        const {
            ref,
            reactive,
            computed,
            nextTick,
            clientId,
            moduleKey,
            clientName,
            normalizeDateForInput,
            interviewDateRank,
            readApiErrorMessage,
            fuzzyMatch,
            uniqueSorted,
            multiSelectSummary,
            interviewTextLength,
            diffDaysFromDate,
            todayInputDate,
            isEmptyOrNoValue,
            csvCell,
            authHeader,
        } = deps;
        const hdr = () => (typeof authHeader === 'function' ? authHeader() : window.crmAuthHeader());


        const interviewFileInput = ref(null);
        const interviewRows = ref([]);
        const interviewScrollWrap = ref(null);
        const interviewFilter = reactive(emptyInterviewFilter());
        const rosterRows = ref([]);
        const interviewHints = ref(emptyInterviewRosterHints());
        const interviewHintRan = ref(false);
        const interviewHintBannerRef = ref(null);
        const interviewHintTotal = computed(() => {
            const h = interviewHints.value;
            return (
                h.activeMissing.length +
                h.activeInterviewNotInRoster.length +
                h.pendingInInterview.length +
                h.leftOnRoster.length +
                h.overdueFollowups.length +
                h.staleInterviewNeedNew.length
            );
        });
        const showInterviewForm = ref(false);
        const interviewEditingId = ref(null);
        const interviewFormReadonly = ref(false);
        const interviewForm = reactive(emptyInterviewForm());
        const interviewFieldErrors = reactive({});
        const resetInterviewFieldErrors = () => {
            INTERVIEW_FIELDS.forEach((x) => {
                if (interviewFieldErrors[x.key]) delete interviewFieldErrors[x.key];
            });
        };
        const clearInterviewFieldErrorKey = (key) => {
            if (interviewFieldErrors[key]) delete interviewFieldErrors[key];
        };
        const interviewFieldRequired = (key) => INTERVIEW_REQUIRED_KEYS.has(key);
        const deliveryJudgmentDuplicate = computed(() => {
            const name = String(interviewForm.full_name || '').trim();
            const judgment = String(interviewForm.delivery_judgment || '').trim();
            if (!name || !judgment) return false;
            return interviewRows.value.some((row) => {
                if (interviewEditingId.value && Number(row.id) === Number(interviewEditingId.value)) return false;
                return String(row.full_name || '').trim() === name && String(row.delivery_judgment || '').trim() === judgment;
            });
        });
        const showInterviewLogs = ref(false);
        const interviewLogsLoading = ref(false);
        const interviewLogs = ref([]);
        const interviewDisplayRows = computed(() => {
            const raw = Array.isArray(interviewRows.value) ? [...interviewRows.value] : [];
            raw.sort((a, b) => Number(a.id || 0) - Number(b.id || 0));
            const nameToSn = new Map();
            let next = 1;
            return raw.map((row) => {
                const name = String(row.full_name || '').trim();
                const key = name || '__empty__';
                let sn;
                if (nameToSn.has(key)) {
                    sn = nameToSn.get(key);
                } else {
                    sn = next;
                    nameToSn.set(key, next);
                    next += 1;
                }
                return { ...row, displaySerial: sn };
            });
        });
        const interviewPositionDropdownOpen = ref(false);
        const interviewQ1DropdownOpen = ref(false);
        const interviewSatisfactionDropdownOpen = ref(false);
        const interviewFilterPanelExpanded = ref(true);
        const toggleInterviewFilterPanel = () => {
            interviewFilterPanelExpanded.value = !interviewFilterPanelExpanded.value;
            if (!interviewFilterPanelExpanded.value) {
                interviewPositionDropdownOpen.value = false;
                interviewQ1DropdownOpen.value = false;
                interviewSatisfactionDropdownOpen.value = false;
            }
        };
        const interviewOptionSearch = reactive({
            position: '',
            employee_q1: '',
            satisfaction: '',
        });
        const interviewPositionFilterRef = ref(null);
        const interviewQ1FilterRef = ref(null);
        const interviewSatisfactionFilterRef = ref(null);
        const interviewSelectOptions = computed(() => ({
            position: uniqueSorted(interviewRows.value, 'position'),
            employee_q1: uniqueSorted(interviewRows.value, 'employee_q1'),
            satisfaction: uniqueSorted(interviewRows.value, 'satisfaction'),
        }));
        const filteredInterviewPositionOptions = computed(() => {
            return interviewSelectOptions.value.position.filter((v) => fuzzyMatch(v, interviewOptionSearch.position));
        });
        const filteredInterviewQ1Options = computed(() => {
            return interviewSelectOptions.value.employee_q1.filter((v) => fuzzyMatch(v, interviewOptionSearch.employee_q1));
        });
        const filteredInterviewSatisfactionOptions = computed(() => {
            return interviewSelectOptions.value.satisfaction.filter((v) => fuzzyMatch(v, interviewOptionSearch.satisfaction));
        });
        const interviewPositionSummary = computed(() => multiSelectSummary(interviewFilter.position));
        const interviewQ1Summary = computed(() => multiSelectSummary(interviewFilter.employee_q1));
        const interviewSatisfactionSummary = computed(() => multiSelectSummary(interviewFilter.satisfaction));
        const toggleInterviewPositionDropdown = () => {
            interviewPositionDropdownOpen.value = !interviewPositionDropdownOpen.value;
            if (interviewPositionDropdownOpen.value) {
                interviewQ1DropdownOpen.value = false;
                interviewSatisfactionDropdownOpen.value = false;
            }
        };
        const toggleInterviewQ1Dropdown = () => {
            interviewQ1DropdownOpen.value = !interviewQ1DropdownOpen.value;
            if (interviewQ1DropdownOpen.value) {
                interviewPositionDropdownOpen.value = false;
                interviewSatisfactionDropdownOpen.value = false;
            }
        };
        const toggleInterviewSatisfactionDropdown = () => {
            interviewSatisfactionDropdownOpen.value = !interviewSatisfactionDropdownOpen.value;
            if (interviewSatisfactionDropdownOpen.value) {
                interviewPositionDropdownOpen.value = false;
                interviewQ1DropdownOpen.value = false;
            }
        };
        const toggleInterviewMultiOption = (key, value) => {
            const selected = Array.isArray(interviewFilter[key]) ? interviewFilter[key] : [];
            const idx = selected.indexOf(value);
            if (idx >= 0) {
                selected.splice(idx, 1);
            } else {
                selected.push(value);
            }
        };
        const clearInterviewMultiOption = (key) => {
            if (Array.isArray(interviewFilter[key])) {
                interviewFilter[key] = [];
            }
        };
        const filteredInterviewRows = computed(() => {
            const f = interviewFilter;
            return interviewDisplayRows.value.filter((row) => {
                if (!fuzzyMatch(row.full_name, f.full_name)) return false;
                if (f.employment_status && String(row.employment_status || '').trim() !== f.employment_status) return false;
                if (Array.isArray(f.position) && f.position.length) {
                    const positionValue = String(row.position || '').trim();
                    if (!f.position.includes(positionValue)) return false;
                }
                if (Array.isArray(f.employee_q1) && f.employee_q1.length) {
                    const q1Value = String(row.employee_q1 || '').trim();
                    if (!f.employee_q1.includes(q1Value)) return false;
                }
                if (Array.isArray(f.satisfaction) && f.satisfaction.length) {
                    const satisfactionValue = String(row.satisfaction || '').trim();
                    if (!f.satisfaction.includes(satisfactionValue)) return false;
                }
                const onboardingNormalized = normalizeDateForInput(row.onboarding_time != null ? String(row.onboarding_time) : '', false);
                if (f.onboarding_start) {
                    if (!onboardingNormalized || onboardingNormalized < f.onboarding_start) return false;
                }
                if (f.onboarding_end) {
                    if (!onboardingNormalized || onboardingNormalized > f.onboarding_end) return false;
                }
                return true;
            });
        });
        const resetInterviewFilter = () => {
            Object.assign(interviewFilter, emptyInterviewFilter());
            interviewOptionSearch.position = '';
            interviewOptionSearch.employee_q1 = '';
            interviewOptionSearch.satisfaction = '';
            interviewPositionDropdownOpen.value = false;
            interviewQ1DropdownOpen.value = false;
            interviewSatisfactionDropdownOpen.value = false;
        };
        const loadInterviewRows = async () => {
            if (moduleKey !== 'interviews') return;
            const r = await fetch(`/api/clients/${clientId}/delivery/interviews`, { headers: hdr() });
            const list = r.ok ? await r.json() : [];
            interviewRows.value = Array.isArray(list) ? list : [];
        };
        const loadRosterRows = async () => {
            if (moduleKey !== 'interviews') return;
            const r = await fetch(`/api/clients/${clientId}/roster`, { headers: hdr() });
            rosterRows.value = r.ok ? await r.json() : [];
        };
        const interviewNameKey = (raw) => {
            const n = normalizePersonName(raw);
            return n ? n : '';
        };
        /** 与提示比对逻辑一致：按访谈日期（及 id 平局）取该姓名最新一条访谈 */
        const pickLatestInterviewRowForNormKey = (normKey, rows) => {
            let latest = null;
            let latestRank = 0;
            let latestId = 0;
            (Array.isArray(rows) ? rows : []).forEach((row) => {
                if (interviewNameKey(row.full_name) !== normKey) return;
                const rowId = Number(row.id || 0);
                const rowDateRank = interviewDateRank(row.interview_date != null ? String(row.interview_date) : '');
                const shouldReplace =
                    !latest ||
                    rowDateRank > latestRank ||
                    (rowDateRank === latestRank && rowId >= latestId);
                if (shouldReplace) {
                    latest = row;
                    latestRank = rowDateRank;
                    latestId = rowId;
                }
            });
            return latest;
        };
        const firstInterviewDisplayName = (rows, normKey) => {
            const row = rows.find((x) => interviewNameKey(x.full_name) === normKey);
            const s = row && row.full_name != null ? String(row.full_name).trim() : '';
            return s || normKey;
        };
        const runInterviewRosterHints = async () => {
            if (moduleKey !== 'interviews') return;
            interviewHintRan.value = true;
            await loadRosterRows();
            await loadInterviewRows();
            const todayDate = todayInputDate();
            const roster = Array.isArray(rosterRows.value) ? rosterRows.value : [];
            const interviews = Array.isArray(interviewRows.value) ? interviewRows.value : [];
            const rosterByName = new Map();
            roster.forEach((row) => {
                const nk = interviewNameKey(row.full_name);
                if (!nk) return;
                if (!rosterByName.has(nk)) {
                    rosterByName.set(nk, {
                        id: row.id,
                        employment_status: row.employment_status != null ? String(row.employment_status) : '',
                        displayName: String(row.full_name != null ? row.full_name : '').trim() || nk,
                        entryDate: row.entry_date != null ? String(row.entry_date) : '',
                    });
                }
            });
            const rosterAllNames = new Set(rosterByName.keys());
            const rosterActiveNames = new Set();
            rosterByName.forEach((meta, nk) => {
                if (classifyEmploymentStatus(meta.employment_status) === 'active') {
                    rosterActiveNames.add(nk);
                }
            });
            const interviewNameToRowId = new Map();
            const interviewNames = new Set();
            const latestInterviewMetaByName = new Map();
            interviews.forEach((row) => {
                const nk = interviewNameKey(row.full_name);
                if (!nk) return;
                interviewNames.add(nk);
                const rowId = Number(row.id || 0);
                const rowDateRank = interviewDateRank(row.interview_date != null ? String(row.interview_date) : '');
                const existingLatest = latestInterviewMetaByName.get(nk);
                const shouldReplaceLatest =
                    !existingLatest ||
                    rowDateRank > existingLatest.dateRank ||
                    (rowDateRank === existingLatest.dateRank && rowId >= existingLatest.rowId);
                if (shouldReplaceLatest) {
                    latestInterviewMetaByName.set(nk, {
                        dateRank: rowDateRank,
                        rowId,
                        status: classifyEmploymentStatus(row.employment_status),
                        row,
                    });
                }
                if (shouldReplaceLatest || !interviewNameToRowId.has(nk)) {
                    interviewNameToRowId.set(nk, rowId);
                }
            });
            const activeMissing = [];
            rosterActiveNames.forEach((nk) => {
                if (!interviewNames.has(nk)) {
                    const meta = rosterByName.get(nk);
                    activeMissing.push({
                        name: meta && meta.displayName ? meta.displayName : nk,
                        text: '花名册为在职，但员工访谈中尚无任何记录；请点击右侧「新建访谈」在本页补录并完成。',
                    });
                }
            });
            activeMissing.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
            const activeInterviewNotInRoster = [];
            interviewNames.forEach((nk) => {
                if (!rosterAllNames.has(nk)) {
                    const latestStatus = latestInterviewMetaByName.get(nk)?.status || 'unknown';
                    if (latestStatus === 'left') return;
                    activeInterviewNotInRoster.push({
                        name: firstInterviewDisplayName(interviews, nk),
                        text: '花名册中无此员工姓名，请核实是否在职、是否需补录花名册。',
                        rowId: interviewNameToRowId.get(nk),
                    });
                }
            });
            activeInterviewNotInRoster.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
            const pendingInInterview = [];
            interviewNames.forEach((nk) => {
                const latestStatus = latestInterviewMetaByName.get(nk)?.status || 'unknown';
                if (latestStatus !== 'pending') return;
                pendingInInterview.push({
                    name: firstInterviewDisplayName(interviews, nk),
                    text: '员工访谈「在职/离职」为待入职；正常情况下访谈不应出现待入职，请确认在职状态。',
                    rowId: interviewNameToRowId.get(nk),
                });
            });
            pendingInInterview.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
            const leftOnRoster = [];
            interviewNames.forEach((nk) => {
                const latestStatus = latestInterviewMetaByName.get(nk)?.status || 'unknown';
                if (latestStatus !== 'left') return;
                if (!rosterAllNames.has(nk)) return;
                const meta = rosterByName.get(nk);
                leftOnRoster.push({
                    name: firstInterviewDisplayName(interviews, nk),
                    rosterStatus: meta ? meta.employment_status : '',
                    text: '员工访谈为离职，但花名册仍有该姓名记录；正常情况离职不应在花名册中，请确认是否需更新在职情况。',
                });
            });
            leftOnRoster.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
            const overdueFollowups = [];
            const followupChecks = [
                { key: 'followup_1d', label: '1D', days: 1 },
                { key: 'followup_7d', label: '7D', days: 7 },
                { key: 'followup_30d', label: '30D', days: 30 },
                { key: 'followup_90d', label: '90D', days: 90 },
            ];
            latestInterviewMetaByName.forEach((meta, nk) => {
                if (!meta || meta.status === 'left') return;
                const row = meta.row || {};
                const daysSinceOnboarding = diffDaysFromDate(row.onboarding_time != null ? String(row.onboarding_time) : '', todayDate);
                if (daysSinceOnboarding < 0) return;
                const overdueLabels = [];
                followupChecks.forEach((item) => {
                    if (daysSinceOnboarding >= item.days && isEmptyOrNoValue(row[item.key])) {
                        overdueLabels.push(item.label);
                    }
                });
                if (!overdueLabels.length) return;
                overdueFollowups.push({
                    name: firstInterviewDisplayName(interviews, nk),
                    text: `已入职 ${daysSinceOnboarding} 天，${overdueLabels.join('、')} 为空或 N，已超期，请尽快补充访谈沟通并更新记录。`,
                    rowId: meta.rowId,
                });
            });
            overdueFollowups.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
            const staleInterviewNeedNew = [];
            rosterActiveNames.forEach((nk) => {
                if (!interviewNames.has(nk)) return;
                const latestMeta = latestInterviewMetaByName.get(nk);
                if (!latestMeta || latestMeta.status === 'left') return;
                const daysSinceLatestInterview = diffDaysFromDate(latestMeta.row?.interview_date != null ? String(latestMeta.row.interview_date) : '', todayDate);
                if (daysSinceLatestInterview < 180) return;
                const rosterMeta = rosterByName.get(nk);
                staleInterviewNeedNew.push({
                    name: rosterMeta && rosterMeta.displayName ? rosterMeta.displayName : firstInterviewDisplayName(interviews, nk),
                    text: `最近一次访谈距今已 ${daysSinceLatestInterview} 天，超过 180 天未做访谈，请新建访谈记录。`,
                });
            });
            staleInterviewNeedNew.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
            interviewHints.value = {
                activeMissing,
                activeInterviewNotInRoster,
                pendingInInterview,
                leftOnRoster,
                overdueFollowups,
                staleInterviewNeedNew,
            };
            await nextTick();
            const tot =
                activeMissing.length +
                activeInterviewNotInRoster.length +
                pendingInInterview.length +
                leftOnRoster.length +
                overdueFollowups.length +
                staleInterviewNeedNew.length;
            if (tot > 0 && interviewHintBannerRef.value && typeof interviewHintBannerRef.value.scrollIntoView === 'function') {
                interviewHintBannerRef.value.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        };
        const goRosterAddForInterviewHint = (displayName) => {
            const n = displayName != null ? String(displayName).trim() : '';
            const q = n ? `?roster_add=1&prefill_full_name=${encodeURIComponent(n)}` : '?roster_add=1';
            window.location.href = `/customers/roster/${clientId}${q}`;
        };
        const markInterviewHintLeftForName = async (displayName) => {
            const n = displayName != null ? String(displayName).trim() : '';
            if (!n) {
                alert('无法识别员工姓名');
                return;
            }
            const r = await fetch(`/api/clients/${clientId}/delivery/interviews/mark-employment-left`, {
                method: 'POST',
                headers: { ...hdr(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name: n }),
            });
            if (!r.ok) {
                let msg = '操作失败';
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') msg = err.detail;
                } catch (e) { /* ignore */ }
                alert(msg);
                return;
            }
            let updated = 0;
            try {
                const j = await r.json();
                if (j && j.updated != null) updated = Number(j.updated) || 0;
            } catch (e) { /* ignore */ }
            await loadInterviewRows();
            if (interviewHintRan.value) {
                await runInterviewRosterHints();
            }
            alert(updated ? `已将 ${updated} 条访谈记录标记为离职` : '未找到匹配的访谈记录');
        };
        /** 按姓名匹配最近一条访谈，预填可继承字段（不改写当前姓名）；无匹配返回 false */
        const applyInterviewFormPrefillFromLatestRow = (displayName) => {
            const n = displayName != null ? String(displayName).trim() : '';
            const nk = interviewNameKey(n);
            if (!nk) return false;
            const latest = pickLatestInterviewRowForNormKey(nk, interviewRows.value);
            if (!latest) return false;
            const st = latest.employment_status != null ? String(latest.employment_status).trim() : '';
            interviewForm.employment_status = st || '在职';
            interviewForm.contact = latest.contact != null ? String(latest.contact).trim() : '';
            interviewForm.project_name = latest.project_name != null ? String(latest.project_name).trim() : '';
            interviewForm.position = latest.position != null ? String(latest.position).trim() : '';
            interviewForm.employee_q1 = latest.employee_q1 != null ? String(latest.employee_q1).trim() : '';
            interviewForm.onboarding_time = normalizeDateForInput(
                latest.onboarding_time != null ? String(latest.onboarding_time) : '',
                false,
            );
            interviewForm.work_location = latest.work_location != null ? String(latest.work_location).trim() : '';
            interviewForm.hometown = latest.hometown != null ? String(latest.hometown).trim() : '';
            const d1 = String(latest.followup_1d || '').trim().toUpperCase();
            const d7 = String(latest.followup_7d || '').trim().toUpperCase();
            if (d1 === 'Y' && d7 === 'Y' && isEmptyOrNoValue(latest.followup_30d)) {
                interviewForm.followup_1d = 'Y';
                interviewForm.followup_7d = 'Y';
                interviewForm.followup_30d = '';
                interviewForm.followup_90d = '';
            } else {
                ['followup_1d', 'followup_7d', 'followup_30d', 'followup_90d'].forEach((k) => {
                    const v = latest[k] != null ? String(latest[k]).trim() : '';
                    const u = v.toUpperCase();
                    interviewForm[k] = u === 'Y' || u === 'N' ? u : '';
                });
            }
            return true;
        };
        /** 新增员工访谈：输入姓名并离开输入框后，与提示「新建访谈」相同的预填逻辑 */
        const onInterviewFormCompactBlur = (key) => {
            if (key !== 'full_name') return;
            if (!showInterviewForm.value || interviewEditingId.value || interviewFormReadonly.value) return;
            applyInterviewFormPrefillFromLatestRow(interviewForm.full_name);
        };
        const openInterviewAdd = () => {
            interviewEditingId.value = null;
            interviewFormReadonly.value = false;
            Object.assign(interviewForm, emptyInterviewForm());
            resetInterviewFieldErrors();
            showInterviewForm.value = true;
        };
        /** 花名册有而访谈无：直接打开新增并预填姓名（缺访谈应补录访谈，而非跳转花名册）；
         * 若已有历史访谈，则按最近一条预填可继承字段（含工作地、老家；历史为空则留空）；阶段项在「1D/7D 已完成、30D 未做」时继承 1D/7D=Y 并清空 30D/90D 供本次补录。 */
        const openInterviewAddForHintName = (displayName) => {
            interviewEditingId.value = null;
            interviewFormReadonly.value = false;
            Object.assign(interviewForm, emptyInterviewForm());
            resetInterviewFieldErrors();
            const n = displayName != null ? String(displayName).trim() : '';
            if (n) {
                interviewForm.full_name = n;
            }
            const hadLatest = n ? applyInterviewFormPrefillFromLatestRow(n) : false;
            if (n && !hadLatest) {
                interviewForm.employment_status = '在职';
            }
            showInterviewForm.value = true;
        };
        const openInterviewEdit = (row) => {
            interviewEditingId.value = row.id;
            interviewFormReadonly.value = false;
            resetInterviewFieldErrors();
            INTERVIEW_FIELDS.forEach((f) => {
                const raw = row[f.key] != null ? String(row[f.key]) : '';
                interviewForm[f.key] = INTERVIEW_DATE_FIELD_KEYS.has(f.key)
                    ? normalizeDateForInput(raw, false)
                    : raw;
            });
            showInterviewForm.value = true;
        };
        const openInterviewDetail = (row) => {
            openInterviewEdit(row);
            interviewFormReadonly.value = true;
        };
        const openInterviewEditByQuery = () => {
            if (moduleKey !== 'interviews') return;
            const params = new URLSearchParams(window.location.search);
            const editIdRaw = params.get('edit_row_id');
            if (!editIdRaw) return;
            const editId = parseInt(editIdRaw, 10);
            if (!Number.isFinite(editId)) return;
            const target = interviewRows.value.find((x) => Number(x.id) === editId);
            if (!target) return;
            openInterviewEdit(target);
            stripInterviewEditQueryFromUrl();
        };
        const saveInterviewForm = async () => {
            if (interviewFormReadonly.value) return;
            resetInterviewFieldErrors();
            const missing = collectInterviewMissingRequiredKeys(interviewForm);
            if (missing.length) {
                missing.forEach((k) => {
                    interviewFieldErrors[k] = true;
                });
                const labels = missing.map((k) => INTERVIEW_LABEL_BY_KEY[k] || k).join('、');
                alert(`请填写以下必填项：${labels}`);
                return;
            }
            if (interviewTextLength(interviewForm.delivery_judgment) < 20) {
                interviewFieldErrors.delivery_judgment = true;
                alert('交付判断至少需要填写 20 个字');
                return;
            }
            if (interviewTextLength(interviewForm.delivery_todos) < 10) {
                interviewFieldErrors.delivery_todos = true;
                alert('交付待办事项至少需要填写 10 个字');
                return;
            }
            if (deliveryJudgmentDuplicate.value) {
                interviewFieldErrors.delivery_judgment = true;
                alert('同一员工的多条访谈记录中，交付判断内容不能重复');
                return;
            }
            const payload = {};
            INTERVIEW_FIELDS.forEach((f) => { payload[f.key] = interviewForm[f.key]; });
            const url = interviewEditingId.value
                ? `/api/delivery/interviews/row/${interviewEditingId.value}`
                : `/api/clients/${clientId}/delivery/interviews`;
            const method = interviewEditingId.value ? 'PUT' : 'POST';
            const r = await fetch(url, {
                method,
                headers: { ...hdr(), 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!r.ok) {
                let msg = '保存失败';
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') msg = err.detail;
                } catch (e) {}
                alert(msg);
                return;
            }
            stripInterviewEditQueryFromUrl();
            showInterviewForm.value = false;
            interviewFormReadonly.value = false;
            await loadInterviewRows();
        };
        const removeInterviewRow = async (row) => {
            const r = await fetch(`/api/delivery/interviews/row/${row.id}`, { method: 'DELETE', headers: hdr() });
            if (!r.ok) {
                alert('删除失败');
                return;
            }
            await loadInterviewRows();
        };
        const clearInterviewDateField = (key) => {
            interviewForm[key] = '';
        };
        const triggerInterviewImport = () => {
            if (interviewFileInput.value) interviewFileInput.value.click();
        };
        const onInterviewImportFile = async (e) => {
            const f = e.target.files && e.target.files[0];
            if (!f) return;
            const token = window.prompt('该操作会先备份并清空当前客户员工访谈数据，再导入新 CSV。\n请输入 CONFIRM 继续：', '');
            if (token == null) {
                e.target.value = '';
                return;
            }
            const fd = new FormData();
            fd.append('file', f);
            fd.append('confirm', token);
            const r = await fetch(`/api/clients/${clientId}/delivery/interviews/import`, {
                method: 'POST',
                headers: hdr(),
                body: fd,
            });
            e.target.value = '';
            if (!r.ok) {
                let msg = `导入失败（HTTP ${r.status}）`;
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') {
                        msg = err.detail;
                    } else if (Array.isArray(err.detail)) {
                        msg = err.detail.map((x) => (x && x.msg) || JSON.stringify(x)).join('；') || msg;
                    } else if (err.detail != null) {
                        msg = String(err.detail);
                    }
                } catch (err2) {
                    if (r.status === 404) {
                        msg = '接口不存在（404）。请确认已重启 CRM 服务并更新到包含「员工访谈导入」的版本。';
                    }
                }
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
            await loadInterviewRows();
        };
        const exportInterviewCsv = async () => {
            const r = await fetch(`/api/clients/${clientId}/delivery/interviews/export`, { headers: hdr() });
            if (!r.ok) {
                alert('导出失败');
                return;
            }
            const disposition = r.headers.get('Content-Disposition') || '';
            const blob = await r.blob();
            window.crmDownloadBlob(blob, disposition, `员工访谈_${Date.now()}.csv`);
        };
        const openInterviewLogs = async () => {
            showInterviewLogs.value = true;
            interviewLogsLoading.value = true;
            try {
                const r = await fetch(`/api/clients/${clientId}/delivery/interviews/logs`, { headers: hdr() });
                interviewLogs.value = r.ok ? await r.json() : [];
            } finally {
                interviewLogsLoading.value = false;
            }
        };
        const restoreInterviewLatestBackup = async () => {
            const ok = window.confirm('将使用「最近一次员工访谈备份」覆盖当前客户数据，是否继续？');
            if (!ok) return;
            const r = await fetch(`/api/clients/${clientId}/delivery/interviews/restore/latest`, {
                method: 'POST',
                headers: hdr(),
            });
            if (!r.ok) {
                let msg = '回滚失败';
                try {
                    const err = await r.json();
                    if (typeof err.detail === 'string') msg = err.detail;
                } catch (e2) {}
                alert(msg);
                return;
            }
            const j = await r.json();
            alert(`已从备份 ${j.backup_file} 回滚，清空 ${j.cleared_existing || 0} 行，恢复 ${j.restored_rows || 0} 行`);
            await loadInterviewRows();
            await openInterviewLogs();
        };
        const copyInterviewHints = async () => {
            const text = buildInterviewHintCopyText(clientName.value, interviewHints.value);
            if (!text) {
                alert('当前没有可复制的提示结果');
                return;
            }
            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(text);
                } else {
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.setAttribute('readonly', 'readonly');
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }
                alert('提示结果已复制');
            } catch (err) {
                alert('复制失败，请稍后重试');
            }
        };
        const exportInterviewHintsCsv = () => {
            const csv = buildInterviewHintCsv(clientName.value, interviewHints.value);
            if (!csv) {
                alert('当前没有可导出的提示结果');
                return;
            }
            const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
            const safeClientName = String(clientName.value || '客户').trim() || '客户';
            window.crmDownloadBlob(blob, '', `${safeClientName}_员工访谈提示_${Date.now()}.csv`);
        };

        function rootContainsTarget(root, target) {
            if (!root || !target) return false;
            const nodes = Array.isArray(root) ? root : [root];
            return nodes.some((node) => {
                const el = node && node.$el ? node.$el : node;
                return !!(el && typeof el.contains === 'function' && el.contains(target));
            });
        }
        function closeInterviewDropdownsForTarget(target) {
            const interviewPositionRoot = interviewPositionFilterRef.value;
            if (interviewPositionDropdownOpen.value && interviewPositionRoot && !rootContainsTarget(interviewPositionRoot, target)) {
                interviewPositionDropdownOpen.value = false;
            }
            const interviewQ1Root = interviewQ1FilterRef.value;
            if (interviewQ1DropdownOpen.value && interviewQ1Root && !rootContainsTarget(interviewQ1Root, target)) {
                interviewQ1DropdownOpen.value = false;
            }
            const interviewSatisfactionRoot = interviewSatisfactionFilterRef.value;
            if (interviewSatisfactionDropdownOpen.value && interviewSatisfactionRoot && !rootContainsTarget(interviewSatisfactionRoot, target)) {
                interviewSatisfactionDropdownOpen.value = false;
            }
        }
        function scrollToTopInterviews() {
            if (moduleKey === 'interviews' && interviewScrollWrap.value && typeof interviewScrollWrap.value.scrollTo === 'function') {
                interviewScrollWrap.value.scrollTo({ top: 0, behavior: 'smooth' });
                return true;
            }
            return false;
        }

        return {
            loadInterviewRows,
            interviewFileInput,
            interviewRows,
            interviewScrollWrap,
            interviewFilter,
            rosterRows,
            interviewHints,
            interviewHintRan,
            interviewHintBannerRef,
            interviewHintTotal,
            showInterviewForm,
            interviewEditingId,
            interviewFormReadonly,
            interviewForm,
            interviewFieldErrors,
            resetInterviewFieldErrors,
            clearInterviewFieldErrorKey,
            interviewFieldRequired,
            deliveryJudgmentDuplicate,
            showInterviewLogs,
            interviewLogsLoading,
            interviewLogs,
            interviewDisplayRows,
            interviewPositionDropdownOpen,
            interviewQ1DropdownOpen,
            interviewSatisfactionDropdownOpen,
            interviewFilterPanelExpanded,
            toggleInterviewFilterPanel,
            interviewOptionSearch,
            interviewPositionFilterRef,
            interviewQ1FilterRef,
            interviewSatisfactionFilterRef,
            interviewSelectOptions,
            filteredInterviewPositionOptions,
            filteredInterviewQ1Options,
            filteredInterviewSatisfactionOptions,
            interviewPositionSummary,
            interviewQ1Summary,
            interviewSatisfactionSummary,
            toggleInterviewPositionDropdown,
            toggleInterviewQ1Dropdown,
            toggleInterviewSatisfactionDropdown,
            toggleInterviewMultiOption,
            clearInterviewMultiOption,
            filteredInterviewRows,
            resetInterviewFilter,
            loadRosterRows,
            runInterviewRosterHints,
            goRosterAddForInterviewHint,
            markInterviewHintLeftForName,
            applyInterviewFormPrefillFromLatestRow,
            onInterviewFormCompactBlur,
            openInterviewAdd,
            openInterviewAddForHintName,
            openInterviewEdit,
            openInterviewDetail,
            saveInterviewForm,
            removeInterviewRow,
            clearInterviewDateField,
            triggerInterviewImport,
            onInterviewImportFile,
            exportInterviewCsv,
            openInterviewLogs,
            restoreInterviewLatestBackup,
            copyInterviewHints,
            exportInterviewHintsCsv,
            closeInterviewDropdownsForTarget,
            openInterviewEditByQuery,
            scrollToTopInterviews,
            interviewFields: INTERVIEW_FIELDS,
            interviewCompactFields: INTERVIEW_COMPACT_FIELDS,
            interviewTextareaFields: INTERVIEW_TEXTAREA_FIELDS,
        };
    }

    window.CrmDeliveryDetailInterviews = {
        createInterviewState,
        INTERVIEW_FIELDS,
        INTERVIEW_COMPACT_FIELDS,
        INTERVIEW_TEXTAREA_FIELDS,
    };
})();
