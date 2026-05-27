# Phase 5E Closeout — delivery_detail 前端拆分收尾

**状态：PASS（Phase 5E 可结束）**
**日期：2026-05-27**

## 1) 结论摘要

| 问题 | 结论 |
|------|------|
| **Phase 5E 是否完成？** | **是** — Step 1–4、6 已编码拆分；Step 5 roster 适用性 N/A 已闭环 |
| **是否还需拆 requirements？** | **否** — 仅 `requirementsSummary` + 一次 `GET /approved-handoff-summary`；无独立业务方法/弹窗/导入导出 |
| **`delivery_detail.html` 还剩多少行？** | **2170**（DOM ~1768 + 配置 8 + inline `createApp` **382**） |
| **剩余 inline 性质？** | **主要是装配层**（四模块 `createXxxState` 解构、`return` 暴露、`onMounted` 编排）+ 少量 **glue**（`scrollToTop`、文档点击关闭、`requirements` fetch） |
| **下一阶段建议** | 结束 5E；后续可选：为 requirements 单独立项（仅当 tab 功能膨胀时）、或转向 plan/26 外其他页面（如 `delivery_turnover.html` 仍 >1200 行） |

---

## 2) 文件行数统计

| 文件 | 行数 |
|------|------|
| `templates/pages/delivery_detail.html` | **2170** |
| `static/js/pages/delivery-detail.js` | **203** |
| `static/js/pages/delivery-detail-settlement.js` | **252** |
| `static/js/pages/delivery-detail-pipeline.js` | **703** |
| `static/js/pages/delivery-detail-interviews.js` | **996** |
| `static/js/pages/delivery-detail-handbook.js` | **796** |
| **外置 JS 小计** | **2950** |

**对比（plan/26 基线）：** `delivery_detail.html` 由约 **4394** 行降至 **2170**（约 **−50%**）。`check_file_sizes.py` 对 `delivery_detail.html` **无 warning**（>1200 的仍是独立页 `delivery_turnover.html` 等）。

### `delivery_detail.html` 结构拆分

| 区段 | 约行 | 说明 |
|------|------|------|
| HTML / Vue 模板 | 1–1768 | 各 tab DOM（未改结构） |
| `window.__CRM_DELIVERY_DETAIL__` | 1770–1776 | 页面配置（保留 inline） |
| inline `createApp` | 1787–2168 | **382 行** — 见下节 |

---

## 3) 剩余 inline 业务逻辑分析

### 3.1 `rg` 要点（`templates/pages/delivery_detail.html`）

| 模式 | 结果 |
|------|------|
| `requirementsSummary` / `approved-handoff-summary` / `moduleKey === 'requirements'` | 模板展示 + `ref(null)` + `onMounted` 内 **1 次** `fetch` |
| `fetch(` | **仅** `/api/clients/{clientId}/approved-handoff-summary`（在 inline 中） |
| `createSettlementState` / `createPipelineState` / `createInterviewState` / `createHandbookState` | 各 **1 处** 装配 |
| `function flattenHandbookOutline` / `const handbookUploadMeta =` / `const pipelineRows =` 等**实现** | **无** |

### 3.2 inline 中仍存在的函数（非模块业务）

| 符号 | 行号约 | 性质 |
|------|--------|------|
| `loadBrief` | 1815 | 委托 `CrmDeliveryDetail.loadClientBrief` |
| `scrollToTop` | 2063–2071 | 组合 pipeline/interviews 回到顶部（glue） |
| `handleDocumentClick` / `handleDocumentFocusIn` | 2072–2079 | 组合关闭 pipeline/interview 下拉（glue） |
| `onMounted` / `onBeforeUnmount` | 2080–2106 | 生命周期编排：加载各模块数据、`mountHandbook`/`unmountHandbook`、requirements fetch |
| `return { ... }` | 2107–2166 | 模板绑定符号暴露（装配） |

**无** `const xxx = async () => { ... }` 形式的长业务方法块（除上述 glue）。

