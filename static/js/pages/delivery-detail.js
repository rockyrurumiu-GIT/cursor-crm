/**
 * Delivery detail page — Phase 5E Step 1: init config + shared helpers only.
 * Tab-specific logic remains in templates/pages/delivery_detail.html until later steps.
 * Requires: Vue 3 CDN before inline mount script; crmAuthHeader from base.html.
 */
(function () {
    'use strict';

    function readConfig() {
        const cfg = window.__CRM_DELIVERY_DETAIL__ || {};
        return {
            clientId: Number(cfg.clientId) || 0,
            moduleKey: String(cfg.moduleKey || ''),
            moduleTitle: String(cfg.moduleTitle || ''),
            handbookAdminCrossSearch: !!cfg.handbookAdminCrossSearch,
        };
    }

    function todayInputDate() {
        const now = new Date();
        const y = now.getFullYear();
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const d = String(now.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    function extractLooseDateParts(raw) {
        const s = String(raw || '').trim();
        if (!s) return null;
        const m = s.match(/(\d{4})\D+(\d{1,2})\D+(\d{1,2})/);
        if (!m) return null;
        return [m[1], m[2], m[3]];
    }

    function normalizeDateForInput(raw, fallbackTodayIfEmpty = false) {
        const s = String(raw || '').trim();
        if (!s) return fallbackTodayIfEmpty ? todayInputDate() : '';
        const parts = extractLooseDateParts(s);
        if (!parts) return s;
        const y = parts[0];
        const mo = String(parseInt(parts[1], 10)).padStart(2, '0');
        const d = String(parseInt(parts[2], 10)).padStart(2, '0');
        if (mo === 'NaN' || d === 'NaN') return s;
        return `${y}-${mo}-${d}`;
    }

    function displayDateSlash(raw) {
        const s = String(raw || '').trim();
        if (!s) return '';
        const parts = extractLooseDateParts(s);
        if (!parts) return s;
        return `${parts[0]}/${parseInt(parts[1], 10)}/${parseInt(parts[2], 10)}`;
    }

    function interviewDateRank(raw) {
        const normalized = normalizeDateForInput(raw, false);
        if (!normalized) return 0;
        return Number(normalized.replace(/-/g, '')) || 0;
    }

    function normalizedDateToUtcMs(raw) {
        const normalized = normalizeDateForInput(raw, false);
        if (!normalized) return 0;
        const m = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (!m) return 0;
        return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    }

    function diffDaysFromDate(raw, endRaw) {
        const startMs = normalizedDateToUtcMs(raw);
        const endMs = normalizedDateToUtcMs(endRaw);
        if (!startMs || !endMs || endMs < startMs) return -1;
        return Math.floor((endMs - startMs) / 86400000);
    }

    function isEmptyOrNoValue(raw) {
        const s = String(raw || '').trim().toUpperCase();
        return !s || s === 'N';
    }

    function csvCell(raw) {
        const s = String(raw == null ? '' : raw);
        if (/[",\n]/.test(s)) {
            return `"${s.replace(/"/g, '""')}"`;
        }
        return s;
    }

    function multiSelectSummary(selected, emptyLabel) {
        const values = Array.isArray(selected) ? selected : [];
        if (!values.length) return emptyLabel || '全部';
        if (values.length === 1) return values[0];
        return `已选${values.length}项`;
    }

    function uniqueSorted(rows, field) {
        const set = new Set();
        (rows || []).forEach((row) => {
            const v = String(row[field] != null ? row[field] : '').trim();
            if (v) set.add(v);
        });
        return [...set].sort((a, b) => a.localeCompare(b, 'zh-CN'));
    }

    function fuzzyMatch(haystack, needle) {
        const n = String(needle || '').trim();
        if (!n) return true;
        return String(haystack || '').toLowerCase().includes(n.toLowerCase());
    }

    function interviewTextLength(raw) {
        return String(raw || '').trim().length;
    }

    function crmEscapeHtml(s) {
        return String(s || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    /** 检索摘录高亮：escape 后包 mark；空格分隔多词均匹配（英文不区分大小写）。 */
    function crmHighlightSearchQuery(raw, query) {
        const t = raw == null ? '' : String(raw);
        const parts = String(query || '').trim().split(/\s+/).filter(Boolean);
        if (!parts.length) return crmEscapeHtml(t);
        const pattern = parts.map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
        if (!pattern) return crmEscapeHtml(t);
        let re;
        try {
            re = new RegExp(`(${pattern})`, 'gi');
        } catch (_) {
            return crmEscapeHtml(t);
        }
        let out = '';
        let last = 0;
        let m;
        while ((m = re.exec(t)) !== null) {
            out += crmEscapeHtml(t.slice(last, m.index));
            out += '<mark class="crm-fs-hit rounded bg-amber-200 px-0.5 text-gray-900 ring-1 ring-amber-400/70">';
            out += crmEscapeHtml(m[0]);
            out += '</mark>';
            last = m.index + m[0].length;
            if (last === re.lastIndex) re.lastIndex++;
        }
        out += crmEscapeHtml(t.slice(last));
        return out;
    }

    async function readApiErrorMessage(response, fallback) {
        let msg = fallback;
        try {
            const err = await response.json();
            if (typeof err.detail === 'string') {
                msg = err.detail;
            } else if (Array.isArray(err.detail)) {
                msg = err.detail.map((x) => (x && x.msg) || JSON.stringify(x)).join('；') || msg;
            } else if (err.detail != null) {
                msg = String(err.detail);
            }
        } catch (err) {
            // Ignore parse failure and keep fallback message.
        }
        return msg;
    }

    function formatDate(ds) {
        if (!ds) return '-';
        const t = new Date(ds);
        return Number.isNaN(t.getTime()) ? String(ds) : t.toLocaleString();
    }

    async function loadClientBrief(clientId, clientNameRef, clientOwnerRef) {
        const r = await fetch(`/api/clients/${clientId}/brief`, { headers: window.crmAuthHeader() });
        if (r.ok) {
            const d = await r.json();
            clientNameRef.value = d.name || clientNameRef.value;
            if (clientOwnerRef) clientOwnerRef.value = d.owner || '';
        }
    }

    window.CrmDeliveryDetail = {
        readConfig,
        todayInputDate,
        extractLooseDateParts,
        normalizeDateForInput,
        displayDateSlash,
        interviewDateRank,
        normalizedDateToUtcMs,
        diffDaysFromDate,
        isEmptyOrNoValue,
        csvCell,
        multiSelectSummary,
        uniqueSorted,
        fuzzyMatch,
        interviewTextLength,
        crmEscapeHtml,
        crmHighlightSearchQuery,
        readApiErrorMessage,
        formatDate,
        loadClientBrief,
    };
})();
