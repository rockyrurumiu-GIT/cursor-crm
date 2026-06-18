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

    var state = {
        users: [],
        usersTotal: 0,
        userPage: 0,
        userPageSize: 20,
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
        if (name === 'audit' && CAN_AUDIT) runTabLoad(function () { return loadAudit(false); });
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
        state._drawerSave = onSave;
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
        ['batch-role-select', 'batch-role-mode', 'btn-batch-roles'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.classList.toggle('hidden', !hasSel || !CAN_USERS);
        });
        var sel = document.getElementById('batch-role-select');
        if (sel && !sel.options.length && state.roles.length) {
            sel.innerHTML = state.roles.map(function (r) {
                return '<option value="' + r.code + '">' + (r.name || r.code) + '</option>';
            }).join('');
        }
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
        var pageInfo = document.getElementById('user-page-info');
        var totalPages = Math.max(1, Math.ceil(state.usersTotal / state.userPageSize));
        var curPage = state.userPage + 1;
        if (pageInfo) {
            pageInfo.textContent = '共 ' + state.usersTotal + ' 人 · 第 ' + curPage + ' / ' + totalPages + ' 页';
        }
        var prev = document.getElementById('btn-user-prev');
        var next = document.getElementById('btn-user-next');
        if (prev) prev.disabled = state.userPage <= 0;
        if (next) next.disabled = (state.userPage + 1) * state.userPageSize >= state.usersTotal;
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="crm-td text-center text-gray-400 py-8">暂无数据</td></tr>';
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
                + '<button type="button" class="crm-op-btn-edit btn-edit-user" data-id="' + u.id + '">编辑</button>'
                + '<button type="button" class="crm-op-btn-handoff btn-reset-pwd" data-id="' + u.id + '">重置密码</button>'
                + (u.status === 'active'
                    ? '<button type="button" class="crm-op-btn-delete btn-disable-user" data-id="' + u.id + '">禁用</button>'
                    : '<button type="button" class="crm-op-btn-edit btn-enable-user" data-id="' + u.id + '">启用</button>')
                + '</div>'
                : '';
            return '<tr data-user-id="' + u.id + '">'
                + '<td class="crm-td text-center"><input type="checkbox" class="user-row-check" data-id="' + u.id + '"' + checked + '></td>'
                + '<td class="crm-td font-medium">' + u.username + mcp + '</td>'
                + '<td class="crm-td">' + (u.display_name || '') + '</td>'
                + '<td class="crm-td">' + u.status + '</td>'
                + '<td class="crm-td text-gray-600">' + deptLabel + '</td>'
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
        return { sales: '销售', delivery: '交付', finance: '财务', general: '通用' }[t] || t || '—';
    }

    async function loadDeptsTab() {
        if (!CAN_USERS) return;
        await ensureDepts(true);
        renderDeptsList();
    }

    function renderDeptsList() {
        var tbody = document.getElementById('depts-tbody');
        if (!tbody) return;
        if (!state.depts.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="crm-td text-center text-gray-400 py-8">暂无部门</td></tr>';
            return;
        }
        tbody.innerHTML = state.depts.map(function (d) {
            var builtin = BUILTIN_DEPT_CODES[d.code];
            var ops = '<div class="crm-op-actions">'
                + '<button type="button" class="crm-op-btn-edit btn-edit-dept" data-id="' + d.id + '">编辑</button>'
                + (builtin || !CAN_DELETE_USERS ? '' : '<button type="button" class="crm-op-btn-delete btn-delete-dept" data-id="' + d.id + '"'
                + ' data-crm-delete-title="确认删除部门"'
                + ' data-crm-delete-target="将删除部门：' + String(d.name || '').replace(/"/g, '&quot;') + '"'
                + ' data-crm-delete-hint="若仍有用户或客户归属将无法删除。">删除</button>')
                + '</div>';
            return '<tr data-dept-id="' + d.id + '">'
                + '<td class="crm-td font-medium">' + d.name + (builtin ? ' <span class="text-xs text-gray-400">内置</span>' : '') + '</td>'
                + '<td class="crm-td text-gray-600">' + d.code + '</td>'
                + '<td class="crm-td text-gray-600">' + (d.parent_id ? deptNameById(d.parent_id) : '—') + '</td>'
                + '<td class="crm-td">' + deptTypeLabel(d.dept_type) + '</td>'
                + '<td class="crm-td">' + d.status + '</td>'
                + '<td class="crm-td text-gray-500 text-xs">' + d.path + '</td>'
                + '<td class="crm-td crm-sticky-right-op crm-op-col-xl whitespace-nowrap">' + ops + '</td></tr>';
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

    function openDeptDrawer(mode, dept) {
        var isNew = mode === 'create';
        var parentId = dept ? dept.parent_id : null;
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
            + '<div><label class="block text-gray-600 mb-1">部门类型</label>'
            + '<select id="d-dept-type" class="w-full border rounded-lg px-3 py-2">'
            + ['general', 'sales', 'delivery', 'finance'].map(function (t) {
                var cur = dept ? dept.dept_type : 'delivery';
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
                    }),
                });
            } else {
                await api('/api/system/depts/' + dept.id, {
                    method: 'PUT',
                    body: JSON.stringify({
                        name: name,
                        dept_type: dtype,
                        status: document.getElementById('d-dept-status').value,
                    }),
                });
            }
            state.depts = [];
            await loadDeptsTab();
            showMsg(isNew ? '部门已创建' : '部门已更新', true);
        });
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
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="crm-td text-center text-gray-400 py-8">暂无角色</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            var builtin = r.is_builtin;
            var typeLabel = builtin ? '内置' : '自定义';
            var desc = (r.description || '').trim() || '—';
            var canDelete = !builtin && CAN_DELETE_ROLES;
            var ops = '<div class="crm-op-actions spc-op-actions">'
                + '<button type="button" class="crm-op-btn-edit btn-role-matrix" data-id="' + r.id + '">编辑权限矩阵</button>'
                + '<button type="button" class="crm-op-btn-detail btn-role-edit" data-id="' + r.id + '">修改</button>'
                + (canDelete
                    ? '<button type="button" class="crm-op-btn-delete btn-role-delete" data-id="' + r.id + '"'
                    + ' data-crm-delete-title="确认删除角色"'
                    + ' data-crm-delete-target="将删除角色：' + String(r.name || r.code).replace(/"/g, '&quot;') + '"'
                    + ' data-crm-delete-hint="若仍有用户绑定将无法删除。">删除</button>'
                    : '')
                + '</div>';
            return '<tr data-role-id="' + r.id + '">'
                + '<td class="crm-td font-medium">' + (r.name || r.code) + '</td>'
                + '<td class="crm-td text-gray-600 font-mono text-xs">' + r.code + '</td>'
                + '<td class="crm-td">' + typeLabel + '</td>'
                + '<td class="crm-td">' + (r.user_count || 0) + '</td>'
                + '<td class="crm-td text-gray-600 max-w-xs truncate" title="' + desc.replace(/"/g, '&quot;') + '">' + desc + '</td>'
                + '<td class="crm-td crm-sticky-right-op crm-op-col-xl whitespace-nowrap">' + ops + '</td></tr>';
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

    var auditOffset = 0;

    async function loadAudit(append) {
        if (!CAN_AUDIT) return;
        if (!append) auditOffset = 0;
        var params = new URLSearchParams();
        var actor = document.getElementById('audit-actor').value.trim();
        var action = document.getElementById('audit-action').value.trim();
        var from = document.getElementById('audit-from').value;
        var to = document.getElementById('audit-to').value;
        if (actor) params.set('actor_username', actor);
        if (action) params.set('action', action);
        if (from) params.set('date_from', from);
        if (to) params.set('date_to', to + 'T23:59:59Z');
        params.set('limit', '50');
        params.set('offset', String(auditOffset));
        var rows = await api('/api/system/audit-logs?' + params.toString());
        var tbody = document.getElementById('audit-tbody');
        if (!append) tbody.innerHTML = '';
        if (!rows.length && !append) {
            tbody.innerHTML = '<tr><td colspan="6" class="crm-td text-center text-gray-400 py-8">无记录</td></tr>';
            return;
        }
        auditOffset += rows.length;
        var html = rows.map(function (log, i) {
            var idx = auditOffset - rows.length + i;
            var detailId = 'audit-detail-' + idx;
            var beforeAfter = '';
            if (log.before || log.after) {
                beforeAfter = '<button type="button" class="text-blue-600 text-xs btn-audit-toggle" data-target="' + detailId + '">展开</button>'
                    + '<pre id="' + detailId + '" class="hidden mt-1 text-xs bg-gray-50 p-2 rounded max-h-40 overflow-auto">'
                    + JSON.stringify({ before: log.before, after: log.after }, null, 2) + '</pre>';
            }
            return '<tr><td class="crm-td whitespace-nowrap">' + formatSpcDateTime(log.created_at) + '</td>'
                + '<td class="crm-td">' + log.actor_username + '</td>'
                + '<td class="crm-td">' + log.action + '</td>'
                + '<td class="crm-td">' + log.target_type + '#' + log.target_id + '</td>'
                + '<td class="crm-td">' + (log.detail || '') + '</td>'
                + '<td class="crm-td">' + beforeAfter + '</td></tr>';
        }).join('');
        tbody.insertAdjacentHTML('beforeend', html);
        var moreBtn = document.getElementById('btn-audit-more');
        if (!moreBtn) {
            var wrap = document.createElement('div');
            wrap.className = 'mt-3 text-center';
            wrap.innerHTML = '<button type="button" id="btn-audit-more" class="text-sm text-blue-600 hover:underline">加载更多</button>';
            document.getElementById('panel-audit').appendChild(wrap);
            document.getElementById('btn-audit-more').addEventListener('click', function () {
                loadAudit(true).catch(function (e) { showMsg(e.message, false); });
            });
        }
        if (moreBtn) moreBtn.style.display = rows.length < 50 ? 'none' : '';
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
        state.userPage -= 1;
        loadUsers().catch(function (e) { showMsg(e.message, false); });
    });
    document.getElementById('btn-user-next').addEventListener('click', function () {
        if ((state.userPage + 1) * state.userPageSize >= state.usersTotal) return;
        state.userPage += 1;
        loadUsers().catch(function (e) { showMsg(e.message, false); });
    });

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
        var id = ev.target.getAttribute('data-id');
        if (!id) return;
        var user = state.users.find(function (u) { return String(u.id) === String(id); });
        if (ev.target.classList.contains('btn-edit-user')) {
            var prep = state.roles.length ? Promise.resolve() : loadRoles();
            prep.then(function () { return ensureDepts(true); })
                .then(function () { openUserDrawer('edit', user); })
                .catch(function (e) { showMsg(e.message, false); });
        } else if (ev.target.classList.contains('btn-reset-pwd')) {
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
        } else if (ev.target.classList.contains('btn-disable-user')) {
            if (!confirm('确认禁用该用户？')) return;
            try {
                await api('/api/system/users/' + id + '/status', { method: 'POST', body: JSON.stringify({ status: 'disabled' }) });
                await loadUsers();
                showMsg('已禁用', true);
            } catch (e) { showMsg(e.message, false); }
        } else if (ev.target.classList.contains('btn-enable-user')) {
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
        var id = ev.target.getAttribute('data-id');
        if (!id) return;
        var role = state.roles.find(function (r) { return String(r.id) === String(id); });
        if (!role) return;
        if (ev.target.classList.contains('btn-role-matrix')) {
            openRoleMatrix(role.id);
        } else if (ev.target.classList.contains('btn-role-edit')) {
            openRoleDrawer('edit', role);
        } else if (ev.target.classList.contains('btn-role-delete')) {
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

    function refreshDeptParentSelect() {
        var sel = document.getElementById('d-dept-parent');
        if (!sel) return;
        sel.innerHTML = '<option value="">无（顶级）</option>' + deptParentOptionsHtml(null, null);
    }

    function handleNewDeptClick() {
        openDeptDrawer('create', null);
        ensureDepts(true).then(function () {
            refreshDeptParentSelect();
        }).catch(function (e) { showMsg(e.message, false); });
    }

    var panelDepts = document.getElementById('panel-depts');
    if (panelDepts) {
        panelDepts.addEventListener('click', async function (ev) {
            var newBtn = ev.target.closest('#btn-new-dept');
            if (newBtn) {
                handleNewDeptClick();
                return;
            }
            var id = ev.target.getAttribute('data-id');
            if (!id) return;
            var dept = state.depts.find(function (d) { return String(d.id) === String(id); });
            if (ev.target.classList.contains('btn-edit-dept')) {
                if (!dept) return;
                openDeptDrawer('edit', dept);
            } else if (ev.target.classList.contains('btn-delete-dept')) {
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
        var oldMore = document.getElementById('btn-audit-more');
        if (oldMore && oldMore.parentElement) oldMore.parentElement.remove();
        loadAudit(false).catch(function (e) { showMsg(e.message, false); });
    });

    document.getElementById('audit-tbody').addEventListener('click', function (ev) {
        if (!ev.target.classList.contains('btn-audit-toggle')) return;
        var pre = document.getElementById(ev.target.getAttribute('data-target'));
        if (pre) pre.classList.toggle('hidden');
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

    var first = CAN_USERS ? 'users' : (CAN_ROLES ? 'roles' : (CAN_INSURANCE ? 'insurance' : (CAN_AUDIT ? 'audit' : 'users')));
    switchTab(first);
})();
