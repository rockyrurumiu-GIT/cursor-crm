# 02 - CRM 本地 RBAC 权限管理

> 执行文档。全局设计见 `00-rbac-master-plan.md`（仅上下文，不直接执行）。

## 目标

实现一套完整的本地功能权限管理：

- 本地用户登录。
- 用户管理。
- 角色管理。
- 权限点管理。
- 菜单按权限显示。
- API 按权限返回 403。
- **全站 HTML 与 API 统一 session 校验**（相对 01 的完整升级）。

本阶段完成后，系统具备本地权限管理能力，但还没有企业级行级数据隔离。

## 不做

- 不做企微 OAuth。
- 不做部门树。
- 不做 Owner 行级隔离。
- 不做客户共享。
- 不做离职交接。
- 不做“销售只能看自己客户”。
- 不做 `sys_file_auth` 行级文件权限（留给 03）。
- 不做 Dump/废弃池（留给 04）。

## 预期结果

admin 登录后可以：

- 创建本地用户。
- 创建角色。
- 给角色分配权限。
- 给用户分配角色。
- 控制用户能看哪些菜单、调用哪些 API。

普通用户登录后：

- 只能看到自己有权限的菜单。
- 调用无权限 API 返回 403。
- 如果有 `crm.clients.read`，仍可看到全部客户数据。

## 建议表结构

新增 `auth/` 模块和 `sys_*` 表：

```text
sys_user
sys_role
sys_permission
sys_user_role
sys_role_permission
sys_audit_log
```

建议 `sys_user` 至少包含：

```text
id
username
display_name
password_hash
status
created_at
updated_at
```

建议种子角色：

```text
SUPER_ADMIN
SALES
DELIVERY
VIEWER
```

建议权限码：

```text
crm.clients.read
crm.clients.write
crm.opportunities.read
crm.opportunities.write
delivery.roster.read
delivery.roster.write
delivery.pipeline.read
delivery.pipeline.write
delivery.handbook.read
delivery.handbook.write
delivery.handoff.review
system.users.manage
system.roles.manage
system.audit.read
```

## 关键改动

### 1. Auth 模块

新增独立模块，避免继续膨胀 `main.py`：

```text
auth/
  models.py
  service.py
  permissions.py
  password.py
  routes.py
```

### 2. 登录机制

- 新增本地登录。
- 推荐使用 HttpOnly Cookie session。
- 不要把长期 token 放进 `localStorage`。
- 保留 legacy 开关，方便回退。

### 2.1 完整 HTML Session 校验（相对 01 的升级）

01 仅做「未登录不可看页面壳」；本阶段必须升级为 **全站统一会话**：

**服务端（必须）**：

- 所有业务 HTML 路由（含 `main.py`、handoff、phase2、visit 注册的页面）经 **同一 session 中间件** 或 `_page()` 守卫校验。
- 校验依据：**HttpOnly Cookie session**（`rbac` 模式）或 legacy Basic（`legacy` 模式），与 API 使用同一 `get_current_user` 入口。
- 未登录 → `302 /login`（推荐）或 `401`；session 过期 → 清除 Cookie 并重定向。
- 白名单：`/static/*`、`/login`、`/api/auth/login`、`/api/auth/logout`、OAuth 回调（03 预留）等。

**前端（必须）**：

- 下线「仅靠 `localStorage.crm_user` 决定是否显示壳」的逻辑；`base.html` 以 `/api/me` 或 session 状态初始化。
- 菜单仍可按权限隐藏，但 **不得以 localStorage 作为安全边界**。

**API 与 HTML 一致性**：

- 同一请求上下文内，HTML 与 `/api/*` 识别为同一用户。
- 禁止出现「页面能开、API 全 401」或「API 能调、页面未登录」的分裂状态。

**硬性要求（必须满足）**：

