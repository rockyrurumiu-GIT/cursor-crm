# 20 CRM 低风险架构拆分总方案

## Summary

本方案基于当前本地代码扫描结果、前一版 `10-13` 架构治理方案，以及 Cursor 的风险预测建议，重新整理出一套更低风险的拆分顺序。

当前基线：

```text
main.py: 7029 行
auth/data_scope.py: 258 行，存在 from main import Client
auth/service.py: 1405 行
templates/base.html: 1596 行
templates/pages/delivery_detail.html: 4394 行
templates/pages/delivery_settlement.html: 1140 行
templates/pages/roster_detail.html: 1503 行
static/js/system-permission-center.js: 739 行
当前测试基线: 59 passed, 61 warnings
```

核心判断：

- 不建议现在做大爆炸重构。
- 不建议先完整搬 `models`，因为模型、engine、migration、tests 都还围绕 `main.py`。
- 第一优先级是断开 `auth/data_scope.py -> main.py` 的反向依赖。
- 第二优先级是先加架构护栏，再拆业务域。
- 后端先拆已有 smoke 测试兜底的 `delivery.settlement`。
- `clients` 和 data scope 关系最紧，必须等反向依赖和护栏稳定后再拆，并拆成读、写、关联接口 3 个子阶段。
- `delivery` 后端大块仍留在 `main.py` 是当前方案缺口，但不能一次补完，必须在 `delivery_detail.html` 前端拆分前分块处理。
- 前端 `delivery_detail.html` 是最高风险面，必须放到最后，并且只有 delivery 后端拆分和 settlement 前端验证通过后才允许按 tab 拆。

## Files In This Plan

按以下顺序交给 Cursor 执行：

```text
21-phase0-import-boundary.md
22-phase1-guardrails-first.md
23-phase2-settlement-domain-split.md
24-phase3-clients-domain-split.md  # 内部分 24A/24B/24C
25-phase4-frontend-foundation-settlement.md
26-phase5-delivery-detail-tab-split.md  # 先 delivery 后端分块，再 delivery_detail 前端 tab 拆分
```

## Global Execution Rules

每个阶段都必须遵守：

1. 单阶段只解决该阶段目标，不顺手重构其他业务域。
2. 不改变现有 API URL、页面入口、请求参数、返回字段。
3. 不弱化权限依赖，不把 `require_permission` 改回 `authenticate`。
4. 不删除历史 migration，不做 `DROP TABLE`、`DROP COLUMN`。
5. 架构拆分阶段只做纯搬移或边界调整，不改业务 if/else。
6. 数据范围相关调用必须保留，尤其是 `apply_client_scope`、`filter_query_by_client_scope`、`assert_client_visible`、`assert_client_in_scope`。
7. 前端先外置 JS 并验证，验证通过后再删除 inline script。
8. 发现问题先停止当前阶段，写测试报告和修复建议，不继续扩大改动。
9. 后端 delivery 大模块拆分时，禁止同一阶段同时迁移 roster、pipeline、interviews、handbook。
10. `delivery_detail.html` 前端拆分前，必须先完成对应后端模块的 route/service 边界或明确记录未拆原因。

## Standard Validation Gate

每个阶段结束都必须运行：

```text
./venv/bin/python -m pytest tests/ -q
```

并根据阶段额外运行专项测试。

每个阶段结束都必须生成测试报告：

```text
reports/architecture/phase-XX-report.md
```

如果 `reports/architecture/` 不存在，则创建。

报告必须包含：

```text
# Phase XX 测试报告

## 执行范围
- 本阶段改了什么
- 明确没有改什么

## 自动化测试
- 命令
- 结果
- 失败用例和错误摘要

## 手动验证
- 页面/接口
- 操作步骤
- 结果

## 风险检查
- 权限是否回归
- API 路径是否变化
- 数据范围是否保留
- 导入导出是否可用

## 问题与修复建议
- 问题
- 根因判断
- 建议修复方法
- 是否阻塞进入下一阶段

## 结论
PASS / BLOCKED
```

如果结论是 `BLOCKED`，不能继续执行下一阶段。

## Stop Conditions

遇到以下情况必须停止：

- 服务无法启动。
- `pytest tests/ -q` 失败。
- 发现任何越权访问。
- 关键页面变空白。
- 导入导出结果和原逻辑不一致。
- Cursor 需要同时改多个业务域才能继续。

## Recommended Order

```text
Phase 0: 断开 auth/data_scope.py 对 main.py 的反向 import
Phase 1: 先加架构护栏和报告机制
Phase 2: 拆 delivery settlement 后端域
Phase 3A: 拆 clients 读接口，重点保护 list/detail/export data scope
Phase 3B: 拆 clients 写接口，重点保护 create/update/delete write scope
Phase 3C: 拆 clients 关联接口，保留 details/brief/handoff-summary 行为
Phase 4: 建前端公共工具，先拆 settlement 页面 JS
Phase 5A: 拆 delivery roster 后端域
Phase 5B: 拆 delivery pipeline 后端域
Phase 5C: 拆 delivery interviews 后端域
Phase 5D: 拆 delivery handbook 后端域
Phase 5E: 最后按 tab 拆 delivery_detail.html
```

这套顺序的目的不是最快拆完，而是让每一步都有明确回滚点、测试点和风险边界。
