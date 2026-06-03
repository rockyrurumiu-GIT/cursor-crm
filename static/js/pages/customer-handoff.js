(function () {
    const { createApp, ref, computed, onMounted } = Vue;
    const cfg = window.__CRM_HANDOFF__ || {};
    const clientId = cfg.clientId;
    let initialHandoffId = cfg.handoffId;

    createApp({
        setup() {
            const auth = () => window.crmAuthHeader();
            const loading = ref(true);
            const clientName = ref('');
            const handoffs = ref([]);
            const handoff = ref(null);
            const selectedId = ref(null);
            const config = ref({ reject_codes: [], spec: { enums: {} }, is_reviewer: false, llm_available: false });
            const step = ref(0);
            const steps = ['上下文', '技术栈', '岗位矩阵', '交付与商务'];
            const form = ref({ title: '', source_text: '', delivery_owner: '', requirement: emptyReq() });
            const logs = ref([]);
            const aiLoading = ref(false);
            const aiBrief = ref('');
            const aiGaps = ref([]);
            const showReject = ref(false);
            const rejectForm = ref({ code: 'REQ_INCOMPLETE', detail: '' });

            function emptyReq() {
                return {
                    context: { project_type: '', location: '', timezone: '', attendance_rules: '', client_contact: '' },
                    tech_stack: { languages: [], middleware: [], version_constraints: '', env_requirements: '' },
                    positions: [],
                    delivery_constraints: { sla: '', acceptance: '', compliance: '', risk_notes: '' },
                    commercial: { quote_ref: '', estimated_amount: '', payment_cycle: '', has_po: false, has_framework: false },
                    urgent: false,
                };
            }

            const spec = computed(() => config.value.spec || { enums: {} });
            const editable = computed(() => handoff.value && ['draft', 'rejected'].includes(handoff.value.status));
            const canReview = computed(() => config.value.is_reviewer && handoff.value && handoff.value.status === 'pending_review');
            const canCreate = computed(() => !handoff.value || handoff.value.status === 'approved');

            const langsStr = computed(() => (form.value.requirement.tech_stack.languages || []).join(', '));
            const mwStr = computed(() => (form.value.requirement.tech_stack.middleware || []).join(', '));

            const setLangs = (e) => {
                form.value.requirement.tech_stack.languages = e.target.value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
            };
            const setMw = (e) => {
                form.value.requirement.tech_stack.middleware = e.target.value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
            };
            const onEstimatedAmountInput = (e) => {
                const digits = String(e && e.target ? e.target.value : '').replace(/[^\d]/g, '');
                form.value.requirement.commercial.estimated_amount = digits ? Number(digits).toLocaleString('zh-CN') : '';
            };

            const statusBadge = (s) => ({
                draft: 'bg-gray-100 text-gray-700',
                pending_review: 'bg-amber-100 text-amber-800',
                rejected: 'bg-red-100 text-red-800',
                approved: 'bg-green-100 text-green-800',
            }[s] || 'bg-gray-100');

            const loadConfig = async () => {
                const r = await fetch('/api/handoff/config', { headers: auth() });
                if (r.ok) config.value = await r.json();
            };

            const loadClient = async () => {
                const r = await fetch('/api/clients/' + clientId, { headers: auth() });
                if (r.ok) {
                    const c = await r.json();
                    clientName.value = c.name;
                }
            };

            const loadHandoffList = async () => {
                const r = await fetch('/api/clients/' + clientId + '/handoffs', { headers: auth() });
                handoffs.value = r.ok ? await r.json() : [];
                if (!selectedId.value && handoffs.value.length) {
                    selectedId.value = initialHandoffId || handoffs.value[0].id;
                }
            };

            const syncFormFromHandoff = (h) => {
                handoff.value = h;
                form.value = {
                    title: h.title,
                    source_text: h.source_text,
                    delivery_owner: h.delivery_owner,
                    requirement: JSON.parse(JSON.stringify(h.requirement)),
                };
                logs.value = h.logs || [];
                aiBrief.value = h.ai_brief_md || '';
                try { aiGaps.value = h.ai_gap_flags || []; } catch (e) { aiGaps.value = []; }
            };

            const loadHandoff = async () => {
                if (!selectedId.value) return;
                loading.value = true;
                const r = await fetch('/api/handoffs/' + selectedId.value, { headers: auth() });
                if (r.ok) syncFormFromHandoff(await r.json());
                loading.value = false;
            };

            const createHandoff = async () => {
                const r = await fetch('/api/clients/' + clientId + '/handoffs', { method: 'POST', headers: auth() });
                const d = await r.json();
                if (!r.ok) { alert(d.detail || '创建失败'); return; }
                await loadHandoffList();
                selectedId.value = d.id;
                await loadHandoff();
            };

            const payload = () => ({
                // 金额输入框允许千分位展示，提交时去掉分隔符。
                requirement: {
                    ...form.value.requirement,
                    commercial: {
                        ...form.value.requirement.commercial,
                        estimated_amount: String(form.value.requirement.commercial.estimated_amount || '').replace(/[,\s]/g, ''),
                    },
                },
                title: form.value.title,
                source_text: form.value.source_text,
                delivery_owner: form.value.delivery_owner,
            });

            const saveDraft = async () => {
                const r = await fetch('/api/handoffs/' + selectedId.value, {
                    method: 'PUT', headers: { ...auth(), 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload()),
                });
                const d = await r.json();
                if (r.ok) { syncFormFromHandoff({ ...d, logs: logs.value }); alert('已保存'); }
                else alert(d.detail || '保存失败');
            };

            const submitHandoff = async () => {
                await saveDraft();
                const r = await fetch('/api/handoffs/' + selectedId.value + '/submit', { method: 'POST', headers: auth() });
                const d = await r.json();
                if (r.ok) { syncFormFromHandoff({ ...d, logs: logs.value }); alert('已提交审批'); await loadHandoffList(); }
                else alert(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail));
            };

            const approveHandoff = async () => {
                if (!confirm('确认通过该交接单？')) return;
                const r = await fetch('/api/handoffs/' + selectedId.value + '/approve', { method: 'POST', headers: auth() });
                const d = await r.json();
                if (r.ok) { await loadHandoff(); await loadHandoffList(); alert('已通过'); }
                else alert(d.detail || '操作失败');
            };

            const confirmReject = async () => {
                if (!rejectForm.value.detail.trim()) { alert('请填写驳回说明'); return; }
                const r = await fetch('/api/handoffs/' + selectedId.value + '/reject', {
                    method: 'POST', headers: { ...auth(), 'Content-Type': 'application/json' },
                    body: JSON.stringify(rejectForm.value),
                });
                const d = await r.json();
                if (r.ok) { showReject.value = false; await loadHandoff(); await loadHandoffList(); }
                else alert(d.detail || '驳回失败');
            };

            const aiParse = async () => {
                aiLoading.value = true;
                const r = await fetch('/api/handoffs/' + selectedId.value + '/ai/parse', {
                    method: 'POST', headers: { ...auth(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: form.value.source_text }),
                });
                const d = await r.json();
                aiLoading.value = false;
                if (d.ok && d.handoff) syncFormFromHandoff({ ...d.handoff, logs: logs.value });
                else alert(d.error || d.detail || 'AI 解析失败');
            };

            const aiReviewAssist = async () => {
                aiLoading.value = true;
                const r = await fetch('/api/handoffs/' + selectedId.value + '/ai/review-assist', { method: 'POST', headers: auth() });
                const d = await r.json();
                aiLoading.value = false;
                if (d.ok) { aiBrief.value = d.brief_md; aiGaps.value = d.gaps || []; }
                else alert(d.error || '生成失败');
            };

            const adoptReject = () => {
                const text = aiGaps.value.map(g => g.suggestion || g.field).join('\n');
                rejectForm.value.detail = text;
                showReject.value = true;
            };

            const addPosition = () => {
                form.value.requirement.positions.push({
                    role: '', level: '', headcount: 1, billing_unit: '人月', start_date: '', skills: '',
                });
            };
            const requestRemovePosition = async (idx) => {
                if (!editable.value) return;
                const list = form.value?.requirement?.positions || [];
                const p = list[idx] || {};
                if (idx >= 0 && idx < list.length) list.splice(idx, 1);
            };

            const syncPipeline = async () => {
                const r = await fetch('/api/handoffs/' + selectedId.value + '/sync-pipeline-demand', { method: 'POST', headers: auth() });
                const d = await r.json();
                if (r.ok) alert('已同步 ' + d.synced + ' 条需求');
                else alert(d.detail || '同步失败');
            };

            onMounted(async () => {
                await loadConfig();
                await loadClient();
                await loadHandoffList();
                if (selectedId.value) await loadHandoff();
                else loading.value = false;
            });

            return {
                loading, clientId, clientName, handoffs, handoff, selectedId, config, step, steps, form, logs,
                spec, editable, canReview, canCreate, langsStr, mwStr, setLangs, setMw, statusBadge,
                aiLoading, aiBrief, aiGaps, showReject, rejectForm,
                loadHandoff, createHandoff, saveDraft, submitHandoff, approveHandoff, confirmReject,
                aiParse, aiReviewAssist, adoptReject, addPosition, requestRemovePosition, syncPipeline, onEstimatedAmountInput,
            };
        },
    }).mount('#handoff-app');
})();
