# Phase 5E Step 2 — Delivery Detail Settlement Embed Split

**状态：PASS**  
**日期：2026-05-27**

## 1) 本 Step 迁移范围

本次仅迁移 `delivery_detail` 中 settlement 嵌入逻辑，保持单一 Vue app，不改 DOM 结构，不改后端 API/数据库/权限模型，不拆其他 tab。

迁移内容：
- `SETTLEMENT_FIELDS`
- `SETTLEMENT_COMPACT_FIELDS`
- `SETTLEMENT_TEXTAREA_FIELDS`
- `emptySettlementForm`
- `settlementReminderLabel`
- `buildSettlementReminderText`
- settlement 状态与方法：`loadSettlementRows`、`showSettlementReminders`、`openAdd`、`openEdit`、`openSettlementDetail`、`saveForm`、`removeRow`、`clearSettlementDateField`
- setup 返回暴露改为来自 settlement 模块（字段名保持不变）

## 2) 修改文件清单

- 新增：`static/js/pages/delivery-detail-settlement.js`
- 修改：`templates/pages/delivery_detail.html`

## 3) 行数变化

- `templates/pages/delivery_detail.html`: **4285 -> 4144**（-141）
- `static/js/pages/delivery-detail-settlement.js`: **252 行**

## 4) 兼容性与边界说明

- DOM 结构：未改动
- Vue app 生命周期结构：未改动（仍由页面内单个 `createApp(...).mount(...)` 挂载）
- 非 settlement 区域：pipeline / interviews / roster / handbook / requirements 未迁移
- API URL：保持原逻辑  
  - `GET /api/delivery/settlement`
  - `POST /api/delivery/settlement`
  - `PUT /api/delivery/settlement/row/{id}`
  - `DELETE /api/delivery/settlement/row/{id}`
- 权限：继续通过 `crmApi` 内部 `window.crmAuthHeader()` 附带认证头

### 4.1) 为何无法按原清单验收 embedded settlement CRUD

`main.py` 中 `page_delivery_module_detail` 对 `module_key == "settlement"` 返回 **302** 重定向到独立页 `/delivery/settlement`：

```text
GET /delivery/settlement/{client_id}  ->  302 /delivery/settlement
```

因此：

- **无法在浏览器中打开** `delivery_detail.html` 的 settlement 嵌入 tab 做 CRUD 点测；
- settlement 的完整 CRUD/导入导出由 Phase 4 独立页 [`delivery_settlement.html`](templates/pages/delivery_settlement.html) + [`delivery-settlement.js`](static/js/pages/delivery-settlement.js) 承担；
- 本 Step 迁移的是 **仍留在 `delivery_detail.html` 内的 settlement 模块代码**（供同一 Vue app 加载、与其他 module 共用脚本栈），通过 pipeline 等仍走 `delivery_detail` 的页面验证脚本加载与全局命名空间即可。

自动化已覆盖 settlement API：`tests/test_smoke_settlement.py`（2 passed）。

## 5) 是否复用公共工具

已复用 Phase 4 工具：
- `static/js/core/crm-api.js`（在 `delivery_detail.html` 的 `page_scripts` 显式加载；`base.html` 未全局加载）
- `static/js/core/crm-download.js`（同上）

实际加载顺序：

1. `/static/js/core/crm-api.js`
2. `/static/js/core/crm-download.js`
3. `/static/js/pages/delivery-detail.js`
4. `/static/js/pages/delivery-detail-settlement.js`
5. inline Vue `createApp` 脚本

## 6) 自动化验证结果

| 命令 | 结果 |
|---|---|
| `node --check static/js/pages/delivery-detail.js` | PASS |
| `node --check static/js/pages/delivery-detail-settlement.js` | PASS |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q` | PASS（9 passed） |
| `./venv/bin/python -m pytest tests/test_permission_datascope.py -q` | PASS（9 passed） |
| `./venv/bin/python -m pytest tests/test_smoke_settlement.py -q` | PASS（2 passed） |
| `./venv/bin/python -m pytest tests/ -q` | PASS（80 passed） |

重定向确认（TestClient，`client_id=1`）：

| 请求 | 结果 |
|---|---|
| `GET /delivery/settlement/1`（不跟随重定向） | **302** → `Location: /delivery/settlement` |

## 7) 浏览器点测结果（修订清单）

原 Step 2 清单中的 `/delivery/settlement/{client_id}` embedded CRUD 点测 **不适用**（见 §4.1）。改为在仍使用 `delivery_detail.html` 的页面上验证 settlement 模块脚本：

| # | 验证项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | `/delivery/pipeline/{client_id}` 页面加载成功（HTTP 200，`#delivery-detail-app` 存在） | **PASS** | Headless Chromium，`client_id=1` |
| 2 | `delivery-detail-settlement.js` 返回 **200** | **PASS** | `GET /static/js/pages/delivery-detail-settlement.js` |
| 3 | `window.CrmDeliveryDetailSettlement` 存在且含 `createSettlementState` | **PASS** | 页面 `evaluate` 检测 |
| 4 | Console 无业务 JS error | **PASS** | pipeline 页加载后无 `ReferenceError` / `TypeError`；登录前 `/api/me` 401 已排除（非业务 JS 异常） |

未在本清单内执行（因路由重定向或超出本 Step 范围）：

- embedded settlement 列表/新增/编辑/删除/readonly（无 `delivery_detail` settlement 路由入口）
- 403 无权限 UI（可由 RBAC pytest 覆盖）

## 8) 失败项与修复方法

- 失败项：无
- 说明：若未来需恢复 embedded settlement 浏览器 CRUD 验收，需先调整 `main.py` 重定向策略或新增专用验收路由

## 9) 是否阻塞进入 Step 3

**否**。自动化全绿，修订后的浏览器点测四项均已通过，可进入 Step 3（pipeline 区域外置）。
