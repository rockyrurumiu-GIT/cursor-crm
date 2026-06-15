# Phase 6A-4：RMS Dashboard 客户岗位阶段统计 — 面试阶段拆分

**状态：** 已实施  
**依赖：** [plan/41-rms-dashboard-chart-system-plan.md](41-rms-dashboard-chart-system-plan.md)（表格 20 列基线、口径分层以 41 为准）

## 目标

将 `table_client_job_stage` 中泛化的 **已面试 / 面试通过** 拆分为 **一面数 / 一面通过(%) / 二面数 / 二面通过(%)**；**待面试** 保持现有快照列不变。API 保留 `interviewed` / `interview_passed` 兼容字段；同步更新客户岗位分析相关图表与测试。

## Cursor 执行口径

按本计划执行：

- 后端新增一面/二面 **6 个字段**；**一面数**复用 `_app_counts_as_interviewed` 口径，**二面数**新增同口径 helper（见下方常量与函数）
- 表格替换 **已面试 / 面试通过** → **一面数 / 一面通过 / 二面数 / 二面通过**
- 旧 API 字段 `interviewed` / `interview_passed` **保留**
- 终面 **不展示**（`pending_final_interview` 仍 API-only）
- 空态 **`colspan="22"`**（当前 20 列，替换 2 列为 4 列后共 22 列，必须全链路同步）
- 测试覆盖：一面 fail、一面 pass、二面 fail、二面 pass、已入职、correction 回退

## 硬约束

### HC-1：表格固定 22 列

当前表为 **20 列**。移除「已面试」「面试通过」2 列，新增「一面数」「一面通过」「二面数」「二面通过」4 列 → **22 列**。

[`templates/pages/rms_dashboard.html`](../templates/pages/rms_dashboard.html) 全链路同步：

| 位置 | 要求 |
|------|------|
| `<thead>` | 恰好 22 个 `<th>` |
| 普通 row / total row | 恰好 22 个 `<td>` |
| 空态 | **`colspan="22"`**（当前为 `colspan="20"`，必须同步改，不可遗漏） |

**列数验算：** 当前 20 列 − 2（已面试、面试通过）+ 4（一面数、一面通过、二面数、二面通过）= **22 列**。

**列顺序（前 5 列不变）：**

1. 时间 · 2. 客户 · 3. 岗位 · 4. HC · 5. 地点  
6. 简历数 · 7. 内筛通过 · 8. 重复 · 9. 待客筛  
10. 客筛通过 · 11. 约面中 · 12. 放弃面试 · 13. **待面试**（快照，保留）  
14. **一面数** · 15. **一面通过**（含 rate tooltip）  
16. **二面数** · 17. **二面通过**（含 rate tooltip）  
18. 待offer · 19. 弃offer · 20. 在途 · 21. 在途流失 · 22. 已入职  

> `pending_second_interview` / `pending_final_interview` / `pending_roster_conversion_count` 仍为 **API only**（积压图），本阶段不入表。

### HC-2：口径分层（与 plan/41 一致）

- **快照：** 待客筛、约面中、待面试、待offer、在途
- **周期+快照守卫：** 一面数/一面通过、二面数/二面通过、简历数、内筛/客筛通过、弃offer、在途流失、已入职
- **API only（兼容/积压）：** `interviewed`、`interview_passed`、`pending_second_interview`、`pending_final_interview`、`pending_roster_conversion_count`

**守卫原则：** 周期内曾到达对应节点，且 `status_at(app, histories, date_to 或当前)` 仍停留在该节点结果之后；误操作 correction 改回前置状态时不计入（与现有 `interviewed` 一致）。

### HC-3：API 兼容

- `_SUMMARY_METRIC_KEYS` **追加** 6 个新键，**不删除** `interviewed` / `interview_passed`
- `interviewed` / `interview_passed` 继续计算，但 **不出现在表格**
- `interview_passed` 语义维持「至少一面通过且仍在该节点之后」（聚合兼容字段）

### HC-4：通过率分母链

| rate 字段 | 分子 | 分母 |
|-----------|------|------|
| `first_interview_passed_rate` | `first_interview_passed_count` | `first_interview_count` |
| `second_interview_passed_rate` | `second_interview_passed_count` | `second_interview_count` |
| `offer_dropped_count_rate` | `offer_dropped_count` | **`second_interview_passed_count`**（替换原 `interview_passed`） |

`total` 行 rate 由 `_attach_job_stage_rates(total)` 对合计分子/分母重算，禁止对各行 rate 取平均。

### HC-5：不改 lifecycle 图

`lifecycle_funnel` / `chart_lifecycle_pass_rate` 继续走 `_historical_overview`；本计划 **不修改** 其数据结构或终面拆分。

## 指标定义（status 集合）

```text
first_interview_count（一面数）:
  周期: history.to_status ∈ {first_interview_passed, first_interview_failed}
  守卫: status_at ∈ statuses_from(first_interview_passed) ∪ {first_interview_failed}
  实现: 复用 _app_counts_as_interviewed 逻辑

first_interview_passed_count（一面通过数）:
  复用 _app_counts_as_stage_passed(stage_key="first_interview", pass_status="first_interview_passed")
  守卫: status_at ∈ statuses_from(first_interview_passed)

second_interview_count（二面数）:
  周期: history.to_status ∈ {second_interview_passed, second_interview_failed, second_interview_abandoned}
  守卫: status_at ∈ statuses_from(second_interview_passed)
         ∪ {second_interview_failed, second_interview_abandoned}
  实现: 新增 _app_counts_as_second_interviewed，镜像 _app_counts_as_interviewed

second_interview_passed_count（二面通过数）:
  复用 _app_counts_as_stage_passed(stage_key="second_interview", pass_status="second_interview_passed")
  守卫: status_at ∈ statuses_from(second_interview_passed)
```

