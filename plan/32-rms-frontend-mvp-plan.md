# RMS Phase 2.5 前端 MVP 执行计划

**状态：** 已实施。

**前置：** Phase 0 权限壳、Phase 1 表、Phase 2 API（[`plan/31-rms-phase2-plan.md`](31-rms-phase2-plan.md)）。

**目标：** 将 `/rms` 从占位页升级为可用的招聘模块首页：岗位 / 候选人 / 推荐三 tab，列表、新建、推荐状态流转；仅使用现有 Phase 2 API。

**页面主说明（终态）：**

> Phase 2.5：前端 MVP 已接入。支持岗位、候选人、推荐记录与状态流转；简历、AI、面试、Offer 与入职转花名册将在后续阶段开放。

---

## 范围

| 做 | 不做 |
|----|------|
| `templates/pages/rms_index.html` + `static/js/pages/rms.js` | migration |
| 三 tab 独立 `GET` 列表 + `POST` 新建 + `POST .../status` | 改 `auth/permissions.py` / `data_scope_catalog.py` |
| JS 内 `ALLOWED_TRANSITIONS`（与 `schemas/rms.py` 同步注释） | 简历 / AI / 面试·Offer / 花名册 |
| 推荐列表 `#job_id` / `#candidate_id` 降级 | 客户/用户选择器 API、前端 data scope |
| `tests/test_rms_frontend_shell.py`（4 项壳断言） | 重复 phase0 的 `/rms` 403、health 测试 |
| Vue 3 CDN（与 dashboards/handoff 同模式） | Vue 本地化、新增 CDN 库 |

---

## 约束

- **权限：** 真实边界以 API 403/404 为准；可用 `/api/me.permissions` 隐藏写按钮，禁止 JS 推断可见客户/候选人范围。
- **CDN：** 离线环境无法加载 CDN 时与现有 Vue 页相同限制；后续统一本地化。
- **Health：** `/api/rms/health` 保持 `phase: 2`（不改 2.5）。
- **路由：** `/rms` 仍 `require_permission("rms.jobs.read")`。

---

## 文件

| 文件 | 操作 |
|------|------|
| `templates/pages/rms_index.html` | 重写 |
| `static/js/pages/rms.js` | 新增 |
| `routes/rms_shell.py` | 注释更新 |
| `tests/test_rms_frontend_shell.py` | 新增 |

---

## 验收

```bash
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/test_rms_frontend_shell.py -q
./venv/bin/python -m pytest tests/test_rms_phase2_mvp.py -q
./venv/bin/python -m pytest tests/ -q
```

---

## 手动冒烟

admin 登录 `/rms`：三 tab 切换；岗位列表；候选人 403 不阻塞推荐 tab；新建与 `recommended → screening` 状态流转。
