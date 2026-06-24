/**
 * Contract management page — attachment filters and upload.
 */
const { createApp, ref, reactive, computed, watch, onMounted, onUnmounted } = Vue;

function emptyForm() {
    return {
        id: null,
        title: '',
        client_id: '',
        contract_type: '',
        contract_no: '',
        expires_mode: 'date',
        expires_at: '',
        remarks: '',
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
        active: 'bg-green-100 text-green-800',
        expiring: 'bg-amber-100 text-amber-800',
        expired: 'bg-red-100 text-red-800',
    };
    return m[code] || 'bg-gray-100 text-gray-600';
}

const PREVIEWABLE_EXTS = [
    '.pdf', '.jpg', '.jpeg', '.png',
    '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
];

const OFFICE_PREVIEW_EXTS = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'];

function fileExt(name) {
    const n = String(name || '').trim().toLowerCase();
    const i = n.lastIndexOf('.');
    return i >= 0 ? n.slice(i) : '';
}

function isPreviewableFile(name) {
    return PREVIEWABLE_EXTS.includes(fileExt(name));
}

function previewModeForFile(name) {
    const ext = fileExt(name);
    if (ext === '.pdf' || OFFICE_PREVIEW_EXTS.includes(ext)) return 'pdf';
    if (ext === '.jpg' || ext === '.jpeg' || ext === '.png') return 'image';
    return 'unsupported';
}

function previewBlobMime(mode, contentType) {
    const ct = String(contentType || '').toLowerCase();
    if (mode === 'pdf') return ct.includes('pdf') ? contentType : 'application/pdf';
    if (mode === 'image') {
        if (ct.includes('png')) return 'image/png';
        if (ct.includes('jpeg') || ct.includes('jpg')) return 'image/jpeg';
        return contentType || 'image/jpeg';
    }
    return contentType || 'application/octet-stream';
}

