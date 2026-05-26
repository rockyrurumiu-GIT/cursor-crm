# Phase 04A 报告：前端公共 JS 工具建立

## 执行范围

### 新增文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `static/js/core/crm-api.js` | 129 | fetch 封装，自动带认证头、credentials: same-origin、统一 401/403 处理 |
| `static/js/core/crm-dom.js` | 69 | escapeHTML、setText、createElement 等 DOM 安全工具 |
| `static/js/core/crm-download.js` | 82 | blob 下载封装，自动提取 Content-Disposition 文件名 |
| `static/js/core/crm-toast.js` | 113 | 轻量 toast 提示，无外部 UI 库依赖 |
| **合计** | **393** | |

### 明确未改动

- 所有 `.html` 模板 — 不动
- `delivery_detail.html` — 不动
- `delivery_settlement.html` — 不动
- 后端 Python 代码 — 不动
- 不引入 npm / Vite / Webpack

## 设计要点

### crm-api.js

- 复用现有 `window.crmAuthHeader()` 机制（定义在 `base.html`）
- 默认 `credentials: "same-origin"` 支持 cookie session
- JSON POST/PUT 自动加 `Content-Type: application/json`
- FormData 上传通过 `postForm()` 不设 Content-Type（让浏览器处理 boundary）
- 401 → 抛出"认证失败，请重新登录"
- 403 → 抛出"无权限"
- 暴露为 `window.crmApi.{get, post, put, del, postForm}`

### crm-dom.js

- `escapeHTML()` 防 XSS
- `setText()` 安全替代 innerHTML
- `createElement()` 便捷构建 DOM 节点
- 暴露为 `window.crmDom.{escapeHTML, setText, createElement}`

### crm-download.js

- 支持从 Content-Disposition 和 URL 推断文件名
- 通过创建隐藏 `<a>` 标签触发下载
- 401/403 同样明确报错
- 暴露为 `window.crmDownload.download(url, filename, opts)`

### crm-toast.js

- 纯 CSS-in-JS，无需额外样式文件
- 4 种类型：success / error / warning / info
- 默认 3 秒自动消失，支持手动 dismiss
- 暴露为 `window.crmToast.{show, success, error, warning, info, dismiss}`

## 自动化验证

| 检查项 | 结果 |
|--------|------|
| `scripts/check_file_sizes.py` | PASS（4 个新文件均 < 1200 行） |
| `pytest tests/ -q` | **59 passed, 62 warnings** |

## 后续集成（25B）

25A 产出的工具库当前未被任何页面引用。25B 将：

1. 在 `delivery_settlement.html` 的 `<head>` 引入 4 个 core JS
2. 将页面内 inline `fetch` 调用替换为 `crmApi.get/post/postForm`
3. 将 blob 下载替换为 `crmDownload.download`
4. 将成功/失败提示替换为 `crmToast.success/error`
5. 外置业务逻辑到 `static/js/pages/delivery-settlement.js`

## 结论

**PASS**
