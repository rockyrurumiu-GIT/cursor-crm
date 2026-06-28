# 系统页面通用规范

> 与 `.cursor/rules/page-conventions.mdc` 内容同步，便于在对话里 `@docs/page-conventions.md` 引用。编辑 UI 规范时两处请保持一致。

新建或改造「列表 / 表格页」时统一遵循以下规范。基准实现：`templates/pages/customers.html`（+ 其 JS）。
说明：下文「表单」指数据列表/表格页；新增/编辑弹窗内的控件沿用既有 `crm-form-control` 样式。

## 1. 顶栏 / 工具条
- 页头只放标题（+ 次要说明），不放动作按钮。
- 所有控件集中到标题下方的「工具条卡片」一行：`rounded-lg border border-[#E5E7EB] bg-white p-2.5 shadow-[0_1px_2px_rgba(16,24,40,0.04)]`。
- 行内顺序：模糊查询框 → `筛选`按钮 →（`ml-auto`）合计条数 → 右侧图标按钮组。

## 2. 模糊查询（默认必备）
搜索框始终可见、带放大镜图标：
```html
<div class="relative w-full sm:w-[280px]">
  <svg ... class="pointer-events-none absolute left-3 top-1/2 h-[18px] w-[18px] -translate-y-1/2 text-[#9AA0A6]">...</svg>
  <input v-model.trim="filterKeyword" type="search" placeholder="搜索…"
    class="h-9 w-full rounded-[6px] border border-[#D7DBE0] pl-9 pr-3 text-sm focus:outline-none focus:border-[#16A39A] focus:ring-2 focus:ring-[#16A39A]/30" />
</div>
```

## 3. `筛选`按钮 = 折叠器
`筛选`按钮只用于展开/收起高级筛选面板（`filterPanelExpanded`），不承载查询本身。激活态描边/文字 teal `#16A39A`，默认 `#D7DBE0`；展开面板在同卡片内，`border-t border-[#EEF0F2] pt-2.5`。

## 4. 右上角动作 → 同一行图标按钮
页面右上若有动作按钮，一律移入工具条同一行（合计条数之后），统一为 `h-9 w-9 rounded-[6px]` 图标按钮，并带悬停提示（`group` tooltip，见 customers.html）。配色：
- 主操作（新增）：`bg-[#456595] text-white`
- 中性：`border-[#D7DBE0] text-[#5B5F6E] hover:bg-[#F9FAFB] hover:text-[#1A1D1F]`
- 警示 / 危险：amber / red 描边

## 5. 表格样式
沿用客户列表：根容器加 `crm-skin`，表格用 `crm-table`；姓名/主键列加 `crm-name-link`（主蓝加粗）。

## 6. 操作列统一图标
操作列用图标按钮（非文字）：`crm-op-btn-edit` / `crm-op-btn-delete` + 内联 SVG，配 `aria-label`。
**不要用原生 `title`**，统一用第 8 节的深色 `group` 悬停说明（原生 title 样式不可控且与规范不符）：
```html
<div class="crm-op-actions">
  <span class="group relative inline-flex">
    <button class="crm-op-btn-edit" @click="..." aria-label="修改"><svg .../></button>
    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#1A1D1F] px-2 py-1 text-xs text-white opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100">修改</span>
  </span>
  <span class="group relative inline-flex">
    <button class="crm-op-btn-delete" @click="..." aria-label="删除"><svg .../></button>
    <span class="pointer-events-none absolute left-1/2 top-full z-50 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-[#1A1D1F] px-2 py-1 text-xs text-white opacity-0 shadow-sm transition-opacity duration-150 group-hover:opacity-100">删除</span>
  </span>
</div>
```
注意：若数据行 `<tr>` 自带 `group` 类，会让整行 hover 触发全部按钮提示——此时去掉 `<tr>` 上多余的 `group`（行底色用直接 `hover:` 而非 `group-hover:`）。
删除二次确认在页面内自行调用 `window.crmConfirmDeleteDialog`（图标无「删除」文案，全局文案兜底不再触发）。

## 7. 分页（每页 10 条）
表格页每页最多 10 条，底部分页沿用客户列表（见 customers.html 662–676）：
- 逻辑：`pageSize=10`，配 `currentPage` / `totalPages` / `pagedRows` / `pageNumbers` / `goPage`；筛选变化时 `currentPage=1`。
- UI：左「共 N 条，第 X / Y 页」；右 `上一页` / 页码（当前页 `bg-[#456595] text-white`）/ `下一页` / 「10 条 / 页」。
- 空数据时隐藏分页（`v-if="filteredRows.length"`）。
- 底部留白：在 `flex-1` 撑满布局里别靠容器 padding（会被撑满吃掉），把留白加在**分页行本身**上（如 `px-1 pt-3 pb-4`）。

## 8. z-index 层级 / 防遮挡规范（重要）
悬停说明（tooltip）、弹窗等被遮挡反复发生，根因是层级没对齐。新增浮层一律按下表取值，**宁可高一档也不要低于所在容器**：

