# RMS Phase 2 执行计划 / Diff 预案（修订版）

**状态：** 待确认后实施（本文件为预案，确认前不写代码）。

**前置：** Phase 0（`adea2d0`）、Phase 1（`4037a9c`）。表见 [`migrations/005_rms_tables.sql`](../migrations/005_rms_tables.sql)；ORM 见 [`models/rms.py`](../models/rms.py)。

**目标：** 岗位、候选人、推荐记录 **API CRUD + 列表**；推荐 **状态流转** + `rms_application_status_history`；**不**做简历上传、AI、入职转花名册、面试/Offer 子表 CRUD、完整前端（API-first 验收）。

**验收基线：** `check_architecture.py` 通过；`pytest tests/ -q` 全绿（预计 +18～28 条 Phase 2 用例）。

---

## 实施必遵（禁止回退旧写法）

| 主题 | 必须 | 禁止 |
|------|------|------|
| 试单 `create_job` | 首个 job 且客户无 `delivery_owner_user_id` → **CRM 客户可见** + `rms.jobs.write` + 必填 `delivery_owner_user_id` → **先**写 client 锚点 **再**插 job | 试单分支调用 `assert_client_in_scope(..., rms.job, write)`；开头统一 `assert_client_in_scope + owner_user_id` |
| 候选人可见 | `created_by_user_id = 我` **OR** `candidate_id` 在**我可见的 applications** 中 | `{ candidate_id \| job 在 scoped_jobs }`；从 job 表直接推 candidate |
| 创建 application | `assert_job_writable` + **`assert_candidate_usable`** + `sync_client_id` | 只校验 job / client_id；猜 `candidate_id` 挂隐藏候选人 |
| 状态 | 仅用 §7 `ALLOWED_TRANSITIONS` map | 线性链 `recommended → screening → …` |
| PATCH application | 请求体出现 `status`/`client_id`/`current_stage`/`last_activity_at` → **400**；仅允许 `job_id?`/`candidate_id?`/`resume_id?` | PATCH 改 `current_stage`/`last_activity_at`；「非状态字段」模糊表述 |
| 流程字段写入 | `current_stage`、`last_activity_at` **仅**在 `POST .../status` 流转成功后由服务端写入 | PATCH/POST 手改流程字段 |
| 创建岗位权限 | 路由 `require_permission("rms.jobs.write")`；仅 CRM 可见 **无** `rms.jobs.write` → **403** | 试单 CRM 路径绕过 jobs.write |

---

## 修订记录

### 实施前补充（4 点 — 全部采纳）

| # | 补充 | 落点 |
|---|------|------|
| A | PATCH application 含 `status`/`client_id`/`current_stage`/`last_activity_at` → **400** | §5、§8 |
| B | `current_stage`、`last_activity_at` 仅 `POST .../status` 成功后写入 | §7.2 |
| C | 测试：PATCH 拒上述四字段；仅 CRM 可见、无 `rms.jobs.write` 创建岗位 **403** | §9 |
| D | 仍禁止简历/AI/面试/Offer CRUD/花名册/完整前端 | §1.2 |

### 评审 5 点（已全部纳入上文）

| # | 问题 | 结论 |
|---|------|------|
| 1 | 试单时 `rms.job` write scope 可能拦掉首个岗位 | **采纳** — 双路径 gate（§6） |
| 2 | Application 未校验候选人可见性 | **采纳** — `assert_candidate_usable_for_application`（§4.4、§5） |
| 3 | 「job 在 scoped_jobs 内」推导候选人 | **采纳** — 删除；仅 creator ∪ 可见 application 的 candidate_id（§4.3） |
| 4 | 状态流转像单链，中间不能 reject | **采纳** — 显式 `ALLOWED_TRANSITIONS` map（§7） |
| 5 | PATCH 可改 status/client_id | **采纳** — PATCH 禁止二者；状态仅专用 POST（§5、§8） |

---

## 1. 范围边界

### 1.1 本阶段必须做

