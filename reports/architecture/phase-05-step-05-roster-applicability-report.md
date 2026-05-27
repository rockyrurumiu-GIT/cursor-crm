# Phase 5E Step 5 — Roster 适用性检查

**状态：N/A（适用性检查 PASS）**
**日期：2026-05-27**

**PASS 含义：** 判定「无需拆分 `delivery-detail-roster.js`」正确；自动化与浏览器回归全绿；**无业务代码 diff**。
**不是：** 完成了 delivery_detail 内 roster tab 的前端拆分。

## 1) 结论

| 项 | 结果 |
|----|------|
| `delivery_detail` 是否存在 roster tab | **否** — `DELIVERY_MODULES` 无 `roster`，无 `moduleKey === 'roster'` |
| 是否应新建 `delivery-detail-roster.js` | **否** |
| roster 在 delivery 侧的职责 | 仅 **interviews 提示**（Step 4 已迁入 `delivery-detail-interviews.js`） |
| 花名册完整 UI | 独立页 `/customers/roster/{client_id}` → `roster_detail.html`（inline JS，非 5E 序列） |
| 下一步 5E 编码 Step | **Step 6 handbook**（见 [plan/26](../../plan/26-phase5-delivery-detail-tab-split.md)） |

## 2) 适用性证据（rg）

### 2.1 无 delivery roster tab

```bash
rg -n "moduleKey === 'roster'|moduleKey.*roster|delivery/roster" \
  templates/pages/delivery_detail.html static/js/pages
```

**结果：** 无匹配。

[`main.py`](../../main.py) 中 `DELIVERY_MODULES`：

```text
requirements | pipeline | interviews | turnover | handbook | settlement
```

（**无 `roster`**。）

### 2.2 独立花名册路由（与 delivery_detail 正交）

```bash
rg -n "customers/roster|roster_detail|roster_index" main.py templates/pages
```

| 位置 | 说明 |
|------|------|
| `main.py` | `GET /customers/roster`、`GET /customers/roster/{client_id}` |
| `roster_index.html` / `roster_detail.html` | 独立花名册页 |
| `delivery_detail.html` | 含 `/customers/roster/${clientId}` **链接**（访谈提示 UI），**非** roster tab |

### 2.3 roster 依赖仅在 interviews 模块

```bash
rg -n "loadRosterRows|runInterviewRosterHints|goRosterAddForInterviewHint|markInterviewHintLeftForName|rosterRows|/api/clients/.*/roster|/customers/roster" \
  templates/pages/delivery_detail.html static/js/pages/delivery-detail-interviews.js
```

| 文件 | 命中 |
|------|------|
| `delivery-detail-interviews.js` | `loadRosterRows`、`GET /api/clients/{id}/roster`、`runInterviewRosterHints`、`goRosterAddForInterviewHint`（跳转 `/customers/roster/...`）、`markInterviewHintLeftForName`（访谈 API `mark-employment-left`） |
| `delivery_detail.html` | DOM 绑定、`return` 暴露名（`rosterRows`、提示按钮、`/customers/roster/` 链接），**无** roster CRUD 逻辑 |

其他 `delivery-detail*.js`：**无** `roster` 业务逻辑（仅 interviews 模块含 roster 提示）。

`delivery-detail-roster.js`：**不存在**（且不应创建）。

### 2.4 两层结论（避免误读 Step 1）

1. **无 delivery roster tab** — `DELIVERY_MODULES` + `moduleKey` 路径均无 roster。
2. **允许** `delivery_detail` 内出现 `rosterRows`、`/customers/roster` 链接与 roster API 调用 — 仅限 **interviews 提示**，已由 Step 4 收口。

## 3) 代码变更

**零 diff**（本 Step 不拆分、不新建 `delivery-detail-roster.js`）。

Phase **5A** 后端 roster 域（如 `routes/delivery_roster.py`）已完成，与 5E Step 5 **无关**。

## 4) 自动化回归

| 命令 | 结果 |
|------|------|
| `node --check` delivery-detail.js / settlement / pipeline / interviews | PASS |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `pytest tests/test_smoke_delivery_interviews.py tests/test_smoke_delivery_pipeline.py tests/test_rbac_api_modules.py tests/test_permission_datascope.py -q` | **27 passed** |
| `pytest tests/ -q` | **80 passed** |

