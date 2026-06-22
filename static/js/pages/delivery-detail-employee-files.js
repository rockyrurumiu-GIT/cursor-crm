/**
 * Delivery detail employee files module.
 */
(function () {
    'use strict';

    const EMPLOYEE_FILE_PAGE_SIZE = 10;

    function createEmployeeFilesState(deps) {
        const {
            ref,
            reactive,
            computed,
            watch,
            clientId,
            moduleKey,
            authHeader,
            downloadBlob,
            displayDateSlash,
        } = deps;

        const hdr = () => (typeof authHeader === 'function' ? authHeader() : window.crmAuthHeader());
        const apiBase = `/api/clients/${clientId}/delivery/employee-files`;

        const employeeFileFilter = reactive({ keyword: '' });
        const employeeFileStatusFilter = ref('');
        const employeeFileFilterPanelExpanded = ref(false);
        const employeeFiles = ref([]);
        const employeeFileUploading = ref(false);
        const employeeFileUploadError = ref('');
        const employeeFileUploadModalOpen = ref(false);
        const employeeFileUploadForm = reactive({ status: 'draft' });
        const employeeFileUploadFiles = ref([]);
        const employeeFileUploadFileInput = ref(null);
        const employeeFileUploadDragging = ref(false);
        const employeeFileDetailRow = ref(null);
        const employeeFilePreviewRow = ref(null);
        const employeeFilePreviewUrl = ref('');
        const employeeFilePreviewMode = ref('');
        const employeeFilePreviewLoading = ref(false);
        let employeeFilePreviewBlobUrl = '';

        const employeeFileCurrentPage = ref(1);

        const employeeFileStatusLabel = (s) => ({ draft: '草稿', published: '已发布', deprecated: '已作废' }[s] || s || '—');
        const employeeFileStatusClass = (s) => {
            if (s === 'published') return 'bg-green-100 text-green-800';
            if (s === 'deprecated') return 'bg-gray-200 text-gray-600';
            return 'bg-amber-100 text-amber-800';
        };
        const employeeFileMediaLabel = (row) => {
            const mk = String((row && row.media_kind) || '').toLowerCase();
            if (mk === 'pdf') return 'PDF';
            if (mk === 'document') return '文档';
            if (mk === 'video') return '视频';
            if (mk === 'audio') return '音频';
            return mk || '文件';
        };
        const employeeFileCanPreview = (row) => {
            const mk = String((row && row.media_kind) || '').toLowerCase();
            return mk === 'pdf' || mk === 'video' || mk === 'audio';
        };
        const employeeFileDisplayDate = (raw) => {
            if (typeof displayDateSlash === 'function') return displayDateSlash(raw) || '—';
            const s = String(raw || '').trim();
            if (!s) return '—';
            return s.slice(0, 10).replace(/-/g, '/');
        };

        const filteredEmployeeFiles = computed(() => {
            let rows = Array.isArray(employeeFiles.value) ? [...employeeFiles.value] : [];
            const st = employeeFileStatusFilter.value;
            if (st) rows = rows.filter((row) => String(row.status || '') === st);
            const keyword = String(employeeFileFilter.keyword || '').trim().toLowerCase();
            if (keyword) {
                rows = rows.filter((row) => {
                    const hay = [
                        row.original_filename,
                        employeeFileStatusLabel(row.status),
                        employeeFileMediaLabel(row),
                    ].join(' ').toLowerCase();
                    return hay.includes(keyword);
                });
            }
            return rows;
        });

        const employeeFileTotalPages = computed(() => Math.max(1, Math.ceil(filteredEmployeeFiles.value.length / EMPLOYEE_FILE_PAGE_SIZE)));
        const pagedEmployeeFiles = computed(() => {
            const start = (employeeFileCurrentPage.value - 1) * EMPLOYEE_FILE_PAGE_SIZE;
            return filteredEmployeeFiles.value.slice(start, start + EMPLOYEE_FILE_PAGE_SIZE);
        });
        const employeeFilePageNumbers = computed(() => {
            const total = employeeFileTotalPages.value;
            const max = 7;
            let start = Math.max(1, employeeFileCurrentPage.value - 3);
            let end = Math.min(total, start + max - 1);
            start = Math.max(1, end - max + 1);
            const arr = [];
            for (let i = start; i <= end; i++) arr.push(i);
            return arr;
        });
        const employeeFileGoPage = (p) => {
            employeeFileCurrentPage.value = Math.min(Math.max(1, p), employeeFileTotalPages.value);
        };

        watch(employeeFileFilter, () => { employeeFileCurrentPage.value = 1; }, { deep: true });
        watch(employeeFileStatusFilter, () => { employeeFileCurrentPage.value = 1; });
        watch(filteredEmployeeFiles, () => {
            if (employeeFileCurrentPage.value > employeeFileTotalPages.value) {
                employeeFileCurrentPage.value = employeeFileTotalPages.value;
            }
        });

        const toggleEmployeeFileFilterPanel = () => {
            employeeFileFilterPanelExpanded.value = !employeeFileFilterPanelExpanded.value;
        };
        const resetEmployeeFileFilter = () => {
            employeeFileFilter.keyword = '';
            employeeFileStatusFilter.value = '';
        };

        const employeeFileUploadSelectedSummary = computed(() => {
            const files = Array.isArray(employeeFileUploadFiles.value) ? employeeFileUploadFiles.value : [];
            if (!files.length) return '';
            if (files.length === 1) return files[0].name || '已选择 1 个文件';
            return `已选择 ${files.length} 个文件`;
        });

        const resetEmployeeFileUploadForm = () => {
            employeeFileUploadForm.status = 'draft';
            employeeFileUploadFiles.value = [];
            employeeFileUploadDragging.value = false;
            employeeFileUploadError.value = '';
            if (employeeFileUploadFileInput.value) employeeFileUploadFileInput.value.value = '';
        };
        const openEmployeeFileUploadModal = () => {
            resetEmployeeFileUploadForm();
            employeeFileUploadModalOpen.value = true;
        };
        const closeEmployeeFileUploadModal = () => {
            employeeFileUploadModalOpen.value = false;
            resetEmployeeFileUploadForm();
        };
        const triggerEmployeeFileUploadPick = () => {
            if (employeeFileUploadFileInput.value) employeeFileUploadFileInput.value.click();
        };
        const applyEmployeeFileUploadFiles = (fileList) => {
            const list = Array.from(fileList || []).filter(Boolean);
            if (!list.length) return;
            employeeFileUploadFiles.value = list;
            employeeFileUploadError.value = '';
        };
        const onEmployeeFileUploadFileChange = (ev) => {
            const input = ev.target;
            applyEmployeeFileUploadFiles(input && input.files ? input.files : []);
            if (input) input.value = '';
        };
        const onEmployeeFileUploadDrop = (ev) => {
            employeeFileUploadDragging.value = false;
            applyEmployeeFileUploadFiles(ev.dataTransfer && ev.dataTransfer.files ? ev.dataTransfer.files : []);
        };
        const clearEmployeeFileUploadFiles = () => {
            employeeFileUploadFiles.value = [];
            if (employeeFileUploadFileInput.value) employeeFileUploadFileInput.value.value = '';
        };

        const loadEmployeeFiles = async () => {
            if (moduleKey !== 'employee_files') return;
            employeeFileUploadError.value = '';
            const r = await fetch(apiBase, { headers: hdr() });
            employeeFiles.value = r.ok ? await r.json() : [];
        };

        const submitEmployeeFileUpload = async () => {
            const list = Array.isArray(employeeFileUploadFiles.value) ? employeeFileUploadFiles.value : [];
            if (!list.length) {
                employeeFileUploadError.value = '请选择文件';
                return;
            }
            employeeFileUploadError.value = '';
            employeeFileUploading.value = true;
            try {
                const fd = new FormData();
                list.forEach((file) => fd.append('files', file));
                fd.append('status', employeeFileUploadForm.status || 'draft');
                const r = await fetch(apiBase, { method: 'POST', headers: hdr(), body: fd });
                if (!r.ok) {
                    let msg = '上传失败';
                    try {
                        const j = await r.json();
                        const d = j.detail;
                        if (typeof d === 'string') msg = d;
                        else if (Array.isArray(d) && d.length) msg = d.map((x) => x.msg || JSON.stringify(x)).join('；');
                        else if (d) msg = JSON.stringify(d);
                    } catch (err) { /* ignore */ }
                    employeeFileUploadError.value = msg;
                    return;
                }
                closeEmployeeFileUploadModal();
                await loadEmployeeFiles();
            } finally {
                employeeFileUploading.value = false;
            }
        };

        const revokeEmployeeFilePreviewBlob = () => {
            if (employeeFilePreviewBlobUrl) {
                URL.revokeObjectURL(employeeFilePreviewBlobUrl);
                employeeFilePreviewBlobUrl = '';
            }
        };
        const closeEmployeeFilePreview = () => {
            revokeEmployeeFilePreviewBlob();
            employeeFilePreviewRow.value = null;
            employeeFilePreviewUrl.value = '';
            employeeFilePreviewMode.value = '';
            employeeFilePreviewLoading.value = false;
        };
        const openEmployeeFilePreview = async (row) => {
            if (!row || !employeeFileCanPreview(row)) return;
            const mk = String(row.media_kind || '').toLowerCase();
            employeeFilePreviewRow.value = row;
            employeeFilePreviewMode.value = 'loading';
            employeeFilePreviewLoading.value = true;
            revokeEmployeeFilePreviewBlob();
            employeeFilePreviewUrl.value = '';
            const url = row.preview_url;
            if (!url) {
                employeeFilePreviewMode.value = 'error';
                employeeFilePreviewLoading.value = false;
                return;
            }
            try {
                const r = await fetch(url, { headers: hdr() });
                if (!r.ok) {
                    employeeFilePreviewMode.value = 'error';
                    return;
                }
                const blob = await r.blob();
                revokeEmployeeFilePreviewBlob();
                employeeFilePreviewBlobUrl = URL.createObjectURL(blob);
                employeeFilePreviewUrl.value = employeeFilePreviewBlobUrl;
                employeeFilePreviewMode.value = mk;
            } catch (_) {
                employeeFilePreviewMode.value = 'error';
            } finally {
                employeeFilePreviewLoading.value = false;
            }
        };
        const openEmployeeFilePreviewFromDetail = () => {
            if (employeeFileDetailRow.value) openEmployeeFilePreview(employeeFileDetailRow.value);
        };

        const openEmployeeFileDetailDrawer = (row) => {
            employeeFileDetailRow.value = row;
        };
        const closeEmployeeFileDetailDrawer = () => {
            employeeFileDetailRow.value = null;
        };

        const downloadEmployeeFile = async (row) => {
            const url = row && row.preview_url;
            if (!url) return;
            try {
                const r = await fetch(url, { headers: hdr() });
                if (!r.ok) {
                    if (window.crmToast) window.crmToast.error('下载失败');
                    else alert('下载失败');
                    return;
                }
                const blob = await r.blob();
                const dl = typeof downloadBlob === 'function' ? downloadBlob : window.crmDownloadBlob;
                dl(blob, blob.type || 'application/octet-stream', row.original_filename || 'employee_file');
            } catch (_) {
                if (window.crmToast) window.crmToast.error('下载失败');
                else alert('下载失败');
            }
        };

        const removeEmployeeFile = async (row) => {
            if (typeof window.crmConfirmDeleteDialog === 'function') {
                const ok = await window.crmConfirmDeleteDialog({
                    title: '确认删除文件',
                    target: row.original_filename || '该文件',
                    hint: '删除后将从当前员工文件列表移除。',
                });
                if (!ok) return;
            } else if (!window.confirm(`确认删除文件「${row.original_filename || ''}」？`)) {
                return;
            }
            const r = await fetch(`${apiBase}/${row.id}`, { method: 'DELETE', headers: hdr() });
            if (!r.ok) {
                if (window.crmToast) window.crmToast.error('删除失败');
                else alert('删除失败');
                return;
            }
            if (employeeFileDetailRow.value && employeeFileDetailRow.value.id === row.id) {
                closeEmployeeFileDetailDrawer();
            }
            if (employeeFilePreviewRow.value && employeeFilePreviewRow.value.id === row.id) {
                closeEmployeeFilePreview();
            }
            await loadEmployeeFiles();
        };

        const mountEmployeeFiles = async () => {
            if (moduleKey !== 'employee_files') return;
            await loadEmployeeFiles();
        };

        return {
            employeeFileFilter,
            employeeFileStatusFilter,
            employeeFileFilterPanelExpanded,
            toggleEmployeeFileFilterPanel,
            filteredEmployeeFiles,
            pagedEmployeeFiles,
            employeeFileCurrentPage,
            employeeFileTotalPages,
            employeeFilePageNumbers,
            employeeFileGoPage,
            resetEmployeeFileFilter,
            employeeFiles,
            employeeFileUploadModalOpen,
            employeeFileUploadForm,
            employeeFileUploadFiles,
            employeeFileUploadFileInput,
            employeeFileUploadDragging,
            employeeFileUploadSelectedSummary,
            employeeFileUploading,
            employeeFileUploadError,
            employeeFileDetailRow,
            employeeFilePreviewRow,
            employeeFilePreviewUrl,
            employeeFilePreviewMode,
            employeeFilePreviewLoading,
            employeeFileStatusLabel,
            employeeFileStatusClass,
            employeeFileMediaLabel,
            employeeFileCanPreview,
            employeeFileDisplayDate,
            loadEmployeeFiles,
            openEmployeeFileUploadModal,
            closeEmployeeFileUploadModal,
            triggerEmployeeFileUploadPick,
            onEmployeeFileUploadFileChange,
            onEmployeeFileUploadDrop,
            clearEmployeeFileUploadFiles,
            submitEmployeeFileUpload,
            openEmployeeFileDetailDrawer,
            closeEmployeeFileDetailDrawer,
            openEmployeeFilePreview,
            openEmployeeFilePreviewFromDetail,
            closeEmployeeFilePreview,
            downloadEmployeeFile,
            removeEmployeeFile,
            mountEmployeeFiles,
        };
    }

    window.CrmDeliveryDetailEmployeeFiles = {
        createEmployeeFilesState,
    };
})();
