/**
 * Delivery detail employee files module.
 */
(function () {
    'use strict';

    function createEmployeeFilesState(deps) {
        const {
            ref,
            reactive,
            computed,
            clientId,
            moduleKey,
            authHeader,
            downloadBlob,
        } = deps;

        const hdr = () => authHeader();
        const apiBase = `/api/clients/${clientId}/delivery/employee-files`;

        const employeeFileFilter = reactive({ keyword: '' });
        const employeeFileStatusFilter = ref('');
        const employeeFiles = ref([]);
        const employeeFileInput = ref(null);
        const employeeFileUploading = ref(false);
        const employeeFileUploadError = ref('');
        const employeeFileSelectedFiles = ref([]);

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

        const resetEmployeeFileFilter = () => {
            employeeFileFilter.keyword = '';
            employeeFileStatusFilter.value = '';
        };

        const clearEmployeeFileSelectedFiles = () => {
            employeeFileSelectedFiles.value = [];
            employeeFileUploadError.value = '';
            if (employeeFileInput.value) employeeFileInput.value = '';
        };

        const employeeFileSelectedFileSummary = computed(() => {
            const files = Array.isArray(employeeFileSelectedFiles.value) ? employeeFileSelectedFiles.value : [];
            if (!files.length) return '';
            if (files.length === 1) return files[0].name || '已选择 1 个文件';
            return `已选择 ${files.length} 个文件：${files.map((f) => f.name || '未命名').join('、')}`;
        });

        const loadEmployeeFiles = async () => {
            if (moduleKey !== 'employee_files') return;
            employeeFileUploadError.value = '';
            const r = await fetch(apiBase, { headers: hdr() });
            employeeFiles.value = r.ok ? await r.json() : [];
        };

        const onEmployeeFilesSelected = async (ev) => {
            const input = ev.target;
            const list = input && input.files ? Array.from(input.files) : [];
            if (input) input.value = '';
            employeeFileSelectedFiles.value = list;
            employeeFileUploadError.value = '';
        };

        const uploadSelectedEmployeeFiles = async () => {
            const list = Array.isArray(employeeFileSelectedFiles.value) ? employeeFileSelectedFiles.value : [];
            if (!list.length) {
                employeeFileUploadError.value = '请选择文件';
                return;
            }
            employeeFileUploadError.value = '';
            employeeFileUploading.value = true;
            try {
                const fd = new FormData();
                list.forEach((file) => fd.append('files', file));
                fd.append('status', 'draft');
                const r = await fetch(apiBase, {
                    method: 'POST',
                    headers: hdr(),
                    body: fd,
                });
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
                await loadEmployeeFiles();
                employeeFileSelectedFiles.value = [];
            } finally {
                employeeFileUploading.value = false;
            }
        };

        const downloadEmployeeFile = async (row) => {
            const url = row && row.preview_url;
            if (!url) return;
            try {
                const r = await fetch(url, { headers: hdr() });
                if (!r.ok) {
                    alert('下载失败');
                    return;
                }
                const blob = await r.blob();
                downloadBlob(blob, row.original_filename || 'employee_file');
            } catch (_) {
                alert('下载失败');
            }
        };

        const removeEmployeeFile = async (row) => {
            const r = await fetch(`${apiBase}/${row.id}`, {
                method: 'DELETE',
                headers: hdr(),
            });
            if (!r.ok) {
                alert('删除失败');
                return;
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
            filteredEmployeeFiles,
            resetEmployeeFileFilter,
            clearEmployeeFileSelectedFiles,
            employeeFiles,
            employeeFileInput,
            employeeFileUploading,
            employeeFileUploadError,
            employeeFileSelectedFiles,
            employeeFileSelectedFileSummary,
            employeeFileStatusLabel,
            employeeFileStatusClass,
            employeeFileMediaLabel,
            loadEmployeeFiles,
            onEmployeeFilesSelected,
            uploadSelectedEmployeeFiles,
            downloadEmployeeFile,
            removeEmployeeFile,
            mountEmployeeFiles,
        };
    }

    window.CrmDeliveryDetailEmployeeFiles = {
        createEmployeeFilesState,
    };
})();