> 终面无独立 `final_interview_passed` 状态（`schemas/rms.py` `APPLICATION_PROGRESS_ORDER`）；终面拆分 **明确不在本阶段**，后续与 Offer Tab / Offer 成功率口径一并设计。

## 后端实现细节

文件：[`services/rms_dashboard.py`](../services/rms_dashboard.py)

**新增二面结果常量**（与 `_FIRST_INTERVIEW_OUTCOME_STATUSES` / `_INTERVIEWED_CURRENT_STATUSES` 对称，避免 helper 内散写集合）：

```python
_SECOND_INTERVIEW_OUTCOME_STATUSES = frozenset({
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
})
_SECOND_INTERVIEWED_CURRENT_STATUSES = _statuses_from("second_interview_passed") | frozenset({
    "second_interview_failed",
    "second_interview_abandoned",
})
```

**新增 helper**（镜像 `_app_counts_as_interviewed`）：

```python
def _app_counts_as_second_interviewed(
    app: Any,
    histories: List[Any],
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_in_period(
        histories, _SECOND_INTERVIEW_OUTCOME_STATUSES, date_from, date_to
    ):
        return False
    return _status_at(app, histories, snapshot_as_of) in _SECOND_INTERVIEWED_CURRENT_STATUSES
```

**`_metrics_for_apps` 内计数映射：**

| 新字段 | 实现 |
|--------|------|
| `first_interview_count` | `_app_counts_as_interviewed(...)` |
| `first_interview_passed_count` | `_app_counts_as_stage_passed(..., "first_interview", "first_interview_passed", ...)` |
| `second_interview_count` | `_app_counts_as_second_interviewed(...)` |
| `second_interview_passed_count` | `_app_counts_as_stage_passed(..., "second_interview", "second_interview_passed", ...)` |

## 实现顺序

1. **本计划文档** — 开工前核对 HC 与列数
2. **后端** — [`services/rms_dashboard.py`](../services/rms_dashboard.py)
3. **测试（后端）** — [`tests/test_rms_dashboard.py`](../tests/test_rms_dashboard.py)
4. **表格 HTML** — [`templates/pages/rms_dashboard.html`](../templates/pages/rms_dashboard.html)
5. **Dashboard JS** — [`static/js/pages/rms-dashboard.js`](../static/js/pages/rms-dashboard.js)（`chart_client_job_stage_*` dataset 改用新字段）
6. **Shell 测试** — [`tests/test_rms_frontend_shell.py`](../tests/test_rms_frontend_shell.py)

**不要先改前端。**

## 文件清单

| 文件 | 改动 |
|------|------|
| `services/rms_dashboard.py` | 6 新字段 + helpers；扩展 `_SUMMARY_METRIC_KEYS`、`_JOB_STAGE_RATE_SPECS`；保留 `interviewed`/`interview_passed` |
| `templates/pages/rms_dashboard.html` | 22 列表头/行/total/空态；替换面试列 |
| `static/js/pages/rms-dashboard.js` | 图表 dataset 改用新字段；chart hint 文案 |
| `tests/test_rms_dashboard.py` | 新指标断言、rollback、total 合计、rate 分母链 |
| `tests/test_rms_frontend_shell.py` | 表头字符串：`一面数`、`二面数` 等 |

**不改：** `routes/rms_dashboard.py`、`schemas/rms.py`（无新 status）、migration、`lifecycle_funnel` 后端逻辑。

## 测试用例

| 用例 | 断言 |
|------|------|
| 一面 fail | 至 `first_interview_failed`：`first_interview_count==1`，`first_interview_passed_count==0`，rate `0%`，`second_*==0` |
| 一面通过待二面 | 至 `first_interview_passed`：`first_interview_passed_count==1`，rate `100%`，`second_interview_count==0` |
| 二面 fail | 至 `second_interview_failed`：一面全 1/100%，`second_interview_count==1`，`second_interview_passed_count==0` |
| 二面通过 | 至 `second_interview_passed`：二面 count/pass 均 1，rate `100%` |
| 已入职全链路 | 一面/二面 count+pass 均 1；`hired_count==1` |
| 一面 rollback | correction 回 `pending_first_interview`：一面/二面新字段均为 0；`pending_interview==1`（扩展 `test_dashboard_interview_metrics_exclude_rollback_to_pending_first`） |
| 二面 rollback | correction 回 `first_interview_passed`：二面字段归零；一面字段仍保留 |
| 周期过滤 | 沿用 `test_dashboard_period_event_pass_without_push_in_range` 模式 |
| total 合计 | 每个 `_SUMMARY_METRIC_KEYS`（含 6 新键 + 兼容键）`total[key] == sum(rows)` |
| offer rate 分母 | `offer_dropped_count_rate` 分母为 `second_interview_passed_count` |
| API 兼容 | 响应仍含 `interviewed`、`interview_passed` |

## 验收命令

```bash
node --check static/js/pages/rms-dashboard.js
./venv/bin/python -m pytest tests/test_rms_dashboard.py -q
./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

## 明确不做（本阶段）

- 终面数 / 终面通过 拆分
- 表格新增 待二面 / 待终面 列
- 新 API 端点或 DB migration
- 修改 `lifecycle_funnel` / `chart_lifecycle_pass_rate` 数据源
- 删除 `interviewed` / `interview_passed` API 字段
- 修改 RMS 推荐进展流转 / Offer Tab / AI 匹配
