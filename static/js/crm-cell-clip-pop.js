/**
 * 表格长文本：单行省略，仅在内容展示不全时悬停显示灰色浮层。
 * 配合 base.html 中 .crm-cell-clip / .crm-cell-clip-text / .crm-cell-clip-pop 使用。
 */
(function () {
    const EMPTY_MARKERS = new Set(['', '—', '-', '–']);

    function isTruncated(textEl) {
        if (!textEl) return false;
        return textEl.scrollWidth > textEl.clientWidth + 1;
    }

    function normalizeClip(el) {
        if (!el || !el.classList.contains('crm-cell-clip')) return null;

        el.querySelectorAll('.crm-cell-clip-text .crm-cell-clip-pop').forEach((nested) => {
            el.appendChild(nested);
        });

        let textEl = el.querySelector(':scope > .crm-cell-clip-text');
        if (!textEl) {
            textEl = document.createElement('span');
            textEl.className = 'crm-cell-clip-text';
            const orphanPops = [];
            while (el.firstChild) {
                const child = el.removeChild(el.firstChild);
                if (child.nodeType === 1 && child.classList.contains('crm-cell-clip-pop')) {
                    orphanPops.push(child);
                } else {
                    textEl.appendChild(child);
                }
            }
            el.appendChild(textEl);
            orphanPops.forEach((p) => el.appendChild(p));
        }

        const pops = [...el.querySelectorAll(':scope > .crm-cell-clip-pop')];
        let pop = pops[0];
        if (!pop) {
            pop = document.createElement('span');
            pop.className = 'crm-cell-clip-pop';
            pop.setAttribute('aria-hidden', 'true');
            el.appendChild(pop);
        }
        pops.slice(1).forEach((p) => p.remove());

        el.dataset.clipReady = '1';
        return el;
    }

    function syncClip(el) {
        if (!el) return;
        normalizeClip(el);
        const textEl = el.querySelector(':scope > .crm-cell-clip-text');
        const pop = el.querySelector(':scope > .crm-cell-clip-pop');
        if (!textEl || !pop) return;
        const raw = (textEl.textContent || '').trim();
        pop.textContent = raw;
        const empty = EMPTY_MARKERS.has(raw);
        el.classList.toggle('crm-cell-clip--empty', empty);
    }

    function openPop(el) {
        syncClip(el);
        if (el.classList.contains('crm-cell-clip--empty')) return;
        const textEl = el.querySelector(':scope > .crm-cell-clip-text');
        if (!isTruncated(textEl)) return;
        el.classList.add('is-pop-open');
        const cell = el.closest('td, .visit-td');
        if (cell) {
            cell.classList.add('crm-cell-clip-td-open');
            const row = cell.closest('tr');
            if (row) row.classList.add('crm-cell-clip-tr-open');
        }
    }

    function closePop(el) {
        if (!el) return;
        el.classList.remove('is-pop-open');
        const cell = el.closest('td, .visit-td');
        if (cell) {
            cell.classList.remove('crm-cell-clip-td-open');
            const row = cell.closest('tr');
            if (row) row.classList.remove('crm-cell-clip-tr-open');
        }
    }

    function scan(root) {
        const scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.crm-cell-clip').forEach((el) => {
            syncClip(el);
        });
    }

    document.addEventListener('mouseover', (event) => {
        const clip = event.target.closest('.crm-cell-clip');
        if (!clip) return;
        const from = event.relatedTarget;
        if (from && clip.contains(from)) return;
        openPop(clip);
    });

    document.addEventListener('mouseout', (event) => {
        const clip = event.target.closest('.crm-cell-clip');
        if (!clip) return;
        const to = event.relatedTarget;
        if (to && clip.contains(to)) return;
        closePop(clip);
    });

    let observerScheduled = false;
    function scheduleScan() {
        if (observerScheduled) return;
        observerScheduled = true;
        requestAnimationFrame(() => {
            observerScheduled = false;
            scan(document);
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        scan(document);
        const observer = new MutationObserver(scheduleScan);
        observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    });

    window.crmRefreshCellClips = scan;
})();
