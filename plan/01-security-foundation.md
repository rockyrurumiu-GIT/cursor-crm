# 01 - CRM 安全底座

> 执行文档。全局设计见 `00-rbac-master-plan.md`（仅上下文，不直接执行）。

## 目标

保留当前单管理员开发体验，同时修复明显安全风险，为后续 RBAC 做准备。

本阶段是安全底座，不是完整权限系统。

## 不做

- 不做多用户管理。
- 不做角色管理。
- 不做菜单权限。
- 不做行级数据隔离。
- 不接企微。
- 不重构全部路由。
- 不做完整 HttpOnly Cookie session（留给 02）。

## 预期结果

开发环境仍可通过以下方式登录：

```bash
CRM_AUTH_MODE=legacy
CRM_ALLOW_DEFAULT_ADMIN=1
```

账号：

```text
admin / admin123
```

正式环境必须设置：

```bash
CRM_ADMIN_USERNAME=admin
CRM_ADMIN_PASSWORD=<strong-password>
```

未设置强密码时，正式环境不得启用默认 `admin/admin123`。

## 工程基线（本阶段，详见 [engineering-baseline.md](engineering-baseline.md)）

### A. 结算 API 路径统一（优先，不等 RBAC）

- 修复 [delivery_detail.html](templates/pages/delivery_detail.html) 与后端不一致：统一为 `/api/delivery/settlement/row/{id}`，或后端补 alias（见 engineering-baseline §1）。
- 验收：结算页 + 客户交付详情内嵌结算的创建、编辑、删除均可用。

### B. smoke tests 首期

- 新增 `tests/`：`pytest` + TestClient。
- 至少覆盖：admin 登录、`/api/files/access` 未登录 401、结算 CRUD、（若已有）`CRM_AUTH_MODE=legacy` 冒烟。
- 本阶段末：`pytest tests/ -q` 通过后再进入 02。

## 关键改动

### 1. 默认密码策略

- 增加 `CRM_ALLOW_DEFAULT_ADMIN` 开关。
- 只有 `CRM_ALLOW_DEFAULT_ADMIN=1` 时允许默认 `admin/admin123`。
- 非开发模式下，如果没有配置 `CRM_ADMIN_PASSWORD` 或本地凭据文件，应拒绝使用默认弱密码。
- 不要删除现有 `.crm_admin_credentials.json` 逻辑。

### 2. 启动日志安全

- 禁止启动日志打印明文密码。
- 可以打印管理员用户名。
- 可以提示当前处于开发默认密码模式，但不要输出密码内容。

### 3. 文件访问安全

- 移除或限制 `/previews` 对 `uploads` 的公开裸露访问。
- 新增受认证保护的文件访问接口，例如：
  - `/api/files/{file_id}/download`
  - 或 `/api/files/access?...`
- 文件接口必须复用当前登录认证。
- 本阶段可以先做到“登录用户才可访问文件”，不要求完整行级文件权限。

### 4. 上传路径安全

修复上传文件路径风险：

- 不直接拼接 `file.filename`。
- 使用安全文件名或 UUID 存储名。
- 先校验客户存在，再生成客户目录。
- 保留文件大小限制。
- 写入前确认最终路径仍在 `UPLOAD_DIR` 下。
- 对路径穿越、空文件名、奇怪扩展名做最小防护。

### 5. HTML 页面最小服务端保护

本阶段不做完整 RBAC session，但要堵住「直接打开 URL 即可看到页面壳」的漏洞。

**目标**：未登录用户不能访问业务 HTML 页面；API 与文件鉴权仍按本阶段现有机制。

**最小实现**（任选一种，优先 Middleware）：

1. **页面保护中间件**（推荐）
   - 对 `GET` 且 `Accept` 含 `text/html` 的业务路由（`/home`、`/customers`、`/delivery/*`、`/opportunity/*` 等）统一校验。
   - 未通过当前登录认证（legacy Basic 或已有 session）→ `302` 到 `/login`（或返回 401 + 简单登录页）。
   - 放行：`/static/*`、`/login`、`/api/auth/*`（若已存在）、健康检查等白名单。

2. **`_page()` 统一入口校验**（备选）
   - 所有 `_page(...)` 调用前检查 `request` 是否已认证；未认证则重定向。
   - 需确保 handoff/phase2/visit 注册的 HTML 路由也走同一入口或同等校验。

**本阶段边界**：

- 只要求「已登录才可打开页面」，不要求按角色隐藏菜单（留给 02）。
- 不要求企微 OAuth 登录页；legacy `admin` 登录即可通过校验。
- 可继续保留 `localStorage` 作为前端展示辅助，但**不得以 localStorage 作为唯一鉴权依据**。
- 登录成功后调用 `POST /api/auth/legacy-bootstrap` 写入 HttpOnly `crm_legacy` Cookie，供 HTML 中间件校验（API 仍用 Basic）。

**与 02 的分工**：

- **01**：最小保护 = 「任何人未登录不能看 HTML 壳」。
- **02**：完整保护 = HttpOnly Cookie session + 全站 HTML/API 统一会话、替换前端壳鉴权。

### 6. 保留开发体验

- 保留现有 admin 全权限行为。
- 不改变当前业务页面的主要交互。
- 不引入用户/角色 UI。

## 建议验收

1. 开发模式下 `admin/admin123` 可以登录。
2. 非开发模式下默认密码不可用。
3. 启动日志不出现明文密码。
4. 直接访问 `/previews/...` 不应绕过认证读取文件。
5. 上传附件后可以通过受认证接口访问。
6. 未登录直接访问 `/customers`、`/delivery/pipeline` 等 HTML 路由 → 重定向登录页或 401，不能看到业务页面壳。
7. 登录后上述 HTML 路由可正常打开（legacy admin 即可）。
8. 客户 CRUD、花名册导入、交接审批至少各跑通一条 happy path。
9. 结算 API 路径已统一；交付详情与结算页 CRUD 均通过。
10. `pytest tests/ -q` 通过（含结算与文件网关 smoke）。

## Cursor 禁止事项

- 不要删除 legacy auth。
- 不要做完整 RBAC。
- 不要一次性替换全库 `Depends(authenticate)`。
- 不要格式化 `main.py` 全文件。
- 不要改动 `.cursor/plans` 原始方案文件。