| 能力 | 说明 |
|------|------|
| Jobs API | 列表/详情/创建/更新；读 scope = delivery client **OR** `owner_user_id`；**写**见 §6 双路径 |
| Candidates API | 列表/详情/创建/更新；可见性 §4.3；脱敏 §4.3 |
| Applications API | CRUD（无 DELETE）；`client_id` 仅由 job 同步；状态仅 `/status` |
| 状态流转 | `POST .../status` + history |
| 试单 | 首个 job 补 `delivery_owner`；CRM 客户可见 + `rms.jobs.write` |
| 测试 | 含试单、PATCH 四字段 400、无 jobs.write 创建岗位 403、candidate 可见性、状态 map |

### 1.2 禁止项（Phase 2 不得实现）

- 不新增 migration（除非 005 硬伤）。
- 不改 `auth/permissions.py` / `auth/data_scope_catalog.py`。
- **简历**上传/解析、`rms_resumes` 业务 API。
- **AI** 匹配、`rms_match_results` 写入。
- **面试 / Offer** 子表（`rms_interviews`、`rms_offers`）CRUD。
- **入职转花名册**（写入 `roster_entries` 或等价交付动作）。
- **完整前端**（`templates/` / `static/js/pages/` 招聘业务页）；本阶段 **API-first**。
- 不用 `clients.delivery_owner` 字符串作 scope 锚点。
- PATCH application 请求体 **不得**出现 `status`、`client_id`、`current_stage`、`last_activity_at`（一律 **400**）。

---

## 2. 拟新增/修改文件

| 文件 | 操作 |
|------|------|
| `services/rms_scope.py` | 新增 — scope、试单 gate、candidate 可见 ID、job 可写校验 |
| `services/rms_jobs.py` | 新增 |
| `services/rms_candidates.py` | 新增 |
| `services/rms_applications.py` | 新增 |
| `routes/rms_jobs.py` | 新增 |
| `routes/rms_candidates.py` | 新增 |
| `routes/rms_applications.py` | 新增 |
| `schemas/rms.py` | 新增 — body、**ALLOWED_TRANSITIONS** |
| `main.py` | 注册三路由 + 注入 `RMS_MODELS`、`Client` |
| `tests/test_rms_phase2_mvp.py` | 新增 |
| `tests/test_rbac_api_modules.py` | 扩展 RMS 403 |

---

## 3. 架构（不变）

路由 → service → `auth/data_scope.py`；`main.py` 在 `register_rms_models` 之后 `register_rms_*_routes`。

---

## 4. Data scope 与可见性

### 4.1 岗位读 — `scoped_jobs_query`

```python
allowed = ds.scoped_client_ids(db, ctx, RESOURCE_RMS_JOB, action, Client)
# allowed is None → 不滤 client
# else → OR(client_id.in_(allowed), owner_user_id == ctx.user_id)
```

单条读：scoped query + `id`，无行 → **404**。

### 4.2 岗位写（常规，非试单）— `assert_job_writable`

- 目标 `client_id` 已通过 **常规路径**（§6.1）：`ds.assert_client_in_scope(..., RESOURCE_RMS_JOB, "write")`。
- 更新 job：须落在 `scoped_jobs_query(..., action="write")` 或等价单条 gate。

### 4.3 候选人可见 ID（修订 — 唯一合法定义）

`rms_jobs` **没有** `candidate_id`，**不能**从 job 行直接推出候选人。

```text
candidate_visible(id) :=
  (created_by_user_id = 当前用户)
  OR (id 出现在当前用户可见的 rms_applications.candidate_id 中)
```

实现：`visible_candidate_ids` = 上式 SQL/子查询结果。

- **可见 applications**：`scoped_applications_query` = `filter_query_by_client_scope(..., RESOURCE_RMS_APPLICATION, action, RmsApplication.client_id, Client)`。
- **若要通过岗位范围放宽**：仅允许  
  `candidate_id IN (SELECT candidate_id FROM rms_applications WHERE job_id IN (SELECT id FROM scoped_jobs_query(...)))`  
  即「**可见 job 下的 applications**」，不是 job 本身；与上式并集等价时可只实现 application 子查询，**不维护**「job 直接可见 candidate」分支。
