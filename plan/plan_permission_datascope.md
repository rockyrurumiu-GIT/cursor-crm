# 02.5 权限数据范围方案：Permission Data Scope

## 执行顺序（Cursor 从这里开始）

> **Gate：Step 0 验收通过前，不得开始 Step 2 及之后的数据库迁移与 API 接入。**

### Step 0：对齐 03 命名 + Client 交付锚点（已完成）

### Step 1–6：已全部实现

| Step | 状态 | 说明 |
|------|------|------|
| 1 | 完成 | 系统 API 权限保护 + `test_viewer_cannot_set_role_data_scopes` |
| 2 | 完成 | `004_permission_datascope.sql`、schema compat、Owner 列 |
| 3 | 完成 | `auth/data_scope.py`、`AuthContext` 扩展、默认 seed |
| 4 | 完成 | 客户/商机/联系人/结算/花名册/交接等核心 API 接入 |
| 5 | 完成 | 权限中心：部门列、数据权限页、权限预览页 |
| 6 | 完成 | `tests/test_permission_datascope.py`，全量 pytest 59 passed |

Owner 迁移脚本：`scripts/migrate_owner_user_id.py`（默认 dry-run）

---

### Step 1–6 概览（Step 0 通过后再做）

| Step | 内容 | 详见 |
|------|------|------|
| 1 | 系统管理 API 功能权限审计 | 下文「当前 RBAC 必须先修正的安全点」 |
| 2 | DB migration + Owner 迁移脚本 | 下文「数据库变更」「初始化数据」 |
| 3 | `auth/data_scope.py` + AuthContext 扩展 | 下文「后端实现要求」 |
| 4 | 核心业务 API 接入数据范围 | 下文「业务接口接入清单」 |
| 5 | 权限管理 UI（部门、数据权限、预览） | 下文「前端 UI 改造」「API 建议」 |
| 6 | pytest + 手工多用户回归 | 下文「测试要求」「验收标准」 |

---

## Summary

本方案是在现有 `02-local-rbac` 基础上增加一层“数据范围权限”，用于解决：

- 同属销售职能的不同销售，只能看到自己负责或本部门范围内的客户、商机、跟进信息。
- 同属交付职能的不同交付人员，只能看到分配给自己或本交付团队范围内的项目、排期、交付信息。
- 功能模块权限继续保留，数据范围权限只决定“同一个模块下能看到哪些业务数据”。

本方案可以理解为 `02.5`，应在正式执行 `03-data-scope-wecom-sharing.md` 之前完成。

## 核心结论

不要推翻现有按功能模块的 RBAC。

现有模型继续负责：

```text
用户 -> 角色 -> 功能权限
```

本方案新增：

```text
用户 -> 角色 -> 功能权限 -> 数据范围
```

权限判断必须拆成两步：

```text
1. 功能权限：这个人能不能进入模块、能不能执行 read/write/export 等动作
2. 数据范围：这个人能访问该模块下哪些业务数据
```

示例：

```text
销售 A 有 crm.clients.read
但数据范围是 assigned
所以他能进入客户模块，但只能看到自己负责或分配给自己的客户。

销售主管有 crm.clients.read
但数据范围是 dept
所以他能进入客户模块，并看到本部门客户。

超级管理员有 crm.clients.read
且数据范围是 all
所以他能看到全部客户。
```

## Goals

1. 保留现有 `sys_user`、`sys_role`、`sys_permission`、`sys_user_role`、`sys_role_permission` 模型。
2. 增加组织/部门模型，用于表达销售团队、交付团队等业务归属。
3. 增加角色数据范围模型，用于配置某角色对某类资源的可见范围。
4. 为核心业务表补充明确的业务 Owner 字段。
5. 所有核心列表、详情、导出、更新接口接入数据范围过滤。
6. 权限管理 UI 增加“数据权限配置”和“权限预览”。
7. 增加测试，证明同功能模块下不同用户只能看到自己的业务数据。

## Non-goals

本方案不做以下内容：

