# 22 Phase 1：先加架构护栏

## Summary

本阶段在真正拆业务域之前，先增加架构护栏，防止拆分过程中出现权限回归、反向 import 回潮、文件继续膨胀、API 路由遗漏等问题。

本阶段可以新增脚本、测试和文档，但不迁移业务路由，不移动大段业务逻辑。

## Implementation Changes

### 1. 新增架构规则文档

新增：

```text
docs/architecture.md
```

必须写清楚：

```text
main.py 只做应用装配和过渡 glue code
auth/ 不允许 import main
routes/ 不允许 import main
services/ 不允许 import main
新增业务 API 必须进入 routes/<domain>.py
新增业务逻辑必须进入 services/<domain>.py
新增页面 JS 必须进入 static/js/pages/
业务 API 必须 require_permission
系统 API 必须 system.* 权限
导入、导出、文件访问必须有权限保护
根目录已有 handoff_routes.py、phase2_routes.py、visit_routes.py 暂不搬迁
架构阶段禁止顺手搬迁根目录旧 routes，除非对应阶段明确要求
```

说明：

- 新模块必须进入 `routes/`、`services/`、`schemas/`。
- 根目录已有 `handoff_routes.py`、`phase2_routes.py`、`visit_routes.py` 属于历史过渡文件，先保持稳定，不在 Phase 1 或 Phase 2 顺手大重构。
- 后续如要迁移这些历史 routes，必须单独出计划、单独测试。

### 2. 新增反向 import 检查

新增：

```text
scripts/check_reverse_imports.py
```

检查：

```text
auth/
routes/
services/
schemas/
models/
*_routes.py
*_core.py
```

不允许出现：

```text
from main import
import main
```

tests 目录允许 import main。

### 3. 新增路由权限扫描

新增：

```text
scripts/check_route_permissions.py
```

扫描：

```text
main.py
*_routes.py
routes/**/*.py
```

规则：

- `/api/auth/login`、`/api/auth/logout`、`/api/me`、`/api/account/change-password` 可以白名单。
- 业务 `/api/` 路由必须出现 `require_permission` 或 `require_any_permission`。
- 如果只出现 `Depends(authenticate)`，脚本必须报出 warning 或 error。

第一版允许静态扫描，不要求 AST 完美，但输出必须能定位文件和行号。

### 4. 新增文件体量检查

新增：

```text
scripts/check_file_sizes.py
```

当前基线：

```text
main.py = 7029
templates/base.html = 1596
templates/pages/delivery_detail.html = 4394
templates/pages/delivery_settlement.html = 1140
templates/pages/roster_detail.html = 1503
```

规则：

- Phase 2 完成前，`main.py` 和 `delivery_detail.html` 超过当前基线 50 行只给 warning，避免误伤必要 bugfix。
- Phase 2 PASS 后，`main.py` 和 `delivery_detail.html` 继续超过治理基线 50 行必须给 error，除非测试报告明确记录原因。
- 新增 `templates/pages/*.html` 超过 1200 行给 warning。
- 新增 `static/js/pages/*.js` 超过 1200 行给 warning。

### 5. 新增统一架构检查入口

新增：

```text
scripts/check_architecture.py
```

执行：

```text
check_reverse_imports.py
check_route_permissions.py
check_file_sizes.py
```

第一版不强制跑全量 pytest，但输出最后必须提示：

```text
Next: ./venv/bin/python -m pytest tests/ -q
```

## Validation Tests

### 自动化测试

执行：

```text
./venv/bin/python scripts/check_reverse_imports.py
./venv/bin/python scripts/check_route_permissions.py
./venv/bin/python scripts/check_file_sizes.py
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

验收：

- 检查脚本可以独立运行。
- 输出清晰，可定位文件。
- 当前已知巨型文件只作为 baseline warning，不阻塞。
- 若发现真实权限缺失，必须修复后再继续。
- pytest 全绿。

### 手动验证

无需大范围手动页面验证，但必须确认：

```text
admin 登录正常
/system/users 正常
/customers 正常
/delivery/settlement 正常
```

### 测试报告

生成：

```text
reports/architecture/phase-01-guardrails-report.md
```

报告必须包含：

- 三个检查脚本的输出摘要。
- 当前被允许保留的 baseline 大文件。
- 是否发现只登录不鉴权的业务 API。
- 是否阻塞进入 settlement 拆分。

## Common Failures And Fixes

### 路由权限扫描误报

修复：

- 先确认是否真的业务 API。
- 如果是 auth/me/change-password 这类公共认证接口，加入集中白名单。
- 如果是业务 API，补 `require_permission`，不要加入白名单逃避。

### 文件体量检查全部失败

修复：

- 当前大文件作为 baseline warning，不应第一版全部 error。
- error 只针对新增长或新增巨型文件。

### 反向 import 检查失败

修复：

- 不要在底层模块 import `main`。
- 通过参数传入模型、settings、依赖函数。
