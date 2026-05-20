const { createApp, ref, onMounted } = Vue;

const emptyForm = () => ({
    id: null,
    client_id: 0,
    week_period: '',
    region: '',
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

const detailFields = [
    { key: 'client_name', label: '客户名称' },
    { key: 'week_period', label: '时间（周）' },
    { key: 'region', label: '区域' },
    { key: 'salesperson', label: '销售' },
    { key: 'planned_time', label: '计划拜访时间' },
    { key: 'way', label: '拜访方式' },
    { key: 'visit_purpose', label: '拜访目的' },
    { key: 'target', label: '拜访对象' },
    { key: 'accompanying', label: '我方随行人员' },
    { key: 'completed', label: '是否完成拜访' },
    { key: 'completion_time', label: '完成拜访时间' },
    { key: 'duration_minutes', label: '拜访时长（分）' },
    { key: 'result', label: '拜访效率/目的是否达成' },
    { key: 'summary_formed', label: '拜访纪要（重要拜访摘要形成）' },
    { key: 'visit_summary', label: '拜访纪要' },
    { key: 'next_plan', label: '下一步行动' },
];

createApp({
    setup() {
        const items = ref([]);
        const filters = ref({ salespeople: [], regions: [], clients: [] });
        const filterSales = ref('');
        const filterRegion = ref('');
        const filterClientId = ref('');
        const showForm = ref(false);
        const form = ref(emptyForm());
        const detailRow = ref(null);

        const auth = () => window.crmAuthHeader();

        const loadFilters = async () => {
            const r = await fetch('/api/customer-visits/filters', { headers: auth() });
            if (r.ok) filters.value = await r.json();
        };

        const load = async () => {
            const params = new URLSearchParams();
            if (filterSales.value) params.set('salesperson', filterSales.value);
            if (filterRegion.value) params.set('region', filterRegion.value);
            if (filterClientId.value) params.set('client_id', filterClientId.value);
            const qs = params.toString();
            const r = await fetch(`/api/customer-visits${qs ? '?' + qs : ''}`, { headers: auth() });
            items.value = r.ok ? await r.json() : [];
        };

        const clearFilters = () => {
            filterSales.value = '';
            filterRegion.value = '';
            filterClientId.value = '';
            load();
        };

        const openCreate = () => {
            form.value = emptyForm();
            showForm.value = true;
        };

        const openEdit = (row) => {
            form.value = {
                id: row.id,
                client_id: row.client_id,
                week_period: row.week_period || '',
                region: row.region || '',
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
            if (!confirm(`确定删除「${row.client_name}」的拜访记录？`)) return;
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
            await loadFilters();
            await load();
        });

        return {
            items,
            filters,
            filterSales,
            filterRegion,
            filterClientId,
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
        };
    },
}).mount('#visits-app');
