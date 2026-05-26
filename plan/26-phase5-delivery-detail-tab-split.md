# 26 Phase 5：Delivery 后端分块拆分 + Delivery Detail 按 Tab 拆分

## Summary

本阶段不是直接拆前端页面。当前最大方案缺口是 delivery 后端大块仍留在 `main.py`，而最高前端风险是：

```text
templates/pages/delivery_detail.html
```

当前该文件约 4394 行，包含大量 Vue 状态、交付管线、面试、花名册、手册、结算嵌入、PDF/媒体预览、导入导出和后台任务触发逻辑。

因此本阶段必须先按 delivery 后端子域拆分，再拆 `delivery_detail.html` 前端。禁止一开始就整页外置前端 JS。

## Preconditions

进入本阶段前必须满足：

```text
Phase 0 PASS
Phase 1 PASS
Phase 2 PASS
Phase 3 PASS
Phase 4 PASS
./venv/bin/python -m pytest tests/ -q 全绿
```

并且：

```text
static/js/core/crm-api.js 已存在
static/js/core/crm-dom.js 已存在
settlement 页面 JS 外置已验证
```

## Implementation Changes

### 0. 5A-5D 前置 API Checklist

每个 delivery 后端子阶段开始前，必须先用 `rg` 生成该子域完整 API 清单，作为迁移 checklist 写入对应报告。

推荐命令：

```text
rg -n "@app\\.(get|post|put|patch|delete).*roster|api/roster|turnover" main.py
rg -n "@app\\.(get|post|put|patch|delete).*pipeline|delivery/pipeline|insight-demand" main.py
rg -n "@app\\.(get|post|put|patch|delete).*interview|delivery/interviews|mark-employment-left" main.py
rg -n "@app\\.(get|post|put|patch|delete).*handbook|delivery/handbooks|handbook-assistant|pdf-text|pdf-page|sync-fts|reindex" main.py
```

要求：

- checklist 必须包含常规 CRUD、global import、export、logs、restore、turnover、后台任务触发接口。
- 每个 checklist 项必须标记：已迁移 / 保留在 main.py 并说明原因 / 不属于本子域。
- 如果 `rg` 发现未计划接口，必须先更新本子阶段 checklist，不允许直接忽略。

### 1. Phase 5A：拆 Delivery Roster 后端域

新增或整理：

```text
routes/delivery_roster.py
services/delivery_roster.py
schemas/delivery_roster.py
```

迁移范围：

```text
GET/POST /api/roster
GET/POST /api/clients/{client_id}/roster
PUT/DELETE /api/roster/{row_id}
roster import/export/logs/restore
roster turnover 相关 API
```

要求：

- 不迁移 pipeline、interviews、handbook。
- 保留 `delivery.roster.read/write` 权限。
- 保留数据范围过滤。
- 导入导出、backup、restore 行为不变。
- 补 1 个 roster smoke 测试，至少覆盖 list、一条 write、import confirm 路径。
- roster smoke 额外覆盖至少 1 条 turnover 路径，例如 `/api/roster/turnover` 或 `/api/roster/turnover/dashboard`。

报告：

```text
reports/architecture/phase-05a-delivery-roster-backend-report.md
```

### 2. Phase 5B：拆 Delivery Pipeline 后端域

新增或整理：

```text
routes/delivery_pipeline.py
services/delivery_pipeline.py
schemas/delivery_pipeline.py
```

迁移范围：

```text
GET/POST /api/clients/{client_id}/delivery/pipeline
PUT/DELETE /api/delivery/pipeline/row/{row_id}
pipeline import/export/logs/restore
pipeline insight / insight-demand
```

要求：

- 不迁移 interviews、handbook。
- 保留 `delivery.pipeline.read/write` 权限。
- 保留客户可见范围校验。
- import/export/restore 不改业务分支。
- 补 1 个 pipeline smoke 测试，至少覆盖 list、一条 write、import confirm 路径。

报告：

