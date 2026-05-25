from __future__ import annotations

from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.permissions import ROLE_SUPER_ADMIN
from auth.service import AuthContext

RESERVED_ROLE_CODES = frozenset({
    ROLE_SUPER_ADMIN,
    "SALES",
    "DELIVERY",
    "VIEWER",
    "RESTRICTED",
})


class PolicyError(ValueError):
    pass


def _fetch_role(db: Session, role_id: int) -> Optional[dict]:
    row = db.execute(
        text("SELECT id, code, name, description, is_builtin FROM sys_role WHERE id = :id"),
        {"id": role_id},
    ).mappings().first()
    return dict(row) if row else None


def count_active_super_admins(db: Session, exclude_user_id: Optional[int] = None) -> int:
    q = (
        "SELECT COUNT(DISTINCT u.id) FROM sys_user u "
        "JOIN sys_user_role ur ON ur.user_id = u.id "
        "JOIN sys_role r ON r.id = ur.role_id "
        "WHERE u.status = 'active' AND r.code = :code"
    )
    params = {"code": ROLE_SUPER_ADMIN}
    if exclude_user_id is not None:
        q += " AND u.id != :uid"
        params["uid"] = exclude_user_id
    row = db.execute(text(q), params).fetchone()
    return int(row[0]) if row else 0


def user_has_super_admin_role(db: Session, user_id: int) -> bool:
    return ROLE_SUPER_ADMIN in _user_roles(db, user_id)


def _user_roles(db: Session, user_id: int) -> List[str]:
    rows = db.execute(
        text(
            "SELECT r.code FROM sys_role r "
            "JOIN sys_user_role ur ON ur.role_id = r.id WHERE ur.user_id = :uid"
        ),
        {"uid": user_id},
    ).fetchall()
    return [str(r[0]) for r in rows]


def assert_actor_is_super(ctx: AuthContext) -> None:
    if not ctx.is_super:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")


def assert_can_edit_role_permissions(ctx: AuthContext, db: Session, role_id: int) -> dict:
    role = _fetch_role(db, role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")
    if role.get("code") == ROLE_SUPER_ADMIN and not ctx.is_super:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅超级管理员可修改超级管理员角色权限",
        )
    return role


def _role_exists(db: Session, code: str) -> bool:
    row = db.execute(text("SELECT 1 FROM sys_role WHERE code = :c"), {"c": code}).fetchone()
    return row is not None


def assert_user_roles_change(
    db: Session,
    *,
    user_id: int,
    new_role_codes: List[str],
    actor: AuthContext,
) -> None:
    if not new_role_codes:
        raise PolicyError("至少分配一个角色")
    for code in new_role_codes:
        if not _role_exists(db, code):
            raise PolicyError(f"无效角色: {code}")
    if user_id <= 0:
        return
    current = _user_roles(db, user_id)
    had_super = ROLE_SUPER_ADMIN in current
    will_have_super = ROLE_SUPER_ADMIN in new_role_codes
    if had_super and not will_have_super:
        others = count_active_super_admins(db, exclude_user_id=user_id)
        if others == 0:
            raise PolicyError("不能移除系统中最后一个超级管理员的角色")


def assert_user_status_change(
    db: Session,
    *,
    user_id: int,
    new_status: str,
    actor: AuthContext,
) -> None:
    if new_status != "active" and user_has_super_admin_role(db, user_id):
        others = count_active_super_admins(db, exclude_user_id=user_id)
        if others == 0:
            raise PolicyError("不能禁用系统中最后一个超级管理员")


def validate_custom_role_name(name: str) -> str:
    n = (name or "").strip()
    if not n or len(n) > 64:
        raise PolicyError("角色名称无效")
    return n


def generate_custom_role_code() -> str:
    import time

    return f"CUSTOM_{int(time.time())}"
