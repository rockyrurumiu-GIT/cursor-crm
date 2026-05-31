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
    RESOURCE_DELIVERY_PIPELINE,
    RESOURCE_DELIVERY_ROSTER,
    RESOURCE_DELIVERY_SETTLEMENT,
)

FieldKind = Literal["text", "numeric", "datetime"]

WIDGET_TYPES: FrozenSet[str] = frozenset({"number", "bar", "pie", "line", "rich_text", "iframe"})
CHART_WIDGET_TYPES: FrozenSet[str] = frozenset({"bar", "pie", "line"})
DATA_WIDGET_TYPES: FrozenSet[str] = frozenset({"number", "bar", "pie", "line"})

METRICS: FrozenSet[str] = frozenset({"count", "sum", "avg", "min", "max"})
NUMERIC_METRICS: FrozenSet[str] = frozenset({"sum", "avg", "min", "max"})
DATE_GROUPS: FrozenSet[str] = frozenset({"day", "week", "month", "year"})

FILTER_OPS: FrozenSet[str] = frozenset({
    "eq", "ne", "gt", "gte", "lt", "lte", "contains", "not_contains", "in",
})

# Style whitelists (Twenty-parity). Fixed enums only — no arbitrary CSS/colors.
CHART_COLORS: FrozenSet[str] = frozenset({"blue", "green", "orange", "red", "purple", "gray"})
DEFAULT_COLOR = "blue"
SORT_MODES: FrozenSet[str] = frozenset({"label_asc", "label_desc", "value_asc", "value_desc"})
DEFAULT_SORT = "value_desc"


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
    "delivery_pipeline_entries": DataSourceDef(
        key="delivery_pipeline_entries",
        label="交付管道",
        permission="delivery.pipeline.read",
        resource_code=RESOURCE_DELIVERY_PIPELINE,
        model_attr="DeliveryPipelineEntry",
        fields=(
            SourceFieldDef("position", "岗位", "text"),
            SourceFieldDef("result", "结果", "text"),
            SourceFieldDef("onboarded", "已入职", "text"),
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
            SourceFieldDef("monthly_quote_tax", "月报价(含税)", "numeric"),
            SourceFieldDef("pre_tax_salary", "税前工资", "numeric"),
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
            SourceFieldDef("fee_month", "费用月份", "text"),
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

SOURCE_KEYS: FrozenSet[str] = frozenset(DATA_SOURCES.keys())


def get_source(key: str) -> Optional[DataSourceDef]:
    return DATA_SOURCES.get(key)


def get_field(source_key: str, field_key: str) -> Optional[SourceFieldDef]:
    src = get_source(source_key)
    if not src:
        return None
    for f in src.fields:
        if f.key == field_key:
            return f
    return None


def build_metadata() -> dict:
    """Return whitelists for frontend config panel."""
    sources = []
    for src in DATA_SOURCES.values():
        sources.append({
            "key": src.key,
            "label": src.label,
            "fields": [{"key": f.key, "label": f.label, "kind": f.kind} for f in src.fields],
        })
    return {
        "sources": sources,
        "widget_types": sorted(WIDGET_TYPES),
        "chart_widget_types": sorted(CHART_WIDGET_TYPES),
        "metrics": sorted(METRICS),
        "filter_ops": sorted(FILTER_OPS),
        "date_groups": sorted(DATE_GROUPS),
        "colors": sorted(CHART_COLORS),
        "sorts": sorted(SORT_MODES),
    }
