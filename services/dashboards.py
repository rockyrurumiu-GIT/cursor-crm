"""Dashboard builder — CRUD, whitelisted aggregation, seed."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional, Tuple, Type
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func, not_, text
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth import service as auth_svc
from auth.service import AuthContext
from schemas.dashboards import (
    AXIS_NAME_DISPLAY,
    AXIS_SORT_MODES,
    CHART_COLORS,
    CHART_EXTRA_RENDERS,
    COLOR_SHADES,
    DEFAULT_AXIS_NAME_DISPLAY,
    DEFAULT_COLOR_SHADE,
    DEFAULT_DATE_GROUP,
    DEFAULT_GROUP_MODE,
    DEFAULT_PRIMARY_AXIS_SORT,
    DEFAULT_SECONDARY_AXIS_SORT,
    CHART_WIDGET_TYPES,
    DATA_WIDGET_TYPES,
    DATA_SOURCES,
    DATE_GROUPS,
    DEFAULT_COLOR,
    DEFAULT_SORT,
    FILTER_OPS,
    GROUP_MODES,
    METRICS,
    NUMERIC_METRICS,
    SECONDARY_AXIS_SORT_MODES,
    SORT_MODES,
    WIDGET_TYPES,
    RMS_BLOCK_KEYS,
    get_field,
    get_source,
)
from services.clients import scoped_client_query
from services import rms_dashboard as rms_dash
from services import rms_scope as rms_ds
from services.delivery_roster import sql_roster_employment_active_pool

FEATURED_VALUE_MODES: FrozenSet[str] = frozenset({"auto", "sum", "latest", "average"})
LINE1_VALUE_MODES: FrozenSet[str] = frozenset({"sum", "latest", "average", "max"})
LINE1_X_AXIS_MODES: FrozenSet[str] = frozenset({"all", "snapshot", "historical"})
PIPELINE_DATA_MODES: FrozenSet[str] = frozenset({"active", "loss", "total"})
PIPELINE_BUCKET_MODES: FrozenSet[str] = frozenset({"active", "loss"})
LINE1_ACTIVE_INDEX_MODES: FrozenSet[str] = frozenset({"first", "middle", "last"})
HIGHLIGHT_ITEM_MODES: FrozenSet[str] = frozenset({"max", "latest"})

from schemas.rms import (
    APPLICATION_PROGRESS_ORDER,
    RMS_ENUM_GROUP_FIELDS,
    RMS_FK_GROUP_FIELDS,
    resolve_rms_group_label,
)

_DEFAULT_SEED_NAME = "经营总览"
_ROSTER_SEED_NAME = "交付毛利总览"
_NUMERIC_RE = re.compile(r"^-?\d+(\.\d+)?$")

# Matches the roster footer math: 不含税月报价 = 含税月报价 / 1.0672 (see roster-detail.js TAX_DIVISOR).
ROSTER_TAX_DIVISOR = 1.0672

# model_attr -> key in models dict passed to service functions
MODEL_MAP_KEYS = {
    "Client": "Client",
    "Contact": "Contact",
    "Opportunity": "Opportunity",
    "VisitRecord": "VisitRecord",
    "HandoffRequest": "HandoffRequest",
    "RosterEntry": "RosterEntry",
    "DeliverySettlementEntry": "DeliverySettlementEntry",
    "DeliveryInterviewEntry": "DeliveryInterviewEntry",
    "RmsJob": "RmsJob",
    "RmsCandidate": "RmsCandidate",
    "RmsApplication": "RmsApplication",
}


def _now() -> datetime:
    return datetime.now()


def _parse_json(raw: str, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _dump_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _get_model(models: dict, source_key: str) -> Type[Any]:
    src = get_source(source_key)
    if not src:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source_key}")
    key = MODEL_MAP_KEYS.get(src.model_attr)
    if not key or key not in models:
        raise HTTPException(status_code=500, detail=f"数据源模型未注入: {source_key}")
    return models[key]


def source_permission(source_key: str) -> str:
    src = get_source(source_key)
    if not src:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source_key}")
    return src.permission


def user_can_read_source(ctx: AuthContext, source_key: str) -> bool:
    if not source_key:
        return True
    perm = source_permission(source_key)
    return auth_svc.user_has_permission(ctx, perm)


def validate_iframe_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="iframe URL 不能为空")
    if "<" in url or ">" in url:
        raise HTTPException(status_code=400, detail="iframe URL 不允许 HTML")
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="iframe 仅允许 https:// URL")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="iframe URL 无效")
    return url


def _validate_extra_views(raw: Any, widget_type: str) -> list:
    """Optional extra chart presentations for the same series data (chart widgets only)."""
    if widget_type not in CHART_WIDGET_TYPES:
        return []
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="extra_views 必须是数组")
    out: list = []
    for item in raw:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="extra_views 项必须是对象")
        render = (item.get("render") or "").strip()
        if render not in CHART_EXTRA_RENDERS:
            raise HTTPException(status_code=400, detail=f"未知 extra_views.render: {render}")
        try:
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            w = int(item.get("w", 4))
            h = int(item.get("h", 4))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="extra_views 布局坐标必须是整数")
        if x < 0 or x > 11:
            raise HTTPException(status_code=400, detail="extra_views.x 须在 0–11 之间")
        if w < 1 or w > 12 or x + w > 12:
            raise HTTPException(status_code=400, detail="extra_views.w 须在 1–12 且不可超出栅格")
        if y < 0:
            raise HTTPException(status_code=400, detail="extra_views.y 须 ≥ 0")
        if h < 1:
            raise HTTPException(status_code=400, detail="extra_views.h 须 ≥ 1")
        entry: dict = {"render": render, "x": x, "y": y, "w": w, "h": h}
        title = (item.get("title") or "").strip()
        if title:
            entry["title"] = title
        if render == "horizontal_bar":
            limit = item.get("limit")
            if limit is not None and limit != "":
                try:
                    limit = int(limit)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=400, detail="extra_views.limit 必须是整数")
                if limit < 1 or limit > 100:
                    raise HTTPException(status_code=400, detail="extra_views.limit 须在 1–100 之间")
                entry["limit"] = limit
        out.append(entry)
    return out


def validate_rich_text(content: str) -> str:
    text = (content or "").strip()
    if "<" in text or ">" in text:
        raise HTTPException(status_code=400, detail="rich_text 不允许 HTML")
    return text


_METRIC_LABELS = {"count": "计数", "sum": "求和", "avg": "平均", "min": "最小", "max": "最大"}
_SECONDARY_CHART_TYPES = frozenset({"bar", "horizontal_bar", "line", "featured_bar", "grouped_1"})


def _primary_sort_to_legacy(sort: str) -> str:
    return {
        "position_asc": "label_asc",
        "position_desc": "label_desc",
        "sum_asc": "value_asc",
        "sum_desc": "value_desc",
        "manual": "label_asc",
    }.get(sort, sort)


def _parse_range_value(raw: Any) -> str:
    if raw is None or raw == "":
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    try:
        float(s)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="range_min/range_max 必须是数字或空")
    return s


def _normalize_widget_config(config: dict) -> dict:
    """Dual-read: new fields preferred, legacy fields as fallback."""
    c = dict(config or {})

    aggregate_field = (c.get("aggregate_field") if c.get("aggregate_field") is not None else c.get("field") or "")
    aggregate_field = str(aggregate_field).strip()

    primary_axis_field = (
        c.get("primary_axis_field") if c.get("primary_axis_field") is not None else c.get("group_by") or ""
    )
    primary_axis_field = str(primary_axis_field).strip()

    date_group = str(c.get("date_group") or "").strip()
    if date_group and not primary_axis_field:
        primary_axis_field = str(c.get("group_by") or "created_at").strip()

    if "display_data_label" in c:
        display_data_label = bool(c.get("display_data_label"))
    else:
        display_data_label = bool(c.get("data_labels", False))

    if "display_legend" in c:
        display_legend = bool(c.get("display_legend"))
    else:
        display_legend = bool(c.get("show_legend", True))

    if "omit_null_values" in c:
        omit_null_values = bool(c.get("omit_null_values"))
    else:
        omit_null_values = bool(c.get("hide_empty", False))

    primary_axis_sort = str(
        c.get("primary_axis_sort") or c.get("sort") or DEFAULT_PRIMARY_AXIS_SORT
    ).strip()
    primary_axis_sort = {
        "value_asc": "sum_asc",
        "value_desc": "sum_desc",
    }.get(primary_axis_sort, primary_axis_sort)

    secondary_axis_field = str(c.get("secondary_axis_field") or "").strip()
    secondary_axis_sort = str(c.get("secondary_axis_sort") or DEFAULT_SECONDARY_AXIS_SORT).strip()
    group_mode = str(c.get("group_mode") or DEFAULT_GROUP_MODE).strip()
    axis_name_display = str(c.get("axis_name_display") or DEFAULT_AXIS_NAME_DISPLAY).strip()

    raw_order = c.get("primary_axis_order")
    primary_axis_order: list = []
    if isinstance(raw_order, list):
        for item in raw_order:
            s = str(item).strip()
            if s:
                primary_axis_order.append(s)

    out = {
        "metric": str(c.get("metric") or "count").strip(),
        "aggregate_field": aggregate_field,
        "field": aggregate_field,
        "primary_axis_field": primary_axis_field,
        "group_by": primary_axis_field,
        "date_group": date_group,
        "primary_axis_sort": primary_axis_sort,
        "sort": _primary_sort_to_legacy(primary_axis_sort),
        "secondary_axis_field": secondary_axis_field,
        "secondary_axis_sort": secondary_axis_sort,
        "omit_null_values": omit_null_values,
        "hide_empty": omit_null_values,
        "range_min": "" if c.get("range_min") in (None, "") else str(c.get("range_min")).strip(),
        "range_max": "" if c.get("range_max") in (None, "") else str(c.get("range_max")).strip(),
        "primary_axis_order": primary_axis_order,
        "group_mode": group_mode,
        "axis_name_display": axis_name_display,
        "display_data_label": display_data_label,
        "data_labels": display_data_label,
        "display_legend": display_legend,
        "show_legend": display_legend,
        "filters": c.get("filters") if isinstance(c.get("filters"), list) else [],
        "limit": c.get("limit", 20),
        "prefix": str(c.get("prefix") or ""),
        "suffix": str(c.get("suffix") or ""),
        "color": str(c.get("color") or DEFAULT_COLOR).strip(),
        "color_shade": c.get("color_shade", DEFAULT_COLOR_SHADE),
        "show_value_center": bool(c.get("show_value_center", True)),
        "extra_views": c.get("extra_views") if isinstance(c.get("extra_views"), list) else [],
        "comparison_label": str(c.get("comparison_label") or "较上期"),
        "average_label": str(c.get("average_label") or "Avg"),
        "show_average_line": bool(c.get("show_average_line", True)),
        "show_comparison": bool(c.get("show_comparison", True)),
        "highlight_latest": bool(c.get("highlight_latest", True)),
        "highlight_item": str(c.get("highlight_item") or "latest").strip(),
        "show_tooltip": bool(c.get("show_tooltip", True)),
        "show_grid": bool(c.get("show_grid", True)),
        "featured_value_mode": str(c.get("featured_value_mode") or "auto"),
        "show_point_values": bool(c.get("show_point_values", True)),
        "show_summary_legend": bool(c.get("show_summary_legend", True)),
        "show_group_composition": bool(c.get("show_group_composition", True)),
        "line1_value_mode": str(c.get("line1_value_mode") or "sum").strip(),
        "line1_x_axis_mode": str(c.get("line1_x_axis_mode") or "all"),
        "pipeline_data_mode": str(c.get("pipeline_data_mode") or "active").strip(),
        "line1_range_label": str(c.get("line1_range_label") or "Last 12 months"),
        "line1_active_index": str(c.get("line1_active_index") or "middle"),
        "show_line1_range": bool(c.get("show_line1_range", True)),
        "show_line1_fullscreen": bool(c.get("show_line1_fullscreen", True)),
        "show_line1_grid": bool(c.get("show_line1_grid", True)),
        "grouped_segment_limit": _clamp_int(c.get("grouped_segment_limit"), 1, 12, 12),
    }
    x_mode = out["line1_x_axis_mode"]
    if x_mode not in LINE1_X_AXIS_MODES:
        out["line1_x_axis_mode"] = "all"
    pipeline_mode = out["pipeline_data_mode"]
    if pipeline_mode not in PIPELINE_DATA_MODES:
        out["pipeline_data_mode"] = "active"
    fvm = out["featured_value_mode"]
    if fvm not in FEATURED_VALUE_MODES:
        out["featured_value_mode"] = "auto"
    lvm = out["line1_value_mode"]
    if lvm not in LINE1_VALUE_MODES:
        out["line1_value_mode"] = "sum"
    lai = out["line1_active_index"]
    if lai not in LINE1_ACTIVE_INDEX_MODES:
        out["line1_active_index"] = "middle"
    hi = out["highlight_item"]
    if hi not in HIGHLIGHT_ITEM_MODES:
        out["highlight_item"] = "latest"
    if "include_left" in c:
        out["include_left"] = bool(c.get("include_left"))
    if "client_id" in c:
        out["client_id"] = c.get("client_id")
    return out


def _axis_labels(source_key: str, config: dict) -> Tuple[str, str]:
    primary = config.get("primary_axis_field") or config.get("group_by") or ""
    metric = config.get("metric") or "count"
    x_label = ""
    if primary:
        if primary == "client":
            x_label = "客户"
        else:
            fdef = get_field(source_key, primary)
            x_label = fdef.label if fdef else primary
    y_label = _METRIC_LABELS.get(metric, metric)
    if metric != "count":
        agg = config.get("aggregate_field") or config.get("field") or ""
        fdef = get_field(source_key, agg)
        if fdef:
            y_label = f"{fdef.label}（{_METRIC_LABELS.get(metric, metric)}）"
    return x_label, y_label


RMS_PRESET_STYLE_BLOCKS: FrozenSet[str] = frozenset({
    "chart_pipeline",
    "chart_pending_backlog",
    "lifecycle_funnel",
    "chart_lifecycle_pass_rate",
    "chart_job_pending_backlog",
    "chart_client_hired_ranking",
    "chart_recruiter_recommend_vs_hired",
    "chart_pipeline_dialysis",
    "kpi_hc",
    "kpi_resume_to_hire_rate",
})
RMS_PRESET_STYLE_KEYS: FrozenSet[str] = frozenset({
    "color", "color_shade", "sort", "show_grid", "bar_radius", "max_items", "show_values", "palette",
    "chart_type", "metric",
    "comparison_label", "average_label", "show_average_line", "show_comparison", "highlight_latest",
    "highlight_item",
    "featured_value_mode", "show_point_values", "show_tooltip", "show_summary_legend",
    "show_group_composition",
    "pipeline_data_mode", "group_mode", "show_data_labels",
    "line1_value_mode", "line1_x_axis_mode", "line1_range_label", "line1_active_index",
    "show_line1_range", "show_line1_fullscreen", "show_line1_grid",
})
RMS_PRESET_CHART_TYPES: FrozenSet[str] = frozenset({"horizontal_bar", "bar", "pie", "line", "featured_line", "line_1", "featured_bar"})
RMS_LEGACY_PRESET_PALETTE: Dict[str, str] = {
    "green_3": "green",
    "blue_3": "blue",
    "orange_3": "orange",
    "gray_3": "gray",
}
RMS_PRESET_SORT_VALUES: FrozenSet[str] = frozenset({"value_desc", "value_asc", "original"})
RMS_PRESET_METRIC_VALUES: FrozenSet[str] = frozenset({"count", "pass_rate"})


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if n < lo or n > hi:
        return default
    return n


def _sanitize_rms_preset_style(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    color = raw.get("color")
    if not color or color not in CHART_COLORS:
        color = RMS_LEGACY_PRESET_PALETTE.get(raw.get("palette"), DEFAULT_COLOR)
        if color not in CHART_COLORS:
            color = DEFAULT_COLOR
    color_shade = _clamp_int(raw.get("color_shade"), 0, 4, DEFAULT_COLOR_SHADE)
    sort = raw.get("sort", "value_desc")
    if sort not in RMS_PRESET_SORT_VALUES:
        sort = "value_desc"
    chart_type = raw.get("chart_type", "horizontal_bar")
    if chart_type not in RMS_PRESET_CHART_TYPES:
        chart_type = "horizontal_bar"
    metric = raw.get("metric", "count")
    if metric not in RMS_PRESET_METRIC_VALUES:
        metric = "count"
    featured_value_mode = str(raw.get("featured_value_mode") or "auto")
    if featured_value_mode not in FEATURED_VALUE_MODES:
        featured_value_mode = "auto"
    comparison_label = str(raw.get("comparison_label") or "较上期").strip()[:32] or "较上期"
    average_label_raw = raw.get("average_label")
    average_label = str(average_label_raw).strip()[:32] if average_label_raw not in (None, "") else ""
    line1_value_mode = str(raw.get("line1_value_mode") or "sum").strip()
    if line1_value_mode not in LINE1_VALUE_MODES:
        line1_value_mode = "sum"
    line1_active_index = str(raw.get("line1_active_index") or "middle")
    if line1_active_index not in LINE1_ACTIVE_INDEX_MODES:
        line1_active_index = "middle"
    line1_range_label = str(raw.get("line1_range_label") or "Last 12 months").strip()[:64] or "Last 12 months"
    highlight_item = str(raw.get("highlight_item") or "latest").strip()
    if highlight_item not in HIGHLIGHT_ITEM_MODES:
        highlight_item = "latest"
    pipeline_data_mode = str(raw.get("pipeline_data_mode") or "active").strip()
    if pipeline_data_mode not in PIPELINE_DATA_MODES:
        pipeline_data_mode = "active"
    group_mode = str(raw.get("group_mode") or "grouped").strip()
    if group_mode not in ("stacked", "grouped"):
        group_mode = "grouped"
    return {
        "color": color,
        "color_shade": color_shade,
        "sort": sort,
        "chart_type": chart_type,
        "metric": metric,
        "show_grid": bool(raw.get("show_grid", True)),
        "show_values": bool(raw.get("show_values", False)),
        "bar_radius": _clamp_int(raw.get("bar_radius"), 4, 16, 8),
        "max_items": _clamp_int(raw.get("max_items"), 3, 20, 8),
        "comparison_label": comparison_label,
        "average_label": average_label,
        "show_average_line": bool(raw.get("show_average_line", True)),
        "show_comparison": bool(raw.get("show_comparison", True)),
        "highlight_latest": bool(raw.get("highlight_latest", True)),
        "highlight_item": highlight_item,
        "featured_value_mode": featured_value_mode,
        "show_point_values": bool(raw.get("show_point_values", False)),
        "show_tooltip": bool(raw.get("show_tooltip", True)),
        "show_summary_legend": bool(raw.get("show_summary_legend", True)),
        "show_group_composition": bool(raw.get("show_group_composition", True)),
        "line1_value_mode": line1_value_mode,
        "line1_range_label": line1_range_label,
        "line1_active_index": line1_active_index,
        "show_line1_range": bool(raw.get("show_line1_range", True)),
        "show_line1_fullscreen": bool(raw.get("show_line1_fullscreen", True)),
        "show_line1_grid": bool(raw.get("show_line1_grid", True)),
        "pipeline_data_mode": pipeline_data_mode,
        "group_mode": group_mode,
        "show_data_labels": bool(raw.get("show_data_labels", False)),
    }


def validate_widget_config(
    widget_type: str,
    source_key: str,
    config: dict,
    allowed_source_keys: Optional[FrozenSet[str]] = None,
) -> dict:
    if widget_type not in WIDGET_TYPES:
        raise HTTPException(status_code=400, detail=f"未知 widget 类型: {widget_type}")

    if widget_type == "iframe":
        return {"url": validate_iframe_url(config.get("url", ""))}

    if widget_type == "rich_text":
        return {"content": validate_rich_text(config.get("content", ""))}

    if widget_type == "roster_summary":
        if source_key != "roster_entries":
            raise HTTPException(status_code=400, detail="roster_summary 仅支持花名册数据源")
        out: dict = {"include_left": bool(config.get("include_left", False))}
        client_id = config.get("client_id")
        if client_id not in (None, "", 0):
            try:
                out["client_id"] = int(client_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="client_id 必须是整数")
        return out

    if widget_type == "rms_block":
        block = (config.get("block") or "").strip()
        if block not in RMS_BLOCK_KEYS:
            raise HTTPException(status_code=400, detail=f"未知 RMS 组件: {block}")
        out: dict = {"block": block}
        if block in RMS_PRESET_STYLE_BLOCKS and isinstance(config.get("style"), dict):
            out["style"] = _sanitize_rms_preset_style(config["style"])
        return out

    if widget_type not in DATA_WIDGET_TYPES:
        raise HTTPException(status_code=400, detail=f"widget 类型不支持数据配置: {widget_type}")

    if not source_key or not get_source(source_key):
        raise HTTPException(status_code=400, detail=f"未知数据源: {source_key}")
    if allowed_source_keys is not None and source_key not in allowed_source_keys:
        raise HTTPException(status_code=400, detail=f"数据源不可用: {source_key}")

    norm = _normalize_widget_config(config)

    metric = norm["metric"]
    if metric not in METRICS:
        raise HTTPException(status_code=400, detail=f"未知聚合方式: {metric}")

    aggregate_field = norm["aggregate_field"]
    if metric in NUMERIC_METRICS:
        if not aggregate_field:
            raise HTTPException(status_code=400, detail="sum/avg/min/max 需要指定 aggregate_field")
        fdef = get_field(source_key, aggregate_field)
        if not fdef or fdef.kind != "numeric":
            raise HTTPException(status_code=400, detail=f"字段不可用于数值聚合: {aggregate_field}")
    elif aggregate_field:
        fdef = get_field(source_key, aggregate_field)
        if not fdef:
            raise HTTPException(status_code=400, detail=f"未知字段: {aggregate_field}")

    primary_axis_field = norm["primary_axis_field"]
    date_group = norm["date_group"]
    secondary_axis_field = norm["secondary_axis_field"]

    if primary_axis_field and primary_axis_field != "client":
        pdef = get_field(source_key, primary_axis_field)
        if not pdef:
            raise HTTPException(status_code=400, detail=f"未知 primary_axis_field: {primary_axis_field}")
        if pdef.kind == "datetime" and not date_group:
            date_group = DEFAULT_DATE_GROUP
            norm["date_group"] = date_group

    if date_group:
        if date_group not in DATE_GROUPS:
            raise HTTPException(status_code=400, detail=f"未知 date_group: {date_group}")
        if not primary_axis_field:
            primary_axis_field = "created_at"
            norm["primary_axis_field"] = primary_axis_field
            norm["group_by"] = primary_axis_field
        dgdef = get_field(source_key, primary_axis_field)
        if not dgdef or dgdef.kind != "datetime":
            raise HTTPException(status_code=400, detail="date_group 仅支持 datetime 类型的 primary_axis_field")

    if secondary_axis_field:
        if widget_type == "line_1":
            raise HTTPException(status_code=400, detail="折线1暂不支持二级分组")
        if widget_type in ("pie", "number", "featured_line"):
            raise HTTPException(status_code=400, detail=f"{widget_type} 不支持 secondary_axis_field")
        if widget_type not in _SECONDARY_CHART_TYPES:
            raise HTTPException(status_code=400, detail=f"{widget_type} 不支持 secondary_axis_field")
        sdef = get_field(source_key, secondary_axis_field)
        if not sdef:
            raise HTTPException(status_code=400, detail=f"未知 secondary_axis_field: {secondary_axis_field}")
        if sdef.kind == "datetime":
            raise HTTPException(status_code=400, detail="secondary_axis_field 不支持 datetime")

    filters = norm.get("filters") or []
    clean_filters = []
    for flt in filters:
        if not isinstance(flt, dict):
            raise HTTPException(status_code=400, detail="filter 项必须是对象")
        op = (flt.get("op") or "").strip()
        fname = (flt.get("field") or "").strip()
        if op not in FILTER_OPS:
            raise HTTPException(status_code=400, detail=f"未知 filter op: {op}")
        fdef = get_field(source_key, fname)
        if not fdef:
            raise HTTPException(status_code=400, detail=f"未知 filter 字段: {fname}")
        clean_filters.append({"field": fname, "op": op, "value": flt.get("value", "")})

    try:
        limit = int(norm.get("limit") or 20)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="limit 必须是整数")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit 须在 1–100 之间")

    if widget_type in CHART_WIDGET_TYPES and not primary_axis_field:
        raise HTTPException(status_code=400, detail="图表 widget 需要 primary_axis_field")

    primary_axis_sort = norm["primary_axis_sort"]
    if primary_axis_sort not in AXIS_SORT_MODES:
        raise HTTPException(status_code=400, detail=f"未知 primary_axis_sort: {primary_axis_sort}")

    secondary_axis_sort = norm["secondary_axis_sort"]
    if secondary_axis_sort not in SECONDARY_AXIS_SORT_MODES:
        raise HTTPException(status_code=400, detail=f"未知 secondary_axis_sort: {secondary_axis_sort}")

    group_mode = norm["group_mode"]
    if group_mode not in GROUP_MODES:
        raise HTTPException(status_code=400, detail=f"未知 group_mode: {group_mode}")

    axis_name_display = norm["axis_name_display"]
    if axis_name_display not in AXIS_NAME_DISPLAY:
        raise HTTPException(status_code=400, detail=f"未知 axis_name_display: {axis_name_display}")

    range_min = _parse_range_value(norm.get("range_min"))
    range_max = _parse_range_value(norm.get("range_max"))

    color = norm["color"]
    if color not in CHART_COLORS:
        raise HTTPException(status_code=400, detail=f"未知配色: {color}")

    try:
        color_shade = int(norm.get("color_shade", DEFAULT_COLOR_SHADE))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="color_shade 必须是 0–4 的整数")
    if color_shade not in COLOR_SHADES:
        raise HTTPException(status_code=400, detail="color_shade 须在 0–4 之间")

    legacy_sort = _primary_sort_to_legacy(primary_axis_sort)
    if legacy_sort not in SORT_MODES:
        legacy_sort = DEFAULT_SORT

    raw_order = norm.get("primary_axis_order")
    primary_axis_order: list = []
    if raw_order is not None:
        if not isinstance(raw_order, list):
            raise HTTPException(status_code=400, detail="primary_axis_order 必须是数组")
        for item in raw_order:
            s = str(item).strip()
            if s:
                primary_axis_order.append(s)

    if widget_type == "featured_line" and norm.get("extra_views"):
        raise HTTPException(status_code=400, detail="featured_line 不支持 extra_views")

    if widget_type == "line_1" and norm.get("extra_views"):
        raise HTTPException(status_code=400, detail="折线1不支持 extra_views")

    if widget_type == "featured_bar" and norm.get("extra_views"):
        raise HTTPException(status_code=400, detail="featured_bar 不支持 extra_views")

    if widget_type == "grouped_1" and norm.get("extra_views"):
        raise HTTPException(status_code=400, detail="grouped_1 不支持 extra_views")

    average_label = str(norm.get("average_label") or "Avg").strip()[:32] or "Avg"

    out = {
        "metric": metric,
        "aggregate_field": aggregate_field,
        "field": aggregate_field,
        "primary_axis_field": primary_axis_field,
        "group_by": primary_axis_field,
        "primary_axis_sort": primary_axis_sort,
        "sort": legacy_sort,
        "primary_axis_order": primary_axis_order,
        "secondary_axis_field": secondary_axis_field,
        "secondary_axis_sort": secondary_axis_sort,
        "omit_null_values": norm["omit_null_values"],
        "hide_empty": norm["omit_null_values"],
        "range_min": range_min,
        "range_max": range_max,
        "group_mode": group_mode,
        "axis_name_display": axis_name_display,
        "display_data_label": norm["display_data_label"],
        "data_labels": norm["display_data_label"],
        "display_legend": norm["display_legend"],
        "show_legend": norm["display_legend"],
        "filters": clean_filters,
        "limit": limit,
        "prefix": norm["prefix"],
        "suffix": norm["suffix"],
        "color": color,
        "color_shade": color_shade,
        "show_value_center": norm["show_value_center"],
        "comparison_label": norm["comparison_label"],
        "average_label": average_label,
        "show_average_line": norm["show_average_line"],
        "show_comparison": norm["show_comparison"],
        "highlight_latest": norm["highlight_latest"],
        "show_tooltip": norm["show_tooltip"],
        "featured_value_mode": norm["featured_value_mode"],
        "show_point_values": norm["show_point_values"],
        "extra_views": _validate_extra_views(norm.get("extra_views"), widget_type),
    }
    if widget_type == "line_1":
        out["line1_value_mode"] = norm["line1_value_mode"]
        out["line1_x_axis_mode"] = norm["line1_x_axis_mode"]
        out["line1_range_label"] = str(norm["line1_range_label"] or "Last 12 months").strip()[:64] or "Last 12 months"
        out["line1_active_index"] = norm["line1_active_index"]
        out["show_line1_range"] = bool(norm.get("show_line1_range", True))
        out["show_line1_fullscreen"] = bool(norm.get("show_line1_fullscreen", True))
        out["show_line1_grid"] = bool(norm.get("show_line1_grid", True))
    if widget_type == "featured_bar":
        out["show_summary_legend"] = bool(norm.get("show_summary_legend", True))
        out["show_grid"] = bool(norm.get("show_grid", True))
        out["highlight_item"] = norm["highlight_item"]
    if widget_type == "grouped_1":
        out["show_summary_legend"] = bool(norm.get("show_summary_legend", True))
        out["show_grid"] = bool(norm.get("show_grid", True))
    if secondary_axis_field:
        out["show_group_composition"] = bool(norm.get("show_group_composition", True))
        out["pipeline_data_mode"] = norm["pipeline_data_mode"]
        if widget_type == "grouped_1" and group_mode == "stacked":
            out["grouped_segment_limit"] = _clamp_int(norm.get("grouped_segment_limit"), 1, 12, 12)
    if date_group:
        out["date_group"] = date_group
    if source_key == "roster_entries":
        out["include_left"] = bool(norm.get("include_left", False))
    return out


def _apply_roster_active_pool(q, source_key: str, config: dict, Model: Type[Any]):
    """Dashboard roster stats default to 在职池; set include_left to count 离职档案 too."""
    if source_key != "roster_entries":
        return q
    if bool(config.get("include_left", False)):
        return q
    return q.filter(sql_roster_employment_active_pool(Model))


def _scoped_query(
    db: Session,
    ctx: AuthContext,
    source_key: str,
    models: dict,
):
    src = get_source(source_key)
    if not src:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source_key}")
    Model = _get_model(models, source_key)
    q = db.query(Model)
    if source_key == "clients":
        return scoped_client_query(db, ctx, models["Client"], action="read")
    if source_key == "rms_jobs":
        return rms_ds.scoped_jobs_query(
            db, ctx, models["RmsJob"], models["Client"], action="read"
        )
    if source_key == "rms_applications":
        return rms_ds.scoped_applications_query(
            db, ctx, models["RmsApplication"], models["Client"], action="read"
        )
    if source_key == "rms_candidates":
        RmsCandidate = models["RmsCandidate"]
        visible = rms_ds.visible_candidate_ids(
            db,
            ctx,
            RmsCandidate,
            models["RmsApplication"],
            models["Client"],
        )
        if visible is None:
            return q
        if not visible:
            return q.filter(RmsCandidate.id == -1)
        return q.filter(RmsCandidate.id.in_(visible))
    if src.has_client_id:
        return ds.filter_query_by_client_scope(
            q,
            db,
            ctx,
            src.resource_code,
            "read",
            Model.client_id,
            models["Client"],
        )
    return q


def _column(Model: Type[Any], field_key: str):
    col = getattr(Model, field_key, None)
    if col is None:
        raise HTTPException(status_code=400, detail=f"字段不存在: {field_key}")
    return col


def _parse_numeric(raw: Any) -> Optional[float]:
    s = str(raw or "").strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not s or not _NUMERIC_RE.match(s):
        return None
    try:
        return float(s)
    except ValueError:
        return None


_USER_FK_FILTER_FIELDS: FrozenSet[Tuple[str, str]] = frozenset({
    ("rms_applications", "recommended_by"),
    ("rms_jobs", "owner_user_id"),
})


def _is_user_fk_filter_field(source_key: Optional[str], field_key: str) -> bool:
    return bool(source_key) and (source_key, field_key) in _USER_FK_FILTER_FIELDS


def _lookup_user_ids_for_filter(db: Session, raw_value: Any, op: str) -> List[int]:
    """Resolve sys_user ids from numeric ids and/or username/display_name tokens."""
    if raw_value is None:
        return []

    if op == "in":
        tokens = [p.strip() for p in str(raw_value).split(",") if p.strip()]
    else:
        text_val = str(raw_value).strip()
        if not text_val:
            return []
        tokens = [text_val]

    ids: List[int] = []
    text_tokens: List[str] = []
    for token in tokens:
        try:
            ids.append(int(token))
        except (TypeError, ValueError):
            text_tokens.append(token)

    if not text_tokens:
        return list(dict.fromkeys(ids))

    match_mode = "contains" if op in ("contains", "not_contains") else "exact"
    for token in text_tokens:
        if match_mode == "contains":
            pattern = f"%{token.lower()}%"
            rows = db.execute(
                text(
                    "SELECT id FROM sys_user WHERE "
                    "LOWER(username) LIKE :pat OR LOWER(COALESCE(display_name, '')) LIKE :pat"
                ),
                {"pat": pattern},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT id FROM sys_user WHERE "
                    "LOWER(username) = LOWER(:tok) OR LOWER(COALESCE(display_name, '')) = LOWER(:tok)"
                ),
                {"tok": token},
            ).fetchall()
        ids.extend(int(row[0]) for row in rows)
    return list(dict.fromkeys(ids))


def _apply_user_fk_filter(q, col, op: str, user_ids: List[int]):
    if op == "eq":
        if not user_ids:
            return q.filter(col == -1)
        if len(user_ids) == 1:
            return q.filter(col == user_ids[0])
        return q.filter(col.in_(user_ids))
    if op == "in":
        return q.filter(col.in_(user_ids or [-1]))
    if op == "contains":
        return q.filter(col.in_(user_ids or [-1]))
    if op == "not_contains":
        if not user_ids:
            return q
        return q.filter(~col.in_(user_ids))
    return None


def _apply_filters(
    q,
    Model: Type[Any],
    filters: list,
    *,
    db: Optional[Session] = None,
    source_key: Optional[str] = None,
):
    for flt in filters:
        field = flt["field"]
        val = flt.get("value", "")
        op = flt["op"]
        col = _column(Model, field)

        if db is not None and _is_user_fk_filter_field(source_key, field):
            user_ids = _lookup_user_ids_for_filter(db, val, op)
            user_q = _apply_user_fk_filter(q, col, op, user_ids)
            if user_q is not None:
                q = user_q
                continue

        if op == "eq":
            q = q.filter(col == val)
        elif op == "ne":
            q = q.filter(col != val)
        elif op == "contains":
            q = q.filter(col.like(f"%{val}%"))
        elif op == "not_contains":
            q = q.filter(~col.like(f"%{val}%"))
        elif op == "gt":
            q = q.filter(col > val)
        elif op == "gte":
            q = q.filter(col >= val)
        elif op == "lt":
            q = q.filter(col < val)
        elif op == "lte":
            q = q.filter(col <= val)
        elif op == "in":
            parts = [p.strip() for p in str(val).split(",") if p.strip()]
            q = q.filter(col.in_(parts))
    return q


def _narrow_apps_by_widget_filters(
    db: Session,
    source_key: str,
    filters: list,
    models: dict,
    apps: List[Any],
) -> List[Any]:
    if not filters or not apps:
        return apps
    Model = _get_model(models, source_key)
    app_ids = [getattr(app, "id", None) for app in apps]
    app_ids = [aid for aid in app_ids if aid is not None]
    if not app_ids:
        return []
    q = db.query(Model).filter(Model.id.in_(app_ids))
    q = _apply_filters(q, Model, filters, db=db, source_key=source_key)
    allowed = {row[0] for row in q.with_entities(Model.id).all()}
    return [app for app in apps if getattr(app, "id", None) in allowed]


def _date_bucket(col, date_group: str):
    if date_group == "day":
        return func.strftime("%Y-%m-%d", col)
    if date_group == "week":
        return func.strftime("%Y-W%W", col)
    if date_group == "month":
        return func.strftime("%Y-%m", col)
    if date_group == "year":
        return func.strftime("%Y", col)
    return func.strftime("%Y-%m", col)


def _aggregate_rows(rows: list, metric: str, field_key: str) -> float:
    if metric == "count":
        return float(len(rows))
    nums = []
    for row in rows:
        v = _parse_numeric(getattr(row, field_key, None))
        if v is not None:
            nums.append(v)
    if not nums:
        return 0.0
    if metric == "sum":
        return sum(nums)
    if metric == "avg":
        return sum(nums) / len(nums)
    if metric == "min":
        return min(nums)
    if metric == "max":
        return max(nums)
    return 0.0


def _rms_fk_label_map(
    db: Session,
    source_key: str,
    field_key: str,
    raw_labels: list,
    models: dict,
) -> dict[str, str]:
    ids: list[int] = []
    for lb in raw_labels:
        s = str(lb).strip()
        if not s or s == "(空)":
            continue
        try:
            ids.append(int(s))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {}

    key = (source_key, field_key)
    if key in {("rms_jobs", "client_id"), ("rms_applications", "client_id")}:
        Client = models.get("Client")
        if not Client:
            return {}
        return {
            str(r.id): (r.name or f"#{r.id}")
            for r in db.query(Client).filter(Client.id.in_(ids)).all()
        }
    if key == ("rms_applications", "job_id"):
        RmsJob = models.get("RmsJob")
        if not RmsJob:
            return {}
        return {
            str(r.id): (r.title or f"#{r.id}")
            for r in db.query(RmsJob).filter(RmsJob.id.in_(ids)).all()
        }
    if key == ("rms_applications", "candidate_id"):
        RmsCandidate = models.get("RmsCandidate")
        if not RmsCandidate:
            return {}
        return {
            str(r.id): (r.name or f"#{r.id}")
            for r in db.query(RmsCandidate).filter(RmsCandidate.id.in_(ids)).all()
        }
    if key in {("rms_jobs", "owner_user_id"), ("rms_applications", "recommended_by")}:
        id_list = ",".join(str(i) for i in ids)
        rows = db.execute(
            text(
                f"SELECT id, COALESCE(NULLIF(display_name, ''), username) AS label "
                f"FROM sys_user WHERE id IN ({id_list})"
            ),
        ).fetchall()
        return {str(r[0]): (str(r[1]).strip() or f"#{r[0]}") for r in rows}
    return {}


def _display_group_labels(
    labels: list,
    source_key: str,
    group_by: str,
    db: Session,
    models: dict,
) -> list:
    if not group_by or group_by == "client":
        return labels
    if (source_key, group_by) in RMS_ENUM_GROUP_FIELDS:
        return [resolve_rms_group_label(source_key, group_by, lb) for lb in labels]
    if (source_key, group_by) in RMS_FK_GROUP_FIELDS:
        fk_map = _rms_fk_label_map(db, source_key, group_by, labels, models)
        if fk_map:
            return [
                fk_map.get(str(lb), str(lb)) if str(lb) != "(空)" else "(空)"
                for lb in labels
            ]
    return labels


def _merge_by_display_labels(
    raw_labels: list,
    values: list,
    source_key: str,
    group_by: str,
    db: Session,
    models: dict,
) -> Tuple[list, list]:
    """Combine buckets whose raw keys resolve to the same display label."""
    merged: Dict[str, float] = {}
    for rl, val in zip(raw_labels, values):
        dl = _display_group_labels([str(rl)], source_key, group_by, db, models)[0]
        merged[dl] = merged.get(dl, 0.0) + float(val)
    labels = list(merged.keys())
    out_values = [merged[l] for l in labels]
    return labels, out_values


def _resolve_sort_mode(config: dict) -> str:
    return str(config.get("primary_axis_sort") or DEFAULT_PRIMARY_AXIS_SORT).strip()


def _field_position_label_order(source_key: str, field_key: str) -> Optional[Dict[str, int]]:
    if source_key == "rms_applications" and field_key in ("current_stage", "status"):
        return {
            resolve_rms_group_label(source_key, field_key, s): i
            for i, s in enumerate(APPLICATION_PROGRESS_ORDER)
        }
    return None


def _sort_display_pairs(
    pairs: list,
    sort_mode: str,
    source_key: str,
    field_key: str,
    manual_order: Optional[list] = None,
) -> list:
    if not pairs:
        return pairs
    if sort_mode == "manual":
        return _apply_manual_order(pairs, manual_order or [])
    if sort_mode in ("position_asc", "position_desc"):
        order_map = _field_position_label_order(source_key, field_key)
        if order_map:
            reverse = sort_mode == "position_desc"
            return sorted(pairs, key=lambda p: order_map.get(str(p[0]), 9999), reverse=reverse)
        sort_mode = "label_asc" if sort_mode == "position_asc" else "label_desc"
    return _sort_label_pairs(pairs, sort_mode)


def _order_entries_by_sorted_pairs(entries: list, sorted_pairs: list) -> list:
    """Reorder {pl, val, pk} entries to match sorted (label, value) pairs."""
    if not entries:
        return entries
    used: set = set()
    ordered = []
    for pl, val in sorted_pairs:
        matched = False
        for i, e in enumerate(entries):
            if i in used:
                continue
            if e["pl"] == pl and e["val"] == val:
                ordered.append(e)
                used.add(i)
                matched = True
                break
        if matched:
            continue
        for i, e in enumerate(entries):
            if i in used:
                continue
            if e["pl"] == pl:
                ordered.append(e)
                used.add(i)
                break
    for i, e in enumerate(entries):
        if i not in used:
            ordered.append(e)
    return ordered


def _sort_label_pairs(pairs: list, sort_mode: str) -> list:
    if sort_mode == "label_asc":
        return sorted(pairs, key=lambda x: str(x[0]))
    if sort_mode == "label_desc":
        return sorted(pairs, key=lambda x: str(x[0]), reverse=True)
    if sort_mode in ("value_asc", "sum_asc"):
        return sorted(pairs, key=lambda x: x[1])
    if sort_mode in ("value_desc", "sum_desc"):
        return sorted(pairs, key=lambda x: x[1], reverse=True)
    return pairs


def _apply_manual_order(pairs: list, manual_order: list) -> list:
    if not manual_order:
        return pairs
    order_map = {str(label): idx for idx, label in enumerate(manual_order)}
    max_idx = len(manual_order)
    known = [p for p in pairs if str(p[0]) in order_map]
    unknown = [p for p in pairs if str(p[0]) not in order_map]
    known.sort(key=lambda p: order_map[str(p[0])])
    unknown.sort(key=lambda p: str(p[0]))
    return known + unknown


def _resolve_field_label(
    raw: Any,
    source_key: str,
    field_key: str,
    db: Session,
    models: dict,
) -> str:
    if field_key == "client":
        return str(raw) if raw else "(未知客户)"
    s = str(raw or "(空)")
    if s == "(空)":
        return "(空)"
    if (source_key, field_key) in RMS_ENUM_GROUP_FIELDS:
        return resolve_rms_group_label(source_key, field_key, s)
    if (source_key, field_key) in RMS_FK_GROUP_FIELDS:
        fk_map = _rms_fk_label_map(db, source_key, field_key, [s], models)
        return fk_map.get(s, s)
    return s


def _finalize_series(
    labels: list,
    values: list,
    hide_empty: bool,
    limit: int,
    prefix: str,
    suffix: str,
    x_axis_label: str = "",
    y_axis_label: str = "",
) -> dict:
    pairs = list(zip(labels, values))
    if hide_empty:
        pairs = [(l, v) for (l, v) in pairs if v]
    pairs = pairs[:limit]
    out_labels = [p[0] for p in pairs]
    out_values = [p[1] for p in pairs]
    return {
        "status": "ok",
        "kind": "series",
        "labels": out_labels,
        "values": out_values,
        "total": sum(out_values),
        "prefix": prefix,
        "suffix": suffix,
        "xAxisLabel": x_axis_label,
        "yAxisLabel": y_axis_label,
    }


def _finalize_sorted_series(
    labels: list,
    values: list,
    sort_mode: str,
    source_key: str,
    field_key: str,
    hide_empty: bool,
    limit: int,
    prefix: str,
    suffix: str,
    manual_order: Optional[list] = None,
    x_axis_label: str = "",
    y_axis_label: str = "",
) -> dict:
    pairs = _sort_display_pairs(list(zip(labels, values)), sort_mode, source_key, field_key, manual_order)
    sorted_labels = [p[0] for p in pairs]
    sorted_values = [p[1] for p in pairs]
    return _finalize_series(
        sorted_labels,
        sorted_values,
        hide_empty,
        limit,
        prefix,
        suffix,
        x_axis_label=x_axis_label,
        y_axis_label=y_axis_label,
    )


def _finalize_grouped_series(
    primary_labels: list,
    secondary_labels: list,
    matrix: Dict[str, Dict[str, float]],
    group_mode: str,
    prefix: str,
    suffix: str,
    x_axis_label: str,
    y_axis_label: str,
    hide_empty: bool,
    limit: int,
) -> dict:
    data_rows = []
    for pl in primary_labels:
        sec_map = matrix.get(pl, {})
        row: dict = {"label": pl}
        for sl in secondary_labels:
            row[sl] = sec_map.get(sl, 0.0)
        if hide_empty and not any(row.get(sl, 0) for sl in secondary_labels):
            continue
        data_rows.append(row)
    data_rows = data_rows[:limit]
    out_primary = [r["label"] for r in data_rows]
    series = [{"key": sl, "label": sl} for sl in secondary_labels]
    return {
        "status": "ok",
        "kind": "grouped_series",
        "labels": out_primary,
        "indexBy": "label",
        "keys": secondary_labels,
        "series": series,
        "data": data_rows,
        "groupMode": group_mode,
        "xAxisLabel": x_axis_label,
        "yAxisLabel": y_axis_label,
        "prefix": prefix,
        "suffix": suffix,
    }


def _bucket_rows_dual(
    rows: list,
    primary_field: str,
    secondary_field: str,
    date_group: str,
    Model: Type[Any],
) -> Dict[Any, Dict[Any, list]]:
    buckets: Dict[Any, Dict[Any, list]] = {}
    primary_col = None if primary_field == "client" else _column(Model, primary_field)
    secondary_col = None if secondary_field == "client" else _column(Model, secondary_field)
    for row in rows:
        if primary_field == "client":
            pk = getattr(row, "client_id", None)
        elif date_group and primary_field:
            col = _column(Model, primary_field)
            raw = getattr(row, primary_field, None)
            pk = _date_bucket_value(raw, date_group)
        else:
            pk = getattr(row, primary_field, None)
        if secondary_field == "client":
            sk = getattr(row, "client_id", None)
        else:
            sk = getattr(row, secondary_field, None)
        pk = pk if pk is not None else "(空)"
        sk = sk if sk is not None else "(空)"
        buckets.setdefault(pk, {}).setdefault(sk, []).append(row)
    return buckets


def _date_bucket_value(raw: Any, date_group: str) -> str:
    if raw is None:
        return "(空)"
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = str(raw).strip()
        if not s:
            return "(空)"
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00")[:19])
        except ValueError:
            return s
    if date_group == "day":
        return dt.strftime("%Y-%m-%d")
    if date_group == "week":
        return dt.strftime("%Y-W%W")
    if date_group == "month":
        return dt.strftime("%Y-%m")
    if date_group == "year":
        return dt.strftime("%Y")
    return dt.strftime("%Y-%m")


def _query_grouped_series(
    db: Session,
    source_key: str,
    config: dict,
    models: dict,
    q,
    Model: Type[Any],
) -> dict:
    primary = config.get("primary_axis_field") or config.get("group_by") or ""
    secondary = config.get("secondary_axis_field") or ""
    metric = config.get("metric", "count")
    field_key = config.get("aggregate_field") or config.get("field") or ""
    date_group = config.get("date_group") or ""
    primary_sort = _resolve_sort_mode(config)
    secondary_sort = config.get("secondary_axis_sort") or DEFAULT_SECONDARY_AXIS_SORT
    hide_empty = bool(config.get("omit_null_values") or config.get("hide_empty"))
    limit = int(config.get("limit") or 20)
    prefix = config.get("prefix", "")
    suffix = config.get("suffix", "")
    group_mode = config.get("group_mode") or DEFAULT_GROUP_MODE
    x_axis_label, y_axis_label = _axis_labels(source_key, config)

    use_python = (
        metric != "count"
        or bool(date_group)
        or primary == "client"
        or secondary == "client"
    )

    matrix_raw: Dict[Any, Dict[Any, float]] = {}

    if use_python:
        rows = q.all()
        buckets = _bucket_rows_dual(rows, primary, secondary, date_group, Model)
        for pk, sec_buckets in buckets.items():
            matrix_raw.setdefault(pk, {})
            for sk, bucket_rows in sec_buckets.items():
                if metric == "count":
                    matrix_raw[pk][sk] = float(len(bucket_rows))
                else:
                    matrix_raw[pk][sk] = _aggregate_rows(bucket_rows, metric, field_key)
    else:
        pcol = _column(Model, primary)
        scol = _column(Model, secondary)
        agg = func.count().label("cnt") if metric == "count" else None
        if metric == "count":
            rows = (
                q.with_entities(pcol.label("pl"), scol.label("sl"), func.count().label("cnt"))
                .group_by(pcol, scol)
                .all()
            )
            for r in rows:
                pk = r.pl if r.pl is not None else "(空)"
                sk = r.sl if r.sl is not None else "(空)"
                matrix_raw.setdefault(pk, {})[sk] = float(r.cnt)
        else:
            rows = q.all()
            buckets = _bucket_rows_dual(rows, primary, secondary, date_group, Model)
            for pk, sec_buckets in buckets.items():
                matrix_raw.setdefault(pk, {})
                for sk, bucket_rows in sec_buckets.items():
                    matrix_raw[pk][sk] = _aggregate_rows(bucket_rows, metric, field_key)

    # Resolve client names for client axis
    Client = models.get("Client")
    if Client and (primary == "client" or secondary == "client"):
        all_cids = set()
        for pk, sec in matrix_raw.items():
            if primary == "client" and pk != "(空)":
                try:
                    all_cids.add(int(pk))
                except (TypeError, ValueError):
                    pass
            if secondary == "client":
                for sk in sec:
                    if sk != "(空)":
                        try:
                            all_cids.add(int(sk))
                        except (TypeError, ValueError):
                            pass
        name_map = {}
        if all_cids:
            for cid, cname in db.query(Client.id, Client.name).filter(Client.id.in_(all_cids)).all():
                name_map[cid] = cname
        remapped: Dict[Any, Dict[Any, float]] = {}
        for pk, sec in matrix_raw.items():
            if primary == "client":
                disp_p = name_map.get(int(pk), "(未知客户)") if pk != "(空)" else "(空)"
            else:
                disp_p = pk
            remapped.setdefault(disp_p, {})
            for sk, val in sec.items():
                if secondary == "client":
                    disp_s = name_map.get(int(sk), "(未知客户)") if sk != "(空)" else "(空)"
                else:
                    disp_s = sk
                remapped[disp_p][disp_s] = remapped[disp_p].get(disp_s, 0) + val
        matrix_raw = remapped
        primary_raw_keys = list(matrix_raw.keys())
        secondary_raw_set: set = set()
        for sec in matrix_raw.values():
            secondary_raw_set.update(sec.keys())
        secondary_raw_keys = list(secondary_raw_set)
    else:
        primary_raw_keys = list(matrix_raw.keys())
        secondary_raw_set: set = set()
        for sec in matrix_raw.values():
            secondary_raw_set.update(sec.keys())
        secondary_raw_keys = list(secondary_raw_set)

    manual_order = config.get("primary_axis_order") or []

    entries = []
    for pk in primary_raw_keys:
        if primary == "client":
            pl = str(pk)
        else:
            pl = _resolve_field_label(pk, source_key, primary, db, models)
        entries.append({"pk": pk, "pl": pl, "val": sum(matrix_raw.get(pk, {}).values())})

    if not (date_group and primary_sort in ("position_asc", "position_desc")):
        sorted_pairs = _sort_display_pairs(
            [(e["pl"], e["val"]) for e in entries],
            primary_sort,
            source_key,
            primary,
            manual_order,
        )
        entries = _order_entries_by_sorted_pairs(entries, sorted_pairs)

    primary_raw_keys = [e["pk"] for e in entries]
    primary_labels = [e["pl"] for e in entries]

    if secondary == "client":
        secondary_display = [str(sk) for sk in secondary_raw_keys]
    else:
        secondary_display = [
            _resolve_field_label(sk, source_key, secondary, db, models)
            for sk in secondary_raw_keys
        ]

    sec_pairs = list(zip(secondary_raw_keys, secondary_display))
    if secondary_sort == "label_desc":
        sec_pairs.sort(key=lambda x: str(x[1]), reverse=True)
    else:
        sec_pairs.sort(key=lambda x: str(x[1]))
    secondary_raw_keys = [p[0] for p in sec_pairs]
    secondary_display = [p[1] for p in sec_pairs]

    matrix: Dict[str, Dict[str, float]] = {}
    for pk, pl in zip(primary_raw_keys, primary_labels):
        matrix[pl] = {}
        raw_sec = matrix_raw.get(pk, {})
        for sr, sd in zip(secondary_raw_keys, secondary_display):
            matrix[pl][sd] = raw_sec.get(sr, 0.0)

    return _finalize_grouped_series(
        primary_labels,
        secondary_display,
        matrix,
        group_mode,
        prefix,
        suffix,
        x_axis_label,
        y_axis_label,
        hide_empty,
        limit,
    )


def _apply_rms_dashboard_filters(
    q,
    db: Session,
    ctx: AuthContext,
    source_key: str,
    dashboard_filters: Optional[dict],
    models: dict,
):
    """Intersect widget query with RMS dashboard top-bar filters."""
    if not dashboard_filters or source_key != "rms_applications":
        return q
    RmsApplication = models["RmsApplication"]
    RmsJob = models.get("RmsJob")
    Client = models.get("Client")
    if RmsJob is None or Client is None:
        return q
    filtered_q = rms_dash._filter_applications_query(
        db, ctx, RmsApplication, RmsJob, Client, dashboard_filters
    )
    ids = [row[0] for row in filtered_q.with_entities(RmsApplication.id).all()]
    if not ids:
        return q.filter(RmsApplication.id == -1)
    return q.filter(RmsApplication.id.in_(ids))


def _query_line1_rms_axis_series(
    db: Session,
    ctx: AuthContext,
    source_key: str,
    config: dict,
    models: dict,
    dashboard_filters: Optional[dict],
) -> dict:
    config = _normalize_widget_config(config)
    metric = config.get("metric", "count")
    if metric != "count":
        raise HTTPException(status_code=400, detail="折线1时点/历史状态仅支持计数")
    group_by = config.get("primary_axis_field") or config.get("group_by") or ""
    if group_by not in ("current_stage", "status"):
        raise HTTPException(status_code=400, detail="折线1时点/历史状态需要 X 轴字段为当前阶段或状态")

    RmsApplication = models["RmsApplication"]
    RmsJob = models["RmsJob"]
    Client = models["Client"]
    RmsApplicationStatusHistory = models["RmsApplicationStatusHistory"]
    filters = dict(dashboard_filters or {})
    apps = rms_dash._scoped_apps(db, ctx, RmsApplication, RmsJob, Client, filters)
    widget_filters = config.get("filters") or []
    if widget_filters:
        apps = _narrow_apps_by_widget_filters(
            db, source_key, widget_filters, models, apps
        )
    hist_map = rms_dash._hist_for_apps(db, [a.id for a in apps], RmsApplicationStatusHistory)
    mode = str(config.get("line1_x_axis_mode") or "all").strip()
    hide_empty = bool(
        config.get("omit_null_values")
        or config.get("hide_empty")
        or mode in ("snapshot", "historical")
    )
    prefix = config.get("prefix", "")
    suffix = config.get("suffix", "")
    x_axis_label, y_axis_label = _axis_labels(source_key, config)
    labels, values = rms_dash.compute_line1_axis_series(
        apps, hist_map, filters, mode, hide_empty=hide_empty
    )
    job_stage_summary = rms_dash._client_job_stage_summary(
        db, ctx, apps, hist_map, RmsJob, Client, filters
    )
    lifecycle_rows = rms_dash._lifecycle_funnel(apps, hist_map, filters).get("rows") or []
    pass_rates = rms_dash.line1_pass_rates_for_labels(
        labels,
        job_stage_summary.get("total"),
        lifecycle_rows,
    )
    result = _finalize_series(
        labels,
        values,
        hide_empty=False,
        limit=int(config.get("limit") or 20),
        prefix=prefix,
        suffix=suffix,
        x_axis_label=x_axis_label,
        y_axis_label=y_axis_label,
    )
    result["pass_rates"] = pass_rates
    return result


def _query_rms_pipeline_grouped_series(
    db: Session,
    ctx: AuthContext,
    source_key: str,
    config: dict,
    models: dict,
    dashboard_filters: Optional[dict],
) -> dict:
    config = _normalize_widget_config(config)
    metric = config.get("metric", "count")
    if metric != "count":
        raise HTTPException(status_code=400, detail="管道活跃/损耗数据仅支持计数")
    secondary = config.get("secondary_axis_field") or ""
    if not secondary:
        raise HTTPException(status_code=400, detail="管道活跃/损耗数据需要分组依据")
    mode = str(config.get("pipeline_data_mode") or "active").strip()
    if mode not in PIPELINE_BUCKET_MODES:
        mode = "active"

    RmsApplication = models["RmsApplication"]
    RmsJob = models["RmsJob"]
    Client = models["Client"]
    RmsApplicationStatusHistory = models["RmsApplicationStatusHistory"]
    filters = dict(dashboard_filters or {})
    apps = rms_dash._scoped_apps(db, ctx, RmsApplication, RmsJob, Client, filters)
    widget_filters = config.get("filters") or []
    if widget_filters:
        apps = _narrow_apps_by_widget_filters(
            db, source_key, widget_filters, models, apps
        )
    hist_map = rms_dash._hist_for_apps(
        db, [a.id for a in apps], RmsApplicationStatusHistory
    )
    hide_empty = bool(config.get("omit_null_values") or config.get("hide_empty"))
    prefix = config.get("prefix", "")
    suffix = config.get("suffix", "")
    group_mode = config.get("group_mode") or DEFAULT_GROUP_MODE
    limit = int(config.get("limit") or 20)
    x_axis_label, y_axis_label = _axis_labels(source_key, config)

    primary_labels, secondary_labels, matrix = rms_dash.compute_pipeline_grouped_series(
        apps,
        hist_map,
        filters,
        mode,
        secondary,
        db,
        Client,
        RmsJob=RmsJob,
        hide_empty=hide_empty,
    )
    primary_labels = primary_labels[:limit]
    trimmed_matrix = {pl: matrix.get(pl, {}) for pl in primary_labels}
    return _finalize_grouped_series(
        primary_labels,
        secondary_labels,
        trimmed_matrix,
        group_mode,
        prefix,
        suffix,
        x_axis_label,
        y_axis_label,
        hide_empty=False,
        limit=limit,
    )


def query_widget_data(
    db: Session,
    ctx: AuthContext,
    source_key: str,
    config: dict,
    models: dict,
    dashboard_filters: Optional[dict] = None,
) -> dict:
    if not user_can_read_source(ctx, source_key):
        return {"status": "forbidden", "message": "无权限查看该数据源"}

    config = _normalize_widget_config(config)
    line1_x_mode = str(config.get("line1_x_axis_mode") or "all").strip()
    group_by = config.get("primary_axis_field") or config.get("group_by") or ""
    if (
        source_key == "rms_applications"
        and group_by in ("current_stage", "status")
        and line1_x_mode in ("snapshot", "historical")
    ):
        return _query_line1_rms_axis_series(
            db, ctx, source_key, config, models, dashboard_filters
        )

    metric = config.get("metric", "count")
    field_key = config.get("aggregate_field") or config.get("field") or ""
    group_by = config.get("primary_axis_field") or config.get("group_by") or ""
    secondary = config.get("secondary_axis_field") or ""
    pipeline_mode = str(config.get("pipeline_data_mode") or "active").strip()
    if (
        source_key == "rms_applications"
        and secondary
        and group_by in ("current_stage", "status")
        and pipeline_mode in PIPELINE_BUCKET_MODES
    ):
        return _query_rms_pipeline_grouped_series(
            db, ctx, source_key, config, models, dashboard_filters
        )

    date_group = config.get("date_group") or ""
    filters = config.get("filters") or []
    limit = int(config.get("limit") or 20)
    prefix = config.get("prefix", "")
    suffix = config.get("suffix", "")
    sort_mode = _resolve_sort_mode(config)
    hide_empty = bool(config.get("omit_null_values") or config.get("hide_empty"))
    x_axis_label, y_axis_label = _axis_labels(source_key, config)
    manual_order = config.get("primary_axis_order") or []

    Model = _get_model(models, source_key)
    q = _scoped_query(db, ctx, source_key, models)
    q = _apply_roster_active_pool(q, source_key, config, Model)
    q = _apply_rms_dashboard_filters(q, db, ctx, source_key, dashboard_filters, models)
    q = _apply_filters(q, Model, filters, db=db, source_key=source_key)

    if secondary:
        return _query_grouped_series(db, source_key, config, models, q, Model)

    if group_by == "client":
        src = get_source(source_key)
        if not src or not src.has_client_id:
            raise HTTPException(status_code=400, detail="该数据源不支持按客户分组")
        Client = models["Client"]
        all_rows = q.all()
        buckets: Dict[Any, list] = {}
        for row in all_rows:
            buckets.setdefault(getattr(row, "client_id", None), []).append(row)
        ids = [cid for cid in buckets.keys() if cid is not None]
        name_map = {}
        if ids:
            for cid, cname in db.query(Client.id, Client.name).filter(Client.id.in_(ids)).all():
                name_map[cid] = cname
        labels = []
        values = []
        for cid, bucket_rows in buckets.items():
            labels.append(name_map.get(cid, "(未知客户)"))
            if metric == "count":
                values.append(float(len(bucket_rows)))
            else:
                values.append(_aggregate_rows(bucket_rows, metric, field_key))
        return _finalize_sorted_series(
            labels, values, sort_mode, source_key, "client",
            hide_empty, limit, prefix, suffix,
            manual_order=manual_order,
            x_axis_label=x_axis_label, y_axis_label=y_axis_label,
        )

    if group_by:
        col = _column(Model, group_by)
        if date_group:
            bucket = _date_bucket(col, date_group)
            rows = (
                q.with_entities(bucket.label("label"), func.count().label("cnt"))
                .group_by(bucket)
                .order_by(bucket)
                .all()
            )
            labels = [str(r.label or "(空)") for r in rows]
            values = [float(r.cnt) for r in rows]
            return _finalize_sorted_series(
                labels, values, sort_mode, source_key, group_by,
                hide_empty, limit, prefix, suffix,
                manual_order=manual_order,
                x_axis_label=x_axis_label, y_axis_label=y_axis_label,
            )

        if metric == "count":
            rows = (
                q.with_entities(col.label("label"), func.count().label("cnt"))
                .group_by(col)
                .all()
            )
            display_buckets: Dict[str, float] = {}
            for r in rows:
                rl = str(r.label or "(空)")
                if (source_key, group_by) in RMS_ENUM_GROUP_FIELDS or (source_key, group_by) in RMS_FK_GROUP_FIELDS:
                    dl = _display_group_labels([rl], source_key, group_by, db, models)[0]
                else:
                    dl = rl
                display_buckets[dl] = display_buckets.get(dl, 0.0) + float(r.cnt)

            pairs = list(display_buckets.items())
            pairs = _sort_display_pairs(pairs, sort_mode, source_key, group_by, manual_order)
            labels = [p[0] for p in pairs]
            values = [p[1] for p in pairs]
            return _finalize_series(
                labels, values, hide_empty, limit, prefix, suffix,
                x_axis_label=x_axis_label, y_axis_label=y_axis_label,
            )

        # grouped numeric metric — compute in Python
        all_rows = q.all()
        buckets: Dict[str, list] = {}
        for row in all_rows:
            key = str(getattr(row, group_by, None) or "(空)")
            buckets.setdefault(key, []).append(row)
        merged: Dict[str, float] = {}
        for raw_key, bucket_rows in buckets.items():
            val = _aggregate_rows(bucket_rows, metric, field_key)
            if (source_key, group_by) in RMS_ENUM_GROUP_FIELDS or (source_key, group_by) in RMS_FK_GROUP_FIELDS:
                dl = _display_group_labels([raw_key], source_key, group_by, db, models)[0]
            else:
                dl = raw_key
            merged[dl] = merged.get(dl, 0.0) + float(val)
        pairs = _sort_display_pairs(list(merged.items()), sort_mode, source_key, group_by, manual_order)
        labels = [p[0] for p in pairs]
        values = [p[1] for p in pairs]
        return _finalize_series(
            labels, values, hide_empty, limit, prefix, suffix,
            x_axis_label=x_axis_label, y_axis_label=y_axis_label,
        )

    # scalar
    rows = q.all()
    value = _aggregate_rows(rows, metric, field_key)
    if metric in NUMERIC_METRICS and value == int(value):
        display = str(int(value)) if value == int(value) else f"{value:.2f}"
    elif metric == "count":
        display = str(int(value))
    else:
        display = f"{value:.2f}"
    return {
        "status": "ok",
        "kind": "scalar",
        "value": value,
        "display": f"{prefix}{display}{suffix}",
        "prefix": prefix,
        "suffix": suffix,
    }


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def dashboard_to_dict(d: Any, tabs: Optional[list] = None) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description or "",
        "scope": getattr(d, "scope", None) or "crm",
        "layout_json": _parse_json(d.layout_json or "{}", {}),
        "created_by": d.created_by or "",
        "created_at": d.created_at.isoformat() if d.created_at else "",
        "updated_at": d.updated_at.isoformat() if d.updated_at else "",
        "tabs": tabs if tabs is not None else [],
    }


def tab_to_dict(t: Any, widgets: Optional[list] = None) -> dict:
    return {
        "id": t.id,
        "dashboard_id": t.dashboard_id,
        "name": t.name,
        "sort_order": t.sort_order or 0,
        "layout_json": _parse_json(getattr(t, "layout_json", None) or "{}", {}),
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
        "widgets": widgets if widgets is not None else [],
    }


def widget_to_dict(w: Any) -> dict:
    return {
        "id": w.id,
        "tab_id": w.tab_id,
        "title": w.title,
        "widget_type": w.widget_type,
        "source_key": w.source_key or "",
        "config": _parse_json(w.config_json or "{}", {}),
        "x": w.x or 0,
        "y": w.y or 0,
        "w": w.w or 4,
        "h": w.h or 3,
        "sort_order": w.sort_order or 0,
        "created_at": w.created_at.isoformat() if w.created_at else "",
        "updated_at": w.updated_at.isoformat() if w.updated_at else "",
    }


# ---------------------------------------------------------------------------
# CRUD (explicit cascade — do not rely on SQLite FK cascade)
# ---------------------------------------------------------------------------

def list_dashboards(
    db: Session,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
    *,
    scope: Optional[str] = None,
) -> list:
    q = db.query(DashboardDashboard).order_by(DashboardDashboard.id)
    if scope:
        q = q.filter(DashboardDashboard.scope == scope)
    dashboards = q.all()
    out = []
    for d in dashboards:
        tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).order_by(
            DashboardTab.sort_order, DashboardTab.id
        ).all()
        tab_dicts = []
        for t in tabs:
            widgets = db.query(DashboardWidget).filter(DashboardWidget.tab_id == t.id).order_by(
                DashboardWidget.sort_order, DashboardWidget.y, DashboardWidget.x, DashboardWidget.id
            ).all()
            tab_dicts.append(tab_to_dict(t, [widget_to_dict(w) for w in widgets]))
        out.append(dashboard_to_dict(d, tab_dicts))
    return out


def get_dashboard(db: Session, dashboard_id: int, DashboardDashboard, DashboardTab, DashboardWidget) -> dict:
    d = db.query(DashboardDashboard).filter(DashboardDashboard.id == dashboard_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dashboard 不存在")
    tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).order_by(
        DashboardTab.sort_order, DashboardTab.id
    ).all()
    tab_dicts = []
    for t in tabs:
        widgets = db.query(DashboardWidget).filter(DashboardWidget.tab_id == t.id).order_by(
            DashboardWidget.sort_order, DashboardWidget.y, DashboardWidget.x, DashboardWidget.id
        ).all()
        tab_dicts.append(tab_to_dict(t, [widget_to_dict(w) for w in widgets]))
    return dashboard_to_dict(d, tab_dicts)


def create_dashboard(
    db: Session,
    body: dict,
    ctx: AuthContext,
    DashboardDashboard,
    *,
    scope: str = "crm",
    seed_rms_tabs: bool = False,
    DashboardTab=None,
    DashboardWidget=None,
) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    now = _now()
    d = DashboardDashboard(
        name=name,
        description=(body.get("description") or "").strip(),
        layout_json=_dump_json(body.get("layout_json") or {}),
        scope=(body.get("scope") or scope or "crm").strip() or "crm",
        created_by=ctx.username,
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    if seed_rms_tabs and DashboardTab is not None and DashboardWidget is not None and d.scope == "rms":
        _add_rms_default_tabs(db, d.id, DashboardTab, DashboardWidget, now)
        db.commit()
    if DashboardTab is not None and DashboardWidget is not None:
        return get_dashboard(db, d.id, DashboardDashboard, DashboardTab, DashboardWidget)
    return dashboard_to_dict(d, [])


def update_dashboard(db: Session, dashboard_id: int, body: dict, DashboardDashboard, DashboardTab, DashboardWidget) -> dict:
    d = db.query(DashboardDashboard).filter(DashboardDashboard.id == dashboard_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dashboard 不存在")
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        d.name = name
    if "description" in body:
        d.description = (body.get("description") or "").strip()
    if "layout_json" in body:
        d.layout_json = _dump_json(body.get("layout_json") or {})
    d.updated_at = _now()
    db.commit()
    return get_dashboard(db, dashboard_id, DashboardDashboard, DashboardTab, DashboardWidget)


def delete_dashboard(db: Session, dashboard_id: int, DashboardDashboard, DashboardTab, DashboardWidget) -> dict:
    d = db.query(DashboardDashboard).filter(DashboardDashboard.id == dashboard_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dashboard 不存在")
    tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == dashboard_id).all()
    for tab in tabs:
        db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab.id).delete(synchronize_session=False)
    db.query(DashboardTab).filter(DashboardTab.dashboard_id == dashboard_id).delete(synchronize_session=False)
    db.query(DashboardDashboard).filter(DashboardDashboard.id == dashboard_id).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}


def create_tab(db: Session, dashboard_id: int, body: dict, DashboardDashboard, DashboardTab) -> dict:
    d = db.query(DashboardDashboard).filter(DashboardDashboard.id == dashboard_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dashboard 不存在")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    now = _now()
    layout = body.get("layout_json") if isinstance(body.get("layout_json"), dict) else {}
    t = DashboardTab(
        dashboard_id=dashboard_id,
        name=name,
        sort_order=int(body.get("sort_order") or 0),
        layout_json=_dump_json(layout),
        created_at=now,
        updated_at=now,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return tab_to_dict(t, [])


def update_tab(db: Session, tab_id: int, body: dict, DashboardTab) -> dict:
    t = db.query(DashboardTab).filter(DashboardTab.id == tab_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tab 不存在")
    if "name" in body:
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        t.name = name
    if "sort_order" in body:
        t.sort_order = int(body.get("sort_order") or 0)
    if "layout_json" in body and isinstance(body.get("layout_json"), dict):
        t.layout_json = _dump_json(body.get("layout_json"))
    t.updated_at = _now()
    db.commit()
    db.refresh(t)
    return tab_to_dict(t)


def delete_tab(db: Session, tab_id: int, DashboardTab, DashboardWidget) -> dict:
    t = db.query(DashboardTab).filter(DashboardTab.id == tab_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tab 不存在")
    db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab_id).delete(synchronize_session=False)
    db.query(DashboardTab).filter(DashboardTab.id == tab_id).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}


def create_widget(
    db: Session,
    tab_id: int,
    body: dict,
    DashboardTab,
    DashboardWidget,
    allowed_source_keys: Optional[FrozenSet[str]] = None,
) -> dict:
    t = db.query(DashboardTab).filter(DashboardTab.id == tab_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tab 不存在")
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")
    widget_type = (body.get("widget_type") or "").strip()
    source_key = (body.get("source_key") or "").strip()
    config = body.get("config") or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config 必须是对象")
    clean_config = validate_widget_config(
        widget_type, source_key, config, allowed_source_keys=allowed_source_keys
    )
    now = _now()
    w = DashboardWidget(
        tab_id=tab_id,
        title=title,
        widget_type=widget_type,
        source_key=source_key,
        config_json=_dump_json(clean_config),
        x=int(body.get("x") or 0),
        y=int(body.get("y") or 0),
        w=int(body.get("w") or 4),
        h=int(body.get("h") or 3),
        sort_order=int(body.get("sort_order") or 0),
        created_at=now,
        updated_at=now,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return widget_to_dict(w)


def update_widget(
    db: Session,
    widget_id: int,
    body: dict,
    DashboardWidget,
    allowed_source_keys: Optional[FrozenSet[str]] = None,
) -> dict:
    w = db.query(DashboardWidget).filter(DashboardWidget.id == widget_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Widget 不存在")
    widget_type = (body.get("widget_type") or w.widget_type).strip()
    source_key = body.get("source_key", w.source_key or "")
    if "title" in body:
        title = (body.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title 不能为空")
        w.title = title
    if "widget_type" in body:
        w.widget_type = widget_type
    if "source_key" in body:
        w.source_key = (source_key or "").strip()
    if "config" in body:
        config = body.get("config") or {}
        if not isinstance(config, dict):
            raise HTTPException(status_code=400, detail="config 必须是对象")
        clean = validate_widget_config(
            widget_type,
            w.source_key or source_key,
            config,
            allowed_source_keys=allowed_source_keys,
        )
        w.config_json = _dump_json(clean)
    for attr in ("x", "y", "w", "h", "sort_order"):
        if attr in body:
            setattr(w, attr, int(body.get(attr) or 0))
    w.updated_at = _now()
    db.commit()
    db.refresh(w)
    return widget_to_dict(w)


def delete_widget(db: Session, widget_id: int, DashboardWidget) -> dict:
    w = db.query(DashboardWidget).filter(DashboardWidget.id == widget_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Widget 不存在")
    db.query(DashboardWidget).filter(DashboardWidget.id == widget_id).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}


def get_widget_data(
    db: Session,
    ctx: AuthContext,
    widget_id: int,
    models: dict,
    DashboardWidget,
    dashboard_filters: Optional[dict] = None,
) -> dict:
    w = db.query(DashboardWidget).filter(DashboardWidget.id == widget_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Widget 不存在")
    config = _parse_json(w.config_json or "{}", {})
    wt = w.widget_type

    if wt == "rich_text":
        return {"status": "ok", "kind": "rich_text", "content": config.get("content", "")}
    if wt == "iframe":
        return {"status": "ok", "kind": "iframe", "url": config.get("url", "")}
    if wt == "roster_summary":
        return query_roster_summary(db, ctx, config, models)

    source_key = w.source_key or ""
    if not source_key:
        return {"status": "error", "message": "未配置数据源"}
    return query_widget_data(db, ctx, source_key, config, models, dashboard_filters)


def _yuan(value: float) -> str:
    return f"¥{round(value):,}"


def list_roster_clients(db: Session, ctx: AuthContext, models: dict) -> dict:
    """Distinct clients present in the user's scoped roster — populates the card dropdown."""
    if not user_can_read_source(ctx, "roster_entries"):
        return {"status": "forbidden", "clients": []}
    RosterEntry = _get_model(models, "roster_entries")
    Client = models["Client"]
    q = _scoped_query(db, ctx, "roster_entries", models)
    q = _apply_roster_active_pool(q, "roster_entries", {}, RosterEntry)
    ids = {cid for (cid,) in q.with_entities(RosterEntry.client_id).distinct().all() if cid and int(cid) > 0}
    clients = []
    if ids:
        for cid, cname in db.query(Client.id, Client.name).filter(Client.id.in_(ids)).order_by(Client.name).all():
            clients.append({"id": cid, "name": cname or f"客户#{cid}"})
    return {"status": "ok", "clients": clients}


