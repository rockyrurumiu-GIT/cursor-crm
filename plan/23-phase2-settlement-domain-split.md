# 23 Phase 2：拆分 Delivery Settlement 后端域

## Summary

本阶段作为第一个真实后端拆分试点，只拆 `delivery.settlement`。原因是 settlement 已有 smoke 测试，接口边界相对清楚，回归可快速发现。

本阶段不拆 clients、roster、pipeline、handbook，不拆前端页面 JS。

## Implementation Changes

### 1. 新增后端目录

如果还不存在，新增：

```text
routes/
services/
schemas/
```

并加入：

```text
routes/__init__.py
services/__init__.py
schemas/__init__.py
```

### 2. 新增 settlement 模块

新增：

```text
routes/delivery_settlement.py
services/delivery_settlement.py
schemas/delivery_settlement.py
```

迁移范围：

```text
GET    /api/delivery/settlement
POST   /api/delivery/settlement
PUT    /api/delivery/settlement/row/{row_id}
DELETE /api/delivery/settlement/row/{row_id}
POST   /api/delivery/settlement/import
GET    /api/delivery/settlement/export
GET    /api/delivery/settlement/logs
POST   /api/delivery/settlement/restore/latest
```

### 3. 职责边界

`routes/delivery_settlement.py`：

- 注册原路径。
- 保留原权限依赖。
- 接收 `db`、`UploadFile`、body。
- 调用 service。
- 返回原响应结构。

`services/delivery_settlement.py`：

- `_settlement_entry_to_dict`
- `_normalize_settlement_payload`
- `_normalize_settlement_amount`
- `_validate_settlement_payload`
- `_resolve_settlement_client_id`
- `_settlement_dedup_key`
- `_write_settlement_backup_csv`
- `_resequence_settlement_serial_no_all`
- restore/import/export 逻辑

`schemas/delivery_settlement.py`：

- 仅放 settlement 请求/响应模型。
- 如果现阶段接口仍使用 dict body，可以先定义最小 Pydantic 模型或保留 dict，不强行改变外部行为。

### 4. 保留数据范围和权限

必须保留：

```text
delivery.settlement.read
delivery.settlement.write
filter_query_by_client_scope / scoped client filtering
```

如果原 settlement list/export 已按客户可见范围过滤，迁移后必须完全保留。

注意：以当前旧代码真实行为为准。若 list 已有 data scope 而 export 原本没有 scope 过滤，本阶段迁移时不要顺手修 export；必须保持原行为，并在 `phase-02-settlement-report.md` 中明确记录：

```text
list 保留现有 data scope；
export 若原无 scope 过滤则保持原样，后续另开权限修复阶段处理。
```

### 5. main.py 只保留注册

目标：

```python
from routes.delivery_settlement import register_delivery_settlement_routes

register_delivery_settlement_routes(
    app,
    get_db=get_db,
    require_permission=require_permission,
    Client=Client,
    DeliverySettlementEntry=DeliverySettlementEntry,
    ...
)
```

不允许保留重复 settlement route。

## Validation Tests

### 自动化测试

执行：

```text
./venv/bin/python scripts/check_reverse_imports.py
./venv/bin/python scripts/check_route_permissions.py
./venv/bin/python -m pytest tests/test_smoke_settlement.py -q
./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q
./venv/bin/python -m pytest tests/test_permission_datascope.py -q
./venv/bin/python -m pytest tests/ -q
```

验收：

- settlement CRUD smoke 通过。
- RESTRICTED 用户访问 settlement read/write 仍 403。
- DELIVERY 用户数据范围测试仍通过。
- 没有重复路由导致异常。

### 手动验证

启动服务后验证：

```text
1. admin 登录
2. 打开 /delivery/settlement
3. 结算列表能加载
4. 新增一条结算记录
5. 编辑该记录
6. 删除该记录
7. 导出 CSV
8. 查看日志
9. 如有测试 CSV，执行导入
```

### 测试报告

生成：

```text
reports/architecture/phase-02-settlement-report.md
```

报告必须包含：

- 迁移出的函数清单。
- 原 settlement 路由是否已从 `main.py` 删除。
- 自动化测试结果。
- 手动验证截图或文字结果。
- 如果导入导出失败，给出具体失败文件、错误行、修复建议。

## Common Failures And Fixes

### API 404

修复：

- 检查 `register_delivery_settlement_routes()` 是否在 `main.py` 调用。
- 检查路径是否和原路径完全一致。

### 权限从 403 变成 200

修复：

- 检查迁移后的 route 是否保留 `Depends(require_permission(...))`。
- 不要用 `authenticate` 替代 `require_permission`。

### 导出为空

修复：

- 检查查询是否错误套用了空 data scope。
- 检查 service 是否拿到同一个 `DeliverySettlementEntry` 模型。
- 检查 CSV writer 字段映射是否和原逻辑一致。

### 导入丢列

修复：

- 回看原 `main.py` 的列映射。
- 不要在迁移时顺手改 header normalize 逻辑。
