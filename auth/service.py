from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from auth import password as pwd
from auth.permissions import (
    ALL_PERMISSION_CODES,
    ROLE_DEFAULT_PERMISSIONS,
    ROLE_DELIVERY,
    ROLE_SALES,
    ROLE_SUPER_ADMIN,
    ROLE_VIEWER,
)
from auth.data_scope_catalog import (
    DATA_SCOPE_ACTIONS,
    PERMISSION_TO_RESOURCE,
    RESOURCE_CODES,
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_JOB,
    SCOPE_ALL,
    SCOPE_ASSIGNED,
    SCOPE_NONE,
    merge_scope_types,
    permission_to_resource,
)

DELETE_PERMISSION_BACKFILL_ID = "rbac_delete_permissions_backfill_v1"

DEPT_TYPE_GENERAL = "general"
DEPT_TYPE_BUSINESS = "business"
DEPT_TYPE_FUNCTIONAL = "functional"

DEPT_TYPE_LABELS: Dict[str, str] = {
    DEPT_TYPE_GENERAL: "通用",
    DEPT_TYPE_BUSINESS: "业务",
    DEPT_TYPE_FUNCTIONAL: "职能",
}

LEGACY_DEPT_TYPE_MAP: Dict[str, str] = {
    "sales": DEPT_TYPE_BUSINESS,
    "delivery": DEPT_TYPE_BUSINESS,
    "finance": DEPT_TYPE_FUNCTIONAL,
}


def normalize_dept_type(dept_type: str) -> str:
    t = (dept_type or DEPT_TYPE_GENERAL).strip() or DEPT_TYPE_GENERAL
    t = LEGACY_DEPT_TYPE_MAP.get(t, t)
    if t not in DEPT_TYPE_LABELS:
        opts = "、".join(DEPT_TYPE_LABELS.values())
        raise ValueError(f"部门类型无效，可选：{opts}")
    return t

DELETE_PERMISSION_COMPAT_PAIRS = (
    ("crm.clients.write", "crm.clients.delete"),
    ("crm.opportunities.write", "crm.opportunities.delete"),
    ("crm.contacts.write", "crm.contacts.delete"),
    ("crm.visits.write", "crm.visits.delete"),
    ("delivery.roster.write", "delivery.roster.delete"),
    ("delivery.pipeline.write", "delivery.pipeline.delete"),
    ("delivery.handbook.write", "delivery.handbook.delete"),
    ("delivery.employee_files.write", "delivery.employee_files.delete"),
    ("delivery.interviews.write", "delivery.interviews.delete"),
    ("delivery.settlement.write", "delivery.settlement.delete"),
    ("rms.jobs.write", "rms.jobs.delete"),
    ("rms.candidates.write", "rms.candidates.delete"),
    ("rms.applications.write", "rms.applications.delete"),
    ("dashboard.write", "dashboard.delete"),
    ("system.users.manage", "system.users.delete"),
    ("system.roles.manage", "system.roles.delete"),
)

_BUILTIN_ROLE_CODES = frozenset({
    ROLE_SUPER_ADMIN,
    ROLE_SALES,
    ROLE_DELIVERY,
    ROLE_VIEWER,
    "RESTRICTED",
})

SESSION_COOKIE_NAME = "crm_session"
SESSION_MAX_AGE = 7 * 86400


def auth_mode() -> str:
    return (os.environ.get("CRM_AUTH_MODE") or "rbac").strip().lower()


def is_rbac_mode() -> bool:
    return auth_mode() == "rbac"


def session_secret() -> str:
    return (os.environ.get("CRM_SESSION_SECRET") or "crm-dev-session-secret-change-me").strip()


@dataclass
class AuthContext:
    username: str
    user_id: Optional[int] = None
    display_name: str = ""
    roles: List[str] = field(default_factory=list)
    role_ids: List[int] = field(default_factory=list)
    permissions: Set[str] = field(default_factory=set)
    dept_ids: List[int] = field(default_factory=list)
    primary_dept_id: Optional[int] = None
    role_data_scopes: Dict[tuple[str, str], str] = field(default_factory=dict)
    is_super: bool = False
    must_change_password: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _user_session_version(db: Session, user_id: int) -> int:
    row = db.execute(
        text("SELECT session_version FROM sys_user WHERE id = :id"),
        {"id": user_id},
    ).fetchone()
    if not row:
        return 0
    try:
        return int(row[0] or 0)
    except (TypeError, ValueError):
        return 0


def make_session_token(user_id: int, username: str, session_version: int) -> str:
    exp = int(datetime.now(timezone.utc).timestamp()) + SESSION_MAX_AGE
    payload = f"{user_id}:{username}:{exp}:{session_version}"
    sig = hmac.new(
        session_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(token: str, db: Session) -> Optional[tuple[int, str]]:
    raw = (token or "").strip()
    parts = raw.split(":")
    if len(parts) == 4:
        try:
            user_id = int(parts[0])
        except ValueError:
            return None
        username = parts[1]
        try:
            exp = int(parts[2])
        except ValueError:
            return None
        sig = parts[3]
        payload = f"{user_id}:{username}:{exp}"
        session_version = 0
    elif len(parts) == 5:
        try:
            user_id = int(parts[0])
        except ValueError:
            return None
        username = parts[1]
        try:
            exp = int(parts[2])
            session_version = int(parts[3])
        except ValueError:
            return None
        sig = parts[4]
        payload = f"{user_id}:{username}:{exp}:{session_version}"
    else:
        return None
    expected = hmac.new(
        session_secret().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not secrets.compare_digest(expected, sig):
        return None
    if exp < int(datetime.now(timezone.utc).timestamp()):
        return None
    row = _fetch_user_row(db, user_id)
    if not row or row.get("status") != "active":
        return None
    if _user_session_version(db, user_id) != session_version:
        return None
    return user_id, username


def _fetch_user_row(db: Session, user_id: int) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(
            "SELECT id, username, display_name, status, last_login_at, session_version, "
            "must_change_password, created_at, updated_at FROM sys_user WHERE id = :id"
        ),
        {"id": user_id},
    ).mappings().first()
    return dict(row) if row else None


def _fetch_user_by_username(db: Session, username: str) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(
            "SELECT id, username, display_name, password_hash, password_salt, password_iters, status "
            "FROM sys_user WHERE LOWER(username) = LOWER(:u)"
        ),
        {"u": username.strip()},
    ).mappings().first()
    return dict(row) if row else None


def get_user_roles(db: Session, user_id: int) -> List[str]:
    rows = db.execute(
        text(
            "SELECT r.code FROM sys_role r "
            "JOIN sys_user_role ur ON ur.role_id = r.id WHERE ur.user_id = :uid"
        ),
        {"uid": user_id},
    ).fetchall()
    return [str(r[0]) for r in rows]


def get_user_permissions(db: Session, user_id: int) -> Set[str]:
    roles = get_user_roles(db, user_id)
    if ROLE_SUPER_ADMIN in roles:
        return set(ALL_PERMISSION_CODES)
    rows = db.execute(
        text(
            "SELECT DISTINCT p.code FROM sys_permission p "
            "JOIN sys_role_permission rp ON rp.permission_id = p.id "
            "JOIN sys_user_role ur ON ur.role_id = rp.role_id "
            "WHERE ur.user_id = :uid"
        ),
        {"uid": user_id},
    ).fetchall()
    return {str(r[0]) for r in rows}


def get_user_role_ids(db: Session, user_id: int) -> List[int]:
    rows = db.execute(
        text(
            "SELECT r.id FROM sys_role r "
            "JOIN sys_user_role ur ON ur.role_id = r.id WHERE ur.user_id = :uid ORDER BY r.id"
        ),
        {"uid": user_id},
    ).fetchall()
    return [int(r[0]) for r in rows]