- `SUPER_ADMIN` / 全量 scope：不限制 ID 集合（仍做脱敏）。

列表：`RmsCandidate.id.in_(visible_candidate_ids)`；空集 → `id == -1`。

创建候选人：`created_by_user_id = ctx.user_id`。

### 4.4 候选人用于推荐时的校验（必做 — 防 application API 绕过 candidate 权限）

`assert_candidate_usable_for_application(db, ctx, candidate_id)`：

- `candidate_id ∈ visible_candidate_ids`（§4.3）；否则 **404**（防枚举）。
- **禁止**仅凭 `rms.applications.write` 绑定对当前用户不可见的候选人（不可猜 ID）。

**创建 application（POST）必做顺序：**

1. `assert_job_writable` — job 在当前用户 **rms.job write** 或试单合法路径内可写。
2. `assert_candidate_usable_for_application` — **必做**，不可省略。
3. `sync_client_id_from_job` — 服务端写入 `client_id`，忽略 body。

**更新 application（PATCH）**：若 body 含 `candidate_id`，必须再次 `assert_candidate_usable_for_application`。

### 4.5 推荐 application

- 列表/读：`filter_query_by_client_scope(..., RmsApplication.client_id, Client)`。
- 写：§4.4 三步 + application 行落在 write scope（创建后 `client_id` 已在 scope 内）。

### 4.6 权限码（路由）

| 资源 | read | write | 状态 |
|------|------|-------|------|
| jobs | `rms.jobs.read` | `rms.jobs.write` | — |
| candidates | `rms.candidates.read` | `rms.candidates.write` | — |
| applications | `rms.applications.read` | `rms.applications.write` | 同 write，仅 `POST .../status` |

---

## 5. Application 请求体约束（修订）

### 5.1 PATCH `/api/rms/applications/{id}`

**允许字段（仅此）：** `job_id?`、`candidate_id?`、`resume_id?`（`ApplicationUpdate` schema 白名单）。

**若请求体（含 JSON extra）出现以下任一键 → HTTP 400**（禁止 ignore/静默丢弃）：

- `status`
- `client_id`
- `current_stage`
- `last_activity_at`

实现建议：Pydantic `model_config = extra="forbid"` 或路由层显式检测后 400。

### 5.2 POST `/api/rms/applications`

- 仅 `job_id`、`candidate_id`、`resume_id?`；**不得**含 `status`、`client_id`、`current_stage`、`last_activity_at`（出现 → **400**）。
- `client_id` 仅服务端从 job 同步；初始 `status` 服务端默认（如 `recommended`）。

### 5.3 其他写操作

| 事件 | 行为 |
|------|------|
| PATCH 改 `job_id` | 重算 `client_id`；须 job 可写 + application 可写 + candidate 可见（若改 candidate） |
| PATCH job.`client_id` | 批量更新该 job 下 applications 的 `client_id` |

**状态与流程字段：** 仅 `POST /api/rms/applications/{id}/status`（§7.2）。

---

## 6. 试单：首个岗位 + 写权限双路径（修订）

**`create_job` 入口禁止写成：**「先 `assert_client_in_scope(..., RESOURCE_RMS_JOB, write)` + 校验 `owner_user_id`」适用于所有请求——试单客户会被 delivery scope 挡死。

在 `create_job` 内先分支：

```text
existing_count = COUNT(rms_jobs WHERE client_id = ?)
if client.delivery_owner_user_id IS NULL AND existing_count == 0:
    → §6.2 试单路径（CRM 可见，不用 rms.job write scope）
else:
    → §6.1 常规路径（rms.job write scope）
```

校验 `owner_user_id` 存在（`sys_user`）两条路径 **都要**做；**scope gate 分路径**。

