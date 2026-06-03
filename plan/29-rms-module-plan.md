# 29 RMS Module Plan

> **用途**：RMS 模块分期**执行计划**（任务、边界、验收）。  
> **不是**架构说明文档；架构见 [`docs/rms-architecture.md`](../docs/rms-architecture.md)、[`docs/architecture.md`](../docs/architecture.md) § RMS。

---

## 全局约束

每个 Phase 只完成该 Phase 目标，不顺手实现后续 Phase。

- 不改变现有 CRM/Delivery API URL 与返回字段（除非本 plan 明确新增 RMS API）。
- 业务 `/api/rms/*` 必须使用 `require_permission`。
- 数据范围相关逻辑保留 `apply_client_scope` / `filter_query_by_client_scope` 等既有模式。
- 不删除历史 migration；不做 `DROP TABLE` / `DROP COLUMN`。
- 全量 pytest 参考基线：**121 passed**（Phase 结束须保持全绿；勿用「59+ passed」表述）。

标准验证（各 Phase 结束，除非本 Phase 写明例外）：

```bash
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

---

## Phase -1（当前唯一执行项：文档与计划）

### 目标

修文档围栏、落本计划、跑基线验证。**不做 RMS 代码实现。**

### 允许修改

- [`docs/architecture.md`](../docs/architecture.md)
- [`docs/rms-architecture.md`](../docs/rms-architecture.md)
- 本文件 [`plan/29-rms-module-plan.md`](29-rms-module-plan.md)

### 禁止

- 不改 [`auth/permissions.py`](../auth/permissions.py)
- 不改 [`auth/permission_catalog.py`](../auth/permission_catalog.py)
- 不改 [`auth/data_scope_catalog.py`](../auth/data_scope_catalog.py)
- 不建 `rms_*` 表、不跑 migration
- 不建 `routes/rms_*`、`services/rms_*`、`schemas/rms_*`
- 不改 `templates/`、`static/`、`main.py`

### 文档要点（已在 Phase -1 写入）

- `docs/architecture.md`：RMS 小节为正常 Markdown（非嵌套代码块）。
- `docs/rms-architecture.md`：`rms_jobs.owner_user_id`；试单与 `clients.delivery_owner_user_id` / `delivery_dept_id`；`rms.contacts.view` → `rms.candidate`。

### 验收

- `check_architecture.py` 通过。
- `pytest` 全绿（参考 **121 passed**）。
- `git diff` 仅含上述三个文件。

---

## Phase 0：权限壳 + 导航壳（无业务表）

### 目标

登记 `rms.*` 权限与 data scope 资源映射；权限中心/导航可见；空页面与空路由占位。**不实现 RMS 业务逻辑。**

### 实现范围

- 新增 `rms.*` 权限码至 [`auth/permissions.py`](../auth/permissions.py) `ALL_PERMISSION_CODES`。
- 同步 [`auth/permission_catalog.py`](../auth/permission_catalog.py)（矩阵/展示）。
- 同步 [`auth/data_scope_catalog.py`](../auth/data_scope_catalog.py)：
  - `RESOURCE_CODES` 增加 RMS resource
  - `PERMISSION_TO_RESOURCE` 完整映射（见下节）
  - `RESOURCE_SCOPE_ANCHOR` 登记锚点（候选人/岗位/推荐等）
- 导航壳：RMS 入口（按权限显示）。
- 空页面：`templates/pages/rms_*.html`（占位）。
- 空路由：`routes/rms_*.py` 注册到 app（health/占位，无业务写库）。
- `GET /rms` 必须使用 `require_permission("rms.jobs.read")`（不只靠导航隐藏）。
- `NAV_SECTION_PERMISSIONS["rms"] = "rms.jobs.read"`（固定，非可选）。
- `build_data_scope_matrix` 的 `resource_labels` 补全 4 个 RMS resource 中文名。
- 修改 `seed_role_data_scopes`：对内置角色**仅补齐缺失**的 `(resource, action)` 行，**不覆盖**已有行（解决已有 DB 上 DELIVERY 有权限无 scope 的问题）。

### Phase 0 默认角色策略（`ROLE_DEFAULT_PERMISSIONS`）

| 角色 | RMS 默认 |
|------|----------|
| `SUPER_ADMIN` | 全部 `rms.*` |
| `DELIVERY` | 仅 `rms.jobs.read`、`rms.applications.read`（见下，不默认其余 read） |
| `SALES` | **不给** RMS |
| `VIEWER` | 无 RMS |
| 招聘负责人 / Lead | **不**新建角色码；**不**进入 `ROLE_DEFAULT_PERMISSIONS` |

`DELIVERY` 默认**不**授予：`rms.candidates.read`、`rms.resumes.read`、`rms.analytics.read`（须权限中心按需授予）。`rms.resumes.read` 可能暴露解析文本中的联系方式，不应默认放开。

招聘 Lead / 负责人所需写权限（`rms.jobs.write`、`rms.applications.write`、`rms.candidates.write`、`rms.candidates.read`、`rms.resumes.read`、`rms.resumes.download`、`rms.contacts.view`、`rms.matching.run`、`rms.analytics.read` 等）由**权限中心手动授予**。

Phase 0 **禁止**：新建 `RECRUITING_LEAD` 等默认角色；给 `DELIVERY` 默认全量 RMS write，或授予上表未列明的 read。

### 验收

- `test_every_business_permission_maps_to_resource` 通过。
- 无 RMS 业务表 migration。

---

## 权限 → Resource 映射（Phase 0 必须完整登记）

所有新增**业务**权限必须进入 `PERMISSION_TO_RESOURCE`，否则 [`tests/test_data_scope_catalog.py`](../tests/test_data_scope_catalog.py) 失败。

| 功能权限 | Resource 码 | 说明 |
|----------|-------------|------|
| `rms.jobs.read` / `rms.jobs.write` | `rms.job` | 岗位；经 `client_id` 继承 delivery client scope |
| `rms.applications.read` / `rms.applications.write` | `rms.application` | 推荐记录 |
| `rms.candidates.read` / `rms.candidates.write` | `rms.candidate` | 候选人主档 |
| `rms.resumes.read` | `rms.resume` | 简历元数据/解析 |
| `rms.resumes.download` | `rms.resume` | 原文件下载（独立动作） |
| `rms.contacts.view` | `rms.candidate` | **仅**服务层脱敏开关；不单独行级过滤 |
| `rms.matching.run` | `rms.job` | AI 匹配锚定岗位及 `client_id` 的 delivery client scope（定死，不映射 `rms.application`） |
| `rms.analytics.read` | `rms.job` | 统计读 scope 锚定岗位/客户 |

Resource 码使用**单数**（对标 `crm.client`）；功能权限段使用**复数**（`rms.candidates.read`）。

### `rms.contacts.view` 特别说明

- **必须**映射 `rms.candidate`，**不得**排除在 `PERMISSION_TO_RESOURCE` 外。
- 运行时：与 `rms.candidates.read` 共用候选人列表行级可见性；无权限时对 phone/email/wechat 脱敏。

---

## Phase 1：RMS 表 migration

### 目标

新增 `rms_*` 表结构；仍可无完整业务 UI。

### 表（至少）

- `rms_jobs`（**必须**含 `client_id`、`owner_user_id`）
- `rms_applications`（见下「字段约定」）
- `rms_candidates`
- `rms_resumes`
- `rms_application_status_history`
- `rms_interviews`
- `rms_offers`
- `rms_match_results`（见下「字段约定」）

### Phase 1 字段约定（已确认）

**`rms_applications` — 明确增加冗余 `client_id`**

- 除 `job_id`、`candidate_id`、`resume_id`、状态与时间戳等流程字段外，**必须**增加 `client_id`。
- 写入/更新时与 `rms_jobs.client_id` 同步（禁止仅依赖运行时 JOIN）。
- Phase 1 后可将 `rms.application` 的 `RESOURCE_SCOPE_ANCHOR` 设为 `inherit_via_client=True`、`client_fk=client_id`。

**`rms_match_results` — 以 `application_id` 为主关联，冗余 job/candidate，第一阶段不加 `client_id`**

- **主关联**：`application_id`（推荐：匹配结果落在「某次推荐」上下文上，Phase 4 写入时必填或强约束）。
- **可保留冗余**：`job_id`、`candidate_id`（及 `resume_id` 若需要），写入时与 application 或对应 job/candidate 一致，便于列表/统计查询，避免每次都 JOIN `rms_applications`。
- **`client_id`**：第一阶段**不强制**加列；客户范围可通过 `rms_applications.client_id`（已冗余）或 `JOIN rms_jobs` 解析；若 Phase 4/6 统计看板有性能需求再单独加列。

### 验收

- Migration 可重复应用；pytest 仍全绿。

---

## Phase 2：岗位 / 候选人 / 推荐 MVP

### 目标

岗位、候选人、推荐记录 CRUD 与列表；推荐状态流转。

### 数据范围（service 层显式实现）

**可见岗位** = 在 delivery client scope 内的客户的岗位 **OR** `rms_jobs.owner_user_id = 当前用户`。

- **不**假设 `entity_owner_col` 对 `rms_jobs` 自动生效；须在 service/query 中写清 OR 条件。

### 试单规则（首个岗位）

创建客户下**首个** `rms_jobs` 时：

- 若 `clients.delivery_owner_user_id` 为空 → 必选交付/招聘对接人。
- 写入 `clients.delivery_owner_user_id`，尽量同步 `clients.delivery_dept_id`。
- `rms_jobs.owner_user_id` 仍必填（岗位负责人）。

**禁止**使用虚构字段 `clients.delivery_owner`（字符串遗留字段仅作展示/迁移，非 clients 主锚点）。

### 验收

- 交付 scope 用户可见已锚定客户岗位；岗位 owner 可见本人负责岗位。
- 试单流程有测试或手工用例记录。

---

## Phase 3：简历 + 脱敏 + 下载

### 目标

简历上传、解析结果存储；联系方式脱敏；独立下载接口。

### 要求

- 下载：`GET /api/rms/resumes/{id}/download`（或等价路径），**必须** `require_permission("rms.resumes.download")`。
- `rms.resumes.read` ≠ 可下载原文件。
- 无 `rms.contacts.view` 时列表/详情脱敏 phone、email、wechat。

### 验收

- 无 download 权限时下载 403。
- 无 contacts.view 时字段脱敏。

---

## Phase 4：AI 匹配

### 目标

AI 匹配结果写入 `rms_match_results`；列表展示评分与解释。写入时以 **`application_id`** 为主键关联，并同步填充冗余 `job_id` / `candidate_id`（不要求本阶段在 match 表加 `client_id`）。

### 边界

- AI **只**辅助排序/解释/推荐。
- **禁止**自动淘汰、自动拒绝、自动改状态、自动写花名册。

### 权限

- 运行匹配需 `rms.matching.run`。

---

## Phase 5：入职转交付

### 目标

Application 入职后，**人工确认**写入 `roster_entries`。

### 要求

- 展示将写入字段；用户确认后提交。
- **不**自动覆盖已有 `roster_entries`。
- 疑似重复须提示；记审计日志。

---

## Phase 6：面试 / Offer / 基础统计

### 目标

- `rms_interviews`、`rms_offers` 维护。
- 基础统计看板（`rms.analytics.read`）。

---

## 与现有 plan 的关系

- 架构护栏与拆分顺序仍遵循 [`20-low-risk-architecture-master.md`](20-low-risk-architecture-master.md)。
- RBAC/数据范围总原则见 [`00-rbac-master-plan.md`](00-rbac-master-plan.md)、[`plan_permission_datascope.md`](plan_permission_datascope.md)。
- RMS 不替代 [`delivery_pipeline_entries`](../docs/rms-architecture.md) 作为长期主表。

---

## Phase -1 完成后检查清单

- [ ] `docs/architecture.md` RMS 为正常章节
- [ ] `docs/rms-architecture.md` 含 `owner_user_id`、试单锚点、`rms.contacts.view` 映射说明；末尾 bash 块闭合
- [ ] 本 plan 已创建
- [ ] `check_architecture.py` 通过
- [ ] `pytest` 全绿（参考 121 passed）
