# Phase 03A 测试报告：Clients Read/List/Detail/Export 拆分

## 执行范围

### 本阶段改了什么

1. 新增文件：
   - `services/clients.py` — 提取 `scoped_client_query` 和 `ensure_client_access` 共享函数
   - `routes/clients.py` — 4 个只读 client API route + `register_client_read_routes()`
   - `schemas/clients.py` — 占位（当前接口无 Pydantic model）

2. 从 `main.py` 删除的路由：
   - `GET /api/stats` (`get_stats`)
   - `GET /api/clients` (`list_clients`)
   - `GET /api/clients/{client_id}` (`get_client`)
   - `GET /api/export/clients` (`export_clients`)

3. `main.py` 中 `_scoped_client_query` / `_ensure_client_access` 改为薄包装，实际逻辑委托给 `services.clients`（24B/24C 路由仍在 main.py 中使用这些函数）。

4. 新增注册调用（位于 `handoff-summary` 路由之后，`POST /api/clients` 之前）：
   ```python
   from routes.clients import register_client_read_routes
   register_client_read_routes(
       app,
       get_db=get_db,
       Client=Client,
       Opportunity=Opportunity,
       HandoffRequest=HandoffRequest,
       CrmNotification=CrmNotification,
       trash_dir=TRASH_DIR,
       set_csv_download_headers=_set_csv_download_headers,
   )
   ```

5. `main.py` 行数变化：6593 → 6470（减少 123 行）

### 明确没有改什么

- `POST /api/clients` (24B) — 不动
- `PUT /api/clients/{client_id}` (24B) — 不动
- `DELETE /api/clients/{client_id}` (24B) — 不动
- `GET /api/clients/handoff-summary` (24C) — 不动
- `GET /api/clients/{client_id}/details` (24C) — 不动
- `GET /api/clients/{client_id}/brief` (24C) — 不动
- settlement 域 — 不动
- roster / pipeline / handbook / interviews — 不动
- `delivery_detail.html` — 不动
- 前端页面 — 不动
- 权限配置 — 不动
- 数据库 migration — 不动

## 自动化测试

### 命令与结果

| 命令 | 结果 |
|------|------|
| `./venv/bin/python scripts/check_reverse_imports.py` | PASS |
| `./venv/bin/python scripts/check_route_permissions.py` | PASS（WARNING: `/api/files/access` 仅 authenticate，已有预期） |
| `./venv/bin/python scripts/check_file_sizes.py` | PASS（strict 模式，WARNING: `delivery_turnover.html` 2089 行） |
| `./venv/bin/python -m pytest tests/test_permission_datascope.py -q` | 9 passed |
| `./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q` | 9 passed |
| `./venv/bin/python -m pytest tests/test_smoke_rbac.py tests/test_smoke_auth.py -q` | 15 passed |
| `./venv/bin/python -m pytest tests/ -q` | **59 passed, 61 warnings** |

### 失败用例

无。

## 路由注册验证

路由注册顺序（关键路径冲突检查）：

```
[32] GET /api/clients/handoff-summary    ← 固定路径，先注册
[34] GET /api/clients                    ← 精确匹配
[35] GET /api/clients/{client_id}        ← 路径参数，后注册
```

`handoff-summary` 在 `{client_id}` 之前注册，路径不会被吞掉。

## 每个 API 的权限与 Data Scope 保留情况

| API | 权限 | Data Scope | 保留状态 |
|-----|------|-----------|---------|
| `GET /api/stats` | `crm.clients.read` | funnel 按 `scoped_client_query` 过滤；handoff pending/rejected/approved 及 notifications 沿用旧全局统计，本阶段不改业务口径 | ✓ funnel scope 保留，全局部分保持原样 |
| `GET /api/clients` | `crm.clients.read` | `scoped_client_query(action="read")` | ✓ 保留 |
| `GET /api/clients/{client_id}` | `crm.clients.read` | `ensure_client_access(action="read")` → `assert_client_visible` | ✓ 保留 |
| `GET /api/export/clients` | `crm.clients.read` | `scoped_client_query(action="export")` | ✓ 保留 |

- `test_sales_users_see_only_own_clients` 通过 — 普通销售只能看自己客户
- `test_super_admin_sees_all_clients` 通过 — SUPER_ADMIN 看全部
- `test_delivery_settlement_scoped_by_delivery_owner` 通过 — 交付范围独立

## 风险检查

### 权限是否回归

4 个 API 均保留 `require_permission("crm.clients.read")`，RBAC 测试通过。

### API 路径是否变化

无变化，4 个路径与原 `main.py` 完全一致。

### 数据范围是否保留

- list 保留 `visible_client_ids` 过滤
- detail 保留 `assert_client_visible`
- export 使用 `action="export"` 同样经过 scope 过滤，不会导出越权客户
- stats 使用 `scoped_client_query` 按范围统计漏斗

### 导出是否可用

迁移后逻辑完全保留：CSV header、字段映射、BOM 写入、下载 headers 均未变。

## 问题与修复建议

### 已解决

| 问题 | 解法 |
|------|------|
| 路由顺序冲突 | `register_client_read_routes()` 放在 `handoff-summary` 之后注册 |
| 共享 helper 被 24B/24C 依赖 | 提取到 `services/clients.py`，main.py 保留薄包装 |

### 后续需关注

| 项目 | 说明 |
|------|------|
| `_scoped_client_query` / `_ensure_client_access` 薄包装 | 24B/24C 完成后可删除 main.py 中的包装，直接从 services import |

### 是否阻塞进入下一阶段

否。

## 结论

**PASS**