- 所有 HTML 路由必须依赖**服务端 session**（`rbac` 为 HttpOnly Cookie；`legacy` 为 Cookie + Basic 等价入口）。禁止仅以 `localStorage` 决定是否可访问页面。
- 未登录访问业务 HTML：`302` 跳转 `/login`；或对明确仅需鉴权的 HTML 请求返回 `401`（二者择一实现，推荐 302，API 型 HTML 片段可用 401）。
- `/api/me` 与页面渲染必须使用同一 `get_current_user` 用户上下文；菜单、页面初始化与后续 API 调用不得出现「页面用户 ≠ API 用户」。

### 3. `/api/me`

新增 `/api/me`，返回：

```json
{
  "user": {},
  "roles": [],
  "permissions": []
}
```

前端菜单基于 `/api/me.permissions` 渲染。

实现上：`/api/me` 与 HTML 中间件 / `_page()` 守卫共用 `get_current_user`，返回的 `user` 即为当前页面会话用户。

### 4. API 权限

新增：

```python
require_permission("perm.code")
```

逐步替换核心 API 的 `Depends(authenticate)`。

优先覆盖：

- 客户列表、客户新增、客户编辑、客户删除。
- 花名册读写。
- 交付管道读写。
- 手册读写。
- 交接审批。
- 用户和角色管理。

### 5. 菜单权限

- `nav.html` 或前端菜单基于权限渲染。
- 无权限菜单不可见。
- 不能只做前端隐藏，后端 API 必须同步校验。

### 6. Admin 兜底

- admin 始终拥有全部权限。
- `SUPER_ADMIN` 拥有全部权限。
- 开发环境继续允许 admin 验证所有功能。

### 7. 回退与开关（02 第一个 commit）

- 实现 `CRM_AUTH_MODE=legacy|rbac`（默认 `legacy`）。
- `legacy`：保留 Basic + 01 的 HTML 最小保护行为。
- `rbac`：Cookie session + `require_permission` + 完整 HTML 校验。
- 改造前建议打 `pre-auth-YYYYMMDD` tag 并备份 `crm_v8.db`（与总方案一致）。

### 8. 工程基线：migration ledger（02 首 commit，见 [engineering-baseline.md](engineering-baseline.md) §2）

- 创建 `schema_migrations` 表与 `run_migrations`（幂等、执行日志）。
- 首批 migration：RBAC 相关 `sys_*` 表；禁止仅靠 `Base.metadata.create_all` 无版本记录。
- Owner 数据迁移仍用 `migrate_owner_user_id.py`（`--dry-run` 默认），与 schema 迁移分离。

### 9. 工程基线：smoke tests 扩展（见 [engineering-baseline.md](engineering-baseline.md) §3）

- 扩展 `tests/`：普通用户 403、`GET /api/me`、（可选）HTML 302 登录门控。
- 02 合并前：`pytest tests/ -q` 全绿。

## 验收

1. admin 可登录并拥有全部权限。
2. admin 可创建用户和角色。
3. admin 可给用户分配角色。
4. 普通用户无权限菜单不可见。
5. 普通用户调用无权限 API 返回 403。
6. 有权限用户可正常访问对应页面/API。
7. legacy 模式仍可回退登录。
8. 02 完成后不应引入 Owner 行级隔离。
9. 未登录访问任意业务 HTML 路由 → `302 /login` 或 `401`（与实现一致；全路由覆盖，含 handoff/phase2/visit 页面）。
10. 登录后 Cookie session 有效时，HTML 与对应 API 为同一用户身份。
11. 清除 Cookie 或 session 过期后，HTML 与 API 均不可继续访问（不能仅靠 localStorage 残留进入壳）。
12. `GET /api/me` 返回的用户与当前 Cookie session 一致；换用户登录后 `/api/me` 与页面展示同步变化。
13. `schema_migrations` 存在且 RBAC 表 migration 已入账；重复执行迁移为 skipped。
14. `pytest tests/ -q` 通过（含 02 权限与 `/api/me` smoke）。

## Cursor 禁止事项

- 不要接企微。
- 不要做部门树。
- 不要改 Owner 规则。
- 不要把“功能权限”和“数据权限”混在本阶段完成。
- 不要一次性重写所有业务 API；优先覆盖核心路径。
