# CRM 架构规则

本仓库处于「低风险拆分」过渡期。新增代码应遵循以下边界，避免 `main.py` 与巨型模板继续膨胀。

## 应用入口

- `main.py` 只做应用装配和过渡 glue code（ORM、engine、`register_*` 调用、页面路由等）。
- 完整搬移模型/engine 不在当前阶段目标内。

## Import 边界

以下目录/文件 **不允许** `from main import` 或 `import main`：

- `auth/`
- `routes/`
- `services/`
- `schemas/`
- `models/`
- `*_routes.py`
- `*_core.py`

`tests/` 允许 import `main` 以便 smoke / datascope 测试。

ORM 模型与依赖由调用方通过参数注入（见 Phase 0 `client_model` 模式）。

## 后端模块布局

| 类型 | 位置 |
|------|------|
| 新业务 API | `routes/<domain>.py` |
| 业务逻辑 | `services/<domain>.py` |
| 请求/响应模型 | `schemas/<domain>.py` |

### 历史过渡文件（暂不搬迁）

根目录已有以下 route 模块，**保持稳定**，不在架构阶段顺手大重构：

- `handoff_routes.py`
- `phase2_routes.py`
- `visit_routes.py`

架构阶段禁止顺手搬迁根目录旧 routes，除非对应阶段 plan 明确要求。

后续迁移须单独出计划与测试。

## 前端模块布局

- 新增页面 JS 必须进入 `static/js/pages/`。
- 公共 fetch/DOM/下载工具进入 `static/js/core/`。
- 不引入 Vite/Webpack 构建链（当前阶段）。

## 权限

- 业务 `/api/` 路由必须使用 `require_permission` 或 `require_any_permission`。
- 系统管理 API 使用 `system.*` 权限（见 `auth/routes.py`）。
- 导入、导出、文件访问须有权限保护；仅 `authenticate` 不够（`/api/files/access` 等待后续专项处理）。

## 自动化检查

```bash
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

各阶段测试报告：`reports/architecture/phase-XX-*.md`

## RMS 招聘模块

- RMS 在当前阶段作为 CRM 一级模块开发，不单独建仓库。
- 页面前缀使用 `/rms`，API 前缀使用 `/api/rms`。
- 表名统一使用 `rms_` 前缀。
- 权限码统一使用 `rms.*` 前缀。
- 复用现有 `clients` 表，不新建客户主数据。
- 不复用 `delivery_pipeline_entries` 作为 RMS 主表；它只可作为历史导入来源。
- RMS 后端遵循 `routes/rms_*.py`、`services/rms_*.py`、`schemas/rms_*.py`。
- RMS 前端 JS 放入 `static/js/pages/`。
- RMS 候选人入职后，通过显式动作转入交付花名册，不自动混写 delivery 表。

详细设计见 [`rms-architecture.md`](rms-architecture.md)；分期执行见 [`plan/29-rms-module-plan.md`](../plan/29-rms-module-plan.md)。