### 6.1 常规路径（已有 delivery 锚点，或该客户已有 job）

- 条件：`client.delivery_owner_user_id IS NOT NULL` **或** `existing_count > 0`。
- Gate：`ds.assert_client_in_scope(db, ctx, client_id, Client, RESOURCE_RMS_JOB, "write")`。
- 然后插入 `rms_jobs`（`owner_user_id` 必填）。

### 6.2 试单路径（首个岗位且客户无 delivery_owner）

- 条件：`client.delivery_owner_user_id IS NULL` **且** `existing_count == 0`。
- Gate（**不用** `rms.job` write 的 delivery scope，避免销售客户进不去）：
  1. 路由已要求 `rms.jobs.write`。
  2. 用户对该 `client_id` 具备 CRM 客户可见性：**`crm.clients.read` 或 `crm.clients.write` 任一** 的 data scope 可见（实现：`ds.assert_client_in_scope(..., RESOURCE_CRM_CLIENT, "read")` **或** `assert_client_in_scope(..., "write")`；或 `client_id in visible_client_ids(db, ctx, Client, action="read") ∪ write`，超级管理员跳过）。
  3. Body **必须**含 `delivery_owner_user_id`。
- 顺序：**先** `UPDATE clients SET delivery_owner_user_id, delivery_dept_id`（dept 来自 `get_user_dept_ids` 主部门），**再** `INSERT rms_jobs`。
- 缺 `delivery_owner_user_id` → **400**。

### 6.3 禁止

- 试单只写 `rms_jobs.owner_user_id` 不写 `clients.delivery_owner_user_id`。
- 试单路径对仅有 `rms.jobs.write`、无 CRM 客户可见的用户放行（防越权摸客户）。

---

## 7. 状态流转（修订 — 仅允许下列 map，禁止线性链文案）

**禁止**在文档/注释中使用：`recommended → screening → interview → offer → hired | rejected | withdrawn` 作为唯一路径。

### 7.1 `schemas/rms.py`

```python
APPLICATION_TERMINAL = frozenset({"hired", "rejected", "withdrawn"})

ALLOWED_TRANSITIONS = {
    "recommended": {"screening", "rejected", "withdrawn"},
    "screening": {"interview", "rejected", "withdrawn"},
    "interview": {"offer", "rejected", "withdrawn"},
    "offer": {"hired", "rejected", "withdrawn"},
    "hired": set(),
    "rejected": set(),
    "withdrawn": set(),
}
```

- 非法 `from_status → to_status` → **400**。
- 终态 **不允许** 任何流出（含不可再 `withdrawn`）。

### 7.2 API — `POST /api/rms/applications/{id}/status`

Body：仅 `to_status`、`reason?`、`note?`。

**流转校验通过后**，服务端在同一事务内更新：

| 字段 | 写入规则 |
|------|----------|
| `status` | `= to_status` |
| `current_stage` | 建议 `= to_status`（或固定映射表；**不得**由 PATCH 写入） |
| `last_activity_at` | 服务端当前时间（ISO/text，与项目时间列风格一致） |
| `rms_application_status_history` | `from_status`、`to_status`、`changed_by`、`changed_at` 等 |

- 非法跳转 → **400**，**不**更新 `current_stage` / `last_activity_at`。
- 可选 `GET .../status-history`（`rms.applications.read`）。
- **`PATCH /api/rms/applications/{id}`** 不得写入 `status`、`current_stage`、`last_activity_at`（§5.1）。

---

## 8. API 端点清单