1. 不做企业微信组织同步。
2. 不做离职交接流程。
3. 不做复杂共享审批流。
4. 不做完整 `sys_file_auth` 文件 ACL 模型。
5. 不做 Dump 生命周期。
6. 不重写登录、会话、密码策略。
7. 不把数据范围硬编码进角色名。

## 必须遵守的设计约束

### 1. 功能权限和数据范围必须分离

不要新增大量类似下面的角色：

```text
SALES_GROUP_A
SALES_GROUP_B
DELIVERY_IMPL_A
DELIVERY_IMPL_B
DELIVERY_PM_A
```

这种做法会导致角色爆炸。

正确做法：

```text
角色控制功能权限
部门/团队/Owner/分配关系控制数据范围
```

### 2. Owner 必须是明确字段

必须使用明确的业务负责人字段：

```text
owner_user_id
owner_dept_id
```

`created_by` 只用于审计，不作为业务权限判断主依据。

不要写成模糊规则：

```text
Owner 或录入人
```

正确规则：

```text
Owner = owner_user_id
部门归属 = owner_dept_id
录入人 = created_by，仅用于审计
```

### 3. 数据范围过滤必须在后端完成

不要只在前端隐藏数据。

以下接口都必须在后端套数据范围：

```text
列表接口
详情接口
更新接口
删除接口
导出接口
文件预览/下载接口中与业务对象绑定的部分
```

### 4. 缺少数据范围配置时默认拒绝

如果用户拥有某个功能权限，但没有对应资源的数据范围配置，默认不返回业务数据。

例外：

```text
SUPER_ADMIN 默认 all
```

其他角色不允许因为配置缺失而自动看到全部数据。

### 5. 多角色合并规则

功能权限按并集计算。

数据范围按同一资源、同一动作下的最大范围计算：

```text
none < own < assigned < dept < dept_tree < all
```

例如一个用户同时拥有：

```text
角色 A: crm.client read = own
角色 B: crm.client read = dept
```

最终：

```text
crm.client read = dept
```

## 数据范围类型

**与 Phase 03 共用同一套 scope 枚举**（backend 存储值），避免 03 重写：

```text
none            无数据权限（02.5）
self            仅 owner_user_id = 当前用户（对应 03 的 SELF；旧称 own）
assigned        owner 或 assigned_user = 当前用户（02.5 扩展）
dept            owner_dept_id 属于当前用户所在部门（02.5 扩展）
dept_and_child  owner_dept_id 属于当前用户部门或下级部门（对应 03 的 DEPT_AND_CHILD；旧称 dept_tree）
all             全部数据（对应 03 的 ALL）
shared          显式共享（03 才启用；02.5 不实现，但枚举预留）
```

合并优先级：

```text
none < self < assigned < dept < dept_and_child < all
（shared 在 03 与上述范围取并集，02.5 忽略）
```

说明：

- `assigned` 必须包含 `self`。
- `dept` 可以包含当前用户所在的一个或多个部门。
- `dept_and_child` 依赖部门树 `path` 或等价结构。
- `all` 只给超级管理员、老板、总监类角色。
- UI 中文可显示「仅本人 / 分配给我 / 本部门 / 本部门及下级 / 全部」，存储必须用上表 code。

## 建议资源编码

资源编码用于**数据范围配置**，与 [`auth/permissions.py`](../auth/permissions.py) 中的**功能权限点**分离，但必须有显式映射。

第一版资源清单（已对齐现有代码，**去掉虚构的 `delivery.project`**）：

```text
crm.client          -> crm.clients.read / .write
crm.opportunity     -> crm.opportunities.read / .write
crm.contact         -> crm.contacts.read / .write
crm.visit           -> crm.visits.read / .write
delivery.roster     -> delivery.roster.read / .write
delivery.pipeline   -> delivery.pipeline.read / .write
delivery.interviews -> delivery.interviews.read / .write
delivery.handbook   -> delivery.handbook.read / .write
delivery.handoff    -> delivery.handoff.read / .write / .review
delivery.settlement -> delivery.settlement.read / .write
file                -> 继承父业务对象 scope（02.5 不做 sys_file_auth）
```

