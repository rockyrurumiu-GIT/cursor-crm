# Phase 5E Step 4 — Delivery Detail Interviews Split

**状态：PASS**  
**日期：2026-05-27**

## 1) 本 Step 范围

- 仅迁移 `delivery_detail.html` 中**员工访谈**区域 JS 至 [`static/js/pages/delivery-detail-interviews.js`](static/js/pages/delivery-detail-interviews.js)
- 未改 HTML DOM、后端 API、权限模型、数据库
- 未统一 fetch（仍 `fetch` + `window.crmAuthHeader()` / 模块内 `hdr()`）

## 2) Step 3.1 关系（必写）

- Step 3.1 已将 `fuzzyMatch` / `uniqueSorted` 置于 [`delivery-detail.js`](static/js/pages/delivery-detail.js)
- 本 Step 后 interviews **不**从 `CrmDeliveryDetailPipeline` 获取 helper；`createInterviewState` 与 `createPipelineState` 均经 `deps` 注入
- `rg CrmDeliveryDetailPipeline templates/pages/delivery_detail.html` → **仅 1 行**（`createPipelineState`）

## 3) API URL Checklist（迁移前 rg，以模板为准）

| 操作 | URL | 模块内函数 |
|------|-----|------------|
| 列表 | `GET /api/clients/{clientId}/delivery/interviews` | `loadInterviewRows` |
| 新增 | `POST /api/clients/{clientId}/delivery/interviews` | `saveInterviewForm` |
| 更新 | `PUT /api/delivery/interviews/row/{id}` | `saveInterviewForm` |
| 删除 | `DELETE /api/delivery/interviews/row/{id}` | `removeInterviewRow` |
| 导入 | `POST /api/clients/{clientId}/delivery/interviews/import` | `onInterviewImportFile` |
| 导出 | `GET /api/clients/{clientId}/delivery/interviews/export` | `exportInterviewCsv` |
| 日志 | `GET /api/clients/{clientId}/delivery/interviews/logs` | `openInterviewLogs` |
| 回滚 | `POST /api/clients/{clientId}/delivery/interviews/restore/latest` | `restoreInterviewLatestBackup` |
| 标离职 | `POST /api/clients/{clientId}/delivery/interviews/mark-employment-left` | `markInterviewHintLeftForName` |
| 花名册 | `GET /api/clients/{clientId}/roster` | `loadRosterRows` / `runInterviewRosterHints` |

迁移前 `rg`（节选）：

```text
templates/pages/delivery_detail.html:2400  interviews list
templates/pages/delivery_detail.html:2406  roster
templates/pages/delivery_detail.html:2612  mark-employment-left
templates/pages/delivery_detail.html:2784  DELETE row
templates/pages/delivery_detail.html:2808  import
...
```

**`CRM_DB_URL=sqlite:///./crm_v8.db` 下 API 核对（`client_id=1`）：**

| 端点 | HTTP | 条数 |
|------|------|------|
| `GET /api/clients/1/delivery/interviews` | 200 | **50** |
| `GET /api/clients/1/delivery/pipeline` | 200 | **1582** |

## 4) 修改文件与行数

| 文件 | 行数 |
|------|------|
| `templates/pages/delivery_detail.html` | **3648 → 2869**（**-779**） |
| `static/js/pages/delivery-detail-interviews.js` | **996**（新增） |

脚本顺序：`crm-api.js` → `crm-download.js` → `delivery-detail.js` → `delivery-detail-settlement.js` → `delivery-detail-pipeline.js` → **`delivery-detail-interviews.js`** → inline `createApp`

## 5) 自动化结果

| 命令 | 结果 |
|------|------|
| `node --check` delivery-detail.js / settlement / pipeline / **interviews** | PASS |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `pytest tests/test_smoke_delivery_interviews.py -q` | PASS |
| `pytest tests/test_smoke_delivery_pipeline.py -q` | PASS |
| `pytest tests/test_rbac_api_modules.py -q` | PASS |
| `pytest tests/test_permission_datascope.py -q` | PASS |
| `pytest tests/ -q` | PASS（80） |

迁移后 `rg`：

- `pipelineFuzzyMatch|pipelineUniqueSorted` in template + interviews.js → **无**
- `CrmDeliveryDetailPipeline` in template → **仅 createPipelineState**

## 6) 双 tab 浏览器验收

**环境：** 业务库 [`crm_v8.db`](crm_v8.db)（`CRM_DB_URL=sqlite:///./crm_v8.db`），`client_id=1`；登录 `#login-user` / `#login-pwd` / `#login-btn`。

**硬性回归（Step 3 类问题）：** 默认/重置筛选后须满足 `filtered*.length === *Rows.length`，且 **API 有数据时页面行数须与 API 一致、不得为 0**。`0 === 0` **不能**作为本次硬验收（无法证明「API 有数据却被筛没」）。

| # | Tab | 项 | 结果 | 备注 |
|---|-----|----|------|------|
| 1 | interviews | `/delivery/interviews/1` HTTP 200 + `#delivery-detail-app` | **PASS** | |
| 2 | interviews | `delivery-detail-interviews.js` → 200 | **PASS** | |
| 3 | interviews | `CrmDeliveryDetailInterviews.createInterviewState` | **PASS** | |
| 4 | interviews | Console 无 ReferenceError/TypeError | **PASS** | |
| 5 | interviews | **无筛选：`filteredInterviewRows.length === interviewRows.length`，且与 API 条数一致** | **PASS** | **rows=50, filtered=50**（API 200，50 条） |
| 6 | interviews | 新增/导入/导出/日志/回滚按钮存在 | **PASS** | |
| 6b | interviews | **`exportInterviewHintsCsv()` 可执行并触发 CSV 下载** | **PASS** | `csvCell` 经 `deps` 注入模块，无作用域错误；无业务 JS error |
| 7 | pipeline | `/delivery/pipeline/1` + `delivery-detail-pipeline.js` 200 | **PASS** | 回归：Step 4 未误伤 pipeline |
| 8 | pipeline | 无筛选：`filteredPipelineRows.length === pipelineRows.length` | **PASS** | **rows=1582, filtered=1582**（API 200，1582 条） |

**报告勘误：** 初稿曾写 `rows=0, filtered=0` 并归因「client_id=1 返回 404」。该结论为**假阳性**——当时自动化浏览器未挂载 `crm_v8.db`（pytest 空库 / 未设 `CRM_DB_URL`），与真实业务环境不一致。以本节及上表为准。

403/401：本 Step 未改权限；由 RBAC/datascope pytest 覆盖。

## 7) 结论

- Step 4 完成：访谈 JS 外置；`csvCell` 等共享 helper 经 `deps` 传入 `createInterviewState`（含 `exportInterviewHintsCsv`）
- 自动化全绿；在 **`crm_v8.db` + `client_id=1`** 下浏览器复测：**访谈 50/50、管道 1582/1582**，硬性回归通过
- 可进入 Step 5（roster）或后续 handbook 分步拆分
