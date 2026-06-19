"""RMS recruitment dashboard aggregation."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Type, Union

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
    "offer_approval_pending": "Offer审批中",
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

_ABANDONED_STATUSES = frozenset({"second_interview_abandoned", "final_interview_abandoned"})

_SCHEDULING_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"scheduling_interview"})
_PENDING_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"pending_first_interview"})
_PENDING_SECOND_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"first_interview_passed"})
_PENDING_FINAL_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"second_interview_passed"})
_ONBOARDING_SNAPSHOT_STATUSES = frozenset({"onboarding"})

_FIRST_INTERVIEW_OUTCOME_STATUSES = frozenset({
    "first_interview_passed",
    "first_interview_failed",
})
_SECOND_INTERVIEW_OUTCOME_STATUSES = frozenset({
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
})
_INTERVIEW_PASSED_STATUSES = frozenset({
    "first_interview_passed",
    "second_interview_passed",
    "pending_offer",
    "onboarding",
    "hired",
})

_OFFER_DROPPED_STATUSES = frozenset({"offer_dropped"})
_ONBOARDING_LOST_STATUSES = frozenset({"onboarding_lost"})
_HIRED_STATUSES = frozenset({"hired"})

_SUMMARY_METRIC_KEYS = (
    "pushed_resume_count",
    "internal_screen_passed",
    "duplicate_count",
    "pending_internal_screen",
    "pending_client_screen",
    "scheduling_interview_count",
    "client_screen_passed",
    "interview_abandoned",
    "pending_interview",
    "pending_second_interview",
    "pending_final_interview",
    "first_interview_count",
    "first_interview_passed_count",
    "second_interview_count",
    "second_interview_passed_count",
    "interviewed",
    "interview_passed",
    "pending_offer_count",
    "offer_dropped_count",
    "onboarding_count",
    "onboarding_lost_count",
    "hired_count",
    "pending_roster_conversion_count",
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


_CLIENT_SCREEN_PASSED_STATUSES = _statuses_from("scheduling_interview")
# 已面试/面试通过：周期内曾到达对应节点，且当前（或 date_to 快照）仍在一面结果之后；
# 误操作改回「待一面」等前置状态时不计入。
_INTERVIEWED_CURRENT_STATUSES = _statuses_from("first_interview_passed") | frozenset({
    "first_interview_failed",
})
_SECOND_INTERVIEWED_CURRENT_STATUSES = _statuses_from("second_interview_passed") | frozenset({
    "second_interview_failed",
    "second_interview_abandoned",
})
# 生命周期/历史各面试阶段「通过」：周期内曾到达该阶段 pass 节点，且当前仍在该 pass 节点之后。
_STAGE_PASS_CURRENT_GUARD = {
    "first_interview": _statuses_from("first_interview_passed"),
    "second_interview": _statuses_from("second_interview_passed"),
    "final_interview": _statuses_from("pending_offer"),
}


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _rate(numerator: int, denominator: int, *, decimals: int = 1) -> str:
    if denominator <= 0:
        return "—"
    pct = 100 * numerator / denominator
    if decimals <= 0:
        return f"{round(pct)}%"
    return f"{round(pct, decimals)}%"


def _effective_job_ids(filters: Dict[str, Any]) -> Optional[List[int]]:
    job_ids = filters.get("job_ids")
    if job_ids:
        return [int(x) for x in job_ids]
    if filters.get("job_id") is not None:
        return [int(filters["job_id"])]
    return None


def _period_bounds(filters: Dict[str, Any]) -> tuple[str, str]:
    return (
        (filters.get("date_from") or "").strip(),
        (filters.get("date_to") or "").strip(),
    )


def _has_period_filter(filters: Dict[str, Any]) -> bool:
    date_from, date_to = _period_bounds(filters)
    return bool(date_from or date_to)


def _date_only(value: Any) -> str:
    normalized = normalize_rms_date(value)
    return normalized[:10] if normalized else ""


def _event_in_period(day: str, date_from: str, date_to: str) -> bool:
    if not day:
        return False
    if date_from and day < date_from:
        return False
    if date_to and day > date_to:
        return False
    return True


def _recommended_in_period(app: Any, date_from: str, date_to: str) -> bool:
    if not _has_period_filter({"date_from": date_from, "date_to": date_to}):
        return True
    return _event_in_period(_date_only(app.recommended_at), date_from, date_to)


def _snapshot_as_of(filters: Dict[str, Any]) -> Optional[str]:
    _, date_to = _period_bounds(filters)
    return date_to or None


def _status_at(
    app: Any,
    histories: List[Any],
    as_of: Optional[str],
) -> str:
    if not as_of:
        return (app.status or "").strip()
    current = "recommended"
    for hist in histories:
        day = _date_only(hist.changed_at)
        if not day or day > as_of:
            break
        to_status = (hist.to_status or "").strip()
        if to_status:
            current = to_status
    return current


def _app_had_transition_in_period(
    histories: List[Any],
    to_statuses: Set[str],
    date_from: str,
    date_to: str,
) -> bool:
    for hist in histories:
        to_status = (hist.to_status or "").strip()
        if to_status not in to_statuses:
            continue
        if not _has_period_filter({"date_from": date_from, "date_to": date_to}):
            return True
        if _event_in_period(_date_only(hist.changed_at), date_from, date_to):
            return True
    return False


def _app_had_transition_to_in_period(
    histories: List[Any],
    to_status: str,
    date_from: str,
    date_to: str,
) -> bool:
    return _app_had_transition_in_period(histories, {to_status}, date_from, date_to)


def _app_counts_as_interviewed(
    app: Any,
    histories: List[Any],
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_in_period(
        histories, _FIRST_INTERVIEW_OUTCOME_STATUSES, date_from, date_to
    ):
        return False
    return _status_at(app, histories, snapshot_as_of) in _INTERVIEWED_CURRENT_STATUSES


def _app_counts_as_second_interviewed(
    app: Any,
    histories: List[Any],
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_in_period(
        histories, _SECOND_INTERVIEW_OUTCOME_STATUSES, date_from, date_to
    ):
        return False
    return _status_at(app, histories, snapshot_as_of) in _SECOND_INTERVIEWED_CURRENT_STATUSES


def _app_counts_as_interview_passed(
    app: Any,
    histories: List[Any],
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_in_period(
        histories, _INTERVIEW_PASSED_STATUSES, date_from, date_to
    ):
        return False
    return _status_at(app, histories, snapshot_as_of) in _INTERVIEW_PASSED_STATUSES


def _app_counts_as_stage_passed(
    app: Any,
    histories: List[Any],
    stage_key: str,
    pass_status: str,
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_to_in_period(histories, pass_status, date_from, date_to):
        return False
    guard = _STAGE_PASS_CURRENT_GUARD.get(stage_key)
    if guard is None:
        return True
    return _status_at(app, histories, snapshot_as_of) in guard


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


def _scoped_apps(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
) -> List[Any]:
    return _filter_applications_query(db, ctx, RmsApplication, RmsJob, Client, filters).all()


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


def _fail_status_set(fail_val: Union[str, Set[str]]) -> Set[str]:
    if isinstance(fail_val, set):
        return fail_val
    return {fail_val}


def _historical_overview(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
) -> List[Dict[str, Any]]:
    date_from, date_to = _period_bounds(filters)
    snapshot_as_of = _snapshot_as_of(filters)
    resume_count = sum(
        1 for app in apps if _recommended_in_period(app, date_from, date_to)
    )
    rows_out: List[Dict[str, Any]] = []

    for stage_key, enter_status in _STAGE_ENTER.items():
        pass_status = _STAGE_PASS[stage_key]
        fail_set = _fail_status_set(_STAGE_FAIL[stage_key])

        entered = 0
        passed = 0
        failed = 0
        pending_now = 0

        for app in apps:
            histories = hist_map.get(app.id, [])
            if _app_had_transition_to_in_period(histories, enter_status, date_from, date_to):
                entered += 1
            if _app_counts_as_stage_passed(
                app, histories, stage_key, pass_status, date_from, date_to, snapshot_as_of
            ):
                passed += 1
            if _app_had_transition_in_period(histories, fail_set, date_from, date_to):
                failed += 1
            if _status_at(app, histories, snapshot_as_of) == enter_status:
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

    hired = 0
    onboarding_lost = 0
    onboarding_pending = 0
    onboarding_entered = 0
    for app in apps:
        histories = hist_map.get(app.id, [])
        if _app_had_transition_to_in_period(histories, "onboarding", date_from, date_to):
            onboarding_entered += 1
        if _app_had_transition_to_in_period(histories, "hired", date_from, date_to):
            hired += 1
        if _app_had_transition_to_in_period(histories, "onboarding_lost", date_from, date_to):
            onboarding_lost += 1
        if _status_at(app, histories, snapshot_as_of) == "onboarding":
            onboarding_pending += 1

    hired_entered = onboarding_entered
    hired_denom = hired_entered - onboarding_pending
    rows_out.append({
        "stage": "hired_summary",
        "label": "入职",
        "entered": hired_entered,
        "passed": hired,
        "failed": onboarding_lost,
        "pending_count": onboarding_pending,
        "denominator": hired_denom,
        "pass_rate": _rate(hired, hired_denom),
    })

    return [{"resume_count": resume_count, "stages": rows_out}]


def _recruiter_performance(
    db: Session,
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    RmsJob: Type[Any],
    today: date,
    filters: Dict[str, Any],
) -> List[Dict[str, Any]]:
    month_start = today.replace(day=1).strftime("%Y-%m-%d")
    month_end = today.strftime("%Y-%m-%d")

    date_from, date_to = _period_bounds(filters)

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
        recommended_count = 0
        for a in rec_apps:
            clients.add(int(a.client_id))
            jids.add(int(a.job_id))
            job = jobs.get(a.job_id)
            if job:
                hc += int(job.headcount or 0)
            if _recommended_in_period(a, date_from, date_to):
                recommended_count += 1
            if (
                (a.status or "") == "hired"
                and (a.hired_at or "") >= month_start
                and (a.hired_at or "") <= month_end
            ):
                hired_month += 1

        hist_subset = {a.id: hist_map.get(a.id, []) for a in rec_apps}
        hist_block = _historical_overview(rec_apps, hist_subset, filters)
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
            "recommended_count": recommended_count,
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
    date_from, date_to = _period_bounds(filters)
    if date_from and date_to:
        return f"{date_from} ~ {date_to}"
    if date_from:
        return f"{date_from} ~"
    if date_to:
        return f"~ {date_to}"
    return "全量"


def _empty_job_metrics() -> Dict[str, int]:
    return {key: 0 for key in _SUMMARY_METRIC_KEYS}


def _metrics_for_apps(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
) -> Dict[str, int]:
    date_from, date_to = _period_bounds(filters)
    snapshot_as_of = _snapshot_as_of(filters)
    metrics = _empty_job_metrics()

    for app in apps:
        histories = hist_map.get(app.id, [])
        status_snapshot = _status_at(app, histories, snapshot_as_of)
        if _recommended_in_period(app, date_from, date_to):
            metrics["pushed_resume_count"] += 1
        if _app_had_transition_to_in_period(
            histories, "pending_client_screen", date_from, date_to
        ):
            metrics["internal_screen_passed"] += 1
        if _app_had_transition_to_in_period(
            histories, "client_screen_duplicate", date_from, date_to
        ):
            metrics["duplicate_count"] += 1
        if status_snapshot == "pending_internal_screen":
            metrics["pending_internal_screen"] += 1
        if status_snapshot == "pending_client_screen":
            metrics["pending_client_screen"] += 1
        if status_snapshot in _SCHEDULING_INTERVIEW_SNAPSHOT_STATUSES:
            metrics["scheduling_interview_count"] += 1
        if _app_had_transition_in_period(
            histories, _CLIENT_SCREEN_PASSED_STATUSES, date_from, date_to
        ):
            metrics["client_screen_passed"] += 1
        if _app_had_transition_in_period(histories, _ABANDONED_STATUSES, date_from, date_to):
            metrics["interview_abandoned"] += 1
        if status_snapshot in _PENDING_INTERVIEW_SNAPSHOT_STATUSES:
            metrics["pending_interview"] += 1
        if status_snapshot in _PENDING_SECOND_INTERVIEW_SNAPSHOT_STATUSES:
            metrics["pending_second_interview"] += 1
        if status_snapshot in _PENDING_FINAL_INTERVIEW_SNAPSHOT_STATUSES:
            metrics["pending_final_interview"] += 1
        if _app_counts_as_interviewed(
            app, histories, date_from, date_to, snapshot_as_of
        ):
            metrics["interviewed"] += 1
            metrics["first_interview_count"] += 1
        if _app_counts_as_stage_passed(
            app,
            histories,
            "first_interview",
            "first_interview_passed",
            date_from,
            date_to,
            snapshot_as_of,
        ):
            metrics["first_interview_passed_count"] += 1
        if _app_counts_as_second_interviewed(
            app, histories, date_from, date_to, snapshot_as_of
        ):
            metrics["second_interview_count"] += 1
        if _app_counts_as_stage_passed(
            app,
            histories,
            "second_interview",
            "second_interview_passed",
            date_from,
            date_to,
            snapshot_as_of,
        ):
            metrics["second_interview_passed_count"] += 1
        if _app_counts_as_interview_passed(
            app, histories, date_from, date_to, snapshot_as_of
        ):
            metrics["interview_passed"] += 1
        if status_snapshot == "pending_offer":
            metrics["pending_offer_count"] += 1
        if _app_had_transition_in_period(
            histories, _OFFER_DROPPED_STATUSES, date_from, date_to
        ):
            metrics["offer_dropped_count"] += 1
        if status_snapshot in _ONBOARDING_SNAPSHOT_STATUSES:
            metrics["onboarding_count"] += 1
        if _app_had_transition_in_period(
            histories, _ONBOARDING_LOST_STATUSES, date_from, date_to
        ):
            metrics["onboarding_lost_count"] += 1
        if _app_had_transition_in_period(histories, _HIRED_STATUSES, date_from, date_to):
            metrics["hired_count"] += 1
        if status_snapshot == "hired" and not getattr(app, "converted_to_roster_entry_id", None):
            metrics["pending_roster_conversion_count"] += 1
    return metrics


_JOB_STAGE_RATE_SPECS = (
    ("internal_screen_passed", "internal_screen_passed_rate", "pushed_resume_count"),
    ("duplicate_count", "duplicate_count_rate", "pushed_resume_count"),
    ("client_screen_passed", "client_screen_passed_rate", "internal_screen_passed"),
    ("interview_abandoned", "interview_abandoned_rate", "internal_screen_passed"),
    ("first_interview_passed_count", "first_interview_passed_rate", "first_interview_count"),
    ("second_interview_passed_count", "second_interview_passed_rate", "second_interview_count"),
    ("interview_passed", "interview_passed_rate", "interviewed"),
    ("offer_dropped_count", "offer_dropped_count_rate", "second_interview_passed_count"),
    ("onboarding_lost_count", "onboarding_lost_count_rate", "onboarding_count"),
)


def _attach_job_stage_rates(metrics: Dict[str, int]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(metrics)
    for num_key, rate_key, denom_key in _JOB_STAGE_RATE_SPECS:
        out[rate_key] = _rate(
            int(metrics.get(num_key, 0)),
            int(metrics.get(denom_key, 0)),
            decimals=0,
        )
    return out


def _parse_rate_value(rate_str: str) -> Optional[float]:
    text = (rate_str or "").strip()
    if not text or text == "—":
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


_LIFECYCLE_FUNNEL_SPECS = (
    ("resume", "简历数"),
    ("internal_screen", "内筛通过"),
    ("client_screen", "客筛通过"),
    ("scheduling", "约面成功"),
    ("first_interview", "一面通过"),
    ("second_interview", "二面通过"),
    ("final_interview", "终面通过"),
    ("offer", "接offer"),
    ("hired_summary", "已入职"),
)


def _lifecycle_funnel(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    hist_block = _historical_overview(apps, hist_map, filters)
    block = hist_block[0] if hist_block else {"resume_count": 0, "stages": []}
    resume_count = int(block.get("resume_count") or 0)
    stage_by_key = {str(s.get("stage") or ""): s for s in (block.get("stages") or [])}

    rows: List[Dict[str, Any]] = []
    prev_entered = resume_count
    for stage_key, label in _LIFECYCLE_FUNNEL_SPECS:
        if stage_key == "resume":
            rows.append({
                "key": stage_key,
                "label": label,
                "entered": resume_count,
                "passed": resume_count,
                "failed": 0,
                "pending": 0,
                "processed": resume_count,
                "pass_rate": "—",
                "pass_rate_value": None,
                "funnel_count": resume_count,
            })
            prev_entered = resume_count
            continue
        stage = stage_by_key.get(stage_key) or {}
        passed = int(stage.get("passed") or 0)
        failed = int(stage.get("failed") or 0)
        pending = int(stage.get("pending_count") or 0)
        entered = prev_entered
        processed = entered - pending
        pass_rate = _rate(passed, processed)
        rows.append({
            "key": stage_key,
            "label": label,
            "entered": entered,
            "passed": passed,
            "failed": failed,
            "pending": pending,
            "processed": processed,
            "pass_rate": pass_rate,
            "pass_rate_value": _parse_rate_value(pass_rate),
            "funnel_count": passed,
        })
        prev_entered = passed

    hired_stage = stage_by_key.get("hired_summary") or {}
    hired_count = int(hired_stage.get("passed") or 0)
    return {
        "base_count": resume_count,
        "hired_count": hired_count,
        "resume_to_hire_rate": _rate(hired_count, resume_count, decimals=1),
        "rows": rows,
    }


def _client_job_stage_summary(
    db: Session,
    ctx: AuthContext,
    scoped_apps: List[Any],
    hist_map: Dict[int, List[Any]],
    RmsJob: Type[Any],
    Client: Type[Any],
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    jobs = _scoped_jobs_query(db, ctx, RmsJob, Client, filters).all()
    client_ids = {int(j.client_id) for j in jobs if j.client_id is not None}
    client_names: Dict[int, str] = {}
    if client_ids:
        for cid, name in (
            db.query(Client.id, Client.name).filter(Client.id.in_(client_ids)).all()
        ):
            client_names[int(cid)] = (name or "").strip()

    apps_by_job: Dict[int, List[Any]] = defaultdict(list)
    for app in scoped_apps:
        apps_by_job[int(app.job_id)].append(app)

    rows: List[Dict[str, Any]] = []
    total = _empty_job_metrics()
    for job in sorted(jobs, key=lambda j: int(j.id)):
        metrics = _metrics_for_apps(apps_by_job.get(int(job.id), []), hist_map, filters)
        cid = int(job.client_id) if job.client_id is not None else None
        row = {
            "job_id": int(job.id),
            "job_title": (job.title or "").strip() or f"岗位#{job.id}",
            "client_id": cid,
            "client_name": client_names.get(cid, "") if cid is not None else "",
            "headcount": int(job.headcount or 0) if (job.status or "").strip() == "open" else 0,
            "location": (job.location or "").strip(),
            **_attach_job_stage_rates(metrics),
        }
        rows.append(row)
        for key in _SUMMARY_METRIC_KEYS:
            total[key] += metrics[key]

    return {
        "period_label": _period_label(filters),
        "rows": rows,
        "total": _attach_job_stage_rates(total),
    }


def _active_users_in_dept_ids(db: Session, dept_ids: Set[int]) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    if not dept_ids:
        return []

    dept_sql = ",".join(str(int(d)) for d in sorted(dept_ids))
    rows = db.execute(
        text(
            "SELECT u.id, u.username, u.display_name "
            "FROM sys_user u "
            "INNER JOIN sys_user_dept ud ON ud.user_id = u.id "
            f"WHERE u.status = 'active' AND ud.dept_id IN ({dept_sql}) "
            "GROUP BY u.id, u.username, u.display_name "
            "ORDER BY COALESCE(u.display_name, u.username), u.username"
        )
    ).mappings().all()
    return [
        {
            "id": int(row["id"]),
            "username": str(row["username"]),
            "display_name": str(row["display_name"] or row["username"]),
        }
        for row in rows
    ]


def _list_dept_subtree_users(
    db: Session,
    ctx: AuthContext,
    Client: Type[Any],
    *,
    client_dept_attr: str,
) -> List[Dict[str, Any]]:
    """Active users in dept subtrees tied to visible clients (for dashboard filters)."""
    from auth import data_scope as ds
    from services.clients import scoped_client_query

    clients = scoped_client_query(db, ctx, Client, action="read").all()
    dept_ids: Set[int] = set()
    for client in clients:
        dept_id = getattr(client, client_dept_attr, None)
        if dept_id is not None:
            dept_ids.add(int(dept_id))
    if not dept_ids:
        return []

    expanded = ds._dept_subtree_ids(db, list(dept_ids))
    return _active_users_in_dept_ids(db, expanded)


def _list_org_dept_subtree_users(
    db: Session,
    *,
    dept_where_sql: str,
    dept_params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Active users in org dept subtrees matching dept_where_sql (for dashboard filters)."""
    from sqlalchemy import text

    from auth import data_scope as ds

    rows = db.execute(
        text(
            "SELECT id FROM sys_dept WHERE status = 'active' "
            f"AND ({dept_where_sql})"
        ),
        dept_params,
    ).fetchall()
    dept_ids = [int(r[0]) for r in rows]
    if not dept_ids:
        return []

    expanded = ds._dept_subtree_ids(db, dept_ids)
    return _active_users_in_dept_ids(db, expanded)


