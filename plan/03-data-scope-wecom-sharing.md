# 03 - CRM 数据权限、企微与共享交接

> 执行文档。全局设计见 `00-rbac-master-plan.md`（仅上下文，不直接执行）。
>
> **Scope 枚举与资源锚点**：以 [`auth/data_scope_catalog.py`](../auth/data_scope_catalog.py) 为准（02.5 Step 0 定稿）。Phase 03 在相同枚举上扩展 `shared`，不另起命名。

## 目标

在 `02-local-rbac.md` 的本地 RBAC 基础上，实现企业级数据权限：

- Owner 行级隔离。
- 部门/主管可见范围。
- 企微 OAuth 和通讯录同步。
- 客户共享。
- 离职交接。
- 文件权限增强（`sys_file_auth` + Signed URL）。

## 不做

- 不重写全部业务模型。
- 不迁移到 MySQL/PostgreSQL。
- 不接 OSS/S3，先保留本地文件存储。
- 不承诺毫秒级企微群组权限回收。
- 不删除旧 Owner 字符串字段。
- 不做 Dump/废弃池（留给 `04-dump-lifecycle.md`）。

## 预期结果

- 销售只能看自己负责的客户。
- 主管可看本部门及子部门客户。
- admin 可看全部。
- Owner 可把客户共享给其他用户或组。
- 用户被禁用后不能继续访问系统。
- 离职用户名下数据必须交接。
- 文件访问跟随业务数据权限，且经 `sys_file_auth` 登记。

## Owner 规则

首期采用确定规则：

```text
Client.owner_user_id = 客户负责人
Opportunity.owner_user_id = 继承 Client，除非单独指定
Roster / Interview / Settlement = 继承 Client.owner_user_id
Pipeline = recruiter_user_id，无法匹配时继承 Client.owner_user_id
Handbook = client.owner_user_id + uploaded_by_user_id + 文件 ACL
```

不要使用“Owner 或录入人”这种模糊规则。

录入人只作为审计字段：

```text
created_by_user_id
updated_by_user_id
```

## 关键改动

### 1. 业务表扩展

业务表只增 nullable 字段，不删除旧字段：

```text
owner_user_id
created_by_user_id
updated_by_user_id
```

可按实体需要增加：

```text
recruiter_user_id
uploaded_by_user_id
```

### 2. Owner 迁移脚本

新增 owner 迁移脚本：

```bash
python scripts/migrate_owner_user_id.py --dry-run
python scripts/migrate_owner_user_id.py --apply
```

要求：

- 默认必须是 `--dry-run`。
- 输出未匹配清单。
- `--apply` 前自动备份数据库。
- 不删除旧 `owner` 字符串字段。
- 未匹配数据进入 admin 待认领，不要静默丢弃。

### 3. DataScopeService

新增 `DataScopeService`：

```text
SELF
DEPT_AND_CHILD
ALL
SHARED
```

查询逻辑：

- `ALL`：admin 或授权角色可见全部。
- `DEPT_AND_CHILD`：可见本部门及子部门 Owner 数据。
- `SELF`：只可见自己 Owner 的数据。
- `SHARED`：可见显式共享给自己的数据。

### 4. 共享能力

新增共享表：

```text
sys_data_share
sys_virtual_group
sys_group_member
```

共享规则：

- Owner 或有授权权限的人可以共享。
- 支持只读和可编辑。
- 禁止普通被共享人二次转授。
- 撤销共享后立即不可见。

### 5. 企微能力

新增企微同步：

```text
sys_department
sys_user.wecom_userid
dept_path
```

要求：

- 支持企微 OAuth 登录。
- 支持通讯录同步用户和部门。
- 支持禁用用户。
- 本地 admin 继续作为兜底超管。

### 6. 离职交接

禁用用户后：

- 不能登录。
- 不能访问原数据。
- admin 进入交接看板完成 owner 移交。
- 移交动作写入审计日志。
- 共享关系需要清洗或转移。

