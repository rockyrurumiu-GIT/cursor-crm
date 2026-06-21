# UI 视觉重构参数字典 · 深色侧栏导航（图1）

```css
/* ============================================================
   UI 视觉重构参数字典 · 深色侧栏导航 / Dark Sidebar Nav（图1）
   说明：深藏青底、青绿(teal)点睛、浅色多级文字；左侧 3px teal 高亮条
   ============================================================ */
:root {

  /* ---------- 1. 色彩系统 Color Palette ---------- */
  --color-bg-base:        #0C2230;   /* 主背景：深藏青（侧栏底） */
  --color-bg-subtle:      #0F2A3A;   /* 次级面：hover 底（比底色略亮，推断） */
  --color-card-bg:        #0C2230;   /* 容器背景：同主背景 */

  --color-text-primary:   #FFFFFF;   /* 主文本 / 选中项文字（纯白） */
  --color-text-secondary: #D6DEE3;   /* 次文本：常规导航项文字 */
  --color-text-muted:     #9FB0B9;   /* 弱化文本：分组/说明 */
  --color-text-faint:     #6E828D;   /* 更弱：占位/编号 */
  --color-text-disabled:  #566A75;   /* 禁用文本 */
  --color-chevron:        #7C8E99;   /* 折叠箭头 / 次级图标 */

  --color-accent:         #22D3A6;   /* 点睛：青绿（图标、激活高亮条） */
  --color-accent-hover:   #1FBF96;   /* hover 加深约 8%（推断） */
  --color-accent-active:  #1AA983;   /* active 再加深（推断） */

  /* 选中项背景：teal 向右渐隐 + 左侧实心高亮条 */
  --nav-active-bg:        linear-gradient(90deg, rgba(34, 211, 166, 0.14) 0%, rgba(34, 211, 166, 0.04) 100%);
  --nav-active-rail:      inset 3px 0 0 0 #22D3A6;   /* 左侧 3px teal 竖条 */

  /* hover（非选中）底色：白色极低透明叠加 */
  --nav-hover-bg:         rgba(255, 255, 255, 0.06);

  /* ---------- 2. 几何参数 Geometry（圆角） ---------- */
  --radius-item:          10px;      /* 导航项 / 选中胶囊圆角 */
  --radius-control:       8px;       /* 按钮 / 输入 */
  --radius-icon:          6px;       /* 图标按钮 */

  /* ---------- 3. 空间韵律 Spacing Rhythm（4px 栅格） ---------- */
  --space-unit:           4px;       /* 基础单位 */
  --sidebar-padding:      24px 16px; /* 侧栏内边距（上下 24 / 左右 16） */
  --nav-item-height:      44px;      /* 导航项高度 */
  --nav-item-gap:         4px;       /* 项与项间距 */
  --nav-icon-gap:         12px;      /* 图标 → 文字间距 */
  --nav-icon-size:        20px;      /* 行图标尺寸 */

  /* ---------- 4. 阴影公式 Box Shadows（深底用更深的墨，非纯黑） ---------- */
  --shadow-overlay:
      0 12px 32px rgba(2, 8, 16, 0.45),
      0 2px 8px rgba(2, 8, 16, 0.30);   /* 深底浮层/抽屉阴影 */
  --shadow-drawer:        0 20px 48px rgba(2, 8, 16, 0.50);

  /* ---------- 5. 边框美学 Borders ---------- */
  --border-width:         1px;
  --border-divider:       rgba(255, 255, 255, 0.07);  /* 分割线（深底上的淡白细线） */
  --border-control:       rgba(255, 255, 255, 0.12);  /* 控件描边 */
}
```

## 测算判断（推断 / 不确定项）

- 数值以本系统现有「深色侧栏」token 为权威来源（截图为小裁切，仅含导航项），故 `--color-bg-base #0C2230`、`--color-text-secondary #D6DEE3`、`--color-accent #22D3A6` 为实测对齐值。
- `--color-bg-subtle #0F2A3A`、`--nav-hover-bg`：截图未直接呈现 hover 态，依据深底常用做法（底色略提亮 / 白色低透明叠加）推断。
- `--color-accent-hover / active`：图中无 hover/active 态，按明度递减约 8% 推算。
- 选中项视觉 = `--nav-active-bg`（teal 横向渐隐）+ `--nav-active-rail`（左侧 3px teal 竖条），非整块描边卡片。
- 阴影针对**深色背景**给出（墨色用接近黑的 `rgba(2,8,16,…)`、较高透明度），与浅色字典的 `rgba(16,24,40,0.04–0.08)` 不同，请勿混用。
- 此字典描述的是「深色侧栏/导航」语义；若要套到浅底表格表头，需要做明暗反相映射（深底→浅底、浅字→深字），不建议直接搬。
