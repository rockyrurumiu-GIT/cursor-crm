# Phase 06 报告：delivery_turnover 前端 JS 外置

**状态：PASS**
**日期：2026-05-28**

## 执行范围

| 文件 | 拆分前行数 | 拆分后行数 |
|------|-----------|-----------|
| `templates/pages/delivery_turnover.html` | 2089 | **1117** |
| `static/js/pages/delivery-turnover.js` | — | **977** |

**模板减少：972 行（−46%）**

### 脚本加载

- Vue 3 CDN：保留在 `{% block head_extra %}`（L4）
- 页面逻辑：`{% block page_scripts %}` 仅引用 `/static/js/pages/delivery-turnover.js`
- 未引入 `crm-api.js`（本阶段零重构，与 plan/27 一致）

### 明确未改动

- `routes/delivery_roster.py`、数据库、权限模型
- `delivery_detail.html` 及其他 delivery 页面
- Vue 模板 DOM / `{% raw %}` 块
- 构建工具链

## API checklist（页面 fetch）

| Method | Path | 后端 |
|--------|------|------|
| GET | `/api/roster/turnover` | `routes/delivery_roster.py` |
| GET | `/api/roster/turnover/dashboard` | 同上 |
| POST | `/api/roster` | 同上 |
| PUT | `/api/roster/{id}` | 同上 |
| DELETE | `/api/roster/{id}` | 同上 |
| POST | `/api/roster/turnover/import` | 同上 |
| GET | `/api/roster/turnover/export` | 同上 |
| GET | `/api/roster/logs` | 同上 |
| POST | `/api/roster/turnover/restore/latest` | 同上 |

冒烟：`tests/test_smoke_delivery_roster.py::TestTurnoverDashboard`（list + dashboard）。

## 自动化验证

| # | 命令 | 结果 |
|---|------|------|
| 1 | `node --check static/js/pages/delivery-turnover.js` | **PASS** |
| 2 | `scripts/check_architecture.py` | **PASS** |
| 3 | `scripts/check_file_sizes.py` | **PASS**（`delivery_turnover.html` >1200 warning **已消除**） |
| 4 | `pytest tests/ -q` | **80 passed** |

补充：

- TestClient（legacy-bootstrap cookie）：`GET /delivery/turnover` 含 `delivery-turnover.js` 与 `#delivery-turnover-app`
- `GET /static/js/pages/delivery-turnover.js` 200，含 `.mount('#delivery-turnover-app')`

## 浏览器验证

| # | 验证项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | 打开 `/delivery/turnover` 不白屏 | **PASS** | Playwright headless：`#delivery-turnover-app` 有内容 |
| 2 | 外置 JS 加载 | **PASS** | `delivery-turnover.js` 在 document.scripts 中 |
| 3 | Vue 可用 | **PASS** | `typeof Vue !== 'undefined'` |
| 4 | Console 无业务 JS error | **PASS** | `pageerror` / `console.error` 为空 |
| 5 | 离职池列表加载 | **PASS** | 页面渲染 + `GET /api/roster/turnover` 冒烟 |
| 6 | 分析看板 API | **PASS** | `GET /api/roster/turnover/dashboard` 冒烟 |
| 7 | 筛选 / CRUD / 导入导出 / 日志 / 回滚 UI | **PASS** | 用户已完成手动网页验证，全部通过 |

## 剩余风险

| 风险 | 级别 | 说明 |
|------|------|------|
| 浏览器缓存旧 inline 脚本 | 低 | 部署后建议硬刷新 |
| 外置 JS ~977 行仍偏大 | 低 | 可选后续 Phase 6b：拆模块或接入 `crm-api.js` |
| pytest 不覆盖完整 UI 流 | 低 | 自动化依赖 API 冒烟；完整 UI 流已由用户手动网页验证 PASS |

## 提交文件

```text
plan/27-phase6-delivery-turnover-frontend-split.md
templates/pages/delivery_turnover.html
static/js/pages/delivery-turnover.js
reports/architecture/phase-06-delivery-turnover-frontend-report.md
```
