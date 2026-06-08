"""RMS recruitment dashboard aggregation."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Type

from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import ACTIVE_PIPELINE_STATUSES, APPLICATION_PROGRESS_ORDER, normalize_rms_date
from services import rms_scope as rms_ds

_PIPELINE_LABELS = {
    "pending_internal_screen": "待内筛",
    "pending_client_screen": "待客筛",
    "scheduling_interview": "约面中",
    "pending_first_interview": "待一面",
    "first_interview_passed": "待二面",
    "second_interview_passed": "待终面",
    "pending_offer": "待offer",
    "onboarding": "在途",
}

_STAGE_ENTER = {
    "internal_screen": "pending_internal_screen",
    "client_screen": "pending_client_screen",
    "scheduling": "scheduling_interview",
    "first_interview": "pending_first_interview",
    "second_interview": "first_interview_passed",
    "final_interview": "second_interview_passed",
    "offer": "pending_offer",
    "onboarding": "onboarding",
}

_STAGE_PASS = {
    "internal_screen": "pending_client_screen",
    "client_screen": "scheduling_interview",
    "scheduling": "pending_first_interview",
    "first_interview": "first_interview_passed",
    "second_interview": "second_interview_passed",
    "final_interview": "pending_offer",
    "offer": "onboarding",
    "onboarding": "hired",
}

_STAGE_FAIL = {
    "internal_screen": "internal_screen_failed",
    "client_screen": {"client_screen_failed", "client_screen_duplicate"},
    "scheduling": "interview_scheduling_failed",
    "first_interview": "first_interview_failed",
    "second_interview": {"second_interview_failed", "second_interview_abandoned"},
    "final_interview": {"final_interview_failed", "final_interview_abandoned"},
    "offer": "offer_dropped",
    "onboarding": "onboarding_lost",
}

_INTERVIEW_PASSED_STATUSES = frozenset({
    "first_interview_passed",
    "second_interview_passed",
    "pending_offer",
    "onboarding",
    "hired",
})
_ABANDONED_STATUSES = frozenset({"second_interview_abandoned", "final_interview_abandoned"})

_OFFER_DROPPED_STATUSES = frozenset({"offer_dropped"})
_ONBOARDING_LOST_STATUSES = frozenset({"onboarding_lost"})
_HIRED_STATUSES = frozenset({"hired"})

_SUMMARY_METRIC_KEYS = (
    "pushed_resume_count",
    "internal_screen_passed",
    "duplicate_count",
    "pending_client_screen",
    "client_screen_passed",
    "interview_abandoned",
    "pending_interview",
    "interviewed",
    "interview_passed",
    "pending_offer_count",
    "offer_dropped_count",
    "onboarding_count",
    "onboarding_lost_count",
    "hired_count",
)


def parse_job_ids(raw: Optional[str]) -> Optional[List[int]]:
    if raw is None or not str(raw).strip():
        return None
    ids: List[int] = []
    for part in str(raw).split(","):
        token = part.strip()
        if not token:
            continue
        if not token.isdigit():
            raise ValueError("job_ids 仅支持逗号分隔的整数")
        ids.append(int(token))
    return ids or None


def _statuses_from(anchor: str) -> Set[str]:
    try:
        idx = APPLICATION_PROGRESS_ORDER.index(anchor)
    except ValueError:
        return set()
    return set(APPLICATION_PROGRESS_ORDER[idx:])


_INTERNAL_SCREEN_PASSED_STATUSES = _statuses_from("pending_client_screen")
_CLIENT_SCREEN_PASSED_STATUSES = _statuses_from("scheduling_interview")
_INTERVIEWED_STATUSES = (
    _statuses_from("first_interview_passed") | _statuses_from("first_interview_failed")
)


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    return f"{round(100 * numerator / denominator, 1)}%"


def _effective_job_ids(filters: Dict[str, Any]) -> Optional[List[int]]:
    job_ids = filters.get("job_ids")
    if job_ids:
        return [int(x) for x in job_ids]
    if filters.get("job_id") is not None:
        return [int(filters["job_id"])]
    return None


def _filter_applications_query(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
):
    q = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    if filters.get("client_id") is not None:
        q = q.filter(RmsApplication.client_id == int(filters["client_id"]))
    job_filter_ids = _effective_job_ids(filters)
    if job_filter_ids is not None:
        q = q.filter(RmsApplication.job_id.in_(job_filter_ids))
    if filters.get("recruiter_user_id") is not None:
        q = q.filter(RmsApplication.recommended_by == int(filters["recruiter_user_id"]))

    need_job = filters.get("priority") or filters.get("city")
    need_client = filters.get("sales_user_id") or filters.get("delivery_user_id")
    if need_job or need_client:
        job_ids_q = rms_ds.scoped_jobs_query(db, ctx, RmsJob, Client, action="read")
        if filters.get("priority"):
            job_ids_q = job_ids_q.filter(RmsJob.priority == filters["priority"])
        if filters.get("city"):
            job_ids_q = job_ids_q.filter(RmsJob.location == filters["city"])
        if need_client:
            client_q = db.query(Client)
            if filters.get("sales_user_id") is not None:
                client_q = client_q.filter(Client.owner_user_id == int(filters["sales_user_id"]))
            if filters.get("delivery_user_id") is not None:
                client_q = client_q.filter(
                    Client.delivery_owner_user_id == int(filters["delivery_user_id"])
                )
            allowed_clients = {c.id for c in client_q.all()}
            job_ids_q = job_ids_q.filter(RmsJob.client_id.in_(allowed_clients or [-1]))
        job_ids = [j.id for j in job_ids_q.all()]
        q = q.filter(RmsApplication.job_id.in_(job_ids or [-1]))
    return q


def _cohort_apps(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
) -> List[Any]:
    q = _filter_applications_query(db, ctx, RmsApplication, RmsJob, Client, filters)
    if filters.get("date_from"):
        q = q.filter(func.substr(RmsApplication.recommended_at, 1, 10) >= filters["date_from"])
    if filters.get("date_to"):
        q = q.filter(func.substr(RmsApplication.recommended_at, 1, 10) <= filters["date_to"])
    return q.all()


def _demand_overview(
    db: Session,
    ctx: AuthContext,
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
) -> Dict[str, int]:
    q = _scoped_jobs_query(db, ctx, RmsJob, Client, filters)
    q = q.filter(RmsJob.status == "open")
    rows = q.all()
    clients: Set[int] = set()
    hc = 0
    for j in rows:
        clients.add(int(j.client_id))
        hc += int(j.headcount or 0)
    return {
        "open_client_count": len(clients),
        "open_job_count": len(rows),
        "open_hc_total": hc,
    }


def _scoped_jobs_query(
    db: Session,
    ctx: AuthContext,
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
):
    q = rms_ds.scoped_jobs_query(db, ctx, RmsJob, Client, action="read")
    if filters.get("client_id") is not None:
        q = q.filter(RmsJob.client_id == int(filters["client_id"]))
    job_filter_ids = _effective_job_ids(filters)
    if job_filter_ids is not None:
        q = q.filter(RmsJob.id.in_(job_filter_ids))
    if filters.get("priority"):
        q = q.filter(RmsJob.priority == filters["priority"])
    if filters.get("city"):
        q = q.filter(RmsJob.location == filters["city"])
    if filters.get("sales_user_id") is not None or filters.get("delivery_user_id") is not None:
        client_q = db.query(Client)
        if filters.get("sales_user_id") is not None:
            client_q = client_q.filter(Client.owner_user_id == int(filters["sales_user_id"]))
        if filters.get("delivery_user_id") is not None:
            client_q = client_q.filter(
                Client.delivery_owner_user_id == int(filters["delivery_user_id"])
            )
        allowed = {c.id for c in client_q.all()}
        q = q.filter(RmsJob.client_id.in_(allowed or [-1]))
    return q


def _pipeline_overview(apps: List[Any]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = defaultdict(int)
    for a in apps:
        st = (a.status or "").strip()
        if st in ACTIVE_PIPELINE_STATUSES:
            counts[st] += 1
    return [
        {"status": st, "label": _PIPELINE_LABELS.get(st, st), "count": counts.get(st, 0)}
        for st in sorted(ACTIVE_PIPELINE_STATUSES, key=lambda x: list(_PIPELINE_LABELS).index(x))
    ]


def _hist_for_apps(
    db: Session,
    app_ids: List[int],
    RmsApplicationStatusHistory: Type[Any],
) -> Dict[int, List[Any]]:
    if not app_ids:
        return {}
    rows = (
        db.query(RmsApplicationStatusHistory)
        .filter(RmsApplicationStatusHistory.application_id.in_(app_ids))
        .order_by(RmsApplicationStatusHistory.id.asc())
        .all()
    )
    out: Dict[int, List[Any]] = defaultdict(list)
    for r in rows:
        out[r.application_id].append(r)
    return out


def _historical_overview(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
) -> List[Dict[str, Any]]:
    app_by_id = {a.id: a for a in apps}
    resume_count = len(apps)
    rows_out: List[Dict[str, Any]] = []

    for stage_key, enter_status in _STAGE_ENTER.items():
        pass_status = _STAGE_PASS[stage_key]
        fail_val = _STAGE_FAIL[stage_key]
        fail_set = fail_val if isinstance(fail_val, set) else {fail_val}

        entered = 0
        passed = 0
        failed = 0
        pending_now = 0

        for app in apps:
            histories = hist_map.get(app.id, [])
            to_statuses = {h.to_status for h in histories}
            to_statuses.add(app.status or "")
            if enter_status in to_statuses or app.status == enter_status:
                entered += 1
            if pass_status in to_statuses:
                passed += 1
            if to_statuses & fail_set:
                failed += 1
            if (app.status or "") == enter_status:
                pending_now += 1

        denom = entered - pending_now
        label_map = {
            "internal_screen": "内筛",
            "client_screen": "客筛",
            "scheduling": "参面",
            "first_interview": "一面",
            "second_interview": "二面",
            "final_interview": "终面",
            "offer": "offer",
            "onboarding": "入职",
        }
        rows_out.append({
            "stage": stage_key,
            "label": label_map.get(stage_key, stage_key),
            "entered": entered,
            "passed": passed,
            "failed": failed,
            "pending_count": pending_now,
            "denominator": denom,
            "pass_rate": _rate(passed, denom),
        })

    hired = sum(1 for a in apps if (a.status or "") == "hired")
    onboarding_lost = sum(
        1 for a in apps
        if any(h.to_status == "onboarding_lost" for h in hist_map.get(a.id, []))
    )
    hired_entered = hired + onboarding_lost
    rows_out.append({
        "stage": "hired_summary",
        "label": "入职",
        "entered": hired_entered,
        "passed": hired,
        "failed": onboarding_lost,
        "pending_count": 0,
        "denominator": hired_entered,
        "pass_rate": _rate(hired, hired_entered),
    })

    return [{"resume_count": resume_count, "stages": rows_out}]


def _recruiter_performance(
    db: Session,
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    RmsJob: Type[Any],
    today: date,
) -> List[Dict[str, Any]]:
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    month_end = today.strftime("%Y-%m-%d")

    by_rec: Dict[Optional[int], List[Any]] = defaultdict(list)
    for a in apps:
        by_rec[a.recommended_by].append(a)

    job_ids = {a.job_id for a in apps}
    jobs = {
        j.id: j
        for j in db.query(RmsJob).filter(RmsJob.id.in_(job_ids or [-1])).all()
    }

    rows: List[Dict[str, Any]] = []
    for rec_id, rec_apps in by_rec.items():
        clients: Set[int] = set()
        jids: Set[int] = set()
        hc = 0
        hired_month = 0
        for a in rec_apps:
            clients.add(int(a.client_id))
            jids.add(int(a.job_id))
            job = jobs.get(a.job_id)
            if job:
                hc += int(job.headcount or 0)
            if (
                (a.status or "") == "hired"
                and (a.hired_at or "") >= month_start
                and (a.hired_at or "") <= month_end
            ):
                hired_month += 1

        hist_subset = {a.id: hist_map.get(a.id, []) for a in rec_apps}
        hist_block = _historical_overview(rec_apps, hist_subset)
        stages = hist_block[0]["stages"] if hist_block else []

        def _stage_rate(key: str) -> str:
            for s in stages:
                if s.get("stage") == key:
                    return s.get("pass_rate", "—")
            return "—"

        rows.append({
            "recruiter_user_id": rec_id,
            "client_count": len(clients),
            "job_count": len(jids),
            "hc_total": hc,
            "hired_this_month": hired_month,
            "internal_screen_rate": _stage_rate("internal_screen"),
            "client_screen_rate": _stage_rate("client_screen"),
            "scheduling_rate": _stage_rate("scheduling"),
            "first_interview_rate": _stage_rate("first_interview"),
            "second_interview_rate": _stage_rate("second_interview"),
            "final_interview_rate": _stage_rate("final_interview"),
            "offer_rate": _stage_rate("offer"),
            "onboarding_rate": _stage_rate("onboarding"),
        })

    rows.sort(key=lambda r: (-(r.get("hired_this_month") or 0), r.get("recruiter_user_id") or 0))
    return rows


def _period_label(filters: Dict[str, Any]) -> str:
    date_from = (filters.get("date_from") or "").strip()
    date_to = (filters.get("date_to") or "").strip()
    if date_from and date_to:
        return f"{date_from} ~ {date_to}"
    if date_from:
        return f"{date_from} ~"
    if date_to:
        return f"~ {date_to}"
    return "全量"


def _app_to_statuses(app: Any, hist_map: Dict[int, List[Any]]) -> Set[str]:
    statuses = {h.to_status for h in hist_map.get(app.id, []) if h.to_status}
    current = (app.status or "").strip()
    if current:
        statuses.add(current)
    return statuses


def _empty_job_metrics() -> Dict[str, int]:
    return {key: 0 for key in _SUMMARY_METRIC_KEYS}


def _metrics_for_apps(apps: List[Any], hist_map: Dict[int, List[Any]]) -> Dict[str, int]:
    metrics = _empty_job_metrics()
    for app in apps:
        metrics["pushed_resume_count"] += 1
        to_statuses = _app_to_statuses(app, hist_map)
        current = (app.status or "").strip()

        if to_statuses & _INTERNAL_SCREEN_PASSED_STATUSES:
            metrics["internal_screen_passed"] += 1
        # duplicate_count: first-version placeholder until duplicate detection field ships.
        if current == "pending_client_screen":
            metrics["pending_client_screen"] += 1
        if to_statuses & _CLIENT_SCREEN_PASSED_STATUSES:
            metrics["client_screen_passed"] += 1
        if to_statuses & _ABANDONED_STATUSES:
            metrics["interview_abandoned"] += 1
        if current == "pending_first_interview":
            metrics["pending_interview"] += 1
        if to_statuses & _INTERVIEWED_STATUSES:
            metrics["interviewed"] += 1
        if to_statuses & _INTERVIEW_PASSED_STATUSES:
            metrics["interview_passed"] += 1
        if current == "pending_offer":
            metrics["pending_offer_count"] += 1
        if to_statuses & _OFFER_DROPPED_STATUSES:
            metrics["offer_dropped_count"] += 1
        if "onboarding" in to_statuses:
            metrics["onboarding_count"] += 1
        if to_statuses & _ONBOARDING_LOST_STATUSES:
            metrics["onboarding_lost_count"] += 1
        if to_statuses & _HIRED_STATUSES:
            metrics["hired_count"] += 1
    return metrics


def _client_job_stage_summary(
    db: Session,
    ctx: AuthContext,
    cohort: List[Any],
    hist_map: Dict[int, List[Any]],
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    jobs = _scoped_jobs_query(db, ctx, RmsJob, Client, filters).all()
    apps_by_job: Dict[int, List[Any]] = defaultdict(list)
    for app in cohort:
        apps_by_job[int(app.job_id)].append(app)

    rows: List[Dict[str, Any]] = []
    total = _empty_job_metrics()
    for job in sorted(jobs, key=lambda j: int(j.id)):
        metrics = _metrics_for_apps(apps_by_job.get(int(job.id), []), hist_map)
        row = {
            "job_id": int(job.id),
            "job_title": (job.title or "").strip() or f"岗位#{job.id}",
            "headcount": int(job.headcount or 0),
            "location": (job.location or "").strip(),
            **metrics,
        }
        rows.append(row)
        for key in _SUMMARY_METRIC_KEYS:
            total[key] += metrics[key]

    return {
        "period_label": _period_label(filters),
        "rows": rows,
        "total": total,
    }


def compute_rms_dashboard(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
    *,
    client_id: Optional[int] = None,
    job_id: Optional[int] = None,
    job_ids: Optional[List[int]] = None,
    priority: Optional[str] = None,
    city: Optional[str] = None,
    sales_user_id: Optional[int] = None,
    delivery_user_id: Optional[int] = None,
    recruiter_user_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    filters = {
        "client_id": client_id,
        "job_id": job_id if not job_ids else None,
        "job_ids": job_ids,
        "priority": priority,
        "city": city,
        "sales_user_id": sales_user_id,
        "delivery_user_id": delivery_user_id,
        "recruiter_user_id": recruiter_user_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    filters = {k: v for k, v in filters.items() if v is not None and v != "" and v != []}

    cohort = _cohort_apps(db, ctx, RmsApplication, RmsJob, Client, filters)
    active_q = _filter_applications_query(db, ctx, RmsApplication, RmsJob, Client, filters)
    active_apps = [
        a for a in active_q.all() if (a.status or "") in ACTIVE_PIPELINE_STATUSES
    ]
    hist_map = _hist_for_apps(db, [a.id for a in cohort], RmsApplicationStatusHistory)

    return {
        "filters": filters,
        "demand_overview": _demand_overview(db, ctx, RmsJob, Client, filters),
        "pipeline_overview": _pipeline_overview(active_apps),
        "historical_overview": _historical_overview(cohort, hist_map),
        "recruiter_performance": _recruiter_performance(
            db, cohort, hist_map, RmsJob, _utc_today()
        ),
        "client_job_stage_summary": _client_job_stage_summary(
            db, ctx, cohort, hist_map, RmsJob, Client, filters
        ),
    }
