# Phase 6A-3：RMS Dashboard 图表体系重构

**Status:** 进行中  
**Supersedes:** [plan/39-rms-dashboard-stats-polish-plan.md](39-rms-dashboard-stats-polish-plan.md)（6A 表格增强已并入 6A-2b/6A-3 口径，以本计划为准）

## 目标

重构 `/rms/dashboard` 为五 Tab 图表体系，补齐 lifecycle_funnel 与积压图口径，幂等清理 obsolete seed 面板，保留 legacy block 渲染兼容。

## Tab IA

| Tab | 默认 blocks |
|-----|-------------|
| 总览 | filter, kpi_resume_count, kpi_hired_count, kpi_resume_to_hire_rate, chart_pipeline, chart_pending_backlog |
| 生命周期转化 | filter, lifecycle_funnel, chart_lifecycle_pass_rate, table_lifecycle_detail |
| 客户岗位分析 | filter, chart_job_pending_backlog, chart_client_hired_ranking, table_client_job_stage |
| 招聘人效 | filter, chart_recruiter, chart_recruiter_recommend_vs_hired, table_recruiter |
| 花名册核对 | 保持现状 |

## 硬约束 HC-1 ~ HC-5

- **HC-1:** `RMS_BLOCK_KEYS` = legacy + new；`RMS_BLOCK_KEYS_ADDABLE` 仅 new；metadata 只暴露 ADDABLE
- **HC-2:** cleanup 仅系统 seed Tab + Test tab；不删用户自定义 Tab 内旧 block
- **HC-3:** `pending_roster_conversion_count` 在 API rows/total，不在 table HTML
- **HC-4:** `lifecycle_funnel.rows` 含 entered/passed/failed/pending/processed/pass_rate/pass_rate_value/funnel_count
- **HC-5:** `_sync_rms_tab_ia_v2` 幂等；sort_order 0–4；永久 stop `_sync_rms_test_tab`

## 口径分层

- **快照：** HC（open only）、pipeline、表格待客筛/约面中/待面试/待offer/在途
- **周期历史：** 简历数、内筛/客筛/已面试/面试通过等；lifecycle_funnel
- **API only（非表格列）：** pending_roster_conversion_count（积压图）

岗位积压公式：

```
pending_internal_screen + pending_client_screen + scheduling_interview_count
+ pending_interview + pending_second_interview + pending_final_interview
+ pending_offer_count + onboarding_count + pending_roster_conversion_count
```

**已面试 / 面试通过（table_client_job_stage）：** 周期内曾到达对应节点，且当前（或 `date_to` 快照）仍在一面结果之后；误操作改回「待一面」等前置状态时不计入。

## 验收

```bash
node --check static/js/pages/rms-dashboard.js
./venv/bin/python -m pytest tests/test_rms_dashboard.py -q
./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```