```text
reports/architecture/phase-05b-delivery-pipeline-backend-report.md
```

### 3. Phase 5C：拆 Delivery Interviews 后端域

新增或整理：

```text
routes/delivery_interviews.py
services/delivery_interviews.py
schemas/delivery_interviews.py
```

迁移范围：

```text
GET/POST /api/clients/{client_id}/delivery/interviews
PUT/DELETE /api/delivery/interviews/row/{row_id}
interviews import/export/logs/restore
mark-employment-left
```

要求：

- 保留 `delivery.interviews.read/write` 权限。
- 保留与 roster employment left 的联动行为。
- 不迁移 handbook。
- 补 1 个 interviews smoke 测试，至少覆盖 list、一条 write、import confirm 路径。

报告：

```text
reports/architecture/phase-05c-delivery-interviews-backend-report.md
```

### 4. Phase 5D：拆 Delivery Handbook 后端域

新增或整理：

```text
routes/delivery_handbook.py
services/delivery_handbook.py
schemas/delivery_handbook.py
```

迁移范围：

```text
GET/POST/PATCH/DELETE delivery handbooks
PDF text/page png
search
assistant chat
sync/reindex FTS
rebuild pdf outline
FTS schema init/helper
```

要求：

- 这是 delivery 后端最高风险子域，必须最后迁移。
- 保留 `delivery.handbook.read/write` 权限。
- 文件访问仍走安全网关，不开放裸路径。
- PDF、OCR、FTS、后台任务逻辑只做搬移，不改算法。
- 单独标记并迁移 handbook FTS 初始化与 helper，例如 `_ensure_handbook_fts_schema()`、FTS upsert/delete/query/snippet 相关 helper；不要只迁 route handler。
- 补 1 个 handbook smoke 测试，至少覆盖 list、一条 write 或上传、一个 confirm 类路径。

报告：

```text
reports/architecture/phase-05d-delivery-handbook-backend-report.md
```

### 5. Phase 5E：最后建立页面配置对象

在模板中保留少量安全初始化：

```html
<script>
  window.__CRM_DELIVERY_DETAIL__ = {
    clientId: {{ client_id }},
    moduleKey: "{{ module_key | e }}"
  };
</script>
```

不要在外置 JS 中读取 Jinja 模板变量。

### 6. Phase 5E：新增页面模块文件

按顺序新增：

```text
static/js/pages/delivery-detail.js
static/js/pages/delivery-detail-pipeline.js
static/js/pages/delivery-detail-interviews.js
static/js/pages/delivery-detail-roster.js
static/js/pages/delivery-detail-handbook.js
static/js/pages/delivery-detail-settlement.js
```

每次只启用一个模块。

### 7. Phase 5E：前端拆分顺序

严格按以下顺序：

```text
Step 1: 页面初始化、client brief、公共状态
Step 2: settlement 嵌入区域
Step 3: pipeline 区域
Step 4: interviews 区域
Step 5: roster 区域
Step 6: handbook 上传、预览、PDF、媒体、搜索
```

不要先拆 handbook，因为它涉及 PDF、媒体、FTS、后台任务，是最高风险子模块。

Step 2 额外要求：

- settlement 嵌入区域必须复用 Phase 4 已验证的 `static/js/core/crm-api.js`。
- settlement 导出或下载必须复用 Phase 4 已验证的 `static/js/core/crm-download.js`。
- 不允许在 `delivery-detail-settlement.js` 中重新实现一套 fetch/download wrapper。

### 8. 每个前端 Step 的规则

每个 Step 都必须：

- 只迁移当前 tab/区域 JS。
- 保留 HTML DOM 结构不变。
- 保留原 API URL 不变。
- 保留原权限 header。
- 保留原导入导出逻辑。
- 验证通过后再删除对应 inline JS。

### 9. 不做的事

本阶段不要做：

- Phase 5E 不改后端 API；后端 API 必须已在 5A-5D 完成或明确记录未拆。
- 不改数据库。
- 不改权限模型。
- 不重写 Vue 组件体系。
- 不引入构建工具。
- 不一次性替换所有 fetch。

