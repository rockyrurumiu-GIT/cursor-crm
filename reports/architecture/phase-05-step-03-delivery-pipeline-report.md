# Phase 5E Step 3 — Delivery Detail Pipeline Split

**状态：PASS**  
**日期：2026-05-27**

## 1) 本 Step 迁移范围

本次仅迁移 `delivery_detail.html` 中 **pipeline** 区域 JS，保持单一 Vue app，不改 DOM、后端 API、权限模型。

迁移内容：

- 模块级：`PIPELINE_*` 常量、`emptyPipelineForm`、`parsePeriodForSort` / `pipelinePeriod*` / `pipelineUniqueSorted` / `pipelineFuzzyMatch` / `emptyPipelineFilter`
- `createPipelineState(deps)`：列表/筛选/周期 picker/简历筛选多选/批量/CRUD/导入导出/日志回滚/`edit_row_id` 深链
- `closeDropdownsForTarget`（仅 pipeline 三类下拉）
- `openPipelineEditByQuery`、`scrollToTopPipeline`
- 模板侧组合 `handleDocumentClick` / `handleDocumentFocusIn`（pipeline + interview 分段关闭）

未迁移：interviews / handbook / requirements / settlement（Step 2 已完成）。

## 2) 修改文件清单

- 新增：`static/js/pages/delivery-detail-pipeline.js`
- 修改：`templates/pages/delivery_detail.html`

## 3) 行数变化

| 文件 | 行数 |
|------|------|
| `templates/pages/delivery_detail.html` | **4144 → 3643**（**-501**） |
| `static/js/pages/delivery-detail-pipeline.js` | **714**（新增） |

`check_file_sizes.py`：pipeline 模块 < 1200 行，无新增 warning。

## 4) API URL Checklist（迁移前以模板/现模块 `fetch` 为准）

| 操作 | URL | 模块内位置 |
|------|-----|------------|
| 列表 | `GET /api/clients/{clientId}/delivery/pipeline` | `loadPipelineRows` |
| 新增 | `POST /api/clients/{clientId}/delivery/pipeline` | `savePipelineForm` |
| 更新 | `PUT /api/delivery/pipeline/row/{row_id}` | `savePipelineForm` / 批量循环 |
| 删除 | `DELETE /api/delivery/pipeline/row/{row_id}` | `removePipelineRow` |
| 导入 | `POST /api/delivery/pipeline/import` + FormData `client_id`, `file`, `confirm` | `onPipelineImportFile` |
| 导出 | `GET /api/clients/{clientId}/delivery/pipeline/export` → `crmDownloadBlob` | `exportPipelineCsv` |
| 日志 | `GET /api/clients/{clientId}/delivery/pipeline/logs` | `openPipelineLogs` |
| 回滚 | `POST /api/clients/{clientId}/delivery/pipeline/restore/latest` | `restorePipelineLatestBackup` |
| Insight 跳转 | `window.location` → `/delivery/pipeline/{clientId}/insight` | `savePipelineForm` |

**注意：** 行级 PUT/DELETE **无** client 前缀；导入使用 **global** `/api/delivery/pipeline/import`（非 `.../clients/{id}/.../import`）。

## 5) 脚本加载顺序

1. `crm-api.js`
2. `crm-download.js`
3. `delivery-detail.js`
4. `delivery-detail-settlement.js`
5. **`delivery-detail-pipeline.js`**
6. inline `createApp`

## 6) 耦合处理

- `handleDocumentClick`：`closePipelineDropdownsForTarget` + `closeInterviewDropdownsForTarget`（interview 逻辑仍 inline）
- `scrollToTop`：先 `scrollToTopPipeline()`，再 interview / `window.scrollTo`
- `interviewScrollWrap` 保留在模板（自 pipeline 块拆出时补回 `ref`）
- 导出保持 `fetch` + `window.crmDownloadBlob`（与 interviews/handbook 一致）

## 7) 自动化验证

| 命令 | 结果 |
|------|------|
| `node --check static/js/pages/delivery-detail.js` | PASS |
| `node --check static/js/pages/delivery-detail-settlement.js` | PASS |
| `node --check static/js/pages/delivery-detail-pipeline.js` | PASS |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q` | PASS（9） |
| `./venv/bin/python -m pytest tests/test_permission_datascope.py -q` | PASS（9） |
| `./venv/bin/python -m pytest tests/test_smoke_delivery_pipeline.py -q` | PASS（5） |
| `./venv/bin/python -m pytest tests/ -q` | PASS（80） |

## 8) 浏览器点测（`/delivery/pipeline/1`，admin）

Headless Chromium + 本地 `uvicorn` `127.0.0.1:8765`；登录 `#login-user` / `#login-pwd` / `#login-btn`。

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | 页面 HTTP 200，`#delivery-detail-app` 存在 | PASS |
| 2 | `delivery-detail-pipeline.js` HTTP 200 | PASS |
| 3 | `window.CrmDeliveryDetailPipeline.createPipelineState` 及导出常量 | PASS |
| 4 | Console 无 `ReferenceError` / `TypeError`（排除 favicon、登录前 `/api/me` 401） | PASS |
| 5 | 「新增」打开表单弹层 | PASS |
| 6 | 筛选区可用 | PASS |
| 7 | 简历筛选/周期控件在 pipeline 模块内 | PASS |
| 8 | 「批量」打开批量弹层 | PASS |
| 9 | 「导入」「导出」按钮存在 | PASS |
| 10 | 「日志」按钮存在 | PASS |
| 11 | 「回滚」触发 `confirm`（`restorePipelineLatestBackup`） | PASS |
| 12 | `?edit_row_id=999999` 不抛 JS 异常 | PASS |
| 13 | 403 可见性 | PASS（`test_rbac_api_modules` / datascope pytest；未另开 viewer 会话） |

## 9) 结论

Pipeline 外置与 Step 1/2 模式一致；`/delivery/pipeline/{client_id}` **无** settlement 式 302，本 Step 可在真实 `delivery_detail` 页完成 CRUD 相关 smoke。自动化与修订浏览器清单均已通过 → **PASS**，可进入 Step 4（interviews）。
