# RMS Module Architecture

最后更新：2026-05-27

## 1. 模块定位

RMS 是 ITO CRM 内的招聘管理模块，不作为独立系统、独立代码库或独立 SaaS 产品开发。

RMS 的核心目标是：

- 管理客户岗位、候选人、简历、推荐记录、面试、Offer、入职结果。
- 支持候选人到岗位的多次推荐关系。
- 支持 AI 辅助匹配、排序和解释。
- 在候选人入职后，通过人工确认动作转入交付花名册。
- 复用 CRM 已有的客户、登录、权限、导航、审计和数据安全能力。

RMS 第一阶段应作为 CRM 的一个独立业务模块开发，但在代码、表结构、API、权限上保留清晰边界，方便未来在必要时拆分。

## 2. 模块边界

RMS 使用以下边界约定：

- 页面前缀：`/rms`
- API 前缀：`/api/rms`
- 数据表前缀：`rms_`
- 权限码前缀：`rms.`
- 后端路由：`routes/rms_*.py`
- 业务逻辑：`services/rms_*.py`
- 请求/响应结构：`schemas/rms_*.py`
- 页面模板：`templates/pages/rms_*.html`
- 页面脚本：`static/js/pages/rms-*.js`

RMS 不应把逻辑直接堆入 `main.py`。新增能力应遵循现有 CRM 架构约定：路由、服务、schema、页面 JS 分层。

## 3. 核心数据模型

RMS 的核心建模原则是：

状态属于 `rms_applications`，不属于 `rms_candidates`。

同一个候选人可以被推荐到多个客户、多个岗位。每一条推荐记录都应有独立状态、面试记录、Offer 信息和状态历史。

建议新增表：

- `rms_jobs`
- `rms_candidates`
- `rms_resumes`
- `rms_applications`
- `rms_application_status_history`
- `rms_interviews`
- `rms_offers`
- `rms_match_results`

### 3.1 rms_jobs

`rms_jobs` 表示客户岗位。

岗位属于 CRM 客户，但不等同于 CRM 商机，也不等同于交付需求。

建议核心字段：

- `id`
- `client_id`
- `title`
- `department`
- `location`
- `headcount`
- `job_description`
- `requirements`
- `status`
- `created_at`
- `updated_at`

其中 `client_id` 关联 CRM 现有客户表，不复制客户主数据。

### 3.2 rms_candidates

`rms_candidates` 表示候选人主档。

候选人主档只存放候选人的基础身份信息，不存放某个岗位上的流程状态。

建议核心字段：

- `id`
- `name`
- `phone`
- `email`
- `wechat`
- `current_company`
- `current_title`
- `city`
- `source`
- `tags`
- `created_at`
- `updated_at`

候选人的手机号、邮箱、微信属于敏感信息。无授权时必须脱敏展示。

### 3.3 rms_resumes

`rms_resumes` 表示候选人的简历文件和解析结果。

一个候选人可以有多份简历。

建议核心字段：

- `id`
- `candidate_id`
- `file_name`
- `file_path`
- `file_type`
- `parsed_text`
- `parsed_json`
- `uploaded_by`
- `created_at`

简历原文件下载必须独立授权，不能只依赖候选人查看权限。

### 3.4 rms_applications

`rms_applications` 表示一次候选人对某个客户岗位的推荐记录。

这是 RMS 流程的主表。

建议核心字段：

- `id`
- `job_id`
- `candidate_id`
- `resume_id`
- `status`
- `recommended_by`
- `recommended_at`
- `current_stage`
- `last_activity_at`
- `created_at`
- `updated_at`

状态应记录在 `rms_applications.status`，而不是 `rms_candidates`。

### 3.5 rms_application_status_history

`rms_application_status_history` 表示推荐记录的状态流转历史。

建议核心字段：

- `id`
- `application_id`
- `from_status`
- `to_status`
- `reason`
- `note`
- `changed_by`
- `changed_at`

所有关键状态变更都应写入历史表，便于审计、复盘和后续统计。

### 3.6 rms_interviews

`rms_interviews` 表示面试安排和面试反馈。

建议核心字段：

- `id`
- `application_id`
- `interview_time`
- `interview_round`
- `interviewer`
- `result`
- `feedback`
- `created_at`
- `updated_at`

### 3.7 rms_offers

`rms_offers` 表示 Offer 和入职信息。

建议核心字段：

- `id`
- `application_id`
- `offer_status`
- `salary`
- `expected_onboard_date`
- `actual_onboard_date`
- `note`
- `created_at`
- `updated_at`

候选人确认入职后，不能自动写入交付花名册，必须通过显式人工动作转入。

### 3.8 rms_match_results

`rms_match_results` 表示 AI 匹配结果。

建议核心字段：

- `id`
- `job_id`
- `candidate_id`
- `resume_id`
- `score`
- `summary`
- `strengths`
- `risks`
- `model_name`
- `created_by`
- `created_at`

AI 匹配结果只能用于辅助排序、解释和推荐，不能自动淘汰候选人。

## 4. 不使用 delivery_pipeline_entries 作为 RMS 主表

`delivery_pipeline_entries` 只能作为历史数据导入来源，不能作为 RMS 的长期主表。

原因：