## Validation Tests

### 自动化测试

5A-5D 每个后端子阶段后执行：

```text
./venv/bin/python scripts/check_reverse_imports.py
./venv/bin/python scripts/check_route_permissions.py
./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q
./venv/bin/python -m pytest tests/test_permission_datascope.py -q
./venv/bin/python -m pytest tests/test_smoke_delivery_<domain>.py -q
./venv/bin/python -m pytest tests/ -q
```

其中 `<domain>` 按子阶段替换为：

```text
roster
pipeline
interviews
handbook
```

如果测试文件尚不存在，本子阶段必须新增最小 smoke 测试。

5E 每个前端 Step 后执行：

```text
./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q
./venv/bin/python -m pytest tests/test_permission_datascope.py -q
./venv/bin/python -m pytest tests/ -q
```

如果已有文件尺寸脚本：

```text
./venv/bin/python scripts/check_file_sizes.py
```

### 手动验证

5A-5D 每个后端子阶段后必须验证对应 API 和页面仍可用。

5E 每个前端 Step 后必须打开对应页面：

```text
/delivery/{module_key}/{client_id}
```

必须验证：

```text
1. 页面不空白
2. Console 无 JS error
3. 当前 tab 可切换
4. 当前 tab 数据可加载
5. 新增/编辑/删除可用
6. 导入/导出可用
7. 日志/恢复可用
8. 403/401 有提示
```

handbook Step 额外验证：

```text
1. 上传文件
2. 预览 PDF/图片/媒体
3. PDF 文本读取
4. PDF 页面图片读取
5. 搜索
6. rebuild outline
7. reindex/sync FTS
```

### 测试报告

5A-5D 后端子阶段报告：

```text
reports/architecture/phase-05a-delivery-roster-backend-report.md
reports/architecture/phase-05b-delivery-pipeline-backend-report.md
reports/architecture/phase-05c-delivery-interviews-backend-report.md
reports/architecture/phase-05d-delivery-handbook-backend-report.md
```

5E 每个前端 Step 都生成独立报告：

```text
reports/architecture/phase-05-step-01-delivery-init-report.md
reports/architecture/phase-05-step-02-delivery-settlement-report.md
reports/architecture/phase-05-step-03-delivery-pipeline-report.md
reports/architecture/phase-05-step-04-delivery-interviews-report.md
reports/architecture/phase-05-step-05-delivery-roster-report.md
reports/architecture/phase-05-step-06-delivery-handbook-report.md
```

报告必须包含：

- API checklist，来自本阶段开始前的 `rg` 输出。
- checklist 每项迁移状态。
- 新增 smoke 测试文件和覆盖场景。
- 本 Step 拆出的函数/状态。
- 模板行数变化。
- 新 JS 文件行数。
- Console 结果。
- 手动验证结果。
- 失败项和修复方法。

## Common Failures And Fixes

### Jinja 变量 undefined

修复：

- 所有模板变量只能通过 `window.__CRM_DELIVERY_DETAIL__` 注入。
- 外置 JS 不允许直接出现 `{{ client_id }}`。

### Vue 挂载失败

修复：

- 确认 Vue CDN 在页面模块 JS 之前。
- 确认 mount selector 没变。
- 确认拆出去的方法仍在同一个 Vue app 生命周期内注册。

### Tab 白屏

修复：

- 检查当前 tab 对应状态是否初始化。
- 检查拆出的模块是否在主 app 创建前/后正确注入。
- 不要让模块各自重复创建 Vue app。

### 导入导出失败

修复：

- 检查 FormData 是否仍按原字段名提交。
- 检查导出是否仍带 auth header。
- 检查 blob 下载工具是否正确处理文件名。

### Handbook 预览失败

修复：

- 检查文件访问仍走 `/api/files/access` 或原安全网关。
- 检查 PDF page/text API URL 未改。
- 检查 Plyr 依赖加载顺序。
