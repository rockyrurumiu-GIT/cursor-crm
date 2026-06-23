/**
 * Delivery detail employee files module.
 */
(function () {
    'use strict';

    const EMPLOYEE_FILE_PAGE_SIZE = 10;
    const LABOR_CONTRACT_TYPE = '劳动合同';

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
        const employeeFileUploadForm = reactive({
            status: 'draft',
            document_type: '其他',
            employee_full_name: '',
            employee_contact_info: '',
            contract_sign_date: '',
            contract_valid_until: '',
            remarks: '',
        });
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

        const isLaborContractUpload = computed(() =>
            String(employeeFileUploadForm.document_type || '').trim() === LABOR_CONTRACT_TYPE
        );

        const employeeFileEntryFiles = (row) => {
            if (Array.isArray(row && row.files) && row.files.length) return row.files;
            return row && row.id ? [row] : [];
        };
        const employeeFileEntryIsGroup = (row) => employeeFileEntryFiles(row).length > 1;
        const employeeFileEntryLabel = (row) => {
            const files = employeeFileEntryFiles(row);
            if (files.length <= 1) return files[0]?.original_filename || '该文件';
            return `${files[0]?.original_filename || '文件'} 等 ${files.length} 个文件`;
        };
        const employeeFileFirstPreviewable = (row) =>
            employeeFileEntryFiles(row).find((f) => {
                const mk = String((f && f.media_kind) || '').toLowerCase();
                return mk === 'pdf' || mk === 'video' || mk === 'audio';
            }) || null;
        const employeeFileRemarksLabel = (row) => {
            const note = String((row && row.remarks) || '').trim();
            return note || '—';
        };
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
        const employeeFileDocumentTypeLabel = (row) => {
            const dt = String((row && row.document_type) || '').trim();
            return dt || '—';
        };
        const employeeFileIsLaborContract = (row) =>
            String((row && row.document_type) || '').trim() === LABOR_CONTRACT_TYPE;
        const employeeFileLaborContractNoLabel = (row) => {
            if (!employeeFileIsLaborContract(row)) return 'NA';
            const no = String((row && row.labor_contract_no) || '').trim();
            return no || '—';
        };
        const employeeFileValidUntilLabel = (row) => {
            if (!employeeFileIsLaborContract(row)) return 'NA';
            return employeeFileDisplayDate(row && row.contract_valid_until);
        };
        const employeeFileCanPreview = (row) => !!employeeFileFirstPreviewable(row);
        const employeeFileCanPublish = (row) =>
            String((row && row.status) || '').trim() === 'draft';
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
                        row.document_type,
                        row.employee_full_name,
                        row.remarks,
                        row.labor_contract_no,
                        row.contract_valid_until,
                        employeeFileStatusLabel(row.status),
                        employeeFileMediaLabel(row),
                        ...employeeFileEntryFiles(row).map((f) => f.original_filename),
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
        watch(isLaborContractUpload, (isLabor) => {
            if (!isLabor) {
                employeeFileUploadError.value = '';
                return;
            }
            const list = Array.isArray(employeeFileUploadFiles.value) ? employeeFileUploadFiles.value : [];
            if (list.length > 1) {
                employeeFileUploadFiles.value = [list[0]];
                employeeFileUploadError.value = '劳动合同每次只能上传 1 个文件';
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
            employeeFileUploadForm.document_type = '其他';
            employeeFileUploadForm.employee_full_name = '';
            employeeFileUploadForm.employee_contact_info = '';
            employeeFileUploadForm.contract_sign_date = '';
            employeeFileUploadForm.contract_valid_until = '';
            employeeFileUploadForm.remarks = '';
            employeeFileUploadFiles.value = [];
            employeeFileUploadDragging.value = false;
            employeeFileUploadError.value = '';
            if (employeeFileUploadFileInput.value) employeeFileUploadFileInput.value.value = '';
        };
        const openEmployeeFileUploadModal = () => {
            employeeFileUploading.value = false;
            resetEmployeeFileUploadForm();
            employeeFileUploadModalOpen.value = true;
        };
        const closeEmployeeFileUploadModal = () => {
            employeeFileUploadModalOpen.value = false;
            employeeFileUploading.value = false;
            resetEmployeeFileUploadForm();
        };
        const triggerEmployeeFileUploadPick = () => {
            if (employeeFileUploadFileInput.value) employeeFileUploadFileInput.value.click();
        };
        const applyEmployeeFileUploadFiles = (fileList) => {
            const list = Array.from(fileList || []).filter(Boolean);
            if (!list.length) return;
            if (isLaborContractUpload.value && list.length > 1) {
                employeeFileUploadError.value = '劳动合同每次只能上传 1 个文件';
                employeeFileUploadFiles.value = [list[0]];
                return;
            }
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

        const parseUploadError = async (r) => {
            let msg = '上传失败';
            try {
                const j = await r.json();
                const d = j.detail;
                if (typeof d === 'string') msg = d;
                else if (d && typeof d === 'object' && d.message) msg = d.message;
                else if (Array.isArray(d) && d.length) msg = d.map((x) => x.msg || JSON.stringify(x)).join('；');
                else if (d) msg = JSON.stringify(d);
            } catch (err) { /* ignore */ }
            return msg;
        };

        const buildUploadFormData = (confirmSameYearRenewal) => {
            const fd = new FormData();
            const list = Array.isArray(employeeFileUploadFiles.value) ? employeeFileUploadFiles.value : [];
            list.forEach((file) => fd.append('files', file));
            fd.append('status', employeeFileUploadForm.status || 'draft');
            fd.append('document_type', employeeFileUploadForm.document_type || '其他');
            if (isLaborContractUpload.value) {
                fd.append('employee_full_name', employeeFileUploadForm.employee_full_name || '');
                fd.append('employee_contact_info', employeeFileUploadForm.employee_contact_info || '');
                fd.append('contract_sign_date', employeeFileUploadForm.contract_sign_date || '');
                fd.append('contract_valid_until', employeeFileUploadForm.contract_valid_until || '');
                fd.append('confirm_same_year_renewal', String(confirmSameYearRenewal ? 1 : 0));
            } else {
                fd.append('employee_full_name', employeeFileUploadForm.employee_full_name || '');
                fd.append('remarks', employeeFileUploadForm.remarks || '');
            }
            return fd;
        };

        const postEmployeeFileUpload = async (confirmSameYearRenewal) => {
            const r = await fetch(apiBase, {
                method: 'POST',
                headers: hdr(),
                body: buildUploadFormData(confirmSameYearRenewal),
            });
            return r;
        };

        const submitEmployeeFileUpload = async () => {
            const list = Array.isArray(employeeFileUploadFiles.value) ? employeeFileUploadFiles.value : [];
            if (!list.length) {
                employeeFileUploadError.value = '请选择文件';
                return;
            }
            if (isLaborContractUpload.value) {
                if (list.length > 1) {
                    employeeFileUploadError.value = '劳动合同每次只能上传 1 个文件';
                    return;
                }
                if (!String(employeeFileUploadForm.employee_full_name || '').trim()) {
                    employeeFileUploadError.value = '请填写员工姓名';
                    return;
                }
                if (!String(employeeFileUploadForm.employee_contact_info || '').trim()) {
                    employeeFileUploadError.value = '请填写手机号';
                    return;
                }
            }
            employeeFileUploadError.value = '';
            employeeFileUploading.value = true;
            try {
                let r = await postEmployeeFileUpload(0);
                if (r.status === 409) {
                    let detail = null;
                    try {
                        const j = await r.json();
                        detail = j.detail;
                    } catch (err) { /* ignore */ }
                    if (detail && detail.code === 'same_year_labor_contract_exists') {
                        let confirmed = false;
                        if (typeof window.crmConfirmActionDialog === 'function') {
                            const result = await window.crmConfirmActionDialog({
                                title: '同年续约确认',
                                lines: [{ label: '提示', value: detail.message || '该员工已在本年上传过合同，是否为同年续约？' }],
                                confirmText: '是',
                                cancelText: '否',
                                zIndex: 200,
                            });
                            confirmed = !!(result && result.ok);
                        } else {
                            confirmed = window.confirm(detail.message || '该员工已在本年上传过合同，是否为同年续约？');
                        }
                        if (!confirmed) return;
                        r = await postEmployeeFileUpload(1);
                    } else {
                        if (typeof detail === 'string') employeeFileUploadError.value = detail;
                        else if (detail && detail.message) employeeFileUploadError.value = detail.message;
                        else employeeFileUploadError.value = '上传失败';
                        return;
                    }
                }
                if (!r.ok) {
                    employeeFileUploadError.value = await parseUploadError(r);
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
            const target = employeeFileFirstPreviewable(row) || row;
            if (!target || !employeeFileCanPreview(row)) return;
            const mk = String(target.media_kind || '').toLowerCase();
            employeeFilePreviewRow.value = target;
            employeeFilePreviewMode.value = 'loading';
            employeeFilePreviewLoading.value = true;
            revokeEmployeeFilePreviewBlob();
            employeeFilePreviewUrl.value = '';
            const url = target.preview_url;
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
        const openEmployeeFilePreviewFromFilename = (row, file) => {
            const target = file || employeeFileFirstPreviewable(row);
            if (!target) {
                const msg = '该格式不支持预览，请下载后查看';
                if (window.crmToast) window.crmToast.info(msg);
                else alert(msg);
                return;
            }
            openEmployeeFilePreview(target);
        };
        const openEmployeeFilePreviewFromDetail = () => {
            if (!employeeFileDetailRow.value) return;
            const target = employeeFileFirstPreviewable(employeeFileDetailRow.value);
            if (target) openEmployeeFilePreview(target);
        };

        const openEmployeeFileDetailDrawer = (row) => {
            employeeFileDetailRow.value = row;
        };
        const closeEmployeeFileDetailDrawer = () => {
            employeeFileDetailRow.value = null;
        };

        const downloadEmployeeFile = async (row) => {
            const files = employeeFileEntryFiles(row);
            if (!files.length) return;
            let failed = false;
            for (const file of files) {
                const url = file && file.preview_url;
                if (!url) continue;
                try {
                    const r = await fetch(url, { headers: hdr() });
                    if (!r.ok) {
                        failed = true;
                        continue;
                    }
                    const blob = await r.blob();
                    const dl = typeof downloadBlob === 'function' ? downloadBlob : window.crmDownloadBlob;
                    dl(blob, blob.type || 'application/octet-stream', file.original_filename || 'employee_file');
                } catch (_) {
                    failed = true;
                }
            }
            if (failed) {
                if (window.crmToast) window.crmToast.error('部分文件下载失败');
                else alert('部分文件下载失败');
            }
        };

        const removeEmployeeFile = async (row) => {
            const isLabor = String((row && row.document_type) || '').trim() === LABOR_CONTRACT_TYPE;
            const isLaborDraft = isLabor && String((row && row.status) || '').trim() === 'draft';
            const isLaborVoid = isLabor && !isLaborDraft;
            const label = employeeFileEntryLabel(row);
            if (typeof window.crmConfirmDeleteDialog === 'function') {
                const ok = await window.crmConfirmDeleteDialog({
                    title: isLaborVoid ? '确认作废文件' : '确认删除文件',
                    targetText: isLaborVoid ? `将作废：${label}` : `将删除：${label}`,
                    hint: isLaborVoid
                        ? '作废后记录与劳动合同编号将保留。'
                        : (isLaborDraft
                            ? '草稿劳动合同删除后编号可重新使用。'
                            : '删除后将从当前员工文件列表移除。'),
                    confirmText: isLaborVoid ? '确认作废' : '确认删除',
                });
                if (!ok) return;
            } else if (!window.confirm(`确认${isLaborVoid ? '作废' : '删除'}文件「${label}」？`)) {
                return;
            }
            const r = await fetch(`${apiBase}/${row.id}`, { method: 'DELETE', headers: hdr() });
            if (!r.ok) {
                let msg = isLaborVoid ? '作废失败' : '删除失败';
                try {
                    const body = await r.json();
                    const detail = body && body.detail;
                    if (typeof detail === 'string' && detail.trim()) msg = detail.trim();
                } catch (_) {}
                if (window.crmToast) window.crmToast.error(msg);
                else alert(msg);
                return;
            }
            if (employeeFileDetailRow.value && employeeFileDetailRow.value.id === row.id) {
                closeEmployeeFileDetailDrawer();
            }
            if (employeeFilePreviewRow.value) {
                const previewIds = employeeFileEntryFiles(row).map((f) => f.id);
                if (previewIds.includes(employeeFilePreviewRow.value.id)) closeEmployeeFilePreview();
            }
            await loadEmployeeFiles();
        };

        const publishEmployeeFile = async (row) => {
            if (!employeeFileCanPublish(row)) return;
            const isLabor = String((row && row.document_type) || '').trim() === LABOR_CONTRACT_TYPE;
            const label = employeeFileEntryLabel(row);
            const hint = isLabor
                ? '发布后劳动合同编号将锁定；若需移除，删除时将作废并保留记录。'
                : '发布后若需移除，删除时将作废并保留记录。';
            if (typeof window.crmConfirmDeleteDialog === 'function') {
                const ok = await window.crmConfirmDeleteDialog({
                    title: '确认发布',
                    targetText: `将发布：${label}`,
                    hint,
                    confirmText: '确认发布',
                });
                if (!ok) return;
            } else if (!window.confirm(`确认发布文件「${label}」？`)) {
                return;
            }
            const r = await fetch(`${apiBase}/${row.id}`, {
                method: 'PATCH',
                headers: { ...hdr(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'published' }),
            });
            if (!r.ok) {
                let msg = '发布失败';
                try {
                    const body = await r.json();
                    const detail = body && body.detail;
                    if (typeof detail === 'string' && detail.trim()) msg = detail.trim();
                } catch (_) {}
                if (window.crmToast) window.crmToast.error(msg);
                else alert(msg);
                return;
            }
            const updated = await r.json().catch(() => null);
            if (employeeFileDetailRow.value && employeeFileDetailRow.value.id === row.id && updated) {
                employeeFileDetailRow.value = updated;
            }
            await loadEmployeeFiles();
            if (window.crmToast) window.crmToast.success('已发布');
        };

        const mountEmployeeFiles = async () => {
            if (moduleKey !== 'employee_files') return;
            await loadEmployeeFiles();
            if (typeof requestAnimationFrame === 'function') {
                requestAnimationFrame(() => {
                    window.crmScheduleTableColumnResize?.(document.getElementById('delivery-detail-app'));
                });
            }
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
            isLaborContractUpload,
            employeeFileDetailRow,
            employeeFilePreviewRow,
            employeeFilePreviewUrl,
            employeeFilePreviewMode,
            employeeFilePreviewLoading,
            employeeFileStatusLabel,
            employeeFileStatusClass,
            employeeFileMediaLabel,
            employeeFileDocumentTypeLabel,
            employeeFileLaborContractNoLabel,
            employeeFileValidUntilLabel,
            employeeFileRemarksLabel,
            employeeFileEntryFiles,
            employeeFileEntryIsGroup,
            employeeFileEntryLabel,
            employeeFileCanPreview,
            employeeFileCanPublish,
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
            openEmployeeFilePreviewFromFilename,
            openEmployeeFilePreviewFromDetail,
            closeEmployeeFilePreview,
            downloadEmployeeFile,
            removeEmployeeFile,
            publishEmployeeFile,
            mountEmployeeFiles,
        };
    }

    window.CrmDeliveryDetailEmployeeFiles = {
        createEmployeeFilesState,
    };
})();
