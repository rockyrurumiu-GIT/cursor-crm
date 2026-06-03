from __future__ import annotations

from typing import Any, List, Optional, Set, Type

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from auth.data_scope_catalog import (
    CLIENT_DEPT_COLS_FOR_LIST,
    RESOURCE_CRM_CLIENT,
    SCOPE_ALL,
    SCOPE_ASSIGNED,
    SCOPE_DEPT,
    SCOPE_DEPT_AND_CHILD,
    SCOPE_NONE,
    SCOPE_SELF,
    client_scope_columns,
    merge_scope_types,
)
from auth.service import AuthContext


def get_effective_data_scope(ctx: AuthContext, resource_code: str, action: str) -> str:
    if ctx.is_super:
        return SCOPE_ALL
    return ctx.role_data_scopes.get((resource_code, action), SCOPE_NONE)


def assert_data_scope(ctx: AuthContext, resource_code: str, action: str) -> str:
    scope = get_effective_data_scope(ctx, resource_code, action)
    if scope == SCOPE_NONE:
        raise HTTPException(status_code=403, detail=f"无数据范围: {resource_code}.{action}")
    return scope


def _dept_subtree_ids(db: Session, dept_ids: List[int]) -> Set[int]:
    if not dept_ids:
        return set()
    from sqlalchemy import text

    out: Set[int] = set()
    for dept_id in dept_ids:
        prow = db.execute(
            text("SELECT path FROM sys_dept WHERE id = :id"),
            {"id": dept_id},
        ).fetchone()
        if not prow:
            continue
        path = str(prow[0] or "")
        if not path:
            continue
        rows = db.execute(
            text("SELECT id FROM sys_dept WHERE path = :p OR path LIKE :pfx"),
            {"p": path, "pfx": f"{path}/%"},
        ).fetchall()
        out.update(int(r[0]) for r in rows)
    return out


def _crm_client_dept_or_filter(client_model: Type[Any], dept_ids: list[int] | set[int]):
    """Match clients when any sales/delivery/recruitment dept column is in dept_ids."""
    clauses = []
    for col_name in CLIENT_DEPT_COLS_FOR_LIST:
        col = getattr(client_model, col_name, None)
        if col is not None:
            clauses.append(col.in_(dept_ids))
    if not clauses:
        return client_model.id == -1
    if len(clauses) == 1:
        return clauses[0]
    return or_(*clauses)


def _apply_scope_to_client_query(
    query: Query,
    scope: str,
    ctx: AuthContext,
    db: Session,
    client_model: Type[Any],
    *,
    sales: bool,
    resource_code: str | None = None,
):
    """Filter a Client ORM query by effective scope."""
    if scope == SCOPE_ALL:
        return query
    if scope == SCOPE_NONE:
        return query.filter(client_model.id == -1)
    if ctx.user_id is None:
        return query.filter(client_model.id == -1)

    owner_col, dept_col, assigned_col = client_scope_columns("sales" if sales else "delivery")
    OwnerCol = getattr(client_model, owner_col)
    DeptCol = getattr(client_model, dept_col)
    AssignedCol = getattr(client_model, assigned_col) if assigned_col else None

    if scope == SCOPE_SELF:
        return query.filter(OwnerCol == ctx.user_id)
    if scope == SCOPE_ASSIGNED:
        if AssignedCol is not None:
            return query.filter(or_(OwnerCol == ctx.user_id, AssignedCol == ctx.user_id))
        return query.filter(OwnerCol == ctx.user_id)
    if scope == SCOPE_DEPT:
        dept_ids = ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])
        if not dept_ids:
            return query.filter(client_model.id == -1)
        if resource_code == RESOURCE_CRM_CLIENT:
            return query.filter(_crm_client_dept_or_filter(client_model, dept_ids))
        return query.filter(DeptCol.in_(dept_ids))
    if scope == SCOPE_DEPT_AND_CHILD:
        dept_ids = list(_dept_subtree_ids(db, ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])))
        if not dept_ids:
            return query.filter(client_model.id == -1)
        if resource_code == RESOURCE_CRM_CLIENT:
            return query.filter(_crm_client_dept_or_filter(client_model, dept_ids))
        return query.filter(DeptCol.in_(dept_ids))
    return query.filter(client_model.id == -1)


def apply_client_scope(
    query: Query,
    db: Session,
    ctx: AuthContext,
    resource_code: str,
    action: str,
    client_model: Type[Any],
) -> Query:
    scope = get_effective_data_scope(ctx, resource_code, action)
    sales = resource_code == RESOURCE_CRM_CLIENT or resource_code.startswith("crm.")
    return _apply_scope_to_client_query(
        query, scope, ctx, db, client_model, sales=sales, resource_code=resource_code
    )


