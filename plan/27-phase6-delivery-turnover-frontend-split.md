# 27 Phase 6：delivery_turnover 前端 JS 外置

## Summary

本阶段只做 `delivery_turnover.html` 的 inline Vue 脚本外置，模式与 Phase 4 settlement 一致：**原样迁移、零重构**。

原因：

- `delivery_turnover.html` 当前约 2089 行，是仓库中最大的超标单页模板之一。
- Phase 5 已将 turnover 相关 API 收敛到 `routes/delivery_roster.py`；本阶段不碰后端。
- `delivery_detail.html` 已在 Phase 5E 收尾；turnover 是 Phase 5 之后自然的前端风险面。

## Preconditions

```text
Phase 0–5 PASS
./venv/bin/python -m pytest tests/ -q 全绿
static/js/pages/delivery-settlement.js 外置已验证（Phase 4 先例）
```

## Scope

### In scope

- `templates/pages/delivery_turnover.html` — 移除 inline `<script>`，改为引用外部 JS
- `static/js/pages/delivery-turnover.js` — 原样承载 L1117–2087 逻辑
- `reports/architecture/phase-06-delivery-turnover-frontend-report.md` — 本阶段报告

### Out of scope

- `routes/delivery_roster.py`、数据库、权限模型
- `delivery_detail.html`、其他 delivery 页面
- 引入 npm / Vite / Webpack
- 迁移到 `crm-api.js` / `crm-toast.js`（可选后续 Phase 6b）
- 修改 Vue 模板 DOM 结构

## API checklist（页面 fetch 清单）

执行前用 `rg` 核对；迁移后行为不变：

| Method | Path | 用途 |
|--------|------|------|
| GET | `/api/roster/turnover` | 离职池列表 |
| GET | `/api/roster/turnover/dashboard` | 分析看板 |
| POST | `/api/roster` | 新增离职档案行 |
| PUT | `/api/roster/{id}` | 修改 |
| DELETE | `/api/roster/{id}` | 删除 |
| POST | `/api/roster/turnover/import` | 导入 CSV |
| GET | `/api/roster/turnover/export` | 导出 CSV |
| GET | `/api/roster/logs` | 操作日志 |
| POST | `/api/roster/turnover/restore/latest` | 回滚最近备份 |

后端注册：`routes/delivery_roster.py`。冒烟：`tests/test_smoke_delivery_roster.py`（turnover list + dashboard）。

## Implementation

### 1. 外置 JS（零重构）

1. 新建 `static/js/pages/delivery-turnover.js`
2. 复制原 inline 脚本（去掉 `<script>` 标签）
3. 文件头注释：依赖 Vue 3 CDN、`#delivery-turnover-app`
4. 模板 `page_scripts` 仅保留：

```html
<script src="/static/js/pages/delivery-turnover.js"></script>
```

**保持不动：** `head_extra` 中 Vue CDN 与 `<style>`；`content` 内 `{% raw %}` DOM。

### 2. 全局依赖（来自 base.html，本阶段不新增 script）

- `window.crmAuthHeader`
- `window.crmDownloadBlob`
- `window.crmScheduleTableColumnResize`（可选）

## Verification

```bash
node --check static/js/pages/delivery-turnover.js
./venv/bin/python scripts/check_architecture.py
./venv/bin/python scripts/check_file_sizes.py
./venv/bin/python -m pytest tests/ -q
```

浏览器 `/delivery/turnover`：列表、筛选、CRUD、导入导出、日志/回滚、分析看板、Console 无 error。

## Success criteria

- `delivery_turnover.html` 行数明显下降（目标 ~1116）
- `delivery-turnover.js` 通过 `node --check`
- pytest 全绿
- `check_file_sizes` 对 turnover HTML 的 >1200 warning 消失
- 页面功能与 API 行为不变

## Commit

```text
plan/27-phase6-delivery-turnover-frontend-split.md
templates/pages/delivery_turnover.html
static/js/pages/delivery-turnover.js
reports/architecture/phase-06-delivery-turnover-frontend-report.md
```

Message: `frontend: extract delivery turnover page script`
