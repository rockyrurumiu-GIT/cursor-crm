# Phase 02 测试报告：Delivery Settlement 后端域拆分

## 执行范围

### 本阶段改了什么

1. 新增目录与文件：
   - `routes/__init__.py`
   - `routes/delivery_settlement.py` — 8 个 settlement API 路由
   - `services/__init__.py`
   - `services/delivery_settlement.py` — settlement 业务逻辑函数与常量
   - `schemas/__init__.py`
   - `schemas/delivery_settlement.py` — 占位（当前 API 仍用 dict body）

2. 从 `main.py` 删除：
   - `_settlement_entry_to_dict`
   - `_normalize_settlement_payload`
   - `_normalize_settlement_amount`
   - `_resequence_settlement_serial_no` (per-client)
   - `_resequence_settlement_serial_no_all`
   - `SETTLEMENT_REQUIRED_FIELDS`
   - `SETTLEMENT_REQUIRED_LABELS`
   - `_validate_settlement_payload`
   - `_resolve_settlement_client_id`
   - `_settlement_dedup_key`
   - `_write_settlement_backup_csv`
   - `SETTLEMENT_EXPORT_HEADERS`
   - `SETTLEMENT_HEADER_MAP`
   - 8 个 settlement route 函数（`settlement_list`, `settlement_create_row`, `settlement_update_row`, `settlement_delete_row`, `settlement_import_csv`, `settlement_export_csv`, `settlement_logs`, `settlement_restore_latest_backup`）
   - `RESOURCE_DELIVERY_SETTLEMENT` import（已迁至 routes 模块）

3. 在 `main.py` 新增注册调用：
   ```python
   from routes.delivery_settlement import register_delivery_settlement_routes
   register_delivery_settlement_routes(
       app,
       get_db=get_db,
       Client=Client,
       DeliverySettlementEntry=DeliverySettlementEntry,
       AuditLog=AuditLog,
       backup_dir=BACKUP_DIR,
       max_file_size=MAX_FILE_SIZE,
       decode_upload_bytes=_decode_roster_upload_bytes,
       strip_excel_sep=_strip_excel_sep_directive,
       pick_latest_backup=_pick_latest_backup,
       set_csv_download_headers=_set_csv_download_headers,
   )
   ```

4. `main.py` 行数变化：7029 → 6593（减少 436 行）

### 明确没有改什么

- clients 域 — 不动
- roster / pipeline / handbook / interviews — 不动
- `delivery_detail.html` — 不动
- 前端页面 — 不动
- 权限配置 — 不动
- 数据库 migration — 不动

## 自动化测试

### 命令与结果

| 命令 | 结果 |
|------|------|
| `./venv/bin/python scripts/check_reverse_imports.py` | PASS（脚本恢复后重新验证） |
| `./venv/bin/python scripts/check_route_permissions.py` | PASS（WARNING: `/api/files/access` 仅 authenticate，已有预期） |
| `./venv/bin/python scripts/check_file_sizes.py` | PASS（strict 模式，WARNING: `delivery_turnover.html` 2089 行） |
| `./venv/bin/python scripts/check_architecture.py` | PASS |
| `./venv/bin/python -m pytest tests/test_smoke_settlement.py -q` | 2 passed |
| `./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q` | 9 passed |
| `./venv/bin/python -m pytest tests/test_permission_datascope.py -q` | 9 passed |
| `./venv/bin/python -m pytest tests/ -q` | **59 passed, 61 warnings** |

### 失败用例

无。

## 手动验证

路由注册验证（通过脚本）：

```
{'GET'} /api/delivery/settlement
{'POST'} /api/delivery/settlement
{'PUT'} /api/delivery/settlement/row/{row_id}
{'DELETE'} /api/delivery/settlement/row/{row_id}
{'POST'} /api/delivery/settlement/import
{'GET'} /api/delivery/settlement/export
{'GET'} /api/delivery/settlement/logs
{'POST'} /api/delivery/settlement/restore/latest
```

共 8 条路由，无重复。

## 风险检查

### 权限是否回归

- `settlement_list`: `require_permission("delivery.settlement.read")` ✓
- `settlement_create_row`: `require_permission("delivery.settlement.write")` ✓
- `settlement_update_row`: `require_permission("delivery.settlement.write")` ✓
- `settlement_delete_row`: `require_permission("delivery.settlement.write")` ✓
- `settlement_import_csv`: `require_permission("delivery.settlement.write")` ✓
- `settlement_export_csv`: `require_permission("delivery.settlement.read")` ✓
- `settlement_logs`: `require_permission("delivery.settlement.read")` ✓
- `settlement_restore_latest_backup`: `require_permission("delivery.settlement.write")` ✓

权限未弱化，RBAC 测试通过。

### API 路径是否变化

无变化，8 个路径与原 `main.py` 完全一致。

### 数据范围是否保留

- **list** 保留现有 `filter_query_by_client_scope` data scope（`RESOURCE_DELIVERY_SETTLEMENT`, `"read"`, `DeliverySettlementEntry.client_id`, `Client`）。`test_delivery_settlement_scoped_by_delivery_owner` 通过。
- **export** 原代码无 scope 过滤（直接 `db.query(DeliverySettlementEntry).order_by(...).all()`），本阶段保持原样，**未添加 scope**。后续另开权限修复阶段处理。

### 导入导出是否可用

迁移后保留原逻辑：
- import 使用 `SETTLEMENT_HEADER_MAP` 映射 + dedup 去重 + `_resequence_settlement_serial_no_all`
- export 使用 `SETTLEMENT_EXPORT_HEADERS` + `_settlement_entry_to_dict` + CSV writer
- 列映射、header normalize 逻辑完全未变

## 问题与修复建议

### 已修复

| 问题 | 根因 | 修复 |
|------|------|------|
| `services/delivery_settlement.py` syntax error | Write 工具将 Unicode 左右双引号（U+201C/U+201D）转换为 ASCII `"`，在 f-string 中产生语法冲突 | 使用 `\u201c`/`\u201d` 转义序列表示 |
| `scripts/check_reverse_imports.py` 缺失 | 文件从未 commit 到 git，工作区文件丢失 | 按 Plan 22 规范重新创建，验证通过 |

### 待后续处理

| 问题 | 建议 |
|------|------|
| export 无 data scope 过滤 | 后续权限修复阶段统一加 scope（需确认业务需求：admin 导出全量 vs. 按人员范围过滤） |

### 是否阻塞进入下一阶段

否。

## 结论

**PASS**
