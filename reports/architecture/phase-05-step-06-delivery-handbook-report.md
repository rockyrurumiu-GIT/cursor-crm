# Phase 5E Step 6 — Delivery Detail Handbook Split

**状态：PASS**  
**日期：2026-05-27**

## 1) 本 Step 范围

- 将 [`templates/pages/delivery_detail.html`](../../templates/pages/delivery_detail.html) 中 **handbook** 相关 inline JS 外置至 [`static/js/pages/delivery-detail-handbook.js`](../../static/js/pages/delivery-detail-handbook.js)
- **未改** HTML DOM、后端 API、权限、数据库、上传/下载/FTS/PDF/Plyr 业务逻辑
- **保留** `window.__CRM_DELIVERY_DETAIL__` 配置块（独立 `<script>`，约 1769–1776 行）
- **保留** `createApp` 主 inline script；仅删除已迁移的 handbook 实现

## 2) 修改文件与行数

| 文件 | 行数 |
|------|------|
| `templates/pages/delivery_detail.html` | **2869 → 2170**（**-699**） |
| `static/js/pages/delivery-detail-handbook.js` | **796**（新增） |

脚本顺序：`crm-api.js` → `crm-download.js` → `delivery-detail.js` → `delivery-detail-settlement.js` → `delivery-detail-pipeline.js` → `delivery-detail-interviews.js` → **`delivery-detail-handbook.js`** → inline `createApp`

## 3) 迁移方式（两阶段）

1. 整段复制 handbook JS 至 `delivery-detail-handbook.js`，`node --check` 新文件通过  
2. 模板加 script + `CrmDeliveryDetailHandbook.createHandbookState` 装配；删除 inline 中 handbook state/method/watch/`flattenHandbookOutline`  
3. **勘误修复：** 误将 `scrollToTop` 拷入 handbook 模块（依赖 `scrollToTopPipeline` / `scrollToTopInterviews`），已移回 `createApp` inline

## 4) API URL Checklist（未改）

| 操作 | URL |
|------|-----|
| 列表 | `GET /api/clients/{clientId}/delivery/handbooks` |
| 上传 | `POST /api/clients/{clientId}/delivery/handbooks` |
| 更新 | `PATCH /api/clients/{clientId}/delivery/handbooks/{id}` |
| 删除 | `DELETE /api/clients/{clientId}/delivery/handbooks/{id}` |
| PDF 正文 | `GET /api/clients/{cid}/delivery/handbooks/{id}/pdf-text` |
| PDF 高亮页 | `GET /api/clients/{cid}/delivery/handbooks/{id}/pdf-page.png` |
| 重建目录 | `POST /api/clients/{cid}/delivery/handbooks/{id}/rebuild-pdf-outline` |
| 全文检索 | `GET /api/delivery/handbooks/search` |
| reindex | `POST /api/delivery/handbooks/reindex-stale` |
| sync FTS | `POST /api/delivery/handbooks/sync-fts-indexed` |
| 文件下载 | `crmFetchAuthenticatedBlob` + `crmDownloadBlob` |

后端 [`routes/delivery_handbook.py`](../../routes/delivery_handbook.py) / [`services/delivery_handbook.py`](../../services/delivery_handbook.py)：**未修改**。

## 5) 迁入模块的主要符号

- **Helper：** `flattenHandbookOutline`
- **State/computed：** `handbookUploadMeta` … `handbookPdfSearchActive`（含阅读器、FTS 面板、元数据/锚点弹窗）
- **方法：** `loadHandbooks`、`openHandbookReader`、`runHandbookGlobalSearch`、`queueHandbookReindexStale`、`syncHandbookFtsFromBody`、`openHandbookSource` / `openHandbookSourceFromUrl` 等
- **Watch：** `handbookReaderRow`、`handbookPdfRenderedPageSrc`
- **生命周期：** `mountHandbook`（`loadHandbooks` + `window.crmOpenHandbookSource` + URL 深链）、`unmountHandbook`（Plyr/blob/全局清理）
- **留在 inline：** `scrollToTop`（组合 pipeline/interviews 回到顶部）

## 6) 遗留 inline 检查

```bash
rg "function flattenHandbookOutline|const handbookUploadMeta" templates/pages/delivery_detail.html
# → 无匹配（仅 createHandbookState 装配与 return 暴露）

rg "__CRM_DELIVERY_DETAIL__" templates/pages/delivery_detail.html
# → 保留
```

## 7) 自动化结果

| 命令 | 结果 |
|------|------|
| `node --check` delivery-detail.js / settlement / pipeline / interviews / **handbook** | PASS |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `pytest tests/test_smoke_delivery_handbook.py -q` | **5 passed** |
| `pytest tests/test_rbac_api_modules.py -q` | PASS |
| `pytest tests/test_permission_datascope.py -q` | PASS |
| `pytest tests/ -q` | **80 passed** |

## 8) 浏览器验收（`crm_v8.db`）

**环境：** `CRM_DB_URL=sqlite:///./crm_v8.db`，`uvicorn` `127.0.0.1:8017`，`client_id=1`，`admin` / `admin123`。

| # | 项 | 结果 | 备注 |
|---|-----|------|------|
| 1 | `/delivery/handbook/1` + `delivery-detail-handbook.js` | **PASS** | Console 无 ReferenceError（修复 `scrollToTop` 后） |
| 2 | `CrmDeliveryDetailHandbook` + `window.crmOpenHandbookSource` | **PASS** | 列表加载后 `crmOpenHandbookSource` 为 function |
| 3 | 列表 `handbookFiles.length === API` | **PASS** | **1 / 1** |
| 4 | PDF 阅读 / `pdf-text` / `pdf-page` 搜索 | **N/A** | 业务库 client 1 仅 **video** 样本，无 PDF |
| 5 | video 播放 | **PASS** | 点击「播放」打开阅读器 |
| 6 | URL `?handbook_id=2` 深链 | **PASS** | 自动打开对应手册 |
| 7 | audio 播放 / 锚点 / PiP | **N/A** | 无 audio 样本 |
| 8 | FTS reindex / sync（`queueHandbookReindexStale`、`syncHandbookFtsFromBody`） | **PASS** | 函数已迁入模块；`pytest tests/test_smoke_delivery_handbook.py` 覆盖 `sync-fts-indexed` / search API。**页面按钮：** 模板中无对应 `@click` 绑定 → **N/A**（未做点按验收，不写「按钮 PASS」） |

## 9) 结论

- Step 6 **PASS**：handbook JS 外置；`__CRM_DELIVERY_DETAIL__` 与 `createApp` 骨架保留；API/权限/下载方式不变  
- 自动化全绿；`crm_v8.db` 下 handbook 列表、video 播放、URL 深链通过；PDF 相关子项因 **无 PDF 样本** 标 **N/A**（非整 Step N/A）  
- 下一步：5E 剩余 tab（如 `requirements`）或按 plan/26 收尾
