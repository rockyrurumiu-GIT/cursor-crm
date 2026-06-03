"""RMS data scope and visibility helpers (Phase 2)."""
from __future__ import annotations

from typing import Any, Optional, Set, Type

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from auth import data_scope as ds
from auth.data_scope_catalog import (
    CLIENT_RECRUITMENT_DEPT_COL,
    CLIENT_RECRUITMENT_OWNER_COL,
    RESOURCE_CRM_CLIENT,
    RESOURCE_RMS_APPLICATION,
    RESOURCE_RMS_JOB,
)
from auth.service import AuthContext


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
) -> Query:
    q = db.query(RmsApplication)
    return ds.filter_query_by_client_scope(
        q, db, ctx, RESOURCE_RMS_APPLICATION, action, RmsApplication.client_id, Client
    )


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


def visible_candidate_ids(
    db: Session,
    ctx: AuthContext,
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Optional[Set[int]]:
    if ctx.is_super:
        return None
    ids: Set[int] = set()
    if ctx.user_id is not None:
        rows = (
            db.query(RmsCandidate.id)
            .filter(RmsCandidate.created_by_user_id == ctx.user_id)
            .all()
        )
        ids.update(int(r[0]) for r in rows)
    app_q = scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    for (cid,) in app_q.with_entities(RmsApplication.candidate_id).distinct().all():
        if cid is not None:
            ids.add(int(cid))
    return ids


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
