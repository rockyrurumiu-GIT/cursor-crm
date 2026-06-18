"""RMS data scope and visibility helpers (Phase 2)."""
from __future__ import annotations

from typing import Any, Optional, Set, Type

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from auth import data_scope as ds
from auth.data_scope_catalog import (
    CLIENT_DELIVERY_DEPT_COL,
    CLIENT_DELIVERY_OWNER_COL,
    CLIENT_RECRUITMENT_DEPT_COL,
    CLIENT_RECRUITMENT_OWNER_COL,
    RESOURCE_CRM_CLIENT,
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_CANDIDATE,
    RESOURCE_RMS_JOB,
)
from auth.service import AuthContext
from auth.permissions import ROLE_DELIVERY


def scoped_jobs_query(
    db: Session,
    ctx: AuthContext,
    RmsJob: Type[Any],
    Client: Type[Any],
    *,
    action: str = "read",
) -> Query:
    q = db.query(RmsJob)
    allowed = ds.scoped_client_ids(db, ctx, RESOURCE_RMS_JOB, action, Client)
    if allowed is None:
        return q
    if not allowed:
        if ctx.user_id is None:
            return q.filter(RmsJob.id == -1)
        return q.filter(or_(RmsJob.owner_user_id == ctx.user_id, RmsJob.id == -1))
    if ctx.user_id is None:
        return q.filter(RmsJob.client_id.in_(allowed))
    return q.filter(or_(RmsJob.client_id.in_(allowed), RmsJob.owner_user_id == ctx.user_id))


def scoped_applications_query(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    action: str = "read",
    include_recommended_by_for_read: bool = True,
) -> Query:
    q = db.query(RmsApplication)
    if (
        action != "read"
        or ctx.user_id is None
        or not include_recommended_by_for_read
    ):
        return ds.filter_query_by_client_scope(
            q, db, ctx, RESOURCE_RMS_APPLICATION, action, RmsApplication.client_id, Client
        )
    allowed = ds.scoped_client_ids(db, ctx, RESOURCE_RMS_APPLICATION, action, Client)
    if allowed is None:
        return q
    if not allowed:
        return q.filter(RmsApplication.recommended_by == ctx.user_id)
    return q.filter(
        or_(
            RmsApplication.client_id.in_(allowed),
            RmsApplication.recommended_by == ctx.user_id,
        )
    )


def apply_candidate_scope_query(
    query: Query,
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    *,
    action: str,
) -> Query:
    scope = ds.get_effective_data_scope(ctx, RESOURCE_RMS_CANDIDATE, action)

    if ctx.is_super or scope == ds.SCOPE_ALL:
        return query

    if scope == ds.SCOPE_NONE or ctx.user_id is None:
        return query.filter(RmsCandidate.id == -1)

    if scope in (ds.SCOPE_SELF, ds.SCOPE_ASSIGNED):
        return query.filter(RmsCandidate.created_by_user_id == ctx.user_id)

    if scope in (ds.SCOPE_DEPT, ds.SCOPE_DEPT_AND_CHILD):
        return query.filter(RmsCandidate.id == -1)

    return query.filter(RmsCandidate.id == -1)


def _recruitment_client_job_writable(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    Client: Type[Any],
) -> bool:
    """True when user is the client's recruitment owner or in its recruitment dept subtree."""
    if ctx.is_super:
        return True
    if ctx.user_id is None:
        return False
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        return False
    rec_owner_col = getattr(Client, CLIENT_RECRUITMENT_OWNER_COL, None)
    rec_dept_col = getattr(Client, CLIENT_RECRUITMENT_DEPT_COL, None)
    if rec_owner_col is not None:
        rec_owner = getattr(client, CLIENT_RECRUITMENT_OWNER_COL, None)
        if rec_owner is not None and int(rec_owner) == ctx.user_id:
            return True
    if rec_dept_col is None:
        return False
    rec_dept = getattr(client, CLIENT_RECRUITMENT_DEPT_COL, None)
    if rec_dept is None:
        return False
    subtree = ds._dept_subtree_ids(db, [int(rec_dept)])
    user_depts = ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])
    return any(int(d) in subtree for d in user_depts)


def _crm_client_id_visible(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    Client: Type[Any],
    action: str,
) -> bool:
    if ctx.is_super:
        return True
    allowed = ds.scoped_client_ids(db, ctx, RESOURCE_CRM_CLIENT, action, Client)
    if allowed is None:
        return True
    return client_id in allowed


