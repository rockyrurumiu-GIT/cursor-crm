/**
 * Company materials library page.
 */
const { createApp, ref, reactive, onMounted, onUnmounted } = Vue;

function emptyForm() {
    return {
        title: '',
        category: 'other',
        confidentiality: 'internal',
        description: '',
        owner_dept_id: '',
        expires_at: '',
    };
}

function formatFileSize(bytes) {
    const n = Number(bytes) || 0;
    if (n < 1024) return n + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(1) + ' MB';
}

function confidentialityBadge(code) {
    const m = {
        public: 'bg-green-100 text-green-800',
        internal: 'bg-amber-100 text-amber-800',
        confidential: 'bg-red-100 text-red-800',
    };
    return m[code] || 'bg-gray-100 text-gray-600';
}

function statusBadge(code) {
    const m = {
        active: 'bg-green-100 text-green-800',
        archived: 'bg-gray-100 text-gray-600',
    };
    return m[code] || 'bg-gray-100 text-gray-600';
}

function buildQuery(filters) {
    const p = new URLSearchParams();
    if (filters.q) p.set('q', filters.q);
    if (filters.category) p.set('category', filters.category);
    if (filters.confidentiality) p.set('confidentiality', filters.confidentiality);
    if (filters.status) p.set('status', filters.status);
    if (filters.owner_dept_id) p.set('owner_dept_id', filters.owner_dept_id);
    if (filters.expires_before) p.set('expires_before', filters.expires_before);
    const qs = p.toString();
    return qs ? '?' + qs : '';
}

