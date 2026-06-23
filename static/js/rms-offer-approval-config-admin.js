(function () {
    'use strict';

    var panel = document.getElementById('panel-offerApproval');
    if (!panel) return;

    var root = document.getElementById('permission-center-app');
    var CAN = root && root.getAttribute('data-can-users') === '1';
    if (!CAN) return;

    var users = [];
    var depts = [];
    var config = { default: null, dept_overrides: [] };

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

    function escapeHtml(s) {
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function userLabel(uid) {
        if (uid == null || uid === '') return '—';
        var u = users.find(function (x) { return x.id === uid; });
        if (!u) return String(uid);
        return (u.display_name || u.username || String(uid));
    }

    function userOptionsHtml(selected) {
        var sel = selected != null && selected !== '' ? String(selected) : '';
        var html = '<option value="">— 未设置 —</option>';
        users.forEach(function (u) {
            if ((u.status || 'active') !== 'active') return;
            var on = String(u.id) === sel ? ' selected' : '';
            var label = (u.display_name || u.username || u.id);
            html += '<option value="' + u.id + '"' + on + '>' + escapeHtml(label) + '</option>';
        });
        return html;
    }

    function readSelect(id) {
        var el = document.getElementById(id);
        if (!el || !el.value) return null;
        return Number(el.value);
    }

    function fillDefaultForm(row) {
        row = row || {};
        document.getElementById('oac-default-dept-superior').innerHTML = userOptionsHtml(row.dept_superior_user_id);
        document.getElementById('oac-default-ops-head').innerHTML = userOptionsHtml(row.ops_head_user_id);
        document.getElementById('oac-default-gm').innerHTML = userOptionsHtml(row.gm_user_id);
    }

    function renderDeptTable() {
        var tbody = document.getElementById('oac-dept-tbody');
        if (!tbody) return;
        var ic = window.SPC_ICONS || {};
        var opBtn = window.spcOpBtn || function (cls, label, attrs, icon) {
            return '<button type="button" class="' + cls + '" ' + (attrs || '') + '>' + label + '</button>';
        };
        var rows = config.dept_overrides || [];
        if (!rows.length) {
            tbody.innerHTML = '<tr><td class="crm-td text-gray-500" colspan="5">暂无部门覆盖，将使用默认审批链</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            var deptLabel = escapeHtml(r.dept_name || ('部门 #' + r.dept_id));
            var ops = '<div class="crm-op-actions">'
                + opBtn('crm-op-btn-edit btn-oac-edit', '修改', 'data-dept-id="' + r.dept_id + '"', ic.edit || '')
                + opBtn('crm-op-btn-delete btn-oac-delete', '删除', 'data-dept-id="' + r.dept_id + '"', ic.delete || '')
                + '</div>';
            return '<tr data-dept-id="' + r.dept_id + '">'
                + '<td class="crm-td crm-name-cell"><span class="crm-name-link">' + deptLabel + '</span></td>'
                + '<td class="crm-td">' + escapeHtml(userLabel(r.dept_superior_user_id)) + '</td>'
                + '<td class="crm-td">' + escapeHtml(userLabel(r.ops_head_user_id)) + '</td>'
                + '<td class="crm-td">' + escapeHtml(userLabel(r.gm_user_id)) + '</td>'
                + '<td class="crm-td crm-sticky-right-op whitespace-nowrap">' + ops + '</td></tr>';
        }).join('');
    }

    async function ensureLookups() {
        if (!users.length) {
            var userData = await api('/api/system/users?limit=0');
            users = userData.items || userData.users || userData || [];
            if (!Array.isArray(users) && userData.items) users = userData.items;
            if (!Array.isArray(users)) users = [];
        }
        if (!depts.length) {
            depts = await api('/api/system/depts');
            if (!Array.isArray(depts)) depts = [];
        }
    }

    async function loadConfig() {
        await ensureLookups();
        config = await api('/api/rms/offer-approval-config');
        fillDefaultForm(config.default || {});
        renderDeptTable();
    }

    function deptOverrideFormHtml(row) {
        row = row || {};
        var deptOpts = depts.map(function (d) {
            var on = row.dept_id === d.id ? ' selected' : '';
            return '<option value="' + d.id + '"' + on + '>' + escapeHtml(d.name) + '</option>';
        }).join('');
        return ''
            + '<div><label class="block mb-1">部门</label>'
            + '<select id="oac-form-dept" class="w-full border rounded px-3 py-2"' + (row.dept_id ? ' disabled' : '') + '>'
            + '<option value="">请选择部门</option>' + deptOpts + '</select></div>'
            + '<div class="mt-3"><label class="block mb-1">部门上级</label>'
            + '<select id="oac-form-dept-superior" class="w-full border rounded px-3 py-2">' + userOptionsHtml(row.dept_superior_user_id) + '</select></div>'
            + '<div class="mt-3"><label class="block mb-1">经营负责人</label>'
            + '<select id="oac-form-ops-head" class="w-full border rounded px-3 py-2">' + userOptionsHtml(row.ops_head_user_id) + '</select></div>'
            + '<div class="mt-3"><label class="block mb-1">总经理</label>'
            + '<select id="oac-form-gm" class="w-full border rounded px-3 py-2">' + userOptionsHtml(row.gm_user_id) + '</select></div>'
            + '<p class="mt-3 text-xs text-gray-500">留空字段将回退到默认审批链配置。</p>';
    }

    function readOverridePayload() {
        return {
            dept_superior_user_id: readSelect('oac-form-dept-superior'),
            ops_head_user_id: readSelect('oac-form-ops-head'),
            gm_user_id: readSelect('oac-form-gm'),
        };
    }

    function openDrawer(title, html, onSave) {
        if (typeof window.spcOpenDrawer === 'function') {
            window.spcOpenDrawer(title, html, onSave);
            return;
        }
        alert('无法打开编辑面板');
    }

    document.getElementById('btn-oac-save-default').addEventListener('click', function () {
        api('/api/rms/offer-approval-config/default', {
            method: 'PUT',
            body: JSON.stringify({
                dept_superior_user_id: readSelect('oac-default-dept-superior'),
                ops_head_user_id: readSelect('oac-default-ops-head'),
                gm_user_id: readSelect('oac-default-gm'),
            }),
        }).then(function () {
            return loadConfig();
        }).then(function () {
            showMsg('默认审批链已保存', true);
        }).catch(function (e) {
            showMsg(e.message, false);
        });
    });

    document.getElementById('btn-oac-add-dept').addEventListener('click', function () {
        ensureLookups().then(function () {
            openDrawer('新增部门覆盖', deptOverrideFormHtml({}), async function () {
                var deptEl = document.getElementById('oac-form-dept');
                var deptId = deptEl ? Number(deptEl.value) : 0;
                if (!deptId) throw new Error('请选择部门');
                await api('/api/rms/offer-approval-config/depts/' + deptId, {
                    method: 'PUT',
                    body: JSON.stringify(readOverridePayload()),
                });
                await loadConfig();
                showMsg('部门覆盖已保存', true);
            });
        }).catch(function (e) {
            showMsg(e.message, false);
        });
    });

    document.getElementById('oac-dept-tbody').addEventListener('click', function (ev) {
        var editBtn = ev.target.closest('.btn-oac-edit');
        var delBtn = ev.target.closest('.btn-oac-delete');
        var tr = ev.target.closest('tr[data-dept-id]');
        if (!tr) return;
        var deptId = Number(tr.getAttribute('data-dept-id'));
        var row = (config.dept_overrides || []).find(function (x) { return x.dept_id === deptId; });
        if (editBtn && row) {
            openDrawer('编辑部门覆盖', deptOverrideFormHtml(row), async function () {
                await api('/api/rms/offer-approval-config/depts/' + deptId, {
                    method: 'PUT',
                    body: JSON.stringify(readOverridePayload()),
                });
                await loadConfig();
                showMsg('部门覆盖已保存', true);
            });
            return;
        }
        if (delBtn) {
            if (!window.confirm('确定删除该部门的审批链覆盖？')) return;
            api('/api/rms/offer-approval-config/depts/' + deptId, { method: 'DELETE' })
                .then(function () { return loadConfig(); })
                .then(function () { showMsg('已删除部门覆盖', true); })
                .catch(function (e) { showMsg(e.message, false); });
        }
    });

    window.loadRmsOfferApprovalConfigAdmin = function () {
        loadConfig().catch(function (e) {
            showMsg(e.message, false);
        });
    };
})();
