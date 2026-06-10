# RMS Phase 3D-1B：批量导入姓名可信度校验

**状态：** 已实施

**目标：** 减少批量简历导入时把「电话 / 个人简历 / 学校 / 测试标题」等误识别为候选人姓名。

**禁止：** 改 `auth/*`、`routes/*`、`templates/*`、`static/*`、`migrations/*`；不改去重规则；不做 OCR/AI/UI；不全局修改 `_RE_NAME` 主正则。

---

## 补充约束（已确认）

1. **`reject_candidate_name_reason(name, *, strict_length=False)`**
   - `strict_length=True`：**仅** [`services/rms_resume_import.py`](services/rms_resume_import.py) 批量导入闸门使用（2-4 汉字 / 含 `·` 放宽至 2-8 汉字）。
   - `strict_length=False`：[`services/rms_applications.py`](services/rms_applications.py) 解析层使用，只做 blocklist / 机构后缀 / 格式过滤，**不**执行 2-4 字严格长度。

2. **不全局收紧 `_RE_NAME_STANDALONE`**
   - 不把 `_RE_NAME_STANDALONE` 从 `{2,6}` 全局改为 `{2,4}`。
   - 页眉收紧仅在 `_extract_name_from_header` 内：扩充 `_NAME_HEADER_SKIP` + `reject_candidate_name_reason(..., strict_length=False)` 过滤候选行。

3. **报告字段 `name_reject_reason`**
   - `invalid_candidate_name` 时：`error=invalid_candidate_name`，`name_reject_reason=<reject_candidate_name_reason 返回值>`（如 `blocklist`、`institution_suffix`、`length`、`format`）。

4. **批量导入顺序（不变）**
   - `missing_name_or_phone` → `invalid_candidate_name` → `duplicate` → `would_create` / `created`

5. **`_clean_extracted_name`**
   - 保留结构清洗；**不**在清洗阶段清空带 `姓名：` 标签的坏名（保证导入闸门能返回 `invalid_candidate_name` 而非 `missing_name_or_phone`）。

---

## 修改文件

| 文件 | 改动 |
|------|------|
| [`services/rms_applications.py`](services/rms_applications.py) | 新增 `reject_candidate_name_reason`、常量；扩充 `_NAME_HEADER_SKIP`；收紧 `_extract_name_from_header`、`_extract_name_from_filename` |
| [`services/rms_resume_import.py`](services/rms_resume_import.py) | 导入闸门 `strict_length=True`；扩展 `REPORT_CSV_FIELDS` + `_report_row` |
| [`tests/test_rms_resume_import.py`](tests/test_rms_resume_import.py) | 坏名/好名/dry-run 参数化测试；夹具 ≤4 字可信名 |

---

## 拒绝规则

### 精确 blocklist（整名匹配）

电话、手机、联系方式、个人简历、简历、基本信息、个人信息、求职意向、教育经历、工作经历、项目经历、自我评价、技能、证书、测试、效果、相机

### 机构/公司后缀（子串）

大学、学院、学校、中学、公司、科技、技术、集团、有限公司、中心、部门

### 长度（仅 `strict_length=True`）

- 纯中文名：2-4 汉字
- 含 `·`：2-8 汉字（不计间隔符）

### 格式

除汉字与 `·` 外有其它字符 → `format`

---

## 测试用例

| 姓名 + 手机号 | 期望 |
|-------------|------|
| 个人简历 | commit/dry-run 均不创建；`invalid_candidate_name` |
| 电话 | 同上 |
| 许昌学院 | 同上 |
| 相机效果测试 | 同上 |
| 周鹏飞 | 正常创建 |
| 刘昱辰 | 正常创建 |
| 张丽娜 | 正常创建 |

模板：`姓名：{name}\n手机 {phone}\n`，手机号用 `_import_phone()`。

### 夹具调整

- `DUP_IMPORT_NAME`：`重复候选人`(5字) → `重复张三`(4字)
- API 测试 `导入候选人`(5字) → `周鹏飞`
- `test_limit`：避免 `候选人0` 等含数字名；改用 `["张三","李四","王五","赵六","孙七"]`

---

## 验收命令

```bash
./venv/bin/python -m pytest tests/test_rms_resume_import.py -q
./venv/bin/python -m pytest tests/test_rms_candidate_detail.py -q
./venv/bin/python -m pytest tests/test_rms_application_workflow.py -q
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q
```
