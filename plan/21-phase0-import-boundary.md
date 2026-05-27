# 21 Phase 0：断开反向 Import 边界

## Summary

本阶段只解决一个问题：`auth/data_scope.py` 不应再 import `main.Client`。

当前事实：

```text
main.py -> from auth import data_scope as ds
auth/data_scope.py -> from main import Client
```

这形成了反向依赖。现在因为是函数内延迟 import，暂时能跑；但后续一旦拆 route/service/model，很容易出现循环 import、启动失败或 pytest 全挂。

本阶段不搬所有模型，不重组 database engine，不拆业务路由。只建立一条低风险边界：`auth/` 不能依赖 `main.py`。

## Implementation Changes

### 1. 移除 `auth/data_scope.py` 中的 `from main import Client`

目标：

```text
auth/data_scope.py 中不再出现 from main import 或 import main
```

做法：

- 将依赖 `Client` 模型的函数改成接收 `client_model` 参数。
- 在 `main.py` 或业务路由调用这些函数时，显式传入当前 `Client` 模型。
- `auth/data_scope.py` 只依赖 `AuthContext`、scope 常量、SQLAlchemy Query/Session，不依赖应用入口。

建议签名方向：

```python
apply_client_scope(query, db, ctx, resource_code, action, client_model)
scoped_client_ids(db, ctx, resource_code, action, client_model)
visible_client_ids(db, ctx, action, client_model)
assert_client_visible(db, ctx, client_id, client_model, action="read")
assert_client_in_scope(db, ctx, client_id, client_model, resource_code, action)
```

如果现有调用点较多，允许先保留旧函数名，但必须新增必填 `client_model` 参数，避免静默回退到 import `main`。

### 2. 更新所有调用点

搜索：

```text
apply_client_scope(
scoped_client_ids(
visible_client_ids(
assert_client_visible(
assert_client_in_scope(
filter_query_by_client_scope(
```

所有调用点必须明确传入 `Client`。

示例目标：

```python
query = ds.apply_client_scope(query, db, ctx, RESOURCE_CRM_CLIENT, "read", Client)
ds.assert_client_visible(db, ctx, client_id, Client, action="read")
```

### 3. 不做的事

本阶段不要做：

- 不迁移 `Client`、`Opportunity`、`DeliverySettlementEntry` 等 ORM 模型。
- 不创建新的 `engine` 或 `SessionLocal`。
- 不移动 settlement、clients、roster、pipeline 路由。
- 不改变任何权限规则。
- 不改变任何数据范围语义。

## Validation Tests

### 自动化测试

执行：

```text
rg -n "from main import|import main" auth *_routes.py *_core.py main.py
./venv/bin/python -m pytest tests/test_data_scope_catalog.py tests/test_permission_datascope.py -q
./venv/bin/python -m pytest tests/test_rbac_api_modules.py tests/test_smoke_auth.py -q
./venv/bin/python -m pytest tests/ -q
```

验收：

- `rg` 结果中允许 tests import main。
- `auth/`、`*_routes.py`、`*_core.py` 中不允许再出现 `from main import` 或 `import main`。
- 所有 pytest 通过。

### 手动验证

启动服务后验证：

```text
/login 可打开
admin 可登录
/customers 可打开
/delivery/settlement 可打开
```

### 测试报告

生成：

```text
reports/architecture/phase-00-import-boundary-report.md
```

报告必须写明：

- 修改了哪些 data scope 函数签名。
- 更新了哪些调用点。
- 是否仍存在非测试代码 import main。
- `tests/test_permission_datascope.py` 是否通过。

## Common Failures And Fixes

### 服务启动失败：ImportError 或 circular import

修复：

- 检查是否还有 `auth/`、`routes/`、`services/` import `main`。
- 将所需模型改为从调用方参数传入，不要在底层模块 import 应用入口。

### 数据范围测试失败

修复：

- 对比改动前后的 scope 类型。
- 确认 `client_model` 使用的是同一个 `Client` ORM 类。
- 确认 `client_scope_columns()` 返回字段仍然在 `Client` 上存在。

### 客户列表为空

修复：

- 检查 `apply_client_scope` 是否拿到正确的 owner/dept/assigned 列。
- 检查 `ctx.role_data_scopes` 是否仍正常加载。
