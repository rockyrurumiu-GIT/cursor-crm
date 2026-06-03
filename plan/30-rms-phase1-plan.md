# RMS Phase 1 执行计划 / Diff 预案

**状态：** Phase 1 已按本预案实施（migration + ORM + schema 测试）。

**文档性质：** 本文件为规范与验收清单；**确认前不得实施**。Phase 1 **实施时仅允许**：`migrations/005_rms_tables.sql`、`models/rms.py`、`main.py` 注册、schema 测试、文档小改；**禁止** CRUD、业务 service、页面、上传、AI、入职转花名册。

**前置：** Phase 0 已合并。`auth/data_scope_catalog.py` 中 `rms.job` / `rms.application` 已为 `inherit_via_client=True`、`client_fk=client_id`。

**目标：** 只建 RMS **数据库地基**（SQL migration + ORM 映射 + schema 测试），不做任何业务功能。

### 实施硬约束（Codex 修订，必须遵守）

1. **`register_rms_models(Base)` 必须在 `run_schema_migrations(engine)` 之后调用**（见 [`main.py`](../main.py)：`create_all` → `run_schema_migrations` → `register_rms_models`）。
2. **[`migrations/005_rms_tables.sql`](../migrations/005_rms_tables.sql) 是 RMS 表唯一 DDL 来源**；ORM **不得**对 RMS 表调用 `create_all`。
3. **`register_rms_models` 必须幂等**：按 `id(Base.metadata)` 分桶缓存；同一 Base 重复调用不重复建表；**不同 Base** 各自注册（见 `test_register_rms_models_separate_base_isolated`）。
4. **`rms_candidates.created_by_user_id`**：`INTEGER NULL REFERENCES sys_user(id)` + 索引 `idx_rms_candidates_created_by_user_id`。
5. **Phase 1 测试不覆盖** `application.client_id` 与 `job.client_id` 的 DB 级一致性（无 trigger/CHECK）；该逻辑属 Phase 2 service。

**验收基线：** `check_architecture.py` 通过；`pytest tests/ -q` 全绿（当前约 **136** passed，Phase 1 预计 +8～12 条 schema 用例）。

---

## 1. 范围边界

### 1.1 本阶段必须做

| 项 | 说明 |
|----|------|
| `migrations/005_rms_tables.sql` | 8 张 `rms_*` 表 + 索引 + 外键 + 必要唯一约束 |
| ORM 映射 | 与 migration 字段一致，供 Phase 2 注入 |
| Schema 测试 | migration 入账、表存在、关键列、幂等、约束抽查 |
| （可选）`reports/architecture/phase-29-rms-phase1-report.md` | 实施后验收记录 |

### 1.2 本阶段禁止做

- `routes/rms_*.py` 业务 API、`services/rms_*.py` CRUD/scope 过滤
- 页面 / `static/js/pages/`、简历上传与解析、AI 匹配写入、入职转花名册
- `rms_applications.client_id` 的 **运行时** 同步逻辑（属 Phase 2 service；Phase 1 只建列 + 文档/测试契约）
- 修改 Phase 0 权限默认值（除非测试发现 catalog 与表名不一致）

---

## 2. 拟变更文件清单（diff 预案）

| 文件 | 操作 | 说明 |
|------|------|------|
| `migrations/005_rms_tables.sql` | **新增** | 唯一 DDL 来源 |
| `models/rms.py` | **新增** | 推荐：ORM 定义 + `register_rms_models(Base)` |
| `main.py` | **小改** | `run_schema_migrations` **之后** `register_rms_models(Base)`；**不**新增路由、**不**对 RMS `create_all` |
| `tests/test_rms_phase1_schema.py` | **新增** | migration + PRAGMA/schema 断言 |
| `plan/30-rms-phase1-plan.md` | 本文件 | 确认后实施时可勾选验收项 |

**不改动（除非实施时发现硬依赖）：** `auth/*`、`templates/*`、`routes/rms_shell.py`（Phase 0 壳保留）。

**不纳入提交：** 无关图片、`_orb_preview.html`、`templates/base.html` 实验等。

