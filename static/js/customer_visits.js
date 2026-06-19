const { createApp, ref, onMounted, nextTick } = Vue;

const todayIso = () => new Date().toISOString().slice(0, 10);

/** 将 week_period（含旧版周区间文本）转为 date 输入框可用的 YYYY-MM-DD */
const weekPeriodToDateInput = (val) => {
    const s = (val || '').trim();
    if (!s) return '';
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const m = s.match(/^(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})/);
    if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
    return '';
};

const emptyForm = () => ({
    id: null,
    client_id: 0,
    week_period: '',
    region: '',
    city: '',
    salesperson: '',
    planned_time: '',
    way: '',
    visit_purpose: '',
    target: '',
    accompanying: '',
    completed: '',
    completion_time: '',
    duration_minutes: '',
    result: '',
    summary_formed: '',
    visit_summary: '',
    next_plan: '',
});

const VISIT_COL_STORAGE = 'visit-table-col-widths-v3';
const VISIT_COL_MIN = 48;
const VISIT_COL_EDGE = 12;
const VISIT_COL_DEFAULTS = [
    96, 72, 72, 72, 120, 80, 200, 100, 120,
    88, 140, 180, 180, 120,
];

const detailFields = [
    { key: 'client_name', label: '客户名称' },
    { key: 'week_period', label: '日期' },
    { key: 'region', label: '区域' },
    { key: 'city', label: '城市' },
    { key: 'salesperson', label: '销售' },
    { key: 'way', label: '拜访方式' },
    { key: 'visit_purpose', label: '拜访目标' },
    { key: 'target', label: '拜访对象' },
    { key: 'accompanying', label: '我方随行人员' },
    { key: 'duration_minutes', label: '拜访时长（分）' },
    { key: 'result', label: '拜访目标是否达成' },
    { key: 'visit_summary', label: '拜访纪要' },
    { key: 'next_plan', label: '下一步行动' },
];

createApp({
    setup() {
        const items = ref([]);
        const filters = ref({ salespeople: [], regions: [], clients: [], weeks: [] });
        const filterSales = ref('');
        const filterRegion = ref('');
        const filterClientId = ref('');
        const filterWeek = ref('');
        const filterPanelExpanded = ref(false);
        const showForm = ref(false);
        const form = ref(emptyForm());
        const detailRow = ref(null);

        const auth = () => window.crmAuthHeader();
        const canDeletePermission = (code) => !window.crmHasPermission || window.crmHasPermission(code);

        const loadFilters = async () => {
            const r = await fetch(`/api/customer-visits/filters?_=${Date.now()}`, {
                headers: auth(),
                cache: 'no-store',
            });
            if (!r.ok) return;
            const data = await r.json();
            filters.value = {
                salespeople: data.salespeople || [],
                regions: data.regions || [],
                clients: data.clients || [],
                weeks: Array.isArray(data.weeks) ? data.weeks : [],
            };
        };

        const load = async () => {
            const params = new URLSearchParams();
            if (filterSales.value) params.set('salesperson', filterSales.value);
            if (filterRegion.value) params.set('region', filterRegion.value);
            if (filterClientId.value) params.set('client_id', filterClientId.value);
            if (filterWeek.value) params.set('week', filterWeek.value);
            const qs = params.toString();
            const r = await fetch(`/api/customer-visits${qs ? '?' + qs : ''}`, { headers: auth() });
            items.value = r.ok ? await r.json() : [];
            nextTick(() => window.crmRefreshOpColumnWidths?.());
        };

        const clearFilters = () => {
            filterSales.value = '';
            filterRegion.value = '';
            filterClientId.value = '';
            filterWeek.value = '';
            load();
        };

        const openCreate = () => {
            form.value = emptyForm();
            form.value.week_period = todayIso();
            showForm.value = true;
        };

        const openEdit = (row) => {
            form.value = {
                id: row.id,
                client_id: row.client_id,
                week_period: weekPeriodToDateInput(row.week_period || row.date || ''),
                region: row.region || '',
                city: row.city || '',
                salesperson: row.salesperson || '',
                planned_time: row.planned_time || '',
                way: row.way || '',
                visit_purpose: row.visit_purpose || '',
                target: row.target || '',
                accompanying: row.accompanying || '',
                completed: row.completed || '',
                completion_time: row.completion_time || '',
                duration_minutes: row.duration_minutes || '',
                result: row.result || '',
                summary_formed: row.summary_formed || '',
                visit_summary: row.visit_summary || '',
                next_plan: row.next_plan || '',
            };
            showForm.value = true;
        };

        const openDetail = (row) => {
            detailRow.value = { ...row };
        };

        const save = async () => {
            if (!form.value.client_id) {
                alert('请选择客户');
                return;
            }
            const body = { ...form.value };
            delete body.id;
            const url = form.value.id ? `/api/customer-visits/${form.value.id}` : '/api/customer-visits';
            const r = await fetch(url, {
                method: form.value.id ? 'PUT' : 'POST',
                headers: { ...auth(), 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (r.ok) {
                showForm.value = false;
                await loadFilters();
                await load();
            } else {
                const d = await r.json().catch(() => ({}));
                alert(d.detail || '保存失败');
            }
        };

        const remove = async (row) => {
            const r = await fetch(`/api/customer-visits/${row.id}`, { method: 'DELETE', headers: auth() });
            if (r.ok) {
                await loadFilters();
                await load();
            } else {
                const d = await r.json().catch(() => ({}));
                alert(d.detail || '删除失败');
            }
        };

        onMounted(async () => {
            const params = new URLSearchParams(window.location.search);
            if (params.get('salesperson')) filterSales.value = params.get('salesperson');
            if (params.get('region')) filterRegion.value = params.get('region');
            if (params.get('client_id')) filterClientId.value = params.get('client_id');
            if (params.get('week')) filterWeek.value = params.get('week');
            await loadFilters();
            await load();
            const table = document.querySelector('#visits-app .visit-table');
            if (table && window.crmInitTableColumnResize) {
                table.dataset.tableResizeKey = VISIT_COL_STORAGE;
                table.dataset.tableMinWidth = '1672';
                window.crmInitTableColumnResize(table, {
                    defaults: VISIT_COL_DEFAULTS,
                    minWidth: VISIT_COL_MIN,
                    edge: VISIT_COL_EDGE,
                });
            }
            nextTick(() => window.crmRefreshOpColumnWidths?.());
        });

        return {
            items,
            filters,
            filterSales,
            filterRegion,
            filterClientId,
            filterWeek,
            filterPanelExpanded,
            showForm,
            form,
            detailRow,
            detailFields,
            load,
            clearFilters,
            openCreate,
            openEdit,
            openDetail,
            save,
            remove,
            canDeletePermission,
        };
    },
}).mount('#visits-app');
