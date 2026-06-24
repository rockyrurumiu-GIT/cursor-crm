/**
 * 表格长文本：单行省略，仅在内容展示不全时悬停显示灰色浮层。
 * 配合 base.html 中 .crm-cell-clip / .crm-cell-clip-text / .crm-cell-clip-pop 使用。
 */
(function () {
    const EMPTY_MARKERS = new Set(['', '—', '-', '–']);
    const VIEWPORT_PAD = 12;

    let portalPopHost = null;
    let portalPopEl = null;
    let portalScrollParents = [];
    let portalScrollHandler = null;
    let portalCopyBtn = null;
    let copyResetTimer = null;

    const COPY_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
    const CHECK_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"></path></svg>';

    function isTruncated(textEl) {
        if (!textEl) return false;
        return textEl.scrollWidth > textEl.clientWidth + 1;
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }
        return new Promise((resolve, reject) => {
            try {
                const ta = document.createElement('textarea');
                ta.value = text;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                resolve();
            } catch (err) {
                reject(err);
            }
        });
    }

    function ensureCopyBtn() {
        if (portalCopyBtn) return portalCopyBtn;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'crm-clip-copy-btn';
        btn.title = '复制内容';
        btn.setAttribute('aria-label', '复制内容');
        btn.innerHTML = COPY_ICON;
        btn.addEventListener('mousedown', (e) => e.preventDefault());
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const text = portalPopEl ? (portalPopEl.__clipText || portalPopEl.textContent || '') : '';
            if (!text) return;
            copyText(text).then(() => {
                btn.classList.add('is-copied');
                btn.innerHTML = CHECK_ICON;
                btn.title = '已复制';
                if (copyResetTimer) clearTimeout(copyResetTimer);
                copyResetTimer = setTimeout(() => {
                    btn.classList.remove('is-copied');
                    btn.innerHTML = COPY_ICON;
                    btn.title = '复制内容';
                }, 1200);
            }).catch(() => {});
        });
        document.body.appendChild(btn);
        portalCopyBtn = btn;
        return btn;
    }

    function showCopyBtn(left, top, width) {
        const btn = ensureCopyBtn();
        const inset = 10;
        btn.style.left = `${Math.round(left + width - 26 - inset)}px`;
        btn.style.top = `${Math.round(top + 8)}px`;
        btn.classList.add('is-visible');
    }

    function hideCopyBtn() {
        if (!portalCopyBtn) return;
        portalCopyBtn.classList.remove('is-visible', 'is-copied');
        portalCopyBtn.innerHTML = COPY_ICON;
        portalCopyBtn.title = '复制内容';
        if (copyResetTimer) {
            clearTimeout(copyResetTimer);
            copyResetTimer = null;
        }
    }

    function portalScrollContainers(clip) {
        const out = [];
        let node = clip.parentElement;
        while (node && node !== document.body) {
            const style = getComputedStyle(node);
            const oy = style.overflowY;
            const ox = style.overflowX;
            const o = style.overflow;
            if (/(auto|scroll|overlay)/.test(`${o}${ox}${oy}`)) out.push(node);
            node = node.parentElement;
        }
        return out;
    }

    function tableStickyHeadBottom(cell) {
        const table = cell && cell.closest('table');
        if (!table || !table.closest('.crm-table-scroll')) return 0;
        const thead = table.querySelector('thead');
        if (!thead) return 0;
        return thead.getBoundingClientRect().bottom;
    }

    function popWidthPx(clip, cellRect, pop) {
        const vw = window.innerWidth;
        const pad = VIEWPORT_PAD;
        const rootPx = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
        const maxW = vw - pad * 2;
        const preferred = Math.min(26 * rootPx, maxW);
        let contentW = 0;
        if (pop) {
            const prevWidth = pop.style.width;
            const prevMaxWidth = pop.style.maxWidth;
            pop.style.width = 'max-content';
            pop.style.maxWidth = `${maxW}px`;
            contentW = pop.scrollWidth;
            pop.style.width = prevWidth;
            pop.style.maxWidth = prevMaxWidth;
        }
        const target = contentW
            ? Math.max(cellRect.width, Math.min(preferred, contentW))
            : Math.max(cellRect.width, preferred);
        return Math.min(target, maxW);
    }

    function popLeftPx(clip, rect, width) {
        const vw = window.innerWidth;
        const pad = VIEWPORT_PAD;
        let left = rect.left;
        if (clip.classList.contains('crm-cell-clip--anchor-right')) {
            left = rect.right - width;
        }
        return Math.max(pad, Math.min(left, vw - width - pad));
    }

    function applyPortalGeometry(clip, pop) {
        const cell = clip.closest('td, .visit-td');
        if (!pop || !cell) return;

        const anchor = clip.getBoundingClientRect();
        const cellRect = cell.getBoundingClientRect();
        const vh = window.innerHeight;
        const pad = VIEWPORT_PAD;
        const headBottom = tableStickyHeadBottom(cell);
        const minTop = headBottom > 0 ? headBottom + 2 : pad;
        const anchorTop = Math.max(anchor.top, minTop);
        const spaceBelow = vh - anchorTop - pad;
        const spaceAbove = anchor.bottom - minTop;
        const viewportMax = vh - pad * 2;
        const width = popWidthPx(clip, cellRect, pop);

        pop.style.left = `${popLeftPx(clip, anchor, width)}px`;
        pop.style.width = `${width}px`;
        pop.style.overflowY = 'auto';
        pop.style.pointerEvents = 'auto';

        // 用最终宽度测量全文所需高度（含 +2px 缓冲，避免最后一行被裁）
        pop.style.visibility = 'hidden';
        pop.style.top = `${anchorTop}px`;
        pop.style.maxHeight = `${viewportMax}px`;
        const needH = pop.scrollHeight + 2;
        pop.style.visibility = '';

        let top;
        let maxH;
        if (needH <= spaceBelow) {
            top = anchorTop;
            maxH = needH;
        } else if (needH <= spaceAbove) {
            top = Math.max(minTop, anchor.bottom - needH);
            maxH = needH;
        } else if (spaceAbove >= spaceBelow) {
            top = minTop;
            maxH = Math.max(80, spaceAbove);
        } else {
            top = anchorTop;
            maxH = Math.max(80, spaceBelow);
        }

        maxH = Math.min(Math.max(80, maxH), viewportMax);
        top = Math.max(minTop, Math.min(top, vh - maxH - pad));

        pop.style.top = `${top}px`;
        pop.style.maxHeight = `${maxH}px`;

        showCopyBtn(parseFloat(pop.style.left) || anchor.left, top, width);
    }

    function resetPortalPop(pop) {
        if (!pop) return;
        pop.classList.remove('crm-cell-clip-pop--fixed');
        pop.style.left = '';
        pop.style.top = '';
        pop.style.width = '';
        pop.style.maxHeight = '';
        pop.style.overflowY = '';
        pop.style.pointerEvents = '';
        pop.style.visibility = '';
    }

    function isPortalPopTarget(node) {
        return !!(node && portalPopEl && (node === portalPopEl || portalPopEl.contains(node)));
    }

    function shouldKeepPortalOpen(to) {
        if (!to) return false;
        if (isPortalPopTarget(to)) return true;
        if (portalCopyBtn && (to === portalCopyBtn || portalCopyBtn.contains(to))) return true;
        if (!portalPopHost) return false;
        if (portalPopHost.contains(to)) return true;
        const cell = portalPopHost.closest('td, .visit-td');
        return !!(cell && cell.contains(to));
    }

    function unbindPortalScroll() {
        if (portalScrollHandler) {
            portalScrollParents.forEach((el) => {
                el.removeEventListener('scroll', portalScrollHandler);
            });
            window.removeEventListener('resize', portalScrollHandler);
        }
        portalScrollParents = [];
        portalScrollHandler = null;
    }

    function bindPortalScroll(clip) {
        unbindPortalScroll();
        portalScrollHandler = () => {
            if (portalPopHost === clip && portalPopEl && clip.classList.contains('is-pop-open')) {
                applyPortalGeometry(clip, portalPopEl);
            }
        };
        portalScrollParents = portalScrollContainers(clip);
        portalScrollParents.forEach((el) => {
            el.addEventListener('scroll', portalScrollHandler, { passive: true });
        });
        window.addEventListener('resize', portalScrollHandler, { passive: true });
    }

    function mountPortalPop(clip) {
        let pop = clip.querySelector(':scope > .crm-cell-clip-pop');
        if (!pop && portalPopHost === clip && portalPopEl) pop = portalPopEl;
        if (!pop) return;
        portalPopHost = clip;
        portalPopEl = pop;
        if (pop.parentElement !== document.body) {
            document.body.appendChild(pop);
        }
        pop.classList.add('crm-cell-clip-pop--fixed');
        applyPortalGeometry(clip, pop);
        bindPortalScroll(clip);
    }

    function unmountPortalPop(clip) {
        if (!portalPopEl || portalPopHost !== clip) return;
        hideCopyBtn();
        resetPortalPop(portalPopEl);
        clip.appendChild(portalPopEl);
        portalPopEl = null;
        portalPopHost = null;
        unbindPortalScroll();
    }

    function normalizeClip(el) {
        if (!el || !el.classList.contains('crm-cell-clip')) return null;

        if (portalPopHost === el && portalPopEl) {
            el.dataset.clipReady = '1';
            return el;
        }

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
        if (portalPopHost === el) return;
        normalizeClip(el);
        const textEl = el.querySelector(':scope > .crm-cell-clip-text');
        const pop = el.querySelector(':scope > .crm-cell-clip-pop');
        if (!textEl || !pop) return;
        const raw = (textEl.textContent || '').trim();
        pop.textContent = raw;
        pop.__clipText = raw;
        const empty = EMPTY_MARKERS.has(raw);
        el.classList.toggle('crm-cell-clip--empty', empty);
    }

    function openPop(el) {
        if (portalPopHost && portalPopHost !== el) {
            closePop(portalPopHost);
        }
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
        requestAnimationFrame(() => {
            if (!el.classList.contains('is-pop-open')) return;
            mountPortalPop(el);
        });
    }

    function closePop(el) {
        if (!el) return;
        if (portalPopHost === el) unmountPortalPop(el);
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
        const fromPop = event.target.closest('.crm-cell-clip-pop--fixed');
        const fromBtn = portalCopyBtn && (event.target === portalCopyBtn || portalCopyBtn.contains(event.target));
        const clipEl = clip || ((fromPop || fromBtn) && portalPopHost);
        if (!clipEl) return;
        const to = event.relatedTarget;
        if (shouldKeepPortalOpen(to)) return;
        closePop(clipEl);
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