实现时新增 `auth/data_scope_catalog.py`，集中维护：

- `RESOURCE_CODES`
- `PERMISSION_TO_RESOURCE`（功能权限前缀 -> 资源码）
- `RESOURCE_SCOPE_ANCHOR`（每条资源的 scope 过滤锚点：见下节）

## 交付隔离锚点：以 Client 为中心

**第一版交付数据范围不以每张交付子表独立 Owner 为主**，而以客户（`clients` 表）为锚：

```text
crm.client 资源：
  Client.owner_user_id
  Client.owner_dept_id
  Client.assigned_user_id（可选，销售协同）

delivery.* 资源（roster / pipeline / interviews / handbook / handoff / settlement）：
  Client.delivery_owner_user_id   # 交付负责人
  Client.delivery_dept_id       # 交付归属部门（可选）
  子表通过 client_id JOIN clients 做 scope，不在每张交付子表重复 owner 三列
```

与 Phase 03 Owner 规则对齐：

```text
Client.owner_user_id = 销售负责人
Client.delivery_owner_user_id = 交付负责人
Opportunity.owner_user_id = 继承 Client，除非单独指定
Roster / Interview / Settlement / Pipeline / Handbook = 继承 Client（Pipeline 可有 recruiter_user_id，无法匹配时仍继承 Client）
HandoffRequest.delivery_owner_user_id -> approve 后同步到 Client.delivery_owner_user_id
```

旧字符串字段（`Client.owner`、`HandoffRequest.delivery_owner`）保留不删，仅作展示/迁移来源。

## 数据库变更

新增 migration 文件，不要直接改历史 migration。

建议文件名：

```text
migrations/003_permission_datascope.sql
```

### 1. 组织/部门表

```sql
CREATE TABLE IF NOT EXISTS sys_dept (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  code TEXT NOT NULL UNIQUE,
  parent_id INTEGER NULL,
  path TEXT NOT NULL,
  dept_type TEXT NOT NULL DEFAULT 'general',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(parent_id) REFERENCES sys_dept(id)
);
```

`dept_type` 建议支持：

```text
sales
delivery
finance
general
```

### 2. 用户部门关系

```sql
CREATE TABLE IF NOT EXISTS sys_user_dept (
  user_id INTEGER NOT NULL,
  dept_id INTEGER NOT NULL,
  is_primary INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, dept_id),
  FOREIGN KEY(user_id) REFERENCES sys_user(id),
  FOREIGN KEY(dept_id) REFERENCES sys_dept(id)
);
```

### 3. 角色数据范围表

```sql
CREATE TABLE IF NOT EXISTS sys_role_data_scope (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role_id INTEGER NOT NULL,
  resource_code TEXT NOT NULL,
  action TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(role_id, resource_code, action),
  FOREIGN KEY(role_id) REFERENCES sys_role(id)
);
```

`action` 第一版支持：

```text
read
write
export
delete
```

### 4. 核心业务表 Owner 字段

**只在需要独立 scope 或无法仅靠 Client 锚点的表上加列**（见上节「交付隔离锚点」）。

#### 4.1 必须 ALTER 的表

`clients`（锚点表）：

```sql
ALTER TABLE clients ADD COLUMN owner_user_id INTEGER NULL;
ALTER TABLE clients ADD COLUMN owner_dept_id INTEGER NULL;
ALTER TABLE clients ADD COLUMN assigned_user_id INTEGER NULL;
ALTER TABLE clients ADD COLUMN delivery_owner_user_id INTEGER NULL;
ALTER TABLE clients ADD COLUMN delivery_dept_id INTEGER NULL;
```

`opportunities`（可覆盖 Client 销售 Owner）：

```sql
ALTER TABLE opportunities ADD COLUMN owner_user_id INTEGER NULL;
ALTER TABLE opportunities ADD COLUMN owner_dept_id INTEGER NULL;
```

`handoff_requests`（交接指派，approve 后写回 Client）：

```sql
ALTER TABLE handoff_requests ADD COLUMN delivery_owner_user_id INTEGER NULL;
```

