# Phase 5D — Delivery Handbook Backend Split Report

**状态：PASS**  
**日期：2026-05-26**

---

## 1. API / Helper Checklist

### API Routes（11 个，全部已迁移）

| # | HTTP | URL | 权限 | 状态 |
|---|------|-----|------|------|
| 1 | GET | `/api/clients/{client_id}/delivery/handbooks` | delivery.handbook.read | 已迁移 |
| 2 | POST | `/api/clients/{client_id}/delivery/handbooks` | delivery.handbook.write | 已迁移 |
| 3 | PATCH | `/api/clients/{client_id}/delivery/handbooks/{row_id}` | delivery.handbook.write | 已迁移 |
| 4 | POST | `/api/clients/{client_id}/delivery/handbooks/{row_id}/rebuild-pdf-outline` | delivery.handbook.write | 已迁移 |
| 5 | GET | `/api/clients/{client_id}/delivery/handbooks/{row_id}/pdf-text` | delivery.handbook.read | 已迁移 |
| 6 | GET | `/api/clients/{client_id}/delivery/handbooks/{row_id}/pdf-page.png` | delivery.handbook.read | 已迁移 |
| 7 | DELETE | `/api/clients/{client_id}/delivery/handbooks/{row_id}` | delivery.handbook.write | 已迁移 |
| 8 | GET | `/api/delivery/handbooks/search` | delivery.handbook.read | 已迁移 |
| 9 | POST | `/api/handbook-assistant/chat` | delivery.handbook.read | 已迁移 |
| 10 | POST | `/api/delivery/handbooks/sync-fts-indexed` | delivery.handbook.write | 已迁移 |
| 11 | POST | `/api/delivery/handbooks/reindex-stale` | delivery.handbook.write | 已迁移 |

### Helper Functions（37 个，全部已迁移到 services/delivery_handbook.py）

- PDF outline：`_toc_levels_to_tree`, `_pdf_outline_fitz`, `_pypdf_outline_aux`, `_pdf_outline_pypdf`, `_pdf_outline_from_internal_links`, `_pdf_outline_heuristic_text`, `_pdf_bytes_to_outline_tree`
- TOC 正则/归一化：`_HANDBOOK_TOC_LINE`, `_HANDBOOK_TOC_INLINE`, `_handbook_normalize_toc_text`, `_section_key_depth`
- PyMuPDF link helpers：`_fitz_link_target_page_1based`
- 文件路径：`_client_upload_folder_name`, `_handbook_client_dir_rel`, `_safe_handbook_filename`
- FTS：`_handbook_fts_delete_row`, `_handbook_fts_upsert_row`, `_handbook_build_fts_query`, `_handbook_search_snippet`, `_handbook_query_terms`, `_handbook_text_matches`
- PDF 文本/渲染/OCR：`_pdf_plain_text_and_pagecount`, `_pdf_plain_text_pages`, `_pdf_render_page_png`, `_pdf_text_suggests_ocr`, `_pdf_ocr_tesseract`
- Search locators：`_handbook_locate_pdf_page`, `_handbook_locate_media_seconds`
- 非 PDF 元数据索引：`_handbook_manual_search_blob`, `_handbook_background_index_manual_meta`
- PDF 后台索引：`_handbook_background_index_pdf`
- 序列化：`_handbook_outline_coerce`, `_handbook_cues_from_json_string`, `_handbook_dt_iso`, `_handbook_row_to_dict`
- Label/status/media：`_handbook_split_comma_labels`, `_handbook_labels_to_json_array`, `_handbook_normalize_status`, `_handbook_suffix_to_media_kind`, `_handbook_parse_json_list`, `_handbook_normalize_media_cues`

### Constants（8 个，已迁移到 schemas/delivery_handbook.py）

- `HANDBOOK_ALLOWED_SUFFIXES`
- `HANDBOOK_STATUS_SET`
- `HANDBOOK_SEARCH_BODY_MAX`
- `HANDBOOK_SEARCH_SNIPPET_LIST`
- `HANDBOOK_SEARCH_SNIPPET_MODAL`
- `HANDBOOK_OCR_MAX_PAGES`
- `HANDBOOK_OCR_ZOOM`

### 保留在 main.py

| 项目 | 原因 |
|------|------|
| `_ensure_handbook_schema_compat()` | 数据库启动时 schema migration，属于全局初始化 |
| `_ensure_handbook_fts_schema()` | FTS 虚拟表创建，属于全局初始化 |
| `DeliveryHandbookFile` ORM model | 与其他 model 放在一起，暂不迁移 |
| `/api/files/access` 安全网关 | 全局通用文件下载，不属于 handbook 域 |
| 页面路由 | 本阶段不迁页面入口，delivery detail 相关页面仍保留在 main.py |

---

