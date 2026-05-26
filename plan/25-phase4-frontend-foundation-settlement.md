# 25 Phase 4：前端公共工具和 Settlement 页面 JS 外置

## Summary

本阶段只做前端低风险拆分：建立公共 JS 工具，并先拆 `delivery_settlement.html`。不要碰 `delivery_detail.html`。

原因：

- `delivery_settlement.html` 相对独立，后端已有 smoke。
- `delivery_detail.html` 是最高风险页面，必须最后按 tab 拆。
- 先建立公共 API/DOM/下载工具，可以降低后续拆大模板风险。

本阶段可以在 clients 拆分完成后执行；如果 clients 子阶段出现 `BLOCKED`，先修复 clients，不要用前端拆分掩盖后端问题。

## Implementation Changes

### 1. 新增前端公共工具

新增：

```text
static/js/core/crm-api.js
static/js/core/crm-dom.js
static/js/core/crm-download.js
static/js/core/crm-toast.js
```

第一版要求：

`crm-api.js`：

- 包装 `fetch`。
- 默认带 `window.crmAuthHeader()`。
- 默认 `credentials: 'same-origin'`。
- JSON 请求自动加 `Content-Type`。
- 401/403 返回明确错误。

`crm-dom.js`：

- 提供 `escapeHTML`。
- 提供安全设置 text 的 helper。
- 尽量减少未转义 `innerHTML`。

`crm-download.js`：

- 统一 blob 下载。
- 保留原导出文件名逻辑，不改后端。

`crm-toast.js`：

- 先做轻量提示。
- 不引入新的 UI 库。

### 2. 外置 settlement 页面 JS

新增：

```text
static/js/pages/delivery-settlement.js
```

从：

```text
templates/pages/delivery_settlement.html
```

迁移：

```text
列表加载
新增/编辑/删除
导入
导出
日志
恢复
表格渲染
弹窗交互
```

模板保留：

- HTML 结构。
- Vue CDN script。
- 必要容器。
- 少量 `window.__CRM_DELIVERY_SETTLEMENT__` 初始化对象。
- 外部 script 引用。

### 3. 不做的事

本阶段不要做：

- 不拆 `delivery_detail.html`。
- 不拆 roster、pipeline、interviews、handbook 页面 JS。
- 不拆 `base.html` 的全部脚本。
- 不替换所有页面 fetch。
- 不引入 Vite/Webpack/npm 构建链。
- 不改后端 API。

## Validation Tests

### 自动化测试

执行：

```text
./venv/bin/python -m pytest tests/test_smoke_settlement.py -q
./venv/bin/python -m pytest tests/test_rbac_api_modules.py -q
./venv/bin/python -m pytest tests/ -q
```

如果已有架构脚本：

```text
./venv/bin/python scripts/check_file_sizes.py
```

验收：

- 后端 settlement 测试仍通过。
- `delivery_settlement.html` 行数下降。
- 新增 JS 文件不超过 1200 行；超过则拆成更小模块。

### 手动验证

必须手动点测：

```text
1. 打开 /delivery/settlement
2. 浏览器 Console 无 JS error
3. 列表加载
4. 新增
5. 编辑
6. 删除
7. 导入
8. 导出
9. 查看日志
10. 恢复 latest backup
11. 无权限用户进入时 API 返回 403，页面提示合理
```

### 测试报告

生成：

```text
reports/architecture/phase-04-frontend-settlement-report.md
```

报告必须包含：

- `delivery_settlement.html` 拆分前后行数。
- 新增 JS 文件行数。
- Console 是否有错误。
- 11 项手动验证结果。
- 失败项修复建议。

## Common Failures And Fixes

### 页面空白

修复：

- 检查 script 加载顺序。
- 确认 Vue CDN 仍在页面 JS 之前加载。
- 确认挂载元素 id 没变。

### 按钮无反应

修复：

- 检查事件绑定是否在 DOM ready 或 Vue mounted 后执行。
- 检查函数是否还挂在 Vue methods 或正确作用域。

### 导出失败

修复：

- 检查 `crm-download.js` 是否正确处理 blob。
- 检查是否仍带 `window.crmAuthHeader()`。

### 403 没提示

修复：

- 在 `crm-api.js` 中统一捕获 403。
- 页面 catch 后展示明确提示，不要吞错误。
