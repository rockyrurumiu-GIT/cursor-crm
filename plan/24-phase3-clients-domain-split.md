# 24 Phase 3：拆分 Clients 后端域

## Summary

本阶段拆分客户域，但必须比 settlement 更谨慎。原因是 clients 是 data scope 的核心锚点，销售、交付、文件、结算、商机都可能通过客户范围判断可见性。

本阶段不允许一次性迁移全部客户接口，必须拆成 3 个子阶段：

```text
24A: clients read/list/detail/export
24B: clients create/update/delete
24C: clients related endpoints: handoff-summary/details/brief
```

每个子阶段都必须生成独立测试报告。任一子阶段 `BLOCKED`，不能继续下一个子阶段。

## Preconditions

进入本阶段前必须满足：

```text
Phase 0 PASS
Phase 1 PASS
Phase 2 PASS
./venv/bin/python -m pytest tests/ -q 全绿
```

特别要求：

```text
auth/data_scope.py 不能再 import main
scripts/check_route_permissions.py 可运行
tests/test_permission_datascope.py 通过
```

## Implementation Changes

### 1. 新增 clients 模块

新增：

```text
routes/clients.py
services/clients.py
schemas/clients.py
```

总迁移范围：

```text
GET    /api/stats
GET    /api/clients
GET    /api/clients/handoff-summary
POST   /api/clients
GET    /api/clients/{client_id}
PUT    /api/clients/{client_id}
DELETE /api/clients/{client_id}
GET    /api/clients/{client_id}/details
GET    /api/export/clients
GET    /api/clients/{client_id}/brief
```

本阶段不迁移：

```text
POST /api/visits
delivery handbooks
delivery roster
delivery pipeline
delivery interviews
handoff routes
phase2 opportunities/contracts/contacts
```

### 2. 子阶段 24A：Clients Read/List/Detail/Export

迁移范围：

```text
GET /api/stats
GET /api/clients
GET /api/clients/{client_id}
GET /api/export/clients
```

要求：

- 只迁移读接口，不迁移新增、编辑、删除。
- `/api/clients` 必须保留 `apply_client_scope` 或等价过滤。
- `/api/clients/{client_id}` 必须保留 `assert_client_visible` 或等价校验。
- `/api/export/clients` 必须和列表使用同一数据范围，不得导出越权客户。

24A 报告：

```text
reports/architecture/phase-03a-clients-read-report.md
```

### 3. 子阶段 24B：Clients Write/Delete

迁移范围：

```text
POST   /api/clients
PUT    /api/clients/{client_id}
DELETE /api/clients/{client_id}
```

要求：

- 只迁移写接口，不迁移关联聚合接口。
- 创建客户时 `owner_user_id`、`owner_dept_id`、销售/交付 owner 字段行为必须保持不变。
- 更新/删除必须保留 write scope 校验。
- 表单字段名、上传附件字段名、审计日志行为不变。

24B 报告：

```text
reports/architecture/phase-03b-clients-write-report.md
```

### 4. 子阶段 24C：Clients Related Endpoints

迁移范围：

```text
GET /api/clients/handoff-summary
GET /api/clients/{client_id}/details
GET /api/clients/{client_id}/brief
```

要求：

- 保留原聚合字段，不改变前端返回结构。
- 如果接口依赖 handoff/visit/contacts 等其他域，只在 clients service 中做薄聚合，不顺手迁移其他域。
- 访问单客户关联数据前必须确认当前用户能看该客户。

24C 报告：

```text
reports/architecture/phase-03c-clients-related-report.md
```

### 5. 职责边界

`routes/clients.py`：

- 保留原路径和权限依赖。
- 接收 query/form/upload 参数。
- 调用 service。
- 返回原 JSON 或 CSV response。

`services/clients.py`：

- 客户查询、创建、更新、删除。
- 客户 primary contact 同步。
- 客户详情聚合。
- 客户导出。
- 客户 brief。
- 只接收 db、模型、ctx/username、输入数据，不依赖 Request。

`schemas/clients.py`：

- 客户创建/更新字段定义。
- 如原接口使用 Form，不强制改成 JSON。

### 6. Data Scope 必须保留

客户域必须保留以下行为：

```text
列表按当前用户数据范围过滤
详情越权返回 404 或当前约定状态
导出不能绕过数据范围
创建时 owner_user_id / owner_dept_id 行为不变
更新/删除必须检查 write scope
```

迁移时必须逐个核对：

```text
apply_client_scope
assert_client_visible
assert_client_in_scope
filter_query_by_client_scope
```

如果旧逻辑中某接口尚未接 data scope，本阶段不要悄悄改变大范围业务语义；先保持旧行为，并在测试报告中列出后续需补点。

### 7. main.py 只保留注册

目标：

```python
from routes.clients import register_client_routes

register_client_routes(
    app,
    get_db=get_db,
    require_permission=require_permission,
    Client=Client,
    VisitRecord=VisitRecord,
    AuditLog=AuditLog,
    ...
)
```

不保留重复客户 API。

## Validation Tests

### 自动化测试

每个子阶段都执行：

```text
./venv/bin/python scripts/check_reverse_imports.py
./venv/bin/python scripts/check_route_permissions.py
./venv/bin/python -m pytest tests/test_permission_datascope.py -q
./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q
./venv/bin/python -m pytest tests/test_smoke_rbac.py tests/test_smoke_auth.py -q
./venv/bin/python -m pytest tests/ -q
```

验收：

- 普通销售只能看自己客户的测试通过。
- 普通销售访问别人客户详情仍被拒绝。
- SUPER_ADMIN 仍能看全部客户。
- RESTRICTED 用户访问客户相关 API 仍 403。
- `/api/export/clients` 不绕过数据范围。

子阶段额外验收：

```text
24A: 列表、详情、导出 data scope 不回归
24B: 新增、编辑、删除 write scope 不回归
24C: handoff-summary/details/brief 返回结构不变
```

### 手动验证

启动服务后验证：

```text
1. admin 登录
2. 打开 /customers
3. 客户列表加载
4. 新增客户
5. 编辑客户
6. 删除测试客户
7. 导出客户 CSV
8. 用 SALES 用户登录，确认只能看到自己范围内客户
```

### 测试报告

每个子阶段分别生成：

```text
reports/architecture/phase-03a-clients-read-report.md
reports/architecture/phase-03b-clients-write-report.md
reports/architecture/phase-03c-clients-related-report.md
```

报告必须包含：

- 本子阶段迁移出的客户 API 列表。
- 明确未迁移的客户 API 列表。
- 每个客户 API 对应的权限依赖。
- 每个客户 API 是否保留 data scope。
- 自动化测试结果。
- SALES 用户手动验证结果。
- 是否存在后续需要补 data scope 的客户相关接口。

## Common Failures And Fixes

### 客户列表数量变多

修复：

- 检查 list 查询是否漏了 `apply_client_scope`。
- 检查导出和列表是否使用同一过滤逻辑。

### 客户详情越权能访问

修复：

- 在详情 service 前加 `assert_client_visible`。
- 不要只依赖列表过滤。

### 新增客户后自己看不到

修复：

- 检查创建时 `owner_user_id`、`owner_dept_id`、销售/交付 owner 字段赋值。
- 检查 SALES 默认 data scope 是否为 assigned。

### 页面保存失败

修复：

- 对比原 Form 字段名。
- 不要把 Form 接口改成 JSON。