createApp({
    setup() {
        const items = ref([]);
        const loading = ref(false);
        const submitting = ref(false);
        const filters = reactive({
            q: '',
            category: '',
            confidentiality: '',
            status: 'active',
            owner_dept_id: '',
            expires_before: '',
        });
        const formOptions = reactive({
            categories: [],
            confidentiality_levels: [],
            statuses: [],
            depts: [],
        });
        const showForm = ref(false);
        const showDetail = ref(false);
        const formMode = ref('create');
        const form = reactive(emptyForm());
        const detailRow = ref(null);
        const editId = ref(null);
        const selectedFile = ref(null);
        const selectedFileName = ref('');
        const editFileName = ref('');
        const editFileSize = ref(0);
        const fileInput = ref(null);
        const dragging = ref(false);

        const canWriteMaterials = ref(false);

        function refreshMaterialPermissions() {
            canWriteMaterials.value = !!window.crmIsSuper
                || !!(window.crmHasPermission && window.crmHasPermission('materials.write'));
        }

        async function loadFormOptions() {
            const data = await window.crmApi.get('/api/materials/form-options');
            formOptions.categories = data.categories || [];
            formOptions.confidentiality_levels = data.confidentiality_levels || [];
            formOptions.statuses = data.statuses || [];
            formOptions.depts = data.depts || [];
        }

        async function loadMaterials() {
            loading.value = true;
            try {
                const data = await window.crmApi.get('/api/materials' + buildQuery(filters));
                items.value = data.items || [];
            } finally {
                loading.value = false;
            }
        }

        function resetFilters() {
            filters.q = '';
            filters.category = '';
            filters.confidentiality = '';
            filters.status = 'active';
            filters.owner_dept_id = '';
            filters.expires_before = '';
            loadMaterials();
        }

        function openCreate() {
            formMode.value = 'create';
            editId.value = null;
            Object.assign(form, emptyForm());
            selectedFile.value = null;
            selectedFileName.value = '';
            editFileName.value = '';
            editFileSize.value = 0;
            if (fileInput.value) fileInput.value.value = '';
            showForm.value = true;
        }

        function openEdit(row) {
            formMode.value = 'edit';
            editId.value = row.id;
            form.title = row.title || '';
            form.category = row.category || 'other';
            form.confidentiality = row.confidentiality || 'internal';
            form.description = row.description || '';
            form.owner_dept_id = row.owner_dept_id != null ? String(row.owner_dept_id) : '';
            form.expires_at = row.expires_at || '';
            editFileName.value = row.file_name || '';
            editFileSize.value = row.file_size || 0;
            selectedFile.value = null;
            selectedFileName.value = '';
            showDetail.value = false;
            showForm.value = true;
        }

        function closeForm() {
            showForm.value = false;
        }

        async function openDetail(row) {
            try {
                detailRow.value = await window.crmApi.get('/api/materials/' + row.id);
                showDetail.value = true;
            } catch (e) {
                console.error(e);
            }
        }

        function closeDetail() {
            showDetail.value = false;
            detailRow.value = null;
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
                if (formMode.value === 'create') {
                    if (!selectedFile.value) {
                        alert('请选择文件');
                        return;
                    }
                    const fd = new FormData();
                    fd.append('title', form.title);
                    fd.append('category', form.category);
                    fd.append('confidentiality', form.confidentiality);
                    fd.append('description', form.description || '');
                    if (form.owner_dept_id) fd.append('owner_dept_id', form.owner_dept_id);
                    if (form.expires_at) fd.append('expires_at', form.expires_at);
                    fd.append('file', selectedFile.value);
                    const headers = window.crmAuthHeader ? window.crmAuthHeader() : {};
                    const r = await fetch('/api/materials', {
                        method: 'POST',
                        headers,
                        credentials: 'same-origin',
                        body: fd,
                    });
                    if (!r.ok) {
                        const err = await r.json().catch(() => ({}));
                        throw new Error(err.detail || '上传失败');
                    }
                } else {
                    const body = { title: form.title, category: form.category, confidentiality: form.confidentiality, description: form.description };
                    if (form.owner_dept_id) {
                        body.owner_dept_id = parseInt(form.owner_dept_id, 10);
                    } else {
                        body.owner_dept_id = null;
                    }
                    body.expires_at = form.expires_at || '';
                    await window.crmApi.patch('/api/materials/' + editId.value, body);
                    if (selectedFile.value) {
                        const fd = new FormData();
                        fd.append('file', selectedFile.value);
                        await window.crmApi.postForm(
                            '/api/materials/' + editId.value + '/replace-file',
                            fd
                        );
                    }
                }
                showForm.value = false;
                await loadMaterials();
            } catch (e) {
                alert(e.message || '保存失败');
            } finally {
                submitting.value = false;
            }
        }

        function downloadMaterial(id) {
            window.location.href = '/api/materials/' + id + '/download';
        }

        async function archiveMaterial(row) {
            if (!confirm('确定删除「' + row.title + '」？删除后默认列表不再显示。')) return;
            try {
                await window.crmApi.post('/api/materials/' + row.id + '/archive', {});
                closeDetail();
                await loadMaterials();
            } catch (e) {
                alert(e.message || '删除失败');
            }
        }

        onMounted(async () => {
            refreshMaterialPermissions();
            window.addEventListener('crm-shell-ready', refreshMaterialPermissions);
            await loadFormOptions();
            refreshMaterialPermissions();
            await loadMaterials();
        });

        onUnmounted(() => {
            window.removeEventListener('crm-shell-ready', refreshMaterialPermissions);
        });

        return {
            items,
            loading,
            submitting,
            filters,
            formOptions,
            showForm,
            showDetail,
            formMode,
            form,
            detailRow,
            fileInput,
            selectedFileName,
            editFileName,
            editFileSize,
            dragging,
            triggerFilePick,
            onDrop,
            clearSelectedFile,
            canWriteMaterials,
            loadMaterials,
            resetFilters,
            openCreate,
            openEdit,
            closeForm,
            openDetail,
            closeDetail,
            onFileChange,
            submitForm,
            downloadMaterial,
            archiveMaterial,
            formatFileSize,
            confidentialityBadge,
            statusBadge,
        };
    },
}).mount('#materials-app');