| 层 | z-index | 说明 |
| --- | --- | --- |
| 普通表格单元格 | 0–8 | 冻结左列 1–2、冻结操作列 tbody=8 |
| 悬停行的冻结操作列 | 20 | 全局已配（base.html），保证操作按钮 tooltip 浮在下一行之上 |
| 冻结表头 thead | 28–32 | sticky 顶部表头 / 右侧操作列表头 |
| 侧边栏 `.bms-sidebar` | 120 | sticky，**任何弹窗/浮层必须高于它** |
| 右侧抽屉 | 150–160 | `.crm-right-drawer` |
| 弹窗 / 遮罩 overlay | **≥ 200** | 全屏 `fixed inset-0` 弹窗统一用 `z-[200]`（对齐 customers `cp-modal`） |

落地要点：
- **工具条/操作按钮的 tooltip**：用 `top-full z-50`（高于冻结表头 32 即可），不要用 `z-30`（会被表头盖住）。
- **冻结操作列里的 tooltip**：所在单元格须 `overflow: visible`（见 roster_detail.html 对 `td.crm-sticky-right-op` 的覆盖），否则向下弹出的提示会被单元格裁掉；行 hover 抬层级已在 base.html 全局处理。
- **任何全屏弹窗**：`z-[200]`，否则会被侧边栏（120）/抽屉遮挡。切忌沿用 `z-50`。

## 9. 表头字段图标（必备）
表格每个列头文字前都要前置一枚图标（对齐客户列表 customers.html 591–603）：
- 写法：列头文字前放 `<svg class="ct-th-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="…"/></svg>` + 文字。
- 样式：`.ct-th-icon` 几何样式已在 base.html 全局定义（14×14、`margin-right:6px`、`vertical-align:middle`），**新页面无需再写**；颜色用 `currentColor` 继承表头文字色（默认蓝底白字，浅色重构表头如客户列表则在页面内覆盖为 teal `#16A39A`）。
- 选图：按字段语义选最贴切的线性图标（人/日历/货币/百分号/地点/链接/齿轮…），同义字段可复用同一路径；务必给 `aria-hidden="true"`。
- 包含序号、操作等所有列；操作列用齿轮图标。

## 10. 详情页（无顶栏 flat 模式，基准：delivery_detail.html「员工访谈」模块）
「客户详情 / 子模块详情」页在遵循 1–9 的基础上，额外遵循以下几条（员工访谈模块为标准实现）：

### 10.1 无顶栏（flat）+ 顶部留白
- 详情页用 flat 壳，让顶栏（用户菜单/通知）浮到右上角、页面标题升到首行（与列表页一致的观感）：
  `{% block shell_extra_class %}bms-shell-flat{% endblock %}`（可按 `module_key` 条件启用；仅 ≥1025px 生效，窄屏自动回退普通顶栏 + 汉堡）。
- 标题平铺在内容区左上：`text-2xl font-bold`，可接 `· 子模块` 次级灰字与「负责人 X」副标题，**不要再包进白卡片**。
- **顶部留白要点（易踩坑）**：详情主区是 `flex-1 min-h-0 flex flex-col` 撑满视口的布局，容器自身的 `pt-*/py-*` 内边距常被 flex 撑满“吃掉”、不产生可见留白。顶部留白请加在**标题块**上（如 `mt-8`），不要指望容器 padding。

### 10.2 返回按钮位置
返回按钮放在工具条**最前面**（模糊查询框之前），样式同中性图标按钮（`h-9 w-9 rounded-[6px]` 描边 + `group` 深色 tooltip），**不要**单独丢在页头。

### 10.3 表头皮肤：浅 / 深色都要对
表格所在容器加 `crm-skin`（不要手写深蓝表头覆盖）。`crm-skin` 会自动给：
- 浅色主题：`#F9FAFB` 底 / `#6B7280` 字 / teal `#16A39A` 列头图标 / 仅横向行线（无竖线、去斑马）。
- 深色侧栏：自动转钢蓝 `#3B6699` 白字。
常见错误：只写了 `#main-shell.bms-sidebar-dark …` 的深蓝覆盖，漏了浅色态 → 浅色主题下表头退回默认深蓝。加 `crm-skin` 即可两态都对。

### 10.4 详情走右侧抽屉（不放操作列）
点击姓名/主键（`crm-name-link`，主蓝加粗）打开右侧抽屉看详情（`crm-right-drawer` + 半透明遮罩 `crm-right-drawer-backdrop`），操作列只保留 修改 / 删除，**不放「详情」按钮**。抽屉/遮罩层级见第 8 节（必须高于侧栏 120）。

### 10.5 新增/编辑弹窗防遮挡
详情页内的全屏弹窗（新增/修改表单）overlay 用 `z-[200]`（见第 8 节），切勿沿用 `z-50` —— 否则会被侧边栏（120）盖住左半边。
