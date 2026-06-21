# UI 视觉重构参数字典 · AI Governance 数据表

```css
/* ============================================================
   UI 视觉重构参数字典 · AI Governance 浅色数据表风格
   说明：16px 基准、4px 栅格；描边优先、阴影克制、点睛色为 teal
   ============================================================ */
:root {

  /* ---------- 1. 色彩系统 Color Palette ---------- */
  --color-bg-base:        #FFFFFF;   /* 主背景（页面）：纯白 */
  --color-bg-subtle:      #F9FAFB;   /* 次级面：表头行 / 行 hover 底色 */
  --color-card-bg:        #FFFFFF;   /* 卡片 / 表格容器背景 */

  --color-text-primary:   #1A1D1F;   /* 主文本：标题、单元格主值（近黑） */
  --color-text-secondary: #6B7280;   /* 次文本：列头、Source/Type 等元信息 */
  --color-text-muted:     #9AA0A6;   /* 弱化文本：分页、占位 */
  --color-text-disabled:  #C2C6CC;   /* 禁用文本 */

  --color-accent:         #16A39A;   /* 点睛：激活 Tab 下划线 / 链接（teal，推断） */
  --color-accent-hover:   #11827B;   /* hover 加深约 12% */
  --color-accent-active:  #0E6E68;

  /* ---------- 2. 状态徽章 Status Badges（浅底+深字+同色描边+实心圆点） ---------- */
  /* Limited（琥珀/黄） */
  --badge-warn-bg:        #FFF6E5;
  --badge-warn-text:      #B45309;
  --badge-warn-border:    #FCE4B6;
  --badge-warn-dot:       #F59E0B;

  /* High（红/粉） */
  --badge-danger-bg:      #FEECEC;
  --badge-danger-text:    #B42318;
  --badge-danger-border:  #FAC5C2;
  --badge-danger-dot:     #F04438;

  /* ---------- 3. 几何参数 Geometry（圆角） ---------- */
  --radius-card:          8px;       /* 外层表格 / 卡片容器 */
  --radius-control:       6px;       /* 按钮（Import）、输入框 */
  --radius-badge:         6px;       /* 状态标签（圆角矩形，非全 pill） */
  --radius-checkbox:      4px;       /* 行首复选框 */

  /* ---------- 4. 空间韵律 Spacing Rhythm（4px 栅格） ---------- */
  --space-unit:           4px;       /* 基础单位 */
  --space-xs:             8px;
  --space-sm:             12px;
  --space-md:             16px;      /* 标准基数：单元格水平内边距 / 模块间距 */
  --space-lg:             24px;
  --space-xl:             32px;

  --cell-padding-x:       16px;      /* 单元格左右内边距 */
  --cell-padding-y:       18px;      /* 单元格上下内边距 */
  --row-height:           56px;      /* 数据行行高（含内边距，约 56–64px） */
  --gap-title-tabs:       16px;      /* 标题 → Tab 栏 */
  --gap-tabs-table:       16px;      /* Tab 栏 → 表格 */
  --gap-table-pager:      20px;      /* 表格 → 分页 */

  /* ---------- 5. 阴影公式 Box Shadows（带环境色，非纯黑） ---------- */
  --shadow-card:
      0 1px 2px rgba(16, 24, 40, 0.04),
      0 1px 3px rgba(16, 24, 40, 0.06);
  --shadow-overlay:
      0 8px 24px rgba(16, 24, 40, 0.08),
      0 2px 6px rgba(16, 24, 40, 0.05);

  /* ---------- 6. 边框美学 Borders ---------- */
  --border-width:         1px;
  --border-default:       #E5E7EB;   /* 表格外框 / 列头分隔 */
  --border-divider:       #EEF0F2;   /* 行与行之间的分割线（更浅） */
  --border-control:       #D7DBE0;   /* 按钮 / 输入框描边 */
}
```

## 测算判断（推断 / 不确定项）

- `--color-accent`（teal `#16A39A`）：图中没有实心主按钮，点睛色依据激活 Tab 下划线/链接推断；其 hover/active 为按明度推算值。若有品牌主色请替换这一组。
- 整体视觉重量靠 `1px` 描边 + 浅底分层（白 `#FFFFFF` ↔ 表头 `#F9FAFB`）撑起，阴影极克制，故卡片阴影压到 `0.04–0.06` 低透明度，且用蓝灰 `rgba(16,24,40,…)` 而非纯黑。
- 徽章为「圆角矩形 + 前置实心圆点」，圆角约 `6px`，非全椭圆 pill。
- 行高 `56px` 为含内边距估算，实际区间约 `56–64px`。
