# 04 - CRM 废弃池与 Dump 生命周期

> 执行文档。全局设计见 `00-rbac-master-plan.md`（仅上下文，不直接执行）。

## 目标

在 `03-data-scope-wecom-sharing.md` 完成后，补齐原 PDF/17c479cb 方案中的 **废弃池（Dump）** 能力：

- 离职/交接后的数据打包登记。
- 超管恢复与销毁。
- 180 天生命周期元数据管理。
- 特权操作写入 `sys_audit_log`。

本阶段不阻塞 01–03 主链路；可在数据权限与交接稳定后再做。

## 前置依赖

- 已完成 `02`：本地 RBAC、`sys_audit_log`、`SUPER_ADMIN`。
- 已完成 `03`：用户禁用、离职交接、`owner_user_id` 移交流程。
- `CRM_AUTH_MODE=rbac` 可在本阶段验收环境启用。

## 不做

- 不接 OSS/S3 存储 Dump 包（首期本地目录或 DB 元数据 + 文件路径）。
- 不做企微卡片/H5 解除清单（可用站内通知替代）。
- 不自动物理删除业务表行（销毁指 Dump 包与登记记录，业务数据销毁需显式确认）。
- 不替代 03 的交接看板；Dump 是交接完成后的归档与合规留存层。

## 预期结果

- 超管可将指定用户/客户相关数据登记为 Dump 条目。
- Dump 条目有状态：`active`（可恢复）、`expired`（超 180 天）、`destroyed`（已销毁）。
- 超管可从 Dump **恢复**到业务库（在权限与 Owner 规则允许下）。
- 超管可 **销毁** Dump 包（元数据 + 本地归档文件）。
- 所有恢复/销毁/登记操作写入 `sys_audit_log`，且仅 `SUPER_ADMIN` 或 `system.dump.manage` 可执行。

## 建议表结构

```text
sys_dump_registry
  dump_id            # 主键
  source_user_id     # 离职/禁用用户（可空）
  source_client_id   # 关联客户（可空）
  module_type        # crm | delivery | mixed
  status             # active | expired | destroyed
  storage_path       # 本地归档路径或打包文件相对路径
  payload_meta_json  # 包含范围摘要：客户数、文件数、时间范围等
  created_by_user_id
  created_at
  expires_at         # 默认 created_at + 180 天
  destroyed_at       # 可空
  destroyed_by_user_id
  notes              # 可选备注
```

**权限码**（若 02 未预置，本阶段补充 seed）：

```text
system.dump.manage
system.dump.restore
system.dump.destroy
```

## 关键改动

### 1. Dump 登记

- 入口：超管「废弃池 / Dump 中心」或交接结案后的「登记 Dump」动作。
- 登记内容：打包元数据 + 可选本地 zip/目录快照（客户、附件索引、关键业务 ID 列表）。
- 登记后业务数据是否保留：由产品规则决定——建议 **交接完成后业务 Owner 已转移，Dump 为归档副本**，不默认删除在线业务数据。

### 2. 恢复

- 仅 `SUPER_ADMIN` / `system.dump.restore` 可操作。
- 恢复前校验：目标 Owner 用户存在且有效；避免覆盖现有活跃数据（冲突时提示或合并策略写死为「拒绝覆盖」）。
- 恢复完成写 `sys_audit_log`：操作人、dump_id、恢复范围摘要。

### 3. 销毁

- 仅 `SUPER_ADMIN` / `system.dump.destroy` 可操作。
- 二次确认（UI 或 API 要求 confirm token）。
- 删除/清理 `storage_path` 归档文件；`sys_dump_registry.status = destroyed`，记录 `destroyed_at` / `destroyed_by_user_id`。
- 写 `sys_audit_log`。

### 4. 180 天生命周期

- 定时任务或启动时扫描：将 `expires_at < now` 且 `status = active` 的条目标为 `expired`。
- `expired` 仍可恢复（可配置）；超期 N 天后自动销毁可列为 **后续增强**，首期仅标记过期 + 超管手动销毁。
- 列表 UI 展示：剩余天数、状态、来源用户/客户。

### 5. 通知

- 首期：**站内通知**（复用现有 `CrmNotification` 或简单 admin 待办列表）。
- 企微卡片通知：明确推迟，不写进本阶段验收。

### 6. 模块位置

```text
auth/
  dump.py              # 登记、恢复、销毁、过期扫描
auth_routes.py         # /api/admin/dump/* 或并入 admin 路由
templates/pages/dump_center.html   # 超管 Dump 中心（简化版）
```

## 验收

1. 超管可登记一条 Dump，`sys_dump_registry` 有记录且 `status=active`。
2. 列表可查看 Dump 状态、过期时间、来源用户/客户摘要。
3. 超管执行恢复后，指定范围内业务数据可按规则重新可见（或恢复到待认领状态）。
4. 超管执行销毁后，归档文件不可再访问，`status=destroyed`。
5. 登记、恢复、销毁均写入 `sys_audit_log`，普通用户无 `system.dump.*` 权限时 API 返回 403。
6. `expires_at` 到期后条目变为 `expired`（扫描或手动触发均可验收）。
7. 01–03 已有功能（登录、RBAC、行级隔离、交接）回归通过。

## Cursor 禁止事项

- 不要在没有审计日志的情况下执行恢复/销毁。
- 不要让非超管用户销毁或恢复 Dump。
- 不要在 04 引入行级规则变更（Owner 规则以 03 为准）。
- 不要默认静默删除在线业务数据。
- 不要接 OSS/S3 作为 04 的前置条件。
