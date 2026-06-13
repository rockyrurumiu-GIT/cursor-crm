# 38 RMS 前端按域拆分

**状态：** R1 已完成 / R2 计划已定 / R3–R4 roadmap

**目标：** 降低 [`static/js/pages/rms.js`](../static/js/pages/rms.js)（~2800 行）与 [`templates/pages/rms_index.html`](../templates/pages/rms_index.html)（~1790 行）维护成本；遵循 [`20-low-risk-architecture-master.md`](20-low-risk-architecture-master.md) 与 delivery detail 拆分经验（[`26-phase5-delivery-detail-tab-split.md`](26-phase5-delivery-detail-tab-split.md)）。

**原则：** 只搬移代码，不改 API / 权限 / 业务规则；每轮只拆一个模块；每步全量测试 + 手动点 `/rms`。

---

## 硬约束（HC-1 – HC-7）

1. **HC-1** — `showValidationPrompt` 可进 `rms-core.js`；`crmConfirmActionDialog` 与业务 overlay（如 `showCandidateDuplicateDialog`）留 shell。
2. **HC-2** — R1 不移动 `EDUCATION_OPTIONS` 等候选人/报告常量；`PRIORITY_OPTIONS` / `STATUS_OPTIONS` 归 jobs 模块。
3. **HC-3** — `jobModalMode` / `editingJobId` 与 `submitJobModal` / `resetJobModalState` 同模块搬迁。
4. **HC-4** — `clientOptions` / `userOptions` 由 jobs 创建但必须 return 并 spread 到 setup。
5. **HC-5** — jobs **不返回** `modalTitle` / `modalShowSave`；返回 `jobModalTitle` / `jobModalShowSave` / `jobModalReadonly`；shell 组合最终模板绑定名。
6. **HC-6** — `canWriteJobs` 等 permission computed R1 留 shell。
7. **HC-7** — 不移动不存在的符号（无 `openJobView`）。

---

## 分阶段 roadmap

| Phase | 范围 | DOM | 风险 |
|-------|------|-----|------|
| **R1** | `rms-core.js` + `rms-jobs.js`；script 标签 | 不改 | 低 |
| **R2** | `rms-candidates.js`；扩充 `rms-candidate-report.js` | 不改 | 中 |
| **R3** | `rms-applications.js`、`rms-pipeline.js`、roster convert；瘦身 shell | 不改 | 中高 |
| **R4** | HTML/CSS partials；可选 `rms-dashboard.js` | 改 | **高 — JS 边界稳定后再做** |

---

## Script 加载顺序

**R1 终态：**

```html
rms-application-labels.js → rms-core.js → rms-candidate-report.js → rms-jobs.js → rms.js
```

**R2-A 后（+ candidates）：**

```html
rms-application-labels.js → rms-core.js → rms-candidate-report.js → rms-jobs.js → rms-candidates.js → rms.js
```

---

## R1 模块边界

### rms-core.js — 纯工具

`rmsRequest`、`messageForStatus`、`workflowMessageForStatus`、`fuzzyMatch`、薪资格式化、`showValidationPrompt`、`showRmsBootError` 等。

### rms-jobs.js — `createJobsState(deps)`

岗位列表/筛选、岗位 modal CRUD、`clientOptions`/`userOptions`、`openJobs`、`priorityLabel`/`statusLabel`、`scheduleJobsTableColumnFit` 等。

### rms.js shell

`activeTab`、`viewMode`、permission computed、报告/候选人/推荐/pipeline、`modalTitle`/`modalShowSave`/`modalCloseLabel` 组合、`submitModal` 候选人分支。

---

## 验收（每 Phase）

```bash
node --check static/js/pages/rms-core.js
node --check static/js/pages/rms-jobs.js
node --check static/js/pages/rms.js
./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

手动：`/rms` 五 tab；R1 重点 — 岗位筛选/新建/修改、「推荐候选人」进报告页、候选人 modal 标题/保存不受影响。

---

## R2 — candidates + report（计划已定，未执行）

**口径：** 只做 JS 拆分；不改 DOM、API、权限、业务行为。`rms_index.html` 只允许改 script 标签。

**执行门禁：** R2-A 全量测试 + 手动验收通过 → 才做 R2-B。禁止 A/B 同批。

### R2 硬约束（HC-R2-1 – HC-R2-11）

| # | 约束 |
|---|------|
| HC-R2-1 | HTML 只改 script 标签，不改 DOM / `data-rms-*` |
| HC-R2-2 | `showCandidateDuplicateDialog` 等业务弹窗留 shell |
| HC-R2-3 | `EDUCATION_OPTIONS` 等常量留 shell（候选人 + 报告共用） |
| HC-R2-4 | 候选人 modal mode/id 与 submit/reset 同模块迁 |
| HC-R2-5 | candidates 返回 `candidateModalTitle` 等，shell 组合 `modalTitle` |
| HC-R2-6 | permission computed 留 shell |
| HC-R2-7 | `viewMode` ref 留 shell |
| HC-R2-8 | `labelCandidate` / `candidateNameById` 经 spread 暴露给模板与 appDisplay |
| HC-R2-9 | applications / pipeline / delivery / roster **不拆** |
| HC-R2-10 | 保留 `RmsCandidateReport` 纯 API；新增 `CrmRmsReport.createReportState` |
| **HC-R2-11** | **spread 只解决模板绑定**；shell setup 内部仍引用候选人/report 符号时，R2-A **必须**建兼容别名（或 `candidates.xxx`），不能悬空 |

### R2-A 兼容别名（推荐）

`createCandidatesState` 之后：

```javascript
const loadCandidates = candidates.loadCandidates;
const scheduleCandidatesTableColumnFit = candidates.scheduleCandidatesTableColumnFit;
const labelCandidate = candidates.labelCandidate;
const candidateNameById = candidates.candidateNameById;
const displayCandidateContact = candidates.displayCandidateContact;
const resumeViewUrl = candidates.resumeViewUrl;
const resumeCanView = candidates.resumeCanView;
const candidateParseSummaryFields = candidates.candidateParseSummaryFields;
const candidateParseSummaryEmpty = candidates.candidateParseSummaryEmpty;
const candidateParseSummaryValue = candidates.candidateParseSummaryValue;
```

R3/R4 再清理为显式 `candidates.xxx`。

### 子阶段

- **R2-A：** `rms-candidates.js`（`createCandidatesState`）+ shell 别名 + script + 测试
- **R2-B：** `CrmRmsReport.createReportState` + report 别名 + 全量 5 项手动验收

### R2 验收命令

```bash
node --check static/js/pages/rms-candidates.js   # R2-A 起
node --check static/js/pages/rms-candidate-report.js
node --check static/js/pages/rms.js
./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

详细步骤见 Cursor plan：`rms_frontend_r2_split_f756bda4.plan.md`

---

## R3–R4（未执行）

- `rms-applications.js`：推荐列表、详情、转 roster
- `rms-pipeline.js`：pipeline 筛选、进展确认、`crmConfirmActionDialog` 流程
- 瘦身 `rms.js` 为装配层

### R4 — HTML/CSS

- CSS 外置；tab partials；**共享 modal 模板拆分最后做**
