/**
 * 全局 CRM 表格列宽拖拽（与客户拜访记录一致）
 * 依赖：thead 末行 th、colgroup col、th[data-col] + .crm-th-resizable
 */
(function () {
    const MIN_WIDTH = 48;
    /** 三键操作列（详情/修改/删除）固定宽 px */
    const OP_COL_WIDTH = 92;
    /** 花名册「打卡」列固定宽（内容用 crm-cell-clip 省略+悬停展开） */
    const CHECKIN_COL_WIDTH = 128;
    const COL_CONTENT_PAD = 14;
    const RESIZE_EDGE = 12;

    function isOpColumnTh(th) {
        return th.classList.contains('crm-sticky-right-op')
            || th.classList.contains('turnover-sticky-right-actions')
            || th.classList.contains('crm-op-col');
    }

    function isCheckinColumnTh(th) {
        return th.classList.contains('roster-col-checkin');
    }

    function opColumnIndex(ths) {
        const last = ths.length - 1;
        if (last >= 0 && isOpColumnTh(ths[last])) return last;
        return ths.findIndex((th) => isOpColumnTh(th));
    }

    function checkinColumnIndex(ths) {
        return ths.findIndex((th) => isCheckinColumnTh(th));
    }

    function minWidthForTh(th, fallback) {
        const colMin = Number(th.dataset.colMin);
        const customMin = Number.isFinite(colMin) && colMin > 0 ? colMin : 0;
        if (isOpColumnTh(th)) return customMin > 0 ? customMin : OP_COL_WIDTH;
        if (isCheckinColumnTh(th)) return CHECKIN_COL_WIDTH;
        if (customMin > 0) return customMin;
        return fallback;
    }

    function storageKeyFor(table) {
        if (table.dataset.tableResizeKey) return table.dataset.tableResizeKey;
        const id = table.dataset.tableId || [...table.classList].find((c) => c.endsWith('-table') && c !== 'crm-table') || 'crm-table';
        return `crm-col-widths:${location.pathname}:${id}`;
    }

    function leafHeaderCells(table) {
        const rows = [...table.querySelectorAll('thead tr')];
        if (!rows.length) return [];
        return [...rows[rows.length - 1].querySelectorAll('th')];
    }

    function ensureColgroup(table, count) {
        let colgroup = table.querySelector('colgroup');
        if (!colgroup) {
            colgroup = document.createElement('colgroup');
            table.insertBefore(colgroup, table.firstChild);
        }
        while (colgroup.children.length < count) {
            const col = document.createElement('col');
            col.className = 'crm-col';
            col.dataset.col = String(colgroup.children.length);
            colgroup.appendChild(col);
        }
        while (colgroup.children.length > count) {
            colgroup.removeChild(colgroup.lastChild);
        }
        return [...colgroup.querySelectorAll('col')];
    }

    function tagOpColElement(col) {
        if (!col) return;
        col.classList.add('crm-col-op');
        col.style.width = `${OP_COL_WIDTH}px`;
        col.style.minWidth = `${OP_COL_WIDTH}px`;
        col.style.maxWidth = `${OP_COL_WIDTH}px`;
    }

    function tagCheckinColElement(col) {
        if (!col) return;
        col.style.width = `${CHECKIN_COL_WIDTH}px`;
        col.style.minWidth = `${CHECKIN_COL_WIDTH}px`;
        col.style.maxWidth = `${CHECKIN_COL_WIDTH}px`;
    }

    /** 冻结列 left/width 依赖 CSS 变量，拖拽后须与 colgroup 同步 */
    function syncStickyColumnVars(table, readColWidth) {
        const px = (i) => `${readColWidth(i)}px`;
        if (table.classList.contains('settlement-table')) {
            table.style.setProperty('--settlement-sticky-serial-width', px(0));
            table.style.setProperty('--settlement-sticky-date-width', px(1));
            table.style.setProperty('--settlement-sticky-customer-width', px(2));
            return;
        }
        if (table.classList.contains('roster-table')) {
            table.style.setProperty('--roster-sticky-serial-width', px(0));
            table.style.setProperty('--roster-sticky-name-width', px(1));
            return;
        }
        if (table.classList.contains('turnover-table')) {
            table.style.setProperty('--roster-sticky-serial-width', px(0));
            return;
        }
        if (table.classList.contains('interview-table')) {
            table.style.setProperty('--interview-sticky-serial-width', px(0));
        }
    }

    function flexGrowColumnIndex(ths) {
        const opIdx = opColumnIndex(ths);
        if (opIdx > 0) {
            for (let i = opIdx - 1; i >= 0; i--) {
                if (isCheckinColumnTh(ths[i])) continue;
                const label = (ths[i].textContent || '').trim();
                if (label === '备注' || label.includes('原因') || label.includes('纪要') || label.includes('沟通')) return i;
            }
            return opIdx - 1;
        }
        return ths.length > 1 ? ths.length - 1 : -1;
    }

    function measureDefaults(table, ths) {
        table.style.tableLayout = 'fixed';
        return ths.map((th) => {
            if (isOpColumnTh(th)) return OP_COL_WIDTH;
            if (isCheckinColumnTh(th)) return CHECKIN_COL_WIDTH;
            const floor = minWidthForTh(th, MIN_WIDTH);
            const w = Math.max(th.offsetWidth || 0, th.scrollWidth || 0);
            return Math.max(floor, w);
        });
    }

    function measureColumnContentWidth(table, ths, cols, colIndex) {
        const th = ths[colIndex];
        if (th.classList.contains('roster-col-position-zntx')) {
            return Math.round(parseFloat(getComputedStyle(th).width) || 240);
        }
        const col = cols[colIndex];
        const prev = col ? col.style.width : '';
        if (col) col.style.width = '1px';
        let w = th.scrollWidth || 0;
        table.querySelectorAll('tbody tr').forEach((tr) => {
            const cells = tr.querySelectorAll(':scope > td');
            if (cells.length !== ths.length) return;
            const td = cells[colIndex];
            if (!td) return;
            const clip = td.querySelector('.crm-cell-clip');
            w = Math.max(w, clip ? (clip.scrollWidth || 0) : (td.scrollWidth || 0));
        });
        if (col) col.style.width = prev;
        return w + COL_CONTENT_PAD;
    }

    function buildColumnHelpers(table, ths, cols, options) {
        const minW = options?.minWidth ?? MIN_WIDTH;
        const tableMin = Number(table.dataset.tableMinWidth) || 0;
        const readColWidth = (i) => {
            if (isOpColumnTh(ths[i])) return OP_COL_WIDTH;
            if (isCheckinColumnTh(ths[i])) return CHECKIN_COL_WIDTH;
            const w = parseFloat(cols[i].style.width);
            if (Number.isFinite(w) && w > 0) return w;
            const th = table.querySelector(`thead th.crm-th-resizable[data-col="${i}"], thead th.visit-th-resizable[data-col="${i}"]`);
            return th ? th.offsetWidth : minW;
        };
        const setColWidth = (i, w) => {
            if (isOpColumnTh(ths[i])) {
                tagOpColElement(cols[i]);
            } else if (isCheckinColumnTh(ths[i])) {
                tagCheckinColElement(cols[i]);
            } else {
                const floor = minWidthForTh(ths[i], minW);
                cols[i].style.width = `${Math.max(floor, Math.round(w))}px`;
                cols[i].style.minWidth = '';
                cols[i].style.maxWidth = '';
            }
            syncStickyColumnVars(table, readColWidth);
        };
        const syncTableWidth = () => {
            let total = cols.reduce((sum, _c, i) => sum + readColWidth(i), 0);
            const target = Math.max(total, tableMin);
            const extra = target - total;
            if (extra > 0.5) {
                const flexIdx = flexGrowColumnIndex(ths);
                if (flexIdx >= 0 && !isOpColumnTh(ths[flexIdx]) && !isCheckinColumnTh(ths[flexIdx])) {
                    const flexW = Math.round(readColWidth(flexIdx) + extra);
                    cols[flexIdx].style.width = `${flexW}px`;
                    total = target;
                }
            }
            table.style.width = `${Math.max(total, tableMin)}px`;
            syncStickyColumnVars(table, readColWidth);
        };
        return { readColWidth, setColWidth, syncTableWidth };
    }

    /** 按表体内容适配列宽（花名册：除打卡/操作外默认显示完整） */
    function fitTableColumnsToContent(table) {
        if (!table) return false;
        if (table.dataset.colResizeReady !== '1') {
            initCrmTableColumnResize(table);
        }
        const ths = leafHeaderCells(table);
        if (!ths.length) return false;
        let cols = [...table.querySelectorAll('colgroup col')];
        if (cols.length !== ths.length) cols = ensureColgroup(table, ths.length);
        table.style.tableLayout = 'fixed';
        const { setColWidth, syncTableWidth, readColWidth } = buildColumnHelpers(table, ths, cols, {});
        const opIdx = opColumnIndex(ths);
        const checkinIdx = checkinColumnIndex(ths);
        ths.forEach((_th, i) => {
            if (i === opIdx) {
                setColWidth(i, OP_COL_WIDTH);
            } else if (i === checkinIdx) {
                setColWidth(i, CHECKIN_COL_WIDTH);
            } else {
                const w = measureColumnContentWidth(table, ths, cols, i);
                setColWidth(i, Math.max(minWidthForTh(ths[i], MIN_WIDTH), w));
            }
        });
        syncTableWidth();
        try {
            const key = storageKeyFor(table);
            localStorage.setItem(key, JSON.stringify(cols.map((_c, idx) => readColWidth(idx))));
        } catch { /* ignore */ }
        return true;
    }

    function applyOpColumnWidth(table) {
        const ths = leafHeaderCells(table);
        if (!ths.length) return false;
        let cols = [...table.querySelectorAll('colgroup col')];
        if (cols.length !== ths.length) cols = ensureColgroup(table, ths.length);
        if (!cols.length) return false;
        if (!table.style.tableLayout) table.style.tableLayout = 'fixed';
        const { setColWidth, syncTableWidth } = buildColumnHelpers(table, ths, cols, {});
        const opIdx = opColumnIndex(ths);
        if (opIdx < 0) return false;
        setColWidth(opIdx, OP_COL_WIDTH);
        syncTableWidth();
        return true;
    }

    function refreshOpColumnWidths(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('table.crm-table, table.visit-table').forEach((table) => {
            if (table.classList.contains('roster-table') && table.dataset.rosterContentFit === '1') {
                fitTableColumnsToContent(table);
            } else {
                applyOpColumnWidth(table);
            }
        });
    }

    function initCrmTableColumnResize(table, options) {
        if (!table || table.dataset.colResize === 'off') return false;
        if (table.dataset.colResizeReady === '1') {
            if (table.classList.contains('roster-table') && table.dataset.rosterContentFit === '1') {
                fitTableColumnsToContent(table);
            } else {
                applyOpColumnWidth(table);
            }
            return true;
        }
        const ths = leafHeaderCells(table);
        if (!ths.length) return false;

        const cols = ensureColgroup(table, ths.length);
        ths.forEach((th, i) => {
            th.dataset.col = String(i);
            if (!isOpColumnTh(th)) th.classList.add('crm-th-resizable');
        });

        const minW = options?.minWidth ?? MIN_WIDTH;
        const edge = options?.edge ?? RESIZE_EDGE;
        const storageKey = options?.storageKey ?? storageKeyFor(table);
        const rosterAutoFit = table.classList.contains('roster-table') && table.dataset.rosterContentFit === '1';

        table.style.tableLayout = 'fixed';
        table.dataset.colResizeReady = '1';

        const { readColWidth, setColWidth, syncTableWidth } = buildColumnHelpers(table, ths, cols, {
            minWidth: minW,
        });

        const applyWidths = (widths) => {
            widths.forEach((w, i) => setColWidth(i, w));
            syncTableWidth();
        };

        let saved;
        try {
            saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
        } catch {
            saved = null;
        }
        const opIdx = opColumnIndex(ths);
        if (rosterAutoFit) {
            applyWidths(measureDefaults(table, ths));
        } else if (Array.isArray(saved) && saved.length === cols.length) {
            if (opIdx >= 0) saved[opIdx] = OP_COL_WIDTH;
            const checkinIdx = checkinColumnIndex(ths);
            if (checkinIdx >= 0) saved[checkinIdx] = CHECKIN_COL_WIDTH;
            applyWidths(saved);
        } else if (Array.isArray(options?.defaults) && options.defaults.length === cols.length) {
            if (opIdx >= 0) options.defaults[opIdx] = OP_COL_WIDTH;
            applyWidths(options.defaults);
        } else {
            applyWidths(measureDefaults(table, ths));
        }
        if (opIdx >= 0) setColWidth(opIdx, OP_COL_WIDTH);
        const checkinIdx = checkinColumnIndex(ths);
        if (checkinIdx >= 0) setColWidth(checkinIdx, CHECKIN_COL_WIDTH);
        syncTableWidth();

        const persistWidths = () => {
            const payload = cols.map((_c, i) => readColWidth(i));
            if (opIdx >= 0) payload[opIdx] = OP_COL_WIDTH;
            if (checkinIdx >= 0) payload[checkinIdx] = CHECKIN_COL_WIDTH;
            localStorage.setItem(storageKey, JSON.stringify(payload));
        };

        const startResize = (th, colIndex, startX) => {
            if (isOpColumnTh(ths[colIndex]) || isCheckinColumnTh(ths[colIndex])) return;
            const startW = readColWidth(colIndex);
            th.classList.add('is-resizing');
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';

            const onMove = (ev) => {
                setColWidth(colIndex, startW + (ev.pageX - startX));
                syncTableWidth();
            };
            const onUp = () => {
                th.classList.remove('is-resizing');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                persistWidths();
            };
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        };

        table.querySelectorAll('thead th.crm-th-resizable[data-col], thead th.visit-th-resizable[data-col]').forEach((th) => {
            const colIndex = Number(th.dataset.col);
            if (!Number.isFinite(colIndex) || colIndex < 0 || colIndex >= cols.length) return;
            if (isOpColumnTh(th) || isCheckinColumnTh(th)) return;

            th.addEventListener('mousedown', (e) => {
                const rect = th.getBoundingClientRect();
                if (rect.right - e.clientX > edge) return;
                e.preventDefault();
                e.stopPropagation();
                startResize(th, colIndex, e.pageX);
            });
        });

        return true;
    }

    function initAll(root, options) {
        const scope = root && root.querySelectorAll ? root : document;
        const selector = options?.selector || 'table.crm-table, table.visit-table';
        scope.querySelectorAll(selector).forEach((table) => {
            initCrmTableColumnResize(table, options);
        });
        refreshOpColumnWidths(scope);
    }

    function schedule(root) {
        const run = () => initAll(root || document);
        requestAnimationFrame(run);
    }

    window.crmInitTableColumnResize = initCrmTableColumnResize;
    window.crmInitAllTableColumnResize = initAll;
    window.crmScheduleTableColumnResize = schedule;
    window.crmRefreshOpColumnWidths = refreshOpColumnWidths;
    window.crmFitTableColumnsToContent = fitTableColumnsToContent;

    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => schedule(document), 80);
        setTimeout(() => schedule(document), 700);
        setTimeout(() => refreshOpColumnWidths(document), 1500);
    });
})();