def get_user_dept_ids(db: Session, user_id: int) -> tuple[List[int], Optional[int]]:
    rows = db.execute(
        text(
            "SELECT dept_id, is_primary FROM sys_user_dept WHERE user_id = :uid ORDER BY is_primary DESC, dept_id"
        ),
        {"uid": user_id},
    ).fetchall()
    dept_ids = [int(r[0]) for r in rows]
    primary = None
    for dept_id, is_primary in rows:
        if int(is_primary or 0):
            primary = int(dept_id)
            break
    if primary is None and dept_ids:
        primary = dept_ids[0]
    return dept_ids, primary


def load_user_role_data_scopes(db: Session, user_id: int) -> Dict[tuple[str, str], str]:
    rows = db.execute(
        text(
            "SELECT rds.resource_code, rds.action, rds.scope_type "
            "FROM sys_role_data_scope rds "
            "JOIN sys_user_role ur ON ur.role_id = rds.role_id "
            "WHERE ur.user_id = :uid"
        ),
        {"uid": user_id},
    ).fetchall()
    merged: Dict[tuple[str, str], str] = {}
    for resource_code, action, scope_type in rows:
        key = (str(resource_code), str(action))
        prev = merged.get(key, SCOPE_NONE)
        merged[key] = merge_scope_types(prev, str(scope_type))
    return merged


def build_auth_context(db: Session, user_id: int, username: str) -> AuthContext:
    row = _fetch_user_row(db, user_id)
    if not row or row.get("status") != "active":
        raise ValueError("inactive user")
    roles = get_user_roles(db, user_id)
    role_ids = get_user_role_ids(db, user_id)
    perms = get_user_permissions(db, user_id)
    dept_ids, primary_dept_id = get_user_dept_ids(db, user_id)
    role_data_scopes = load_user_role_data_scopes(db, user_id)
    is_super = ROLE_SUPER_ADMIN in roles
    return AuthContext(
        username=username,
        user_id=user_id,
        display_name=str(row.get("display_name") or username),
        roles=roles,
        role_ids=role_ids,
        permissions=perms,
        dept_ids=dept_ids,
        primary_dept_id=primary_dept_id,
        role_data_scopes=role_data_scopes,
        is_super=is_super,
        must_change_password=bool(int(row.get("must_change_password") or 0)),
    )


def verify_sys_user_password(db: Session, username: str, password: str) -> Optional[AuthContext]:
    row = _fetch_user_by_username(db, username)
    if not row or row.get("status") != "active":
        return None
    iters = int(row.get("password_iters") or pwd.PBKDF2_ITERATIONS)
    if not pwd.verify_password(
        password,
        salt_b64=str(row.get("password_salt") or ""),
        hash_b64=str(row.get("password_hash") or ""),
        iterations=iters,
    ):
        return None
    return build_auth_context(db, int(row["id"]), str(row["username"]))


def user_has_permission(ctx: AuthContext, code: str) -> bool:
    if ctx.is_super:
        return True
    return code in ctx.permissions


def audit_log(
    db: Session,
    *,
    actor: str,
    action: str,
    target_type: str = "",
    target_id: str = "",
    detail: str = "",
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
) -> None:
    db.execute(
        text(
            "INSERT INTO sys_audit_log (actor_username, action, target_type, target_id, detail, "
            "before_json, after_json, created_at) "
            "VALUES (:actor, :action, :tt, :tid, :detail, :before, :after, :at)"
        ),
        {
            "actor": actor,
            "action": action,
            "tt": target_type,
            "tid": target_id,
            "detail": detail,
            "before": json.dumps(before, ensure_ascii=False) if before is not None else "",
            "after": json.dumps(after, ensure_ascii=False) if after is not None else "",
            "at": _utc_now(),
        },
    )


def bump_session_version(db: Session, user_id: int) -> None:
    db.execute(
        text(
            "UPDATE sys_user SET session_version = COALESCE(session_version, 0) + 1, "
            "updated_at = :at WHERE id = :uid"
        ),
        {"at": _utc_now(), "uid": user_id},
    )


def record_login(db: Session, user_id: int) -> None:
    db.execute(
        text("UPDATE sys_user SET last_login_at = :at, updated_at = :at WHERE id = :uid"),
        {"at": _utc_now(), "uid": user_id},
    )


def sync_permission_catalog_rows(db: Session) -> None:
    """Ensure sys_permission has a row for every code in ALL_PERMISSION_CODES (idempotent)."""
    for code in sorted(ALL_PERMISSION_CODES):
        existing = db.execute(
            text("SELECT id FROM sys_permission WHERE code = :c"), {"c": code}
        ).fetchone()
        if not existing:
            db.execute(
                text(
                    "INSERT INTO sys_permission (code, name, module) VALUES (:c, :n, :m)"
                ),
                {"c": code, "n": code, "m": code.split(".")[0]},
            )


def seed_rbac_data(
    db: Session,
    *,
    admin_username: str,
    admin_password: str,
) -> None:
    """Idempotent seed: permissions, roles, admin user."""
    now = _utc_now()
    sync_permission_catalog_rows(db)

    from auth.policy import RESERVED_ROLE_CODES

    role_defs = [
        (ROLE_SUPER_ADMIN, "超级管理员", "拥有全部权限"),
        (ROLE_SALES, "销售", "客户与商机"),
        (ROLE_DELIVERY, "交付", "花名册、管道、手册、交接"),
        (ROLE_VIEWER, "只读", "只读访问"),
        ("RESTRICTED", "无业务权限", "测试/占位：不分配任何权限码"),
    ]
    role_ids: Dict[str, int] = {}
    for code, name, desc in role_defs:
        row = db.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": code}).fetchone()
        is_builtin = 1 if code in RESERVED_ROLE_CODES else 0
        if row:
            role_ids[code] = int(row[0])
            db.execute(
                text("UPDATE sys_role SET is_builtin = :b WHERE id = :id"),
                {"b": is_builtin, "id": role_ids[code]},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO sys_role (code, name, description, is_builtin, created_at) "
                    "VALUES (:c, :n, :d, :b, :at)"
                ),
                {"c": code, "n": name, "d": desc, "b": is_builtin, "at": now},
            )
            rid = db.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": code}).fetchone()
            role_ids[code] = int(rid[0])

    # Builtin roles: only add missing default permissions; do not wipe customized grants.
    for role_code, perms in ROLE_DEFAULT_PERMISSIONS.items():
        if role_code not in role_ids:
            continue
        rid = role_ids[role_code]
        for perm_code in perms:
            prow = db.execute(
                text("SELECT id FROM sys_permission WHERE code = :c"), {"c": perm_code}
            ).fetchone()
            if not prow:
                continue
            db.execute(
                text(
                    "INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id) "
                    "VALUES (:rid, :pid)"
                ),
                {"rid": rid, "pid": int(prow[0])},
            )

    user_row = db.execute(
        text("SELECT id FROM sys_user WHERE username = :u"), {"u": admin_username}
    ).fetchone()
    if user_row:
        uid = int(user_row[0])
    else:
        salt_b64, hash_b64, iters = pwd.hash_password(admin_password)
        db.execute(
            text(
                "INSERT INTO sys_user (username, display_name, password_hash, password_salt, "
                "password_iters, status, created_at, updated_at) "
                "VALUES (:u, :dn, :h, :s, :i, 'active', :at, :at)"
            ),
            {
                "u": admin_username,
                "dn": admin_username,
                "h": hash_b64,
                "s": salt_b64,
                "i": iters,
                "at": now,
            },
        )
        uid = int(
            db.execute(text("SELECT id FROM sys_user WHERE username = :u"), {"u": admin_username})
            .fetchone()[0]
        )

    super_rid = role_ids[ROLE_SUPER_ADMIN]
    db.execute(
        text("INSERT OR IGNORE INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"),
        {"uid": uid, "rid": super_rid},
    )
    seed_departments(db)
    seed_role_data_scopes(db, role_ids)
    backfill_delete_permissions_once(db)
    _ensure_user_dept_defaults(db, uid, [ROLE_SUPER_ADMIN])


