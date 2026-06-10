# RMS Phase 3D-1C：批量导入修正 CSV + 导入帮助入口

**状态：** 已实施

**目标：**

1. `corrections.csv` 支持 create / update / skip 修正批量导入结果
2. 招聘下拉新增「批量导入帮助」→ `/rms/import-help`

**禁止：** 真实 CSV/简历目录执行命令；上传 UI；OCR/AI；新权限码；migration

---

## 必须修正（实施前已确认）

### 1. `parsed_json` 同步

- **create：** CSV 字段写入 `rms_candidates` 后，须**覆盖** `rms_resumes.parsed_json` 中对应字段再入库，避免详情「简历解析摘要」仍显示误解析姓名（如「电话」）。
- **update：** 除更新 `rms_candidates` 外，同步更新该候选人**最新一条** `rms_resumes.parsed_json`；无 resume 则只更新 candidate。
- **同步字段：** name、phone、email_wechat、school、major、education_level、source

### 2. 招聘导航父级权限

```html
data-crm-nav-any="rms.jobs.read,rms.analytics.read,rms.candidates.read"
```

子链接：

- 招聘Dashboard → `rms.analytics.read`
- 需求&人才库 → `rms.jobs.read`
- 批量导入帮助 → `rms.candidates.read`

### 3. update 非空覆盖

- 仅 CSV **非空**字段覆盖；空字符串不得清空已有 candidate / parsed_json 数据
- phone / email_wechat 仅非空时校验并同步

### 4. update 改 name/phone 后查重

- 合并后的最终 `name + phone` 若与其它候选人重复（**排除自身 `candidate_id`**）→ `failed`，`error=duplicate_name_phone`，不更新

### 5. create 校验顺序

1. 解析原文件 `parsed_json`
2. CSV 覆盖 `parsed_json` / fields
3. 从覆盖后取 `name`/`phone`
4. `reject_candidate_name_reason(strict_length=True)` + 去重

（原解析 `电话`、CSV 修正 `张三` 时，校验的是 `张三`）

### 6. 帮助页通用路径占位

- 命令示例使用 `--source-dir "/你的简历文件夹"`、`--csv "/你的修正CSV路径/rms_resume_corrections.csv"`
- **不写死** `/Users/rocky/...`

---

## 新增文件

| 文件 | 说明 |
|------|------|
| `services/rms_resume_import_corrections.py` | CSV 修正服务 |
| `scripts/apply_rms_resume_import_corrections.py` | CLI |
| `tests/test_rms_resume_import_corrections.py` | 测试 |
| `templates/pages/rms_import_help.html` | 帮助页 |

## 修改文件

| 文件 | 说明 |
|------|------|
| `routes/rms_shell.py` | `GET /rms/import-help` |
| `templates/partials/nav.html` | 父级 nav-any + 三条子链接 |
| `tests/test_nav.py` | 导航权限断言更新 |

---

## corrections.csv 格式

```csv
resume_file_path,action,candidate_id,name,phone,email_wechat,school,major,education_level,source
/path/a.pdf,create,,张三,13800138000,zhangsan@example.com,西安电子科技大学,计算机,本科,批量导入
,update,123,李四,13900139000,lisi@example.com,,,,批量导入
/path/c.pdf,skip,,,,,,,
```

## 报告

`reports/rms_imports/rms_resume_correction_YYYYMMDD_HHMMSS.{csv,json}`（脱敏，已在 .gitignore）

---

## 测试要点

- create：CSV 覆盖后再校验；API `latest_resume_parse_summary.name` = 修正姓名（电话→张三）
- update：candidate + `latest_resume_parse_summary` 均更新；空字段不清空
- update：改成与其它候选人同名同号 → `duplicate_name_phone`，DB 不变
- 仅 `rms.candidates.read` 用户可见招聘菜单并访问 `/rms/import-help`
- 帮助页无写死本机路径，含通用占位符

---

## 验收

```bash
./venv/bin/python -m pytest tests/test_rms_resume_import_corrections.py -q
./venv/bin/python -m pytest tests/test_rms_resume_import.py -q
./venv/bin/python -m pytest tests/test_nav.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```
