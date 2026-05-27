# Phase 07 报告：roster_detail 前端 JS 外置

**状态：PASS**
**日期：2026-05-28**

## 执行范围

| 文件 | 拆分前行数 | 拆分后行数 |
|------|-----------|-----------|
| `templates/pages/roster_detail.html` | 1503 | **581** |
| `static/js/pages/roster-detail.js` | — | **927** |

**模板减少：922 行（−61%）**

### 脚本加载

- Vue 3 CDN：保留在 `{% block head_extra %}`
- 页面配置：保留在 `{% block content %}` 末尾（`window.__ROSTER_CLIENT_ID__ = {{ client_id }}`）
- 页面逻辑：`{% block page_scripts %}` 仅引用 `/static/js/pages/roster-detail.js`
- 未引入 `crm-api.js`（零重构，与 plan/28 一致）

### 明确未改动

- `routes/delivery_roster.py`、`routes/clients.py`、数据库、权限
- `roster_index.html`、`delivery_detail.html` 及其他页面
- Vue 模板 DOM / `{% raw %}` 块
- `IS_GLOBAL_ROSTER` 与全局/客户 API 分支逻辑

## API checklist

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

冒烟：`tests/test_smoke_delivery_roster.py`（roster CRUD/import 等）。

## 自动化验证

| # | 命令 | 结果 |
|---|------|------|
| 1 | `node --check static/js/pages/roster-detail.js` | **PASS** |
| 2 | `scripts/check_architecture.py` | **PASS** |
| 3 | `scripts/check_file_sizes.py` | **PASS**（`roster_detail.html` 低于 baseline 1503） |
| 4 | `pytest tests/ -q` | **80 passed** |

补充：TestClient 断言 `/customers/roster/0` 含配置脚本、`roster-detail.js`、`#roster-detail-app`；静态 JS 200。

## 浏览器验证

| # | 验证项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | `/customers/roster/0` 不白屏 | **PASS** | Playwright：`__ROSTER_CLIENT_ID__ === 0` |
| 2 | 外置 JS 已加载 | **PASS** | `roster-detail.js` in document.scripts |
| 3 | Console 无业务 JS error | **PASS** | Playwright hooks 为空 |
| 4 | `/customers/roster/{client_id}` 客户入口 | **PASS** | 用户已完成手动网页验证，无异常 |
| 5 | 筛选 / CRUD / 导入导出 / 日志 / 回滚 / 校验 / `?roster_add=1` | **PASS** | 用户已完成手动网页验证，无异常 |

## 剩余风险

| 风险 | 级别 | 说明 |
|------|------|------|
| 误删配置脚本 | 中 | 已保留在 content block；外置 JS 勿含 `{{ client_id }}` |
| 客户模式未自动化点测 | 低 | 自动化未逐按钮覆盖；客户入口与完整 UI 流已由用户手动网页验证 PASS |
| 外置 JS ~927 行仍偏大 | 低 | 可选 Phase 7b 接 `crm-api.js` 或拆模块 |

## 提交文件

```text
plan/28-phase7-roster-detail-frontend-split.md
templates/pages/roster_detail.html
static/js/pages/roster-detail.js
reports/architecture/phase-07-roster-detail-frontend-report.md
```