def seed_departments(db: Session) -> None:
    now = _utc_now()
    defs = [
        ("ROOT", "公司", None, "ROOT", DEPT_TYPE_GENERAL),
        ("SALES", "销售部", "ROOT", "ROOT/SALES", DEPT_TYPE_BUSINESS),
        ("DELIVERY", "交付部", "ROOT", "ROOT/DELIVERY", DEPT_TYPE_BUSINESS),
        ("FINANCE", "财务部", "ROOT", "ROOT/FINANCE", DEPT_TYPE_FUNCTIONAL),
        ("ADMIN", "管理部", "ROOT", "ROOT/ADMIN", DEPT_TYPE_GENERAL),
        ("OPERATIONS", "经营部", "ROOT", "ROOT/OPERATIONS", DEPT_TYPE_GENERAL),
    ]
    code_to_id: Dict[str, int] = {}
    for code, name, parent_code, path, dept_type in defs:
        row = db.execute(text("SELECT id FROM sys_dept WHERE code = :c"), {"c": code}).fetchone()
        parent_id = code_to_id.get(parent_code) if parent_code else None
        if row:
            code_to_id[code] = int(row[0])
            db.execute(
                text(
                    "UPDATE sys_dept SET name = :n, parent_id = :pid, path = :p, dept_type = :t, updated_at = :at "
                    "WHERE code = :c"
                ),
                {"n": name, "pid": parent_id, "p": path, "t": dept_type, "at": now, "c": code},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO sys_dept (name, code, parent_id, path, dept_type, status, created_at, updated_at) "
                    "VALUES (:n, :c, :pid, :p, :t, 'active', :at, :at)"
                ),
                {"n": name, "c": code, "pid": parent_id, "p": path, "t": dept_type, "at": now},
            )
            rid = db.execute(text("SELECT id FROM sys_dept WHERE code = :c"), {"c": code}).fetchone()
            code_to_id[code] = int(rid[0])


def _scope_rows_for_role(role_code: str) -> Dict[tuple[str, str], str]:
    crm_resources = [c for c in RESOURCE_CODES if c.startswith("crm.")]
    delivery_resources = [c for c in RESOURCE_CODES if c.startswith("delivery.")]
    rows: Dict[tuple[str, str], str] = {}
    if role_code == ROLE_SUPER_ADMIN:
        for resource in RESOURCE_CODES:
            for action in DATA_SCOPE_ACTIONS:
                rows[(resource, action)] = SCOPE_ALL
        return rows
    if role_code == ROLE_SALES:
        for resource in crm_resources:
            for action in ("read", "write", "export"):
                rows[(resource, action)] = SCOPE_ASSIGNED
            rows[(resource, "delete")] = SCOPE_NONE
        return rows
    if role_code == ROLE_DELIVERY:
        for resource in delivery_resources:
            for action in ("read", "write", "export"):
                rows[(resource, action)] = SCOPE_ASSIGNED
            rows[(resource, "delete")] = SCOPE_NONE
        rows[("crm.client", "read")] = SCOPE_ASSIGNED
        for resource in (RESOURCE_RMS_JOB, RESOURCE_RMS_APPLICATION):
            rows[(resource, "read")] = SCOPE_ASSIGNED
            for action in ("write", "export", "delete"):
                rows[(resource, action)] = SCOPE_NONE
        return rows
    if role_code == ROLE_VIEWER:
        for resource in RESOURCE_CODES:
            if resource.startswith("rms."):
                continue
            rows[(resource, "read")] = SCOPE_ASSIGNED
            for action in ("write", "export", "delete"):
                rows[(resource, action)] = SCOPE_NONE
        return rows
    if role_code == "RESTRICTED":
        for resource in RESOURCE_CODES:
            for action in DATA_SCOPE_ACTIONS:
                rows[(resource, action)] = SCOPE_NONE
        return rows
    return rows


def seed_role_data_scopes(db: Session, role_ids: Dict[str, int]) -> None:
    now = _utc_now()
    for role_code, rid in role_ids.items():
        if role_code not in _BUILTIN_ROLE_CODES:
            continue
        defaults = _scope_rows_for_role(role_code)
        if not defaults:
            continue
        for (resource_code, action), scope_type in defaults.items():
            exists = db.execute(
                text(
                    "SELECT 1 FROM sys_role_data_scope "
                    "WHERE role_id = :rid AND resource_code = :rc AND action = :act LIMIT 1"
                ),
                {"rid": rid, "rc": resource_code, "act": action},
            ).fetchone()
            if exists:
                continue
            db.execute(
                text(
                    "INSERT INTO sys_role_data_scope (role_id, resource_code, action, scope_type, created_at, updated_at) "
                    "VALUES (:rid, :rc, :act, :st, :at, :at)"
                ),
                {"rid": rid, "rc": resource_code, "act": action, "st": scope_type, "at": now},
            )


def backfill_delete_permissions_once(db: Session) -> None:
    """One-time compatibility backfill: old write/manage grants also allowed delete."""
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
    )
    exists = db.execute(
        text("SELECT 1 FROM schema_migrations WHERE migration_id = :id"),
        {"id": DELETE_PERMISSION_BACKFILL_ID},
    ).fetchone()
    if exists:
        return

    now = _utc_now()
    sync_permission_catalog_rows(db)
    for source_code, delete_code in DELETE_PERMISSION_COMPAT_PAIRS:
        db.execute(
            text(
                "INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id) "
                "SELECT rp.role_id, p_delete.id "
                "FROM sys_role_permission rp "
                "JOIN sys_permission p_source ON p_source.id = rp.permission_id "
                "JOIN sys_permission p_delete ON p_delete.code = :delete_code "
                "WHERE p_source.code = :source_code"
            ),
            {"source_code": source_code, "delete_code": delete_code},
        )

    for source_code, delete_code in DELETE_PERMISSION_COMPAT_PAIRS:
        resource = PERMISSION_TO_RESOURCE.get(delete_code)
        if not resource:
            continue
        db.execute(
            text(
                "UPDATE sys_role_data_scope "
                "SET scope_type = COALESCE(("
                "    SELECT src.scope_type FROM sys_role_data_scope src "
                "    WHERE src.role_id = sys_role_data_scope.role_id "
                "      AND src.resource_code = :resource "
                "      AND src.action = 'write' "
                "    LIMIT 1"
                "), scope_type), updated_at = :now "
                "WHERE resource_code = :resource AND action = 'delete' "
                "AND role_id IN ("
                "    SELECT rp.role_id "
                "    FROM sys_role_permission rp "
                "    JOIN sys_permission p ON p.id = rp.permission_id "
                "    WHERE p.code = :delete_code"
                ")"
            ),
            {"resource": resource, "delete_code": delete_code, "now": now},
        )
        db.execute(
            text(
                "INSERT INTO sys_role_data_scope "
                "(role_id, resource_code, action, scope_type, created_at, updated_at) "
                "SELECT rp.role_id, :resource, 'delete', src.scope_type, :now, :now "
                "FROM sys_role_permission rp "
                "JOIN sys_permission p ON p.id = rp.permission_id "
                "JOIN sys_role_data_scope src "
                "  ON src.role_id = rp.role_id "
                " AND src.resource_code = :resource "
                " AND src.action = 'write' "
                "WHERE p.code = :delete_code "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM sys_role_data_scope existing "
                "    WHERE existing.role_id = rp.role_id "
                "      AND existing.resource_code = :resource "
                "      AND existing.action = 'delete'"
                ")"
            ),
            {"resource": resource, "delete_code": delete_code, "now": now},
        )

    db.execute(
        text("INSERT INTO schema_migrations (migration_id, applied_at) VALUES (:id, :at)"),
        {"id": DELETE_PERMISSION_BACKFILL_ID, "at": now},
    )


