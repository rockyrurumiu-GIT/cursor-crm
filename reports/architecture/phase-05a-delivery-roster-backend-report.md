# Phase 05A: Delivery Roster Backend 迁移报告

> 状态：**PASS**

## 1. API Checklist (rg 输出)

| # | 路由 | 类别 | 迁移状态 |
|---|------|------|----------|
| 1 | `GET /api/roster` | list-all | ✅ routes/delivery_roster.py |
| 2 | `POST /api/roster` | create-all | ✅ routes/delivery_roster.py |
| 3 | `GET /api/clients/{client_id}/roster` | list-client | ✅ routes/delivery_roster.py |
| 4 | `POST /api/clients/{client_id}/roster` | create-client | ✅ routes/delivery_roster.py |
| 5 | `PUT /api/roster/{row_id}` | update | ✅ routes/delivery_roster.py |
| 6 | `DELETE /api/roster/{row_id}` | delete | ✅ routes/delivery_roster.py |
| 7 | `GET /api/roster/turnover` | turnover-list | ✅ routes/delivery_roster.py |
| 8 | `GET /api/roster/turnover/dashboard` | turnover-dashboard | ✅ routes/delivery_roster.py |
| 9 | `POST /api/roster/import` | import-all | ✅ routes/delivery_roster.py |
| 10 | `POST /api/roster/turnover/import` | turnover-import | ✅ routes/delivery_roster.py |
| 11 | `POST /api/clients/{client_id}/roster/import` | import-client | ✅ routes/delivery_roster.py |
| 12 | `GET /api/roster/export` | export-all | ✅ routes/delivery_roster.py |
| 13 | `GET /api/roster/turnover/export` | turnover-export | ✅ routes/delivery_roster.py |
| 14 | `GET /api/clients/{client_id}/roster/export` | export-client | ✅ routes/delivery_roster.py |
| 15 | `POST /api/roster/restore/latest` | restore-all | ✅ routes/delivery_roster.py |
| 16 | `POST /api/clients/{client_id}/roster/restore/latest` | restore-client | ✅ routes/delivery_roster.py |
| 17 | `POST /api/roster/turnover/restore/latest` | turnover-restore | ✅ routes/delivery_roster.py |
| 18 | `GET /api/roster/logs` | logs | ✅ routes/delivery_roster.py |
| 19 | `GET /customers/roster` | 页面入口 | 保留在 main.py，原因：页面入口暂不属于 API 迁移范围 |
| 20 | `GET /customers/roster/{client_id}` | 页面入口 | 保留在 main.py，原因：页面入口暂不属于 API 迁移范围 |
| 21 | `/delivery/turnover` redirect | 页面入口 | 保留在 main.py，原因：页面入口暂不属于 API 迁移范围 |

## 2. 新增文件

| 文件 | 行数 | 用途 |
|------|------|------|
| `services/date_utils.py` | 23 | 公共日期解析 `parse_loose_date`，供 roster/pipeline/interviews 共享 |
| `schemas/delivery_roster.py` | 196 | 花名册常量：字段集、中英表头映射、客户别名规则、导出表头、必填项等 |
| `services/delivery_roster.py` | 1053 | 全部花名册业务逻辑 + 完整离职率看板 scope 计算 |
| `routes/delivery_roster.py` | 659 | 18 个 API handler + `register_delivery_roster_routes` 注册函数 |
| `tests/test_smoke_delivery_roster.py` | 109 | 7 条 smoke 测试：list、write、delete、import confirm、turnover dashboard |

## 3. main.py 变化

| 指标 | 变化 |
|------|------|
| Phase 5A 迁移前行数 | 6269 |
| 5A-1 后行数 | 5198 |
| 5A-2 后行数（最终） | **4535** |
| 净减少 | **1734 行** |
| 路由 handler 已移除 | 是（18 个 API handler） |
| 页面路由 | 保留在 main.py（`/customers/roster`, `/customers/roster/{client_id}`） |

## 4. 设计决策

### `_parse_loose_date` 放置位置
- 放入 `services/date_utils.py` 作为公共模块
- roster service 直接 `from services.date_utils import parse_loose_date`
- pipeline (5B) / interviews (5C) 可直接复用，无需重复定义

### 离职率看板 scope 逻辑
- 全部 330+ 行 dashboard 私有函数整体迁入 `services/delivery_roster.py`
- 包含：`roster_distinct_client_ids`, `dashboard_scope_client_ids`, `roster_entries_for_business_scope`, `roster_entries_department_dashboard`, headcount/departure/onboarding 计算, tenure bucket, trend trim 等
- 汇总为 `compute_turnover_dashboard()` 单一入口函数

### 跨域耦合处理
- roster PUT 修改离职状态时同步 interviews 的 `mark_left` 逻辑
- 通过 `register_delivery_roster_routes` 的 `interview_mark_left_fn` / `normalize_interview_name_fn` callable 注入解决
- 不引入 roster → interviews 的直接 import

### 数据范围（data scope）现状
- `GET /api/roster`（整体花名册）和 `GET /api/roster/turnover`（离职列表）：已支持 `data_scope` 过滤（基于 `ctx` 的 client 范围）
- `GET /api/clients/{client_id}/roster`（客户花名册）：**保持旧行为，未新增数据范围修复** — 当前仅校验 `delivery.roster.read` 权限，不做 client-level scope 过滤。此为原有设计，本阶段不改动。
- 所有 write 操作：仅校验 `delivery.roster.write` 权限，不做 scope 限制，保持旧行为。

### 依赖注入模式
- `register_delivery_roster_routes(app, *, get_db, Client, RosterEntry, AuditLog, ...)`
- 通过参数传入所有跨域依赖（ORM 模型、共享工具函数），routes 模块不直接 import main.py 内容
- 保证 import 方向为 main → routes（单向），无反向依赖

## 5. 验证结果

### 架构检查
```
check_reverse_imports.py    PASS
check_route_permissions.py  PASS (1 warning: /api/files/access authenticate only — 既有)
check_file_sizes.py         PASS (1 warning: delivery_turnover.html 2089 lines — 既有)
check_architecture.py       PASS
```

### pytest
```
66 passed, 62 warnings in 5.98s
```

### 新增 smoke 测试覆盖
| 测试 | 场景 |
|------|------|
| `test_list_all` | GET /api/roster 返回 200 + list |
| `test_list_by_client` | GET /api/clients/{id}/roster 返回 200 + list |
| `test_create_row_client` | POST /api/clients/{id}/roster 正常新增 |
| `test_delete_row` | DELETE /api/roster/{id} 正常删除 |
| `test_import_requires_confirm` | POST import 缺少 confirm=CONFIRM 返回 400 |
| `test_dashboard_returns_200` | GET /api/roster/turnover/dashboard 返回 200 + dict |
| `test_turnover_list` | GET /api/roster/turnover 返回 200 + list |

## 6. 总结

Phase 5A 完成。18 个 roster API handler 全部迁移至 `routes/delivery_roster.py`，通过 `register_delivery_roster_routes` 在 main.py 中注册。业务逻辑层完全封装在 `services/delivery_roster.py`。所有原有 URL、参数、返回结构、权限检查保持不变。零回归，全部测试通过。
