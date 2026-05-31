"""Sales-to-Delivery handoff business logic (no SQLAlchemy models here)."""
from __future__ import annotations

import json
import os
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(BASE_DIR, "data", "requirement_spec.json")
SCHEMA_PATH = os.path.join(BASE_DIR, "data", "requirement_schema.json")
REVIEWERS_STORE = os.path.join(BASE_DIR, ".crm_delivery_reviewers.json")

HANDOFF_STATUSES = frozenset({"draft", "pending_review", "rejected", "approved", "superseded"})

HANDOFF_REJECT_CODES = {
    "REQ_INACCURATE": "需求信息不准",
    "REQ_INCOMPLETE": "需求要素缺失",
    "RESOURCE_SHORTAGE": "资源不足",
    "COMMERCIAL_RISK": "商务条件未就绪",
    "OTHER": "其他",
}

HANDOFF_STATUS_LABELS = {
    "draft": "草稿",
    "pending_review": "待审",
    "rejected": "已驳回",
    "approved": "已通过",
    "superseded": "已取代",
}


def resolve_client_handoff_status(latest_handoff: Any) -> str:
    """客户当前交接状态；无有效交接单时为 none（未提交）。"""
    return latest_handoff.status if latest_handoff else "none"


def build_clients_handoff_summary(handoff_rows: List[Any]) -> Dict[str, Dict[str, Any]]:
    """按客户汇总最新交接状态（供 /api/clients/handoff-summary 使用）。"""
    by_client: Dict[int, Any] = {}
    for r in handoff_rows:
        prev = by_client.get(r.client_id)
        if not prev or r.version > prev.version or (r.version == prev.version and r.id > prev.id):
            by_client[r.client_id] = r
    return {
        str(cid): {
            "status": h.status,
            "status_label": HANDOFF_STATUS_LABELS.get(h.status, h.status),
            "handoff_id": h.id,
            "version": h.version,
        }
        for cid, h in by_client.items()
    }


def empty_requirement() -> Dict[str, Any]:
    return {
        "context": {
            "project_type": "",
            "location": "",
            "timezone": "",
            "attendance_rules": "",
            "client_contact": "",
        },
        "tech_stack": {
            "languages": [],
            "middleware": [],
            "version_constraints": "",
            "env_requirements": "",
        },
        "positions": [],
        "delivery_constraints": {
            "sla": "",
            "acceptance": "",
            "compliance": "",
            "risk_notes": "",
        },
        "commercial": {
            "quote_ref": "",
            "estimated_amount": "",
            "payment_cycle": "",
            "has_po": False,
            "has_framework": False,
        },
        "urgent": False,
    }


def load_requirement_spec() -> Dict[str, Any]:
    try:
        with open(SPEC_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"required_fields": ["context.project_type", "tech_stack.languages", "positions"]}