### 7. 文件权限增强与 `sys_file_auth`

**必要性**：CRM 附件、交付手册为高敏数据；文件权限不能停留在 01 的「登录即可访问」，必须与业务 Owner、`DataScope`、手册 ACL 绑定后经网关签发临时 URL。

新增显式文件鉴权表（对齐原 PDF/17c479cb 方案）：

```text
sys_file_auth
  file_id              # 主键，全局唯一
  module_type          # crm | delivery | handbook | attachment 等
  data_id              # 关联业务主键（如 client_id、handbook_id）
  owner_user_id        # 文件 Owner，可与业务 Owner 一致
  storage_key          # 相对 UPLOAD_DIR 或逻辑路径
  uploaded_by_user_id  # 上传人（审计；手册等可与业务 uploaded_by 一致）
  acl_json             # 可选；手册等部门/职级可见性快照，如 {"departments":[],"levels":[]}
  mime_type            # 可选
  created_by_user_id   # 创建记录人（可与 uploaded_by 相同）
  created_at
```

`acl_json` 用途：

- 手册（`module_type=handbook`）：上传时从 `permission_departments_json` / `permission_levels_json` 写入快照，Gatekeeper 校验时优先读 `acl_json`，避免仅联查业务表。
- 客户附件等无额外 ACL：`acl_json` 可为空，仅走 `DataScope` + `owner_user_id`。

**写入时机**：

- 客户附件、交付手册、预览 PDF 等上传成功后，同步写入 `sys_file_auth`。
- 历史文件可在迁移脚本中按 `stored_path` + 业务表回填（允许分批）。

**读取链路**：

1. `GET /api/files/{file_id}/access` 或签名 URL 入口。
2. Gatekeeper 查 `sys_file_auth` → 关联业务实体。
3. `DataScopeService` / 共享表 / `acl_json`（手册部门职级）判定当前用户是否可读。
4. 通过则签发 **HMAC Signed URL**（TTL 默认 60min）；前端可在 55min 无感续期。
5. 过期或签名无效 → 403。

**与 01 的差异**：

- 01：登录即可访问文件（无行级）。
- 03：必须满足业务数据权限 + `sys_file_auth` 记录存在。

**模块扩展**：

- 在 `auth/` 增加 `file_gatekeeper.py`（或等价模块），禁止绕过表直接 `open(UPLOAD_DIR/...)`。

本阶段可继续使用本地文件存储，不接 OSS/S3；`storage_key` 预留后续 OSS 后端字段。

### 8. 客户共享 UI（可选 P0）

- 客户详情页共享 Side Sheet（简化版）：授权对象、只读/可编辑、撤销。
- 可放在 03 末期，不阻塞 DataScope 与迁移脚本。

## 验收

1. 销售 A 看不到销售 B 的客户。
2. 主管能看到下属客户。
3. admin 能看到全部客户。
4. 客户共享给某用户后，该用户可见。
5. 撤销共享后立即不可见。
6. 禁用用户无法登录。
7. 离职交接后数据 Owner 正确转移。
8. 文件下载权限与客户权限一致；无 `sys_file_auth` 记录的文件不可通过网关访问。
9. 手册文件：`acl_json` 不满足部门/职级时，即使有登录态也 403；满足时可访问。
10. Signed URL 过期后返回 403；续期后仍可访问（权限未变前提下）。
11. 旧 `owner` 字符串字段仍保留，legacy 数据可追溯。

## Cursor 禁止事项

- 不要删除旧 Owner 字段。
- 不要把未匹配 Owner 静默归给 admin。
- 不要一次性迁移数据库类型。
- 不要接 OSS/S3。
- 不要承诺企微权限毫秒级回收。
- 不要绕过 `DataScopeService` 直接返回业务数据。
- 不要在本阶段实现 Dump/废弃池（见 04）。
