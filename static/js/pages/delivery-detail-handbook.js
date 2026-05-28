/**
 * Delivery detail handbook module (Phase 5E Step 6).
 */
(function () {
    'use strict';

function flattenHandbookOutline(nodes, depth = 0) {
    const out = [];
    (nodes || []).forEach((n) => {
        const page = Number(n.page) > 0 ? Number(n.page) : 1;
        out.push({ title: n.title || '未命名', page, depth });
        if (n.children && n.children.length) {
            out.push(...flattenHandbookOutline(n.children, depth + 1));
        }
    });
    return out;
}

    function createHandbookState(deps) {
        const {
            ref,
            reactive,
            computed,
            watch,
            nextTick,
            clientId,
            moduleKey,
            handbookAdminCrossSearch,
            crmHighlightSearchQuery,
            authHeader,
            fetchBlob,
            downloadBlob,
        } = deps;
        const hdr = () => (typeof authHeader === 'function' ? authHeader() : window.crmAuthHeader());
        const fetchAuthBlob = (path) => (typeof fetchBlob === 'function' ? fetchBlob(path) : window.crmFetchAuthenticatedBlob(path));
        const dlBlob = (blob, mime, name) => (typeof downloadBlob === 'function' ? downloadBlob(blob, mime, name) : window.crmDownloadBlob(blob, mime, name));

                const handbookUploadMeta = reactive({
                    version_label: '',
                    status: '',
                    tags: '',
                    permission_departments: '',
                    permission_levels: '',
                });
                const handbookStatusFilter = ref('');
                const handbookFiles = ref([]);
                const handbookFileInput = ref(null);
                const handbookUploading = ref(false);
                const handbookUploadError = ref('');
                const handbookSelectedFiles = ref([]);
                const handbookFsPanelOpen = ref(false);
                const handbookFsQuery = ref('');
                const handbookFsResults = ref([]);
                const handbookFsBusy = ref(false);
                const handbookFsError = ref('');
                const handbookFsSearched = ref(false);
                const handbookReindexBusy = ref(false);
                const handbookFtsSyncBusy = ref(false);
                const handbookFsDetailOpen = ref(false);
                const handbookFsDetailHit = ref(null);
                const highlightHandbookSearchHtml = (text) => crmHighlightSearchQuery(text, handbookFsQuery.value);
                const handbookReaderRow = ref(null);
                const handbookReaderMediaUrl = ref('');
                const handbookPdfBlobUrl = ref('');
                const handbookReaderPdfPage = ref(1);
                const handbookPdfSearchQuery = ref('');
                const handbookPdfTextPages = ref([]);
                const handbookPdfTextLoadedId = ref(null);
                const handbookPdfTextBusy = ref(false);
                const handbookPdfTextError = ref('');
                const handbookPdfRenderedPageUrl = ref('');
                const handbookPdfRenderBusy = ref(false);
                const handbookMediaRef = ref(null);
                const handbookPlyrInstance = ref(null);
                const handbookReaderPipBrowseMode = ref(false);
                const handbookPendingMediaSeek = ref(null);
                const handbookMetaModalOpen = ref(false);
                const handbookMetaForm = reactive({
                    id: null,
                    version_label: '',
                    status: 'draft',
                    tags: '',
                    permission_departments: '',
                    permission_levels: '',
                });
                const handbookCuesModalOpen = ref(false);
                const handbookCuesEdit = ref([]);
                const handbookCuesEditingId = ref(null);
                const filteredHandbookFiles = computed(() => {
                    let rows = Array.isArray(handbookFiles.value) ? [...handbookFiles.value] : [];
                    const st = handbookStatusFilter.value;
                    if (st) rows = rows.filter((r) => r.status === st);
                    return rows;
                });
                const handbookSelectedFileSummary = computed(() => {
                    const files = Array.isArray(handbookSelectedFiles.value) ? handbookSelectedFiles.value : [];
                    if (!files.length) return '';
                    if (files.length === 1) return files[0].name || '已选择 1 个文件';
                    return `已选择 ${files.length} 个文件：${files.map((f) => f.name || '未命名').join('、')}`;
                });
                const handbookPdfOutlineFlat = computed(() => {
                    const row = handbookReaderRow.value;
                    if (!row || row.media_kind !== 'pdf') return [];
                    const o = row.pdf_outline;
                    if (o && o.length) return flattenHandbookOutline(o);
                    return [{ title: '文档首页', page: 1, depth: 0 }];
                });
                const handbookPdfIframeSrc = computed(() => {
                    const row = handbookReaderRow.value;
                    if (!row || row.media_kind !== 'pdf') return '';
                    const p = handbookReaderPdfPage.value || 1;
                    const base = handbookPdfBlobUrl.value || '';
                    if (!base) return '';
                    const q = String(handbookPdfSearchQuery.value || '').trim();
                    const parts = [`page=${encodeURIComponent(String(p))}`];
                    if (q) parts.push(`search=${encodeURIComponent(q)}`);
                    return `${base}#${parts.join('&')}`;
                });
                const handbookPdfRenderedPageSrc = computed(() => {
                    const row = handbookReaderRow.value;
                    if (!row || row.media_kind !== 'pdf' || !handbookPdfSearchActive.value) return '';
                    const cid = handbookRowClientId(row);
                    const id = Number(row.id);
                    if (!Number.isFinite(id) || id <= 0) return '';
                    const page = Math.max(1, Number(handbookReaderPdfPage.value) || 1);
                    const q = String(handbookPdfSearchQuery.value || '').trim();
                    return `/api/clients/${cid}/delivery/handbooks/${id}/pdf-page.png?page=${encodeURIComponent(String(page))}&q=${encodeURIComponent(q)}`;
                });
                const handbookPdfSearchTerms = computed(() => (
                    String(handbookPdfSearchQuery.value || '').trim().split(/\s+/).filter(Boolean)
                ));
                const handbookPdfSearchResults = computed(() => {
                    const terms = handbookPdfSearchTerms.value;
                    if (!terms.length) return [];
                    return handbookPdfTextPages.value.filter((p) => {
                        const text = String(p && p.text != null ? p.text : '').toLowerCase();
                        return terms.some((term) => text.includes(String(term).toLowerCase()));
                    });
                });
                const handbookPdfSearchCount = computed(() => handbookPdfSearchResults.value.length);
                const handbookPdfSearchActive = computed(() => !!handbookPdfSearchTerms.value.length);
                const handbookStatusLabel = (s) => ({ draft: '草稿', published: '已发布', deprecated: '已作废' }[s] || s || '—');
                const handbookStatusClass = (s) => {
                    if (s === 'published') return 'bg-green-100 text-green-800';
                    if (s === 'deprecated') return 'bg-gray-200 text-gray-600';
                    return 'bg-amber-50 text-amber-800';
                };
                const handbookMediaLabel = (row) => {
                    const mk = row && row.media_kind ? row.media_kind : '';
                    if (mk === 'pdf') return 'PDF';
                    if (mk === 'video') return '视频';
                    if (mk === 'audio') return '音频';
                    if (mk === 'document') return '文档';
                    return '文件';
                };
                const handbookSearchStatusLabel = (f) => {
                    if (!f || f.media_kind !== 'pdf') return '—';
                    const s = f.search_status || 'pending';
                    const map = {
                        pending: '待索引',
                        indexing: '索引中…',
                        indexed: '已索引',
                        failed: '失败',
                        skipped: '跳过',
                    };
                    return map[s] || s || '—';
                };
                const handbookSearchStatusClass = (f) => {
                    if (!f || f.media_kind !== 'pdf') return 'text-gray-400';
                    const s = f.search_status || 'pending';
                    if (s === 'indexed') return 'bg-emerald-50 text-emerald-800';
                    if (s === 'failed') return 'bg-red-50 text-red-800';
                    if (s === 'indexing') return 'bg-blue-50 text-blue-800';
                    if (s === 'skipped') return 'bg-gray-100 text-gray-600';
                    return 'bg-amber-50 text-amber-900';
                };
                const formatHandbookSeconds = (sec) => {
                    const s = Math.max(0, Number(sec) || 0);
                    const m = Math.floor(s / 60);
                    const r = Math.floor(s % 60);
                    return `${m}:${String(r).padStart(2, '0')}`;
                };
                const runHandbookGlobalSearch = async () => {
                    handbookFsError.value = '';
                    const q = handbookFsQuery.value.trim();
                    if (!q) {
                        handbookFsError.value = '请输入检索词';
                        return;
                    }
                    handbookFsBusy.value = true;
                    handbookFsSearched.value = true;
                    try {
                        const u = new URL(`${window.location.origin}/api/delivery/handbooks/search`);
                        u.searchParams.set('q', q);
                        const r = await fetch(u.toString(), { headers: hdr() });
                        const data = await r.json().catch(() => ({}));
                        if (!r.ok) {
                            const d = data.detail;
                            handbookFsError.value = Array.isArray(d) ? d.map((x) => x.msg || '').filter(Boolean).join('；') : (d || `检索失败（${r.status}）`);
                            handbookFsResults.value = [];
                            return;
                        }
                        handbookFsResults.value = Array.isArray(data.results) ? data.results : [];
                    } catch (e) {
                        handbookFsError.value = '网络错误';
                        handbookFsResults.value = [];
                    } finally {
                        handbookFsBusy.value = false;
                    }
                };
                const closeHandbookFsDetail = () => {
                    handbookFsDetailOpen.value = false;
                    handbookFsDetailHit.value = null;
                };
                const openHandbookFsExcerptDetail = (hit) => {
                    handbookFsDetailHit.value = hit;
                    handbookFsDetailOpen.value = true;
                };
                const openHandbookReaderFromFsDetail = async () => {
                    const h = handbookFsDetailHit.value;
                    closeHandbookFsDetail();
                    if (h) await openHandbookReader(h);
                };
                const queueHandbookReindexStale = async () => {
                    handbookReindexBusy.value = true;
                    try {
                        const r = await fetch(`${window.location.origin}/api/delivery/handbooks/reindex-stale`, {
                            method: 'POST',
                            headers: hdr(),
                        });
                        const j = await r.json().catch(() => ({}));
                        if (!r.ok) {
                            const d = j.detail;
                            alert(Array.isArray(d) ? d.map((x) => x.msg || '').join('；') : (d || '排队失败'));
                            return;
                        }
                        alert(`已加入后台队列：${j.queued || 0} 条 PDF`);
                    } finally {
                        handbookReindexBusy.value = false;
                    }
                };
                const syncHandbookFtsFromBody = async () => {
                    handbookFtsSyncBusy.value = true;
                    try {
                        const r = await fetch(`${window.location.origin}/api/delivery/handbooks/sync-fts-indexed`, {
                            method: 'POST',
                            headers: hdr(),
                        });
                        const j = await r.json().catch(() => ({}));
                        if (!r.ok) {
                            const d = j.detail;
                            alert(Array.isArray(d) ? d.map((x) => x.msg || '').join('；') : (d || '同步失败'));
                            return;
                        }
                        alert(`已根据正文重建 FTS：${j.synced || 0} 条`);
                    } finally {
                        handbookFtsSyncBusy.value = false;
                    }
                };
                const syncHandbookReaderFromList = () => {
                    const cur = handbookReaderRow.value;
                    if (!cur || !cur.id) return;
                    const found = handbookFiles.value.find((x) => Number(x.id) === Number(cur.id));
                    if (found) handbookReaderRow.value = found;
                };
                const destroyHandbookPlyr = () => {
                    const inst = handbookPlyrInstance.value;
                    if (inst) {
                        try {
                            inst.destroy();
                        } catch (_) { /* ignore */ }
                        handbookPlyrInstance.value = null;
                    }
                };
                const initHandbookPlyrForOpenRow = () => {
                    destroyHandbookPlyr();
                    const row = handbookReaderRow.value;
                    if (!row || (row.media_kind !== 'video' && row.media_kind !== 'audio')) return;
                    if (typeof window.Plyr === 'undefined') {
                        const el = handbookMediaRef.value;
                        if (el && el.setAttribute) el.setAttribute('controls', 'controls');
                        return;
                    }
                    const el = handbookMediaRef.value;
                    if (!el) return;
                    const isVideo = row.media_kind === 'video';
                    const plyrOpts = {
                        iconUrl: 'https://unpkg.com/plyr@3.7.8/dist/plyr.svg',
                        controls: isVideo
                            ? ['play', 'progress', 'current-time', 'mute', 'volume', 'pip', 'fullscreen']
                            : ['play', 'progress', 'current-time', 'mute', 'volume'],
                        keyboard: { focused: true, global: false },
                        tooltips: { controls: false, seek: true },
                        hideControlsOnPause: true,
                        resetOnEnd: false,
                        fullscreen: { enabled: true, fallback: true, iosNative: true },
                    };
                    let inst;
                    try {
                        inst = new window.Plyr(el, plyrOpts);
                    } catch (_) {
                        if (el.setAttribute) el.setAttribute('controls', 'controls');
                        return;
                    }
                    if (typeof inst.on === 'function') {
                        inst.on('enterpip', () => {
                            handbookReaderPipBrowseMode.value = true;
                        });
                        inst.on('leavepip', () => {
                            handbookReaderPipBrowseMode.value = false;
                        });
                    }
                    handbookPlyrInstance.value = inst;
                };
                const flushHandbookPendingMediaSeek = () => {
                    const seconds = handbookPendingMediaSeek.value;
                    if (seconds === null || seconds === undefined) return;
                    handbookPendingMediaSeek.value = null;
                    setTimeout(() => seekHandbookMedia(seconds), 120);
                };
                watch(handbookReaderRow, async (row) => {
                    handbookReaderPipBrowseMode.value = false;
                    destroyHandbookPlyr();
                    if (!row || (row.media_kind !== 'video' && row.media_kind !== 'audio')) return;
                    await nextTick();
                    await nextTick();
                    initHandbookPlyrForOpenRow();
                    flushHandbookPendingMediaSeek();
                });
                watch(handbookPdfRenderedPageSrc, () => {
                    loadHandbookPdfRenderedPage();
                });
                const restoreHandbookReaderFromPipBrowse = async () => {
                    handbookReaderPipBrowseMode.value = false;
                    const inst = handbookPlyrInstance.value;
                    const media = inst && inst.media;
                    if (media && document.pictureInPictureElement === media) {
                        try {
                            await document.exitPictureInPicture();
                        } catch (_) { /* ignore */ }
                    }
                };
                const handbookRowClientId = (row) => {
                    const x = Number(row && row.client_id);
                    return Number.isFinite(x) && x > 0 ? x : clientId;
                };
                const clearHandbookReaderBlobUrls = () => {
                    if (handbookReaderMediaUrl.value) {
                        URL.revokeObjectURL(handbookReaderMediaUrl.value);
                        handbookReaderMediaUrl.value = '';
                    }
                    if (handbookPdfBlobUrl.value) {
                        URL.revokeObjectURL(handbookPdfBlobUrl.value);
                        handbookPdfBlobUrl.value = '';
                    }
                };
                const loadHandbookReaderBlobs = async (row) => {
                    const sp = (row && row.stored_path) || '';
                    if (!sp) return;
                    const rowId = Number(row.id);
                    try {
                        const blob = await fetchAuthBlob(sp);
                        if (!handbookReaderRow.value || Number(handbookReaderRow.value.id) !== rowId) return;
                        if (row.media_kind === 'pdf') {
                            if (handbookPdfBlobUrl.value) URL.revokeObjectURL(handbookPdfBlobUrl.value);
                            handbookPdfBlobUrl.value = URL.createObjectURL(blob);
                        } else if (row.media_kind === 'video' || row.media_kind === 'audio') {
                            if (handbookReaderMediaUrl.value) URL.revokeObjectURL(handbookReaderMediaUrl.value);
                            handbookReaderMediaUrl.value = URL.createObjectURL(blob);
                        }
                    } catch (e) { /* ignore */ }
                };
                const downloadHandbookFile = async (f) => {
                    const sp = (f && f.stored_path) || '';
                    if (!sp) return;
                    try {
                        const blob = await fetchAuthBlob(sp);
                        dlBlob(blob, '', (f && f.original_filename) || 'download');
                    } catch (e) {
                        alert('下载失败');
                    }
                };
                const openHandbookReader = async (row, opts = {}) => {
                    clearHandbookReaderBlobUrls();
                    handbookReaderRow.value = row;
                    handbookReaderPdfPage.value = Math.max(1, Number(opts.page) || 1);
                    if (row.media_kind === 'pdf') {
                        handbookPdfSearchQuery.value = '';
                        loadHandbookPdfText(row);
                    }
                    loadHandbookReaderBlobs(row);
                    if ((row.media_kind === 'video' || row.media_kind === 'audio') && opts.seconds !== undefined && opts.seconds !== null) {
                        handbookPendingMediaSeek.value = Math.max(0, Number(opts.seconds) || 0);
                    }
                    const po = row.pdf_outline;
                    const cid = handbookRowClientId(row);
                    if (row.media_kind === 'pdf' && (!Array.isArray(po) || !po.length)) {
                        try {
                            const r = await fetch(`/api/clients/${cid}/delivery/handbooks/${row.id}/rebuild-pdf-outline`, {
                                method: 'POST',
                                headers: hdr(),
                            });
                            if (r.ok) {
                                const updated = await r.json();
                                if (
                                    handbookReaderRow.value &&
                                    Number(handbookReaderRow.value.id) === Number(row.id)
                                ) {
                                    handbookReaderRow.value = updated;
                                }
                                if (cid === clientId) await loadHandbooks();
                            }
                        } catch (e) { /* ignore */ }
                    }
                    if (row.media_kind === 'pdf' && opts.page) {
                        handbookReaderPdfPage.value = Math.max(1, Number(opts.page) || 1);
                    }
                };
                const closeHandbookReader = () => {
                    handbookReaderPipBrowseMode.value = false;
                    handbookPdfSearchQuery.value = '';
                    clearHandbookPdfRenderedPage();
                    clearHandbookReaderBlobUrls();
                    destroyHandbookPlyr();
                    handbookReaderRow.value = null;
                };
                const handbookReaderBackdropClick = () => {
                    if (handbookReaderPipBrowseMode.value) return;
                    closeHandbookReader();
                };
                const setHandbookPdfPage = (page) => {
                    handbookReaderPdfPage.value = Math.max(1, Number(page) || 1);
                };
                const handbookPdfTextSnippet = (raw) => {
                    const text = String(raw || '').replace(/\s+/g, ' ').trim();
                    if (text.length <= 900) return text;
                    const terms = handbookPdfSearchTerms.value;
                    const lower = text.toLowerCase();
                    let hit = -1;
                    for (const term of terms) {
                        const pos = lower.indexOf(String(term).toLowerCase());
                        if (pos >= 0 && (hit < 0 || pos < hit)) hit = pos;
                    }
                    const start = hit >= 0 ? Math.max(0, hit - 260) : 0;
                    const end = Math.min(text.length, start + 900);
                    return `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`;
                };
                const highlightHandbookPdfHtml = (text) => crmHighlightSearchQuery(text, handbookPdfSearchQuery.value);
                const handbookPdfOutlineMatches = (item) => {
                    const terms = handbookPdfSearchTerms.value;
                    if (!terms.length || !item) return false;
                    const title = String(item.title || '').toLowerCase();
                    return terms.some((term) => title.includes(String(term).toLowerCase()));
                };
                let handbookPdfRenderSeq = 0;
                const clearHandbookPdfRenderedPage = () => {
                    if (handbookPdfRenderedPageUrl.value) {
                        URL.revokeObjectURL(handbookPdfRenderedPageUrl.value);
                        handbookPdfRenderedPageUrl.value = '';
                    }
                };
                const loadHandbookPdfRenderedPage = async () => {
                    const src = handbookPdfRenderedPageSrc.value;
                    const seq = ++handbookPdfRenderSeq;
                    clearHandbookPdfRenderedPage();
                    if (!src) return;
                    handbookPdfRenderBusy.value = true;
                    try {
                        const r = await fetch(src, { headers: hdr() });
                        if (!r.ok) return;
                        const blob = await r.blob();
                        if (seq !== handbookPdfRenderSeq) return;
                        handbookPdfRenderedPageUrl.value = URL.createObjectURL(blob);
                    } finally {
                        if (seq === handbookPdfRenderSeq) handbookPdfRenderBusy.value = false;
                    }
                };
                const loadHandbookPdfText = async (row) => {
                    const target = row || handbookReaderRow.value;
                    if (!target || target.media_kind !== 'pdf') return;
                    const id = Number(target.id);
                    if (handbookPdfTextLoadedId.value === id) return;
                    handbookPdfTextBusy.value = true;
                    handbookPdfTextError.value = '';
                    try {
                        const cid = handbookRowClientId(target);
                        const r = await fetch(`/api/clients/${cid}/delivery/handbooks/${id}/pdf-text`, {
                            headers: hdr(),
                        });
                        const data = await r.json().catch(() => ({}));
                        if (!r.ok) {
                            const d = data.detail;
                            throw new Error(Array.isArray(d) ? d.map((x) => x.msg || '').join('；') : (d || '读取 PDF 正文失败'));
                        }
                        handbookPdfTextPages.value = Array.isArray(data.pages) ? data.pages : [];
                        handbookPdfTextLoadedId.value = id;
                    } catch (e) {
                        handbookPdfTextPages.value = [];
                        handbookPdfTextLoadedId.value = id;
                        handbookPdfTextError.value = e && e.message ? e.message : '读取 PDF 正文失败';
                    } finally {
                        handbookPdfTextBusy.value = false;
                    }
                };
                const focusHandbookPdfSearch = async () => {
                    await loadHandbookPdfText();
                    await nextTick();
                    const el = document.getElementById('handbook-pdf-search-input');
                    if (el && typeof el.focus === 'function') el.focus();
                };
                const clearHandbookPdfSearch = () => {
                    handbookPdfSearchQuery.value = '';
                };
                const seekHandbookMedia = (seconds) => {
                    const inst = handbookPlyrInstance.value;
                    const el = (inst && inst.media) || handbookMediaRef.value;
                    if (el && Number.isFinite(Number(seconds))) {
                        el.currentTime = Math.max(0, Number(seconds));
                        try {
                            el.play();
                        } catch (e) { /* ignore */ }
                    }
                };
                const openHandbookSource = async (source) => {
                    if (moduleKey !== 'handbook' || !source) return false;
                    const cid = Number(source.client_id);
                    if (Number.isFinite(cid) && cid > 0 && cid !== clientId) return false;
                    const hid = Number(source.handbook_id || source.id || source.handbook_id);
                    if (!Number.isFinite(hid) || hid <= 0) return false;
                    if (!handbookFiles.value.length) await loadHandbooks();
                    let row = handbookFiles.value.find((x) => Number(x.id) === hid);
                    if (!row) {
                        await loadHandbooks();
                        row = handbookFiles.value.find((x) => Number(x.id) === hid);
                    }
                    if (!row) return false;
                    await openHandbookReader(row, {
                        page: source.page,
                        seconds: source.seconds,
                    });
                    if (row.media_kind === 'pdf' && source.page) {
                        setHandbookPdfPage(source.page);
                    } else if ((row.media_kind === 'video' || row.media_kind === 'audio') && source.seconds !== undefined && source.seconds !== null) {
                        handbookPendingMediaSeek.value = Math.max(0, Number(source.seconds) || 0);
                        await nextTick();
                        await nextTick();
                        flushHandbookPendingMediaSeek();
                    }
                    return true;
                };
                const openHandbookSourceFromUrl = async () => {
                    if (moduleKey !== 'handbook') return;
                    const params = new URLSearchParams(window.location.search || '');
                    const hid = Number(params.get('handbook_id') || params.get('handbookId') || '');
                    if (!Number.isFinite(hid) || hid <= 0) return;
                    const opened = await openHandbookSource({
                        client_id: clientId,
                        handbook_id: hid,
                        page: params.get('page') || undefined,
                        seconds: params.get('seconds') || undefined,
                    });
                    if (opened) {
                        params.delete('handbook_id');
                        params.delete('handbookId');
                        params.delete('page');
                        params.delete('seconds');
                        const qs = params.toString();
                        const newUrl = window.location.pathname + (qs ? `?${qs}` : '') + (window.location.hash || '');
                        window.history.replaceState({}, '', newUrl);
                    }
                };
                const openHandbookMetaModal = (f) => {
                    handbookMetaForm.id = f.id;
                    handbookMetaForm.version_label = f.version_label || '';
                    handbookMetaForm.status = f.status || 'draft';
                    handbookMetaForm.tags = Array.isArray(f.tags) ? f.tags.join(', ') : '';
                    handbookMetaForm.permission_departments = Array.isArray(f.permission_departments)
                        ? f.permission_departments.join(', ')
                        : '';
                    handbookMetaForm.permission_levels = Array.isArray(f.permission_levels) ? f.permission_levels.join(', ') : '';
                    handbookMetaModalOpen.value = true;
                };
                const saveHandbookMeta = async () => {
                    const id = handbookMetaForm.id;
                    if (!id) return;
                    const body = {
                        version_label: handbookMetaForm.version_label,
                        status: handbookMetaForm.status,
                        tags: handbookMetaForm.tags,
                        permission_departments: handbookMetaForm.permission_departments,
                        permission_levels: handbookMetaForm.permission_levels,
                    };
                    const r = await fetch(`/api/clients/${clientId}/delivery/handbooks/${id}`, {
                        method: 'PATCH',
                        headers: { ...hdr(), 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    if (!r.ok) {
                        alert('保存失败');
                        return;
                    }
                    handbookMetaModalOpen.value = false;
                    await loadHandbooks();
                    syncHandbookReaderFromList();
                };
                const openHandbookCuesModal = (f) => {
                    handbookCuesEditingId.value = f.id;
                    handbookCuesEdit.value = (f.media_cues || []).map((c) => ({
                        label: c.label || '',
                        seconds: Number(c.seconds) || 0,
                    }));
                    if (!handbookCuesEdit.value.length) {
                        handbookCuesEdit.value = [{ label: '', seconds: 0 }];
                    }
                    handbookCuesModalOpen.value = true;
                };
                const saveHandbookCues = async () => {
                    const id = handbookCuesEditingId.value;
                    if (!id) return;
                    const cues = handbookCuesEdit.value
                        .filter((c) => String(c.label || '').trim() || Number(c.seconds) > 0)
                        .map((c) => ({
                            label: String(c.label || '').trim() || '锚点',
                            seconds: Math.max(0, Number(c.seconds) || 0),
                        }));
                    const r = await fetch(`/api/clients/${clientId}/delivery/handbooks/${id}`, {
                        method: 'PATCH',
                        headers: { ...hdr(), 'Content-Type': 'application/json' },
                        body: JSON.stringify({ media_cues: cues }),
                    });
                    if (!r.ok) {
                        alert('保存失败');
                        return;
                    }
                    handbookCuesModalOpen.value = false;
                    await loadHandbooks();
                    syncHandbookReaderFromList();
                };
                const rebuildHandbookOutline = async () => {
                    const row = handbookReaderRow.value;
                    if (!row || row.media_kind !== 'pdf') return;
                    const cid = handbookRowClientId(row);
                    const r = await fetch(`/api/clients/${cid}/delivery/handbooks/${row.id}/rebuild-pdf-outline`, {
                        method: 'POST',
                        headers: hdr(),
                    });
                    if (!r.ok) {
                        let msg = '目录提取失败';
                        try {
                            const j = await r.json();
                            if (typeof j.detail === 'string') msg = j.detail;
                        } catch (e) { /* ignore */ }
                        alert(msg);
                        return;
                    }
                    const updated = await r.json();
                    handbookReaderRow.value = updated;
                    if (cid === clientId) await loadHandbooks();
                };
                const loadHandbooks = async () => {
                    if (moduleKey !== 'handbook') return;
                    handbookUploadError.value = '';
                    const r = await fetch(`/api/clients/${clientId}/delivery/handbooks`, { headers: hdr() });
                    handbookFiles.value = r.ok ? await r.json() : [];
                };
                const onHandbookFilesSelected = async (ev) => {
                    const input = ev.target;
                    const list = input && input.files ? Array.from(input.files) : [];
                    if (input) input.value = '';
                    handbookSelectedFiles.value = list;
                    handbookUploadError.value = '';
                };
                const validateHandbookUploadMeta = () => {
                    if (!handbookSelectedFiles.value.length) return '请选择文件';
                    if (!String(handbookUploadMeta.status || '').trim()) return '请选择状态';
                    if (!String(handbookUploadMeta.tags || '').trim()) return '请填写标签';
                    if (!String(handbookUploadMeta.permission_departments || '').trim()) return '请填写阅读部门';
                    if (!String(handbookUploadMeta.permission_levels || '').trim()) return '请选择阅读级别';
                    return '';
                };
                const uploadSelectedHandbookFiles = async () => {
                    const list = Array.isArray(handbookSelectedFiles.value) ? handbookSelectedFiles.value : [];
                    const validationMsg = validateHandbookUploadMeta();
                    if (validationMsg) {
                        handbookUploadError.value = validationMsg;
                        return;
                    }
                    handbookUploadError.value = '';
                    handbookUploading.value = true;
                    try {
                        const fd = new FormData();
                        list.forEach((file) => fd.append('files', file));
                        fd.append('version_label', handbookUploadMeta.version_label || '');
                        fd.append('status', handbookUploadMeta.status || '');
                        fd.append('tags', handbookUploadMeta.tags || '');
                        fd.append('permission_departments', handbookUploadMeta.permission_departments || '');
                        fd.append('permission_levels', handbookUploadMeta.permission_levels || '');
                        const r = await fetch(`/api/clients/${clientId}/delivery/handbooks`, {
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
                            handbookUploadError.value = msg;
                            return;
                        }
                        await loadHandbooks();
                        handbookSelectedFiles.value = [];
                    } finally {
                        handbookUploading.value = false;
                    }
                };
                const removeHandbook = async (row) => {
                    const ok = await window.crmConfirmDeleteDialog({
                        title: '确认删除文件',
                        targetText: `将删除文件：${row.original_filename || '未命名文件'}`,
                        hint: '删除后将从当前交付手册列表移除。',
                    });
                    if (!ok) return;
                    if (handbookReaderRow.value && Number(handbookReaderRow.value.id) === Number(row.id)) {
                        handbookReaderRow.value = null;
                    }
                    const r = await fetch(`/api/clients/${clientId}/delivery/handbooks/${row.id}`, {
                        method: 'DELETE',
                        headers: hdr(),
                    });
                    if (!r.ok) {
                        alert('删除失败');
                        return;
                    }
                    await loadHandbooks();
                };
                const onHandbookReaderEscape = async (e) => {
                    if ((e.ctrlKey || e.metaKey) && String(e.key || '').toLowerCase() === 'f' && handbookReaderRow.value && handbookReaderRow.value.media_kind === 'pdf') {
                        e.preventDefault();
                        await focusHandbookPdfSearch();
                        return;
                    }
                    if (e.key !== 'Escape') return;
                    if (handbookFsDetailOpen.value) {
                        closeHandbookFsDetail();
                        return;
                    }
                    if (handbookReaderPipBrowseMode.value) {
                        await restoreHandbookReaderFromPipBrowse();
                        return;
                    }
                    if (handbookReaderRow.value) closeHandbookReader();
                };

        const mountHandbook = async () => {
            if (moduleKey !== 'handbook') return;
            await loadHandbooks();
            window.crmOpenHandbookSource = openHandbookSource;
            await openHandbookSourceFromUrl();
        };

        const unmountHandbook = () => {
            if (window.crmOpenHandbookSource === openHandbookSource) {
                delete window.crmOpenHandbookSource;
            }
            clearHandbookPdfRenderedPage();
            destroyHandbookPlyr();
        };

        return {
            handbookUploadMeta, handbookStatusFilter, filteredHandbookFiles, handbookPdfOutlineFlat, handbookPdfIframeSrc,
            handbookPdfSearchQuery, handbookPdfSearchResults, handbookPdfSearchCount, handbookPdfSearchActive,
            handbookPdfRenderedPageSrc, handbookPdfRenderedPageUrl, handbookPdfRenderBusy,
            handbookPdfTextBusy, handbookPdfTextError, loadHandbookPdfText, clearHandbookPdfSearch,
            handbookPdfTextSnippet, highlightHandbookPdfHtml, handbookPdfOutlineMatches,
            handbookAdminCrossSearch, handbookFsPanelOpen, handbookFsQuery, handbookFsResults, handbookFsBusy, handbookFsError, handbookFsSearched,
            handbookFsDetailOpen, handbookFsDetailHit, closeHandbookFsDetail, openHandbookFsExcerptDetail, openHandbookReaderFromFsDetail,
            handbookReindexBusy, handbookFtsSyncBusy, runHandbookGlobalSearch, queueHandbookReindexStale, syncHandbookFtsFromBody,
            highlightHandbookSearchHtml,
            handbookFiles, handbookFileInput, handbookUploading, handbookUploadError, handbookSelectedFiles, handbookSelectedFileSummary, handbookReaderRow, handbookReaderPdfPage, handbookMediaRef,
            handbookReaderPipBrowseMode, restoreHandbookReaderFromPipBrowse,
            handbookMetaModalOpen, handbookMetaForm, handbookCuesModalOpen, handbookCuesEdit,
            handbookStatusLabel, handbookStatusClass, handbookMediaLabel, handbookSearchStatusLabel, handbookSearchStatusClass, formatHandbookSeconds,
            loadHandbooks, onHandbookFilesSelected, uploadSelectedHandbookFiles, removeHandbook, downloadHandbookFile,
            openHandbookReader, closeHandbookReader, handbookReaderBackdropClick, setHandbookPdfPage, seekHandbookMedia,
            handbookReaderMediaUrl,
            openHandbookMetaModal, saveHandbookMeta, openHandbookCuesModal, saveHandbookCues, rebuildHandbookOutline,
            onHandbookReaderEscape,
            mountHandbook,
            unmountHandbook,
        };
    }

    window.CrmDeliveryDetailHandbook = {
        createHandbookState,
    };
})();
