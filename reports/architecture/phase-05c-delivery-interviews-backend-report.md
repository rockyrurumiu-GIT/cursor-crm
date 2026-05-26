# Phase 5C: Delivery Interviews 后端拆分 — 报告

## 状态: PASS

## API Checklist

| # | API | 方法 | 权限 | Data Scope 现状 |
|---|-----|------|------|-----------------|
| 1 | `/api/clients/{client_id}/delivery/interviews` | GET | delivery.interviews.read | 保持旧行为（按 client_id 路径过滤，无全局 data scope） |
| 2 | `/api/clients/{client_id}/delivery/interviews` | POST | delivery.interviews.write | 保持旧行为 |
| 3 | `/api/clients/{client_id}/delivery/interviews/mark-employment-left` | POST | delivery.interviews.write | 保持旧行为 |
| 4 | `/api/delivery/interviews/row/{row_id}` | PUT | delivery.interviews.write | 保持旧行为（按 row_id 定位，无 client-level scope） |
| 5 | `/api/delivery/interviews/row/{row_id}` | DELETE | delivery.interviews.write | 保持旧行为 |
| 6 | `/api/clients/{client_id}/delivery/interviews/import` | POST | delivery.interviews.write | 保持旧行为 |
| 7 | `/api/delivery/interviews/import` | POST | delivery.interviews.write | 保持旧行为（global form 入口） |
| 8 | `/api/clients/{client_id}/delivery/interviews/export` | GET | delivery.interviews.read | 保持旧行为 |
| 9 | `/api/clients/{client_id}/delivery/interviews/logs` | GET | delivery.interviews.read | 保持旧行为 |
| 10 | `/api/clients/{client_id}/delivery/interviews/restore/latest` | POST | delivery.interviews.write | 保持旧行为 |

**页面路由**：本阶段不迁页面入口，delivery detail 相关页面仍保留在 main.py。

## 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `services/csv_utils.py` | 13 | 公共 CSV 工具函数（`strip_csv_header_noise`） |
| `schemas/delivery_interviews.py` | 90 | Interviews 常量：INTERVIEW_EXPORT_HEADERS、INTERVIEW_HEADER_MAP、INTERVIEW_IMPORT_ALIASES |
| `services/delivery_interviews.py` | 172 | 9 个业务逻辑函数 |
| `routes/delivery_interviews.py` | 398 | 10 个 API handler + `register_delivery_interviews_routes` |
| `tests/test_smoke_delivery_interviews.py` | 110 | Smoke 测试（list/create/import-confirm/mark-left） |

## main.py 行数变化

| 阶段 | 行数 |
|------|------|
| Phase 5B 结束 | 3587 |
| Phase 5C 结束 | 3031 |
| **净减少** | **556** |

## 设计决策

### 1. 公共模块 `services/csv_utils.py`

`_strip_csv_header_noise` 原为 `services/delivery_roster.py` 的私有函数，但 interviews 导入逻辑也需使用。为避免 interviews→roster 的跨域直接依赖，将其抽到 `services/csv_utils.py` 作为公共工具函数。roster 和 interviews 均从此 import。

### 2. Callable 注入保持

`normalize_interview_person_name` 和 `interview_mark_left_for_normalized_name_keys` 迁入 `services/delivery_interviews.py` 后，由 `main.py` 导入并通过 lambda 包装后注入给 `register_delivery_roster_routes`。roster 路由模块不直接 import interviews service，保持单向依赖。

### 3. `_ensure_interview_schema_compat()` 保留 main.py

该函数在应用初始化时执行 DB schema 兼容迁移，属于基础设施层，不迁入 interviews 域。

### 4. 潜在 bug 修复

原 main.py interviews import handler 使用 `_strip_csv_header_noise` 但缺少 import（Phase 5A 遗留）。迁移后该函数在 `routes/delivery_interviews.py` 中正确从 `services.csv_utils` import，问题自然消除。

## 验证结果

```
$ ./venv/bin/python scripts/check_architecture.py
Reverse import check passed.
Route permission check passed with warnings.
File size check passed.

$ ./venv/bin/python -m pytest tests/test_smoke_delivery_interviews.py tests/test_rbac_api_modules.py tests/test_permission_datascope.py -q
22 passed

$ ./venv/bin/python -m pytest tests/ -q
75 passed
```

## 依赖关系图

```
main.py
  ├── from services.delivery_interviews import normalize_interview_person_name, interview_mark_left_for_normalized_name_keys_svc
  ├── from routes.delivery_interviews import register_delivery_interviews_routes
  │
  ├── register_delivery_roster_routes(..., interview_mark_left_fn=lambda..., normalize_interview_name_fn=...)
  └── register_delivery_interviews_routes(..., InterviewEntry=DeliveryInterviewEntry, ...)

routes/delivery_interviews.py
  ├── from schemas.delivery_interviews import INTERVIEW_EXPORT_HEADERS, INTERVIEW_HEADER_MAP, INTERVIEW_IMPORT_ALIASES
  ├── from services.csv_utils import strip_csv_header_noise
  └── from services.delivery_interviews import (9 functions)

services/delivery_interviews.py
  └── from schemas.delivery_interviews import INTERVIEW_EXPORT_HEADERS, INTERVIEW_HEADER_MAP

services/delivery_roster.py
  └── from services.csv_utils import strip_csv_header_noise (替换原私有定义)
```

无反向依赖，无跨域 service 直接 import。
