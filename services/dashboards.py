"""Dashboard builder — CRUD, whitelisted aggregation, seed."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Type
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func, not_, text
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth import service as auth_svc
from auth.service import AuthContext
from schemas.dashboards import (
    CHART_COLORS,
    CHART_WIDGET_TYPES,
    DATA_WIDGET_TYPES,
    DATA_SOURCES,
    DATE_GROUPS,
    DEFAULT_COLOR,
    DEFAULT_SORT,
    FILTER_OPS,
    METRICS,
    NUMERIC_METRICS,
    SORT_MODES,
    WIDGET_TYPES,
    get_field,
    get_source,
)
from services.clients import scoped_client_query
from services.delivery_roster import sql_roster_employment_active_pool

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
    "DeliveryPipelineEntry": "DeliveryPipelineEntry",
    "RosterEntry": "RosterEntry",
    "DeliverySettlementEntry": "DeliverySettlementEntry",
    "DeliveryInterviewEntry": "DeliveryInterviewEntry",
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


def validate_rich_text(content: str) -> str:
    text = (content or "").strip()
    if "<" in text or ">" in text:
        raise HTTPException(status_code=400, detail="rich_text 不允许 HTML")
    return text


def validate_widget_config(
    widget_type: str,
    source_key: str,
    config: dict,
) -> dict:
    if widget_type not in WIDGET_TYPES:
        raise HTTPException(status_code=400, detail=f"未知 widget 类型: {widget_type}")

    out: dict = {}

    if widget_type == "iframe":
        out["url"] = validate_iframe_url(config.get("url", ""))
        return out

    if widget_type == "rich_text":
        out["content"] = validate_rich_text(config.get("content", ""))
        return out

    if widget_type == "roster_summary":
        if source_key != "roster_entries":
            raise HTTPException(status_code=400, detail="roster_summary 仅支持花名册数据源")
        client_id = config.get("client_id")
        if client_id not in (None, "", 0):
            try:
                out["client_id"] = int(client_id)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="client_id 必须是整数")
        out["include_left"] = bool(config.get("include_left", False))
        return out

    if widget_type not in DATA_WIDGET_TYPES:
        raise HTTPException(status_code=400, detail=f"widget 类型不支持数据配置: {widget_type}")

    if not source_key or source_key not in DATA_SOURCES:
        raise HTTPException(status_code=400, detail=f"未知数据源: {source_key}")

    metric = (config.get("metric") or "count").strip()
    if metric not in METRICS:
        raise HTTPException(status_code=400, detail=f"未知聚合方式: {metric}")

    field = (config.get("field") or "").strip()
    if metric in NUMERIC_METRICS:
        if not field:
            raise HTTPException(status_code=400, detail="sum/avg/min/max 需要指定 field")
        fdef = get_field(source_key, field)
        if not fdef or fdef.kind != "numeric":
            raise HTTPException(status_code=400, detail=f"字段不可用于数值聚合: {field}")
    elif field:
        fdef = get_field(source_key, field)
        if not fdef:
            raise HTTPException(status_code=400, detail=f"未知字段: {field}")

    group_by = (config.get("group_by") or "").strip()
    if group_by:
        gdef = get_field(source_key, group_by)
        if not gdef:
            raise HTTPException(status_code=400, detail=f"未知分组字段: {group_by}")
        if gdef.kind == "datetime":
            raise HTTPException(status_code=400, detail="datetime 字段请使用 date_group 而非 group_by")

    date_group = (config.get("date_group") or "").strip()
    if date_group:
        if date_group not in DATE_GROUPS:
            raise HTTPException(status_code=400, detail=f"未知 date_group: {date_group}")
        dg_field = (config.get("group_by") or "created_at").strip()
        dgdef = get_field(source_key, dg_field)
        if not dgdef or dgdef.kind != "datetime":
            raise HTTPException(status_code=400, detail="date_group 仅支持 datetime 字段")
        group_by = dg_field

    filters = config.get("filters") or []
    if not isinstance(filters, list):
        raise HTTPException(status_code=400, detail="filters 必须是数组")
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

    limit = config.get("limit", 20)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="limit 必须是整数")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit 须在 1–100 之间")

    if widget_type in CHART_WIDGET_TYPES and not group_by and metric == "count":
        pass  # count without group is ok for number widget only
    if widget_type in CHART_WIDGET_TYPES and not group_by:
        raise HTTPException(status_code=400, detail="图表 widget 需要 group_by 或 date_group")

    out["metric"] = metric
    out["field"] = field
    out["group_by"] = group_by
    if date_group:
        out["date_group"] = date_group
    out["filters"] = clean_filters
    out["limit"] = limit
    out["prefix"] = str(config.get("prefix") or "")
    out["suffix"] = str(config.get("suffix") or "")

    # Style options (Twenty-parity) — fixed enums / booleans only.
    color = (config.get("color") or DEFAULT_COLOR).strip()
    if color not in CHART_COLORS:
        raise HTTPException(status_code=400, detail=f"未知配色: {color}")
    out["color"] = color

    sort_mode = (config.get("sort") or DEFAULT_SORT).strip()
    if sort_mode not in SORT_MODES:
        raise HTTPException(status_code=400, detail=f"未知排序: {sort_mode}")
    out["sort"] = sort_mode

    out["show_legend"] = bool(config.get("show_legend", True))
    out["show_value_center"] = bool(config.get("show_value_center", True))
    out["data_labels"] = bool(config.get("data_labels", False))
    out["hide_empty"] = bool(config.get("hide_empty", False))
    if source_key == "roster_entries":
        out["include_left"] = bool(config.get("include_left", False))
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


def _apply_filters(q, Model: Type[Any], filters: list):
    for flt in filters:
        col = _column(Model, flt["field"])
        val = flt.get("value", "")
        op = flt["op"]
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


def _finalize_series(
    labels: list,
    values: list,
    sort_mode: str,
    hide_empty: bool,
    limit: int,
    prefix: str,
    suffix: str,
    preserve_order: bool = False,
) -> dict:
    pairs = list(zip(labels, values))
    if hide_empty:
        pairs = [(l, v) for (l, v) in pairs if v]
    if not preserve_order:
        if sort_mode == "label_asc":
            pairs.sort(key=lambda x: str(x[0]))
        elif sort_mode == "label_desc":
            pairs.sort(key=lambda x: str(x[0]), reverse=True)
        elif sort_mode == "value_asc":
            pairs.sort(key=lambda x: x[1])
        else:  # value_desc (default)
            pairs.sort(key=lambda x: x[1], reverse=True)
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
    }


def query_widget_data(
    db: Session,
    ctx: AuthContext,
    source_key: str,
    config: dict,
    models: dict,
) -> dict:
    if not user_can_read_source(ctx, source_key):
        return {"status": "forbidden", "message": "无权限查看该数据源"}

    metric = config.get("metric", "count")
    field_key = config.get("field", "")
    group_by = config.get("group_by", "")
    date_group = config.get("date_group", "")
    filters = config.get("filters") or []
    limit = int(config.get("limit") or 20)
    prefix = config.get("prefix", "")
    suffix = config.get("suffix", "")
    sort_mode = config.get("sort") or DEFAULT_SORT
    hide_empty = bool(config.get("hide_empty", False))

    Model = _get_model(models, source_key)
    q = _scoped_query(db, ctx, source_key, models)
    q = _apply_roster_active_pool(q, source_key, config, Model)
    q = _apply_filters(q, Model, filters)

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
        return _finalize_series(labels, values, sort_mode, hide_empty, limit, prefix, suffix)

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
            # Time series: keep chronological order regardless of sort.
            return _finalize_series(
                labels, values, sort_mode, hide_empty, limit, prefix, suffix,
                preserve_order=True,
            )

        if metric == "count":
            rows = (
                q.with_entities(col.label("label"), func.count().label("cnt"))
                .group_by(col)
                .all()
            )
            labels = [str(r.label or "(空)") for r in rows]
            values = [float(r.cnt) for r in rows]
            return _finalize_series(
                labels, values, sort_mode, hide_empty, limit, prefix, suffix,
            )

        # grouped numeric metric — compute in Python
        all_rows = q.all()
        buckets: Dict[str, list] = {}
        for row in all_rows:
            key = str(getattr(row, group_by, None) or "(空)")
            buckets.setdefault(key, []).append(row)
        labels = []
        values = []
        for label, bucket_rows in buckets.items():
            labels.append(label)
            values.append(_aggregate_rows(bucket_rows, metric, field_key))
        return _finalize_series(
            labels, values, sort_mode, hide_empty, limit, prefix, suffix,
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

def list_dashboards(db: Session, DashboardDashboard, DashboardTab, DashboardWidget) -> list:
    dashboards = db.query(DashboardDashboard).order_by(DashboardDashboard.id).all()
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


def create_dashboard(db: Session, body: dict, ctx: AuthContext, DashboardDashboard) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    now = _now()
    d = DashboardDashboard(
        name=name,
        description=(body.get("description") or "").strip(),
        layout_json=_dump_json(body.get("layout_json") or {}),
        created_by=ctx.username,
        created_at=now,
        updated_at=now,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
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
    t = DashboardTab(
        dashboard_id=dashboard_id,
        name=name,
        sort_order=int(body.get("sort_order") or 0),
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


def create_widget(db: Session, tab_id: int, body: dict, DashboardTab, DashboardWidget) -> dict:
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
    clean_config = validate_widget_config(widget_type, source_key, config)
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


def update_widget(db: Session, widget_id: int, body: dict, DashboardWidget) -> dict:
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
        clean = validate_widget_config(widget_type, w.source_key or source_key, config)
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
    return query_widget_data(db, ctx, source_key, config, models)


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
            "x": 0, "y": 0, "w": 6, "h": 6,
        },
        {
            "title": "单客户毛利概览",
            "widget_type": "roster_summary",
            "source_key": "roster_entries",
            "config": dict(client_config),
            "x": 6, "y": 0, "w": 6, "h": 6,
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
            "x": 0, "y": 6, "w": 6, "h": 7,
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
            "x": 6, "y": 6, "w": 6, "h": 7,
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
            w.x = spec["x"]
            w.y = spec["y"]
            w.w = spec["w"]
            w.h = spec["h"]
            w.updated_at = now
            if spec["widget_type"] == "bar":
                cfg = _parse_json(w.config_json, {})
                cfg["data_labels"] = False
                w.config_json = _dump_json(cfg)
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

    preset_rects = _preset_rects_from_specs(specs)
    base_y = _max_preset_bottom(specs)
    all_widgets = db.query(DashboardWidget).filter(DashboardWidget.tab_id == tab.id).all()

    to_relocate = []
    for w in all_widgets:
        if w.id in managed_preset_ids:
            continue
        _x, wy, _ww, _wh = _widget_rect(w)
        if wy >= base_y and not _widget_overlaps_any_preset_rect(w, preset_rects):
            continue
        if _widget_overlaps_any_preset_rect(w, preset_rects):
            to_relocate.append(w)

    to_relocate.sort(key=lambda w: (int(w.y or 0), int(w.x or 0), w.id))
    offset = 0
    for w in to_relocate:
        _x, _y, _ww, height = _widget_rect(w)
        w.x = 0
        w.y = base_y + offset
        w.updated_at = now
        offset += height

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