## 2. 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `schemas/delivery_handbook.py` | 25 | 常量定义 |
| `services/delivery_handbook.py` | 1031 | 业务逻辑、PDF/OCR/FTS helpers、后台任务工厂 |
| `routes/delivery_handbook.py` | 658 | 11 个 API handler + register 函数 |
| `tests/test_smoke_delivery_handbook.py` | 87 | Smoke 测试 |

---

## 3. main.py 行数变化

| 阶段 | 行数 |
|------|------|
| Phase 5C 完成后 | 3031 |
| Phase 5D 完成后 | 1518 |
| **减少** | **1513 行 (49.9%)** |

---

## 4. 设计决策

### 4.1 后台任务注入方案：Scheme A（工厂模式）

```python
bg_index_pdf = make_background_index_pdf(session_factory, engine, HandbookFile, upload_dir)
# 使用: background_tasks.add_task(bg_index_pdf, row_id)
```

`make_background_index_pdf` 和 `make_background_index_manual_meta` 是工厂函数，返回闭包 `fn(row_id)`。闭包内部捕获注入的 `session_factory`（即 `SessionLocal`）和 `engine`，避免 service 层直接依赖模块级全局变量。

### 4.2 FTS helpers 的 engine 注入

所有 FTS 操作函数（`handbook_fts_delete_row`, `handbook_fts_upsert_row`）接受 `engine` 作为第一个参数：

```python
def handbook_fts_delete_row(engine, row_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handbook_fts WHERE rowid = :rid"), {"rid": row_id})
```

### 4.3 权限依赖

routes 文件直接 `from auth.deps import require_permission`，与 roster/pipeline/interviews routes 保持一致。

### 4.4 文件访问安全网关

handbook 文件下载/预览仍通过 `/api/files/access` 安全网关（保留在 main.py），`_handbook_row_to_dict` 使用 `sec.file_access_url(stored_path)` 生成预览 URL。

---

## 5. FTS 初始化/helper 迁移情况

- `_ensure_handbook_fts_schema()`：**保留 main.py**（全局启动初始化）
- FTS CRUD helpers (`handbook_fts_delete_row`, `handbook_fts_upsert_row`)：**已迁移** services
- FTS query 构建 (`handbook_build_fts_query`)：**已迁移** services
- FTS search snippet/terms：**已迁移** services

---

## 6. PDF/OCR/后台任务

- PDF outline 提取（4 策略链）：只搬移位置，未改算法
- PDF 文本提取 + 页面渲染：只搬移位置，未改算法
- OCR (tesseract)：只搬移位置，未改算法；lazy import 保持不变
- 后台索引任务：改为工厂闭包模式，但内部逻辑未改

---

## 7. 文件访问安全网关

handbook 文件通过 `sec.resolve_upload_path(upload_dir, stored_rel)` 写入，通过 `sec.file_access_url(sp)` 生成访问 URL。`/api/files/access` 路由保留在 main.py，经过 `authenticate` 鉴权和 `sec.resolve_upload_path` 路径验证。未开放裸路径。

---

## 8. Smoke 测试覆盖

| 场景 | 测试 |
|------|------|
| GET handbooks list 返回 200 | `TestHandbookList.test_list` |
| POST upload PDF 返回 200 | `TestHandbookUpload.test_upload_pdf` |
| POST sync-fts-indexed 返回 200 | `TestHandbookSyncFTS.test_sync_fts_returns_200` |
| GET search 返回 200 | `TestHandbookSearch.test_search_returns_200` |
| GET search 空查询 400 | `TestHandbookSearch.test_search_empty_query_400` |

---

## 9. 自动化测试结果

```
check_architecture.py:
  - Reverse import check: PASS
  - Route permission check: PASS (with existing /api/files/access warning)
  - File size check: PASS

pytest tests/ -q:
  80 passed, 0 failed
```

---

## 10. 未覆盖风险

| 风险项 | 说明 |
|--------|------|
| 真实 PDF 大文件 outline 提取 | Smoke 测试使用 fake PDF bytes，未验证真实 PyMuPDF outline 提取 |
| OCR (tesseract) 端到端 | 未在测试中安装/执行 tesseract，仅验证 API 入口通路 |
| 大文件预览/渲染 | 未在测试中上传真实多页 PDF 并验证 page render |
| handbook-assistant/chat | 未单独 smoke 覆盖（依赖 search 数据），但 search 已验证 |
| 后台任务执行完整性 | BackgroundTasks 在 TestClient 中同步执行，但 fake PDF 无法成功 index |

---

## 验收标准

- [x] `check_architecture.py` PASS
- [x] 全量 pytest PASS (80/80)
- [x] main.py 不再包含 handbook API handler
- [x] `routes/delivery_handbook.py` 不 import main.py
- [x] `services/delivery_handbook.py` 不 import main.py
- [x] 现有 URL、权限、返回结构保持不变
- [x] 报告状态：**PASS**
