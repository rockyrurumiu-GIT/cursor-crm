# Phase 6A：招聘 Dashboard 客户岗位阶段统计增强

**状态：** 已 superseded by [plan/41-rms-dashboard-chart-system-plan.md](41-rms-dashboard-chart-system-plan.md)

## 目标

增强现有 `/rms/dashboard` 的 `table_client_job_stage` 区块；复用 `GET /api/rms/dashboard` 与 `client_job_stage_summary`；权限 `rms.analytics.read`。不新建看板入口，不改通用 CRM dashboard。

## 执行前提

- `git status --short` 为空后再开工。
- 核心改动文件（仅此路径）：
  - [`services/rms_dashboard.py`](../services/rms_dashboard.py)
  - [`templates/pages/rms_dashboard.html`](../templates/pages/rms_dashboard.html)
  - [`static/js/pages/rms-dashboard.js`](../static/js/pages/rms-dashboard.js)
  - [`tests/test_rms_dashboard.py`](../tests/test_rms_dashboard.py)
  - [`tests/test_rms_frontend_shell.py`](../tests/test_rms_frontend_shell.py)
  - 本计划文档

## 实现顺序（必须按此顺序）

**不要先改前端**——否则表格会引用尚未存在的 API 字段。严格顺序：

1. **本计划文档** — 确认 [`plan/39-rms-dashboard-stats-polish-plan.md`](39-rms-dashboard-stats-polish-plan.md) 与硬约束一致（开工前核对一次即可）。
2. **后端** — [`services/rms_dashboard.py`](../services/rms_dashboard.py)：补 `client_id` / `client_name`、花名册两计数字段（`status_at == "hired"` + 转入字段双条件）；`total` 聚合同步扩展。
3. **表格 HTML** — [`templates/pages/rms_dashboard.html`](../templates/pages/rms_dashboard.html)：严格 **21 列**全链路（`<thead>`、普通 row、total row、`colspan="21"`）；total 行前 5 列对齐。
4. **Dashboard JS** — [`static/js/pages/rms-dashboard.js`](../static/js/pages/rms-dashboard.js)：`city` 筛选、`buildQuery` / filter 状态、标题文案（`RMS_BLOCK_LAYOUT_PRESETS` 等）。
5. **可选 RMS 标题** — 仅在需要时改 [`services/dashboards.py`](../services/dashboards.py)：`scope="rms"` 且 `block="table_client_job_stage"` 的 seed/sync 标题；[`schemas/dashboards.py`](../schemas/dashboards.py) RMS block 展示文案。
6. **测试与验收** — [`tests/test_rms_dashboard.py`](../tests/test_rms_dashboard.py)、[`tests/test_rms_frontend_shell.py`](../tests/test_rms_frontend_shell.py)，再跑下方验收命令。

## 硬约束（实现时必须遵守）

### 1. 表格固定 21 列

当前表为 **18 列**。新增 **客户**、**待转花名册**、**已转花名册** 后为 **21 列**。

[`templates/pages/rms_dashboard.html`](../templates/pages/rms_dashboard.html) 中 `table_client_job_stage` 必须同步改：

| 位置 | 要求 |
|------|------|
| `<thead>` | 恰好 21 个 `<th>` |
| 普通 row | 恰好 21 个 `<td>` |
| total row | 恰好 21 个 `<td>` |
| 空态 | `colspan="21"` |

**列顺序（前 5 列固定）：**

1. 时间
2. 客户（新增）
3. 岗位
4. 需求数量
5. 地点
6. 推送简历量 … 面试通过（现有指标，保留 rate tooltip）
7. 待offer / 弃offer / 在途 / 在途流失 / 已入职（表头对齐用户口径）
8. 待转花名册（新增）
9. 已转花名册（新增）

**total 行前 5 列对齐：**

| 列 | 显示 |
|----|------|
| 时间 | `clientJobStagePeriodLabel` |
| 客户 | `合计` |
| 岗位 | `—` |
| 需求数量 | `—` |
| 地点 | `—` |
| 第 6 列起 | 各指标合计（含花名册两列） |

> 注意：当前 total 行把「合计」写在岗位列，实施时必须移到**客户**列。

### 2. 花名册计数口径（写死）

在 [`services/rms_dashboard.py`](../services/rms_dashboard.py) `_metrics_for_apps` 中，`snapshot_as_of = _snapshot_as_of(filters)`（有 `date_to` 用截止日快照，否则当前 status）：

```text
pending_roster_conversion_count:
  status_at(app, histories, snapshot_as_of) == "hired"
  AND converted_to_roster_entry_id 为空

converted_to_roster_count:
  converted_to_roster_entry_id 非空
  AND status_at(app, histories, snapshot_as_of) == "hired"
```