---

## 3. ORM 模型放在哪里

### 3.1 现状

- 全仓库 ORM 均在 `main.py` 的 `Base = declarative_base()` 下（`Client`、`RosterEntry`、`DeliveryPipelineEntry` 等）。
- `docs/architecture.md` 规划了 `models/`，但 **尚无** `models/base.py`；`models/` **禁止** `import main`（避免循环）。

### 3.2 Phase 1 推荐（与架构方向一致）

**新增 `models/rms.py`**，提供：

```python
def register_rms_models(Base) -> dict[str, type]:
    """Attach RMS ORM classes to the app Base; called once from main.py."""
    ...
    return {
        "RmsJob": RmsJob,
        "RmsCandidate": RmsCandidate,
        ...
    }
```

- `main.py` 在 **`run_schema_migrations(engine)` 之后** 调用 `register_rms_models(Base)`，赋值 `RMS_MODELS`（不再次 `create_all`）。
- **禁止** 在 `models/rms.py` 内 `from main import Base`。
- **`register_rms_models` 幂等**：按 `id(Base.metadata)` 分桶缓存；若 `rms_jobs` 已在该 Base 的 metadata 则返回已有类。

### 3.3 备选（更小 diff，不推荐长期）

8 个 class 直接追加在 `main.py` `DeliveryHandbookFile` 之后。优点：零新 import 图；缺点：加剧 `main.py` 膨胀，与 `models/` 规划背离。

**预案默认采用 3.2**；若你要求极简 diff，实施时可改为 3.3 并在本计划备注。

### 3.4 ORM 与 migration 对齐约定

- SQL migration 为 **权威**；ORM `__tablename__` / 列名与 `005` 一致。
- 时间列：migration 用 `TEXT NOT NULL DEFAULT (datetime('now'))`（对齐 `sys_*` migration）；ORM 可用 `Column(String)` 或 `DateTime`（与 `DeliveryPipelineEntry.created_at` 一致即可）。
- 外键：`ForeignKey("clients.id")`、`ForeignKey("sys_user.id")` 等与现有 delivery 表相同风格；**不设** ORM `relationship()`（Phase 2 再按需）。

---

## 4. `migrations/005_rms_tables.sql` 设计

### 4.1 幂等性（两层）

| 层级 | 机制 |
|------|------|
| **文件级** | [`auth/migrate.py`](../auth/migrate.py)：`schema_migrations` 已有 `005_rms_tables.sql` 则整文件跳过 |
| **语句级** | 全部 `CREATE TABLE IF NOT EXISTS`、`CREATE INDEX IF NOT EXISTS`；**禁止** `DROP` / 破坏性 `ALTER` |

**注意：** 文件级幂等意味着「已入账后 SQL 修改不会自动重跑」。列变更应走 `006_*` 新 migration，不在 005 上改已发布库。

### 4.2 依赖顺序（建表顺序）

```
rms_candidates
rms_jobs          → clients, sys_user
rms_resumes       → rms_candidates, sys_user
rms_applications  → rms_jobs, rms_candidates, clients, rms_resumes (nullable), sys_user
rms_application_status_history → rms_applications, sys_user
rms_interviews    → rms_applications
rms_offers        → rms_applications
rms_match_results → rms_applications, rms_jobs, rms_candidates, rms_resumes (nullable), sys_user
```

### 4.3 表字段、外键、唯一约束、索引

类型默认：`INTEGER PRIMARY KEY AUTOINCREMENT`、`TEXT`；`score` 用 `REAL`。

#### `rms_jobs`

| 列 | 约束 |
|----|------|
| `id` | PK |
| `client_id` | NOT NULL, FK → `clients(id)` |
| `title`, `department`, `location` | TEXT NOT NULL DEFAULT '' |
| `headcount` | INTEGER NOT NULL DEFAULT 1 |
| `job_description`, `requirements` | TEXT NOT NULL DEFAULT '' |
| `status` | TEXT NOT NULL DEFAULT 'open' |
| `owner_user_id` | NOT NULL, FK → `sys_user(id)` |
| `created_at`, `updated_at` | TEXT NOT NULL |

