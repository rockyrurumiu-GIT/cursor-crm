# UI 视觉重构参数字典 · 首页 Hero 落地页（GitHub 风格暗色）

```css
/* ============================================================
   UI 视觉重构参数字典 · 首页 Hero 落地页 / Dark Hero Landing
   来源：GitHub 中文首页 Hero 截图 + 本项目 home.html 实测对齐
   ============================================================ */
:root {

  /* ---------- 1. 色彩系统 Color Palette ---------- */
  --color-bg-base:        #010409;   /* 主背景：近黑墨底 */
  --color-bg-subtle:      #0d1117;   /* 次级面：顶栏/输入深底（推断） */
  --color-bg-hero-glow:   radial-gradient(
                              ellipse 130% 90% at 50% 100%,
                              rgba(124, 58, 237, 0.42) 0%,
                              rgba(37, 99, 235, 0.18) 38%,
                              transparent 62%
                            );       /* 底部紫蓝光晕层 */

  --color-card-bg:        transparent; /* Hero 无卡片容器，内容直接浮于背景 */

  --color-text-primary:   #FFFFFF;   /* 主标题 */
  --color-text-secondary: #8b949e;   /* 副标题 / 说明 */
  --color-text-muted:     #6e7681;   /* 更弱说明（推断） */
  --color-text-disabled:  #484f58;   /* 禁用 / 占位弱化 */

  --color-accent:         #238636;   /* 主按钮（GitHub 绿） */
  --color-accent-hover:   #2ea043;   /* 主按钮 hover */
  --color-accent-active:  #238636;   /* active 同底略深（推断 #1a7f37） */

  --color-ghost-text:     #FFFFFF;   /* 次按钮文字 */
  --color-ghost-border:   #30363d;   /* 次按钮描边 */
  --color-ghost-hover-bg: rgba(255, 255, 255, 0.06); /* 次按钮 hover 底 */

  --color-input-bg:       #FFFFFF;   /* 邮箱输入（截图：浅底高对比） */
  --color-input-text:     #1f2328;   /* 输入文字（推断） */
  --color-input-placeholder: #656d76; /* placeholder */
  --color-input-border:   #d0d7de;   /* 输入默认边（推断） */
  --color-input-focus:    #58a6ff;   /* focus 环 / 边框高亮 */
  --color-input-focus-ring: rgba(88, 166, 255, 0.35);

  --color-star-dot:       rgba(255, 255, 255, 0.35); /* 背景星点 */
  --color-mascot-glow-purple: rgba(216, 180, 254, 0.50);
  --color-mascot-glow-cyan:   rgba(56, 189, 248, 0.28);
  --color-mascot-glow-pink:   rgba(244, 114, 182, 0.22);

  /* ---------- 2. 状态徽章 Status Badges ---------- */
  /* 截图无状态徽章，本页不适用 */

  /* ---------- 3. 几何参数 Geometry（圆角） ---------- */
  --radius-hero-control:  6px;       /* 按钮 / 输入 rounded-md */
  --radius-hero-pill:     9999px;    /* 若改为胶囊 CTA 时使用 */
  --radius-kbd-hint:      4px;       /* 搜索框 "/" 快捷键徽标 */

  /* ---------- 4. 空间韵律 Spacing Rhythm（4px 栅格） ---------- */
  --space-unit:           4px;
  --space-md:             16px;      /* 标题 → 副标题间距基数 */
  --space-lg:             24px;
  --gap-headline-sub:     16px;      /* mb-4；md: 20px mb-5 */
  --gap-sub-actions:      36px;      /* mb-9；md: 40px mb-10 */
  --gap-action-row:       12px;      /* 按钮组 gap-3；sm: 16px gap-4 */
  --hero-padding-x:       16px;      /* px-4；sm: 24px */
  --hero-padding-top:     48px;      /* pt-12；md: 80px；lg: 96px */
  --hero-padding-bottom:  160px;    /* 为底部 mascot 留空 pb-40+ */
  --hero-max-width:       1100px;    /* 内容区最大宽 */
  --headline-max-width:   704px;     /* max-w-[44rem] 标题行宽 */
  --sub-max-width:        672px;     /* max-w-2xl */
  --actions-max-width:    576px;     /* max-w-xl 按钮组 */
  --row-height-cta:       44px;      /* h-11；sm: 48px h-12 */
  --cta-padding-x:        24px;      /* px-6；sm: 32px px-8 */

  /* ---------- 5. 阴影公式 Box Shadows ---------- */
  --shadow-cta-primary:
      0 8px 24px rgba(35, 134, 54, 0.35);          /* 主按钮品牌绿光晕 */
  --shadow-cta-ghost:     none;                     /* 次按钮无投影 */
  --shadow-mascot:
      0 0 18px rgba(196, 181, 253, 0.35),
      0 0 28px rgba(56, 189, 248, 0.18),
      0 14px 28px rgba(0, 0, 0, 0.38);              /* 底部装饰图体积光 */
  --shadow-input-focus:   0 0 0 3px var(--color-input-focus-ring);

  /* ---------- 6. 边框美学 Borders ---------- */
  --border-width:         1px;
  --border-default:       #30363d;   /* 次按钮 / 深底控件 */
  --border-divider:       rgba(48, 54, 61, 0.65); /* 弱分割（推断） */
  --border-control:       #d0d7de;   /* 浅底输入默认边 */
  --border-ghost:         #30363d;   /* 透明次按钮描边 */

  /* ---------- 7.  typography（补充，截图可读） ---------- */
  --font-hero-headline:   ui-sans-serif, system-ui, -apple-system, "Segoe UI",
                          "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  --font-weight-headline: 400;       /* 大字常规字重，非粗黑 */
  --letter-headline:      -0.025em;
  --line-height-headline: 1.16;
  --size-headline:        clamp(2.05rem, 4vw, 3.35rem);
  --size-sub:             clamp(0.875rem, 2vw, 1.125rem);
  --size-cta:             clamp(0.875rem, 1.5vw, 1rem);
}
```

## 测算判断

- **可直接测量（截图 + 现有 `home.html`）**：主背景 `#010409`、标题白字、副标题 `#8b949e`、主按钮 `#238636` / hover `#2ea043`、次按钮 `#30363d` 描边、圆角约 **6px**、CTA 高度 **44–48px**、底部紫蓝 radial 光晕与 mascot 多层 glow。
- **截图可见、首页尚未实现**：邮箱输入 + 「注册」组合控件——输入为**浅底 `#FFFFFF`**、与绿色主按钮同排；若复刻 GitHub 原样，需单独做 `--color-input-*` 浅色系，与当前首页纯双按钮布局不同。
- **推断项（标注）**：`--color-text-muted`、`--color-accent-active`、`--color-input-border`、部分 divider 透明度——依据 GitHub Primer 邻近色推算，误差约 ±1 色阶。
- **不适用**：状态徽章四件套（Hero 页无 badge）。

如需把本字典应用到 `/home` 或合同管理等页面换皮，可说明目标页面，我再按 `reskin-ui-with-tokens` 流程落地。
