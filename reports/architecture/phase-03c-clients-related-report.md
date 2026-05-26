# Phase 03C 报告：Clients Related Endpoints 拆分

## 执行范围

### 迁移内容

在 `routes/clients.py` 新增 `register_client_related_routes()` 函数，包含 3 个 API：

| # | 路由 | 方法 | 来源 |
|---|------|------|------|
| 1 | `/api/clients/handoff-summary` | GET | main.py |
| 2 | `/api/clients/{client_id}/details` | GET | main.py |
| 3 | `/api/clients/{client_id}/brief` | GET | main.py |

### main.py 变化

- 行数：6312 → 6287（减少 25 行）
- 路由数：72 → 69（减少 3 个）
- 新增注册调用 `register_client_related_routes()`，位于 `register_client_read_routes()` 之前

### 明确未改动

- settlement / roster / pipeline / handbook / interviews — 不动
- `delivery_detail.html` — 不动
- 前端页面 — 不动
- 权限配置 — 不动
- 数据库 migration — 不动

## 路由注册顺序

```
register_client_related_routes()   ← handoff-summary 先注册
register_client_read_routes()      ← /api/clients/{client_id} 后注册
register_client_write_routes()
```

确保 `/api/clients/handoff-summary` 不会被 `{client_id}` 路径参数匹配拦截。

## 自动化验证

| 检查项 | 结果 |
|--------|------|
| `scripts/check_reverse_imports.py` | PASS |
| `scripts/check_route_permissions.py` | PASS（已知 WARNING: `/api/files/access`） |
| `scripts/check_file_sizes.py` | PASS（已知 WARNING: `delivery_turnover.html` 2089 行） |
| `scripts/check_architecture.py` | PASS |
| `pytest tests/ -q` | **59 passed, 61 warnings** |

### 失败用例

无。

## 权限与 Data Scope 保留情况

| API | 权限 | Data Scope | 状态 |
|-----|------|-----------|------|
| `GET /api/clients/handoff-summary` | `crm.clients.read` | 无（全局统计，原行为） | ✓ 保留 |
| `GET /api/clients/{client_id}/details` | `crm.clients.read` | `ensure_client_access(action="read")` | ✓ 保留 |
| `GET /api/clients/{client_id}/brief` | `crm.clients.read` | `ensure_client_access(action="read")` | ✓ 已修复 |

## 返回结构保留

| API | 返回字段 | 一致性 |
|-----|---------|--------|
| `handoff-summary` | 委托 `build_clients_handoff_summary(rows)` | ✓ |
| `details` | `{"visits": [...], "logs": [...]}` | ✓ |
| `brief` | `{"id", "name", "owner", "phase"}` | ✓ |

## 后续修复（本次追加）

| 项目 | 操作 |
|------|------|
| `brief` 原无 data scope | 已加 `ensure_client_access(action="read")`，补越权测试 `brief_b → 404` |
| main.py 薄包装死代码 | 已删除 `_scoped_client_query` / `_ensure_client_access` 及对应 import（-18 行） |

## 后续需关注

| 项目 | 说明 |
|------|------|
| `handoff-summary` 无 data scope | 原代码全局统计，后续可按需加入 scope 策略 |

## 是否阻塞下一阶段

否。Phase 3（24A/24B/24C）全部完成。

## 结论

**PASS**