### 3.3 requirements 是否单独拆？

**建议：不拆。**

| 维度 | 现状 |
|------|------|
| State | `requirementsSummary = ref(null)` |
| API | `GET /api/clients/{clientId}/approved-handoff-summary`（仅 `moduleKey === 'requirements'` 时） |
| 模板 | 只读展示 `brief_md`、`positions` 等，无 CRUD/导入/弹窗 |
| 复杂度 | 远低于已外置的 pipeline/interviews/handbook |

若未来 requirements tab 增加编辑、导入或大量 computed，再单独立项 `delivery-detail-requirements.js`；**不属于 5E 收尾阻塞项**。

---

## 4) 已迁移模块残留检查

| 模块 | inline 中是否仍有**实现** | 装配 / `return` 暴露 |
|------|---------------------------|----------------------|
| settlement | **无** | `createSettlementState` + 解构 + `return` |
| pipeline | **无** | `createPipelineState` + 解构 + `return` |
| interviews | **无** | `createInterviewState` + 解构 + `return` |
| handbook | **无** | `createHandbookState` + 解构 + `return` |
| roster (5E Step 5) | N/A（无 delivery tab） | 仅 interviews 内 roster 提示 API |

模板中出现的 `handbookUploadMeta`、`PIPELINE_*` 等均为 **v-model / @click 绑定**，符号由模块 `return` 注入，**非** inline 实现。

---

## 5) Step 1–6 与 plan/26 对齐

| Step | 内容 | 状态 |
|------|------|------|
| 1 | `delivery-detail.js` 初始化 / 共享 helper | PASS — [phase-05-step-01](phase-05-step-01-delivery-init-report.md) |
| 2 | settlement 嵌入 | PASS — [phase-05-step-02](phase-05-step-02-delivery-settlement-report.md) |
| 3 | pipeline | PASS — [phase-05-step-03](phase-05-step-03-delivery-pipeline-report.md) |
| 3.1 | 共享 `fuzzyMatch` / `uniqueSorted` | PASS — [phase-05-step-03-1](phase-05-step-03-1-shared-helpers-report.md) |
| 4 | interviews | PASS — [phase-05-step-04](phase-05-step-04-delivery-interviews-report.md) |
| 5 | roster | **N/A**（适用性）— [phase-05-step-05](phase-05-step-05-roster-applicability-report.md) |
| 6 | handbook | PASS — [phase-05-step-06](phase-05-step-06-delivery-handbook-report.md) |

plan/26 中的 `delivery-detail-roster.js` **不应**在 5E 执行（无 delivery roster tab）。

---

## 6) 验证结果

| 命令 | 结果 |
|------|------|
| `node --check` delivery-detail.js | PASS |
| `node --check` delivery-detail-settlement.js | PASS |
| `node --check` delivery-detail-pipeline.js | PASS |
| `node --check` delivery-detail-interviews.js | PASS |
| `node --check` delivery-detail-handbook.js | PASS |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `./venv/bin/python scripts/check_file_sizes.py` | PASS（`delivery_detail.html` 无超标 warning） |
| `./venv/bin/python -m pytest tests/ -q` | **80 passed** |

---

## 7) 下一阶段建议

1. **正式关闭 Phase 5E** — 在 master plan / changelog 中标记 delivery_detail tab 拆分完成。
2. **不强制拆 requirements** — 维持当前 glue，降低无收益 churn。
3. **可选后续（非 5E）：**
   - `delivery_turnover.html`（>1200 行）若需同策略外置 JS；
   - `roster_detail.html` inline JS 外置（与 5A 后端正交，单独立项）；
   - 统一 `crmFetch` 替换零散 `fetch`（plan/26 §9 明确 **5E 不做**）。

---

## 8) 最终判定

**Phase 5E：完成。**
`delivery_detail.html` 剩余 **382 行** inline `createApp` 为**装配 + 少量 glue**；**无需**新增 `delivery-detail-requirements.js` 即可收尾。