`visits`（若拜访记录不总是挂 Client 且需独立 scope）：

```sql
ALTER TABLE visits ADD COLUMN owner_user_id INTEGER NULL;
ALTER TABLE visits ADD COLUMN owner_dept_id INTEGER NULL;
```

`delivery_pipeline_entries`（可选，仅当需 recruiter 独立 scope）：

```sql
ALTER TABLE delivery_pipeline_entries ADD COLUMN recruiter_user_id INTEGER NULL;
```

#### 4.2 通过 Client 继承、不重复 Owner 列的表

```text
roster_entries
delivery_settlement_entries
delivery_interview_entries
delivery_handbook_files
```

查询模式：`... JOIN clients c ON c.id = <table>.client_id`，对 `delivery.*` 用 `c.delivery_owner_user_id` / `c.delivery_dept_id` 套 scope；对销售侧重资源用 `c.owner_user_id` / `c.owner_dept_id`。

#### 4.3 索引

```sql
CREATE INDEX IF NOT EXISTS idx_clients_owner_user_id ON clients(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_clients_owner_dept_id ON clients(owner_dept_id);
CREATE INDEX IF NOT EXISTS idx_clients_delivery_owner_user_id ON clients(delivery_owner_user_id);
CREATE INDEX IF NOT EXISTS idx_clients_delivery_dept_id ON clients(delivery_dept_id);
-- opportunities / handoff_requests / visits 同理
```

## 初始化数据

迁移后需要初始化默认部门和默认数据范围。

### 1. 默认部门

至少初始化：

```text
ROOT
SALES
DELIVERY
FINANCE
ADMIN
```

示例：

```text
ROOT / 公司
ROOT/SALES / 销售部
ROOT/DELIVERY / 交付部
ROOT/FINANCE / 财务部
ROOT/ADMIN / 管理部
```

### 2. 默认用户归属

如果现有用户没有部门：

- `admin` 放入 `ADMIN`
- 角色包含 `SALES` 的用户放入 `SALES`
- 角色包含 `DELIVERY` 的用户放入 `DELIVERY`
- 无法判断的用户放入 `ROOT` 或 `ADMIN`，但必须在 UI 中可修改

### 3. 默认角色数据范围

建议：

```text
SUPER_ADMIN:
  所有资源 read/write/export/delete = all

SALES:
  crm.client read/write/export = assigned
  crm.opportunity read/write/export = assigned
  crm.visit read/write/export = assigned

DELIVERY:
  delivery.roster read/write/export = assigned
  delivery.pipeline read/write/export = assigned
  delivery.interviews read/write/export = assigned
  delivery.handbook read/write/export = assigned
  delivery.handoff read/write/export = assigned
  delivery.settlement read/write/export = assigned
  # assigned = Client.delivery_owner_user_id 或 assigned 语义匹配当前用户

VIEWER:
  常用资源 read = assigned
  write/export/delete = none

RESTRICTED:
  全部 none
```

如果需要主管角色，可以新增：

```text
SALES_MANAGER:
  销售资源 read/write/export = dept

DELIVERY_MANAGER:
  交付资源 read/write/export = dept
```

第一版不要自动创建过多业务角色，只保留必要角色。

## 后端实现要求

### 1. AuthContext 增强

在当前认证上下文中增加：

```text
user_id
username
role_codes
permission_codes
dept_ids
primary_dept_id
is_super_admin
```

不要在业务接口里重复查用户角色。

### 2. 增加数据范围服务

建议新增或扩展：

```text
auth/data_scope.py
```

核心函数建议：

```python
get_effective_data_scope(ctx, resource_code, action) -> str
```

```python
assert_data_scope(ctx, resource_code, action) -> str
```

```python
apply_data_scope(
    query,
    model,
    ctx,
    resource_code,
    action,
    owner_user_col,
    owner_dept_col,
    assigned_user_col=None,
)
```

如果当前代码存在 raw SQL 查询，可以额外提供：

```python
build_data_scope_where(
    ctx,
    resource_code,
    action,
    owner_user_column,
    owner_dept_column,
    assigned_user_column=None,
) -> tuple[str, dict]
```

