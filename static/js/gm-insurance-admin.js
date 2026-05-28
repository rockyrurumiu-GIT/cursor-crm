(function () {
    'use strict';

    var panel = document.getElementById('panel-insurance');
    if (!panel) return;

    var CAN = document.getElementById('permission-center-app').getAttribute('data-can-insurance') === '1';
    if (!CAN) return;

    var tbody = document.getElementById('insurance-tbody');
    var rows = [];

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

    function renderTable() {
        if (!tbody) return;
        tbody.innerHTML = rows.map(function (r) {
            return '<tr>'
                + '<td class="crm-td">' + escapeHtml(r.location) + '</td>'
                + '<td class="crm-td text-right">' + r.social_insurance + '</td>'
                + '<td class="crm-td text-right">' + r.housing_fund + '</td>'
                + '<td class="crm-td text-center">' + r.sort_order + '</td>'
                + '<td class="crm-td">' + (r.is_active ? '启用' : '停用') + '</td>'
                + '<td class="crm-td text-xs text-gray-500">' + formatTime(r.updated_at) + '</td>'
                + '<td class="crm-td">'
                + '<button type="button" class="text-blue-600 hover:underline mr-2 btn-ins-edit" data-id="' + r.id + '">编辑</button>'
                + (r.is_active ? '<button type="button" class="text-red-600 hover:underline btn-ins-off" data-id="' + r.id + '">停用</button>' : '')
                + '</td></tr>';
        }).join('');
    }

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    async function loadRows() {
        rows = await api('/api/system/insurance-locations');
        renderTable();
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

    window.loadGmInsuranceAdmin = loadRows;
})();