def list_recruitment_dept_users(
    db: Session,
    ctx: AuthContext,
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    """Active users in recruitment-dept subtrees (for dashboard 推荐人 filter)."""
    return _list_dept_subtree_users(
        db, ctx, Client, client_dept_attr="recruitment_dept_id"
    )


def list_delivery_dept_users(
    db: Session,
    ctx: AuthContext,
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    """Active users in 交付部 org dept subtrees (for dashboard 交付 filter)."""
    _ = ctx, Client
    return _list_org_dept_subtree_users(
        db,
        dept_where_sql=(
            "name LIKE :pat OR code = 'DELIVERY' OR dept_type = 'delivery'"
        ),
        dept_params={"pat": "%交付部%"},
    )


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

    scoped_apps = _scoped_apps(db, ctx, RmsApplication, RmsJob, Client, filters)
    active_q = _filter_applications_query(db, ctx, RmsApplication, RmsJob, Client, filters)
    active_apps = [
        a for a in active_q.all() if (a.status or "") in ACTIVE_PIPELINE_STATUSES
    ]
    hist_map = _hist_for_apps(db, [a.id for a in scoped_apps], RmsApplicationStatusHistory)

    return {
        "filters": filters,
        "demand_overview": _demand_overview(db, ctx, RmsJob, Client, filters),
        "pipeline_overview": _pipeline_overview(active_apps),
        "historical_overview": _historical_overview(scoped_apps, hist_map, filters),
        "recruiter_performance": _recruiter_performance(
            db, scoped_apps, hist_map, RmsJob, _utc_today(), filters
        ),
        "client_job_stage_summary": _client_job_stage_summary(
            db, ctx, scoped_apps, hist_map, RmsJob, Client, filters
        ),
        "lifecycle_funnel": _lifecycle_funnel(scoped_apps, hist_map, filters),
    }