def scoped_client_ids(
    db: Session,
    ctx: AuthContext,
    resource_code: str,
    action: str,
    client_model: Type[Any],
) -> Optional[Set[int]]:
    """Return None if all clients visible, else set of allowed client ids (may be empty)."""
    scope = get_effective_data_scope(ctx, resource_code, action)
    if scope == SCOPE_ALL:
        return None
    q = db.query(client_model.id)
    q = apply_client_scope(q, db, ctx, resource_code, action, client_model)
    return {int(r[0]) for r in q.all()}


def visible_client_ids(
    db: Session,
    ctx: AuthContext,
    client_model: Type[Any],
    action: str = "read",
) -> Optional[Set[int]]:
    """Union of client ids visible via any mapped resource the user may access."""
    from auth.data_scope_catalog import PERMISSION_TO_RESOURCE, RESOURCE_FILE

    if ctx.is_super:
        return None
    merged: Set[int] = set()
    checked = False
    for perm, resource in PERMISSION_TO_RESOURCE.items():
        if perm not in ctx.permissions:
            continue
        if resource == RESOURCE_FILE:
            continue
        if action == "export":
            if not (perm.endswith(".read") or perm.endswith(".write")):
                continue
        elif action == "read" and not perm.endswith(".read"):
            continue
        elif action == "write" and not perm.endswith(".write"):
            continue
        elif action not in ("read", "write", "export"):
            continue
        scoped = scoped_client_ids(db, ctx, resource, action, client_model)
        checked = True
        if scoped is None:
            return None
        merged.update(scoped)
    if not checked:
        return set()
    return merged


def assert_client_visible(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    client_model: Type[Any],
    *,
    action: str = "read",
) -> None:
    allowed = visible_client_ids(db, ctx, client_model, action=action)
    if allowed is None:
        return
    if client_id not in allowed:
        raise HTTPException(status_code=404, detail="客户不存在")


def assert_client_in_scope(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    client_model: Type[Any],
    resource_code: str,
    action: str,
) -> None:
    allowed = scoped_client_ids(db, ctx, resource_code, action, client_model)
    if allowed is None:
        return
    if client_id not in allowed:
        raise HTTPException(status_code=404, detail="客户不存在")


def filter_query_by_client_scope(
    query: Query,
    db: Session,
    ctx: AuthContext,
    resource_code: str,
    action: str,
    client_id_column: Any,
    client_model: Type[Any],
) -> Query:
    allowed = scoped_client_ids(db, ctx, resource_code, action, client_model)
    if allowed is None:
        return query
    if not allowed:
        return query.filter(client_id_column == -1)
    return query.filter(client_id_column.in_(allowed))


def build_data_scope_where(
    db: Session,
    ctx: AuthContext,
    resource_code: str,
    action: str,
    owner_user_column: str,
    owner_dept_column: str,
    assigned_user_column: Optional[str] = None,
) -> tuple[str, dict]:
    """Raw SQL fragment for legacy queries. Returns (sql_fragment, params)."""
    scope = get_effective_data_scope(ctx, resource_code, action)
    if scope == SCOPE_ALL:
        return "1=1", {}
    if scope == SCOPE_NONE or ctx.user_id is None:
        return "1=0", {}
    uid = ctx.user_id
    if scope == SCOPE_SELF:
        return f"{owner_user_column} = :ds_uid", {"ds_uid": uid}
    if scope == SCOPE_ASSIGNED:
        if assigned_user_column:
            return (
                f"({owner_user_column} = :ds_uid OR {assigned_user_column} = :ds_uid)",
                {"ds_uid": uid},
            )
        return f"{owner_user_column} = :ds_uid", {"ds_uid": uid}
    if scope == SCOPE_DEPT:
        dept_ids = ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])
        if not dept_ids:
            return "1=0", {}
        placeholders = ", ".join(f":ds_dept_{i}" for i in range(len(dept_ids)))
        params = {f"ds_dept_{i}": did for i, did in enumerate(dept_ids)}
        return f"{owner_dept_column} IN ({placeholders})", params
    if scope == SCOPE_DEPT_AND_CHILD:
        from sqlalchemy import text

        dept_ids = list(
            _dept_subtree_ids(
                db,
                ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else []),
            )
        )
        if not dept_ids:
            return "1=0", {}
        placeholders = ", ".join(f":ds_dept_{i}" for i in range(len(dept_ids)))
        params = {f"ds_dept_{i}": did for i, did in enumerate(dept_ids)}
        return f"{owner_dept_column} IN ({placeholders})", params
    return "1=0", {}


def default_owner_fields(ctx: AuthContext) -> dict:
    """Fields to set when creating a client."""
    out: dict = {}
    if ctx.user_id is not None:
        out["owner_user_id"] = ctx.user_id
    if ctx.primary_dept_id is not None:
        out["owner_dept_id"] = ctx.primary_dept_id
    return out