要求：

- 数据范围逻辑必须集中实现。
- 不要在各个路由里散落 `if role == "SALES"`。
- 不要在前端拼数据范围参数。

### 3. 接口鉴权顺序

所有业务接口必须遵守：

```text
1. authenticate
2. require_permission(function_permission)
3. apply_data_scope / check_resource_access
4. 执行业务逻辑
```

示例：

```text
GET /api/clients
  -> require crm.clients.read
  -> apply crm.client read data scope

PUT /api/clients/{id}
  -> require crm.clients.write
  -> check crm.client write data scope for this client

GET /api/clients/export
  -> require crm.clients.read 或 crm.clients.export
  -> apply crm.client export data scope
```

### 4. 列表接口

列表必须在数据库查询阶段过滤，不允许查出全部数据后在 Python 或前端过滤。

对于分页接口，过滤必须发生在 count 和 list 查询之前，避免总数泄露。

### 5. 详情接口

详情接口必须检查单条数据是否在当前用户数据范围内。

推荐：

```text
无权限访问该数据时返回 404
```

这样避免暴露“这条数据存在但你不能看”。

如果现有系统统一使用 403，也可以继续用 403，但必须全局一致。

### 6. 写接口

更新、删除、状态变更、审批等接口必须检查 `write` 或 `delete` 数据范围。

创建数据时：

```text
默认 owner_user_id = 当前用户
默认 owner_dept_id = 当前用户 primary_dept_id
```

如果前端传入 owner 字段：

- SUPER_ADMIN 可以指定任意 Owner。
- 主管只能指定本部门范围内 Owner。
- 普通成员不能给别人创建 Owner 数据，除非有明确业务需求和测试。

### 7. 导出接口

导出接口必须使用 `export` 数据范围。

如果暂时没有独立 `export` 权限点，可以先复用 read，但数据范围 action 仍然用 `export`，便于后续收紧。

### 8. 文件访问

本方案不做完整文件 ACL。

但如果文件可以关联到客户、商机、交付项目或结算，文件访问必须继承父业务对象的数据范围。

示例：

```text
客户附件 -> 按 crm.client read 判断
商机附件 -> 按 crm.opportunity read 判断
交付附件 -> 按父资源 delivery.* read 判断（经 client 锚点继承）
```

不要重新开放裸文件路径。

## 当前 RBAC 必须先修正的安全点

在执行数据范围前，先确认系统管理接口本身已经有功能权限保护。

至少确认：

```text
创建用户 -> system.users.manage
修改用户角色 -> system.users.manage
重置密码 -> system.users.manage
修改角色权限 -> system.roles.manage
修改数据范围 -> system.roles.manage
查看审计日志 -> system.audit.read
```

如果发现这些接口只做了登录校验，没有做权限校验，必须先修。

这是 P0，因为没有它，任何登录用户都可能改角色或数据范围。

## 前端 UI 改造

当前“角色与权限”页面不要继续只展示权限代码。

建议拆成以下页签：

```text
1. 用户管理
2. 角色管理
3. 功能权限矩阵
4. 数据权限配置
5. 权限预览
6. 审计日志
```

本方案重点完成：

```text
用户管理中的部门选择
数据权限配置
权限预览
```

### 1. 用户管理

用户列表增加：

```text
用户名
显示名
状态
部门
角色
最后登录
操作
```

创建/编辑用户时增加：

```text
主部门
附属部门
角色多选
```

不要让管理员手动输入角色代码字符串。

### 2. 数据权限配置

建议 UI 结构：

```text
选择角色：SALES / DELIVERY / VIEWER / ...

资源                 read        write       export      delete
客户                 assigned    assigned    assigned    none
商机                 assigned    assigned    assigned    none
客户拜访             assigned    assigned    assigned    none
交付项目             assigned    assigned    assigned    none
交付排期             assigned    assigned    assigned    none
交付结算             assigned    assigned    assigned    none
```

每个单元格是下拉选择：

```text
无
仅本人
分配给我
本部门
本部门及下级
全部
```

