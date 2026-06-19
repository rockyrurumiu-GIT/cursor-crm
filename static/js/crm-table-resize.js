/**
 * 全局 CRM 表格列宽拖拽（与客户拜访记录一致）
 * 依赖：thead 末行 th、colgroup col、th[data-col] + .crm-th-resizable
 */
(function () {
    const MIN_WIDTH = 64;
    /** 三键操作列（详情/修改/删除）固定宽 px，默认与 base.html CSS 变量一致 */
    const OP_COL_WIDTH = 144;
    const OP_COL_WIDTH_WIDE = 208;
    const OP_COL_WIDTH_XL = 288;
    /** 花名册「打卡」列固定宽（内容用 crm-cell-clip 省略+悬停展开） */
    const CHECKIN_COL_WIDTH = 128;
    /** 花名册「备注」列固定 15 汉字宽（crm-cell-clip 省略+悬停展开） */
    const ROSTER_REMARKS_COL_EM = 15;
    const COL_CONTENT_PAD = 14;
    const RESIZE_EDGE = 12;
    /** 大表按内容测宽时抽样行数，避免上千行卡顿 */
    const CONTENT_SAMPLE_ROWS = 48;
    const STORAGE_VERSION = 'v5';
    const RMS_JOBS_STORAGE_VERSION = 'v12';
    /** 候选人表列顺序重建后须 bump，避免 localStorage 列宽错位 */
    const RMS_CANDIDATES_STORAGE_VERSION = 'v2';
    /** 交付内审操作列收窄后须 bump，避免 localStorage 沿用旧宽 */
    const RMS_DELIVERY_REVIEW_STORAGE_VERSION = 'v2';
    /** 招聘管道「当前招聘进展」预设列宽后须 bump */
    const RMS_PIPELINE_STORAGE_VERSION = 'v1';
    /** 需求清单 JD 固定 30 字宽；岗位名称冻结后须 bump */
    const REQUIREMENTS_JOBS_STORAGE_VERSION = 'v2';
    /** 花名册备注列固定 15 字宽后须 bump，避免 localStorage 沿用按全文测出的旧宽 */
    const ROSTER_STORAGE_VERSION = 'v2';
    /** 员工访谈长文本列固定 20 字宽后须 bump */
    const INTERVIEW_STORAGE_VERSION = 'v1';
    /** 员工访谈「交付判断/员工诉求/交付待办」固定 20 汉字宽 */
    const INTERVIEW_TEXT_WIDE_COL_EM = 20;

    function readCssLengthPx(varName, fallbackPx) {
        const root = getComputedStyle(document.documentElement);
        const raw = (root.getPropertyValue(varName) || '').trim();
        const num = parseFloat(raw);
        if (!Number.isFinite(num) || num <= 0) return fallbackPx;
        if (raw.includes('rem')) {
            const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
            return Math.round(num * remPx);
        }
        return Math.round(num);
    }

    function isOpColumnTh(th) {
        return th.classList.contains('crm-sticky-right-op')
            || th.classList.contains('roster-sticky-op')
            || th.classList.contains('rms-sticky-recommend')
            || th.classList.contains('rms-col-manage')
            || th.classList.contains('crm-op-col-wide')
            || th.classList.contains('crm-op-col-xl')
            || th.classList.contains('rms-delivery-review-op');
    }

    function rmsDeliveryReviewOpColumnWidthPx(th) {
        const table = th && th.closest ? th.closest('table[data-table-id="rms-delivery-review"]') : null;
        if (!table) return null;
        const fontPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
        const raw = getComputedStyle(table).getPropertyValue('--rms-delivery-review-op-col-width').trim();
        const num = parseFloat(raw);
        if (Number.isFinite(num) && num > 0) {
            if (raw.includes('rem')) return Math.round(num * fontPx);
            return Math.round(num);
        }
        return Math.round(OP_COL_WIDTH_WIDE * (3 / 4));
    }

    function rmsJobsStickyColWidthPx(th, varName, fallbackPx) {
        const table = th && th.closest ? th.closest('.rms-jobs-table') : null;
        if (!table) return null;
        const raw = getComputedStyle(table).getPropertyValue(varName).trim();
        const num = parseFloat(raw);
        if (!Number.isFinite(num) || num <= 0) return fallbackPx;
        if (raw.includes('rem')) {
            const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
            return Math.round(num * remPx);
        }
        return Math.round(num);
    }

    function rmsJobsRecommendColumnWidthPx(th) {
        return rmsJobsStickyColWidthPx(th, '--rms-jobs-recommend-col-width', 120);
    }

    function rmsJobsManageColumnWidthPx(th) {
        return rmsJobsStickyColWidthPx(th, '--rms-jobs-manage-col-width', OP_COL_WIDTH);
    }

    function isRmsPipelinePresetColumnTh(th) {
        return th.classList.contains('rms-pipeline-progress')
            || th.classList.contains('rms-pipeline-next-op');
    }

    function rmsPipelinePresetColumnWidthPx(th) {
        if (!th || !isRmsPipelinePresetColumnTh(th)) return null;
        const table = th.closest ? th.closest('table[data-table-id="rms-pipeline"]') : null;
        if (!table) return null;
        const fontPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
        const varName = th.classList.contains('rms-pipeline-next-op')
            ? '--rms-pipeline-next-op-width'
            : '--rms-pipeline-progress-width';
        const raw = getComputedStyle(table).getPropertyValue(varName).trim();
        const num = parseFloat(raw);
        if (Number.isFinite(num) && num > 0) {
            if (raw.includes('rem')) return Math.round(num * fontPx);
            return Math.round(num);
        }
        return th.classList.contains('rms-pipeline-next-op')
            ? Math.round(15.75 * fontPx)
            : Math.round(7 * fontPx);
    }

    function opColumnWidthPx(th) {
        const narrow = readCssLengthPx('--crm-op-col-width', OP_COL_WIDTH);
        const wide = readCssLengthPx('--crm-op-col-width-wide', OP_COL_WIDTH_WIDE);
        const xl = readCssLengthPx('--crm-op-col-width-xl', OP_COL_WIDTH_XL);
        if (!th) return narrow;
        if (th && th.closest('.handbook-table')) {
            const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
            return 12 * rem;
        }
        if (th && th.closest('table[data-table-id="system-users"]')) {
            return Math.round(xl * (2 / 3));
        }
        if (th && th.classList.contains('rms-delivery-review-op')) {
            const drW = rmsDeliveryReviewOpColumnWidthPx(th);
            if (drW != null) return drW;
        }
        if (th && th.closest('.rms-jobs-table') && th.classList.contains('rms-sticky-recommend')) {
            return rmsJobsRecommendColumnWidthPx(th);
        }
        if (th && th.closest('.rms-jobs-table') && th.classList.contains('rms-col-manage')) {
            return rmsJobsManageColumnWidthPx(th);
        }
        if (th.classList.contains('crm-op-col-xl')) return xl;
        if (th.classList.contains('crm-op-col-wide')) return wide;
        return narrow;
    }

    function isCheckinColumnTh(th) {
        return th.classList.contains('roster-col-checkin');
    }

    function isRosterRemarksColumnTh(th) {
        return th.classList.contains('roster-col-remarks');
    }

    function isInterviewTextWideColumnTh(th) {
        return th.classList.contains('interview-col-text-wide');
    }

    function rosterRemarksColumnWidthPx(th) {
        const fontPx = parseFloat(getComputedStyle(th || document.documentElement).fontSize)
            || parseFloat(getComputedStyle(document.documentElement).fontSize)
            || 16;
        const cssW = cssLengthPx(th, 'width') || cssLengthPx(th, 'maxWidth') || cssLengthPx(th, 'minWidth');
        if (cssW > 0 && cssW <= Math.round(ROSTER_REMARKS_COL_EM * fontPx * 1.2)) return Math.round(cssW);
        return Math.round(ROSTER_REMARKS_COL_EM * fontPx);
    }

    function interviewTextWideColumnWidthPx(th) {
        const table = th && th.closest ? th.closest('.interview-table') : null;
        const fontPx = parseFloat(getComputedStyle(th || document.documentElement).fontSize)
            || parseFloat(getComputedStyle(document.documentElement).fontSize)
            || 16;
        if (table) {
            const raw = getComputedStyle(table).getPropertyValue('--interview-text-wide-width').trim();
            const num = parseFloat(raw);
            if (Number.isFinite(num) && num > 0) {
                if (raw.endsWith('em')) return Math.round(num * fontPx);
                if (raw.endsWith('rem')) {
                    const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
                    return Math.round(num * remPx);
                }
                return Math.round(num);
            }
        }
        const cssW = cssLengthPx(th, 'width') || cssLengthPx(th, 'maxWidth') || cssLengthPx(th, 'minWidth');
        if (cssW > 0 && cssW <= Math.round(INTERVIEW_TEXT_WIDE_COL_EM * fontPx * 1.2)) return Math.round(cssW);
        return Math.round(INTERVIEW_TEXT_WIDE_COL_EM * fontPx);
    }

    /** RMS / 需求清单 JD：crm-cell-clip 省略+悬停展开，初始宽取 CSS，不按全文测宽 */
    function isRmsJdColumnTh(th) {
        return th.classList.contains('rms-col-jd') || th.classList.contains('requirements-col-jd');
    }

    function jdHostTable(th) {
        if (!th || !th.closest) return null;
        return th.closest('.rms-jobs-table') || th.closest('table[data-table-id="requirements-jobs"]');
    }

    function isRequirementsJobsTable(table) {
        return !!(table && table.dataset && table.dataset.tableId === 'requirements-jobs');
    }

    function rmsJdDefaultWidthPx(th) {
        const table = jdHostTable(th);
        const fontPx = parseFloat(getComputedStyle(th || document.documentElement).fontSize)
            || parseFloat(getComputedStyle(document.documentElement).fontSize)
            || 16;
        if (table) {
            const raw = getComputedStyle(table).getPropertyValue('--rms-jobs-jd-width').trim()
                || getComputedStyle(table).getPropertyValue('--requirements-jd-width').trim();
            const num = parseFloat(raw);
            if (Number.isFinite(num) && num > 0) {
                if (raw.endsWith('em')) return Math.round(num * fontPx);
                if (raw.endsWith('rem')) {
                    const remPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
                    return Math.round(num * remPx);
                }
                return Math.round(num);
            }
        }
        return Math.round(35 * fontPx);
    }

    function opColumnIndex(ths) {
        for (let i = ths.length - 1; i >= 0; i -= 1) {
            if (isOpColumnTh(ths[i])) return i;
        }
        return -1;
    }

    function applyAllOpColumnWidths(ths, setColWidth) {
        ths.forEach((th, i) => {
            if (isOpColumnTh(th)) setColWidth(i, opColumnWidthPx(th));
        });
    }

    function checkinColumnIndex(ths) {
        return ths.findIndex((th) => isCheckinColumnTh(th));
    }

    function cssLengthPx(el, prop) {
        if (!el) return 0;
        const value = parseFloat(getComputedStyle(el)[prop]);
        return Number.isFinite(value) && value > 0 ? value : 0;
    }

    function headerTextMinWidth(th) {
        const text = (th.textContent || '').replace(/\s+/g, '');
        if (!text) return MIN_WIDTH;
        return Math.max(MIN_WIDTH, Math.ceil(text.length * 14) + 24);
    }

    function minWidthForTh(th, fallback) {
        const colMin = Number(th.dataset.colMin);
        const customMin = Number.isFinite(colMin) && colMin > 0 ? colMin : 0;
        if (isOpColumnTh(th)) return customMin > 0 ? customMin : opColumnWidthPx(th);
        if (isCheckinColumnTh(th)) return CHECKIN_COL_WIDTH;
        if (isRosterRemarksColumnTh(th)) return rosterRemarksColumnWidthPx(th);
        if (isInterviewTextWideColumnTh(th)) return interviewTextWideColumnWidthPx(th);
        const cssMin = cssLengthPx(th, 'minWidth');
        return Math.max(customMin, cssMin, headerTextMinWidth(th), fallback);
    }

    function measureCellWidth(el) {
        if (!el) return 0;
        return Math.max(
            cssLengthPx(el, 'minWidth'),
            cssLengthPx(el, 'width'),
            el.offsetWidth || 0,
            el.scrollWidth || 0,
        );
    }

    function storageKeyFor(table) {
        if (table.dataset.tableResizeKey) return table.dataset.tableResizeKey;
        const id = table.dataset.tableId || [...table.classList].find((c) => c.endsWith('-table') && c !== 'crm-table') || 'crm-table';
        let version = STORAGE_VERSION;
        if (id === 'rms-jobs') version = RMS_JOBS_STORAGE_VERSION;
        else if (id === 'rms-candidates') version = RMS_CANDIDATES_STORAGE_VERSION;
        else if (id === 'rms-delivery-review') version = RMS_DELIVERY_REVIEW_STORAGE_VERSION;
        else if (id === 'rms-pipeline') version = RMS_PIPELINE_STORAGE_VERSION;
        else if (id === 'requirements-jobs') version = REQUIREMENTS_JOBS_STORAGE_VERSION;
        else if (id === 'roster') version = ROSTER_STORAGE_VERSION;
        else if (id === 'interview') version = INTERVIEW_STORAGE_VERSION;
        return `crm-col-widths:${version}:${location.pathname}:${id}`;
    }

    function tbodyDataRows(table) {
        return [...table.querySelectorAll('tbody tr')].filter((tr) => {
            const cells = tr.querySelectorAll(':scope > td');
            if (cells.length <= 1) return false;
            const first = cells[0];
            const colspan = Number(first.getAttribute('colspan') || 1);
            return !(colspan > 1);
        });
    }

    function sampleBodyRows(table) {
        const rows = tbodyDataRows(table);
        if (rows.length <= CONTENT_SAMPLE_ROWS) return rows;
        const picked = [];
        const step = rows.length / CONTENT_SAMPLE_ROWS;
        for (let i = 0; i < CONTENT_SAMPLE_ROWS; i += 1) {
            picked.push(rows[Math.min(rows.length - 1, Math.floor(i * step))]);
        }
        return picked;
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

    function tagOpColElement(col, th) {
        if (!col) return;
        const w = opColumnWidthPx(th);
        col.classList.remove(
            'crm-col-op', 'crm-col-op-wide', 'crm-col-op-xl',
            'crm-col-rms-jobs-recommend', 'crm-col-rms-jobs-manage', 'rms-delivery-review-op-col',
        );
        if (th && th.classList.contains('rms-delivery-review-op')) {
            col.classList.add('rms-delivery-review-op-col');
        } else if (th && th.closest('.rms-jobs-table') && th.classList.contains('rms-sticky-recommend')) {
            col.classList.add('crm-col-rms-jobs-recommend');
        } else if (th && th.closest('.rms-jobs-table') && th.classList.contains('rms-col-manage')) {
            col.classList.add('crm-col-rms-jobs-manage');
        } else if (th && th.closest('.rms-jobs-table') && th.classList.contains('crm-op-col-xl')) {
            col.classList.add('crm-col-rms-jobs-recommend');
        } else if (th && th.classList.contains('crm-op-col-xl')) col.classList.add('crm-col-op-xl');
        else if (th && th.classList.contains('crm-op-col-wide')) col.classList.add('crm-col-op-wide');
        else col.classList.add('crm-col-op');
        col.style.width = `${w}px`;
        col.style.minWidth = `${w}px`;
        col.style.maxWidth = `${w}px`;
    }

    function tagCheckinColElement(col) {
        if (!col) return;
        col.style.width = `${CHECKIN_COL_WIDTH}px`;
        col.style.minWidth = `${CHECKIN_COL_WIDTH}px`;
        col.style.maxWidth = `${CHECKIN_COL_WIDTH}px`;
    }

    function tagRosterRemarksColElement(col, widthPx) {
        if (!col) return;
        const w = Math.round(widthPx);
        col.style.width = `${w}px`;
        col.style.minWidth = `${w}px`;
        col.style.maxWidth = `${w}px`;
    }

    function tagInterviewTextWideColElement(col, widthPx) {
        tagRosterRemarksColElement(col, widthPx);
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
            return;
        }
        if (table.classList.contains('rms-jobs-table')) {
            table.style.setProperty('--rms-jobs-sticky-serial-width', px(0));
            table.style.setProperty('--rms-jobs-sticky-title-width', px(1));
            return;
        }
        if (table.dataset.tableId === 'customer-visits') {
            const ths = table.querySelectorAll('thead th');
            for (let i = 0; i < 5; i++) {
                const th = ths[i];
                if (!th) break;
                table.style.setProperty(`--visit-sticky-col${i}-left`, `${th.offsetLeft}px`);
                table.style.setProperty(`--visit-sticky-col${i}-width`, `${readColWidth(i)}px`);
            }
            return;
        }
        if (table.dataset.tableId === 'opportunity-leads') {
            const ths = table.querySelectorAll('thead th');
            if (ths[0]) {
                table.style.setProperty('--opp-sticky-col0-width', `${ths[0].offsetWidth}px`);
            }
            if (ths[1]) {
                table.style.setProperty('--opp-sticky-col1-width', `${ths[1].offsetWidth}px`);
                table.style.setProperty('--opp-sticky-col1-left', `${ths[1].offsetLeft}px`);
            }
            return;
        }
    }

    function tableScrollContainerWidth(table) {
        const wrap = table && table.closest
            ? table.closest('.crm-table-scroll, .rms-candidates-scroll, .rms-jobs-scroll')
            : null;
        if (!wrap) return 0;
        const w = wrap.clientWidth || 0;
        return w > 0 ? w : 0;
    }

    function isTableLayoutVisible(table) {
        if (!table) return false;
        const st = window.getComputedStyle(table);
        if (st.display === 'none' || st.visibility === 'hidden') return false;
        const rect = table.getBoundingClientRect();
        return rect.width > 0 || rect.height > 0;
    }

    function flexGrowColumnIndex(ths) {
        const opIdx = opColumnIndex(ths);
        if (opIdx > 0) {
            for (let i = opIdx - 1; i >= 0; i--) {
                if (isCheckinColumnTh(ths[i]) || isRosterRemarksColumnTh(ths[i]) || isInterviewTextWideColumnTh(ths[i]) || isRmsJdColumnTh(ths[i]) || isOpColumnTh(ths[i])) continue;
                const label = (ths[i].textContent || '').trim();
                if (label === '备注' || label === '说明' || label.includes('原因') || label.includes('纪要') || label.includes('沟通')) return i;
            }
            return opIdx - 1;
        }
        return ths.length > 1 ? ths.length - 1 : -1;
    }

    function measureContentWidths(table, ths, cols) {
        const bodyRows = sampleBodyRows(table);
        const savedColWidths = cols.map((col) => col.style.width);
        const prevLayout = table.style.tableLayout;
        const prevWidth = table.style.width;

        cols.forEach((col) => {
            col.style.width = '';
            col.style.minWidth = '';
            col.style.maxWidth = '';
        });
        table.style.tableLayout = 'auto';
        table.style.width = 'max-content';

        const widths = ths.map((th, i) => {
            const pipelinePreset = rmsPipelinePresetColumnWidthPx(th);
            if (pipelinePreset != null) return pipelinePreset;
            if (isOpColumnTh(th)) return opColumnWidthPx(th);
            if (isCheckinColumnTh(th)) return CHECKIN_COL_WIDTH;
            if (isRosterRemarksColumnTh(th)) return rosterRemarksColumnWidthPx(th);
            if (isInterviewTextWideColumnTh(th)) return interviewTextWideColumnWidthPx(th);
            if (isRmsJdColumnTh(th)) {
                return rmsJdDefaultWidthPx(th) + COL_CONTENT_PAD;
            }
            if (th.classList.contains('roster-col-position-zntx')) {
                return Math.max(
                    minWidthForTh(th, MIN_WIDTH),
                    Math.round(cssLengthPx(th, 'width') || cssLengthPx(th, 'minWidth') || 240),
                );
            }
            let w = Math.max(minWidthForTh(th, MIN_WIDTH), measureCellWidth(th));
            bodyRows.forEach((tr) => {
                const cells = tr.querySelectorAll(':scope > td');
                if (cells.length !== ths.length) return;
                const td = cells[i];
                if (!td) return;
                const clip = td.querySelector('.crm-cell-clip');
                const clipTarget = clip && !isInterviewTextWideColumnTh(ths[i])
                    ? (clip.querySelector('.crm-cell-clip-text') || clip)
                    : null;
                w = Math.max(w, measureCellWidth(td), clipTarget ? measureCellWidth(clipTarget) : 0);
            });
            return w + COL_CONTENT_PAD;
        });

        cols.forEach((col, i) => {
            col.style.width = savedColWidths[i];
        });
        table.style.tableLayout = prevLayout || 'fixed';
        if (prevWidth) table.style.width = prevWidth;

        return widths;
    }

    function clampWidthsToContent(table, ths, cols, widths) {
        const mins = measureContentWidths(table, ths, cols);
        const rmsJdIdx = ths.findIndex(isRmsJdColumnTh);
        return widths.map((w, i) => {
            if (rmsJdIdx === i) {
                const def = rmsJdDefaultWidthPx(ths[i]);
                const saved = Number(w) || 0;
                const floor = minWidthForTh(ths[i], MIN_WIDTH) + COL_CONTENT_PAD;
                const cap = def + COL_CONTENT_PAD;
                if (!Number.isFinite(saved) || saved < floor) return cap;
                if (isRequirementsJobsTable(table) && saved > cap) return cap;
                if (saved > def * 2) return cap;
                return saved;
            }
            return Math.max(Number(w) || 0, mins[i]);
        });
    }

    function buildColumnHelpers(table, ths, cols, options) {
        const minW = options?.minWidth ?? MIN_WIDTH;
        const tableMin = Number(table.dataset.tableMinWidth) || 0;
        const readColWidth = (i) => {
            const pipelinePreset = rmsPipelinePresetColumnWidthPx(ths[i]);
            if (isOpColumnTh(ths[i])) return opColumnWidthPx(ths[i]);
            if (isCheckinColumnTh(ths[i])) return CHECKIN_COL_WIDTH;
            if (isRosterRemarksColumnTh(ths[i])) return rosterRemarksColumnWidthPx(ths[i]);
            if (isInterviewTextWideColumnTh(ths[i])) return interviewTextWideColumnWidthPx(ths[i]);
            if (isRmsJdColumnTh(ths[i])) {
                const w = parseFloat(cols[i].style.width);
                if (Number.isFinite(w) && w > 0) return w;
                return rmsJdDefaultWidthPx(ths[i]) + COL_CONTENT_PAD;
            }
            const w = parseFloat(cols[i].style.width);
            if (Number.isFinite(w) && w > 0) return w;
            if (pipelinePreset != null) return pipelinePreset;
            const th = table.querySelector(`thead th.crm-th-resizable[data-col="${i}"], thead th.visit-th-resizable[data-col="${i}"]`);
            return th ? th.offsetWidth : minW;
        };
        const setColWidth = (i, w) => {
            if (isOpColumnTh(ths[i])) {
                tagOpColElement(cols[i], ths[i]);
            } else if (isCheckinColumnTh(ths[i])) {
                tagCheckinColElement(cols[i]);
            } else if (isRosterRemarksColumnTh(ths[i])) {
                tagRosterRemarksColElement(cols[i], rosterRemarksColumnWidthPx(ths[i]));
            } else if (isInterviewTextWideColumnTh(ths[i])) {
                tagInterviewTextWideColElement(cols[i], interviewTextWideColumnWidthPx(ths[i]));
            } else if (isRmsPipelinePresetColumnTh(ths[i])) {
                const floor = minWidthForTh(ths[i], minW);
                const preset = rmsPipelinePresetColumnWidthPx(ths[i]);
                let nextW = Math.max(floor, Math.round(w));
                if (preset != null && (!Number.isFinite(w) || w <= 0)) nextW = preset;
                cols[i].style.width = `${nextW}px`;
                cols[i].style.minWidth = `${nextW}px`;
                cols[i].style.maxWidth = `${nextW}px`;
            } else if (isRmsJdColumnTh(ths[i])) {
                const def = rmsJdDefaultWidthPx(ths[i]) + COL_CONTENT_PAD;
                const floor = minWidthForTh(ths[i], minW);
                let nextW = Math.max(floor, Math.round(w));
                if (nextW > def * 2) nextW = def;
                cols[i].style.width = `${nextW}px`;
                cols[i].style.minWidth = '';
                cols[i].style.maxWidth = '';
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
            const containerW = tableScrollContainerWidth(table);
            const target = Math.max(total, tableMin, containerW);
            let extra = target - total;
            if (extra > 0.5) {
                const flexIdx = flexGrowColumnIndex(ths);
                if (flexIdx >= 0 && !isOpColumnTh(ths[flexIdx]) && !isCheckinColumnTh(ths[flexIdx]) && !isRosterRemarksColumnTh(ths[flexIdx]) && !isInterviewTextWideColumnTh(ths[flexIdx]) && !isRmsJdColumnTh(ths[flexIdx])) {
                    setColWidth(flexIdx, readColWidth(flexIdx) + extra);
                    total = target;
                } else {
                    const growable = [];
                    for (let i = 0; i < cols.length; i += 1) {
                        if (!isOpColumnTh(ths[i]) && !isCheckinColumnTh(ths[i]) && !isRosterRemarksColumnTh(ths[i]) && !isInterviewTextWideColumnTh(ths[i]) && !isRmsJdColumnTh(ths[i])) growable.push(i);
                    }
                    if (growable.length) {
                        const share = extra / growable.length;
                        growable.forEach((i) => {
                            setColWidth(i, readColWidth(i) + share);
                        });
                        total = cols.reduce((sum, _c, idx) => sum + readColWidth(idx), 0);
                    }
                }
            }
            table.style.width = `${Math.max(total, tableMin)}px`;
            syncStickyColumnVars(table, readColWidth);
        };
        return { readColWidth, setColWidth, syncTableWidth };
    }

    /** 按表头 + 表体内容适配列宽，保证默认不重叠 */
    function fitTableColumnsToContent(table, options) {
        if (!table) return false;
        if (!isTableLayoutVisible(table)) return false;
        if (table.dataset.colResizeReady !== '1') {
            initCrmTableColumnResize(table);
        }
        const ths = leafHeaderCells(table);
        if (!ths.length) return false;
        let cols = [...table.querySelectorAll('colgroup col')];
        if (cols.length !== ths.length) cols = ensureColgroup(table, ths.length);
        table.style.tableLayout = 'fixed';
        const { setColWidth, syncTableWidth, readColWidth } = buildColumnHelpers(table, ths, cols, {});
        measureContentWidths(table, ths, cols).forEach((w, i) => setColWidth(i, w));
        syncTableWidth();
        table.dataset.colContentFit = '1';
        if (options?.persist !== false) {
            try {
                const key = storageKeyFor(table);
                localStorage.setItem(key, JSON.stringify(cols.map((_c, idx) => readColWidth(idx))));
            } catch { /* ignore */ }
        }
        window.crmRefreshCellClips?.(table);
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
        applyAllOpColumnWidths(ths, setColWidth);
        syncTableWidth();
        return true;
    }

    function refreshTableColumnWidths(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('table.crm-table, table.visit-table').forEach((table) => {
            if (table.dataset.colResize === 'off') return;
            if (!isTableLayoutVisible(table)) return;
            if (tbodyDataRows(table).length > 0 && table.dataset.colContentFit !== '1') {
                fitTableColumnsToContent(table);
            } else {
                applyOpColumnWidth(table);
            }
        });
    }

    function refreshOpColumnWidths(root) {
        refreshTableColumnWidths(root);
    }

    function initCrmTableColumnResize(table, options) {
        if (!table || table.dataset.colResize === 'off') return false;
        if (table.dataset.colResizeReady === '1') {
            if (!isTableLayoutVisible(table)) return true;
            if (tbodyDataRows(table).length > 0 && table.dataset.colContentFit !== '1') {
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
            if (!isOpColumnTh(th) && !isCheckinColumnTh(th) && !isRosterRemarksColumnTh(th) && !isInterviewTextWideColumnTh(th)) th.classList.add('crm-th-resizable');
        });

        const minW = options?.minWidth ?? MIN_WIDTH;
        const edge = options?.edge ?? RESIZE_EDGE;
        const storageKey = options?.storageKey ?? storageKeyFor(table);
        const hasBodyRows = tbodyDataRows(table).length > 0;

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
        const checkinIdx = checkinColumnIndex(ths);
        const remarksIdx = ths.findIndex(isRosterRemarksColumnTh);
        const interviewTextWideIndices = ths.map((th, i) => (isInterviewTextWideColumnTh(th) ? i : -1)).filter((i) => i >= 0);
        const contentWidths = () => measureContentWidths(table, ths, cols);
        const normalizeSaved = (widths) => {
            const next = [...widths];
            ths.forEach((th, i) => {
                if (isOpColumnTh(th)) next[i] = opColumnWidthPx(th);
            });
            if (checkinIdx >= 0) next[checkinIdx] = CHECKIN_COL_WIDTH;
            if (remarksIdx >= 0) next[remarksIdx] = rosterRemarksColumnWidthPx(ths[remarksIdx]);
            interviewTextWideIndices.forEach((idx) => {
                next[idx] = interviewTextWideColumnWidthPx(ths[idx]);
            });
            const rmsJdIdx = ths.findIndex(isRmsJdColumnTh);
            if (rmsJdIdx >= 0) {
                const def = rmsJdDefaultWidthPx(ths[rmsJdIdx]) + COL_CONTENT_PAD;
                const saved = Number(next[rmsJdIdx]);
                if (!Number.isFinite(saved) || saved < 120) {
                    next[rmsJdIdx] = def;
                } else if (isRequirementsJobsTable(table) && saved > def) {
                    next[rmsJdIdx] = def;
                } else if (saved > def * 2) {
                    next[rmsJdIdx] = def;
                }
            }
            return next;
        };
        if (hasBodyRows) {
            if (Array.isArray(saved) && saved.length === cols.length) {
                applyWidths(clampWidthsToContent(table, ths, cols, normalizeSaved(saved)));
                table.dataset.colContentFit = '1';
            } else if (Array.isArray(options?.defaults) && options.defaults.length === cols.length) {
                applyWidths(clampWidthsToContent(table, ths, cols, normalizeSaved(options.defaults)));
                table.dataset.colContentFit = '1';
            } else {
                fitTableColumnsToContent(table);
            }
        } else if (Array.isArray(saved) && saved.length === cols.length) {
            applyWidths(clampWidthsToContent(table, ths, cols, normalizeSaved(saved)));
        } else if (Array.isArray(options?.defaults) && options.defaults.length === cols.length) {
            applyWidths(clampWidthsToContent(table, ths, cols, normalizeSaved(options.defaults)));
        } else {
            applyWidths(contentWidths());
        }
        if (!hasBodyRows) {
            applyAllOpColumnWidths(ths, setColWidth);
            if (checkinIdx >= 0) setColWidth(checkinIdx, CHECKIN_COL_WIDTH);
            if (remarksIdx >= 0) setColWidth(remarksIdx, rosterRemarksColumnWidthPx(ths[remarksIdx]));
            interviewTextWideIndices.forEach((idx) => {
                setColWidth(idx, interviewTextWideColumnWidthPx(ths[idx]));
            });
            syncTableWidth();
        }

        const persistWidths = () => {
            const payload = cols.map((_c, i) => readColWidth(i));
            ths.forEach((th, i) => {
                if (isOpColumnTh(th)) payload[i] = opColumnWidthPx(th);
            });
            if (checkinIdx >= 0) payload[checkinIdx] = CHECKIN_COL_WIDTH;
            if (remarksIdx >= 0) payload[remarksIdx] = rosterRemarksColumnWidthPx(ths[remarksIdx]);
            interviewTextWideIndices.forEach((idx) => {
                payload[idx] = interviewTextWideColumnWidthPx(ths[idx]);
            });
            localStorage.setItem(storageKey, JSON.stringify(payload));
        };

        const startResize = (th, colIndex, startX) => {
            if (isOpColumnTh(ths[colIndex]) || isCheckinColumnTh(ths[colIndex]) || isRosterRemarksColumnTh(ths[colIndex]) || isInterviewTextWideColumnTh(ths[colIndex])) return;
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
            if (isOpColumnTh(th) || isCheckinColumnTh(th) || isRosterRemarksColumnTh(th) || isInterviewTextWideColumnTh(th)) return;

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

    function ensureRmsJobsTableColumns(table) {
        if (!table || table.dataset.tableId !== 'rms-jobs') return false;
        if (table.dataset.colResizeReady !== '1') {
            return initCrmTableColumnResize(table);
        }
        if (!tbodyDataRows(table).length) return false;
        const ths = leafHeaderCells(table);
        const rmsJdIdx = ths.findIndex(isRmsJdColumnTh);
        if (rmsJdIdx < 0) return false;
        let cols = [...table.querySelectorAll('colgroup col')];
        if (cols.length !== ths.length) cols = ensureColgroup(table, ths.length);
        const { setColWidth, syncTableWidth, readColWidth } = buildColumnHelpers(table, ths, cols, {});
        applyAllOpColumnWidths(ths, setColWidth);
        const def = rmsJdDefaultWidthPx(ths[rmsJdIdx]) + COL_CONTENT_PAD;
        const current = readColWidth(rmsJdIdx);
        if (!Number.isFinite(current) || current < 120 || current > def * 2) {
            setColWidth(rmsJdIdx, def);
            syncTableWidth();
            try {
                localStorage.setItem(storageKeyFor(table), JSON.stringify(cols.map((_c, i) => readColWidth(i))));
            } catch { /* ignore */ }
        } else {
            syncTableWidth();
        }
        return true;
    }

    function ensureRmsCandidatesTableColumns(table) {
        if (!table || table.dataset.tableId !== 'rms-candidates') return false;
        if (table.dataset.colResizeReady !== '1') {
            return initCrmTableColumnResize(table);
        }
        if (!isTableLayoutVisible(table)) return false;
        const ths = leafHeaderCells(table);
        if (!ths.length) return false;
        let cols = [...table.querySelectorAll('colgroup col')];
        if (cols.length !== ths.length) cols = ensureColgroup(table, ths.length);
        const storageKey = storageKeyFor(table);
        const { readColWidth, setColWidth, syncTableWidth } = buildColumnHelpers(table, ths, cols, {});
        let saved = null;
        try {
            saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
        } catch {
            saved = null;
        }
        const normalizeSaved = (widths) => {
            const next = [...widths];
            ths.forEach((th, i) => {
                if (isOpColumnTh(th)) next[i] = opColumnWidthPx(th);
            });
            return next;
        };
        if (Array.isArray(saved) && saved.length === cols.length) {
            const widths = clampWidthsToContent(table, ths, cols, normalizeSaved(saved));
            widths.forEach((w, i) => setColWidth(i, w));
            syncTableWidth();
            table.dataset.colContentFit = '1';
        } else if (tbodyDataRows(table).length > 0) {
            fitTableColumnsToContent(table);
        } else {
            applyAllOpColumnWidths(ths, setColWidth);
            syncTableWidth();
        }
        return true;
    }

    function ensureRmsPipelineTableColumns(table) {
        if (!table || table.dataset.tableId !== 'rms-pipeline') return false;
        if (table.dataset.colResizeReady !== '1') {
            return initCrmTableColumnResize(table);
        }
        if (!isTableLayoutVisible(table)) return false;
        const ths = leafHeaderCells(table);
        if (!ths.length) return false;
        let cols = [...table.querySelectorAll('colgroup col')];
        if (cols.length !== ths.length) cols = ensureColgroup(table, ths.length);
        const storageKey = storageKeyFor(table);
        const { readColWidth, setColWidth, syncTableWidth } = buildColumnHelpers(table, ths, cols, {});
        let saved = null;
        try {
            saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
        } catch {
            saved = null;
        }
        const normalizeSaved = (widths) => {
            const next = [...widths];
            ths.forEach((th, i) => {
                if (isOpColumnTh(th)) next[i] = opColumnWidthPx(th);
            });
            return next;
        };
        if (Array.isArray(saved) && saved.length === cols.length) {
            saved.forEach((w, i) => setColWidth(i, w));
            syncTableWidth();
            table.dataset.colContentFit = '1';
        } else {
            applyAllOpColumnWidths(ths, setColWidth);
            syncTableWidth();
        }
        return true;
    }

    window.crmInitTableColumnResize = initCrmTableColumnResize;
    window.crmEnsureRmsCandidatesTableColumns = ensureRmsCandidatesTableColumns;
    window.crmEnsureRmsPipelineTableColumns = ensureRmsPipelineTableColumns;
    window.crmEnsureRmsJobsTableColumns = ensureRmsJobsTableColumns;
    window.crmInitAllTableColumnResize = initAll;
    window.crmScheduleTableColumnResize = schedule;
    window.crmRefreshOpColumnWidths = refreshOpColumnWidths;
    window.crmFitTableColumnsToContent = fitTableColumnsToContent;

    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => schedule(document), 80);
        setTimeout(() => schedule(document), 700);
        setTimeout(() => refreshTableColumnWidths(document), 1500);
    });
})();
