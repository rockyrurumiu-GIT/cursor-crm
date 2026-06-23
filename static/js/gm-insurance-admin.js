(function () {
    'use strict';

    var panel = document.getElementById('panel-insurance');
    if (!panel) return;

    var CAN = document.getElementById('permission-center-app').getAttribute('data-can-insurance') === '1';
    if (!CAN) return;

    var tbody = document.getElementById('insurance-tbody');
    var rows = [];
    var page = 0;
    var pageSize = 10;
    var total = 0;

    function opBtn(cls, label, attrs, icon) {
        if (typeof window.spcOpBtn === 'function') {
            return window.spcOpBtn(cls, label, attrs, icon);
        }
        return '<button type="button" class="' + cls + '" aria-label="' + label + '" ' + (attrs || '') + '>' + label + '</button>';
    }

    function icons() {
        return window.SPC_ICONS || {
            edit: '',
            delete: '',
        };
    }

    function headers() {
        return Object.assign({}, window.crmAuthHeader(), { 'Content-Type': 'application/json' });
    }

    function showMsg(text, ok) {
        if (typeof window.spcShowMsg === 'function') {
            window.spcShowMsg(text, ok);
            return;
        }
        alert(text);
    }

    async function api(path, opts) {
        opts = opts || {};
        var r = await fetch(path, Object.assign({ credentials: 'same-origin', headers: headers() }, opts));
        var data = await r.json().catch(function () { return {}; });
        if (!r.ok) {
            var detail = data.detail;
            throw new Error(typeof detail === 'string' ? detail : ('HTTP ' + r.status));
        }
        return data;
    }

    function formatTime(raw) {
        if (!raw) return '—';
        return String(raw).replace('T', ' ').replace(/\.\d{3}/, '').slice(0, 19);
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function computePageNumbers(current, totalPages) {
        var max = 7;
        var start = Math.max(1, current - 3);
        var end = Math.min(totalPages, start + max - 1);
        start = Math.max(1, end - max + 1);
        var arr = [];
        for (var i = start; i <= end; i++) arr.push(i);
        return arr;
    }

    function renderPagination() {
        var wrap = document.getElementById('insurance-pagination');
        var pageInfo = document.getElementById('insurance-page-info');
        var pageNumsEl = document.getElementById('insurance-page-numbers');
        if (!wrap) return;
        if (!total) {
            wrap.classList.add('hidden');
            return;
        }
        wrap.classList.remove('hidden');
        var totalPages = Math.max(1, Math.ceil(total / pageSize));
        var curPage = page + 1;
        if (pageInfo) {
            pageInfo.innerHTML = '共 <span class="font-semibold text-[#1A1D1F]">' + total + '</span> 条，第 ' + curPage + ' / ' + totalPages + ' 页';
        }
        var prev = document.getElementById('btn-insurance-prev');
        var next = document.getElementById('btn-insurance-next');
        if (prev) prev.disabled = page <= 0;
        if (next) next.disabled = (page + 1) * pageSize >= total;
        if (!pageNumsEl) return;
        var pages = computePageNumbers(curPage, totalPages);
        pageNumsEl.innerHTML = pages.map(function (p) {
            var active = p === curPage
                ? 'border-[#456595] bg-[#456595] text-white'
                : 'border-[#D7DBE0] bg-white text-[#1A1D1F] hover:bg-[#F9FAFB]';
            return '<button type="button" class="spc-insurance-page inline-flex h-8 min-w-8 items-center justify-center rounded-[6px] border px-2 text-sm transition-colors ' + active + '" data-page="' + p + '">' + p + '</button>';
        }).join('');
    }

    function renderTable() {
        if (!tbody) return;
        renderPagination();
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="crm-td text-center text-gray-400 py-8">暂无数据</td></tr>';
            return;
        }
        var ic = icons();
        tbody.innerHTML = rows.map(function (r) {
            var ops = '<div class="crm-op-actions">'
                + opBtn('crm-op-btn-edit btn-ins-edit', '修改', 'data-id="' + r.id + '"', ic.edit)
                + (r.is_active ? opBtn('crm-op-btn-delete btn-ins-off', '停用', 'data-id="' + r.id + '"', ic.delete) : '')
                + '</div>';
            return '<tr>'
                + '<td class="crm-td crm-name-cell"><span class="crm-name-link">' + escapeHtml(r.location) + '</span></td>'
                + '<td class="crm-td text-right">' + r.social_insurance + '</td>'
                + '<td class="crm-td text-right">' + r.housing_fund + '</td>'
                + '<td class="crm-td text-center">' + r.sort_order + '</td>'
                + '<td class="crm-td">' + (r.is_active ? '启用' : '停用') + '</td>'
                + '<td class="crm-td text-xs text-gray-500">' + formatTime(r.updated_at) + '</td>'
                + '<td class="crm-td crm-sticky-right-op whitespace-nowrap">' + ops + '</td></tr>';
        }).join('');
    }

    async function resolveTotal(params, data) {
        if (data && !Array.isArray(data) && data.total != null) {
            return data.total;
        }
        var items = Array.isArray(data) ? data : (data.items || []);
        if (items.length < pageSize) {
            return page * pageSize + items.length;
        }
        var countParams = new URLSearchParams(params);
        countParams.set('limit', '500');
        countParams.set('offset', '0');
        var all = await api('/api/system/insurance-locations?' + countParams.toString());
        if (Array.isArray(all)) return all.length;
        return all.total || items.length;
    }

    async function loadRows() {
        var params = new URLSearchParams({
            limit: String(pageSize),
            offset: String(page * pageSize),
        });
        var data = await api('/api/system/insurance-locations?' + params.toString());
        rows = Array.isArray(data) ? data : (data.items || []);
        total = await resolveTotal(params, data);
        if (!rows.length && page > 0) {
            page -= 1;
            return loadRows();
        }
        renderTable();
    }

    function goPage(nextPage) {
        var totalPages = Math.max(1, Math.ceil(total / pageSize));
        page = Math.min(Math.max(0, nextPage), totalPages - 1);
        loadRows().catch(function (e) { showMsg(e.message, false); });
    }

    function openDrawer(title, html, onSave) {
        if (typeof window.spcOpenDrawer === 'function') {
            window.spcOpenDrawer(title, html, onSave);
            return;
        }
        alert('无法打开编辑面板');
    }

    function formHtml(row) {
        row = row || {};
        return ''
            + '<div><label class="block mb-1">参保地</label><input id="ins-loc" class="w-full border rounded px-3 py-2" value="' + escapeHtml(row.location || '') + '"></div>'
            + '<div class="mt-3"><label class="block mb-1">最低社保（元/月）</label><input id="ins-soc" type="number" step="0.01" min="0" class="w-full border rounded px-3 py-2" value="' + (row.social_insurance != null ? row.social_insurance : '') + '"></div>'
            + '<div class="mt-3"><label class="block mb-1">最低公积金（元/月）</label><input id="ins-hf" type="number" step="0.01" min="0" class="w-full border rounded px-3 py-2" value="' + (row.housing_fund != null ? row.housing_fund : '') + '"></div>'
            + '<div class="mt-3"><label class="block mb-1">排序</label><input id="ins-sort" type="number" min="0" class="w-full border rounded px-3 py-2" value="' + (row.sort_order != null ? row.sort_order : 0) + '"></div>'
            + (row.id ? '<div class="mt-3"><label class="inline-flex items-center gap-2"><input id="ins-active" type="checkbox" ' + (row.is_active !== false ? 'checked' : '') + '> 启用</label></div>' : '');
    }

    document.getElementById('btn-insurance-new').addEventListener('click', function () {
        openDrawer('新增参保地', formHtml({}), async function () {
            await api('/api/system/insurance-locations', {
                method: 'POST',
                body: JSON.stringify({
                    location: document.getElementById('ins-loc').value.trim(),
                    social_insurance: Number(document.getElementById('ins-soc').value),
                    housing_fund: Number(document.getElementById('ins-hf').value),
                    sort_order: Number(document.getElementById('ins-sort').value) || 0,
                    is_active: true,
                }),
            });
            page = 0;
            await loadRows();
            showMsg('已新增', true);
        });
    });

    tbody.addEventListener('click', function (ev) {
        var editBtn = ev.target.closest('.btn-ins-edit');
        var offBtn = ev.target.closest('.btn-ins-off');
        if (editBtn) {
            var id = Number(editBtn.getAttribute('data-id'));
            var row = rows.find(function (x) { return x.id === id; });
            if (!row) return;
            openDrawer('编辑参保地', formHtml(row), async function () {
                await api('/api/system/insurance-locations/' + id, {
                    method: 'PUT',
                    body: JSON.stringify({
                        location: document.getElementById('ins-loc').value.trim(),
                        social_insurance: Number(document.getElementById('ins-soc').value),
                        housing_fund: Number(document.getElementById('ins-hf').value),
                        sort_order: Number(document.getElementById('ins-sort').value) || 0,
                        is_active: document.getElementById('ins-active').checked,
                    }),
                });
                await loadRows();
                showMsg('已保存', true);
            });
        }
        if (offBtn) {
            var rid = Number(offBtn.getAttribute('data-id'));
            if (!confirm('确定停用该参保地？')) return;
            api('/api/system/insurance-locations/' + rid, { method: 'DELETE' })
                .then(loadRows)
                .then(function () { showMsg('已停用', true); })
                .catch(function (e) { showMsg(e.message, false); });
        }
    });

    document.getElementById('btn-insurance-prev').addEventListener('click', function () {
        if (page <= 0) return;
        goPage(page - 1);
    });
    document.getElementById('btn-insurance-next').addEventListener('click', function () {
        if ((page + 1) * pageSize >= total) return;
        goPage(page + 1);
    });
    document.getElementById('insurance-pagination').addEventListener('click', function (ev) {
        var btn = ev.target.closest('.spc-insurance-page');
        if (!btn) return;
        goPage(parseInt(btn.getAttribute('data-page'), 10) - 1);
    });

    window.loadGmInsuranceAdmin = function () {
        page = 0;
        return loadRows();
    };
})();
