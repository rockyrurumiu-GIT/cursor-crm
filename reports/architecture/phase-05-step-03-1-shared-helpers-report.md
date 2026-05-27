# Phase 5E Step 3.1 — Shared Filter Helpers

**状态：PASS**  
**日期：2026-05-27**

## 背景

Step 3 将 `pipelineFuzzyMatch` / `pipelineUniqueSorted` 迁入 `delivery-detail-pipeline.js` 后，员工访谈 inline 仍引用二者，导致 `filteredInterviewRows` 计算失败（API 有数据、页面 0 条）。热修曾从 `CrmDeliveryDetailPipeline` 再导出；本 Step 将 helper 收到共享层，消除 interviews 对 pipeline 模块的依赖。

## 变更

| 文件 | 变更 |
|------|------|
| [`static/js/pages/delivery-detail.js`](static/js/pages/delivery-detail.js) | 新增并导出 `fuzzyMatch`、`uniqueSorted` |
| [`static/js/pages/delivery-detail-pipeline.js`](static/js/pages/delivery-detail-pipeline.js) | 删除本地实现；`createPipelineState` 经 `deps` 注入 |
| [`templates/pages/delivery_detail.html`](templates/pages/delivery_detail.html) | 从 `CrmDeliveryDetail` 解构；interviews 改用新名；`createPipelineState` 传入 helper |

## 验收

```bash
# 无 pipeline 前缀 helper 残留
rg -n "pipelineFuzzyMatch|pipelineUniqueSorted" templates/pages/delivery_detail.html static/js/pages/delivery-detail-pipeline.js
# → 无结果

# interviews 仅通过 createPipelineState 使用 pipeline 模块（无 helper 导出依赖）
rg -n "CrmDeliveryDetailPipeline" templates/pages/delivery_detail.html
# → 仅 createPipelineState 一行
```

| 检查 | 结果 |
|------|------|
| `node --check` delivery-detail.js / delivery-detail-pipeline.js | PASS |
| `pytest` pipeline + interviews smoke | PASS（9） |
| 浏览器 `/delivery/pipeline/1` | 200，无 Ref/Type 错误，`CrmDeliveryDetail.fuzzyMatch` 可用 |
| 浏览器 `/delivery/interviews/1` | 200，表格有行，无 Ref/Type 错误 |

## 下一步

Step 4：拆分 interviews 前端 JS 至 `delivery-detail-interviews.js`；继续从 `CrmDeliveryDetail` 使用 `fuzzyMatch` / `uniqueSorted`。