async function validatePreviewBlob(blob, mode) {
    if (!blob || !blob.size) {
        throw new Error('预览文件为空');
    }
    const buf = await blob.arrayBuffer();
    const head = new Uint8Array(buf.slice(0, 16));
    const textHead = new TextDecoder().decode(buf.slice(0, 256)).trim().toLowerCase();
    const looksHtml = textHead.startsWith('<!doctype') || textHead.startsWith('<html')
        || textHead === 'not found' || textHead.includes('not found');
    const looksJson = textHead.startsWith('{') && textHead.includes('"detail"');
    if (looksHtml || looksJson) {
        let msg = '预览失败，请稍后重试';
        if (looksJson) {
            try {
                msg = JSON.parse(new TextDecoder().decode(buf)).detail || msg;
            } catch (_) { /* ignore */ }
        } else if (textHead === 'not found' || textHead.includes('not found')) {
            msg = '预览接口不可用，请刷新页面或重启服务后重试';
        }
        throw new Error(msg);
    }
    if (mode === 'pdf') {
        const magic = String.fromCharCode(head[0], head[1], head[2], head[3]);
        if (magic !== '%PDF') {
            throw new Error('无法生成 PDF 预览，请下载附件查看');
        }
    }
    return buf;
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
            contract_types: [],
        });
        const showForm = ref(false);
        const showDetail = ref(false);
        const detailRow = ref(null);
        const form = reactive(emptyForm());
        const clientPickerQuery = ref('');
        const clientPickerOpen = ref(false);
        const selectedFile = ref(null);
        const selectedFileName = ref('');
        const existingFileName = ref('');
        const fileInput = ref(null);
        const dragging = ref(false);
        const showPreview = ref(false);
        const previewTitle = ref('');
        const previewContent = ref('');
        const previewMode = ref('');
        const previewUrl = ref('');
        const previewErrorMessage = ref('');
        const previewLoading = ref(false);
        let previewBlobUrl = '';
        const canWriteContracts = ref(false);
        const canDeleteContracts = ref(false);
        const canDownloadContracts = ref(false);

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

        const filteredClients = computed(() => {
            const q = (clientPickerQuery.value || '').trim().toLowerCase();
            const list = formOptions.clients || [];
            if (!q) return list.slice(0, 50);
            return list.filter((c) => String(c.name || '').toLowerCase().includes(q)).slice(0, 50);
        });

        const selectedClient = computed(() => {
            const id = String(form.client_id || '');
            if (!id) return null;
            return (formOptions.clients || []).find((c) => String(c.id) === id) || null;
        });

        const selectedClientLabel = computed(() => (selectedClient.value ? selectedClient.value.name : ''));

        const formSalesOwner = computed(() => (selectedClient.value ? (selectedClient.value.sales_owner_name || '—') : '—'));

        const isVendorContract = computed(() => form.contract_type === 'vendor');

        const isEditMode = computed(() => !!form.id);

        const isLongTermExpiry = computed(() => form.expires_mode === 'long_term');

        const formatExpiresAt = (raw) => {
            const s = String(raw || '').trim();
            return s || '长期';
        };

        const goPage = (p) => {
            currentPage.value = Math.min(Math.max(1, p), totalPages.value);
        };

        watch(() => filteredItems.value.length, () => {
            if (currentPage.value > totalPages.value) currentPage.value = totalPages.value;
        });

        watch(() => form.contract_type, (ct) => {
            if (ct !== 'vendor' && !form.id) form.contract_no = '';
        });

        watch(() => form.expires_mode, (mode) => {
            if (mode === 'long_term') form.expires_at = '';
        });

        function refreshContractPermissions() {
            const isSuper = !!window.crmIsSuper;
            const has = (code) => isSuper || !!(window.crmHasPermission && window.crmHasPermission(code));
            canWriteContracts.value = has('crm.contracts.write');
            canDeleteContracts.value = has('crm.contracts.delete');
            canDownloadContracts.value = has('crm.contracts.download');
        }

        async function loadFormOptions() {
            const data = await window.crmApi.get('/api/contracts/form-options');
            formOptions.statuses = data.statuses || [];
            formOptions.clients = data.clients || [];
            formOptions.contract_types = data.contract_types || [];
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
            clientPickerQuery.value = '';
            clientPickerOpen.value = false;
            selectedFile.value = null;
            selectedFileName.value = '';
            existingFileName.value = '';
            if (fileInput.value) fileInput.value.value = '';
            showForm.value = true;
        }

        function openEdit(row) {
            if (row.handoff_id) {
                alert('交接生成的合同不可在此修改，请在交接单中调整');
                return;
            }
            if (!canWriteContracts.value) {
                alert('无权限修改合同');
                return;
            }
            form.id = row.id;
            form.title = row.title || row.material_name || '';
            form.client_id = String(row.client_id || '');
            clientPickerQuery.value = row.client_name || '';
            form.contract_type = row.contract_type || '';
            form.contract_no = row.contract_no || '';
            const exp = String(row.expires_at || row.end_date || '').trim();
            form.expires_mode = exp ? 'date' : 'long_term';
            form.expires_at = exp;
            form.remarks = row.remarks || '';
            existingFileName.value = row.file_name || '';
            selectedFile.value = null;
            selectedFileName.value = '';
            clientPickerOpen.value = false;
            if (fileInput.value) fileInput.value.value = '';
            showForm.value = true;
        }

        function closeForm() {
            showForm.value = false;
            clientPickerOpen.value = false;
            Object.assign(form, emptyForm());
            existingFileName.value = '';
        }

        function selectClient(c) {
            form.client_id = String(c.id);
            clientPickerQuery.value = c.name || '';
            clientPickerOpen.value = false;
        }

        function onClientPickerBlur() {
            window.setTimeout(() => { clientPickerOpen.value = false; }, 150);
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
                if (!isEditMode.value && !selectedFile.value) {
                    alert('请选择文件');
                    return;
                }
                if (!form.client_id) {
                    alert('请选择客户');
                    return;
                }
                if (!form.contract_type) {
                    alert('请选择合同类型');
                    return;
                }
                if (form.expires_mode === 'date' && !form.expires_at) {
                    alert('请选择有效期或选择长期');
                    return;
                }
                if (isVendorContract.value && !String(form.contract_no || '').trim()) {
                    alert('请填写供应商合同编号');
                    return;
                }
                const fd = new FormData();
                fd.append('title', form.title);
                fd.append('client_id', form.client_id);
                fd.append('contract_type', form.contract_type);
                if (isVendorContract.value) {
                    fd.append('contract_no', form.contract_no || '');
                }
                fd.append('expires_at', form.expires_at || '');
                fd.append('remarks', form.remarks || '');
                const headers = window.crmAuthHeader ? window.crmAuthHeader() : {};
                if (isEditMode.value) {
                    const r = await fetch('/api/contracts/' + form.id, {
                        method: 'PATCH',
                        headers,
                        credentials: 'same-origin',
                        body: fd,
                    });
                    if (!r.ok) {
                        const err = await r.json().catch(() => ({}));
                        throw new Error(err.detail || '保存失败');
                    }
                    if (selectedFile.value) {
                        const fileFd = new FormData();
                        fileFd.append('file', selectedFile.value);
                        const fr = await fetch('/api/contracts/' + form.id + '/replace-file', {
                            method: 'POST',
                            headers,
                            credentials: 'same-origin',
                            body: fileFd,
                        });
                        if (!fr.ok) {
                            const err = await fr.json().catch(() => ({}));
                            throw new Error(err.detail || '附件替换失败');
                        }
                    }
                } else {
                    fd.append('file', selectedFile.value);
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
                }
                closeForm();
                await loadContracts();
            } catch (e) {
                alert(e.message || (isEditMode.value ? '保存失败' : '上传失败'));
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

        const openPreview = async (row) => {
            previewTitle.value = row.material_name || row.title || row.contract_no || '合同预览';
            if (row.has_attachment) {
                const mode = previewModeForFile(row.file_name);
                previewErrorMessage.value = '';
                revokePreviewBlob();
                previewUrl.value = '';
                previewContent.value = '';
                if (mode === 'unsupported') {
                    previewMode.value = 'unsupported';
                    previewLoading.value = false;
                    showPreview.value = true;
                    return;
                }
                previewMode.value = 'loading';
                previewLoading.value = true;
                showPreview.value = true;
                const url = '/api/contracts/' + row.id + '/preview';
                try {
                    const headers = window.crmAuthHeader ? window.crmAuthHeader() : {};
                    const r = await fetch(url, { credentials: 'same-origin', headers });
                    if (!r.ok) {
                        const err = await r.json().catch(() => ({}));
                        previewMode.value = 'error';
                        previewErrorMessage.value = err.detail || '预览失败，请稍后重试';
                        return;
                    }
                    const ct = r.headers.get('content-type') || '';
                    const rawBlob = await r.blob();
                    const buf = await validatePreviewBlob(rawBlob, mode);
                    revokePreviewBlob();
                    const typedBlob = new Blob([buf], { type: previewBlobMime(mode, ct) });
                    previewBlobUrl = URL.createObjectURL(typedBlob);
                    previewUrl.value = previewBlobUrl;
                    previewMode.value = mode;
                } catch (e) {
                    previewMode.value = 'error';
                    previewErrorMessage.value = (e && e.message) || '预览失败，请稍后重试';
                } finally {
                    previewLoading.value = false;
                }
                return;
            }
            previewMode.value = 'markdown';
            previewContent.value = row.sow_markdown || '';
            showPreview.value = true;
        };

        function revokePreviewBlob() {
            if (previewBlobUrl) {
                URL.revokeObjectURL(previewBlobUrl);
                previewBlobUrl = '';
            }
        }

        const closePreview = () => {
            showPreview.value = false;
            previewTitle.value = '';
            previewContent.value = '';
            previewMode.value = '';
            previewUrl.value = '';
            previewErrorMessage.value = '';
            revokePreviewBlob();
        };

        function downloadContract(row) {
            if (!canDownloadContracts.value) {
                alert('无权限下载合同');
                return;
            }
            if (!row || !row.id || !row.has_attachment) return;
            window.location.href = '/api/contracts/' + row.id + '/download';
        }

        const deleteContract = async (row) => {
            if (!canDeleteContracts.value) {
                alert('无权限删除合同');
                return;
            }
            const name = row.material_name || row.title || row.contract_no || '该合同';
            let ok = false;
            if (typeof window.crmConfirmDeleteDialog === 'function') {
                ok = await window.crmConfirmDeleteDialog({
                    title: '确认删除',
                    targetText: '将删除：' + name,
                    hint: '删除后不可恢复，将从当前列表移除。',
                });
            } else {
                ok = window.confirm('确定删除「' + name + '」？');
            }
            if (!ok) return;
            try {
                const headers = window.crmAuthHeader ? window.crmAuthHeader() : {};
                const r = await fetch('/api/contracts/' + row.id, {
                    method: 'DELETE',
                    headers,
                    credentials: 'same-origin',
                });
                if (!r.ok) {
                    const err = await r.json().catch(() => ({}));
                    throw new Error(err.detail || '删除失败');
                }
                if (detailRow.value && detailRow.value.id === row.id) closeDetail();
                if (showForm.value && form.id === row.id) closeForm();
                await loadContracts();
            } catch (e) {
                alert(e.message || '删除失败');
            }
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
            clientPickerQuery,
            clientPickerOpen,
            filteredClients,
            selectedClientLabel,
            formSalesOwner,
            isVendorContract,
            isEditMode,
            isLongTermExpiry,
            formatExpiresAt,
            fileInput,
            selectedFileName,
            existingFileName,
            dragging,
            showPreview,
            previewTitle,
            previewContent,
            previewMode,
            previewUrl,
            previewErrorMessage,
            previewLoading,
            canWriteContracts,
            canDeleteContracts,
            canDownloadContracts,
            loadContracts,
            resetFilters,
            openCreate,
            openEdit,
            closeForm,
            selectClient,
            onClientPickerBlur,
            onFileChange,
            triggerFilePick,
            onDrop,
            clearSelectedFile,
            submitForm,
            openDetail,
            closeDetail,
            openPreview,
            closePreview,
            downloadContract,
            deleteContract,
            seed,
            displayAmount,
            formatDateTime,
            statusBadge,
        };
    },
}).mount('#contracts-app');