**索引：** `idx_rms_jobs_client_id (client_id)`；`idx_rms_jobs_owner_user_id (owner_user_id)`；`idx_rms_jobs_status (status)`。

#### `rms_candidates`

| 列 | 约束 |
|----|------|
| `id` | PK |
| `name` | TEXT NOT NULL DEFAULT '' |
| `phone`, `email`, `wechat` | TEXT NOT NULL DEFAULT '' |
| `current_company`, `current_title`, `city`, `source` | TEXT NOT NULL DEFAULT '' |
| `tags` | TEXT NOT NULL DEFAULT '[]'（JSON 数组字符串，与 handbook `tags_json` 一致） |
| `created_by_user_id` | INTEGER NULL, FK → `sys_user(id)` |
| `created_at`, `updated_at` | TEXT NOT NULL |

**索引：** `idx_rms_candidates_created_by_user_id (created_by_user_id)`；`idx_rms_candidates_name (name)`（可选列表）；**不**对 phone 做 UNIQUE。

#### `rms_resumes`

| 列 | 约束 |
|----|------|
| `id` | PK |
| `candidate_id` | NOT NULL, FK → `rms_candidates(id)` ON DELETE CASCADE |
| `file_name`, `file_path`, `file_type` | TEXT NOT NULL DEFAULT '' |
| `parsed_text` | TEXT NOT NULL DEFAULT '' |
| `parsed_json` | TEXT NOT NULL DEFAULT '{}' |
| `uploaded_by` | FK → `sys_user(id)`（可 NULL，Phase 1 允许空） |
| `created_at` | TEXT NOT NULL |

**索引：** `idx_rms_resumes_candidate_id (candidate_id)`。

#### `rms_applications`（含冗余 `client_id`）

| 列 | 约束 |
|----|------|
| `id` | PK |
| `job_id` | NOT NULL, FK → `rms_jobs(id)` |
| `candidate_id` | NOT NULL, FK → `rms_candidates(id)` |
| `client_id` | NOT NULL, FK → `clients(id)` |
| `resume_id` | NULL, FK → `rms_resumes(id)` |
| `status` | TEXT NOT NULL DEFAULT 'recommended' |
| `recommended_by` | FK → `sys_user(id)` NULL |
| `recommended_at`, `current_stage`, `last_activity_at` | TEXT NOT NULL DEFAULT '' |
| `created_at`, `updated_at` | TEXT NOT NULL |

**唯一约束：** `UNIQUE (job_id, candidate_id)` — 同一岗位同一候选人仅一条推荐主记录（与 [`plan/29-rms-module-plan.md`](29-rms-module-plan.md) 主表语义一致；若未来要「重新推荐」走状态流转而非第二行）。

**索引：** `idx_rms_applications_client_id (client_id)`；`idx_rms_applications_job_id`；`idx_rms_applications_candidate_id`；`idx_rms_applications_status (status)`。

#### `rms_application_status_history`

| 列 | 约束 |
|----|------|
| `id` | PK |
| `application_id` | NOT NULL, FK → `rms_applications(id)` ON DELETE CASCADE |
| `from_status`, `to_status` | TEXT NOT NULL DEFAULT '' |
| `reason`, `note` | TEXT NOT NULL DEFAULT '' |
| `changed_by` | FK → `sys_user(id)` NULL |
| `changed_at` | TEXT NOT NULL |

**索引：** `idx_rms_app_status_hist_app_id (application_id)`；`idx_rms_app_status_hist_changed_at (changed_at)`。

#### `rms_interviews`

| 列 | 约束 |
|----|------|
| `id` | PK |
| `application_id` | NOT NULL, FK → `rms_applications(id)` ON DELETE CASCADE |
| `interview_time`, `interview_round`, `interviewer`, `result`, `feedback` | TEXT NOT NULL DEFAULT '' |
| `created_at`, `updated_at` | TEXT NOT NULL |

**索引：** `idx_rms_interviews_application_id (application_id)`。

#### `rms_offers`