def _ensure_user_dept_defaults(db: Session, user_id: int, role_codes: List[str]) -> None:
    existing = db.execute(
        text("SELECT 1 FROM sys_user_dept WHERE user_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).fetchone()
    if existing:
        return
    dept_code = "ADMIN"
    if ROLE_SALES in role_codes:
        dept_code = "SALES"
    elif ROLE_DELIVERY in role_codes:
        dept_code = "DELIVERY"
    row = db.execute(text("SELECT id FROM sys_dept WHERE code = :c"), {"c": dept_code}).fetchone()
    if not row:
        return
    db.execute(
        text(
            "INSERT OR IGNORE INTO sys_user_dept (user_id, dept_id, is_primary, created_at) "
            "VALUES (:uid, :did, 1, :at)"
        ),
        {"uid": user_id, "did": int(row[0]), "at": _utc_now()},
    )


def resolve_rbac_from_request(
    request,
    db: Session,
    *,
    legacy_verify: Callable[[str, str], bool],
    legacy_effective_username: Callable[[], str],
) -> Optional[AuthContext]:
    import security_foundation as sec

    cookie = request.cookies.get(SESSION_COOKIE_NAME) or ""
    parsed = verify_session_token(cookie, db)
    if parsed:
        user_id, username = parsed
        try:
            return build_auth_context(db, user_id, username)
        except ValueError:
            return None

    creds = sec._parse_basic_auth(request)
    if creds:
        u, p = creds
        ctx = verify_sys_user_password(db, u, p)
        if ctx:
            return ctx
        if legacy_verify(u, p) and u.strip().lower() == legacy_effective_username().lower():
            return AuthContext(
                username=legacy_effective_username(),
                user_id=None,
                display_name=u,
                roles=[ROLE_SUPER_ADMIN],
                permissions=set(ALL_PERMISSION_CODES),
                is_super=True,
            )
    legacy_cookie = request.cookies.get(sec.LEGACY_COOKIE_NAME) or ""
    eff = legacy_effective_username()
    if sec.verify_legacy_session_token(legacy_cookie, effective_username=eff):
        ctx = _fetch_user_by_username(db, eff)
        if ctx and ctx.get("status") == "active":
            return build_auth_context(db, int(ctx["id"]), eff)
        return AuthContext(
            username=eff,
            user_id=None,
            display_name=eff,
            roles=[ROLE_SUPER_ADMIN],
            permissions=set(ALL_PERMISSION_CODES),
            is_super=True,
        )
    return None


def resolve_legacy_from_request(
    request,
    *,
    legacy_verify: Callable[[str, str], bool],
    legacy_effective_username: Callable[[], str],
) -> Optional[AuthContext]:
    import security_foundation as sec

    eff = legacy_effective_username()
    creds = sec._parse_basic_auth(request)
    if creds and legacy_verify(creds[0], creds[1]) and creds[0].strip().lower() == eff.lower():
        return AuthContext(
            username=eff,
            display_name=eff,
            roles=[ROLE_SUPER_ADMIN],
            permissions=set(ALL_PERMISSION_CODES),
            is_super=True,
        )
    cookie = request.cookies.get(sec.LEGACY_COOKIE_NAME) or ""
    if sec.verify_legacy_session_token(cookie, effective_username=eff):
        return AuthContext(
            username=eff,
            display_name=eff,
            roles=[ROLE_SUPER_ADMIN],
            permissions=set(ALL_PERMISSION_CODES),
            is_super=True,
        )
    return None


def list_users(
    db: Session,
    *,
    q: str = "",
    limit: int = 0,
    offset: int = 0,
) -> Dict[str, Any]:
    sql = (
        "SELECT id, username, display_name, status, last_login_at, must_change_password, "
        "created_at, updated_at FROM sys_user WHERE 1=1"
    )
    params: Dict[str, Any] = {}
    needle = (q or "").strip().lower()
    if needle:
        sql += " AND (LOWER(username) LIKE :q OR LOWER(display_name) LIKE :q)"
        params["q"] = f"%{needle}%"
    count_sql = "SELECT COUNT(*) FROM sys_user WHERE 1=1"
    if needle:
        count_sql += " AND (LOWER(username) LIKE :q OR LOWER(display_name) LIKE :q)"
    total = int(db.execute(text(count_sql), params).scalar() or 0)
    sql += " ORDER BY id"
    if limit > 0:
        sql += " LIMIT :lim OFFSET :off"
        params["lim"] = max(1, min(limit, 500))
        params["off"] = max(0, offset)
    rows = db.execute(text(sql), params).mappings().all()
    out = []
    for row in rows:
        d = dict(row)
        uid = int(d["id"])
        d["must_change_password"] = bool(int(d.get("must_change_password") or 0))
        d["roles"] = get_user_roles(db, uid)
        d["role_labels"] = _role_labels_for_codes(db, d["roles"])
        dept_ids, primary_dept_id = get_user_dept_ids(db, uid)
        d["dept_ids"] = dept_ids
        d["primary_dept_id"] = primary_dept_id
        if dept_ids:
            placeholders = ", ".join(f":d{i}" for i in range(len(dept_ids)))
            params = {f"d{i}": did for i, did in enumerate(dept_ids)}
            drows = db.execute(
                text(f"SELECT id, name, code FROM sys_dept WHERE id IN ({placeholders})"),
                params,
            ).fetchall()
            d["depts"] = [{"id": int(r[0]), "name": str(r[1]), "code": str(r[2])} for r in drows]
        else:
            d["depts"] = []
        out.append(d)
    return {"items": out, "total": total, "limit": limit, "offset": offset}


def _role_labels_for_codes(db: Session, codes: List[str]) -> List[str]:
    if not codes:
        return []
    placeholders = ", ".join(f":c{i}" for i in range(len(codes)))
    params = {f"c{i}": c for i, c in enumerate(codes)}
    rows = db.execute(
        text(f"SELECT code, name FROM sys_role WHERE code IN ({placeholders})"),
        params,
    ).fetchall()
    name_map = {str(r[0]): str(r[1]) for r in rows}
    return [name_map.get(c, c) for c in codes]


def _role_permission_codes(db: Session, role_id: int) -> List[str]:
    rows = db.execute(
        text(
            "SELECT p.code FROM sys_permission p "
            "JOIN sys_role_permission rp ON rp.permission_id = p.id "
            "WHERE rp.role_id = :rid ORDER BY p.code"
        ),
        {"rid": role_id},
    ).fetchall()
    return [str(r[0]) for r in rows]


def list_roles(db: Session) -> List[Dict[str, Any]]:
    from auth.policy import RESERVED_ROLE_CODES

    rows = db.execute(
        text(
            "SELECT id, code, name, description, is_builtin, created_at FROM sys_role ORDER BY id"
        )
    ).mappings().all()
    out = []
    for row in rows:
        d = dict(row)
        rid = int(d["id"])
        d["permissions"] = _role_permission_codes(db, rid)
        code = str(d.get("code") or "")
        d["is_builtin"] = bool(int(d.get("is_builtin") or 0)) or code in RESERVED_ROLE_CODES
        cnt = db.execute(
            text("SELECT COUNT(*) FROM sys_user_role WHERE role_id = :rid"),
            {"rid": rid},
        ).fetchone()
        d["user_count"] = int(cnt[0]) if cnt else 0
        out.append(d)
    return out


def list_audit_logs(
    db: Session,
    *,
    actor_username: str = "",
    target_type: str = "",
    action: str = "",
    level: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    where = "WHERE 1=1"
    params: Dict[str, Any] = {}
    if actor_username:
        where += " AND actor_username = :actor"
        params["actor"] = actor_username
    if target_type:
        where += " AND target_type = :tt"
        params["tt"] = target_type
    if action:
        where += " AND action = :act"
        params["act"] = action
    lvl = (level or "").strip().lower()
    if lvl == "high":
        where += " AND (LOWER(action) LIKE '%.delete' OR LOWER(action) LIKE '%.disable')"
    elif lvl == "low":
        where += " AND (LOWER(action) LIKE '%.create' OR LOWER(action) LIKE '%.import')"
    elif lvl == "medium":
        where += (
            " AND LOWER(action) NOT LIKE '%.delete' AND LOWER(action) NOT LIKE '%.disable'"
            " AND LOWER(action) NOT LIKE '%.create' AND LOWER(action) NOT LIKE '%.import'"
        )
    if date_from:
        where += " AND created_at >= :df"
        params["df"] = date_from
    if date_to:
        where += " AND created_at <= :dt"
        params["dt"] = date_to
    lim = max(1, min(limit, 500))
    off = max(0, offset)
    total = int(db.execute(text(f"SELECT COUNT(*) FROM sys_audit_log {where}"), params).scalar() or 0)
    q = (
        "SELECT id, actor_username, action, target_type, target_id, detail, before_json, after_json, created_at "
        f"FROM sys_audit_log {where} ORDER BY id DESC LIMIT :lim OFFSET :off"
    )
    params = dict(params)
    params["lim"] = lim
    params["off"] = off
    rows = db.execute(text(q), params).mappings().all()
    out = []
    for row in rows:
        d = dict(row)
        for key in ("before_json", "after_json"):
            raw = d.get(key) or ""
            if raw:
                try:
                    d[key.replace("_json", "")] = json.loads(raw)
                except json.JSONDecodeError:
                    d[key.replace("_json", "")] = raw
            else:
                d[key.replace("_json", "")] = None
        out.append(d)
    return {"items": out, "total": total, "limit": lim, "offset": off}


def list_audit_filter_options(db: Session) -> Dict[str, List[str]]:
    actors = db.execute(
        text("SELECT DISTINCT actor_username FROM sys_audit_log ORDER BY actor_username")
    ).scalars().all()
    actions = db.execute(
        text("SELECT DISTINCT action FROM sys_audit_log ORDER BY action")
    ).scalars().all()
    return {
        "actors": [str(a) for a in actors if a],
        "actions": [str(a) for a in actions if a],
    }


def create_user(
    db: Session,
    *,
    username: str,
    password: str,
    display_name: str,
    role_codes: List[str],
    dept_ids: Optional[List[int]] = None,
    primary_dept_id: Optional[int] = None,
    actor: str,
    actor_ctx: AuthContext,
) -> Dict[str, Any]:
    from auth import policy

    if _fetch_user_by_username(db, username):
        raise ValueError("用户名已存在")
    policy.assert_user_roles_change(db, user_id=0, new_role_codes=role_codes, actor=actor_ctx)
    now = _utc_now()
    salt_b64, hash_b64, iters = pwd.hash_password(password)
    db.execute(
        text(
            "INSERT INTO sys_user (username, display_name, password_hash, password_salt, "
            "password_iters, status, session_version, created_at, updated_at) "
            "VALUES (:u, :dn, :h, :s, :i, 'active', 0, :at, :at)"
        ),
        {
            "u": username,
            "dn": display_name or username,
            "h": hash_b64,
            "s": salt_b64,
            "i": iters,
            "at": now,
        },
    )
    row = _fetch_user_by_username(db, username)
    if not row:
        raise ValueError("用户创建失败")
    uid = int(row["id"])
    _set_user_roles(db, uid, role_codes)
    if dept_ids:
        set_user_departments(
            db,
            uid,
            dept_ids,
            primary_dept_id=primary_dept_id,
            actor=actor,
        )
    else:
        _ensure_user_dept_defaults(db, uid, role_codes)
    assigned = get_user_roles(db, uid)
    if role_codes and not assigned:
        raise ValueError("角色无效，请从列表中选择")
    audit_log(
        db,
        actor=actor,
        action="user.create",
        target_type="user",
        target_id=str(uid),
        detail=username,
        after={"username": username, "roles": assigned},
    )
    return {"id": uid, "username": username}


def update_user_profile(
    db: Session,
    user_id: int,
    *,
    display_name: str,
    actor: str,
) -> None:
    row = _fetch_user_row(db, user_id)
    if not row:
        raise ValueError("用户不存在")
    before = {"display_name": row.get("display_name")}
    now = _utc_now()
    db.execute(
        text("UPDATE sys_user SET display_name = :dn, updated_at = :at WHERE id = :uid"),
        {"dn": display_name, "at": now, "uid": user_id},
    )
    audit_log(
        db,
        actor=actor,
        action="user.update",
        target_type="user",
        target_id=str(user_id),
        detail=str(row.get("username")),
        before=before,
        after={"display_name": display_name},
    )


def set_user_status(db: Session, user_id: int, status: str, *, actor: str, actor_ctx: AuthContext) -> None:
    from auth import policy

    if status not in ("active", "disabled"):
        raise ValueError("无效状态")
    row = _fetch_user_row(db, user_id)
    if not row:
        raise ValueError("用户不存在")
    policy.assert_user_status_change(db, user_id=user_id, new_status=status, actor=actor_ctx)
    before = {"status": row.get("status")}
    now = _utc_now()
    db.execute(
        text("UPDATE sys_user SET status = :st, updated_at = :at WHERE id = :uid"),
        {"st": status, "at": now, "uid": user_id},
    )
    if status != "active":
        bump_session_version(db, user_id)
    audit_log(
        db,
        actor=actor,
        action="user.disable" if status == "disabled" else "user.enable",
        target_type="user",
        target_id=str(user_id),
        detail=str(row.get("username")),
        before=before,
        after={"status": status},
    )


def update_user_roles(
    db: Session,
    user_id: int,
    role_codes: List[str],
    *,
    actor: str,
    actor_ctx: AuthContext,
) -> None:
    from auth import policy

    row = _fetch_user_row(db, user_id)
    if not row:
        raise ValueError("用户不存在")
    before_roles = get_user_roles(db, user_id)
    policy.assert_user_roles_change(db, user_id=user_id, new_role_codes=role_codes, actor=actor_ctx)
    _set_user_roles(db, user_id, role_codes)
    after_roles = get_user_roles(db, user_id)
    audit_log(
        db,
        actor=actor,
        action="user.roles",
        target_type="user",
        target_id=str(user_id),
        detail=str(row.get("username")),
        before={"roles": before_roles},
        after={"roles": after_roles},
    )


def reset_user_password(
    db: Session,
    user_id: int,
    password: str,
    *,
    actor: str,
    must_change_password: bool = False,
) -> None:
    row = _fetch_user_row(db, user_id)
    if not row:
        raise ValueError("用户不存在")
    salt_b64, hash_b64, iters = pwd.hash_password(password)
    now = _utc_now()
    db.execute(
        text(
            "UPDATE sys_user SET password_hash = :h, password_salt = :s, "
            "password_iters = :i, must_change_password = :mcp, updated_at = :at WHERE id = :uid"
        ),
        {
            "h": hash_b64,
            "s": salt_b64,
            "i": iters,
            "mcp": 1 if must_change_password else 0,
            "at": now,
            "uid": user_id,
        },
    )
    bump_session_version(db, user_id)
    audit_log(
        db,
        actor=actor,
        action="user.password_reset",
        target_type="user",
        target_id=str(user_id),
        detail=str(row.get("username") or user_id),
        before={},
        after={"password_reset": True, "must_change_password": must_change_password},
    )


def clear_must_change_password(db: Session, user_id: int) -> None:
    db.execute(
        text("UPDATE sys_user SET must_change_password = 0, updated_at = :at WHERE id = :uid"),
        {"at": _utc_now(), "uid": user_id},
    )


def change_own_password(
    db: Session,
    user_id: int,
    *,
    current_password: str,
    new_password: str,
) -> None:
    row = db.execute(
        text(
            "SELECT username, password_hash, password_salt, password_iters, status "
            "FROM sys_user WHERE id = :id"
        ),
        {"id": user_id},
    ).mappings().first()
    if not row or row.get("status") != "active":
        raise ValueError("用户不存在或已禁用")
    iters = int(row.get("password_iters") or pwd.PBKDF2_ITERATIONS)
    if not pwd.verify_password(
        current_password,
        salt_b64=str(row.get("password_salt") or ""),
        hash_b64=str(row.get("password_hash") or ""),
        iterations=iters,
    ):
        raise ValueError("当前密码不正确")
    salt_b64, hash_b64, iters = pwd.hash_password(new_password)
    now = _utc_now()
    db.execute(
        text(
            "UPDATE sys_user SET password_hash = :h, password_salt = :s, password_iters = :i, "
            "must_change_password = 0, updated_at = :at WHERE id = :uid"
        ),
        {"h": hash_b64, "s": salt_b64, "i": iters, "at": now, "uid": user_id},
    )
    bump_session_version(db, user_id)


def batch_update_user_roles(
    db: Session,
    user_ids: List[int],
    role_codes: List[str],
    *,
    mode: str,
    actor: str,
    actor_ctx: AuthContext,
) -> Dict[str, Any]:
    if not user_ids:
        raise ValueError("请选择至少一个用户")
    if not role_codes:
        raise ValueError("请选择至少一个角色")
    if mode not in ("replace", "add"):
        raise ValueError("无效批量模式")
    updated = 0
    for uid in user_ids:
        if mode == "add":
            merged = list(dict.fromkeys(get_user_roles(db, uid) + role_codes))
            update_user_roles(db, uid, merged, actor=actor, actor_ctx=actor_ctx)
        else:
            update_user_roles(db, uid, role_codes, actor=actor, actor_ctx=actor_ctx)
        updated += 1
    audit_log(
        db,
        actor=actor,
        action="user.roles.batch",
        target_type="user",
        target_id=",".join(str(i) for i in user_ids),
        detail=f"mode={mode}",
        after={"role_codes": role_codes, "count": updated},
    )
    return {"updated": updated}


def import_users_csv(
    db: Session,
    rows: List[Dict[str, str]],
    *,
    actor: str,
    actor_ctx: AuthContext,
) -> Dict[str, Any]:
    created = 0
    skipped = 0
    errors: List[str] = []
    for i, row in enumerate(rows, start=2):
        username = (row.get("username") or "").strip()
        password = (row.get("password") or "").strip()
        display_name = (row.get("display_name") or "").strip()
        roles_raw = (row.get("role_codes") or row.get("roles") or "").strip()
        if not username and not password and not roles_raw:
            continue
        if not username or not password:
            errors.append(f"第{i}行: 缺少用户名或密码")
            skipped += 1
            continue
        role_codes = [c.strip() for c in roles_raw.replace(";", ",").split(",") if c.strip()]
        if not role_codes:
            role_codes = ["VIEWER"]
        if _fetch_user_by_username(db, username):
            skipped += 1
            continue
        try:
            create_user(
                db,
                username=username,
                password=password,
                display_name=display_name,
                role_codes=role_codes,
                actor=actor,
                actor_ctx=actor_ctx,
            )
            created += 1
        except Exception as e:
            errors.append(f"第{i}行 {username}: {e}")
            skipped += 1
    audit_log(
        db,
        actor=actor,
        action="user.import",
        target_type="user",
        target_id="csv",
        detail=f"created={created} skipped={skipped}",
        after={"created": created, "skipped": skipped, "errors": errors[:20]},
    )
    return {"created": created, "skipped": skipped, "errors": errors}


def create_custom_role(db: Session, *, name: str, description: str, actor: str) -> Dict[str, Any]:
    from auth import policy

    label = policy.validate_custom_role_name(name)
    code = policy.generate_custom_role_code()
    now = _utc_now()
    db.execute(
        text(
            "INSERT INTO sys_role (code, name, description, is_builtin, created_at) "
            "VALUES (:c, :n, :d, 0, :at)"
        ),
        {"c": code, "n": label, "d": (description or "").strip(), "at": now},
    )
    row = db.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": code}).fetchone()
    rid = int(row[0])
    audit_log(
        db,
        actor=actor,
        action="role.create",
        target_type="role",
        target_id=str(rid),
        detail=code,
        after={"code": code, "name": label},
    )
    return {"id": rid, "code": code, "name": label}


def delete_role(db: Session, role_id: int, *, actor: str) -> None:
    from auth.policy import RESERVED_ROLE_CODES

    role = db.execute(
        text("SELECT id, code, name, is_builtin FROM sys_role WHERE id = :id"),
        {"id": role_id},
    ).mappings().first()
    if not role:
        raise ValueError("角色不存在")
    code = str(role["code"])
    if int(role.get("is_builtin") or 0) or code in RESERVED_ROLE_CODES:
        raise ValueError("内置角色不可删除")
    cnt = db.execute(
        text("SELECT COUNT(*) FROM sys_user_role WHERE role_id = :rid"),
        {"rid": role_id},
    ).scalar()
    if int(cnt or 0) > 0:
        raise ValueError(f"仍有 {int(cnt)} 个用户使用该角色，无法删除")
    db.execute(text("DELETE FROM sys_role_data_scope WHERE role_id = :rid"), {"rid": role_id})
    db.execute(text("DELETE FROM sys_role_permission WHERE role_id = :rid"), {"rid": role_id})
    db.execute(text("DELETE FROM sys_role WHERE id = :rid"), {"rid": role_id})
    audit_log(
        db,
        actor=actor,
        action="role.delete",
        target_type="role",
        target_id=str(role_id),
        detail=code,
        before={"name": role.get("name"), "code": code},
    )


def update_role_meta(
    db: Session,
    role_id: int,
    *,
    name: str,
    description: str,
    actor: str,
) -> None:
    role = db.execute(
        text("SELECT id, code, name, description, is_builtin FROM sys_role WHERE id = :id"),
        {"id": role_id},
    ).mappings().first()
    if not role:
        raise ValueError("角色不存在")
    before = dict(role)
    db.execute(
        text("UPDATE sys_role SET name = :n, description = :d WHERE id = :id"),
        {"n": name.strip(), "d": (description or "").strip(), "id": role_id},
    )
    audit_log(
        db,
        actor=actor,
        action="role.update",
        target_type="role",
        target_id=str(role_id),
        detail=str(before.get("code")),
        before={"name": before.get("name"), "description": before.get("description")},
        after={"name": name, "description": description},
    )


def _set_user_roles(db: Session, user_id: int, role_codes: List[str]) -> None:
    db.execute(text("DELETE FROM sys_user_role WHERE user_id = :uid"), {"uid": user_id})
    for code in role_codes:
        row = db.execute(text("SELECT id FROM sys_role WHERE code = :c"), {"c": code}).fetchone()
        if row:
            db.execute(
                text("INSERT OR IGNORE INTO sys_user_role (user_id, role_id) VALUES (:uid, :rid)"),
                {"uid": user_id, "rid": int(row[0])},
            )


def set_role_permissions(
    db: Session,
    role_id: int,
    permission_codes: List[str],
    *,
    actor: str,
    actor_ctx: AuthContext,
) -> None:
    from auth import policy

    role = policy.assert_can_edit_role_permissions(actor_ctx, db, role_id)
    sync_permission_catalog_rows(db)
    before_perms = _role_permission_codes(db, role_id)
    db.execute(text("DELETE FROM sys_role_permission WHERE role_id = :rid"), {"rid": role_id})
    skipped: List[str] = []
    for code in permission_codes:
        row = db.execute(text("SELECT id FROM sys_permission WHERE code = :c"), {"c": code}).fetchone()
        if row:
            db.execute(
                text(
                    "INSERT OR IGNORE INTO sys_role_permission (role_id, permission_id) "
                    "VALUES (:rid, :pid)"
                ),
                {"rid": role_id, "pid": int(row[0])},
            )
        else:
            skipped.append(code)
    if skipped:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"权限码未入库，无法保存: {', '.join(sorted(skipped))}",
        )
    after_perms = _role_permission_codes(db, role_id)
    audit_log(
        db,
        actor=actor,
        action="role.permissions",
        target_type="role",
        target_id=str(role_id),
        detail=str(role.get("code")),
        before={"permissions": before_perms},
        after={"permissions": after_perms},
    )
    return after_perms


def list_departments(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT id, name, code, parent_id, path, dept_type, status, head_user_id "
            "FROM sys_dept ORDER BY path"
        )
    ).mappings().all()
    depts = [dict(r) for r in rows]
    head_ids = sorted({int(d["head_user_id"]) for d in depts if d.get("head_user_id")})
    head_map: Dict[int, Dict[str, Any]] = {}
    if head_ids:
        placeholders = ", ".join(f":h{i}" for i in range(len(head_ids)))
        params = {f"h{i}": hid for i, hid in enumerate(head_ids)}
        hrows = db.execute(
            text(
                f"SELECT id, username, display_name FROM sys_user WHERE id IN ({placeholders})"
            ),
            params,
        ).mappings().all()
        for row in hrows:
            head_map[int(row["id"])] = {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "display_name": str(row["display_name"] or row["username"]),
            }
    user_rows = db.execute(
        text(
            "SELECT ud.dept_id, u.id, u.username, u.display_name "
            "FROM sys_user_dept ud "
            "JOIN sys_user u ON u.id = ud.user_id "
            "ORDER BY ud.dept_id, COALESCE(u.display_name, u.username), u.username"
        )
    ).mappings().all()
    users_by_dept: Dict[int, List[Dict[str, Any]]] = {}
    for row in user_rows:
        dept_id = int(row["dept_id"])
        users_by_dept.setdefault(dept_id, []).append(
            {
                "id": int(row["id"]),
                "username": str(row["username"]),
                "display_name": str(row["display_name"] or row["username"]),
            }
        )
    for dept in depts:
        bound = users_by_dept.get(int(dept["id"]), [])
        dept["user_count"] = len(bound)
        dept["bound_users"] = bound
        hid = dept.get("head_user_id")
        dept["head_user"] = head_map.get(int(hid)) if hid else None
    return depts


BUILTIN_DEPT_CODES = frozenset({"ROOT", "SALES", "DELIVERY", "FINANCE", "ADMIN", "OPERATIONS"})

OPS_DEPT_NAME = "经营部"
OPS_DEPT_CODES = ("OPERATIONS", "OPS", "OPERATING")


def get_operations_dept_head(db: Session) -> Dict[str, Any]:
    """经营部负责人（交接审批人）。"""
    row = db.execute(
        text(
            "SELECT d.head_user_id, u.username, u.display_name "
            "FROM sys_dept d "
            "LEFT JOIN sys_user u ON u.id = d.head_user_id AND u.status = 'active' "
            "WHERE d.status = 'active' AND (d.name = :name OR d.code IN ('OPERATIONS', 'OPS', 'OPERATING')) "
            "ORDER BY CASE WHEN d.name = :name THEN 0 ELSE 1 END, d.id "
            "LIMIT 1"
        ),
        {"name": OPS_DEPT_NAME},
    ).mappings().first()
    if not row or not row["head_user_id"] or not row["username"]:
        return {"user_id": None, "username": "", "display_name": ""}
    return {
        "user_id": int(row["head_user_id"]),
        "username": str(row["username"]),
        "display_name": str(row["display_name"] or row["username"]),
    }


def is_operations_dept_head(db: Session, user_id: Optional[int]) -> bool:
    if not user_id:
        return False
    head = get_operations_dept_head(db)
    return head["user_id"] is not None and int(head["user_id"]) == int(user_id)


def _dept_reference_reason(db: Session, dept_id: int) -> Optional[str]:
    if db.execute(
        text("SELECT 1 FROM sys_dept WHERE parent_id = :id LIMIT 1"), {"id": dept_id}
    ).fetchone():
        return "存在子部门"
    if db.execute(
        text("SELECT 1 FROM sys_user_dept WHERE dept_id = :id LIMIT 1"), {"id": dept_id}
    ).fetchone():
        return "仍有用户归属该部门"
    if db.execute(
        text(
            "SELECT 1 FROM clients WHERE owner_dept_id = :id OR delivery_dept_id = :id "
            "OR recruitment_dept_id = :id LIMIT 1"
        ),
        {"id": dept_id},
    ).fetchone():
        return "仍有客户归属该部门"
    return None


def create_department(
    db: Session,
    *,
    name: str,
    code: str,
    parent_id: Optional[int],
    dept_type: str,
    head_user_id: Optional[int] = None,
    actor: str,
) -> Dict[str, Any]:
    name = (name or "").strip()
    code = (code or "").strip().upper()
    if not name:
        raise ValueError("部门名称不能为空")
    if not re.fullmatch(r"[A-Z0-9_]+", code):
        raise ValueError("部门编码只能包含大写字母、数字、下划线")
    if db.execute(text("SELECT 1 FROM sys_dept WHERE code = :c"), {"c": code}).fetchone():
        raise ValueError("部门编码已存在")
    parent_path = ""
    pid: Optional[int] = None
    if parent_id:
        prow = db.execute(
            text("SELECT id, path FROM sys_dept WHERE id = :id"), {"id": parent_id}
        ).fetchone()
        if not prow:
            raise ValueError("上级部门不存在")
        pid = int(prow[0])
        parent_path = str(prow[1] or "")
    path = f"{parent_path}/{code}" if parent_path else code
    dtype = normalize_dept_type(dept_type)
    hid: Optional[int] = None
    if head_user_id is not None:
        urow = db.execute(
            text("SELECT id FROM sys_user WHERE id = :id AND status = 'active'"),
            {"id": head_user_id},
        ).fetchone()
        if not urow:
            raise ValueError("部门主管用户不存在或已禁用")
        hid = int(urow[0])
    now = _utc_now()
    db.execute(
        text(
            "INSERT INTO sys_dept (name, code, parent_id, path, dept_type, status, head_user_id, created_at, updated_at) "
            "VALUES (:n, :c, :pid, :p, :t, 'active', :hid, :at, :at)"
        ),
        {"n": name, "c": code, "pid": pid, "p": path, "t": dtype, "hid": hid, "at": now},
    )
    did = int(db.execute(text("SELECT id FROM sys_dept WHERE code = :c"), {"c": code}).fetchone()[0])
    audit_log(
        db,
        actor=actor,
        action="dept.create",
        target_type="dept",
        target_id=str(did),
        detail=code,
        after={"name": name, "code": code, "parent_id": pid, "path": path, "dept_type": dtype, "head_user_id": hid},
    )
    return {"id": did, "code": code, "name": name, "path": path}


def update_department(
    db: Session,
    dept_id: int,
    *,
    name: str,
    dept_type: str,
    status: str,
    head_user_id: Optional[int] = None,
    actor: str,
) -> None:
    row = db.execute(
        text("SELECT id, code, name, dept_type, status, head_user_id FROM sys_dept WHERE id = :id"),
        {"id": dept_id},
    ).mappings().first()
    if not row:
        raise ValueError("部门不存在")
    name = (name or "").strip()
    if not name:
        raise ValueError("部门名称不能为空")
    dtype = normalize_dept_type(dept_type or row["dept_type"] or DEPT_TYPE_GENERAL)
    st = (status or row["status"] or "active").strip()
    if st not in ("active", "disabled"):
        raise ValueError("无效状态")
    hid: Optional[int] = None
    if head_user_id is not None:
        urow = db.execute(
            text("SELECT id FROM sys_user WHERE id = :id AND status = 'active'"),
            {"id": head_user_id},
        ).fetchone()
        if not urow:
            raise ValueError("部门主管用户不存在或已禁用")
        hid = int(urow[0])
    before = {
        "name": row["name"],
        "dept_type": row["dept_type"],
        "status": row["status"],
        "head_user_id": row.get("head_user_id"),
    }
    db.execute(
        text(
            "UPDATE sys_dept SET name = :n, dept_type = :t, status = :s, head_user_id = :hid, updated_at = :at "
            "WHERE id = :id"
        ),
        {"n": name, "t": dtype, "s": st, "hid": hid, "at": _utc_now(), "id": dept_id},
    )
    audit_log(
        db,
        actor=actor,
        action="dept.update",
        target_type="dept",
        target_id=str(dept_id),
        detail=str(row["code"]),
        before=before,
        after={"name": name, "dept_type": dtype, "status": st, "head_user_id": hid},
    )


def delete_department(db: Session, dept_id: int, *, actor: str) -> None:
    row = db.execute(
        text("SELECT id, code, name FROM sys_dept WHERE id = :id"), {"id": dept_id}
    ).mappings().first()
    if not row:
        raise ValueError("部门不存在")
    if str(row["code"]) in BUILTIN_DEPT_CODES:
        raise ValueError("系统内置部门不可删除")
    reason = _dept_reference_reason(db, dept_id)
    if reason:
        raise ValueError(f"无法删除：{reason}")
    db.execute(text("DELETE FROM sys_dept WHERE id = :id"), {"id": dept_id})
    audit_log(
        db,
        actor=actor,
        action="dept.delete",
        target_type="dept",
        target_id=str(dept_id),
        detail=str(row["code"]),
        before={"name": row["name"], "code": row["code"]},
    )


def set_user_departments(
    db: Session,
    user_id: int,
    dept_ids: List[int],
    *,
    primary_dept_id: Optional[int] = None,
    actor: str,
) -> None:
    row = _fetch_user_row(db, user_id)
    if not row:
        raise ValueError("用户不存在")
    if not dept_ids:
        raise ValueError("至少选择一个部门")
    if not dept_ids:
        valid = 0
    else:
        placeholders = ", ".join(f":vd{i}" for i in range(len(dept_ids)))
        params = {f"vd{i}": int(d) for i, d in enumerate(dept_ids)}
        valid = db.execute(
            text(f"SELECT COUNT(*) FROM sys_dept WHERE id IN ({placeholders})"),
            params,
        ).scalar()
    if int(valid or 0) != len(dept_ids):
        raise ValueError("部门无效")
    primary = primary_dept_id if primary_dept_id in dept_ids else dept_ids[0]
    db.execute(text("DELETE FROM sys_user_dept WHERE user_id = :uid"), {"uid": user_id})
    now = _utc_now()
    for did in dept_ids:
        db.execute(
            text(
                "INSERT INTO sys_user_dept (user_id, dept_id, is_primary, created_at) "
                "VALUES (:uid, :did, :pri, :at)"
            ),
            {"uid": user_id, "did": int(did), "pri": 1 if int(did) == int(primary) else 0, "at": now},
        )
    audit_log(
        db,
        actor=actor,
        action="user.depts",
        target_type="user",
        target_id=str(user_id),
        detail=str(row.get("username")),
        after={"dept_ids": dept_ids, "primary_dept_id": primary},
    )


def get_role_data_scopes(db: Session, role_id: int) -> List[Dict[str, Any]]:
    rows = db.execute(
        text(
            "SELECT resource_code, action, scope_type FROM sys_role_data_scope "
            "WHERE role_id = :rid ORDER BY resource_code, action"
        ),
        {"rid": role_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def set_role_data_scopes(
    db: Session,
    role_id: int,
    scopes: List[Dict[str, str]],
    *,
    actor: str,
    actor_ctx: AuthContext,
) -> None:
    from auth import policy
    from auth.data_scope_catalog import SCOPE_TYPES

    role = policy.assert_can_edit_role_permissions(actor_ctx, db, role_id)
    if str(role.get("code")) == ROLE_SUPER_ADMIN:
        raise ValueError("超级管理员数据范围为全部，不可修改")
    valid_types = set(SCOPE_TYPES)
    now = _utc_now()
    before = get_role_data_scopes(db, role_id)
    db.execute(text("DELETE FROM sys_role_data_scope WHERE role_id = :rid"), {"rid": role_id})
    for item in scopes:
        rc = str(item.get("resource_code") or "").strip()
        act = str(item.get("action") or "").strip()
        st = str(item.get("scope_type") or "").strip()
        if rc not in RESOURCE_CODES or act not in DATA_SCOPE_ACTIONS or st not in valid_types:
            raise ValueError(f"无效数据范围配置: {item}")
        db.execute(
            text(
                "INSERT INTO sys_role_data_scope (role_id, resource_code, action, scope_type, created_at, updated_at) "
                "VALUES (:rid, :rc, :act, :st, :at, :at)"
            ),
            {"rid": role_id, "rc": rc, "act": act, "st": st, "at": now},
        )
    after = get_role_data_scopes(db, role_id)
    audit_log(
        db,
        actor=actor,
        action="role.data_scopes",
        target_type="role",
        target_id=str(role_id),
        detail=str(role.get("code")),
        before={"data_scopes": before},
        after={"data_scopes": after},
    )


def build_data_scope_matrix(role_scopes: Optional[List[Dict[str, Any]]] = None) -> dict:
    from auth.data_scope_catalog import SCOPE_TYPES

    scope_labels = {
        "none": "无",
        "self": "仅本人",
        "assigned": "分配给我",
        "dept": "本部门",
        "dept_and_child": "本部门及下级",
        "all": "全部",
        "shared": "共享",
    }
    granted = {
        (str(x["resource_code"]), str(x["action"])): str(x["scope_type"])
        for x in (role_scopes or [])
    }
    resource_labels = {
        "crm.client": "客户",
        "crm.opportunity": "商机",
        "crm.contact": "联系人",
        "crm.visit": "客户拜访",
        "delivery.roster": "花名册",
        "delivery.pipeline": "交付管道",
        "delivery.interviews": "访谈记录",
        "delivery.handbook": "交付手册",
        "delivery.employee_files": "员工文件",
        "delivery.handoff": "项目交接",
        "delivery.settlement": "结算台账",
        "rms.job": "招聘岗位",
        "rms.application": "推荐记录",
        "rms.candidate": "候选人",
        "rms.resume": "简历",
        "file": "文件",
    }
    action_labels = {"read": "查看", "write": "编辑", "export": "导出", "delete": "删除"}
    rows = []
    for resource in RESOURCE_CODES:
        cells = {}
        for action in DATA_SCOPE_ACTIONS:
            cells[action] = granted.get((resource, action), SCOPE_NONE)
        rows.append({
            "resource_code": resource,
            "label": resource_labels.get(resource, resource),
            "cells": cells,
        })
    return {
        "scope_types": [{"code": c, "label": scope_labels.get(c, c)} for c in SCOPE_TYPES if c != "shared"],
        "actions": [{"code": a, "label": action_labels[a]} for a in DATA_SCOPE_ACTIONS],
        "rows": rows,
    }


def user_permission_preview(db: Session, user_id: int) -> Dict[str, Any]:
    row = _fetch_user_row(db, user_id)
    if not row:
        raise ValueError("用户不存在")
    ctx = build_auth_context(db, user_id, str(row["username"]))
    from auth.data_scope import get_effective_data_scope

    data_scopes = []
    for resource in RESOURCE_CODES:
        for action in DATA_SCOPE_ACTIONS:
            perm_codes = [
                p for p in ctx.permissions if permission_to_resource(p) == resource
            ]
            if action == "read" and not any(p.endswith(".read") for p in perm_codes):
                if not any(
                    p.startswith(resource.split(".")[0]) for p in ctx.permissions
                ):
                    continue
            scope = get_effective_data_scope(ctx, resource, action)
            data_scopes.append({
                "resource_code": resource,
                "action": action,
                "scope_type": scope,
            })
    dept_ids, primary_dept_id = get_user_dept_ids(db, user_id)
    return {
        "user": {
            "id": user_id,
            "username": ctx.username,
            "display_name": ctx.display_name,
        },
        "roles": ctx.roles,
        "permissions": sorted(ctx.permissions),
        "dept_ids": dept_ids,
        "primary_dept_id": primary_dept_id,
        "data_scopes": data_scopes,
    }


def bootstrap_after_migrate(
    engine: Engine,
    *,
    admin_username: str,
    admin_password: str,
) -> None:
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        seed_rbac_data(db, admin_username=admin_username, admin_password=admin_password)
        seed_departments(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