def query_roster_summary(
    db: Session,
    ctx: AuthContext,
    config: dict,
    models: dict,
) -> dict:
    """Roster economics card: 月报价合计 / 税前工资合计 / GM$ / GM%, all clients or one.

    Mirrors the roster footer: GM% = Σgms / (Σ月报价 / 1.0672), over the active pool
    (employment_status not containing 离职) unless include_left is set.
    """
    if not user_can_read_source(ctx, "roster_entries"):
        return {"status": "forbidden", "message": "无权限查看花名册"}

    RosterEntry = _get_model(models, "roster_entries")
    q = _scoped_query(db, ctx, "roster_entries", models)

    q = _apply_roster_active_pool(q, "roster_entries", config, RosterEntry)

    client_id = config.get("client_id")
    client_name = ""
    if client_id not in (None, "", 0):
        q = q.filter(RosterEntry.client_id == int(client_id))
        Client = models["Client"]
        row = db.query(Client.name).filter(Client.id == int(client_id)).first()
        client_name = row[0] if row else ""

    rows = q.all()
    revenue = 0.0
    salary = 0.0
    gms = 0.0
    for r in rows:
        revenue += _parse_numeric(r.monthly_quote_tax) or 0.0
        salary += _parse_numeric(r.pre_tax_salary) or 0.0
        gms += _parse_numeric(r.gms) or 0.0
    net_revenue = revenue / ROSTER_TAX_DIVISOR if revenue else 0.0
    gm_pct = (gms / net_revenue * 100) if net_revenue else 0.0

    return {
        "status": "ok",
        "kind": "roster_summary",
        "scope": "client" if client_id not in (None, "", 0) else "all",
        "client_id": int(client_id) if client_id not in (None, "", 0) else None,
        "client_name": client_name,
        "headcount": len(rows),
        "revenue": {"value": revenue, "display": _yuan(revenue)},
        "salary": {"value": salary, "display": _yuan(salary)},
        "gms": {"value": gms, "display": _yuan(gms)},
        "gm_pct": {"value": gm_pct, "display": f"{gm_pct:.2f}%"},
    }


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed_default_dashboards(
    db: Session,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """幂等预置默认看板。每个看板独立判断是否已存在，不覆盖已有看板。"""
    _seed_business_overview(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _seed_roster_margin(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _sync_roster_margin_preset_layout(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _seed_rms_recruitment(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _sync_rms_preset_widgets(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _cleanup_rms_obsolete_seed_widgets(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _sync_rms_tab_ia_v2(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _sync_rms_client_job_required_widgets(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _sync_rms_client_job_stage_title(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _sync_rms_filter_block_height(db, DashboardDashboard, DashboardTab, DashboardWidget)
    _ensure_rms_tab_widget_locks(db, DashboardDashboard, DashboardTab, DashboardWidget)


_RMS_DEFAULT_TABS = (
    ("总览", "overview", 0),
    ("生命周期转化", "lifecycle", 1),
    ("客户岗位分析", "client_job", 2),
    ("招聘人效", "recruiter", 3),
    ("花名册核对", "roster", 4),
)
_RMS_TEST_TAB_NAME = "Test"
_RMS_SEED_NAME = "招聘总览"
_RMS_TAB_SORT = {
    "总览": 0,
    "生命周期转化": 1,
    "历史转化": 1,
    "客户岗位分析": 2,
    "招聘人效": 3,
    "花名册核对": 4,
}
_RMS_SYSTEM_TAB_TEMPLATES = frozenset({
    "overview", "lifecycle", "history", "client_job", "recruiter", "roster", "test",
})
_RMS_SYSTEM_TAB_NAMES = frozenset({
    "总览", "生命周期转化", "历史转化", "客户岗位分析", "招聘人效", "花名册核对", "Test",
})
_RMS_OBSOLETE_BLOCKS = frozenset({
    "chart_history_pass",
    "table_history",
    "chart_client_job_stage_grouped",
    "chart_client_job_stage_stacked",
    "chart_client_job_stage_funnel",
})


def _add_rms_default_tabs(db: Session, dashboard_id: int, DashboardTab, DashboardWidget, now) -> None:
    for name, template, sort_order in _RMS_DEFAULT_TABS:
        tab = DashboardTab(
            dashboard_id=dashboard_id,
            name=name,
            sort_order=sort_order,
            layout_json=_dump_json({"rms_template": template}),
            created_at=now,
            updated_at=now,
        )
        db.add(tab)
        db.flush()
        if DashboardWidget is not None and template != "empty":
            _seed_rms_tab_widgets(db, tab.id, template, DashboardWidget, now)


_RMS_TEMPLATE_WIDGETS = {
    "overview": [
        {"title": "筛选", "widget_type": "rms_block", "source_key": "", "config": {"block": "filter"}, "x": 0, "y": 0, "w": 12, "h": 1},
        {"title": "简历数", "widget_type": "rms_block", "source_key": "", "config": {"block": "kpi_resume_count"}, "x": 0, "y": 1, "w": 4, "h": 3},
        {"title": "入职数", "widget_type": "rms_block", "source_key": "", "config": {"block": "kpi_hired_count"}, "x": 4, "y": 1, "w": 4, "h": 3},
        {"title": "百简历入职转化率", "widget_type": "rms_block", "source_key": "", "config": {"block": "kpi_resume_to_hire_rate"}, "x": 8, "y": 1, "w": 4, "h": 3},
        {"title": "招聘管道（活动态）", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_pipeline"}, "x": 0, "y": 4, "w": 8, "h": 6},
        {"title": "待处理积压", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_pending_backlog"}, "x": 8, "y": 4, "w": 4, "h": 6},
    ],
    "lifecycle": [
        {"title": "筛选", "widget_type": "rms_block", "source_key": "", "config": {"block": "filter"}, "x": 0, "y": 0, "w": 12, "h": 1},
        {"title": "招聘生命周期漏斗", "widget_type": "rms_block", "source_key": "", "config": {"block": "lifecycle_funnel"}, "x": 0, "y": 1, "w": 12, "h": 6},
        {"title": "五率通过率", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_lifecycle_pass_rate", "style": {"chart_type": "line", "sort": "original", "metric": "pass_rate"}}, "x": 0, "y": 7, "w": 12, "h": 5},
        {"title": "生命周期明细", "widget_type": "rms_block", "source_key": "", "config": {"block": "table_lifecycle_detail"}, "x": 0, "y": 12, "w": 12, "h": 5},
    ],
    "client_job": [
        {"title": "筛选", "widget_type": "rms_block", "source_key": "", "config": {"block": "filter"}, "x": 0, "y": 0, "w": 12, "h": 1},
        {"title": "岗位待处理积压", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_job_pending_backlog"}, "x": 0, "y": 1, "w": 6, "h": 6},
        {"title": "客户入职量排行", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_client_hired_ranking"}, "x": 6, "y": 1, "w": 6, "h": 6},
        {"title": "客户岗位阶段统计", "widget_type": "rms_block", "source_key": "", "config": {"block": "table_client_job_stage"}, "x": 0, "y": 7, "w": 12, "h": 6},
    ],
    "recruiter": [
        {"title": "筛选", "widget_type": "rms_block", "source_key": "", "config": {"block": "filter"}, "x": 0, "y": 0, "w": 12, "h": 1},
        {"title": "当月入职排名", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_recruiter"}, "x": 0, "y": 1, "w": 12, "h": 6},
        {"title": "推荐量 vs 入职量", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_recruiter_recommend_vs_hired"}, "x": 0, "y": 7, "w": 12, "h": 6},
        {"title": "人效明细", "widget_type": "rms_block", "source_key": "", "config": {"block": "table_recruiter"}, "x": 0, "y": 13, "w": 12, "h": 6},
    ],
    "roster": [
        {"title": "已入职与花名册一致性核对", "widget_type": "rms_block", "source_key": "", "config": {"block": "roster_header"}, "x": 0, "y": 0, "w": 12, "h": 2},
        {"title": "一致", "widget_type": "rms_block", "source_key": "", "config": {"block": "roster_kpi_matched"}, "x": 0, "y": 2, "w": 3, "h": 3},
        {"title": "缺失", "widget_type": "rms_block", "source_key": "", "config": {"block": "roster_kpi_missing"}, "x": 3, "y": 2, "w": 3, "h": 3},
        {"title": "不一致", "widget_type": "rms_block", "source_key": "", "config": {"block": "roster_kpi_mismatch"}, "x": 6, "y": 2, "w": 3, "h": 3},
        {"title": "多匹配", "widget_type": "rms_block", "source_key": "", "config": {"block": "roster_kpi_ambiguous"}, "x": 9, "y": 2, "w": 3, "h": 3},
        {"title": "核对明细", "widget_type": "rms_block", "source_key": "", "config": {"block": "table_roster"}, "x": 0, "y": 5, "w": 12, "h": 7},
    ],
    "test": [
        {"title": "筛选", "widget_type": "rms_block", "source_key": "", "config": {"block": "filter"}, "x": 0, "y": 0, "w": 12, "h": 1},
        {"title": "岗位阶段（分组柱）", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_client_job_stage_grouped"}, "x": 0, "y": 1, "w": 12, "h": 7},
        {"title": "岗位阶段（堆叠柱）", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_client_job_stage_stacked"}, "x": 0, "y": 8, "w": 12, "h": 7},
        {"title": "岗位阶段（漏斗）", "widget_type": "rms_block", "source_key": "", "config": {"block": "chart_client_job_stage_funnel"}, "x": 0, "y": 15, "w": 12, "h": 6},
    ],
}


def _seed_rms_tab_widgets(db: Session, tab_id: int, template: str, DashboardWidget, now) -> None:
    specs = _RMS_TEMPLATE_WIDGETS.get(template) or []
    for i, spec in enumerate(specs):
        db.add(DashboardWidget(
            tab_id=tab_id,
            title=spec["title"],
            widget_type=spec["widget_type"],
            source_key=spec.get("source_key") or "",
            config_json=_dump_json(spec.get("config") or {}),
            x=spec["x"], y=spec["y"], w=spec["w"], h=spec["h"],
            sort_order=i,
            created_at=now,
            updated_at=now,
        ))


def seed_rms_tab_widgets(db: Session, tab_id: int, template: str, DashboardWidget) -> None:
    """Public helper — seed preset widgets for an RMS tab (idempotent skip if widgets exist)."""
    count = db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab_id).count()
    if count > 0 or template in ("", "empty"):
        return
    now = _now()
    _seed_rms_tab_widgets(db, tab_id, template, DashboardWidget, now)
    db.commit()


def _rms_tab_template(tab) -> str:
    layout = _parse_json(getattr(tab, "layout_json", None) or "{}", {})
    return (layout.get("rms_template") or "").strip()


def _tab_widgets_locked(tab) -> bool:
    layout = _parse_json(getattr(tab, "layout_json", None) or "{}", {})
    return bool(layout.get("widgets_locked"))


def lock_rms_tab_widgets(db: Session, tab_id: int, DashboardTab) -> None:
    """Mark an RMS tab as user-customized; seed sync will no longer add/remove/move widgets."""
    tab = db.query(DashboardTab).filter(DashboardTab.id == tab_id).first()
    if not tab or _tab_widgets_locked(tab):
        return
    layout = _parse_json(tab.layout_json or "{}", {})
    layout["widgets_locked"] = True
    tab.layout_json = _dump_json(layout)
    tab.updated_at = _now()
    db.commit()


def _is_rms_system_tab(tab) -> bool:
    name = (tab.name or "").strip()
    template = _rms_tab_template(tab)
    return template in _RMS_SYSTEM_TAB_TEMPLATES or name in _RMS_SYSTEM_TAB_NAMES


def _widget_block(widget) -> str:
    cfg = _parse_json(getattr(widget, "config_json", None) or "{}", {})
    return (cfg.get("block") or "").strip()


def _tab_has_block(db, tab_id: int, block: str, DashboardWidget) -> bool:
    for w in db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab_id).all():
        if _widget_block(w) == block:
            return True
    return False


def _cleanup_rms_obsolete_seed_widgets(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Remove Test tab and obsolete blocks from RMS system tabs only (HC-2)."""
    changed = False
    dashboards = db.query(DashboardDashboard).filter(DashboardDashboard.scope == "rms").all()
    for d in dashboards:
        tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).all()
        for tab in list(tabs):
            if (tab.name or "").strip() == _RMS_TEST_TAB_NAME:
                db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab.id).delete(
                    synchronize_session=False
                )
                db.query(DashboardTab).filter(DashboardTab.id == tab.id).delete(
                    synchronize_session=False
                )
                changed = True
                continue
            if not _is_rms_system_tab(tab):
                continue
            if _tab_widgets_locked(tab):
                continue
            widgets = db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab.id).all()
            for w in widgets:
                if _widget_block(w) not in _RMS_OBSOLETE_BLOCKS:
                    continue
                db.query(DashboardWidget).filter(DashboardWidget.id == w.id).delete(
                    synchronize_session=False
                )
                changed = True
    if changed:
        db.commit()


def _sync_rms_tab_ia_v2(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """No-op: user-deleted or customized RMS tabs must not be recreated or reordered on startup."""
    return


def _sync_rms_client_job_required_widgets(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Backfill missing table_client_job_stage on unlocked client_job tabs only."""
    table_spec = None
    table_sort_order = 0
    for i, spec in enumerate(_RMS_TEMPLATE_WIDGETS.get("client_job") or []):
        if (spec.get("config") or {}).get("block") == "table_client_job_stage":
            table_spec = spec
            table_sort_order = i
            break
    if table_spec is None:
        return

    changed = False
    now = _now()
    dashboards = db.query(DashboardDashboard).filter(DashboardDashboard.scope == "rms").all()
    for d in dashboards:
        tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).all()
        for tab in tabs:
            name = (tab.name or "").strip()
            template = _rms_tab_template(tab)
            if name != "客户岗位分析" and template != "client_job":
                continue
            if _tab_widgets_locked(tab):
                continue
            if _tab_has_block(db, tab.id, "table_client_job_stage", DashboardWidget):
                continue
            db.add(DashboardWidget(
                tab_id=tab.id,
                title=table_spec["title"],
                widget_type=table_spec["widget_type"],
                source_key=table_spec.get("source_key") or "",
                config_json=_dump_json(table_spec.get("config") or {}),
                x=table_spec["x"],
                y=table_spec["y"],
                w=table_spec["w"],
                h=table_spec["h"],
                sort_order=table_sort_order,
                created_at=now,
                updated_at=now,
            ))
            changed = True
    if changed:
        db.commit()


def _sync_rms_preset_widgets(db, DashboardDashboard, DashboardTab, DashboardWidget) -> None:
    """Backfill widgets for RMS tabs that only have rms_template layout (no widgets yet)."""
    dashboards = db.query(DashboardDashboard).filter(DashboardDashboard.scope == "rms").all()
    changed = False
    now = _now()
    for d in dashboards:
        tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).all()
        for t in tabs:
            count = db.query(DashboardWidget).filter(DashboardWidget.tab_id == t.id).count()
            if count > 0:
                continue
            layout = _parse_json(getattr(t, "layout_json", None) or "{}", {})
            template = (layout.get("rms_template") or "").strip()
            if not template or template == "empty":
                continue
            _seed_rms_tab_widgets(db, t.id, template, DashboardWidget, now)
            changed = True
    if changed:
        db.commit()


def _backfill_missing_rms_tab_widgets(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Deprecated: no longer called on startup — user tab layouts must not be auto-mutated."""
    return


def _ensure_rms_tab_widget_locks(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Mark RMS tabs that already have widgets as user-owned (skip seed sync)."""
    changed = False
    now = _now()
    dashboards = db.query(DashboardDashboard).filter(DashboardDashboard.scope == "rms").all()
    for d in dashboards:
        tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).all()
        for tab in tabs:
            if _tab_widgets_locked(tab):
                continue
            count = db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab.id).count()
            if count <= 0:
                continue
            layout = _parse_json(tab.layout_json or "{}", {})
            layout["widgets_locked"] = True
            tab.layout_json = _dump_json(layout)
            tab.updated_at = now
            changed = True
    if changed:
        db.commit()


def _sync_rms_client_job_stage_title(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Rename RMS table_client_job_stage widget title to 客户岗位阶段统计."""
    rms_dashboard_ids = {
        int(row[0])
        for row in db.query(DashboardDashboard.id)
        .filter(DashboardDashboard.scope == "rms")
        .all()
    }
    if not rms_dashboard_ids:
        return
    rms_tab_ids = {
        int(row[0])
        for row in db.query(DashboardTab.id)
        .filter(DashboardTab.dashboard_id.in_(rms_dashboard_ids))
        .all()
    }
    if not rms_tab_ids:
        return
    changed = False
    now = _now()
    for w in db.query(DashboardWidget).filter(
        DashboardWidget.tab_id.in_(rms_tab_ids),
        DashboardWidget.widget_type == "rms_block",
    ).all():
        tab = db.query(DashboardTab).filter(DashboardTab.id == w.tab_id).first()
        if tab and _tab_widgets_locked(tab):
            continue
        if (w.title or "").strip() != "历史数据":
            continue
        cfg = _parse_json(w.config_json or "{}", {})
        if (cfg.get("block") or "").strip() != "table_client_job_stage":
            continue
        w.title = "客户岗位阶段统计"
        w.updated_at = now
        changed = True
    if changed:
        db.commit()


def _sync_rms_filter_block_height(
    db,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Shrink RMS filter block to h=1 and pull widgets below up (single-row filter)."""
    rms_dashboard_ids = {
        int(row[0])
        for row in db.query(DashboardDashboard.id)
        .filter(DashboardDashboard.scope == "rms")
        .all()
    }
    if not rms_dashboard_ids:
        return
    changed = False
    now = _now()
    tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id.in_(rms_dashboard_ids)).all()
    for tab in tabs:
        if _tab_widgets_locked(tab):
            continue
        widgets = (
            db.query(DashboardWidget)
            .filter(DashboardWidget.tab_id == tab.id)
            .all()
        )
        filter_widgets = []
        for w in widgets:
            if w.widget_type != "rms_block":
                continue
            cfg = _parse_json(w.config_json or "{}", {})
            if (cfg.get("block") or "").strip() != "filter":
                continue
            old_h = int(w.h or 0)
            if old_h <= 1:
                continue
            filter_widgets.append((w, old_h))
        if not filter_widgets:
            continue
        for fw, old_h in filter_widgets:
            fy = int(fw.y or 0)
            shift_from = fy + old_h
            savings = old_h - 1
            fw.h = 1
            fw.updated_at = now
            changed = True
            for w in widgets:
                if w.id == fw.id:
                    continue
                wy = int(w.y or 0)
                if wy >= shift_from:
                    w.y = wy - savings
                    w.updated_at = now
                    changed = True
    if changed:
        db.commit()


def _sync_rms_test_tab(db, DashboardDashboard, DashboardTab, DashboardWidget) -> None:
    """Idempotently add Test tab (3 job-stage chart variants) to existing RMS dashboards."""
    dashboards = db.query(DashboardDashboard).filter(DashboardDashboard.scope == "rms").all()
    changed = False
    now = _now()
    for d in dashboards:
        tabs = db.query(DashboardTab).filter(DashboardTab.dashboard_id == d.id).all()
        if any((t.name or "").strip() == _RMS_TEST_TAB_NAME for t in tabs):
            continue
        max_sort = max((int(t.sort_order or 0) for t in tabs), default=-1)
        tab = DashboardTab(
            dashboard_id=d.id,
            name=_RMS_TEST_TAB_NAME,
            sort_order=max_sort + 1,
            layout_json=_dump_json({"rms_template": "test"}),
            created_at=now,
            updated_at=now,
        )
        db.add(tab)
        db.flush()
        _seed_rms_tab_widgets(db, tab.id, "test", DashboardWidget, now)
        changed = True
    if changed:
        db.commit()


def _seed_rms_recruitment(db, DashboardDashboard, DashboardTab, DashboardWidget) -> None:
    existing = (
        db.query(DashboardDashboard)
        .filter(DashboardDashboard.scope == "rms", DashboardDashboard.name == _RMS_SEED_NAME)
        .first()
    )
    if existing:
        return
    now = _now()
    d = DashboardDashboard(
        name=_RMS_SEED_NAME,
        description="系统预置招聘 Dashboard",
        layout_json="{}",
        scope="rms",
        created_by="system",
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    db.flush()
    _add_rms_default_tabs(db, d.id, DashboardTab, DashboardWidget, now)
    db.commit()


def _seed_widgets(db, DashboardTab, DashboardWidget, dashboard_id, tab_name, widgets_spec, now):
    tab = DashboardTab(
        dashboard_id=dashboard_id,
        name=tab_name,
        sort_order=0,
        created_at=now,
        updated_at=now,
    )
    db.add(tab)
    db.flush()
    for i, spec in enumerate(widgets_spec):
        db.add(DashboardWidget(
            tab_id=tab.id,
            title=spec["title"],
            widget_type=spec["widget_type"],
            source_key=spec["source_key"],
            config_json=_dump_json(spec["config"]),
            x=spec["x"], y=spec["y"], w=spec["w"], h=spec["h"],
            sort_order=i,
            created_at=now,
            updated_at=now,
        ))


def _seed_business_overview(db, DashboardDashboard, DashboardTab, DashboardWidget) -> None:
    existing = (
        db.query(DashboardDashboard)
        .filter(DashboardDashboard.name == _DEFAULT_SEED_NAME)
        .first()
    )
    if existing:
        return

    now = _now()
    d = DashboardDashboard(
        name=_DEFAULT_SEED_NAME,
        description="系统预置经营总览",
        layout_json="{}",
        created_by="system",
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    db.flush()

    # Twenty 式默认看板：克制的 2x2 大卡布局（欢迎 / 环形 / 柱状 / 折线），无 KPI 数字卡。
    # 全部用显式 x/y/w/h 做 12 栅格定位（前端按 grid-column/row 映射，非 DOM 流式排列）。
    welcome_text = (
        "欢迎使用经营总览\n"
        "这里汇总了商机的分布、金额与创建趋势。点击右上角「编辑」可自定义看板、"
        "新增标签页与组件。"
    )
    widgets_spec = [
        {
            "title": "欢迎",
            "widget_type": "rich_text",
            "source_key": "",
            "config": {"content": welcome_text},
            "x": 0, "y": 0, "w": 6, "h": 6,
        },
        {
            "title": "商机阶段分布",
            "widget_type": "pie",
            "source_key": "opportunities",
            "config": {
                "metric": "count", "group_by": "stage", "limit": 8,
                "color": "blue", "sort": "value_desc",
                "show_legend": True, "show_value_center": True, "hide_empty": True,
            },
            "x": 6, "y": 0, "w": 6, "h": 6,
        },
        {
            "title": "各阶段商机金额",
            "widget_type": "bar",
            "source_key": "opportunities",
            "config": {
                "metric": "sum", "field": "amount", "group_by": "stage", "limit": 8,
                "color": "blue", "sort": "value_desc",
                "data_labels": False, "hide_empty": True, "prefix": "¥",
            },
            "x": 0, "y": 5, "w": 6, "h": 6,
        },
        {
            "title": "商机创建趋势",
            "widget_type": "line",
            "source_key": "opportunities",
            "config": {
                "metric": "count", "group_by": "created_at", "date_group": "month",
                "limit": 12, "color": "blue",
            },
            "x": 6, "y": 5, "w": 6, "h": 6,
        },
    ]

    _seed_widgets(db, DashboardTab, DashboardWidget, d.id, "总览", widgets_spec, now)
    db.commit()


_ROSTER_MARGIN_TAB_NAME = "毛利总览"


def _roster_margin_sample_client_id(db: Session):
    row = db.execute(text(
        "SELECT client_id FROM roster_entries WHERE client_id IS NOT NULL AND client_id > 0 "
        "AND (employment_status IS NULL OR employment_status = '' OR employment_status NOT LIKE '%离职%') "
        "GROUP BY client_id ORDER BY COUNT(*) DESC LIMIT 1"
    )).first()
    return row[0] if row else None


def _roster_margin_preset_specs(sample_client_id) -> list:
    """Fresh dict/list per call — do not hoist to a module-level mutable spec list."""
    active_filter = [{"field": "employment_status", "op": "not_contains", "value": "离职"}]
    client_config = {"client_id": sample_client_id} if sample_client_id else {}
    return [
        {
            "title": "全公司毛利概览",
            "widget_type": "roster_summary",
            "source_key": "roster_entries",
            "config": {},
            "x": 0, "y": 0, "w": 6, "h": 5,
        },
        {
            "title": "单客户毛利概览",
            "widget_type": "roster_summary",
            "source_key": "roster_entries",
            "config": dict(client_config),
            "x": 6, "y": 0, "w": 6, "h": 5,
        },
        {
            "title": "各客户月报价(含税)",
            "widget_type": "bar",
            "source_key": "roster_entries",
            "config": {
                "metric": "sum", "field": "monthly_quote_tax", "group_by": "client",
                "limit": 12, "color": "blue", "sort": "value_desc",
                "data_labels": False, "hide_empty": True, "prefix": "¥",
                "filters": list(active_filter),
            },
            "x": 0, "y": 5, "w": 6, "h": 5,
        },
        {
            "title": "各客户 GM$",
            "widget_type": "bar",
            "source_key": "roster_entries",
            "config": {
                "metric": "sum", "field": "gms", "group_by": "client",
                "limit": 12, "color": "green", "sort": "value_desc",
                "data_labels": False, "hide_empty": True, "prefix": "¥",
                "filters": list(active_filter),
            },
            "x": 6, "y": 5, "w": 6, "h": 5,
        },
    ]


def _find_roster_margin_tab(db: Session, dashboard_id: int, DashboardTab):
    tab = (
        db.query(DashboardTab)
        .filter(DashboardTab.dashboard_id == dashboard_id, DashboardTab.name == _ROSTER_MARGIN_TAB_NAME)
        .first()
    )
    if tab:
        return tab
    return (
        db.query(DashboardTab)
        .filter(DashboardTab.dashboard_id == dashboard_id)
        .order_by(DashboardTab.sort_order, DashboardTab.id)
        .first()
    )


def _spec_rect(spec: dict) -> tuple:
    x = int(spec["x"])
    y = int(spec["y"])
    width = max(1, int(spec["w"]))
    height = max(1, int(spec["h"]))
    return (x, y, width, height)


def _widget_rect(w) -> tuple:
    x = int(w.x or 0)
    y = int(w.y or 0)
    width = max(1, int(w.w or 1))
    height = max(1, int(w.h or 1))
    return (x, y, width, height)


def _rects_overlap(a: tuple, b: tuple) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _preset_rects_from_specs(specs: list) -> list:
    return [_spec_rect(s) for s in specs]


def _max_preset_bottom(specs: list) -> int:
    return max(y + h for _x, y, _w, h in (_spec_rect(s) for s in specs))


def _widget_overlaps_any_preset_rect(w, preset_rects: list) -> bool:
    wr = _widget_rect(w)
    return any(_rects_overlap(wr, pr) for pr in preset_rects)


def _match_preset_widget(widgets: list, spec: dict):
    for w in widgets:
        if (
            w.title == spec["title"]
            and w.widget_type == spec["widget_type"]
            and (w.source_key or "") == spec["source_key"]
        ):
            return w
    return None


def _sync_roster_margin_preset_layout(
    db: Session,
    DashboardDashboard,
    DashboardTab,
    DashboardWidget,
) -> None:
    """Sync layout for existing system seed dashboard only; preserve user config semantics."""
    d = (
        db.query(DashboardDashboard)
        .filter(
            DashboardDashboard.name == _ROSTER_SEED_NAME,
            DashboardDashboard.created_by == "system",
        )
        .first()
    )
    if not d:
        return

    tab = _find_roster_margin_tab(db, d.id, DashboardTab)
    if not tab:
        return

    sample_client_id = _roster_margin_sample_client_id(db)
    specs = _roster_margin_preset_specs(sample_client_id)
    now = _now()
    widgets = db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab.id).all()
    next_sort = max((w.sort_order for w in widgets), default=-1)

    managed_preset_ids = set()

    for spec in specs:
        w = _match_preset_widget(widgets, spec)
        if w:
            if int(w.h or 0) >= 6:
                w.h = spec["h"]
                w.updated_at = now
            if spec["widget_type"] == "bar":
                cfg = _parse_json(w.config_json, {})
                cfg["data_labels"] = False
                w.config_json = _dump_json(cfg)
                w.updated_at = now
        else:
            next_sort += 1
            w = DashboardWidget(
                tab_id=tab.id,
                title=spec["title"],
                widget_type=spec["widget_type"],
                source_key=spec["source_key"],
                config_json=_dump_json(spec["config"]),
                x=spec["x"],
                y=spec["y"],
                w=spec["w"],
                h=spec["h"],
                sort_order=next_sort,
                created_at=now,
                updated_at=now,
            )
            db.add(w)
            db.flush()
            widgets.append(w)
        managed_preset_ids.add(w.id)

    db.commit()


def _seed_roster_margin(db, DashboardDashboard, DashboardTab, DashboardWidget) -> None:
    """幂等预置「交付毛利总览」：花名册收入/薪资/GM$/GM% 概览 + 按客户拆分。"""
    existing = (
        db.query(DashboardDashboard)
        .filter(DashboardDashboard.name == _ROSTER_SEED_NAME)
        .first()
    )
    if existing:
        return

    now = _now()
    d = DashboardDashboard(
        name=_ROSTER_SEED_NAME,
        description="系统预置交付毛利总览",
        layout_json="{}",
        created_by="system",
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    db.flush()

    sample_client_id = _roster_margin_sample_client_id(db)
    widgets_spec = _roster_margin_preset_specs(sample_client_id)

    _seed_widgets(db, DashboardTab, DashboardWidget, d.id, _ROSTER_MARGIN_TAB_NAME, widgets_spec, now)
    db.commit()
