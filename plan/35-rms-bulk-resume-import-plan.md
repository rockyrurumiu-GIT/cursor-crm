# RMS Phase 3D-1：批量简历导入人才库

**状态：** 已实施

**目标：** 后台命令行工具，将文件夹内大量简历导入 RMS 人才库（仅 `rms_candidates` + `rms_resumes`）。

**禁止：** 对真实简历目录执行导入命令；不写 `rms_applications`；不改 auth/routes/templates/static/migrations。

---

## 新增文件

| 文件 | 说明 |
|------|------|
| `services/rms_resume_import.py` | 扫描、解析、去重、原子 commit、报告 |
| `scripts/import_rms_resumes.py` | CLI 入口 |
| `tests/test_rms_resume_import.py` | pytest（仅用 tmp_path） |

## 修改文件

| 文件 | 说明 |
|------|------|
| `.gitignore` | 忽略 `reports/rms_imports/` |

---

## CLI

```bash
./venv/bin/python scripts/import_rms_resumes.py --source-dir DIR --dry-run
./venv/bin/python scripts/import_rms_resumes.py --source-dir DIR --commit
```

- `--dry-run` / `--commit` 二选一
- 默认报告目录：`reports/rms_imports/`
- 不得对真实简历目录执行（开发/测试仅用 pytest 临时目录）

---

## 核心规则

| 主题 | 规则 |
|------|------|
| 写入表 | 仅 `rms_candidates`、`rms_resumes` |
| 最低条件 | 姓名 + 手机号同时存在 |
| 去重 | 仅姓名+手机号同时相同 → `skipped_duplicate` |
| 不支持 | `.png`/`.jpg`/`.jpeg` 及非允许后缀 → `skipped_unsupported` |
| Word | `.doc`/`.docx` 支持后缀；解析不到姓名+手机 → `skipped_unparseable` |
| 原子 commit | 候选人+文件+resume 任一步失败 → `rollback` + `failed`，不留半成品 |
| 报告脱敏 | CSV/JSON 仅 `phone_masked`/`email_masked`，不写完整联系方式 |
| 搜索权限 | `parsed_text` 搜索保持现有 `_apply_candidate_keyword_search` 逻辑，本阶段不修改 |

---

## 验收命令

```bash
./venv/bin/python -m pytest tests/test_rms_resume_import.py -q
./venv/bin/python -m pytest tests/test_rms_candidate_detail.py -q
./venv/bin/python -m pytest tests/test_rms_application_workflow.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```