| 列 | 约束 |
|----|------|
| `id` | PK |
| `application_id` | NOT NULL, FK → `rms_applications(id)` ON DELETE CASCADE |
| `offer_status`, `salary`, `expected_onboard_date`, `actual_onboard_date`, `note` | TEXT NOT NULL DEFAULT '' |
| `created_at`, `updated_at` | TEXT NOT NULL |

**索引：** `idx_rms_offers_application_id (application_id)`。

#### `rms_match_results`（无 `client_id`）

| 列 | 约束 |
|----|------|
| `id` | PK |
| `application_id` | NOT NULL, FK → `rms_applications(id)` ON DELETE CASCADE |
| `job_id` | NOT NULL, FK → `rms_jobs(id)` |
| `candidate_id` | NOT NULL, FK → `rms_candidates(id)` |
| `resume_id` | NULL, FK → `rms_resumes(id)` |
| `score` | REAL NULL |
| `summary`, `strengths`, `risks` | TEXT NOT NULL DEFAULT '' |
| `model_name` | TEXT NOT NULL DEFAULT '' |
| `created_by` | FK → `sys_user(id)` NULL |
| `created_at` | TEXT NOT NULL |

**不**加 `client_id`（[`plan/29`](29-rms-module-plan.md) / [`docs/rms-architecture.md`](../docs/rms-architecture.md) 已确认）。

**唯一约束：** **不**对 `(application_id)` 做 UNIQUE（允许多次 AI 运行多条结果）。

**索引：** `idx_rms_match_results_application_id`；`idx_rms_match_results_job_id`。

### 4.4 SQLite 外键说明

- Migration 中声明 `FOREIGN KEY` 与现有 migration 一致。
- 测试库若需强制 FK，可在 schema 测试里 `PRAGMA foreign_keys=ON` 后做 **可选** 负面插入用例；不强制改 `auth/migrate.py` 全局 PRAGMA（与现网行为一致）。

---

## 5. `rms_applications.client_id` 同步规则

Phase 1 **只建列 + 契约**；同步在 **Phase 2 `services/rms_applications.py`** 实现。规则如下（写入实施说明 / 单测占位注释）：

### 5.1 写入规则（Phase 2 必实现）

| 事件 | 规则 |
|------|------|
| **创建** application | `client_id := (SELECT client_id FROM rms_jobs WHERE id = :job_id)`；`job_id` 不存在 → 400 |
| **更新** `job_id` | 重新查询 job 的 `client_id` 并写回 `rms_applications.client_id` |
| **更新** `rms_jobs.client_id`** | 批量 `UPDATE rms_applications SET client_id = :new WHERE job_id = :job_id`（Phase 2 岗位编辑若允许改客户） |
| **禁止** | 仅改 `client_id` 而不校验与 job 一致（API 层拒绝或覆盖为 job 值） |

### 5.2 Phase 1 是否用 DB 触发器

| 方案 | 建议 |
|------|------|
| SQLite TRIGGER | **不做** — 与「业务在 service」一致，且 trigger 与 ORM/迁移演进难测 |
| CHECK 子查询 | SQLite 支持弱；**不做** |
| 空表 + 文档 | **采用** |

### 5.3 与 data scope 的关系

Phase 0 已登记 `rms.application` → `inherit_via_client=True`, `client_fk=client_id`。Phase 1 建列后，Phase 2 的 `filter_query_by_client_scope` 才能对 `rms_applications` **直接**按 `client_id` 过滤，无需仅 JOIN `rms_jobs`。

### 5.4 Phase 1 测试对同步的覆盖

- **不**测业务 API 同步（无 CRUD）。
- **不**测 DB 拒绝 `application.client_id ≠ job.client_id`（Phase 2 service 测一致性）。

---

## 6. Schema 测试设计（`tests/test_rms_phase1_schema.py`）

### 6.1 用例列表