中文展示可以用中文，但后端存储必须使用稳定 code：

```text
none / own / assigned / dept / dept_tree / all
```

### 3. 权限预览

新增一个预览工具：

```text
选择用户
显示该用户角色
显示该用户功能权限
显示该用户每个资源的最终数据范围
```

示例展示：

```text
用户：A1
角色：SALES

客户：
  read = assigned
  write = assigned
  export = assigned

商机：
  read = assigned
  write = assigned
  export = assigned

交付项目：
  read = none
```

第一版不要求展示具体可见数据列表，但如果实现成本低，可以展示：

```text
可见客户数
可见商机数
可见交付项目数
```

## API 建议

新增或补充以下接口。

### 部门接口

```text
GET  /api/system/depts
POST /api/system/depts
PUT  /api/system/depts/{dept_id}
```

权限：

```text
system.users.manage
```

### 用户部门接口

可以合并进用户创建/编辑接口，也可以单独提供：

```text
PUT /api/system/users/{user_id}/depts
```

权限：

```text
system.users.manage
```

### 角色数据范围接口

```text
GET /api/system/roles/{role_id}/data-scopes
PUT /api/system/roles/{role_id}/data-scopes
```

权限：

```text
system.roles.manage
```

### 权限预览接口

```text
GET /api/system/users/{user_id}/permission-preview
```

权限：

```text
system.roles.manage 或 system.users.manage
```

返回：

```json
{
  "user": {
    "id": 1,
    "username": "A1",
    "display_name": "A1"
  },
  "roles": ["SALES"],
  "permissions": ["crm.clients.read", "crm.clients.write"],
  "data_scopes": [
    {
      "resource_code": "crm.client",
      "action": "read",
      "scope_type": "assigned"
    }
  ]
}
```

## 业务接口接入清单

Cursor 执行时必须搜索当前代码中的所有业务接口，不要只改显眼页面。

重点检查：

```text
客户列表、详情、新增、编辑、删除、导出
商机列表、详情、新增、编辑、删除、导出
客户拜访/跟进列表、详情、新增、编辑、导出
交付管线列表、详情、新增、编辑、导出
交付排期列表、详情、新增、编辑、导入、导出
交付手册列表、详情、新增、编辑、PDF/导出
交接相关接口
结算相关接口
文件访问接口
```

所有接口必须做到：

```text
有功能权限，但没有数据范围 -> 看不到数据
有数据范围，但没有功能权限 -> 不能访问模块/API
```

## 测试要求

新增或扩展 pytest。

建议测试文件：

```text
tests/test_permission_datascope.py
```

至少覆盖以下场景：

### 1. 普通销售只能看自己的客户

```text
用户 sales_a 属于 SALES_DEPT_A
用户 sales_b 属于 SALES_DEPT_B

客户 A owner_user_id = sales_a
客户 B owner_user_id = sales_b

sales_a 请求客户列表
只能看到客户 A
看不到客户 B
```

### 2. 普通销售不能访问别人客户详情

```text
sales_a GET /api/clients/{client_b_id}
返回 404 或 403
```

### 3. 销售主管能看本部门客户

```text
sales_manager 属于 SALES_DEPT_A
scope = dept

能看到 SALES_DEPT_A 的客户
不能看到 SALES_DEPT_B 的客户
```

### 4. 交付人员只能看分配给自己的交付数据

```text
delivery_a scope = assigned

只能看到 owner_user_id = delivery_a 或 assigned_user_id = delivery_a 的交付项目
```

### 5. SUPER_ADMIN 能看全部

```text
admin scope = all

所有资源列表均不被业务数据范围过滤
```

### 6. 没有数据范围配置默认拒绝

```text
用户有 crm.clients.read
但角色没有 crm.client read data scope

客户列表为空或返回拒绝
```

### 7. 导出不能绕过数据范围

```text
sales_a 导出客户
导出结果不包含 sales_b 的客户
```

### 8. 系统管理接口必须有功能权限

```text
普通 VIEWER 不能修改用户角色
普通 VIEWER 不能修改角色数据范围
```

