"""RMS Offer approval chain configuration (Phase 6B-0)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import utc_date_str

SCOPE_DEFAULT = "default"
SCOPE_DEPT_PREFIX = "dept:"

STEP_DEPT_SUPERIOR = "dept_superior"
STEP_OPS_HEAD = "ops_head"
STEP_GM = "gm"

STEP_TYPE_LABELS = {
    STEP_DEPT_SUPERIOR: "部门上级审批中",
    STEP_OPS_HEAD: "经营负责人审批中",
    STEP_GM: "总经理审批中",
}

OFFER_APPROVAL_CONFIG_INCOMPLETE = "Offer审批链未配置完整，请联系管理员在系统管理中配置"

_CONFIG_FIELDS = ("dept_superior_user_id", "ops_head_user_id", "gm_user_id")


@dataclass
class ApprovalStepSpec:
    step_order: int
    step_type: str
    approver_user_id: int


def approval_node_label(step_type: str) -> str:
    return STEP_TYPE_LABELS.get((step_type or "").strip(), step_type or "")


def _dept_scope_key(dept_id: int) -> str:
    return f"{SCOPE_DEPT_PREFIX}{int(dept_id)}"


def _normalize_user_id(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        uid = int(raw)
    except (TypeError, ValueError):
        return None
    return uid if uid > 0 else None


def _extract_payload(payload: Dict[str, Any]) -> Dict[str, Optional[int]]:
    return {k: _normalize_user_id(payload.get(k)) for k in _CONFIG_FIELDS}


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "scope_key": row.scope_key,
        "dept_id": row.dept_id,
        "dept_superior_user_id": row.dept_superior_user_id,
        "ops_head_user_id": row.ops_head_user_id,
        "gm_user_id": row.gm_user_id,
        "updated_by": row.updated_by,
        "created_at": row.created_at or "",
        "updated_at": row.updated_at or "",
    }


def _dept_name_map(db: Session) -> Dict[int, str]:
    rows = db.execute(text("SELECT id, name FROM sys_dept")).fetchall()
    return {int(r[0]): (r[1] or "").strip() for r in rows if r[0] is not None}


def _dept_exists(db: Session, dept_id: int) -> bool:
    row = db.execute(
        text("SELECT id FROM sys_dept WHERE id = :did LIMIT 1"),
        {"did": int(dept_id)},
    ).first()
    return row is not None


def _user_exists(db: Session, user_id: int) -> bool:
    row = db.execute(
        text("SELECT id FROM sys_user WHERE id = :uid AND status = 'active' LIMIT 1"),
        {"uid": int(user_id)},
    ).first()
    return row is not None


def _validate_user_ids(db: Session, fields: Dict[str, Optional[int]]) -> None:
    for key, uid in fields.items():
        if uid is None:
            continue
        if not _user_exists(db, uid):
            raise HTTPException(status_code=400, detail=f"审批人配置无效：用户 {uid} 不存在或未激活 ({key})")


def _get_row_by_scope(db: Session, RmsOfferApprovalConfig: Type[Any], scope_key: str) -> Any:
    return (
        db.query(RmsOfferApprovalConfig)
        .filter(RmsOfferApprovalConfig.scope_key == scope_key)
        .first()
    )


def _merged_field_values(
    db: Session,
    RmsOfferApprovalConfig: Type[Any],
    dept_id: Optional[int],
) -> Dict[str, Optional[int]]:
    default_row = _get_row_by_scope(db, RmsOfferApprovalConfig, SCOPE_DEFAULT)
    dept_row = (
        _get_row_by_scope(db, RmsOfferApprovalConfig, _dept_scope_key(dept_id))
        if dept_id is not None
        else None
    )
    out: Dict[str, Optional[int]] = {}
    for field in _CONFIG_FIELDS:
        val = None
        if dept_row is not None and getattr(dept_row, field) is not None:
            val = getattr(dept_row, field)
        elif default_row is not None:
            val = getattr(default_row, field)
        out[field] = _normalize_user_id(val)
    return out


def _primary_dept_id(db: Session, user_id: int) -> Optional[int]:
    row = db.execute(
        text(
            "SELECT dept_id FROM sys_user_dept WHERE user_id = :uid AND is_primary = 1 LIMIT 1"
        ),
        {"uid": user_id},
    ).first()
    if row and row[0] is not None:
        return int(row[0])
    row = db.execute(
        text("SELECT dept_id FROM sys_user_dept WHERE user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).first()
    if row and row[0] is not None:
        return int(row[0])
    return None


def list_offer_approval_configs(db: Session, *, RmsOfferApprovalConfig: Type[Any]) -> Dict[str, Any]:
    rows = (
        db.query(RmsOfferApprovalConfig)
        .order_by(RmsOfferApprovalConfig.scope_key)
        .all()
    )
    dept_names = _dept_name_map(db)
    default: Optional[Dict[str, Any]] = None
    dept_overrides: List[Dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row)
        if row.scope_key == SCOPE_DEFAULT:
            default = item
        elif row.scope_key.startswith(SCOPE_DEPT_PREFIX):
            item["dept_name"] = dept_names.get(int(row.dept_id or 0), "")
            dept_overrides.append(item)
    dept_overrides.sort(key=lambda x: (x.get("dept_name") or "", x.get("dept_id") or 0))
    return {"default": default, "dept_overrides": dept_overrides}


def upsert_default_offer_approval_config(
    db: Session,
    payload: Dict[str, Any],
    ctx: AuthContext,
    *,
    RmsOfferApprovalConfig: Type[Any],
) -> Dict[str, Any]:
    fields = _extract_payload(payload)
    _validate_user_ids(db, fields)
    now = utc_date_str()
    row = _get_row_by_scope(db, RmsOfferApprovalConfig, SCOPE_DEFAULT)
    if row is None:
        row = RmsOfferApprovalConfig(
            scope_key=SCOPE_DEFAULT,
            dept_id=None,
            created_at=now,
        )
        db.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.updated_by = ctx.user_id
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return _row_to_dict(row)


def upsert_dept_offer_approval_config(
    db: Session,
    dept_id: int,
    payload: Dict[str, Any],
    ctx: AuthContext,
    *,
    RmsOfferApprovalConfig: Type[Any],
) -> Dict[str, Any]:
    did = int(dept_id)
    if not _dept_exists(db, did):
        raise HTTPException(status_code=404, detail="部门不存在")
    fields = _extract_payload(payload)
    _validate_user_ids(db, fields)
    scope_key = _dept_scope_key(did)
    now = utc_date_str()
    row = _get_row_by_scope(db, RmsOfferApprovalConfig, scope_key)
    if row is None:
        row = RmsOfferApprovalConfig(
            scope_key=scope_key,
            dept_id=did,
            created_at=now,
        )
        db.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.dept_id = did
    row.updated_by = ctx.user_id
    row.updated_at = now
    db.commit()
    db.refresh(row)
    item = _row_to_dict(row)
    names = _dept_name_map(db)
    item["dept_name"] = names.get(did, "")
    return item


def delete_dept_offer_approval_config(
    db: Session,
    dept_id: int,
    ctx: AuthContext,
    *,
    RmsOfferApprovalConfig: Type[Any],
) -> Dict[str, Any]:
    _ = ctx
    did = int(dept_id)
    row = _get_row_by_scope(db, RmsOfferApprovalConfig, _dept_scope_key(did))
    if row is None:
        raise HTTPException(status_code=404, detail="部门覆盖配置不存在")
    db.delete(row)
    db.commit()
    return {"ok": True, "dept_id": did}


def resolve_offer_approvers(
    db: Session,
    applicant_user_id: int,
    gm_pct: str,
    *,
    RmsOfferApprovalConfig: Type[Any],
) -> List[ApprovalStepSpec]:
    dept_id = _primary_dept_id(db, applicant_user_id)
    merged = _merged_field_values(db, RmsOfferApprovalConfig, dept_id)

    try:
        pct = float(str(gm_pct or "").strip().replace("%", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="GM% 格式无效")

    steps: List[ApprovalStepSpec] = []
    order = 1
    for step_type, key in (
        (STEP_DEPT_SUPERIOR, "dept_superior_user_id"),
        (STEP_OPS_HEAD, "ops_head_user_id"),
    ):
        uid = merged.get(key)
        if uid is None:
            raise HTTPException(status_code=409, detail=OFFER_APPROVAL_CONFIG_INCOMPLETE)
        if not _user_exists(db, uid):
            raise HTTPException(status_code=400, detail=f"审批人配置无效：用户 {uid} 不存在或未激活")
        steps.append(ApprovalStepSpec(step_order=order, step_type=step_type, approver_user_id=uid))
        order += 1

    if pct < 15:
        gm_uid = merged.get("gm_user_id")
        if gm_uid is None:
            raise HTTPException(status_code=409, detail=OFFER_APPROVAL_CONFIG_INCOMPLETE)
        if not _user_exists(db, gm_uid):
            raise HTTPException(status_code=400, detail=f"审批人配置无效：用户 {gm_uid} 不存在或未激活")
        steps.append(ApprovalStepSpec(step_order=order, step_type=STEP_GM, approver_user_id=gm_uid))

    return steps