### Jobs

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/rms/jobs` | `client_id?`, `status?` |
| GET | `/api/rms/jobs/{id}` | |
| POST | `/api/rms/jobs` | 试单字段 `delivery_owner_user_id?`（§6） |
| PATCH | `/api/rms/jobs/{id}` | |

### Candidates

| Method | Path |
|--------|------|
| GET/POST | `/api/rms/candidates` |
| GET/PATCH | `/api/rms/candidates/{id}` |

### Applications

**硬约束（routes + schemas + service）：**

| 规则 | 说明 |
|------|------|
| PATCH 出现 `status` / `client_id` / `current_stage` / `last_activity_at` | 一律 **400** |
| PATCH 允许 | 仅 `job_id?`, `candidate_id?`, `resume_id?` |
| POST 创建 | 仅 `job_id`, `candidate_id`, `resume_id?`；同上四字段出现 → **400** |
| `current_stage` / `last_activity_at` | **仅** `POST .../status` 成功后服务端写入（§7.2） |
| POST 创建岗位 | 路由 **`require_permission("rms.jobs.write")`**；无该权限即使 CRM 客户可见 → **403**（先于试单逻辑） |

| Method | Path | Body |
|--------|------|------|
| GET | `/api/rms/applications` | — |
| POST | `/api/rms/applications` | `job_id`, `candidate_id`, `resume_id?` |
| PATCH | `/api/rms/applications/{id}` | `job_id?`, `candidate_id?`, `resume_id?` **only** |
| POST | `/api/rms/applications/{id}/status` | `to_status`, `reason?`, `note?` |

重复推荐 → **409**。无 DELETE。

---

## 9. 测试用例（增补评审项）

| 用例 | 断言 |
|------|------|
| `test_first_job_via_trial_path_crm_visible` | 无 delivery_owner、无历史 job；用户有 `rms.jobs.write` + `crm.clients.read` 可见客户 → POST 带 `delivery_owner_user_id` **201** |
| `test_first_job_blocked_without_crm_client_visibility` | 有 `rms.jobs.write` 但 CRM 客户不可见 → **404/403** |
| `test_first_job_blocked_without_delivery_owner_body` | 试单路径缺 `delivery_owner_user_id` → **400** |
| `test_first_job_regular_path_after_delivery_owner_set` | 已有 delivery_owner → 走 `rms.job` write scope |
| `test_application_rejects_invisible_candidate` | candidate 不在 visible 集 → POST **404** |
| `test_patch_application_rejects_forbidden_fields` | PATCH 分别带 `status`、`client_id`、`current_stage`、`last_activity_at`（可参数化 4 次）→ 均 **400** |
| `test_patch_application_allows_only_job_candidate_resume` | PATCH 仅 `resume_id` 等允许字段 → **200**（在 fixture 合法前提下） |
| `test_create_job_forbidden_without_rms_jobs_write` | 用户仅有 `crm.clients.read` 可见客户、**无** `rms.jobs.write` → `POST /api/rms/jobs` **403**（权限层，不进试单） |
| `test_status_transition_writes_current_stage_and_activity` | `POST .../status` 成功后 `current_stage`/`last_activity_at`/`status` 已更新 |
| `test_status_reject_from_screening` | `screening` → `rejected` **200** |
| `test_status_terminal_no_transition` | `rejected` → `screening` **400** |
| （保留原表）scope、sync、owner 可见、脱敏、409、rbac 扩展 | |

---

## 10. 验收命令

```bash
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/test_rms_phase2_mvp.py -q
./venv/bin/python -m pytest tests/ -q
```

---

## 11. 实施顺序

1. `schemas/rms.py`（**ALLOWED_TRANSITIONS**；`ApplicationUpdate` 仅三字段 + `extra=forbid`；拒 PATCH 四键）
2. `services/rms_scope.py`（试单 gate、visible_candidate_ids、job/candidate asserts）
3. `rms_jobs` → `rms_applications`（含 candidate 校验、PATCH 约束）→ `rms_candidates`
4. routes + `main.py` + tests

**停止条件：** 需简历/AI/花名册/改 auth 权限表才能绿测 → 停止报告。

---

## 12. plan/29 对齐

- 交付 scope + 岗位 owner OR 可见
- 试单补 `delivery_owner_user_id`（含 CRM 可见入口）
- `client_id` service 同步与测试
- 状态流转含中间 reject/withdraw
