# Phase 5E Step 1 — Delivery Detail 初始化与公共 Helper 外置

**状态：PASS**  
**日期：2026-05-27**

---

## 1. 执行范围

本 Step 仅做低风险基础拆分：页面配置对象、client brief、跨 tab 纯函数 helper。未改后端 API、未改 DOM、未拆 pipeline / interviews / handbook / settlement 业务逻辑。

| 文件 | 拆分前 | 拆分后 | 变化 |
|------|--------|--------|------|
| `templates/pages/delivery_detail.html` | 4394 | 4285 | **-109 行** |
| `static/js/pages/delivery-detail.js` | — | 186 | 新增 |

---

## 2. 配置对象迁移

| 旧全局变量 | 新字段 (`window.__CRM_DELIVERY_DETAIL__`) | 注入方式 |
|------------|-------------------------------------------|----------|
| `__DELIVERY_CLIENT_ID__` | `clientId` | `{{ client_id }}`（整数） |
| `__DELIVERY_MODULE_KEY__` | `moduleKey` | `{{ module_key \| tojson }}` |
| `__DELIVERY_MODULE_TITLE__` | `moduleTitle` | `{{ module_title \| tojson }}` |
| `__HANDBOOK_ADMIN_CROSS_SEARCH__` | `handbookAdminCrossSearch` | `{{ handbook_admin_cross_search\|default(false)\|tojson }}` |

`setup()` 通过 `window.CrmDeliveryDetail.readConfig()` 读取，不再直接访问旧全局量。

**安全加固：** `moduleKey` / `moduleTitle` 由未转义字符串改为 `tojson`，避免标题中含引号时破坏 JS 字面量。

---

## 3. 外置至 `static/js/pages/delivery-detail.js`（`window.CrmDeliveryDetail`）

### 配置与初始化

- `readConfig`
- `loadClientBrief`

### 日期 / CSV / 通用

- `todayInputDate`, `extractLooseDateParts`, `normalizeDateForInput`, `displayDateSlash`
- `interviewDateRank`, `normalizedDateToUtcMs`, `diffDaysFromDate`
- `isEmptyOrNoValue`, `csvCell`
- `multiSelectSummary`, `interviewTextLength`

### DOM 安全（handbook `v-html` 高亮链）

- `crmEscapeHtml`, `crmHighlightSearchQuery`（算法原样搬迁）

### API / 展示

- `readApiErrorMessage`, `formatDate`

内联脚本顶部从 `CrmDeliveryDetail` 解构上述符号，业务 `createApp` 仍留在模板中。

---

## 4. 仍留在模板 inline（后续 Step 迁移）

### Tab / 域常量与表单

- `PIPELINE_*`, `INTERVIEW_*`, `SETTLEMENT_*` 字段定义与 `empty*Form`
- `flattenHandbookOutline`, `collectInterviewMissingRequiredKeys`

### Tab 专用 helper

- `settlementReminderLabel`, `buildSettlementReminderText`
- `flattenInterviewHintItems`, `buildInterviewHintCopyText`, `buildInterviewHintCsv`
- `normalizePersonName`, `classifyEmploymentStatus`, `emptyInterviewRosterHints`, `stripInterviewEditQueryFromUrl`
- `parsePeriodForSort`, `pipelinePeriodValue`, `pipelinePeriodDisplay`, `pipelinePeriodPanelStyle`, `pipelineUniqueSorted`, `pipelineFuzzyMatch`
- `emptyPipelineFilter`, `emptyInterviewFilter`

### 业务 `setup()` 全文

- 各 tab 的 `load*Rows`、`onMounted` 多模块加载、`handleDocumentClick`、handbook 阅读器、pipeline/interview CRUD 等

---

## 5. 脚本加载顺序

```html
<!-- head_extra -->
<script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
...

<!-- 模板内（content block 末） -->
<script>window.__CRM_DELIVERY_DETAIL__ = { ... };</script>

<!-- page_scripts -->
<script src="/static/js/pages/delivery-detail.js"></script>
<script>/* 解构 CrmDeliveryDetail + createApp ... */</script>
```

---

## 6. 明确未改动

- 后端 API URL 与权限头
- HTML DOM / Vue 模板
- `delivery_index.html` 仍使用旧 `__DELIVERY_*` 全局量（非本页范围）
- 未引入 `crm-api.js`（Step 2 settlement 嵌入时再复用）

---

## 7. 自动化验证

| # | 命令 | 结果 |
|---|------|------|
| 1 | `node --check static/js/pages/delivery-detail.js` | PASS |
| 2 | `scripts/check_file_sizes.py` | PASS（`delivery_detail.html` 4285 &lt; baseline 4394+50） |
| 3 | `pytest tests/test_rbac_api_modules.py -q` | **9 passed** |
| 4 | `pytest tests/test_permission_datascope.py -q` | **9 passed** |
| 5 | `pytest tests/ -q` | **80 passed** |

---

## 8. 手动验证清单

需在浏览器中点测（自动化未覆盖 UI）：

| # | 验证项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | `/delivery/pipeline/{client_id}` 不空白、客户名来自 brief | 待测 | |
| 2 | `/delivery/interviews/{client_id}` | 待测 | |
| 3 | `/delivery/handbook/{client_id}` 跨客户搜索 UI 与 `handbookAdminCrossSearch` | 待测 | |
| 4 | `/delivery/requirements/{client_id}` | 待测 | |
| 5 | Console 无 `ReferenceError` / 404 `delivery-detail.js` | 待测 | |
| 6 | 无权限用户 403/401 有提示 | 待测 | |

---

## 9. Console / 安全备注

- **XSS：** `crmHighlightSearchQuery` + `v-html` 为既有面；本 Step 未改算法。
- **IDOR：** `clientId` 仍在 `window`；授权依赖 API + `crmAuthHeader()` + 服务端 data scope（与改前一致）。
- **技术债：** `crmEscapeHtml` 与 `crm-dom.js` 的 `escapeHTML` 重复，后续可统一。

---

## 10. 下一步（Step 2）

- 外置 settlement 嵌入区域至 `delivery-detail-settlement.js`
- 复用 `static/js/core/crm-api.js` 与 `crm-download.js`