| 用例 | 断言 |
|------|------|
| `test_migration_005_applied` | `schema_migrations` 含 `005_rms_tables.sql` |
| `test_rms_tables_exist` | `sqlite_master` 含 8 张 `rms_*` 表 |
| `test_rms_jobs_has_owner_and_client` | `PRAGMA table_info(rms_jobs)` 含 `client_id`, `owner_user_id` |
| `test_rms_applications_has_client_id` | 含 `client_id`；`UNIQUE` 含 `(job_id, candidate_id)`（查 `sqlite_master` 或 `PRAGMA index_list`） |
| `test_rms_match_results_has_application_id` | 含 `application_id`；**无** `client_id` 列 |
| `test_rms_match_results_no_client_id_column` | 显式否定 |
| `test_migration_005_idempotent_second_run` | 再次 `run_all(engine)` 不抛错；表数量不变 |
| `test_orm_models_registered` | `main` 或 `register_rms_models` 返回的类 `__tablename__` 与表名一致 |
| `test_register_rms_models_idempotent` | 重复 `register_rms_models` 返回同一类 |
| `test_rms_applications_client_id_fk_to_clients`（可选） | `PRAGMA foreign_keys=ON`：无效 `client_id` 插入失败（仅校验存在于 `clients`） |

**禁止：** 测试「`application.client_id` 与 `job.client_id` 不一致被 DB 拒绝」——无 trigger/CHECK 时 SQLite 无法保证；由 Phase 2 service 测试覆盖。

### 6.2 风格

- 对齐 [`tests/test_permission_datascope.py`](../tests/test_permission_datascope.py) 的 `test_migration_004_applied`。
- 使用 `import main as crm_main` + `crm_main.engine`；不启动业务路由。

### 6.3 不写的测试

- CRUD API、权限 403、文件上传、AI、花名册转入。

---

## 7. 验收命令

```bash
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```

可选人工：

```bash
sqlite3 tests/_pytest_crm.db ".tables" | tr ' ' '\n' | grep rms_
sqlite3 tests/_pytest_crm.db "SELECT migration_id FROM schema_migrations WHERE migration_id='005_rms_tables.sql';"
```

---

## 8. 实施顺序（确认后执行）

```
1. 编写 migrations/005_rms_tables.sql → 本地 pytest 库自动 migrate
2. 新增 models/rms.py；main.py 在 run_schema_migrations 之后 register_rms_models（不 create_all RMS）
3. 新增 tests/test_rms_phase1_schema.py
4. check_architecture + 全量 pytest
5. （可选）reports/architecture/phase-29-rms-phase1-report.md
```

**停止条件：** 若实施需新增 `routes/rms_jobs.py` 或 `services/*` 才能绿测 — 说明范围膨胀，应回退为纯 schema。

---

## 9. 风险与待确认项

| 项 | 说明 | 默认决策 |
|----|------|----------|
| `UNIQUE(job_id, candidate_id)` | 禁止同一岗位重复推荐同一候选人 | **采用** |
| `ON DELETE CASCADE` | 删 application 级联 history/interview/offer/match | **采用**（子表）；删 job **不** CASCADE applications（RESTRICT 默认） |
| `rms_jobs` 删 job | 有 application 时 SQLite 默认 RESTRICT | 保持，Phase 2 软删/status |
| ORM 放 `main.py` vs `models/rms.py` | 见 §3 | **models/rms.py** |
| `status` 枚举值 | Phase 1 仅 TEXT + DEFAULT | 枚举常量放 Phase 2 `schemas/rms.py` |

---

## 10. 与 plan/29 验收清单对齐

Phase 1 完成后勾选（[`plan/29-rms-module-plan.md`](29-rms-module-plan.md) §Phase 1）：

- [ ] `005_rms_tables.sql` 入账且可重复跑迁移流程
- [ ] 8 表字段与文档一致（含 `rms_applications.client_id`、`rms_match_results.application_id`、match 无 `client_id`）
- [ ] pytest 全绿
- [ ] 无 CRUD / 页面 / 上传 / AI / 花名册

---

**下一步：** 你确认本预案（尤其 §3 ORM 位置、`UNIQUE(job_id, candidate_id)`、§5 同步仅 Phase 2）后，再在 Agent 模式实施 Phase 1。
