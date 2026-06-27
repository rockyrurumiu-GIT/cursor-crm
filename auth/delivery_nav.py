"""Delivery org department helpers for help-center nav visibility."""
from __future__ import annotations

from typing import Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import data_scope as ds
from auth.service import AuthContext

_DELIVERY_DEPT_MATCH_SQL = (
    "name LIKE :pat OR UPPER(code) LIKE 'DELIVERY%' OR path LIKE '%/DELIVERY%'"
)


def delivery_org_dept_ids(db: Session) -> Set[int]:
    rows = db.execute(
        text(
            "SELECT id FROM sys_dept WHERE status = 'active' "
            f"AND ({_DELIVERY_DEPT_MATCH_SQL})"
        ),
        {"pat": "%交付%"},
    ).fetchall()
    root_ids = [int(r[0]) for r in rows]
    if not root_ids:
        return set()
    return ds._dept_subtree_ids(db, root_ids)


def user_in_delivery_org_dept(db: Session, ctx: AuthContext) -> bool:
    if ctx.is_super or ctx.user_id is None:
        return False
    user_depts = ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])
    if not user_depts:
        return False
    delivery_ids = delivery_org_dept_ids(db)
    if not delivery_ids:
        return False
    return any(int(d) in delivery_ids for d in user_depts)