- 它是偏交付过程的平铺表，不适合表达候选人、岗位、简历、推荐记录之间的多对多关系。
- 它无法清晰表达同一候选人被推荐到多个客户或多个岗位的状态差异。
- 它不适合作为 AI 匹配、面试历史、Offer、状态流转的长期数据基础。
- 它与交付模块耦合较强，直接复用会让 RMS 和 Delivery 边界混乱。

正确做法是：

- 保留 `delivery_pipeline_entries` 的历史价值。
- 后续可以提供一次性导入或迁移工具。
- 导入后数据进入 `rms_*` 表。
- 新 RMS 功能只读写 `rms_*` 表。

## 5. 权限与数据安全

RMS API 必须使用 `require_permission`，不能只依赖登录态。

首批权限码建议如下：

- `rms.jobs.read`
- `rms.jobs.write`
- `rms.candidates.read`
- `rms.candidates.write`
- `rms.resumes.read`
- `rms.resumes.download`
- `rms.contacts.view`
- `rms.applications.read`
- `rms.applications.write`
- `rms.matching.run`
- `rms.analytics.read`

权限设计原则：

- 查看候选人列表不等于可以查看联系方式。
- 查看简历记录不等于可以下载简历原文件。
- 运行 AI 匹配必须独立授权。
- 查看统计分析必须独立授权。
- 所有 `/api/rms/*` 接口都必须显式声明权限。

### 5.1 联系方式脱敏

无 `rms.contacts.view` 权限时，以下字段必须脱敏：

- 手机号
- 邮箱
- 微信

脱敏规则可以在第一阶段保持简单：

- 手机号：保留前三位和后四位。
- 邮箱：保留首字符和域名。
- 微信：只显示部分字符。

### 5.2 简历下载权限

简历原文件下载必须使用 `rms.resumes.download` 权限。

拥有 `rms.resumes.read` 只能查看简历元数据和解析结果，不代表可以下载原文件。

## 6. 与 CRM 的关系

RMS 复用 CRM 客户，不复制客户表。

客户仍然由 CRM 模块维护。RMS 岗位通过 `client_id` 关联 CRM 客户。

RMS 不应新增独立客户主表，避免出现以下问题：

- 客户数据重复。
- 客户名称不一致。
- 权限边界混乱。
- 后续客户经营、商机、合同、交付数据无法统一。

RMS 岗位属于客户，但不等同于 CRM 商机或合同。

## 7. 与 Delivery 的关系

RMS 和 Delivery 应保持业务边界。

RMS 负责：

- 岗位招聘。
- 候选人管理。
- 简历管理。
- 推荐流程。
- 面试与 Offer。
- AI 匹配。
- 候选人入职前流程。

Delivery 负责：

- 已入职人员交付管理。
- 花名册。
- 结算。
- 交付过程跟踪。

当 RMS Application 已入职后，可以通过显式动作转入交付花名册。

转入交付花名册必须满足：

- 用户手动点击确认。
- 系统展示即将写入的花名册字段。
- 不自动覆盖已有 `roster_entries`。
- 如存在疑似重复人员，应提示用户处理。
- 转换动作应记录审计日志。

## 8. AI 匹配边界

AI 在 RMS 第一阶段只做辅助，不做自动决策。

允许：

- 简历解析。
- 候选人与岗位匹配评分。
- 推荐理由总结。
- 风险点提示。
- 候选人排序辅助。
- JD 与简历关键词对齐分析。

不允许：

- 自动淘汰候选人。
- 自动拒绝候选人。
- 自动替用户提交客户推荐。
- 自动覆盖人工状态。
- 自动写入交付花名册。

AI 结果应保存在 `rms_match_results`，并作为可追溯的辅助信息展示。

## 9. 第一阶段暂不实现

第一阶段不做以下内容：

- 单独 RMS repo。
- 多租户 SaaS 架构。
- 自动爬 BOSS / 猎聘。
- 客户门户。
- 复杂审批流。
- 日历 / 邮件深度集成。
- AI 自动淘汰候选人。
- 自定义流程模板。
- 复杂 BI 报表设计器。

这些能力不应进入第一阶段代码设计，避免过早复杂化。

## 10. 第一阶段建议交付范围

第一阶段建议只交付 RMS 最小闭环：

1. RMS 导航入口。
2. RMS 权限码注册。
3. 客户岗位管理。
4. 候选人管理。
5. 简历上传与解析结果存储。
6. 候选人推荐到岗位。
7. 推荐状态流转与历史记录。
8. 面试记录。
9. Offer / 入职信息。
10. AI 匹配结果保存与展示。
11. 入职后人工确认转入交付花名册。
12. 基础统计看板。

第一阶段的目标不是做完整 ATS，而是验证 RMS 与现有 CRM / Delivery 体系能否形成稳定业务闭环。

## 11. 验收原则

RMS 模块完成后，应满足以下条件：

- CRM 原有客户、商机、联系人、交付功能不受影响。
- RMS API 全部使用 `require_permission`。
- 候选人联系方式在无权限时正确脱敏。
- 简历原文件下载受独立权限控制。
- 同一候选人可以被推荐到多个客户岗位。
- 每条推荐记录有独立状态和状态历史。
- `delivery_pipeline_entries` 不作为 RMS 主表。
- 入职转交付必须人工确认。
- AI 匹配结果不会自动淘汰候选人。
- 架构检查和测试通过。

推荐验证命令：

```bash
./venv/bin/python scripts/check_architecture.py
./venv/bin/python -m pytest tests/ -q