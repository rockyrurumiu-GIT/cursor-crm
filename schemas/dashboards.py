"""Dashboard builder whitelists — sources, fields, metrics, widget types."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Literal, Optional, Tuple

from auth.data_scope_catalog import (
    RESOURCE_CRM_CLIENT,
    RESOURCE_CRM_CONTACT,
    RESOURCE_CRM_OPPORTUNITY,
    RESOURCE_CRM_VISIT,
    RESOURCE_DELIVERY_HANDOFF,
    RESOURCE_DELIVERY_INTERVIEWS,
    RESOURCE_DELIVERY_ROSTER,
    RESOURCE_DELIVERY_SETTLEMENT,
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_CANDIDATE,
    RESOURCE_RMS_JOB,
)

FieldKind = Literal["text", "numeric", "datetime"]

# roster_summary is a dedicated delivery widget (multi-KPI card); it is a data widget
# but NOT a chart and does not use the generic metric/group path.
WIDGET_TYPES: FrozenSet[str] = frozenset({
    "number", "bar", "horizontal_bar", "pie", "line", "featured_line", "featured_bar",
    "rich_text", "iframe", "roster_summary",
    "rms_block",
})

# Preset recruitment-dashboard blocks (stored as widget_type=rms_block, config.block=…).
RMS_BLOCK_KEYS_LEGACY: FrozenSet[str] = frozenset({
    "chart_history_pass",
    "table_history",
    "chart_client_job_stage_grouped",
    "chart_client_job_stage_stacked",
    "chart_client_job_stage_funnel",
})

RMS_BLOCK_KEYS_NEW: FrozenSet[str] = frozenset({
    "filter",
    "kpi_clients", "kpi_jobs", "kpi_hc",
    "kpi_resume_count", "kpi_hired_count", "kpi_resume_to_hire_rate",
    "chart_pipeline", "filter_summary",
    "chart_pending_backlog",
    "lifecycle_funnel", "chart_lifecycle_pass_rate", "table_lifecycle_detail",
    "chart_recruiter", "table_recruiter",
    "chart_job_pending_backlog", "chart_client_hired_ranking",
    "chart_recruiter_recommend_vs_hired",
    "roster_header",
    "roster_kpi_matched", "roster_kpi_missing", "roster_kpi_mismatch", "roster_kpi_ambiguous",
    "table_roster",
    "table_client_job_stage",
})

RMS_BLOCK_KEYS: FrozenSet[str] = RMS_BLOCK_KEYS_LEGACY | RMS_BLOCK_KEYS_NEW
RMS_BLOCK_KEYS_ADDABLE: FrozenSet[str] = RMS_BLOCK_KEYS_NEW

RMS_BLOCK_LABELS: Dict[str, str] = {
    "filter": "筛选",
    "kpi_clients": "KPI · 有需求客户数",
    "kpi_jobs": "KPI · 需求总数",
    "kpi_hc": "KPI · HC 总数",
    "kpi_resume_count": "KPI · 简历数",
    "kpi_hired_count": "KPI · 入职数",
    "kpi_resume_to_hire_rate": "KPI · 百简历入职转化率",
    "chart_pipeline": "图表 · 招聘管道",
    "filter_summary": "当前筛选摘要",
    "chart_pending_backlog": "图表 · 待处理积压",
    "lifecycle_funnel": "图表 · 招聘生命周期漏斗",
    "chart_lifecycle_pass_rate": "图表 · 五率通过率",
    "table_lifecycle_detail": "表格 · 生命周期明细",
    "chart_history_pass": "图表 · 阶段通过率",
    "table_history": "表格 · 阶段明细",
    "chart_recruiter": "图表 · 当月入职排名",
    "table_recruiter": "表格 · 人效明细",
    "chart_job_pending_backlog": "图表 · 岗位待处理积压",
    "chart_client_hired_ranking": "图表 · 客户入职量排行",
    "chart_recruiter_recommend_vs_hired": "图表 · 推荐量 vs 入职量",
    "roster_header": "花名册核对操作",
    "roster_kpi_matched": "KPI · 一致",
    "roster_kpi_missing": "KPI · 缺失",
    "roster_kpi_mismatch": "KPI · 不一致",
    "roster_kpi_ambiguous": "KPI · 多匹配",
    "table_roster": "表格 · 核对明细",
    "table_client_job_stage": "表格 · 客户岗位阶段统计",
    "chart_client_job_stage_grouped": "图表 · 岗位阶段（分组柱）",
    "chart_client_job_stage_stacked": "图表 · 岗位阶段（堆叠柱）",
    "chart_client_job_stage_funnel": "图表 · 岗位阶段（漏斗）",
}

RMS_WIDGET_TYPE_DISPLAY_ORDER: Tuple[str, ...] = ("rms_block", "rich_text")
CHART_WIDGET_TYPES: FrozenSet[str] = frozenset({"bar", "horizontal_bar", "pie", "line", "featured_line", "featured_bar"})
CHART_EXTRA_RENDERS: FrozenSet[str] = frozenset({"doughnut", "horizontal_bar"})
DATA_WIDGET_TYPES: FrozenSet[str] = frozenset({"number", "bar", "horizontal_bar", "pie", "line", "featured_line", "featured_bar"})
# Config panel type grid order (subset of WIDGET_TYPES).
WIDGET_TYPE_DISPLAY_ORDER: Tuple[str, ...] = (
    "number", "bar", "horizontal_bar", "pie", "line", "featured_line", "featured_bar",
    "rich_text", "iframe", "roster_summary",
)

METRICS: FrozenSet[str] = frozenset({"count", "sum", "avg", "min", "max"})
NUMERIC_METRICS: FrozenSet[str] = frozenset({"sum", "avg", "min", "max"})
DATE_GROUPS: FrozenSet[str] = frozenset({"day", "week", "month", "year"})

FILTER_OPS: FrozenSet[str] = frozenset({
    "eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains", "in",
})

# Style whitelists (Twenty-parity). Fixed enums only — no arbitrary CSS/colors.
CHART_COLOR_ORDER: Tuple[str, ...] = (
    "red", "ruby", "crimson", "tomato", "orange", "amber", "yellow",
    "lime", "grass", "green", "jade", "mint", "turquoise", "cyan", "sky", "blue",
    "iris", "violet", "purple", "plum", "pink", "bronze", "gold", "brown", "gray",
)
CHART_COLORS: FrozenSet[str] = frozenset(CHART_COLOR_ORDER)
COLOR_SHADES: FrozenSet[int] = frozenset({0, 1, 2, 3, 4})
DEFAULT_COLOR = "blue"
DEFAULT_COLOR_SHADE = 2
SORT_MODES: FrozenSet[str] = frozenset({"label_asc", "label_desc", "value_asc", "value_desc"})
DEFAULT_SORT = "value_desc"

AXIS_SORT_MODES: FrozenSet[str] = frozenset({
    "position_asc", "position_desc",
    "label_asc", "label_desc",
    "sum_asc", "sum_desc",
    "manual",
})
PRIMARY_AXIS_SORT_ORDER: Tuple[str, ...] = (
    "position_asc", "position_desc",
    "label_asc", "label_desc",
    "sum_asc", "sum_desc",
    "manual",
)
SECONDARY_AXIS_SORT_MODES: FrozenSet[str] = frozenset({"label_asc", "label_desc"})
GROUP_MODES: FrozenSet[str] = frozenset({"stacked", "grouped"})
AXIS_NAME_DISPLAY: FrozenSet[str] = frozenset({"none", "x", "y", "both"})
DEFAULT_PRIMARY_AXIS_SORT = "position_asc"
DEFAULT_SECONDARY_AXIS_SORT = "label_asc"
DEFAULT_GROUP_MODE = "stacked"
DEFAULT_AXIS_NAME_DISPLAY = "none"
DEFAULT_DATE_GROUP = "month"


@dataclass(frozen=True)
class SourceFieldDef:
    key: str
    label: str
    kind: FieldKind


@dataclass(frozen=True)
class DataSourceDef:
    key: str
    label: str
    permission: str
    resource_code: str
    model_attr: str  # injected model name hint for routes
    fields: Tuple[SourceFieldDef, ...]
    has_client_id: bool = True


DATA_SOURCES: Dict[str, DataSourceDef] = {
    "clients": DataSourceDef(
        key="clients",
        label="客户",
        permission="crm.clients.read",
        resource_code=RESOURCE_CRM_CLIENT,
        model_attr="Client",
        has_client_id=False,
        fields=(
            SourceFieldDef("phase", "阶段", "text"),
            SourceFieldDef("industry", "行业", "text"),
            SourceFieldDef("city", "城市", "text"),
            SourceFieldDef("scale", "规模", "text"),
            SourceFieldDef("win_rate", "赢率", "text"),
            SourceFieldDef("estimated_annual_amount", "预估年金额", "numeric"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "contacts": DataSourceDef(
        key="contacts",
        label="联系人",
        permission="crm.contacts.read",
        resource_code=RESOURCE_CRM_CONTACT,
        model_attr="Contact",
        fields=(
            SourceFieldDef("city", "城市", "text"),
            SourceFieldDef("title", "职位", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "opportunities": DataSourceDef(
        key="opportunities",
        label="商机",
        permission="crm.opportunities.read",
        resource_code=RESOURCE_CRM_OPPORTUNITY,
        model_attr="Opportunity",
        fields=(
            SourceFieldDef("stage", "阶段", "text"),
            SourceFieldDef("amount", "金额", "numeric"),
            SourceFieldDef("estimated_current_year_amount", "当年预估金额", "numeric"),
            SourceFieldDef("probability", "概率", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "visits": DataSourceDef(
        key="visits",
        label="客户拜访",
        permission="crm.visits.read",
        resource_code=RESOURCE_CRM_VISIT,
        model_attr="VisitRecord",
        fields=(
            SourceFieldDef("city", "城市", "text"),
            SourceFieldDef("region", "区域", "text"),
            SourceFieldDef("completed", "是否完成", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "handoff_requests": DataSourceDef(
        key="handoff_requests",
        label="项目交接",
        permission="delivery.handoff.read",
        resource_code=RESOURCE_DELIVERY_HANDOFF,
        model_attr="HandoffRequest",
        fields=(
            SourceFieldDef("status", "状态", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "roster_entries": DataSourceDef(
        key="roster_entries",
        label="花名册",
        permission="delivery.roster.read",
        resource_code=RESOURCE_DELIVERY_ROSTER,
        model_attr="RosterEntry",
        fields=(
            SourceFieldDef("employment_status", "在职情况", "text"),
            SourceFieldDef("position_title", "岗位", "text"),
            SourceFieldDef("client", "客户", "text"),  # virtual: resolves via client_id -> Client.name
            SourceFieldDef("monthly_quote_tax", "月报价(含税)", "numeric"),
            SourceFieldDef("pre_tax_salary", "税前工资", "numeric"),
            SourceFieldDef("gms", "GM$", "numeric"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "delivery_settlement_entries": DataSourceDef(
        key="delivery_settlement_entries",
        label="结算台账",
        permission="delivery.settlement.read",
        resource_code=RESOURCE_DELIVERY_SETTLEMENT,
        model_attr="DeliverySettlementEntry",
        fields=(
            SourceFieldDef("fee_month", "工作量月份", "text"),
            SourceFieldDef("amount", "金额", "numeric"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
    "delivery_interview_entries": DataSourceDef(
        key="delivery_interview_entries",
        label="员工访谈",
        permission="delivery.interviews.read",
        resource_code=RESOURCE_DELIVERY_INTERVIEWS,
        model_attr="DeliveryInterviewEntry",
        fields=(
            SourceFieldDef("employment_status", "在职情况", "text"),
            SourceFieldDef("satisfaction", "满意度", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
        ),
    ),
}

RMS_DATA_SOURCES: Dict[str, DataSourceDef] = {
    "rms_jobs": DataSourceDef(
        key="rms_jobs",
        label="岗位",
        permission="rms.jobs.read",
        resource_code=RESOURCE_RMS_JOB,
        model_attr="RmsJob",
        has_client_id=True,
        fields=(
            SourceFieldDef("client_id", "客户", "text"),
            SourceFieldDef("title", "岗位名称", "text"),
            SourceFieldDef("department", "部门", "text"),
            SourceFieldDef("location", "地点", "text"),
            SourceFieldDef("headcount", "HC", "numeric"),
            SourceFieldDef("status", "状态", "text"),
            SourceFieldDef("priority", "优先级", "text"),
            SourceFieldDef("years_required", "年限要求", "text"),
            SourceFieldDef("education", "学历", "text"),
            SourceFieldDef("owner_user_id", "负责人", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
            SourceFieldDef("updated_at", "更新时间", "datetime"),
        ),
    ),
    "rms_candidates": DataSourceDef(
        key="rms_candidates",
        label="人选",
        permission="rms.candidates.read",
        resource_code=RESOURCE_RMS_CANDIDATE,
        model_attr="RmsCandidate",
        has_client_id=False,
        fields=(
            SourceFieldDef("name", "姓名", "text"),
            SourceFieldDef("city", "城市", "text"),
            SourceFieldDef("source", "来源", "text"),
            SourceFieldDef("education_level", "学历", "text"),
            SourceFieldDef("school", "学校", "text"),
            SourceFieldDef("major", "专业", "text"),
            SourceFieldDef("gender", "性别", "text"),
            SourceFieldDef("marital_status", "婚姻状况", "text"),
            SourceFieldDef("current_company", "当前公司", "text"),
            SourceFieldDef("current_title", "当前职位", "text"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
            SourceFieldDef("updated_at", "更新时间", "datetime"),
        ),
    ),
    "rms_applications": DataSourceDef(
        key="rms_applications",
        label="推荐记录",
        permission="rms.applications.read",
        resource_code=RESOURCE_RMS_APPLICATION,
        model_attr="RmsApplication",
        has_client_id=True,
        fields=(
            SourceFieldDef("client_id", "客户", "text"),
            SourceFieldDef("job_id", "岗位", "text"),
            SourceFieldDef("candidate_id", "人选", "text"),
            SourceFieldDef("status", "状态", "text"),
            SourceFieldDef("receive_status", "接收状态", "text"),
            SourceFieldDef("delivery_review_status", "交付审核", "text"),
            SourceFieldDef("current_stage", "当前阶段", "text"),
            SourceFieldDef("recommended_by", "推荐人", "text"),
            SourceFieldDef("recommended_at", "推荐时间", "datetime"),
            SourceFieldDef("hired_at", "入职时间", "datetime"),
            SourceFieldDef("created_at", "创建时间", "datetime"),
            SourceFieldDef("updated_at", "更新时间", "datetime"),
        ),
    ),
}

CRM_SOURCE_KEYS: FrozenSet[str] = frozenset(DATA_SOURCES.keys())
RMS_SOURCE_KEYS: FrozenSet[str] = frozenset(RMS_DATA_SOURCES.keys())
RMS_ALLOWED_SOURCE_KEYS: FrozenSet[str] = CRM_SOURCE_KEYS | RMS_SOURCE_KEYS
SOURCE_KEYS: FrozenSet[str] = CRM_SOURCE_KEYS | RMS_SOURCE_KEYS


def get_source(key: str) -> Optional[DataSourceDef]:
    return DATA_SOURCES.get(key) or RMS_DATA_SOURCES.get(key)


def get_field(source_key: str, field_key: str) -> Optional[SourceFieldDef]:
    src = get_source(source_key)
    if not src:
        return None
    for f in src.fields:
        if f.key == field_key:
            return f
    return None


def _field_metadata(f: SourceFieldDef) -> dict:
    if f.kind == "datetime":
        role = "datetime"
        metricable = False
        sortable = True
    elif f.kind == "numeric":
        role = "numeric"
        metricable = True
        sortable = False
    else:
        role = "dimension"
        metricable = False
        sortable = True
    return {
        "key": f.key,
        "label": f.label,
        "kind": f.kind,
        "role": role,
        "filterable": True,
        "metricable": metricable,
        "sortable": sortable,
    }


def _source_to_metadata(src: DataSourceDef) -> dict:
    return {
        "key": src.key,
        "label": src.label,
        "fields": [_field_metadata(f) for f in src.fields],
    }


def build_rms_metadata() -> dict:
    """Whitelists for RMS dashboard widget config panel (CRM builder + recruitment presets)."""
    meta = build_metadata()
    meta["sources"] = meta["sources"] + [
        _source_to_metadata(src) for src in RMS_DATA_SOURCES.values()
    ]
    meta["widget_types"] = list(WIDGET_TYPE_DISPLAY_ORDER) + ["rms_block"]
    meta["rms_blocks"] = [
        {"key": k, "label": RMS_BLOCK_LABELS.get(k, k)}
        for k in sorted(RMS_BLOCK_KEYS_ADDABLE)
    ]
    return meta


def build_metadata() -> dict:
    """Return whitelists for frontend config panel."""
    sources = []
    for src in DATA_SOURCES.values():
        sources.append({
            "key": src.key,
            "label": src.label,
            "fields": [_field_metadata(f) for f in src.fields],
        })
    return {
        "sources": sources,
        "widget_types": [t for t in WIDGET_TYPE_DISPLAY_ORDER if t in WIDGET_TYPES],
        "chart_widget_types": sorted(CHART_WIDGET_TYPES),
        "metrics": sorted(METRICS),
        "filter_ops": sorted(FILTER_OPS),
        "date_groups": sorted(DATE_GROUPS),
        "colors": list(CHART_COLOR_ORDER),
        "color_shades": sorted(COLOR_SHADES),
        "sorts": sorted(SORT_MODES),
        "primary_axis_sorts": list(PRIMARY_AXIS_SORT_ORDER),
        "secondary_axis_sorts": sorted(SECONDARY_AXIS_SORT_MODES),
        "group_modes": sorted(GROUP_MODES),
        "axis_name_displays": sorted(AXIS_NAME_DISPLAY),
        "chart_extra_renders": sorted(CHART_EXTRA_RENDERS),
    }
