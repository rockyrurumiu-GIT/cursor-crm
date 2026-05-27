# 28 Phase 7：roster_detail 前端 JS 外置

## Summary

本阶段只做 `roster_detail.html` 的 inline Vue 脚本外置，模式与 Phase 6 turnover 一致：**原样迁移、零重构**。

与 Phase 6 的差异：**必须保留** `{% block content %}` 末尾的 `window.__ROSTER_CLIENT_ID__ = {{ client_id }}` 配置脚本；外置 JS 在 `page_scripts` 中加载，读取该全局变量以区分整体花名册（`client_id=0`）与客户花名册。

## Preconditions

```text
Phase 6 PASS
./venv/bin/python -m pytest tests/ -q 全绿
static/js/pages/delivery-turnover.js 外置已验证
```

## Scope

### In scope

- `templates/pages/roster_detail.html` — 移除大段 inline `<script>`，保留配置脚本
- `static/js/pages/roster-detail.js` — 原样承载 L581–1501 逻辑
- `reports/architecture/phase-07-roster-detail-frontend-report.md`

### Out of scope

- `routes/delivery_roster.py`、`routes/clients.py`、数据库、权限
- `roster_index.html`、`delivery_detail.html`、其他页面
- 引入 npm / Vite / Webpack
- 迁移到 `crm-api.js`（可选 Phase 7b）
- 修改 Vue 模板 DOM

## 页面入口（手工验证）

| 场景 | URL |
|------|-----|
| 整体花名册 | `/customers/roster/0` |
| 客户花名册 | `/customers/roster/{client_id}` |
| 面试跳转新增 | `/customers/roster/{clientId}?roster_add=1&prefill_full_name=...` |

## API checklist（`IS_GLOBAL_ROSTER` 分支）

| Method | Path | 模式 |
|--------|------|------|
| GET | `/api/clients/{client_id}/brief` | 客户 |
| GET | `/api/clients` | 共用 |
| GET | `/api/roster` | 全局 |
| GET | `/api/clients/{client_id}/roster` | 客户 |
| POST | `/api/roster` | 全局 |
| POST | `/api/clients/{client_id}/roster` | 客户 |
| PUT | `/api/roster/{id}` | 共用 |
| DELETE | `/api/roster/{id}` | 共用 |
| POST | `/api/roster/import` | 全局 |
| POST | `/api/clients/{client_id}/roster/import` | 客户 |
| GET | `/api/roster/export` | 全局 |
| GET | `/api/clients/{client_id}/roster/export` | 客户 |
| GET | `/api/roster/logs` | 全局日志 |
| GET | `/api/clients/{client_id}/details` | 客户日志 |
| POST | `/api/roster/restore/latest` | 全局 |
| POST | `/api/clients/{client_id}/roster/restore/latest` | 客户 |

## Implementation

1. 新建 `static/js/pages/roster-detail.js`（L581–1501 原样）
2. 模板保留配置脚本；`page_scripts` 仅 `<script src="/static/js/pages/roster-detail.js">`
3. 验证：`node --check`、architecture、file_sizes、pytest
4. 浏览器双入口验证

## Success criteria

- `roster_detail.html` 行数明显下降（约 ~581）
- `roster-detail.js` 通过 `node --check`
- pytest 全绿
- `/customers/roster/0` 与 `/customers/roster/{id}` 行为不变

## Commit

```text
plan/28-phase7-roster-detail-frontend-split.md
templates/pages/roster_detail.html
static/js/pages/roster-detail.js
reports/architecture/phase-07-roster-detail-frontend-report.md
```

Message: `frontend: extract roster detail page script`
