# 工程基线（横切任务）

> **可执行文档**。全局权限设计见 [00-rbac-master-plan.md](00-rbac-master-plan.md)（仅上下文，不直接执行）。  
> 与权限无关的功能债与可维护性底座；按落点在 **01** / **02** 实施。

---

## 总览

| 基线项 | 必要性 | 落点 |
|--------|--------|------|
| 结算 API 路径统一 | 明确功能 bug；RBAC 会放大前后端不一致 | **01**（优先，不等 RBAC） |
| SQLite migration ledger | 02/03 多表多字段，需 schema 版本账本 | **02 首 commit** |
| pytest smoke tests | 权限改造易漏 403 或页面/API 分裂 | **01 末起，02/03 扩展** |

---

## 1. 结算 API 路径统一

**现状（已知不一致）**：

| 调用方 | 编辑/删除路径 |
|--------|----------------|
| 后端 [main.py](../main.py) | `PUT/DELETE /api/delivery/settlement/row/{row_id}` |
| [delivery_settlement.html](../templates/pages/delivery_settlement.html) | `/api/delivery/settlement/row/{id}`（一致） |
| [delivery_detail.html](../templates/pages/delivery_detail.html) | `/api/delivery/settlement/{id}`（**缺 `/row/`，bug**） |

**要求**（二选一，推荐 A）：

- **A**：前端统一为 `/api/delivery/settlement/row/{id}`（改 `delivery_detail.html`）。
- **B**：后端增加兼容 alias：`PUT/DELETE /api/delivery/settlement/{row_id}` 转发至同一 handler。

**验收**：结算页与客户交付详情内嵌结算的列表、创建、编辑、删除均成功；纳入 smoke tests。

---

## 2. 轻量 migration 机制

- 表：`schema_migrations(migration_id TEXT PRIMARY KEY, applied_at)`（见 00 表设计）。
- 模块：`scripts/run_migrations.py` 或 `auth/migrations.py`；按序应用 `migrations/*`。
- **幂等**：ledger 中已有的 `migration_id` 跳过。
- **日志**：applied / skipped / failed；失败中止后续迁移。
- **与 Owner 脚本**：`migrate_owner_user_id.py` 为数据迁移，`--dry-run` 默认、`--apply` 前备份；不替代 schema ledger。
- **02 首批**：RBAC 相关 `sys_*`；**03** 追加部门、共享、`sys_file_auth` 等。

---

## 3. 最小自动化 smoke tests

- **pytest** + FastAPI **TestClient**；目录 `tests/`。
- 测试库：内存 SQLite 或临时 `crm_test.db`；conftest 固定 `CRM_AUTH_MODE` / `CRM_ALLOW_DEFAULT_ADMIN`。

### 01 首期

| 用例 | 断言 |
|------|------|
| admin 登录 | bootstrap / Basic 后 `/api/stats` 200 |
| 未登录文件 | `/api/files/access` 401 |
| 结算 CRUD | 列表、创建、`PUT/DELETE .../row/{id}` |
| legacy 回退 | `CRM_AUTH_MODE=legacy` 核心 API 可访问（若已实现） |

### 02 扩展

| 用例 | 断言 |
|------|------|
| 普通用户无权限 | 无 `crm.clients.read` 时 `GET /api/clients` 403 |
| `/api/me` | permissions 与角色一致 |
| HTML 门控 | 无 Cookie 时 `GET /customers` 302 `/login`（可选） |

### 03 扩展

行级隔离、文件网关 + `sys_file_auth` 拒绝无权限文件。

**原则**：每阶段合并前 `pytest tests/ -q`；新增 API 权限时补一条 smoke。

---

## 与分阶段文档的关系

| 阶段文档 | 本文件条目 |
|----------|------------|
| [01-security-foundation.md](01-security-foundation.md) | §1 结算、§3 首期 smoke |
| [02-local-rbac.md](02-local-rbac.md) | §2 migration、§3 扩展 smoke |