两条都必须带 **hired 快照** 条件，避免把异常脏数据（已转花名册但非 hired）算进去。

花名册两列为**快照态**；`pushed_resume_count` / `hired_count` 等为**时段事件态**——测试与文档中勿混读。

### 3. `services/dashboards.py` 仅允许 RMS scope 小改

允许改 seed / sync **标题**，但必须同时满足：

- 只动 `scope="rms"` **且** `config.block == "table_client_job_stage"` 的 widget `title`
- **不改** CRM scope 任何逻辑
- **不改** 通用 dashboard config 结构
- **不改** widget CRUD 行为

具体：将 seed 标题与 `_sync_rms_client_job_stage_title` 从「历史数据」改回「客户岗位阶段统计」，范围限定如上。

[`schemas/dashboards.py`](../schemas/dashboards.py) 仅改 RMS block 展示文案：`"table_client_job_stage": "表格 · 客户岗位阶段统计"`（不动通用 widget config schema）。

### 4. 明确不做

- 新建「统计看板」导航或页面
- 新 API / 新 migration（`converted_to_roster_*` 字段已存在）
- 改 `/dashboards` 或通用 CRM dashboard
- AI 匹配、面试独立模块、拖拽布局改造
- 改已有 block 的 `config.block` key（仍为 `table_client_job_stage`）

---

## 第 1 步：后端 `client_job_stage_summary`

**文件：** [`services/rms_dashboard.py`](../services/rms_dashboard.py)

1. `_SUMMARY_METRIC_KEYS` 追加 `converted_to_roster_count`、`pending_roster_conversion_count`（不重命名已有键）。
2. `_metrics_for_apps` 按上文**硬约束 §2** 实现花名册计数。
3. `_client_job_stage_summary` 每 row 补：
   - `client_id`、`client_name`（批量查 `Client.name`）
   - 已有：`job_id`, `job_title`, `headcount`, `location` + 阶段指标 + rate
4. `total` 只对数值指标键求和；`total[key] == sum(row[key])` 需在测试中验证。

[`routes/rms_dashboard.py`](../routes/rms_dashboard.py) 无需改动（`city` 等参数已 wired）。

---

## 第 2 步：前端表格与筛选

**文件：** [`templates/pages/rms_dashboard.html`](../templates/pages/rms_dashboard.html)、[`static/js/pages/rms-dashboard.js`](../static/js/pages/rms-dashboard.js)

### 表格（硬约束 §1）

- 21 列 thead / tbody / total / 空态 `colspan="21"`
- total 行前 5 列按 §1 对齐

### 筛选（复用现有 `filter` block）

在 `cloneFilters` / `buildQuery` / `applyFilterValues` / `activeFilterSummary` 增加 `city`：

- UI：城市下拉（可选）
- 选项：`jobOptions` 去重 `location`，不新 API
- 已有：客户单选、`job_ids` 多选、`date_from`/`date_to`、交付、招聘

### 展示命名

- `RMS_BLOCK_LAYOUT_PRESETS.table_client_job_stage.title` → 「客户岗位阶段统计」
- block key 不变：`table_client_job_stage`

---

## 第 3 步：测试

### [`tests/test_rms_dashboard.py`](../tests/test_rms_dashboard.py)

| 用例 | 断言 |
|------|------|
| row 字段 | `client_id`, `client_name`, `job_title`, `location` + 全部阶段数字段 |
| total 合计 | 每个 `_SUMMARY_METRIC_KEYS`（含花名册键）`total[key] == sum(rows)` |
| 花名册 | hired 未转 → `pending_roster_conversion_count==1`；convert 后 → `converted_to_roster_count==1` 且 pending==0 |
| city 过滤 | 两岗位不同 location，`city=` 后 rows 仅匹配 |
| 403 | 无 `rms.analytics.read` 时 `/api/rms/dashboard` 与 `/rms/dashboard` 均 403 |

### [`tests/test_rms_frontend_shell.py`](../tests/test_rms_frontend_shell.py)

- 更新 `test_rms_dashboard_twenty_shell` required 字符串：`客户`、`待转花名册`、`已转花名册`、`待offer`、`已入职` 等
- 移除旧表头依赖（`offer在谈`、`入职数`）若 HTML 已改
- 保留 `node --check static/js/pages/rms-dashboard.js`

---

## 验收命令（按顺序）

```bash
node --check static/js/pages/rms-dashboard.js
./venv/bin/python -m pytest tests/test_rms_dashboard.py -q
./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```
