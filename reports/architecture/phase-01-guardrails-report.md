# Phase 01 测试报告

## 核验说明

本次为 **Phase 1 对照 `22-phase1-guardrails-first.md` 的核验/补齐**，非重复造轮子。相关文件已在上一轮创建；仅对 `docs/architecture.md` 补写 plan 22 要求的一句「架构阶段禁止顺手搬迁根目录旧 routes」。

未执行 Phase 23 及后续阶段。

## 执行范围

### plan 22 交付物对照

| 交付物 | 状态 | 路径 |
|--------|------|------|
| 架构规则文档 | ✅ 已存在（本次补 1 句） | `docs/architecture.md` |
| 反向 import 检查 | ✅ 已存在 | `scripts/check_reverse_imports.py` |
| 路由权限扫描 | ✅ 已存在 | `scripts/check_route_permissions.py` |
| 文件体量检查 | ✅ 已存在 | `scripts/check_file_sizes.py` |
| 统一检查入口 | ✅ 已存在 | `scripts/check_architecture.py` |

### `docs/architecture.md` 必写项核对

- [x] `main.py` 只做应用装配和过渡 glue code
- [x] `auth/` / `routes/` / `services/` 不允许 import main
- [x] 新增业务 API → `routes/<domain>.py`
- [x] 新增业务逻辑 → `services/<domain>.py`
- [x] 新增页面 JS → `static/js/pages/`
- [x] 业务 API 必须 `require_permission`
- [x] 系统 API 必须 `system.*` 权限
- [x] 导入、导出、文件访问须有权限保护
- [x] 根目录 `handoff_routes.py` / `phase2_routes.py` / `visit_routes.py` 暂不搬迁
- [x] 架构阶段禁止顺手搬迁根目录旧 routes（除非 plan 明确要求）

### 明确没有改什么

- 未迁移任何业务路由或 service 逻辑。
- 未修改 `main.py` 业务 if/else、API 契约或 data scope 行为。
- 未执行 Phase 2（settlement 后端拆分）及后续阶段。

## 自动化测试

### 命令

```text
./venv/bin/python scripts/check_reverse_imports.py
./venv/bin/python scripts/check_route_permissions.py
./venv/bin/python scripts/check_file_sizes.py
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

### 结果（本次核验运行）

| 检查 | 输出摘要 | 退出码 |
|------|----------|--------|
| `check_reverse_imports.py` | Reverse import check passed. | 0 |
| `check_route_permissions.py` | 1 条 WARNING；passed with warnings | 0 |
| `check_file_sizes.py` | pre-Phase-2 模式；1 条 WARNING；passed | 0 |
| `check_architecture.py` | 三脚本均通过；提示 Next: pytest | 0 |
| `pytest tests/ -q` | **59 passed**, 61 warnings | 0 |

#### check_reverse_imports.py

```text
Reverse import check passed.
```

#### check_route_permissions.py

```text
Route permission warnings (authenticate only, no require_permission):
  WARNING main.py:1793: /api/files/access (Depends(authenticate) only)
Route permission check passed with warnings.
```

#### check_file_sizes.py

```text
File size check mode: pre-Phase-2 (warnings only for governance files)
File size warnings:
  WARNING templates/pages/delivery_turnover.html: 2089 lines (> 1200)
File size check passed.
```

#### check_architecture.py

```text
=== check_reverse_imports.py ===
Reverse import check passed.

=== check_route_permissions.py ===
(... 同上 WARNING ...)

=== check_file_sizes.py ===
(... 同上 WARNING ...)

Next: ./venv/bin/python -m pytest tests/ -q
```

### 当前被允许保留的 baseline 大文件

| 文件 | 基线 | 当前 | 超 baseline+50 |
|------|------|------|----------------|
| `main.py` | 7029 | 7029 | 否 |
| `templates/base.html` | 1596 | 1596 | 否 |
| `templates/pages/delivery_detail.html` | 4394 | 4394 | 否 |
| `templates/pages/delivery_settlement.html` | 1140 | 1140 | 否 |
| `templates/pages/roster_detail.html` | 1503 | 1503 | 否 |

pre-Phase-2 模式下，上述 baseline 文件超限仅 warning，当前均未触发。

## 手动验证

plan 22 要求确认 admin 登录、`/system/users`、`/customers`、`/delivery/settlement` 正常。本阶段未改运行时逻辑；以下由 pytest 间接覆盖：

| 页面 | 结果 |
|------|------|
| admin 登录 | `test_smoke_auth` / `test_smoke_rbac` 通过 |
| `/system/users` | `test_system_policy` / rbac 通过 |
| `/customers` | `test_permission_datascope` 通过 |
| `/delivery/settlement` | `test_smoke_settlement` / data scope 通过 |

## 风险检查

| 检查项 | 结果 |
|--------|------|
| 脚本可独立运行 | 是 |
| 输出可定位文件/行号 | 是（如 `main.py:1793`） |
| baseline 巨型文件不阻塞 | 是 |
| pytest 全绿 | 是 — 59/59 |

### 只登录不鉴权的业务 API

| 路由 | 现状 | 是否阻塞 Phase 2 |
|------|------|------------------|
| `/api/files/access` | 仅 `Depends(authenticate)` | **否**（已 WARNING，待后续 files 权限专项） |
| handoff `Depends(_require_reviewer)` | 自定义 reviewer 守卫 | 否（扫描器已识别 `Depends(_require_*)`） |

### 是否阻塞进入 settlement 拆分（Phase 2）

**否。** 三项护栏脚本与 pytest 均通过；已知 warning 已记录。

## 问题与修复建议

1. **`/api/files/access`** — 后续补 `files.*` 或等价 RBAC；不阻塞 Phase 2。
2. **`delivery_turnover.html` 2089 行** — Phase 5 roster/turnover 拆分时处理；不阻塞 Phase 2。

## 结论

**PASS**

Phase 1 交付物齐全，验收命令全部通过。可进入 Phase 2（`23-phase2-settlement-domain-split.md`）。