def _get_nested(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _is_filled(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, list):
        return len(val) > 0
    if isinstance(val, dict):
        return any(_is_filled(v) for v in val.values())
    return True


def compute_completeness(requirement: Dict[str, Any]) -> Dict[str, Any]:
    spec = load_requirement_spec()
    required = spec.get("required_fields") or []
    labels = spec.get("field_labels") or {}
    missing: List[Dict[str, str]] = []
    for field in required:
        val = _get_nested(requirement, field)
        if not _is_filled(val):
            missing.append({"field": field, "label": labels.get(field, field)})
    total = len(required) or 1
    score = int(round(100 * (total - len(missing)) / total))
    return {"score": score, "missing": missing, "total_required": total}


def validate_for_submit(requirement: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    spec = load_requirement_spec()
    rules = spec.get("submit_rules") or {}
    comp = compute_completeness(requirement)
    for m in comp["missing"]:
        errors.append(f"缺少必填项：{m['label']}")

    positions = requirement.get("positions") or []
    min_pos = int(rules.get("min_positions") or 1)
    if len(positions) < min_pos:
        errors.append(f"岗位编制矩阵至少需要 {min_pos} 行")

    langs = (requirement.get("tech_stack") or {}).get("languages") or []
    if rules.get("require_language") and not langs:
        errors.append("技术栈主语言/框架为必填")

    for i, row in enumerate(positions):
        if not str(row.get("role") or "").strip():
            errors.append(f"岗位矩阵第 {i + 1} 行：岗位名称必填")
        if not str(row.get("start_date") or "").strip():
            errors.append(f"岗位矩阵第 {i + 1} 行：到岗时间必填")

    urgent_threshold = int(rules.get("urgent_days_threshold") or 90)
    today = date.today()
    for row in positions:
        sd = str(row.get("start_date") or "").strip()
        if not sd:
            continue
        try:
            d = datetime.strptime(sd[:10], "%Y-%m-%d").date()
            if (d - today).days <= urgent_threshold and not requirement.get("urgent"):
                errors.append(f"到岗时间 {sd} 在 {urgent_threshold} 天内，请勾选「加急」并说明")
        except ValueError:
            errors.append(f"到岗时间格式无效：{sd}")

    return (len(errors) == 0, errors)


def merge_ai_into_requirement(base: Dict[str, Any], ai_data: Dict[str, Any]) -> Dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key in ("context", "tech_stack", "delivery_constraints", "commercial"):
        if isinstance(ai_data.get(key), dict):
            out[key].update({k: v for k, v in ai_data[key].items() if v not in (None, "", [])})
    if isinstance(ai_data.get("positions"), list) and ai_data["positions"]:
        out["positions"] = ai_data["positions"]
    if "urgent" in ai_data:
        out["urgent"] = bool(ai_data["urgent"])
    return out


def generate_brief_markdown(
    client_name: str,
    handoff_title: str,
    requirement: Dict[str, Any],
    sales_owner: str,
) -> str:
    ctx = requirement.get("context") or {}
    tech = requirement.get("tech_stack") or {}
    positions = requirement.get("positions") or []
    dc = requirement.get("delivery_constraints") or {}
    comm = requirement.get("commercial") or {}

    lines = [
        f"# 项目启动前置需求书",
        "",
        f"- **客户**：{client_name}",
        f"- **交接标题**：{handoff_title or '—'}",
        f"- **销售负责人**：{sales_owner or '—'}",
        f"- **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 背景",
        f"- 项目类型：{ctx.get('project_type') or '待确认'}",
        f"- 办公地点：{ctx.get('location') or '待确认'}",
        f"- 客户接口人：{ctx.get('client_contact') or '待确认'}",
        "",
        "## 技术栈",
        f"- 主语言/框架：{', '.join(tech.get('languages') or []) or '待确认'}",
        f"- 中间件：{', '.join(tech.get('middleware') or []) or '—'}",
        f"- 版本约束：{tech.get('version_constraints') or '—'}",
        "",
        "## 编制需求",
    ]
    if positions:
        lines.append("| 岗位 | 级别 | 编制 | 计费 | 到岗 | 技能要求 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for p in positions:
            lines.append(
                f"| {p.get('role','')} | {p.get('level','')} | {p.get('headcount','')} "
                f"| {p.get('billing_unit','')} | {p.get('start_date','')} | {p.get('skills','')} |"
            )
    else:
        lines.append("（暂无岗位矩阵）")

    lines.extend(
        [
            "",
            "## 到岗计划",
            f"- 加急：{'是' if requirement.get('urgent') else '否'}",
            "",
            "## 交付约束",
            f"- SLA：{dc.get('sla') or '—'}",
            f"- 验收标准：{dc.get('acceptance') or '—'}",
            f"- 合规：{dc.get('compliance') or '—'}",
            f"- 风险自评：{dc.get('risk_notes') or '—'}",
            "",
            "## 商务前置",
            f"- 报价单：{comm.get('quote_ref') or '—'}",
            f"- 预计金额：{comm.get('estimated_amount') or '—'}",
            f"- 付款周期：{comm.get('payment_cycle') or '—'}",
            f"- 已有 PO：{'是' if comm.get('has_po') else '否'}",
            f"- 框架合同：{'是' if comm.get('has_framework') else '否'}",
        ]
    )
    return "\n".join(lines)


def parse_requirement_json(raw: Optional[str]) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return empty_requirement()
    base = empty_requirement()
    if isinstance(data, dict):
        for k in base:
            if k in data and data[k] is not None:
                if isinstance(base[k], dict) and isinstance(data[k], dict):
                    base[k].update(data[k])
                else:
                    base[k] = data[k]
    return base


def load_delivery_reviewers(default_admin: str) -> List[str]:
    if os.path.isfile(REVIEWERS_STORE):
        try:
            with open(REVIEWERS_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [str(x).strip() for x in data if str(x).strip()]
        except (OSError, json.JSONDecodeError):
            pass
    env = os.environ.get("CRM_DELIVERY_REVIEWERS", "").strip()
    if env:
        return [x.strip() for x in env.split(",") if x.strip()]
    return [default_admin]


def is_delivery_reviewer(username: str, default_admin: str) -> bool:
    return username in load_delivery_reviewers(default_admin)


def ai_parse_schema_hint() -> str:
    return json.dumps(
        {
            "context": {"project_type": "驻场|离岸|混合", "location": "", "client_contact": ""},
            "tech_stack": {"languages": ["Java"], "middleware": [], "version_constraints": ""},
            "positions": [
                {
                    "role": "Java后端",
                    "level": "高级",
                    "headcount": 2,
                    "billing_unit": "人月",
                    "start_date": "2026-06-01",
                    "skills": "",
                }
            ],
            "delivery_constraints": {"sla": "", "risk_notes": ""},
            "commercial": {"estimated_amount": "", "payment_cycle": "月度"},
            "urgent": False,
        },
        ensure_ascii=False,
        indent=2,
    )
