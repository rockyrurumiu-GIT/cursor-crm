# Phase 05B: Delivery Pipeline Backend 迁移报告

> 状态：**PASS**

## 1. API Checklist

| # | 路由 | 类别 | 迁移状态 |
|---|------|------|----------|
| 1 | `GET /api/clients/{cid}/delivery/pipeline/insight` | insight 仪表盘 | ✅ routes/delivery_pipeline.py |
| 2 | `PUT /api/clients/{cid}/delivery/pipeline/insight-demand` | insight 需求量编辑 | ✅ routes/delivery_pipeline.py |
| 3 | `GET /api/clients/{cid}/delivery/pipeline` | list | ✅ routes/delivery_pipeline.py |
| 4 | `POST /api/clients/{cid}/delivery/pipeline` | create | ✅ routes/delivery_pipeline.py |
| 5 | `PUT /api/delivery/pipeline/row/{row_id}` | update | ✅ routes/delivery_pipeline.py |
| 6 | `DELETE /api/delivery/pipeline/row/{row_id}` | delete | ✅ routes/delivery_pipeline.py |
| 7 | `POST /api/clients/{cid}/delivery/pipeline/import` | import-client | ✅ routes/delivery_pipeline.py |
| 8 | `POST /api/delivery/pipeline/import` | import-global | ✅ routes/delivery_pipeline.py |
| 9 | `GET /api/clients/{cid}/delivery/pipeline/export` | export | ✅ routes/delivery_pipeline.py |
| 10 | `GET /api/clients/{cid}/delivery/pipeline/logs` | logs | ✅ routes/delivery_pipeline.py |
| 11 | `POST /api/clients/{cid}/delivery/pipeline/restore/latest` | restore | ✅ routes/delivery_pipeline.py |
| 12 | `GET /delivery/pipeline/{cid}/insight` | 页面入口 | 保留在 main.py，原因：页面入口暂不属于 API 迁移范围 |

## 2. 新增文件

| 文件 | 行数 | 用途 |
|------|------|------|
| `services/period_utils.py` | 82 | 公共周期/周标签工具函数（`week_label_from_date` 等 5 个），供 pipeline/roster 共享 |
| `schemas/delivery_pipeline.py` | 71 | 管道数据常量：导出表头、中英映射、导入别名 |
| `services/delivery_pipeline.py` | 424 | 管道数据业务逻辑 + 完整 insight 仪表盘计算 |
| `routes/delivery_pipeline.py` | 375 | 11 个 API handler + `register_delivery_pipeline_routes` 注册函数 |
| `tests/test_smoke_delivery_pipeline.py` | 103 | 5 条 smoke 测试：list、create、delete、import confirm、insight |

## 3. main.py 变化

| 指标 | 变化 |
|------|------|
| Phase 5B 迁移前行数 | 4535（5A 完成后） |
| Phase 5B 迁移后行数 | **3587** |
| 净减少 | **948 行** |
| 已移除项 | 11 个 API handler + 5 个周期函数 + pipeline helpers/constants |
| 页面路由 | 保留在 main.py（`/delivery/pipeline/{cid}/insight`） |

## 4. 设计决策

### 公共周期函数放置位置
- 5 个函数（`week_label_from_date`, `normalize_period_label`, `period_week_bounds`, `period_sort_key`, `extract_period_month`）迁入 `services/period_utils.py`
- main.py 中已删除对应的 thin import alias（无其他代码引用）
- 当前主要由 pipeline service 使用（`services/delivery_pipeline.py` 直接 import `services.period_utils`）
- 公共模块为后续 roster/其他域复用预留
- **无 roster → pipeline 依赖，无 pipeline → roster 依赖**

### insight 大函数处理
- 原 ~345 行内联 handler 整体提取为 `compute_pipeline_insight()` 单一入口函数
- 所有内部 helper（detail 构造、group 聚合、异常检测）作为闭包保留在函数内部
- handler 本身在 routes 中仅 1 行调用

### Python 3.14 f-string 兼容性
- Python 3.14 的新 f-string 解析器将 Unicode LEFT/RIGHT DOUBLE QUOTATION MARK（U+201C/U+201D）视为字符串定界符
- 迁移时在 `services/delivery_pipeline.py` 中使用 `\u201c`/`\u201d` 转义序列替代字面量
- 返回的错误消息内容不变

### 依赖注入模式
- `register_delivery_pipeline_routes(app, *, get_db, Client, PipelineEntry, InsightDemand, AuditLog, ...)`
- 共享工具函数（`strip_excel_sep`, `decode_upload_bytes`, `pick_latest_backup`, `set_csv_download_headers`）通过参数注入
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
71 passed, 62 warnings in 6.18s
```

### 新增 smoke 测试覆盖
| 测试 | 场景 |
|------|------|
| `test_list` | GET /api/clients/{cid}/delivery/pipeline 返回 200 + list |
| `test_create_row` | POST 正常新增一行 |
| `test_delete_row` | DELETE 正常删除 |
| `test_import_requires_confirm` | POST import 缺少 confirm=CONFIRM 返回 400 |
| `test_insight_returns_200` | GET insight 返回 200 + {rows, anomalies} |

## 6. 累计进度

| Phase | main.py 行数 | 净减少 |
|-------|-------------|--------|
| 迁移前（原始） | 6269 | — |
| 5A 完成 | 4535 | -1734 |
| **5B 完成** | **3587** | **-948**（累计 -2682） |

## 7. 总结

Phase 5B 完成。11 个 pipeline API handler 全部迁移至 `routes/delivery_pipeline.py`，通过 `register_delivery_pipeline_routes` 在 main.py 中注册。5 个公共周期函数迁入 `services/period_utils.py` 供 pipeline 和 roster 共享，不引入跨域直接依赖。所有原有 URL、参数、返回结构、权限检查保持不变。零回归，全部测试通过。
