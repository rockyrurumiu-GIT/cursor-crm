# Phase 04 报告：前端公共工具 + Settlement 页面 JS 外置

## 执行范围

### 25A：公共 JS 工具（新增）

| 文件 | 行数 | 职责 |
|------|------|------|
| `static/js/core/crm-api.js` | 129 | fetch 封装，带认证头 + credentials: same-origin + 401/403 统一处理 |
| `static/js/core/crm-dom.js` | 69 | escapeHTML、setText、createElement |
| `static/js/core/crm-download.js` | 82 | blob 下载，自动提取 Content-Disposition 文件名 |
| `static/js/core/crm-toast.js` | 113 | 轻量 toast 提示，无外部 UI 库 |

### 25B：Settlement 页面 JS 外置

| 文件 | 拆分前行数 | 拆分后行数 |
|------|-----------|-----------|
| `templates/pages/delivery_settlement.html` | 1140 | 434 |
| `static/js/pages/delivery-settlement.js` | — | 702 |

**模板减少：706 行（-62%）**

### 脚本加载顺序

```html
<script src="/static/js/core/crm-api.js"></script>
<script src="/static/js/core/crm-dom.js"></script>
<script src="/static/js/core/crm-download.js"></script>
<script src="/static/js/core/crm-toast.js"></script>
<script src="/static/js/pages/delivery-settlement.js"></script>
```

Vue CDN 在 `head_extra` block 中加载（line 4），先于 `page_scripts` block 执行。

### 模板保留内容

- HTML 结构（Vue 模板语法）
- Vue 3 CDN script（`head_extra` block）
- CSS 样式（`head_extra` block）
- 外部 script 引用（`page_scripts` block）

### 明确未改动

- `delivery_detail.html` — 不动
- roster / pipeline / interviews / handbook 页面 — 不动
- 后端 API — 不动
- 其他页面的 fetch 调用 — 不动
- 不引入 npm / Vite / Webpack

## 自动化验证

| # | 命令 | 结果 |
|---|------|------|
| 1 | `scripts/check_reverse_imports.py` | PASS |
| 2 | `scripts/check_route_permissions.py` | PASS（已知 WARNING: `/api/files/access`） |
| 3 | `scripts/check_file_sizes.py` | PASS（已知 WARNING: `delivery_turnover.html` 2089 行） |
| 4 | `scripts/check_architecture.py` | PASS |
| 5 | `pytest tests/test_smoke_settlement.py -q` | **2 passed** |
| 6 | `pytest tests/test_rbac_api_modules.py -q` | **9 passed** |
| 7 | `pytest tests/ -q` | **59 passed, 62 warnings** |

## 手动验证清单

以下需手动在浏览器中点测：

| # | 验证项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | 打开 /delivery/settlement | PASS | |
| 2 | Console 无 JS error | PASS | favicon 404 不属于业务 JS/API 错误，已排除 |
| 3 | 列表加载 | PASS | |
| 4 | 新增 | PASS | |
| 5 | 编辑 | PASS | |
| 6 | 删除 | PASS | |
| 7 | 导入 | PASS | |
| 8 | 导出 | PASS | |
| 9 | 查看日志 | PASS | |
| 10 | 恢复 latest backup | PASS | |
| 11 | 无权限用户 API 403，页面有合理提示 | PASS | |

## Console 错误

自动化测试无法验证浏览器 Console。需手动确认：
- Vue 挂载成功（页面非空白）
- 无 `404` 加载 JS 文件错误
- 无 `ReferenceError` / `TypeError`

## 潜在故障与修复指引

| 问题 | 修复 |
|------|------|
| 页面空白 | 确认 Vue CDN 在 page JS 之前加载；确认 `#delivery-settlement-app` 元素存在 |
| 按钮无反应 | 确认外部 JS 已被浏览器缓存清除后重新加载 |
| 导出失败 | 确认 `crmDownload.download` 正常工作；检查 `crm-download.js` 是否在 page JS 之前加载 |
| 403 无提示 | `crmApi` 统一抛错后由 `crmToast.error(e.message)` 展示"无权限 (403)" |

## 公共工具使用情况

`delivery-settlement.js` 已全面接入 Phase 04A 公共工具：

| 公共工具 | 使用场景 |
|---------|---------|
| `crmApi.get` | loadRows、openLogs |
| `crmApi.post` | saveForm（新增）、restoreLatestBackup |
| `crmApi.put` | saveForm（编辑）、fillPaymentDaysByDates |
| `crmApi.del` | removeRow |
| `crmApi.postForm` | onImportFile |
| `crmDownload.download` | exportCsv |
| `crmToast.success` | 保存/删除/导入/回滚/回款天数统计成功 |
| `crmToast.error` | 所有失败提示 |
| `crmToast.info` | 无数据提示 |

保留 `alert()` 的场景：导入跳过明细（长文本需用户逐行阅读）、回款提示文本（需展示完整内容）。
保留 `window.confirm()` / `window.prompt()`：确认对话框（浏览器原生阻塞式 confirm 无法用 toast 替代）。

## 结论

- **自动化验证：PASS**
- **浏览器验收：PASS**（11/11 项通过）

**Phase 04 PASS**