## 验收标准

执行完成后必须满足：

1. 现有功能 RBAC 没有被推翻。
2. 权限判断链路明确为：

```text
authenticate -> require_permission -> apply_data_scope
```

3. 用户可以归属到部门。
4. 角色可以配置不同资源、不同动作的数据范围。
5. 客户、商机、交付等核心业务数据有明确 `owner_user_id` / `owner_dept_id` 或可从父对象继承 Owner。
6. `created_by` 不作为业务权限主判断。
7. 普通销售不能看到其他销售的数据。
8. 普通交付不能看到其他交付的数据。
9. 主管可以按部门范围看到数据。
10. SUPER_ADMIN 可以看到全部数据。
11. 列表、详情、导出都不能绕过数据范围。
12. 权限管理页不再要求手动输入角色代码字符串。
13. 新增测试通过。

## 建议执行顺序

完整步骤已移至**文档顶部「执行顺序（Cursor 从这里开始）」**。此处保留 Step 1–6 细节供 Step 0 完成后查阅。

> Step 0 验收通过前，不得开始下列 Step 2 及之后内容。

### Step 1：安全前置校验

检查并修正系统管理接口权限：

```text
用户管理 API 必须 system.users.manage
角色管理 API 必须 system.roles.manage
数据范围 API 必须 system.roles.manage
审计 API 必须 system.audit.read
```

验证：

```text
普通 VIEWER 调用系统管理写接口返回 403
```

### Step 2：数据库迁移

新增：

```text
sys_dept
sys_user_dept
sys_role_data_scope
业务表 owner_user_id / owner_dept_id / assigned_user_id
必要索引
```

验证：

```text
迁移可重复执行
旧数据不丢失
默认 admin 可登录
```

### Step 3：认证上下文和数据范围服务

实现：

```text
AuthContext 部门信息
get_effective_data_scope
apply_data_scope
build_data_scope_where
```

验证：

```text
单元测试覆盖 own / assigned / dept / all
```

### Step 4：接入核心业务接口

按模块逐个接入：

```text
客户
商机
拜访/跟进
交付
排期
手册
交接
结算
文件访问
```

验证：

```text
不同用户看到的数据不同
导出结果也被过滤
```

### Step 5：权限管理 UI 改造

增加：

```text
用户部门选择
数据权限配置
权限预览
```

验证：

```text
管理员可以用 UI 配置角色数据范围
选择用户后可以看到最终权限和最终数据范围
```

### Step 6：测试和回归

运行：

```text
./venv/bin/python -m pytest tests/ -q
```

若项目有启动验证，也需要启动本地服务手动验证：

```text
admin 登录
创建销售 A / 销售 B / 交付 A / 交付 B
分别创建归属数据
确认互相不可见
```

## Cursor 执行注意事项

1. 先用 `rg` 搜索现有 RBAC、权限点、系统管理页和业务接口，不要凭空猜文件结构。
2. 不要重写整个认证系统。
3. 不要删除现有角色权限表。
4. 不要把数据范围写死在角色名里。
5. 不要只改前端。
6. 不要把 `created_by` 当 Owner。
7. 不要让导出接口绕过数据范围。
8. 不要让 `/api/files/access` 或类似文件接口绕过父业务对象权限。
9. 代码改动完成后必须补测试。
10. 如果某些老数据没有 Owner，迁移时要有明确兜底策略，并在结果中说明。

## 完成后预期效果

执行本方案后，系统应达到：

```text
同一个销售模块：
  销售 A 只能看自己的客户/商机
  销售 B 只能看自己的客户/商机
  销售主管能看本部门客户/商机
  超级管理员能看全部

同一个交付模块：
  交付 A 只能看分配给自己的交付数据
  交付 B 只能看分配给自己的交付数据
  交付主管能看本交付团队数据
  超级管理员能看全部
```

这一步完成后，再执行 `03-data-scope-wecom-sharing.md` 时，可以专注做：

```text
企微组织同步
共享/协作 ACL
离职交接
完整文件权限
```

而不是把基础数据范围和组织同步混在一起做。