## 5) 浏览器验收（`crm_v8.db`）

**环境：** `CRM_DB_URL=sqlite:///./crm_v8.db`，`uvicorn` `127.0.0.1:8016`，`client_id=1`，登录 `#login-user` / `#login-pwd` / `#login-btn`（`admin` / `admin123`）。

**硬性回归（与 Step 4 一致）：** 无筛选时 `filtered*.length === *Rows.length`，且 **API 有数据时页面行数须与 API 一致**；`0 === 0` 不足。

### API 条数（登录后 `fetch`）

| 端点 | HTTP | 条数 |
|------|------|------|
| `GET /api/clients/1/delivery/interviews` | 200 | **50** |
| `GET /api/clients/1/delivery/pipeline` | 200 | **1582** |
| `GET /api/clients/1/roster` | 200 | **34** |

### 页面验收表

| # | 页面/操作 | 项 | 结果 | 备注 |
|---|-----------|----|------|------|
| 1 | `/delivery/interviews/1` | HTTP 200 + `delivery-detail-interviews.js` | **PASS** | |
| 2 | interviews | `filteredInterviewRows === interviewRows === API` | **PASS** | **50 / 50** |
| 3 | interviews | 点击「提示」→ `interviewHintRan`，`rosterRows` 与 API roster 一致 | **PASS** | rosterRows=**34** |
| 4 | interviews | 「去花名册」跳转 URL 含 `clientId` | **PASS** | 当前数据无 `leftOnRoster` 项，无「去花名册」按钮（N/A）；`goRosterAddForInterviewHint` 代码路径含 `/customers/roster/{clientId}?roster_add=1&...` |
| 5 | `/delivery/pipeline/1` | Pipeline 回归：`filteredPipelineRows === pipelineRows === API` | **PASS** | **1582 / 1582**（须 `networkidle` 等待加载；快速切页会得到 0 假阴性） |
| 6 | `/customers/roster/1` | HTTP 200，列表可加载 | **PASS** | 表格/列表 present |
| 7 | Console | 无业务 ReferenceError/TypeError | **PASS** | 仅见未登录态 `/api/me` 401 类 network 日志（已过滤，不计 FAIL） |

## 6) 计划对齐（plan/26 更正）

| 文档 | 说法 | 现网 |
|------|------|------|
| [plan/26](../../plan/26-phase5-delivery-detail-tab-split.md) § Step 5 | 「roster 区域」拆至 `delivery-detail-roster.js` | **无此 tab** — 条文 **过时** |
| Phase 5A | roster **后端** 拆分 | 已完成，与 5E Step 5 **无关** |
| Step 4 结语「可进入 Step 5（roster）」 | 应理解为 **适用性检查** | 本 Step = **N/A**，非编码拆分 |

**后续 5E：** 下一编码 Step 为 **Step 6 handbook**（plan/26 原 Step 6；多子步、风险最高）。

若将来拆分花名册前端，应单独立项「`roster_detail.html` inline JS 外置」，**不属于** delivery_detail 5E 序列。

## 7) 风险与遗漏

| 项 | 级别 | 本 Step 处理 |
|----|------|----------------|
| 误拆 `roster_detail` | 低 | 边界已写明，未改代码 |
| interviews 提示回归 | 中 | 浏览器已点「提示」并核对 roster API 条数 |
| pipeline 快速导航假 0 行 | 中 | 验收使用 `networkidle` + 等待；报告已注明 |
| turnover 与 roster 混淆 | 低 | `turnover` 为 delivery 独立页 302，未纳入本 Step |

## 8) 总结

- Step 5 **适用性检查 PASS**：roster **不是** `delivery_detail` tab；依赖 **仅** interviews 模块；**无需** `delivery-detail-roster.js`。
- 零代码变更；`node --check`、architecture、pytest **80** 全绿。
- **`crm_v8.db` + client_id=1**：interviews **50/50**、pipeline **1582/1582**、独立花名册 **200**、访谈「提示」加载 roster **34** 条。
- **下一步：** Phase 5E **Step 6 — handbook** 拆分。
