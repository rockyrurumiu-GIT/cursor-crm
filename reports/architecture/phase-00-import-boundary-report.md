# Phase 00 测试报告

## 执行范围

### 本阶段改了什么

- 移除 `auth/data_scope.py` 中全部 `from main import Client`（原第 64、116 行）。
- 为依赖 `Client` ORM 的 data scope 函数新增必填 `client_model` 参数：
  - `_apply_scope_to_client_query(..., client_model, *, sales)`
  - `apply_client_scope(..., client_model)`
  - `scoped_client_ids(..., client_model)`
  - `visible_client_ids(db, ctx, client_model, action=...)`
  - `assert_client_visible(db, ctx, client_id, client_model, *, action=...)`
  - `assert_client_in_scope(db, ctx, client_id, client_model, resource_code, action)`
  - `filter_query_by_client_scope(..., client_id_column, client_model)`

- 更新调用点，全部显式传入 `Client`：
  - `main.py`：`_scoped_client_query`、`_ensure_client_access`、roster scope 过滤（2 处）、settlement list scope（1 处）
  - `handoff_routes.py`：`assert_client_in_scope`（1 处）、`filter_query_by_client_scope`（1 处）
  - `phase2_routes.py`：opportunities/contacts 的 `assert_client_in_scope`（7 处）、`filter_query_by_client_scope`（2 处）

### 明确没有改什么

- 未迁移 ORM 模型、`engine`、`SessionLocal`。
- 未移动 settlement、clients、roster、pipeline 等业务路由。
- 未改变权限规则或 data scope 语义。
- 未执行 Phase 1 及后续阶段（护栏脚本、业务域拆分等）。

## 自动化测试

### 命令

```text
grep "from main import|import main" auth/ *_routes.py *_core.py main.py
./venv/bin/python -m pytest tests/test_data_scope_catalog.py tests/test_permission_datascope.py -q
./venv/bin/python -m pytest tests/test_rbac_api_modules.py tests/test_smoke_auth.py -q
./venv/bin/python -m pytest tests/ -q
```

（环境中无 `rg`，使用等效 grep 扫描。）

### 结果

| 套件 | 结果 |
|------|------|
| `test_data_scope_catalog.py` + `test_permission_datascope.py` | **20 passed** |
| `test_rbac_api_modules.py` + `test_smoke_auth.py` | **17 passed** |
| 全量 `tests/` | **59 passed**, 61 warnings |

失败用例：无。

反向 import 扫描：

- `auth/`、`*_routes.py`、`*_core.py`、`main.py`：**无** `from main import` / `import main`
- `tests/` 内 import main：**允许**（conftest 与各 smoke/datascope 测试）

## 手动验证

本阶段为 import 边界调整，未启动独立 HTTP 服务做页面点测。以下页面/接口在自动化测试中已有覆盖，行为未变：

| 页面/接口 | 操作 | 结果 |
|-----------|------|------|
| `/login`、admin 登录 | smoke auth / rbac 测试 | 通过 |
| `/customers`、客户 data scope | `test_permission_datascope.py` | 通过 |
| `/delivery/settlement`、settlement scope | `test_permission_datascope.py` | 通过 |

建议在合并前本地再快速打开 `/login`、`/customers`、`/delivery/settlement` 确认 UI 正常。

## 风险检查

| 检查项 | 结果 |
|--------|------|
| 权限是否回归 | 否 — RESTRICTED/SALES/DELIVERY scope 测试均通过 |
| API 路径是否变化 | 否 — 无路由改动 |
| 数据范围是否保留 | 是 — `test_permission_datascope.py` 全通过 |
| 导入导出是否可用 | 未改相关逻辑；全量测试通过 |

## 问题与修复建议

- **问题**：无。
- **根因判断**：—
- **建议修复方法**：—
- **是否阻塞进入 Phase 1**：否

## 结论

**PASS**

Phase 0 目标已达成：`auth/` 不再依赖 `main.py`，调用方显式传入 `Client` 模型，59 项自动化测试全部通过。可进入 Phase 1（架构护栏）。
