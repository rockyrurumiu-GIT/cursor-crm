# Phase 03B 测试报告：Clients Write/Delete 拆分

## 执行范围

### 本阶段改了什么

1. 在 `routes/clients.py` 新增 `register_client_write_routes()` 函数，包含 3 个写路由：
   - `POST /api/clients` (create_client)
   - `PUT /api/clients/{client_id}` (update_client)
   - `DELETE /api/clients/{client_id}` (delete_client)

2. 从 `main.py` 删除上述 3 个路由函数（约 158 行）

3. 在 `main.py` 新增注册调用：
   ```python
   register_client_write_routes(
       app,
       get_db=get_db,
       Client=Client,
       Contact=Contact,
       Opportunity=Opportunity,
       AuditLog=AuditLog,
       VisitRecord=VisitRecord,
       DeliveryHandbookFile=DeliveryHandbookFile,
       upload_dir=UPLOAD_DIR,
       trash_dir=TRASH_DIR,
       sync_primary_contact=_sync_client_primary_contact,
   )
   ```

4. `main.py` 行数变化：6470 → 6312（减少 158 行）

### 明确没有改什么

- `/api/stats` 的 handoff scope — 不修
- `GET /api/clients/handoff-summary` (24C) — 不动
- `GET /api/clients/{client_id}/details` (24C) — 不动
- `GET /api/clients/{client_id}/brief` (24C) — 不动
- settlement 域 — 不动
- roster / pipeline / handbook / interviews — 不动
- `delivery_detail.html` — 不动
- 前端页面 — 不动
- 数据库 migration — 不动

## 自动化测试

### 命令与结果

| 命令 | 结果 |
|------|------|
| `./venv/bin/python scripts/check_reverse_imports.py` | PASS |
| `./venv/bin/python scripts/check_route_permissions.py` | PASS（WARNING: `/api/files/access`，已有预期） |
| `./venv/bin/python scripts/check_file_sizes.py` | PASS（strict 模式，WARNING: `delivery_turnover.html` 2089 行） |
| `./venv/bin/python scripts/check_architecture.py` | PASS（三脚本均通过） |
| `./venv/bin/python -m pytest tests/test_permission_datascope.py -q` | 9 passed |
| `./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q` | 9 passed |
| `./venv/bin/python -m pytest tests/ -q` | **59 passed, 61 warnings** |

### 失败用例

无。

## 每个 API 的权限与 Data Scope 保留情况

| API | 权限 | Data Scope | 保留状态 |
|-----|------|-----------|---------|
| `POST /api/clients` | `crm.clients.write` | `assert_data_scope(ctx, RESOURCE_CRM_CLIENT, "write")` + `default_owner_fields` | ✓ 保留 |
| `PUT /api/clients/{client_id}` | `crm.clients.write` | `ensure_client_access(action="write")` + `scoped_client_query(action="write")` for duplicate check | ✓ 保留 |
| `DELETE /api/clients/{client_id}` | `crm.clients.write` | `ensure_client_access(action="write")` | ✓ 保留 |

## 关键行为验证

| 行为 | 保留 |
|------|------|
| 创建客户时 `owner_user_id` / `owner_dept_id` 赋值 | ✓ `default_owner_fields(ctx)` |
| 创建/更新后同步首要联系人到 contacts 表 | ✓ `sync_primary_contact(db, client)` |
| 更新时客户改名触发文件夹重命名（uploads + handbooks） | ✓ |
| 更新时 visit 附件路径同步更新 | ✓ |
| 更新时 handbook stored_path 同步更新 | ✓ |
| 删除时文件移入回收站 | ✓ |
| 删除时清除 DeliveryHandbookFile 记录 | ✓ |
| 更新时审计日志记录每个字段变更 | ✓ |
| 表单字段名完全不变（Form fields） | ✓ |

## 风险检查

### 权限是否回归

3 个 API 均保留 `require_permission("crm.clients.write")`，RBAC 测试通过。

### API 路径是否变化

无变化。

### 数据范围是否保留

- create: `assert_data_scope` 确保用户有写权限
- update: `ensure_client_access(action="write")` 确保用户对该客户有写权限
- delete: 同 update

### 路由注册顺序

```
GET  /api/clients/handoff-summary  [32]  ← 固定路径，最先
GET  /api/clients                  [34]  ← 精确匹配
GET  /api/clients/{client_id}      [35]  ← 路径参数
POST /api/clients                  [36]  ← 不同 method，无冲突
PUT  /api/clients/{client_id}      [37]
DELETE /api/clients/{client_id}    [38]
```

无路径冲突。

## 问题与修复建议

### 已解决

无问题出现，一次通过。

### 后续需关注

| 项目 | 说明 |
|------|------|
| `_sync_client_primary_contact` 仍在 main.py | 24C 完成后可考虑迁入 services/clients.py |
| `_scoped_client_query` / `_ensure_client_access` 薄包装 | 24C 完成后可删除 main.py 中的包装 |
| PUT/DELETE 成功路径 smoke test 缺失 | 现有测试覆盖了 POST 创建和 GET list/detail 的 scope 行为，但无 PUT/DELETE 200 成功路径覆盖。代码为纯搬移，非阻塞；建议后续补一个 smoke：create → update → delete，验证 200 和返回结构 |

### 是否阻塞进入下一阶段

否。

## 结论

**PASS**
