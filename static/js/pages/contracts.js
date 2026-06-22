/**
 * Contract management page — attachment filters and upload.
 */
const { createApp, ref, reactive, computed, watch, onMounted, onUnmounted } = Vue;

function emptyForm() {
    return {
        title: '',
        client_id: '',
        contract_no: '',
        end_date: '',
    };
}

function buildQuery(filters) {
    const p = new URLSearchParams();
    if (filters.q) p.set('q', filters.q);
    if (filters.status) p.set('status', filters.status);
    if (filters.client_id) p.set('client_id', filters.client_id);
    if (filters.expires_before) p.set('expires_before', filters.expires_before);
    const qs = p.toString();
    return qs ? '?' + qs : '';
}

function statusBadge(code) {
    const m = {
        draft: 'bg-gray-100 text-gray-600',
        signed: 'bg-blue-100 text-blue-800',
        active: 'bg-green-100 text-green-800',
        closed: 'bg-slate-100 text-slate-600',
    };
    return m[code] || 'bg-gray-100 text-gray-600';
}

createApp({
    setup() {
        const items = ref([]);
        const loading = ref(false);
        const submitting = ref(false);
        const filterPanelExpanded = ref(false);
        const pageSize = 10;
        const currentPage = ref(1);
        const filters = reactive({
            q: '',
            status: '',
            client_id: '',
            expires_before: '',
        });
        const formOptions = reactive({
            statuses: [],
            clients: [],
        });
        const showForm = ref(false);
        const showDetail = ref(false);
        const detailRow = ref(null);
        const form = reactive(emptyForm());
        const selectedFile = ref(null);
        const selectedFileName = ref('');
        const fileInput = ref(null);
        const dragging = ref(false);
        const showPreview = ref(false);
        const previewTitle = ref('');
        const previewContent = ref('');
        const canWriteContracts = ref(false);

        const filteredItems = computed(() => items.value);
        const totalPages = computed(() => Math.max(1, Math.ceil(filteredItems.value.length / pageSize)));
        const pagedItems = computed(() => {
            const start = (currentPage.value - 1) * pageSize;
            return filteredItems.value.slice(start, start + pageSize);
        });
        const pageNumbers = computed(() => {
            const total = totalPages.value;
            const cur = currentPage.value;
            const max = 7;
            if (total <= max) return Array.from({ length: total }, (_, i) => i + 1);
            let start = Math.max(1, cur - 3);
            const end = Math.min(total, start + max - 1);
            start = Math.max(1, end - max + 1);
            return Array.from({ length: end - start + 1 }, (_, i) => start + i);
        });

        const goPage = (p) => {
            currentPage.value = Math.min(Math.max(1, p), totalPages.value);
        };

        watch(() => filteredItems.value.length, () => {
            if (currentPage.value > totalPages.value) currentPage.value = totalPages.value;
        });

        function refreshContractPermissions() {
            canWriteContracts.value = !!window.crmIsSuper
                || !!(window.crmHasPermission && window.crmHasPermission('crm.opportunities.write'));
        }

        async function loadFormOptions() {
            const data = await window.crmApi.get('/api/contracts/form-options');
            formOptions.statuses = data.statuses || [];
            formOptions.clients = data.clients || [];
        }

        async function loadContracts() {
            loading.value = true;
            try {
                items.value = await window.crmApi.get('/api/contracts' + buildQuery(filters));
                currentPage.value = 1;
            } finally {
                loading.value = false;
            }
        }

        function resetFilters() {
            filters.q = '';
            filters.status = '';
            filters.client_id = '';
            filters.expires_before = '';
            loadContracts();
        }

        function openCreate() {
            Object.assign(form, emptyForm());
            selectedFile.value = null;
            selectedFileName.value = '';
            if (fileInput.value) fileInput.value.value = '';
            showForm.value = true;
        }

        function closeForm() {
            showForm.value = false;
        }

        function setSelectedFile(f) {
            selectedFile.value = f || null;
            selectedFileName.value = f ? f.name : '';
        }

        function onFileChange(e) {
            const f = e.target.files && e.target.files[0];
            setSelectedFile(f);
        }

        function triggerFilePick() {
            if (fileInput.value) fileInput.value.click();
        }

        function onDrop(e) {
            dragging.value = false;
            const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
            if (f) setSelectedFile(f);
        }

        function clearSelectedFile() {
            selectedFile.value = null;
            selectedFileName.value = '';
            if (fileInput.value) fileInput.value.value = '';
        }

        async function submitForm() {
            submitting.value = true;
            try {
                if (!selectedFile.value) {
                    alert('请选择文件');
                    return;
                }
                if (!form.client_id) {
                    alert('请选择客户');
                    return;
                }
                const fd = new FormData();
                fd.append('title', form.title);
                fd.append('client_id', form.client_id);
                fd.append('contract_no', form.contract_no || '');
                fd.append('end_date', form.end_date || '');
                fd.append('file', selectedFile.value);
                const headers = window.crmAuthHeader ? window.crmAuthHeader() : {};
                const r = await fetch('/api/contracts', {
                    method: 'POST',
                    headers,
                    credentials: 'same-origin',
                    body: fd,
                });
                if (!r.ok) {
                    const err = await r.json().catch(() => ({}));
                    throw new Error(err.detail || '上传失败');
                }
                showForm.value = false;
                await loadContracts();
            } catch (e) {
                alert(e.message || '上传失败');
            } finally {
                submitting.value = false;
            }
        }

        const displayAmount = (raw) => {
            const digits = String(raw || '').replace(/[^\d.-]/g, '').trim();
            if (!digits) return '—';
            const n = Number(digits);
            if (!Number.isFinite(n)) return String(raw || '—');
            return n.toLocaleString('zh-CN');
        };

        const formatDateTime = (raw) => {
            if (!raw) return '—';
            const d = new Date(raw);
            if (Number.isNaN(d.getTime())) return raw;
            return d.toLocaleString('zh-CN', { hour12: false });
        };

        const openDetail = (row) => {
            detailRow.value = row;
            showDetail.value = true;
        };
        const closeDetail = () => {
            showDetail.value = false;
            detailRow.value = null;
        };

        const openPreview = (row) => {
            if (row.has_attachment) {
                window.location.href = '/api/contracts/' + row.id + '/download';
                return;
            }
            previewTitle.value = row.material_name || row.title || row.contract_no || '合同预览';
            previewContent.value = row.sow_markdown || '';
            showPreview.value = true;
        };
        const closePreview = () => {
            showPreview.value = false;
            previewTitle.value = '';
            previewContent.value = '';
        };

        const deleteContract = (row) => {
            const name = row.material_name || row.title || row.contract_no || '该合同';
            if (!window.confirm('确定删除「' + name + '」？')) return;
            alert('合同由交接单自动生成，暂不支持删除');
        };

        const seed = async (c, m) => {
            const r = await fetch('/api/contracts/' + c.id + '/milestones/' + m.id + '/seed-settlement', {
                method: 'POST',
                headers: window.crmAuthHeader ? window.crmAuthHeader() : {},
            });
            if (r.ok) {
                await loadContracts();
                if (detailRow.value && detailRow.value.id === c.id) {
                    detailRow.value = items.value.find((item) => item.id === c.id) || null;
                }
            } else {
                alert((await r.json()).detail || '失败');
            }
        };

        onMounted(async () => {
            refreshContractPermissions();
            window.addEventListener('crm-shell-ready', refreshContractPermissions);
            await loadFormOptions();
            refreshContractPermissions();
            await loadContracts();
        });

        onUnmounted(() => {
            window.removeEventListener('crm-shell-ready', refreshContractPermissions);
        });

        return {
            items,
            loading,
            submitting,
            filterPanelExpanded,
            filters,
            formOptions,
            filteredItems,
            pagedItems,
            pageSize,
            currentPage,
            totalPages,
            pageNumbers,
            goPage,
            showForm,
            showDetail,
            detailRow,
            form,
            fileInput,
            selectedFileName,
            dragging,
            showPreview,
            previewTitle,
            previewContent,
            canWriteContracts,
            loadContracts,
            resetFilters,
            openCreate,
            closeForm,
            onFileChange,
            triggerFilePick,
            onDrop,
            clearSelectedFile,
            submitForm,
            openDetail,
            closeDetail,
            openPreview,
            closePreview,
            deleteContract,
            seed,
            displayAmount,
            formatDateTime,
            statusBadge,
        };
    },
}).mount('#contracts-app');