def assert_crm_client_visible_for_trial(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    Client: Type[Any],
) -> None:
    """Trial path: CRM client visibility or recruitment dept / owner on the client."""
    if ctx.is_super:
        return
    if _recruitment_client_job_writable(db, ctx, client_id, Client):
        return
    if _crm_client_id_visible(db, ctx, client_id, Client, "read"):
        return
    if _crm_client_id_visible(db, ctx, client_id, Client, "write"):
        return
    raise HTTPException(status_code=404, detail="客户不存在")


def assert_rms_client_writable_regular(
    db: Session,
    ctx: AuthContext,
    client_id: int,
    Client: Type[Any],
) -> None:
    if _recruitment_client_job_writable(db, ctx, client_id, Client):
        return
    ds.assert_client_in_scope(db, ctx, client_id, Client, RESOURCE_RMS_JOB, "write")


def assert_job_writable(
    db: Session,
    ctx: AuthContext,
    job_id: int,
    RmsJob: Type[Any],
    Client: Type[Any],
):
    job = scoped_jobs_query(db, ctx, RmsJob, Client, action="write").filter(RmsJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return job


def _user_manages_client_delivery_dept(
    db: Session,
    ctx: AuthContext,
    client: Any,
) -> bool:
    """True when the user's dept subtree covers the client's delivery department."""
    if ctx.user_id is None:
        return False
    delivery_dept = getattr(client, CLIENT_DELIVERY_DEPT_COL, None)
    if delivery_dept is None:
        return False
    user_depts = ctx.dept_ids or ([ctx.primary_dept_id] if ctx.primary_dept_id else [])
    if not user_depts:
        return False
    managed = ds._dept_subtree_ids(db, [int(d) for d in user_depts])
    return int(delivery_dept) in managed


def can_act_as_offer_submitter(
    db: Session,
    ctx: AuthContext,
    client: Any,
) -> bool:
    if ctx.is_super:
        return True
    if ctx.user_id is None:
        return False
    perms = ctx.permissions or set()
    if "rms.offer_approval.submit" in perms:
        return True
    delivery_owner = getattr(client, CLIENT_DELIVERY_OWNER_COL, None)
    if delivery_owner is not None and int(delivery_owner) == int(ctx.user_id):
        return True
    return _user_manages_client_delivery_dept(db, ctx, client)


def can_submit_offer_approval(
    db: Session,
    ctx: AuthContext,
    client: Any,
    *,
    app_status: str,
) -> bool:
    if (app_status or "").strip() != "pending_offer":
        return False
    if client is None:
        return False
    return can_act_as_offer_submitter(db, ctx, client)


def assert_can_submit_offer_approval(
    db: Session,
    ctx: AuthContext,
    client: Any,
) -> None:
    if can_act_as_offer_submitter(db, ctx, client):
        return
    raise HTTPException(status_code=403, detail="仅交付负责人或授权人员可发起 Offer 审批")


def visible_candidate_ids(
    db: Session,
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    action: str = "read",
) -> Optional[Set[int]]:
    if ctx.is_super:
        return None
    if action == "read":
        candidate_scope = ds.get_effective_data_scope(ctx, RESOURCE_RMS_CANDIDATE, "read")
        if candidate_scope == ds.SCOPE_ALL:
            return None
    ids: Set[int] = set()
    if ctx.user_id is not None:
        rows = (
            db.query(RmsCandidate.id)
            .filter(RmsCandidate.created_by_user_id == ctx.user_id)
            .all()
        )
        ids.update(int(r[0]) for r in rows)
    app_q = scoped_applications_query(db, ctx, RmsApplication, Client, action=action)
    for (cid,) in app_q.with_entities(RmsApplication.candidate_id).distinct().all():
        if cid is not None:
            ids.add(int(cid))
    return ids


def can_view_rms_delivery_ops_tabs(
    db: Session,
    ctx: AuthContext,
    Client: Type[Any],
) -> bool:
    """True when user has delivery client scope on applications, not recommended-by-only read."""
    if ctx.is_super:
        return True
    perms = ctx.permissions or set()
    if "rms.applications.read" not in perms and "rms.applications.write" not in perms:
        return False
    for action in ("write", "read"):
        if action == "write" and "rms.applications.write" not in perms:
            continue
        if action == "read" and "rms.applications.read" not in perms:
            continue
        allowed = ds.scoped_client_ids(db, ctx, RESOURCE_RMS_APPLICATION, action, Client)
        if allowed is None:
            return True
        if allowed:
            return True
    if ROLE_DELIVERY in (ctx.roles or []):
        return True
    return False


def assert_candidate_usable_for_application(
    db: Session,
    ctx: AuthContext,
    candidate_id: int,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> None:
    visible = visible_candidate_ids(db, ctx, RmsCandidate, RmsApplication, Client)
    if visible is None:
        return
    if candidate_id not in visible:
        raise HTTPException(status_code=404, detail="候选人不存在")
