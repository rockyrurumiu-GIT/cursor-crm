(function () {
    'use strict';

    var root = document.getElementById('permission-center-app');
    if (!root) return;

    var CAN_USERS = root.getAttribute('data-can-users') === '1';
    var CAN_ROLES = root.getAttribute('data-can-roles') === '1';
    var CAN_AUDIT = root.getAttribute('data-can-audit') === '1';
    var CAN_INSURANCE = root.getAttribute('data-can-insurance') === '1';
    var IS_SUPER = root.getAttribute('data-is-super') === '1';
    var CAN_DELETE_USERS = IS_SUPER || !window.crmHasPermission || window.crmHasPermission('system.users.delete');
    var CAN_DELETE_ROLES = IS_SUPER || !window.crmHasPermission || window.crmHasPermission('system.roles.delete');
    var BUILTIN_DEPT_CODES = { ROOT: 1, SALES: 1, DELIVERY: 1, FINANCE: 1, ADMIN: 1 };

    var SPC_ICONS = {
        edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
        delete: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>',
        key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
        enable: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 11l-3 3-2-2"/></svg>',
        matrix: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    };

    function spcOpBtn(cls, label, attrs, icon) {
        return '<span class="group relative inline-flex">'
            + '<button type="button" class="' + cls + '" aria-label="' + label + '" ' + (attrs || '') + '>' + icon + '</button>'
            + '<span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#1A1D1F] px-2 py-1 text-xs text-white opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100">' + label + '</span>'
            + '</span>';
    }

    function computePageNumbers(current, total) {
        var max = 7;
        var start = Math.max(1, current - 3);
        var end = Math.min(total, start + max - 1);
        start = Math.max(1, end - max + 1);
        var arr = [];
        for (var i = start; i <= end; i++) arr.push(i);
        return arr;
    }

    function toggleFilterPanel(btnId, panelId) {
        var btn = document.getElementById(btnId);
        var panel = document.getElementById(panelId);
        if (!btn || !panel) return;
        var open = panel.classList.toggle('hidden') === false;
        btn.classList.toggle('border-[#16A39A]', open);
        btn.classList.toggle('text-[#16A39A]', open);
        btn.classList.toggle('border-[#D7DBE0]', !open);
        btn.classList.toggle('text-[#1A1D1F]', !open);
    }

    function clearUserFilters() {
        var search = document.getElementById('user-search');
        var roleSel = document.getElementById('batch-role-select');
        var modeSel = document.getElementById('batch-role-mode');
        if (search) search.value = '';
        if (roleSel) roleSel.value = '';
        if (modeSel) modeSel.value = 'replace';
        state.userPage = 0;
        loadUsers().catch(function (e) { showMsg(e.message, false); });
    }

    function clearRoleFilters() {
        var search = document.getElementById('role-search');
        if (search) search.value = '';
        renderRolesTable();
    }

    function clearDeptFilters() {
        var search = document.getElementById('dept-search');
        if (search) search.value = '';
        renderDeptsList();
    }

    function clearAuditFilters() {
        ['audit-keyword', 'audit-from', 'audit-to'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.value = '';
        });
        ['audit-actor', 'audit-action', 'audit-level'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.value = '';
        });
        state.auditPage = 0;
        loadAudit().catch(function (e) { showMsg(e.message, false); });
    }

    var state = {
        users: [],
        usersTotal: 0,
        userPage: 0,
        userPageSize: 10,
        userSearchTimer: null,
        selectedUserIds: new Set(),
        roles: [],
        matrixData: null,
        matrixReadonly: false,
        dataScopeData: null,
        dataScopeReadonly: false,
        depts: [],
        drawerMode: null,
        drawerUserId: null,
        auditLogs: [],
        auditTotal: 0,
        auditPage: 0,
        auditPageSize: 10,
    };

    function buildHeaders(withJson) {
        var h = Object.assign({}, window.crmAuthHeader());
        if (withJson) h['Content-Type'] = 'application/json';
        return h;
    }

    function showMsg(text, ok) {
        var el = document.getElementById('spc-global-msg');
        if (!el) return;
        el.textContent = text;
        el.classList.remove('hidden', 'text-red-600', 'text-green-700');
        el.classList.add(ok ? 'text-green-700' : 'text-red-600');
    }

    function formatSpcDateTime(raw) {
        if (raw == null || raw === '') return '—';
        var s = String(raw).trim();
        if (!s) return '—';
        var d = new Date(s);
        if (Number.isNaN(d.getTime())) {
            return s.replace('T', ' ').replace(/Z$/i, '').replace(/\.\d{3}$/, '');
        }
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return d.getFullYear() + '-'
            + pad(d.getMonth() + 1) + '-'
            + pad(d.getDate()) + ' '
            + pad(d.getHours()) + ':'
            + pad(d.getMinutes()) + ':'
            + pad(d.getSeconds());
    }

    function formatSpcDateOnly(raw) {
        if (raw == null || raw === '') return '—';
        var s = String(raw).trim();
        if (!s) return '—';
        var d = new Date(s);
        if (Number.isNaN(d.getTime())) {
            var normalized = s.replace('T', ' ').replace(/Z$/i, '').replace(/\.\d{3}$/, '');
            return normalized.length >= 10 ? normalized.slice(0, 10) : normalized;
        }
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }

    function clearMsg() {
        var el = document.getElementById('spc-global-msg');
        if (!el) return;
        el.textContent = '';
        el.classList.add('hidden');
    }

    function escAttr(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/</g, '&lt;');
    }

    function escHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function syncDrawerFooter(readOnly) {
        var saveBtn = document.getElementById('drawer-save');
        var cancelBtn = document.getElementById('drawer-cancel');
        if (saveBtn) saveBtn.classList.toggle('hidden', !!readOnly);
        if (cancelBtn) cancelBtn.textContent = readOnly ? '关闭' : '取消';
    }

    async function api(path, opts) {
        opts = opts || {};
        var hasBody = opts.body != null && opts.body !== '';
        var r = await fetch(path, Object.assign({
            credentials: 'same-origin',
            headers: buildHeaders(hasBody),
        }, opts));
        var data = await r.json().catch(function () { return {}; });
        if (!r.ok) {
            var detail = data.detail;
            if (typeof detail !== 'string' && r.status === 405) {
                detail = 'Method Not Allowed（请重启后端服务，或当前环境不支持该 HTTP 方法）';
            }
            throw new Error(typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : ('HTTP ' + r.status)));
        }
        return data;
    }

    async function apiDelete(path) {
        try {
            await api(path, { method: 'DELETE' });
        } catch (e) {
            var msg = String(e.message || '').toLowerCase();
            if (msg.indexOf('method not allowed') < 0 && msg.indexOf('405') < 0) {
                throw e;
            }
            await api(path + '/delete', { method: 'POST' });
        }
    }

    function runTabLoad(fn) {
        Promise.resolve().then(fn).catch(function (e) {
            showMsg(e.message, false);
        });
    }

    function switchTab(name) {
        clearMsg();
        document.querySelectorAll('.spc-tab').forEach(function (btn) {
            btn.classList.toggle('active', btn.getAttribute('data-tab') === name);
        });
        document.querySelectorAll('.spc-panel').forEach(function (p) {
            p.classList.add('hidden');
        });
        var panel = document.getElementById('panel-' + name);
        if (panel) panel.classList.remove('hidden');
        if (name === 'users' && CAN_USERS) runTabLoad(loadUsers);
        if (name === 'roles' && CAN_ROLES) runTabLoad(loadRoles);
        if (name === 'matrix' && CAN_ROLES) runTabLoad(loadMatrixTab);
        if (name === 'datascope' && CAN_ROLES) runTabLoad(loadDataScopeTab);
        if (name === 'preview' && CAN_USERS) runTabLoad(loadPreviewTab);
        if (name === 'depts' && CAN_USERS) runTabLoad(loadDeptsTab);
        if (name === 'offerApproval' && CAN_USERS && typeof window.loadRmsOfferApprovalConfigAdmin === 'function') {
            window.loadRmsOfferApprovalConfigAdmin();
        }
        if (name === 'audit' && CAN_AUDIT) runTabLoad(function () {
            state.auditPage = 0;
            return loadAuditFilterOptions()
                .catch(function () { /* 筛选项加载失败不阻断列表 */ })
                .then(function () { return loadAudit(); });
        });
        if (name === 'insurance' && CAN_INSURANCE && typeof window.loadGmInsuranceAdmin === 'function') {
            window.loadGmInsuranceAdmin();
        }
    }

    function openDrawer(title, html, onSave) {
        var chatShell = document.getElementById('handbook-assistant');
        state._chatbotWasVisible = !!(chatShell && !chatShell.classList.contains('hidden'));
        if (window.crmHideHandbookAssistant) {
            window.crmHideHandbookAssistant();
        }
        document.getElementById('drawer-title').textContent = title;
        document.getElementById('drawer-body').innerHTML = html;
        document.getElementById('spc-drawer-backdrop').classList.remove('hidden');
        document.getElementById('spc-drawer').classList.add('open');
        state._drawerSave = onSave || null;
        syncDrawerFooter(!onSave);
    }

    function closeDrawer() {
        document.getElementById('spc-drawer-backdrop').classList.add('hidden');
        document.getElementById('spc-drawer').classList.remove('open');
        state._drawerSave = null;
        if (state._chatbotWasVisible) {
            var chatShell = document.getElementById('handbook-assistant');
            if (chatShell) {
                chatShell.classList.remove('hidden');
            }
        }
        state._chatbotWasVisible = false;
    }

    function roleOptionsHtml(selected) {
        var sel = selected || [];
        return state.roles.map(function (r) {
            var on = sel.indexOf(r.code) >= 0 ? ' selected' : '';
            return '<option value="' + r.code + '"' + on + '>' + (r.name || r.code) + '</option>';
        }).join('');
    }

    function roleCheckboxesHtml(selectedCodes) {
        var sel = selectedCodes || [];
        if (!state.roles.length) {
            return '<p class="text-gray-400 text-xs">暂无角色</p>';
        }
        return '<div class="spc-check-group border rounded-lg px-3 py-2 max-h-[160px] overflow-y-auto space-y-1">'
            + state.roles.map(function (r) {
                var on = sel.indexOf(r.code) >= 0 ? ' checked' : '';
                return '<label class="flex items-center gap-2 cursor-pointer">'
                    + '<input type="checkbox" class="d-role-check" value="' + r.code + '"' + on + '>'
                    + '<span>' + (r.name || r.code) + '</span></label>';
            }).join('')
            + '</div>';
    }

    function deptCheckboxesHtml(selectedIds) {
        var sel = selectedIds || [];
        if (!state.depts.length) {
            return '<p class="text-gray-400 text-xs">暂无部门，请先在「部门管理」中创建</p>';
        }
        return '<div class="spc-check-group border rounded-lg px-3 py-2 max-h-[160px] overflow-y-auto space-y-1">'
            + state.depts.map(function (d) {
                var on = sel.indexOf(d.id) >= 0 ? ' checked' : '';
                return '<label class="flex items-center gap-2 cursor-pointer">'
                    + '<input type="checkbox" class="d-dept-check" value="' + d.id + '"' + on + '>'
                    + '<span>' + d.name + ' (' + d.code + ')</span></label>';
            }).join('')
            + '</div>';
    }

    function collectCheckedRoleCodes() {
        return Array.from(document.querySelectorAll('.d-role-check:checked')).map(function (el) {
            return el.value;
        });
    }

    function collectCheckedDeptIds() {
        return Array.from(document.querySelectorAll('.d-dept-check:checked')).map(function (el) {
            return parseInt(el.value, 10);
        });
    }

    function syncBatchRoleUi() {
        var hasSel = state.selectedUserIds.size > 0;
        var batchWrap = document.getElementById('user-batch-wrap');
        if (batchWrap) batchWrap.classList.toggle('hidden', !hasSel || !CAN_USERS);
        var sel = document.getElementById('batch-role-select');
        if (sel && !sel.options.length && state.roles.length) {
            sel.innerHTML = state.roles.map(function (r) {
                return '<option value="' + r.code + '">' + (r.name || r.code) + '</option>';
            }).join('');
        }
    }

    function goUserPage(page) {
        var totalPages = Math.max(1, Math.ceil(state.usersTotal / state.userPageSize));
        state.userPage = Math.min(Math.max(0, page), totalPages - 1);
        loadUsers().catch(function (e) { showMsg(e.message, false); });
    }

    function renderUserPagination() {
        var wrap = document.getElementById('user-pagination');
        var pageInfo = document.getElementById('user-page-info');
        var countNum = document.getElementById('user-count-num');
        var pageNumsEl = document.getElementById('user-page-numbers');
        var total = state.usersTotal;
        if (countNum) countNum.textContent = String(total);
        if (!wrap) return;
        if (!total) {
            wrap.classList.add('hidden');
            return;
        }
        wrap.classList.remove('hidden');
        var totalPages = Math.max(1, Math.ceil(total / state.userPageSize));
        var curPage = state.userPage + 1;
        if (pageInfo) {
            pageInfo.innerHTML = '共 <span class="font-semibold text-[#1A1D1F]">' + total + '</span> 条，第 ' + curPage + ' / ' + totalPages + ' 页';
        }
        var prev = document.getElementById('btn-user-prev');
        var next = document.getElementById('btn-user-next');
        if (prev) prev.disabled = state.userPage <= 0;
        if (next) next.disabled = (state.userPage + 1) * state.userPageSize >= total;
        if (!pageNumsEl) return;
        var pages = computePageNumbers(curPage, totalPages);
        pageNumsEl.innerHTML = pages.map(function (p) {
            var active = p === curPage
                ? 'border-[#456595] bg-[#456595] text-white'
                : 'border-[#D7DBE0] bg-white text-[#1A1D1F] hover:bg-[#F9FAFB]';
            return '<button type="button" class="spc-user-page inline-flex h-8 min-w-8 items-center justify-center rounded-[6px] border px-2 text-sm transition-colors ' + active + '" data-page="' + p + '">' + p + '</button>';
        }).join('');
    }

    async function loadUsers() {
        if (!CAN_USERS) return;
        if (!state.roles.length) await loadRoles();
        var q = (document.getElementById('user-search').value || '').trim();
        var params = new URLSearchParams({
            q: q,
            limit: String(state.userPageSize),
            offset: String(state.userPage * state.userPageSize),
        });
        var data = await api('/api/system/users?' + params.toString());
        state.users = data.items || [];
        state.usersTotal = data.total || 0;
        renderUsers();
        syncBatchRoleUi();
    }

    function renderUsers() {
        var tbody = document.getElementById('users-tbody');
        var rows = state.users;
        renderUserPagination();
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="crm-td text-center text-gray-400 py-8">暂无数据</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (u) {
            var deptLabel = (u.depts || []).map(function (d) { return d.name; }).join('、') || '—';
            var chips = (u.role_labels || u.roles || []).map(function (lbl) {
                return '<span class="spc-chip">' + lbl + '</span>';
            }).join(' ');
            var mcp = u.must_change_password ? ' <span class="text-amber-700 text-xs">须改密</span>' : '';
            var checked = state.selectedUserIds.has(u.id) ? ' checked' : '';
            var ops = CAN_USERS
                ? '<div class="crm-op-actions">'
                + spcOpBtn('crm-op-btn-edit btn-edit-user', '修改', 'data-id="' + u.id + '"', SPC_ICONS.edit)
                + spcOpBtn('crm-op-btn-handoff btn-reset-pwd', '重置密码', 'data-id="' + u.id + '"', SPC_ICONS.key)
                + (u.status === 'active'
                    ? spcOpBtn('crm-op-btn-delete btn-disable-user', '禁用', 'data-id="' + u.id + '"', SPC_ICONS.delete)
                    : spcOpBtn('crm-op-btn-edit btn-enable-user', '启用', 'data-id="' + u.id + '"', SPC_ICONS.enable))
                + '</div>'
                : '';
            return '<tr data-user-id="' + u.id + '">'
                + '<td class="crm-td spc-users-sticky-lead crm-name-cell">'
                + '<div class="spc-users-lead-inner">'
                + '<input type="checkbox" class="user-row-check shrink-0" data-id="' + u.id + '"' + checked + '>'
                + '<span class="min-w-0"><button type="button" class="crm-name-link btn-detail-user" data-id="' + u.id + '">' + escHtml(u.username) + '</button>' + mcp + '</span>'
                + '</div></td>'
                + '<td class="crm-td">' + (u.display_name || '') + '</td>'
                + '<td class="crm-td">' + u.status + '</td>'
                + '<td class="crm-td text-gray-600"><span class="block truncate" title="' + escAttr(deptLabel) + '">' + escHtml(deptLabel) + '</span></td>'
                + '<td class="crm-td">' + chips + '</td>'
                + '<td class="crm-td text-gray-500 whitespace-nowrap">' + formatSpcDateTime(u.last_login_at) + '</td>'
                + '<td class="crm-td text-gray-500 whitespace-nowrap">' + formatSpcDateOnly(u.created_at) + '</td>'
                + '<td class="crm-td crm-sticky-right-op crm-op-col-xl whitespace-nowrap">' + ops + '</td></tr>';
        }).join('');
    }

    async function ensureDepts(force) {
        if ((state.depts.length && !force) || !CAN_USERS) return;
        state.depts = await api('/api/system/depts');
    }

    function deptNameById(deptId) {
        var d = state.depts.find(function (x) { return x.id === deptId; });
        return d ? (d.name + ' (' + d.code + ')') : '—';
    }

    function deptTypeLabel(t) {
        return {
            general: '通用',
            business: '业务',
            functional: '职能',
            sales: '业务',
            delivery: '业务',
            finance: '职能',
        }[t] || t || '—';
    }

    async function loadDeptsTab() {
        if (!CAN_USERS) return;
        await ensureDepts(true);
        renderDeptsList();
    }

    function filteredDepts() {
        var q = (document.getElementById('dept-search') && document.getElementById('dept-search').value || '').trim().toLowerCase();
        return state.depts.filter(function (d) {
            if (!q) return true;
            return (d.name || '').toLowerCase().indexOf(q) >= 0
                || (d.code || '').toLowerCase().indexOf(q) >= 0;
        });
    }

    function boundUsersCountCell(item) {
        var users = item.bound_users || [];
        var count = item.user_count != null ? item.user_count : users.length;
        if (!count) return '<span class="text-gray-400">0</span>';
        var labels = users.map(function (u) {
            return escHtml(u.display_name || u.username);
        }).join('、');
        return '<span class="group relative inline-flex cursor-help">'
            + '<span class="font-medium tabular-nums text-[#1A1D1F]">' + count + '</span>'
            + '<span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 w-max max-w-[240px] -translate-x-1/2 whitespace-normal rounded-md bg-[#1A1D1F] px-2 py-1 text-left text-xs text-white opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100">' + labels + '</span>'
            + '</span>';
    }

    function renderDeptsList() {
        var tbody = document.getElementById('depts-tbody');
        if (!tbody) return;
        var rows = filteredDepts();
        var countNum = document.getElementById('dept-count-num');
        if (countNum) countNum.textContent = String(rows.length);
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="crm-td text-center text-gray-400 py-8">暂无部门</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (d) {
            var builtin = BUILTIN_DEPT_CODES[d.code];
            var typeCell = deptTypeLabel(d.dept_type)
                + (builtin ? ' <span class="text-xs text-gray-400">内置</span>' : '');
            var ops = '<div class="crm-op-actions">'
                + spcOpBtn('crm-op-btn-edit btn-edit-dept', '修改', 'data-id="' + d.id + '"', SPC_ICONS.edit)
                + (builtin || !CAN_DELETE_USERS ? '' : spcOpBtn('crm-op-btn-delete btn-delete-dept', '删除', 'data-id="' + d.id + '"'
                + ' data-crm-delete-title="确认删除部门"'
                + ' data-crm-delete-target="将删除部门：' + String(d.name || '').replace(/"/g, '&quot;') + '"'
                + ' data-crm-delete-hint="若仍有用户或客户归属将无法删除。"', SPC_ICONS.delete))
                + '</div>';
            var parentLabel = d.parent_id ? deptNameById(d.parent_id) : '—';
            var headLabel = d.head_user ? (d.head_user.display_name || d.head_user.username) : '—';
            return '<tr data-dept-id="' + d.id + '">'
                + '<td class="crm-td crm-name-cell spc-dept-sticky-name"><button type="button" class="crm-name-link btn-detail-dept block w-full truncate text-left" title="' + escAttr(d.name) + '" data-id="' + d.id + '">' + escHtml(d.name) + '</button></td>'
                + '<td class="crm-td">' + typeCell + '</td>'
                + '<td class="crm-td text-gray-600"><span class="block truncate" title="' + escAttr(parentLabel) + '">' + escHtml(parentLabel) + '</span></td>'
                + '<td class="crm-td text-gray-600"><span class="block truncate" title="' + escAttr(headLabel) + '">' + escHtml(headLabel) + '</span></td>'
                + '<td class="crm-td spc-bound-users-cell">' + boundUsersCountCell(d) + '</td>'
                + '<td class="crm-td">' + escHtml(d.status) + '</td>'
                + '<td class="crm-td text-gray-600 font-mono text-xs">' + escHtml(d.code) + '</td>'
                + '<td class="crm-td crm-sticky-right-op whitespace-nowrap">' + ops + '</td></tr>';
        }).join('');
    }

    function deptParentOptionsHtml(selectedId, excludeId) {
        return state.depts
            .filter(function (d) { return d.id !== excludeId; })
            .map(function (d) {
                var on = selectedId === d.id ? ' selected' : '';
                return '<option value="' + d.id + '"' + on + '>' + d.name + ' (' + d.code + ')</option>';
            }).join('');
    }

    function deptHeadUserOptionsHtml(users, selectedId, selectedUser) {
        var html = '<option value="">— 未设置 —</option>';
        var selectedIncluded = false;
        (users || []).forEach(function (u) {
            var isSelected = selectedId != null && String(u.id) === String(selectedId);
            if ((u.status || 'active') !== 'active' && !isSelected) return;
            if (isSelected) selectedIncluded = true;
            var on = isSelected ? ' selected' : '';
            html += '<option value="' + u.id + '"' + on + '>' + escHtml(u.display_name || u.username) + '</option>';
        });
        if (selectedId != null && !selectedIncluded) {
            var label = selectedUser ? (selectedUser.display_name || selectedUser.username) : ('#' + selectedId);
            html += '<option value="' + selectedId + '" selected>' + escHtml(label) + '</option>';
        }
        return html;
    }

    function openDeptDetailDrawer(dept) {
        if (!dept) return;
        var parentLabel = dept.parent_id ? deptNameById(dept.parent_id) : '无（顶级）';
        var headLabel = dept.head_user ? (dept.head_user.display_name || dept.head_user.username) : '—';
        var users = dept.bound_users || [];
        var userCount = dept.user_count != null ? dept.user_count : users.length;
        var usersHtml = users.length
            ? users.map(function (u) {
                return '<span class="spc-chip">' + escHtml(u.display_name || u.username) + '</span>';
            }).join('')
            : '<span class="text-sm text-[#9AA0A6]">暂无绑定用户</span>';
        var builtin = BUILTIN_DEPT_CODES[dept.code];
        var html = ''
            + '<div class="spc-user-detail space-y-5">'
            + '<div class="rounded-lg border border-[#EEF0F2] bg-[#F9FAFB] p-4">'
            + '<div class="flex items-start justify-between gap-3">'
            + '<div class="min-w-0">'
            + '<p class="text-lg font-semibold text-[#1A1D1F]">' + escHtml(dept.name) + '</p>'
            + '<p class="mt-0.5 text-sm font-mono text-[#6B7280]">' + escHtml(dept.code) + '</p>'
            + '</div>'
            + userStatusBadgeHtml(dept.status === 'active' ? 'active' : 'disabled')
            + '</div>'
            + (builtin ? '<p class="mt-2 text-xs text-gray-500">内置部门</p>' : '')
            + '</div>'
            + '<section>'
            + '<p class="spc-detail-section-title mb-2">基本信息</p>'
            + '<dl class="spc-detail-grid mt-2">'
            + '<div class="spc-detail-field"><dt>类型</dt><dd>' + escHtml(deptTypeLabel(dept.dept_type)) + '</dd></div>'
            + '<div class="spc-detail-field"><dt>上级部门</dt><dd>' + escHtml(parentLabel) + '</dd></div>'
            + '<div class="spc-detail-field"><dt>部门主管</dt><dd>' + escHtml(headLabel) + '</dd></div>'
            + '<div class="spc-detail-field"><dt>路径</dt><dd class="font-mono text-xs">' + escHtml(dept.path || '—') + '</dd></div>'
            + '</dl>'
            + '</section>'
            + '<section class="pt-4 border-t border-[#EEF0F2]">'
            + '<p class="spc-detail-section-title mb-3">绑定用户'
            + ' <span class="font-normal text-[#6B7280]">（' + userCount + ' 人）</span></p>'
            + '<div class="flex flex-wrap gap-1.5">' + usersHtml + '</div>'
            + '</section>'
            + '</div>';
        openDrawer('部门详情 · ' + dept.name, html, null);
    }

    function openDeptDrawer(mode, dept, users) {
        var isNew = mode === 'create';
        var parentId = dept ? dept.parent_id : null;
        var headId = dept ? (dept.head_user_id != null ? dept.head_user_id : (dept.head_user ? dept.head_user.id : null)) : null;
        var html = ''
            + (isNew
                ? '<div><label class="block text-gray-600 mb-1">部门编码</label>'
                    + '<input id="d-dept-code" class="w-full border rounded-lg px-3 py-2" placeholder="如 KEY_DELIV"></div>'
                : '<div class="text-sm text-gray-500 mb-2">编码：<span class="font-mono">' + dept.code + '</span>（不可修改）</div>')
            + '<div><label class="block text-gray-600 mb-1">部门名称</label>'
            + '<input id="d-dept-name" class="w-full border rounded-lg px-3 py-2" value="' + (dept ? (dept.name || '') : '') + '"></div>'
            + (isNew
                ? '<div><label class="block text-gray-600 mb-1">上级部门</label>'
                    + '<select id="d-dept-parent" class="w-full border rounded-lg px-3 py-2">'
                    + '<option value="">无（顶级）</option>' + deptParentOptionsHtml(parentId, null) + '</select></div>'
                : '')
            + '<div><label class="block text-gray-600 mb-1">部门主管</label>'
            + '<select id="d-dept-head" class="w-full border rounded-lg px-3 py-2">'
            + deptHeadUserOptionsHtml(users, headId) + '</select></div>'
            + '<div><label class="block text-gray-600 mb-1">部门类型</label>'
            + '<select id="d-dept-type" class="w-full border rounded-lg px-3 py-2">'
            + ['general', 'business', 'functional'].map(function (t) {
                var cur = dept ? dept.dept_type : 'general';
                return '<option value="' + t + '"' + (cur === t ? ' selected' : '') + '>' + deptTypeLabel(t) + '</option>';
            }).join('')
            + '</select></div>'
            + (!isNew
                ? '<div class="mt-3"><label class="block text-gray-600 mb-1">状态</label>'
                    + '<select id="d-dept-status" class="w-full border rounded-lg px-3 py-2">'
                    + '<option value="active"' + ((dept && dept.status === 'active') ? ' selected' : '') + '>启用</option>'
                    + '<option value="disabled"' + ((dept && dept.status === 'disabled') ? ' selected' : '') + '>停用</option>'
                    + '</select></div>'
                : '');
        openDrawer(isNew ? '新建部门' : '编辑部门 · ' + dept.name, html, async function () {
            var name = document.getElementById('d-dept-name').value.trim();
            var dtype = document.getElementById('d-dept-type').value;
            var headEl = document.getElementById('d-dept-head');
            var headRaw = headEl ? headEl.value : '';
            var headUserId = headRaw ? parseInt(headRaw, 10) : null;
            if (!name) throw new Error('请填写部门名称');
            if (isNew) {
                var code = document.getElementById('d-dept-code').value.trim();
                var parentRaw = document.getElementById('d-dept-parent').value;
                if (!code) throw new Error('请填写部门编码');
                await api('/api/system/depts', {
                    method: 'POST',
                    body: JSON.stringify({
                        name: name,
                        code: code,
                        parent_id: parentRaw ? parseInt(parentRaw, 10) : null,
                        dept_type: dtype,
                        head_user_id: headUserId,
                    }),
                });
            } else {
                await api('/api/system/depts/' + dept.id, {
                    method: 'PUT',
                    body: JSON.stringify({
                        name: name,
                        dept_type: dtype,
                        status: document.getElementById('d-dept-status').value,
                        head_user_id: headUserId,
                    }),
                });
            }
            state.depts = [];
            await loadDeptsTab();
            showMsg(isNew ? '部门已创建' : '部门已更新', true);
        });
    }

    function userStatusBadgeHtml(status) {
        if (status === 'active') {
            return '<span class="spc-status-badge spc-status-active">启用</span>';
        }
        return '<span class="spc-status-badge spc-status-disabled">禁用</span>';
    }

    function scopeTypeLabel(scopeType) {
        return {
            all: '全部',
            dept: '本部门',
            self: '仅本人',
            dept_tree: '部门及下级',
            none: '无',
        }[scopeType] || scopeType;
    }

    function dataScopeActionLabel(action) {
        return { read: '读', write: '写', export: '导出' }[action] || action;
    }

    function groupPermsByModule(perms) {
        var groups = {};
        (perms || []).forEach(function (p) {
            var mod = String(p).split('.')[0] || 'other';
            if (!groups[mod]) groups[mod] = [];
            groups[mod].push(p);
        });
        return Object.keys(groups).sort().map(function (mod) {
            return { module: mod, items: groups[mod] };
        });
    }

    function buildPermissionPreviewHtml(data) {
        var perms = data.permissions || [];
        var groups = groupPermsByModule(perms);
        var permHtml = groups.length
            ? groups.map(function (g) {
                return '<div class="spc-perm-module">'
                    + '<p class="spc-perm-module-title">' + escHtml(g.module) + ' · ' + g.items.length + '</p>'
                    + '<div class="spc-perm-chips">'
                    + g.items.map(function (p) {
                        return '<span class="spc-perm-chip">' + escHtml(p) + '</span>';
                    }).join('')
                    + '</div></div>';
            }).join('')
            : '<p class="text-xs text-[#9AA0A6]">无功能权限</p>';
        var scopeRows = (data.data_scopes || []).filter(function (x) { return x.scope_type !== 'none'; });
        var scopeHtml = scopeRows.length
            ? '<table class="spc-matrix w-full mt-2"><thead><tr>'
            + '<th>资源</th><th>动作</th><th>范围</th></tr></thead><tbody>'
            + scopeRows.map(function (x) {
                return '<tr><td class="font-mono text-xs">' + escHtml(x.resource_code) + '</td>'
                    + '<td>' + escHtml(dataScopeActionLabel(x.action)) + '</td>'
                    + '<td><span class="spc-scope-badge">' + escHtml(scopeTypeLabel(x.scope_type)) + '</span></td></tr>';
            }).join('')
            + '</tbody></table>'
            : '<p class="mt-2 text-xs text-[#9AA0A6]">无有效数据范围</p>';
        return '<div class="space-y-4">'
            + '<div><p class="spc-detail-section-title mb-2">功能权限'
            + (perms.length ? ' <span class="font-normal text-[#6B7280]">（共 ' + perms.length + ' 项）</span>' : '')
            + '</p>' + permHtml + '</div>'
            + '<div class="pt-3 border-t border-[#EEF0F2]"><p class="spc-detail-section-title">有效数据范围</p>' + scopeHtml + '</div>'
            + '</div>';
    }

    async function openUserDetailDrawer(user) {
        if (!user) return;
        var deptLabel = (user.depts || []).map(function (d) { return d.name; }).join('、') || '—';
        var roleLabels = user.role_labels || user.roles || [];
        var roleChips = roleLabels.length
            ? roleLabels.map(function (lbl) { return '<span class="spc-chip">' + escHtml(lbl) + '</span>'; }).join('')
            : '<span class="text-sm text-[#9AA0A6]">—</span>';
        var mcp = user.must_change_password
            ? '<p class="mt-2 text-xs text-amber-700">首次登录须修改密码</p>'
            : '';
        var displayName = user.display_name || user.username || '—';
        var html = ''
            + '<div class="spc-user-detail space-y-5">'
            + '<div class="rounded-lg border border-[#EEF0F2] bg-[#F9FAFB] p-4">'
            + '<div class="flex items-start justify-between gap-3">'
            + '<div class="min-w-0">'
            + '<p class="text-lg font-semibold text-[#1A1D1F]">' + escHtml(displayName) + '</p>'
            + '<p class="mt-0.5 text-sm text-[#6B7280]">' + escHtml(user.username) + '</p>'
            + '</div>'
            + userStatusBadgeHtml(user.status)
            + '</div>'
            + '<div class="mt-3 flex flex-wrap gap-1.5">' + roleChips + '</div>'
            + mcp
            + '</div>'
            + '<section>'
            + '<p class="spc-detail-section-title mb-2">基本信息</p>'
            + '<dl class="spc-detail-grid mt-2">'
            + '<div class="spc-detail-field"><dt>部门</dt><dd>' + escHtml(deptLabel) + '</dd></div>'
            + '<div class="spc-detail-field"><dt>最后登录</dt><dd class="whitespace-nowrap">' + escHtml(formatSpcDateTime(user.last_login_at)) + '</dd></div>'
            + '<div class="spc-detail-field"><dt>创建时间</dt><dd class="whitespace-nowrap">' + escHtml(formatSpcDateOnly(user.created_at)) + '</dd></div>'
            + '</dl>'
            + '</section>'
            + '<section class="pt-4 border-t border-[#EEF0F2]">'
            + '<p class="spc-detail-section-title mb-3">权限概览</p>'
            + '<div id="user-detail-perms" class="text-sm text-[#6B7280]">加载中…</div>'
            + '</section>'
            + '</div>';
        openDrawer('用户详情 · ' + user.username, html, null);
        var box = document.getElementById('user-detail-perms');
        try {
            var data = await api('/api/system/users/' + user.id + '/permission-preview');
            if (box) box.innerHTML = buildPermissionPreviewHtml(data);
        } catch (e) {
            if (box) box.textContent = '权限加载失败';
        }
    }

    function openUserDrawer(mode, user) {
        var isNew = mode === 'create';
        var sel = user ? (user.roles || []) : ['VIEWER'];
        var deptIds = user ? (user.dept_ids || []) : [];
        var html = ''
            + (isNew ? '<div><label class="block text-gray-600 mb-1">用户名</label><input id="d-username" class="w-full border rounded-lg px-3 py-2"></div>'
                + '<div><label class="block text-gray-600 mb-1">密码</label><input id="d-password" type="password" class="w-full border rounded-lg px-3 py-2"></div>' : '')
            + '<div><label class="block text-gray-600 mb-1">显示名</label><input id="d-display" class="w-full border rounded-lg px-3 py-2" value="' + (user ? (user.display_name || '') : '') + '"></div>'
            + '<div><label class="block text-gray-600 mb-1">角色</label>'
            + roleCheckboxesHtml(sel)
            + '</div>'
            + '<div><label class="block text-gray-600 mb-1">部门</label>'
            + deptCheckboxesHtml(deptIds)
            + '<p class="text-xs text-gray-500 mt-1">可多选；列表中第一个勾选的部门为主部门' + (isNew ? '；不选则按角色自动分配默认部门' : '') + '</p></div>';
        openDrawer(isNew ? '新建用户' : '编辑用户 · ' + user.username, html, async function () {
            var roleCodes = collectCheckedRoleCodes();
            if (!roleCodes.length) throw new Error('至少选择一个角色');
            var deptIdsSelected = collectCheckedDeptIds();
            if (isNew) {
                var payload = {
                    username: document.getElementById('d-username').value.trim(),
                    password: document.getElementById('d-password').value,
                    display_name: document.getElementById('d-display').value.trim(),
                    role_codes: roleCodes,
                };
                if (deptIdsSelected.length) {
                    payload.dept_ids = deptIdsSelected;
                    payload.primary_dept_id = deptIdsSelected[0];
                }
                await api('/api/system/users', {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
            } else {
                await api('/api/system/users/' + user.id, {
                    method: 'PUT',
                    body: JSON.stringify({ display_name: document.getElementById('d-display').value.trim() }),
                });
                await api('/api/system/users/' + user.id + '/roles', {
                    method: 'PUT',
                    body: JSON.stringify({ role_codes: roleCodes }),
                });
                if (deptIdsSelected.length) {
                    await api('/api/system/users/' + user.id + '/depts', {
                        method: 'PUT',
                        body: JSON.stringify({
                            dept_ids: deptIdsSelected,
                            primary_dept_id: deptIdsSelected[0],
                        }),
                    });
                }
            }
            await loadUsers();
            showMsg(isNew ? '用户已创建' : '用户已更新', true);
        });
    }

    function syncRoleSelectOptions() {
        var sel = document.getElementById('matrix-role-select');
        if (sel) {
            var matrixPrev = sel.value;
            sel.innerHTML = state.roles.map(function (r) {
                return '<option value="' + r.id + '">' + (r.name || r.code) + '</option>';
            }).join('');
            if (matrixPrev && state.roles.some(function (r) { return String(r.id) === matrixPrev; })) {
                sel.value = matrixPrev;
            }
        }
        var dsSel = document.getElementById('datascope-role-select');
        if (dsSel) {
            var dsPrev = dsSel.value;
            dsSel.innerHTML = state.roles.map(function (r) {
                return '<option value="' + r.id + '">' + (r.name || r.code) + '</option>';
            }).join('');
            if (dsPrev && state.roles.some(function (r) { return String(r.id) === dsPrev; })) {
                dsSel.value = dsPrev;
            }
        }
    }

    async function loadRoles() {
        if (!CAN_ROLES) return;
        state.roles = await api('/api/system/roles');
        renderRolesTable();
        syncRoleSelectOptions();
    }

    function filteredRoles() {
        var q = (document.getElementById('role-search').value || '').trim().toLowerCase();
        return state.roles.filter(function (r) {
            if (!q) return true;
            return (r.name || '').toLowerCase().indexOf(q) >= 0
                || (r.code || '').toLowerCase().indexOf(q) >= 0;
        });
    }

    function renderRolesTable() {
        var tbody = document.getElementById('roles-tbody');
        if (!tbody) return;
        var rows = filteredRoles();
        var countNum = document.getElementById('role-count-num');
        if (countNum) countNum.textContent = String(rows.length);
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="crm-td text-center text-gray-400 py-8">暂无角色</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            var builtin = r.is_builtin;
            var typeLabel = builtin ? '内置' : '自定义';
            var desc = (r.description || '').trim() || '—';
            var canDelete = !builtin && CAN_DELETE_ROLES;
            var ops = '<div class="crm-op-actions">'
                + spcOpBtn('crm-op-btn-detail btn-role-matrix', '编辑权限矩阵', 'data-id="' + r.id + '"', SPC_ICONS.matrix)
                + spcOpBtn('crm-op-btn-edit btn-role-edit', '修改', 'data-id="' + r.id + '"', SPC_ICONS.edit)
                + (canDelete
                    ? spcOpBtn('crm-op-btn-delete btn-role-delete', '删除', 'data-id="' + r.id + '"'
                    + ' data-crm-delete-title="确认删除角色"'
                    + ' data-crm-delete-target="将删除角色：' + String(r.name || r.code).replace(/"/g, '&quot;') + '"'
                    + ' data-crm-delete-hint="若仍有用户绑定将无法删除。"', SPC_ICONS.delete)
                    : '')
                + '</div>';
            return '<tr data-role-id="' + r.id + '">'
                + '<td class="crm-td crm-name-cell"><span class="crm-name-link">' + (r.name || r.code) + '</span></td>'
                + '<td class="crm-td text-gray-600 font-mono text-xs">' + r.code + '</td>'
                + '<td class="crm-td">' + typeLabel + '</td>'
                + '<td class="crm-td spc-bound-users-cell">' + boundUsersCountCell(r) + '</td>'
                + '<td class="crm-td text-gray-600 max-w-xs truncate">' + desc + '</td>'
                + '<td class="crm-td crm-sticky-right-op whitespace-nowrap">' + ops + '</td></tr>';
        }).join('');
    }

    function openRoleDrawer(mode, role) {
        var isNew = mode === 'create';
        var html = '<div><label class="block text-gray-600 mb-1">角色名称</label>'
            + '<input id="d-rname" class="w-full border rounded-lg px-3 py-2" value="' + (role ? (role.name || '') : '') + '"></div>'
            + '<div class="mt-3"><label class="block text-gray-600 mb-1">描述</label>'
            + '<textarea id="d-rdesc" rows="3" class="w-full border rounded-lg px-3 py-2">'
            + (role ? (role.description || '') : '') + '</textarea></div>'
            + (isNew ? '<p class="text-xs text-gray-500 mt-2">保存后可在「功能权限」「数据权限」中配置权限。</p>' : '');
        openDrawer(isNew ? '新建角色' : '修改角色 · ' + (role.name || role.code), html, async function () {
            var name = document.getElementById('d-rname').value.trim();
            var description = document.getElementById('d-rdesc').value.trim();
            if (!name) throw new Error('请填写角色名称');
            if (isNew) {
                await api('/api/system/roles', {
                    method: 'POST',
                    body: JSON.stringify({ name: name, description: description }),
                });
            } else {
                await api('/api/system/roles/' + role.id, {
                    method: 'PUT',
                    body: JSON.stringify({ name: name, description: description }),
                });
            }
            await loadRoles();
            showMsg(isNew ? '角色已创建' : '角色已更新', true);
        });
    }

    function openRoleMatrix(roleId) {
        var sel = document.getElementById('matrix-role-select');
        if (sel) sel.value = String(roleId);
        switchTab('matrix');
    }

    async function loadMatrixTab() {
        if (!CAN_ROLES) return;
        if (!state.roles.length) await loadRoles();
        var sel = document.getElementById('matrix-role-select');
        var rid = parseInt(sel.value, 10) || (state.roles[0] && state.roles[0].id);
        if (!rid) return;
        state.matrixData = await api('/api/system/permissions/matrix?role_id=' + rid);
        state.matrixReadonly = !!state.matrixData.readonly && !IS_SUPER;
        document.getElementById('matrix-readonly-hint').classList.toggle(
            'hidden',
            !(state.matrixData.readonly && !IS_SUPER)
        );
        document.getElementById('btn-save-matrix').disabled = state.matrixReadonly;
        renderMatrix();
    }

    function renderMatrix() {
        var box = document.getElementById('matrix-container');
        var data = state.matrixData;
        if (!data || !data.modules) {
            box.innerHTML = '<p class="text-gray-500">无数据</p>';
            return;
        }
        var cols = data.columns || [];
        var html = '';
        data.modules.forEach(function (mod) {
            html += '<h3 class="font-semibold text-sm mt-4 mb-2">' + mod.label + '</h3>';
            html += '<table class="spc-matrix w-full mb-4"><thead><tr><th>权限项</th>';
            cols.forEach(function (c) { html += '<th class="text-center">' + c.label + '</th>'; });
            html += '</tr></thead><tbody>';
            (mod.rows || []).forEach(function (row) {
                html += '<tr><td>' + row.label
                    + '<div class="spc-code-hint" title="' + (row.codes || []).join(', ') + '">'
                    + (row.codes || []).join(' · ') + '</div></td>';
                cols.forEach(function (c) {
                    var checked = row.cells && row.cells[c.key] ? ' checked' : '';
                    var dis = state.matrixReadonly ? ' disabled' : '';
                    html += '<td class="text-center"><input type="checkbox" data-row="' + escAttr(row.label) + '" data-col="' + escAttr(c.key) + '"' + checked + dis + '></td>';
                });
                html += '</tr>';
            });
            html += '</tbody></table>';
        });
        box.innerHTML = html;
    }

    function collectMatrixPermissions() {
        var codes = new Set();
        var box = document.getElementById('matrix-container');
        var data = state.matrixData;
        if (!box || !data) return [];
        var rowByLabel = {};
        (data.modules || []).forEach(function (mod) {
            (mod.rows || []).forEach(function (row) {
                rowByLabel[row.label] = row;
            });
        });
        box.querySelectorAll('input[type="checkbox"][data-row][data-col]:checked').forEach(function (inp) {
            var label = inp.getAttribute('data-row');
            var colKey = inp.getAttribute('data-col');
            var row = rowByLabel[label || ''];
            if (!row || !colKey) return;
            var list = (row.col_codes && row.col_codes[colKey]) || [];
            list.forEach(function (c) { codes.add(c); });
        });
        return Array.from(codes).sort();
    }

    async function saveMatrix() {
        var rid = parseInt(document.getElementById('matrix-role-select').value, 10);
        if (!rid) return;
        if (state.matrixData.readonly && IS_SUPER) {
            if (!confirm('修改超级管理员权限将影响全站，确认继续？')) return;
        }
        if (state.matrixReadonly) return;
        var codes = collectMatrixPermissions();
        var res = await api('/api/system/roles/' + rid + '/permissions', {
            method: 'PUT',
            body: JSON.stringify({ permission_codes: codes }),
        });
        var saved = (res && res.permission_codes) ? res.permission_codes.length : codes.length;
        showMsg('权限已保存（' + saved + ' 项）', true);
        await loadRoles();
        await loadMatrixTab();
    }

    async function loadDataScopeTab() {
        if (!CAN_ROLES) return;
        if (!state.roles.length) await loadRoles();
        var sel = document.getElementById('datascope-role-select');
        var rid = parseInt(sel.value, 10) || (state.roles[0] && state.roles[0].id);
        if (!rid) return;
        state.dataScopeData = await api('/api/system/roles/' + rid + '/data-scopes');
        var role = state.roles.find(function (r) { return r.id === rid; });
        state.dataScopeReadonly = role && role.code === 'SUPER_ADMIN';
        document.getElementById('datascope-readonly-hint').classList.toggle('hidden', !state.dataScopeReadonly);
        document.getElementById('btn-save-datascope').disabled = state.dataScopeReadonly;
        renderDataScope();
    }

    function renderDataScope() {
        var box = document.getElementById('datascope-container');
        var data = state.dataScopeData;
        if (!data || !data.rows) {
            box.innerHTML = '<p class="text-gray-500">无数据</p>';
            return;
        }
        var actions = data.actions || [];
        var scopeTypes = data.scope_types || [];
        var html = '<table class="spc-matrix w-full"><thead><tr><th>资源</th>';
        actions.forEach(function (a) { html += '<th class="text-center">' + a.label + '</th>'; });
        html += '</tr></thead><tbody>';
        data.rows.forEach(function (row) {
            html += '<tr><td>' + row.label + '<div class="spc-code-hint">' + row.resource_code + '</div></td>';
            actions.forEach(function (a) {
                var cur = (row.cells && row.cells[a.code]) || 'none';
                html += '<td class="text-center"><select class="border rounded text-xs ds-cell" data-resource="' + row.resource_code + '" data-action="' + a.code + '"' + (state.dataScopeReadonly ? ' disabled' : '') + '>';
                scopeTypes.forEach(function (st) {
                    html += '<option value="' + st.code + '"' + (st.code === cur ? ' selected' : '') + '>' + st.label + '</option>';
                });
                html += '</select></td>';
            });
            html += '</tr>';
        });
        html += '</tbody></table>';
        box.innerHTML = html;
    }

    async function saveDataScope() {
        var rid = parseInt(document.getElementById('datascope-role-select').value, 10);
        if (!rid || state.dataScopeReadonly) return;
        var scopes = [];
        document.querySelectorAll('.ds-cell').forEach(function (el) {
            scopes.push({
                resource_code: el.getAttribute('data-resource'),
                action: el.getAttribute('data-action'),
                scope_type: el.value,
            });
        });
        await api('/api/system/roles/' + rid + '/data-scopes', {
            method: 'PUT',
            body: JSON.stringify({ scopes: scopes }),
        });
        showMsg('数据权限已保存', true);
    }

    async function loadPreviewTab() {
        if (!CAN_USERS) return;
        await ensureDepts();
        if (!state.users.length) await loadUsers();
        var sel = document.getElementById('preview-user-select');
        if (sel && !sel.options.length) {
            sel.innerHTML = state.users.map(function (u) {
                return '<option value="' + u.id + '">' + (u.display_name || u.username) + '</option>';
            }).join('');
        }
        await renderPreview();
    }

    async function renderPreview() {
        var uid = parseInt(document.getElementById('preview-user-select').value, 10);
        if (!uid) return;
        var data = await api('/api/system/users/' + uid + '/permission-preview');
        var box = document.getElementById('preview-container');
        var roles = (data.roles || []).join('、');
        var perms = (data.permissions || []).slice(0, 12).join(' · ');
        var scopeRows = (data.data_scopes || []).filter(function (x) { return x.scope_type !== 'none'; }).slice(0, 24);
        var scopeHtml = scopeRows.map(function (x) {
            return '<tr><td class="px-2 py-1">' + x.resource_code + '</td><td class="px-2 py-1">' + x.action + '</td><td class="px-2 py-1">' + x.scope_type + '</td></tr>';
        }).join('');
        box.innerHTML = '<p><strong>用户</strong>：' + (data.user.display_name || data.user.username) + '</p>'
            + '<p class="mt-2"><strong>角色</strong>：' + roles + '</p>'
            + '<p class="mt-2"><strong>功能权限</strong>（节选）：' + perms + '</p>'
            + '<p class="mt-3 font-semibold">有效数据范围（非 none）</p>'
            + '<table class="spc-matrix w-full mt-1"><thead><tr><th>资源</th><th>动作</th><th>范围</th></tr></thead><tbody>'
            + (scopeHtml || '<tr><td colspan="3" class="px-2 py-2 text-gray-500">无</td></tr>') + '</tbody></table>';
    }

    function goAuditPage(page) {
        var totalPages = Math.max(1, Math.ceil(state.auditTotal / state.auditPageSize));
        state.auditPage = Math.min(Math.max(0, page), totalPages - 1);
        loadAudit().catch(function (e) { showMsg(e.message, false); });
    }

    function renderAuditPagination() {
        var wrap = document.getElementById('audit-pagination');
        var pageInfo = document.getElementById('audit-page-info');
        var pageNumsEl = document.getElementById('audit-page-numbers');
        var total = state.auditTotal;
        if (!wrap) return;
        if (!total) {
            wrap.classList.add('hidden');
            return;
        }
        wrap.classList.remove('hidden');
        var totalPages = Math.max(1, Math.ceil(total / state.auditPageSize));
        var curPage = state.auditPage + 1;
        if (pageInfo) {
            pageInfo.innerHTML = '共 <span class="font-semibold text-[#1A1D1F]">' + total + '</span> 条，第 ' + curPage + ' / ' + totalPages + ' 页';
        }
        var prev = document.getElementById('btn-audit-prev');
        var next = document.getElementById('btn-audit-next');
        if (prev) prev.disabled = state.auditPage <= 0;
        if (next) next.disabled = (state.auditPage + 1) * state.auditPageSize >= total;
        if (!pageNumsEl) return;
        var pages = computePageNumbers(curPage, totalPages);
        pageNumsEl.innerHTML = pages.map(function (p) {
            var active = p === curPage
                ? 'border-[#456595] bg-[#456595] text-white'
                : 'border-[#D7DBE0] bg-white text-[#1A1D1F] hover:bg-[#F9FAFB]';
            return '<button type="button" class="spc-audit-page inline-flex h-8 min-w-8 items-center justify-center rounded-[6px] border px-2 text-sm transition-colors ' + active + '" data-page="' + p + '">' + p + '</button>';
        }).join('');
    }

    function renderAuditTable() {
        var tbody = document.getElementById('audit-tbody');
        if (!tbody) return;
        renderAuditPagination();
        var rows = state.auditLogs;
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="crm-td text-center text-gray-400 py-8">无记录</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (log) {
            return '<tr><td class="crm-td whitespace-nowrap">' + escHtml(formatSpcDateTime(log.created_at)) + '</td>'
                + '<td class="crm-td">' + escHtml(log.actor_username) + '</td>'
                + '<td class="crm-td font-mono text-xs">' + escHtml(log.action) + '</td>'
                + '<td class="crm-td">' + escHtml(auditSummaryText(log)) + '</td>'
                + '<td class="crm-td text-center">' + auditLevelCell(log.action) + '</td></tr>';
        }).join('');
    }

    function auditActionLevel(action) {
        var a = String(action || '').toLowerCase();
        if (a.indexOf('.delete') >= 0 || a.indexOf('.disable') >= 0) return 'high';
        if (a.indexOf('.create') >= 0 || a.indexOf('.import') >= 0) return 'low';
        return 'medium';
    }

    function auditLevelLabel(level) {
        return { high: '高', medium: '中', low: '低' }[level] || '中';
    }

    function auditLevelCell(action) {
        var level = auditActionLevel(action);
        var label = auditLevelLabel(level);
        return '<span class="spc-audit-level spc-audit-level-' + level + '">' + label + '</span>';
    }

    function auditTargetTypeLabel(targetType) {
        return { user: '用户', role: '角色', dept: '部门' }[targetType] || targetType || '对象';
    }

    function auditActionLabel(action) {
        var labels = {
            'user.create': '新增用户',
            'user.update': '更新用户',
            'user.disable': '禁用用户',
            'user.enable': '启用用户',
            'user.roles': '调整用户角色',
            'user.depts': '调整用户部门',
            'user.password_reset': '重置用户密码',
            'user.roles.batch': '批量调整角色',
            'user.import': '导入用户',
            'role.create': '新增角色',
            'role.update': '更新角色',
            'role.delete': '删除角色',
            'role.permissions': '更新功能权限',
            'role.data_scopes': '更新数据权限',
            'dept.create': '新增部门',
            'dept.update': '更新部门',
            'dept.delete': '删除部门',
        };
        return labels[action] || action;
    }

    function auditSummaryText(log) {
        var action = String(log.action || '');
        var detail = String(log.detail || '').trim();
        var after = log.after || {};
        var before = log.before || {};
        var subject = detail || String(log.target_id || '').trim();
        switch (action) {
            case 'user.create':
                return '新增了用户 ' + subject;
            case 'user.update':
                return '更新了用户 ' + subject + (after.display_name != null ? ' 的显示名' : '');
            case 'user.disable':
                return '禁用了用户 ' + subject;
            case 'user.enable':
                return '启用了用户 ' + subject;
            case 'user.roles':
                return '调整了用户 ' + subject + ' 的角色';
            case 'user.depts':
                return '调整了用户 ' + subject + ' 的部门';
            case 'user.password_reset':
                return '重置了用户 ' + subject + ' 的密码';
            case 'user.roles.batch':
                return '批量调整了 ' + (after.count != null ? after.count : '多名') + ' 个用户的角色';
            case 'user.import':
                return '导入了用户（新增 ' + (after.created != null ? after.created : subject) + ' 个）';
            case 'role.create':
                return '新增了角色 ' + (after.name || subject) + (after.code && after.code !== subject ? '（' + after.code + '）' : '');
            case 'role.update':
                return '更新了角色 ' + subject;
            case 'role.delete':
                return '删除了角色 ' + (before.name || subject);
            case 'role.permissions':
                return '更新了角色 ' + subject + ' 的功能权限';
            case 'role.data_scopes':
                return '更新了角色 ' + subject + ' 的数据权限';
            case 'dept.create':
                return '新增了部门 ' + (after.name || subject);
            case 'dept.update':
                return '更新了部门 ' + subject;
            case 'dept.delete':
                return '删除了部门 ' + (before.name || subject);
            default:
                return auditTargetTypeLabel(log.target_type) + ' · ' + action + (subject ? ' · ' + subject : '');
        }
    }

    var KNOWN_AUDIT_ACTIONS = [
        'user.create', 'user.update', 'user.disable', 'user.enable', 'user.roles',
        'user.depts', 'user.password_reset', 'user.roles.batch', 'user.import',
        'role.create', 'role.update', 'role.delete', 'role.permissions', 'role.data_scopes',
        'dept.create', 'dept.update', 'dept.delete',
    ];

    function renderAuditFilterSelects(actors, actions) {
        var actorSel = document.getElementById('audit-actor');
        var actionSel = document.getElementById('audit-action');
        if (!actorSel || !actionSel) return;
        var actorVal = actorSel.value;
        var actionVal = actionSel.value;
        actorSel.innerHTML = '<option value="">全部操作人</option>'
            + (actors || []).map(function (a) {
                return '<option value="' + escAttr(a) + '">' + escHtml(a) + '</option>';
            }).join('');
        actionSel.innerHTML = '<option value="">全部操作类型</option>'
            + (actions || []).map(function (a) {
                return '<option value="' + escAttr(a) + '">' + escHtml(auditActionLabel(a)) + '</option>';
            }).join('');
        if (actorVal) actorSel.value = actorVal;
        if (actionVal) actionSel.value = actionVal;
    }

    async function loadAuditFilterOptions() {
        var actors = [];
        var actions = KNOWN_AUDIT_ACTIONS.slice();
        try {
            var data = await api('/api/system/audit-logs/filters');
            actors = data.actors || [];
            if (data.actions && data.actions.length) actions = data.actions;
        } catch (e) {
            if (CAN_USERS) {
                try {
                    var users = await api('/api/system/users?limit=0');
                    actors = (users.items || []).map(function (u) { return u.username; }).filter(Boolean);
                } catch (_) { /* ignore */ }
            }
        }
        renderAuditFilterSelects(actors, actions);
    }

    async function resolveAuditTotal(params, data) {
        if (data && !Array.isArray(data) && data.total != null) {
            return data.total;
        }
        var rows = Array.isArray(data) ? data : (data.items || []);
        if (rows.length < state.auditPageSize) {
            return state.auditPage * state.auditPageSize + rows.length;
        }
        var countParams = new URLSearchParams(params);
        countParams.set('limit', '500');
        countParams.set('offset', '0');
        var all = await api('/api/system/audit-logs?' + countParams.toString());
        if (Array.isArray(all)) return all.length;
        return all.total || rows.length;
    }

    async function loadAudit() {
        if (!CAN_AUDIT) return;
        var params = new URLSearchParams();
        var actor = document.getElementById('audit-actor').value.trim();
        var action = document.getElementById('audit-action').value.trim();
        var levelEl = document.getElementById('audit-level');
        var level = levelEl ? levelEl.value.trim() : '';
        var from = document.getElementById('audit-from').value;
        var to = document.getElementById('audit-to').value;
        if (actor) params.set('actor_username', actor);
        if (action) params.set('action', action);
        if (level) params.set('level', level);
        if (from) params.set('date_from', from);
        if (to) params.set('date_to', to + 'T23:59:59Z');
        params.set('limit', String(state.auditPageSize));
        params.set('offset', String(state.auditPage * state.auditPageSize));
        var data = await api('/api/system/audit-logs?' + params.toString());
        state.auditLogs = Array.isArray(data) ? data : (data.items || []);
        state.auditTotal = await resolveAuditTotal(params, data);
        renderAuditTable();
    }

    document.querySelectorAll('.spc-tab').forEach(function (btn) {
        btn.addEventListener('click', function () {
            switchTab(btn.getAttribute('data-tab'));
        });
    });

    document.getElementById('btn-new-user').addEventListener('click', function () {
        var open = function () { openUserDrawer('create', null); };
        var prep = state.roles.length ? Promise.resolve() : loadRoles();
        prep.then(function () { return ensureDepts(true); })
            .then(open)
            .catch(function (e) { showMsg(e.message, false); });
    });

    document.getElementById('user-search').addEventListener('input', function () {
        clearTimeout(state.userSearchTimer);
        state.userSearchTimer = setTimeout(function () {
            state.userPage = 0;
            loadUsers().catch(function (e) { showMsg(e.message, false); });
        }, 300);
    });

    document.getElementById('btn-user-prev').addEventListener('click', function () {
        if (state.userPage <= 0) return;
        goUserPage(state.userPage - 1);
    });
    document.getElementById('btn-user-next').addEventListener('click', function () {
        if ((state.userPage + 1) * state.userPageSize >= state.usersTotal) return;
        goUserPage(state.userPage + 1);
    });
    document.getElementById('user-pagination').addEventListener('click', function (ev) {
        var btn = ev.target.closest('.spc-user-page');
        if (!btn) return;
        goUserPage(parseInt(btn.getAttribute('data-page'), 10) - 1);
    });

    document.getElementById('btn-audit-prev').addEventListener('click', function () {
        if (state.auditPage <= 0) return;
        goAuditPage(state.auditPage - 1);
    });
    document.getElementById('btn-audit-next').addEventListener('click', function () {
        if ((state.auditPage + 1) * state.auditPageSize >= state.auditTotal) return;
        goAuditPage(state.auditPage + 1);
    });
    document.getElementById('audit-pagination').addEventListener('click', function (ev) {
        var btn = ev.target.closest('.spc-audit-page');
        if (!btn) return;
        goAuditPage(parseInt(btn.getAttribute('data-page'), 10) - 1);
    });

    var btnUserFilter = document.getElementById('btn-user-filter');
    if (btnUserFilter) {
        btnUserFilter.addEventListener('click', function () {
            toggleFilterPanel('btn-user-filter', 'user-filter-panel');
        });
    }

    var btnAuditFilter = document.getElementById('btn-audit-filter');
    if (btnAuditFilter) {
        btnAuditFilter.addEventListener('click', function () {
            toggleFilterPanel('btn-audit-filter', 'audit-filter-panel');
        });
    }

    var btnUserClearFilter = document.getElementById('btn-user-clear-filter');
    if (btnUserClearFilter) btnUserClearFilter.addEventListener('click', clearUserFilters);

    var btnRoleClearFilter = document.getElementById('btn-role-clear-filter');
    if (btnRoleClearFilter) btnRoleClearFilter.addEventListener('click', clearRoleFilters);

    var btnDeptClearFilter = document.getElementById('btn-dept-clear-filter');
    if (btnDeptClearFilter) btnDeptClearFilter.addEventListener('click', clearDeptFilters);

    var btnAuditClearFilter = document.getElementById('btn-audit-clear-filter');
    if (btnAuditClearFilter) btnAuditClearFilter.addEventListener('click', clearAuditFilters);

    var deptSearchEl = document.getElementById('dept-search');
    if (deptSearchEl) {
        deptSearchEl.addEventListener('input', renderDeptsList);
    }

    document.getElementById('user-select-all').addEventListener('change', function (ev) {
        var on = ev.target.checked;
        state.users.forEach(function (u) {
            if (on) state.selectedUserIds.add(u.id);
            else state.selectedUserIds.delete(u.id);
        });
        renderUsers();
        syncBatchRoleUi();
    });

    document.getElementById('users-tbody').addEventListener('change', function (ev) {
        if (!ev.target.classList.contains('user-row-check')) return;
        var id = parseInt(ev.target.getAttribute('data-id'), 10);
        if (ev.target.checked) state.selectedUserIds.add(id);
        else state.selectedUserIds.delete(id);
        syncBatchRoleUi();
    });

    document.getElementById('btn-batch-roles').addEventListener('click', async function () {
        var roleCode = document.getElementById('batch-role-select').value;
        var mode = document.getElementById('batch-role-mode').value;
        if (!roleCode || !state.selectedUserIds.size) return;
        if (!confirm('确认为 ' + state.selectedUserIds.size + ' 个用户' + (mode === 'add' ? '追加' : '设置') + '角色？')) return;
        try {
            await api('/api/system/users/batch-roles', {
                method: 'PUT',
                body: JSON.stringify({
                    user_ids: Array.from(state.selectedUserIds),
                    role_codes: [roleCode],
                    mode: mode,
                }),
            });
            state.selectedUserIds.clear();
            await loadUsers();
            showMsg('批量角色已更新', true);
        } catch (e) { showMsg(e.message, false); }
    });

    document.getElementById('user-import-file').addEventListener('change', async function (ev) {
        var file = ev.target.files && ev.target.files[0];
        ev.target.value = '';
        if (!file) return;
        var fd = new FormData();
        fd.append('file', file);
        try {
            var r = await fetch('/api/system/users/import', {
                method: 'POST',
                credentials: 'same-origin',
                headers: window.crmAuthHeader(),
                body: fd,
            });
            var data = await r.json().catch(function () { return {}; });
            if (!r.ok) throw new Error(data.detail || ('HTTP ' + r.status));
            await loadUsers();
            showMsg('导入完成：新增 ' + (data.created || 0) + '，跳过 ' + (data.skipped || 0), true);
            if (data.errors && data.errors.length) console.warn('import errors', data.errors);
        } catch (e) { showMsg(e.message, false); }
    });

    document.getElementById('users-tbody').addEventListener('click', async function (ev) {
        var detailBtn = ev.target.closest('.btn-detail-user');
        if (detailBtn) {
            var detailId = detailBtn.getAttribute('data-id');
            var detailUser = state.users.find(function (u) { return String(u.id) === String(detailId); });
            if (!detailUser) return;
            try {
                await openUserDetailDrawer(detailUser);
            } catch (e) { showMsg(e.message, false); }
            return;
        }
        var editBtn = ev.target.closest('.btn-edit-user');
        var resetBtn = ev.target.closest('.btn-reset-pwd');
        var disableBtn = ev.target.closest('.btn-disable-user');
        var enableBtn = ev.target.closest('.btn-enable-user');
        var btn = editBtn || resetBtn || disableBtn || enableBtn;
        if (!btn) return;
        var id = btn.getAttribute('data-id');
        if (!id) return;
        var user = state.users.find(function (u) { return String(u.id) === String(id); });
        if (editBtn) {
            var prep = state.roles.length ? Promise.resolve() : loadRoles();
            prep.then(function () { return ensureDepts(true); })
                .then(function () { openUserDrawer('edit', user); })
                .catch(function (e) { showMsg(e.message, false); });
        } else if (resetBtn) {
            var pw = prompt('输入新密码（至少6位）');
            if (!pw) return;
            var _forceResult = await (window.crmConfirmActionDialog
                ? window.crmConfirmActionDialog({ title: '是否强制用户下次登录修改密码？', confirmText: '是', cancelText: '否' })
                : { ok: confirm('是否强制用户下次登录修改密码？') });
            var force = !!(_forceResult && _forceResult.ok);
            try {
                await api('/api/system/users/' + id + '/password', {
                    method: 'PUT',
                    body: JSON.stringify({ password: pw, must_change_password: force }),
                });
                showMsg('密码已重置', true);
                await loadUsers();
            } catch (e) { showMsg(e.message, false); }
        } else if (disableBtn) {
            if (!user) return;
            var username = user.display_name || user.username || ('#' + id);
            var ok = false;
            if (typeof window.crmConfirmDeleteDialog === 'function') {
                ok = await window.crmConfirmDeleteDialog({
                    title: '确认禁用',
                    targetText: '将禁用用户：' + username,
                    hint: '禁用后该用户将无法登录，可在列表中重新启用。',
                    confirmText: '确认禁用',
                });
            } else {
                ok = confirm('确认禁用该用户？');
            }
            if (!ok) return;
            try {
                await api('/api/system/users/' + id + '/status', { method: 'POST', body: JSON.stringify({ status: 'disabled' }) });
                await loadUsers();
                showMsg('已禁用', true);
            } catch (e) { showMsg(e.message, false); }
        } else if (enableBtn) {
            try {
                await api('/api/system/users/' + id + '/status', { method: 'POST', body: JSON.stringify({ status: 'active' }) });
                await loadUsers();
                showMsg('已启用', true);
            } catch (e) { showMsg(e.message, false); }
        }
    });

    document.getElementById('btn-new-role').addEventListener('click', function () {
        openRoleDrawer('create', null);
    });

    document.getElementById('roles-tbody').addEventListener('click', async function (ev) {
        var matrixBtn = ev.target.closest('.btn-role-matrix');
        var editBtn = ev.target.closest('.btn-role-edit');
        var deleteBtn = ev.target.closest('.btn-role-delete');
        var btn = matrixBtn || editBtn || deleteBtn;
        if (!btn) return;
        var id = btn.getAttribute('data-id');
        if (!id) return;
        var role = state.roles.find(function (r) { return String(r.id) === String(id); });
        if (!role) return;
        if (matrixBtn) {
            openRoleMatrix(role.id);
        } else if (editBtn) {
            openRoleDrawer('edit', role);
        } else if (deleteBtn) {
            try {
                await apiDelete('/api/system/roles/' + role.id);
                await loadRoles();
                showMsg('角色已删除', true);
            } catch (e) { showMsg(e.message, false); }
        }
    });

    document.getElementById('role-search').addEventListener('input', renderRolesTable);
    document.getElementById('matrix-role-select').addEventListener('change', loadMatrixTab);
    document.getElementById('btn-save-matrix').addEventListener('click', function () {
        saveMatrix().catch(function (e) { showMsg(e.message, false); });
    });
    document.getElementById('datascope-role-select').addEventListener('change', loadDataScopeTab);
    document.getElementById('btn-save-datascope').addEventListener('click', function () {
        saveDataScope().catch(function (e) { showMsg(e.message, false); });
    });
    document.getElementById('btn-load-preview').addEventListener('click', function () {
        renderPreview().catch(function (e) { showMsg(e.message, false); });
    });
    document.getElementById('preview-user-select').addEventListener('change', function () {
        renderPreview().catch(function (e) { showMsg(e.message, false); });
    });

    function openDeptDrawerWithLookups(mode, dept) {
        Promise.all([
            ensureDepts(true),
            api('/api/system/users?limit=0'),
        ]).then(function (results) {
            var userData = results[1] || {};
            openDeptDrawer(mode, dept, userData.items || []);
        }).catch(function (e) { showMsg(e.message, false); });
    }

    function handleNewDeptClick() {
        openDeptDrawerWithLookups('create', null);
    }

    var panelDepts = document.getElementById('panel-depts');
    if (panelDepts) {
        panelDepts.addEventListener('click', async function (ev) {
            var newBtn = ev.target.closest('#btn-new-dept');
            if (newBtn) {
                handleNewDeptClick();
                return;
            }
            var editBtn = ev.target.closest('.btn-edit-dept');
            var deleteBtn = ev.target.closest('.btn-delete-dept');
            var detailBtn = ev.target.closest('.btn-detail-dept');
            if (detailBtn) {
                var detailId = detailBtn.getAttribute('data-id');
                if (!detailId) return;
                var detailDept = state.depts.find(function (d) { return String(d.id) === String(detailId); });
                if (detailDept) openDeptDetailDrawer(detailDept);
                return;
            }
            var btn = editBtn || deleteBtn;
            if (!btn) return;
            var id = btn.getAttribute('data-id');
            if (!id) return;
            var dept = state.depts.find(function (d) { return String(d.id) === String(id); });
            if (editBtn) {
                if (!dept) return;
                openDeptDrawerWithLookups('edit', dept);
            } else if (deleteBtn) {
                if (!dept) return;
                try {
                    await apiDelete('/api/system/depts/' + dept.id);
                    state.depts = [];
                    await loadDeptsTab();
                    showMsg('部门已删除', true);
                } catch (e) { showMsg(e.message, false); }
            }
        });
    }

    document.getElementById('btn-audit-search').addEventListener('click', function () {
        var kwEl = document.getElementById('audit-keyword');
        var actorEl = document.getElementById('audit-actor');
        if (kwEl && actorEl && kwEl.value.trim() && !actorEl.value) {
            var kw = kwEl.value.trim().toLowerCase();
            for (var i = 0; i < actorEl.options.length; i++) {
                var opt = actorEl.options[i];
                if (!opt.value) continue;
                if (opt.value.toLowerCase() === kw || opt.text.toLowerCase().indexOf(kw) >= 0) {
                    actorEl.value = opt.value;
                    break;
                }
            }
        }
        state.auditPage = 0;
        loadAudit().catch(function (e) { showMsg(e.message, false); });
    });

    document.getElementById('drawer-close').addEventListener('click', closeDrawer);
    document.getElementById('drawer-cancel').addEventListener('click', closeDrawer);
    document.getElementById('spc-drawer-backdrop').addEventListener('click', closeDrawer);
    document.getElementById('drawer-save').addEventListener('click', async function () {
        if (!state._drawerSave) return;
        try {
            await state._drawerSave();
            closeDrawer();
        } catch (e) {
            showMsg(e.message, false);
        }
    });

    if (!CAN_USERS) document.getElementById('tab-btn-users').style.display = 'none';
    if (!CAN_ROLES) {
        document.getElementById('tab-btn-roles').style.display = 'none';
        document.getElementById('tab-btn-matrix').style.display = 'none';
        document.getElementById('tab-btn-datascope').style.display = 'none';
    }
    if (!CAN_USERS) document.getElementById('tab-btn-preview').style.display = 'none';
    if (!CAN_USERS) document.getElementById('tab-btn-depts').style.display = 'none';
    if (!CAN_USERS) {
        var oacTab = document.getElementById('tab-btn-offer-approval');
        if (oacTab) oacTab.style.display = 'none';
    }
    if (!CAN_AUDIT) document.getElementById('tab-btn-audit').style.display = 'none';
    if (!CAN_INSURANCE) {
        var insTab = document.getElementById('tab-btn-insurance');
        if (insTab) insTab.style.display = 'none';
    }

    window.spcOpenDrawer = openDrawer;
    window.spcShowMsg = showMsg;
    window.spcOpBtn = spcOpBtn;
    window.SPC_ICONS = SPC_ICONS;

    var first = CAN_USERS ? 'users' : (CAN_ROLES ? 'roles' : (CAN_INSURANCE ? 'insurance' : (CAN_AUDIT ? 'audit' : 'users')));
    switchTab(first);
})();
