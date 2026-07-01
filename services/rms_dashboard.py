"""RMS recruitment dashboard aggregation."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Type, Union

from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import (
    ACTIVE_PIPELINE_STATUSES,
    APPLICATION_PROGRESS_ORDER,
    normalize_rms_date,
)
from services import rms_scope as rms_ds

_PIPELINE_LABELS = {
    "recommended": "待内筛",
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
    "internal_screen": "recommended",
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
_ABANDONED_STAGE_LABELS = {
    "second_interview_abandoned": "二面弃面",
    "final_interview_abandoned": "终面弃面",
}

_SCHEDULING_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"scheduling_interview"})
_PENDING_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"pending_first_interview"})
_PENDING_SECOND_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"first_interview_passed"})
_PENDING_FINAL_INTERVIEW_SNAPSHOT_STATUSES = frozenset({"second_interview_passed"})
_ONBOARDING_SNAPSHOT_STATUSES = frozenset({"onboarding"})

_LOSS_METRIC_NAME_KEYS = (
    "interview_abandoned_names",
    "offer_dropped_names",
    "onboarding_lost_names",
)
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
    "pending_delivery_review_count",
    "internal_screen_passed",
    "duplicate_count",
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
    "offer_accepted_count",
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
_SCHEDULING_PASSED_STATUSES = _statuses_from("pending_first_interview")
_INTERNAL_SCREEN_PASSED_STATUSES = _statuses_from("pending_client_screen")
_FIRST_INTERVIEW_PASSED_STATUSES = _statuses_from("first_interview_passed") - frozenset({
    "first_interview_failed",
})
# 一面数历史：与一面通过双保险一致，并含 first_interview_failed
_FIRST_INTERVIEW_REACHED_STATUSES = frozenset(
    _FIRST_INTERVIEW_PASSED_STATUSES | frozenset({"first_interview_failed"})
)
_SECOND_INTERVIEW_PASSED_STATUSES = _statuses_from("second_interview_passed") - frozenset({
    "second_interview_failed",
    "second_interview_abandoned",
})
# 二面数历史：与二面通过双保险一致，并含 second_interview_failed / second_interview_abandoned
_SECOND_INTERVIEW_REACHED_STATUSES = frozenset(
    _SECOND_INTERVIEW_PASSED_STATUSES | frozenset({
        "second_interview_failed",
        "second_interview_abandoned",
    })
)
_FINAL_INTERVIEW_PASSED_STATUSES = _statuses_from("pending_offer")
# 接 offer：周期内进入在途及之后（含在途流失）；弃 offer 为 offer 阶段 fail，不算接 offer
_OFFER_PASSED_STATUSES = _statuses_from("onboarding")

# 各阶段「通过」：周期内曾到达对应节点及之后（双保险），且当前仍在该集合内；
# 改回前序节点或该阶段 fail/弃面等结果态时不计入。
_STAGE_PASSED_STATUS_SETS: Dict[str, frozenset] = {
    "internal_screen": frozenset(_INTERNAL_SCREEN_PASSED_STATUSES),
    "client_screen": frozenset(_CLIENT_SCREEN_PASSED_STATUSES),
    "scheduling": frozenset(_SCHEDULING_PASSED_STATUSES),
    "first_interview": frozenset(_FIRST_INTERVIEW_PASSED_STATUSES),
    "second_interview": frozenset(_SECOND_INTERVIEW_PASSED_STATUSES),
    "final_interview": frozenset(_FINAL_INTERVIEW_PASSED_STATUSES),
    "offer": frozenset(_OFFER_PASSED_STATUSES),
}
# 已面试/面试通过：周期内曾到达对应节点，且当前（或 date_to 快照）仍在一面结果之后；
# 误操作改回「待一面」等前置状态时不计入。
_INTERVIEWED_CURRENT_STATUSES = _statuses_from("first_interview_passed") | frozenset({
    "first_interview_failed",
})
_SECOND_INTERVIEWED_CURRENT_STATUSES = _statuses_from("second_interview_passed") | frozenset({
    "second_interview_failed",
    "second_interview_abandoned",
})


def _app_reached_and_still_in_pass_set(
    app: Any,
    histories: List[Any],
    passed_statuses: Set[str],
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_in_period(histories, passed_statuses, date_from, date_to):
        return False
    return _status_at(app, histories, snapshot_as_of) in passed_statuses


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


def _pending_delivery_review_count(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
) -> int:
    """周期内推送且快照仍为 recommended（待内筛）的推荐数。"""
    date_from, date_to = _period_bounds(filters)
    snapshot_as_of = _snapshot_as_of(filters)
    count = 0
    for app in apps:
        if not _recommended_in_period(app, date_from, date_to):
            continue
        histories = hist_map.get(app.id, [])
        if _status_at(app, histories, snapshot_as_of) == "recommended":
            count += 1
    return count


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
        histories, _FIRST_INTERVIEW_REACHED_STATUSES, date_from, date_to
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
        histories, _SECOND_INTERVIEW_REACHED_STATUSES, date_from, date_to
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


def _app_counts_as_hired(
    app: Any,
    histories: List[Any],
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    if not _app_had_transition_in_period(histories, _HIRED_STATUSES, date_from, date_to):
        return False
    return _status_at(app, histories, snapshot_as_of) in _HIRED_STATUSES


def _app_counts_as_stage_passed(
    app: Any,
    histories: List[Any],
    stage_key: str,
    pass_status: str,
    date_from: str,
    date_to: str,
    snapshot_as_of: Optional[str],
) -> bool:
    passed_statuses = _STAGE_PASSED_STATUS_SETS.get(stage_key)
    if passed_statuses is not None:
        return _app_reached_and_still_in_pass_set(
            app, histories, passed_statuses, date_from, date_to, snapshot_as_of
        )
    return _app_had_transition_to_in_period(histories, pass_status, date_from, date_to)


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
        if _app_counts_as_hired(app, histories, date_from, date_to, snapshot_as_of):
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

    _patch_scheduling_pass_rate(rows_out, apps, hist_map, filters, stage_key_field="stage")
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


def _empty_job_metrics() -> Dict[str, Any]:
    metrics: Dict[str, Any] = {key: 0 for key in _SUMMARY_METRIC_KEYS}
    for key in _LOSS_METRIC_NAME_KEYS:
        metrics[key] = []
    return metrics


def _candidate_display_name(app: Any, candidate_names: Dict[int, str]) -> str:
    cid = getattr(app, "candidate_id", None)
    if cid is not None:
        name = (candidate_names.get(int(cid)) or "").strip()
        if name:
            return name
        return f"候选人#{cid}"
    return f"投递#{getattr(app, 'id', '?')}"


def _append_unique_name(names: List[str], name: str) -> None:
    if name and name not in names:
        names.append(name)


def _abandoned_stage_labels_in_period(
    histories: List[Any],
    date_from: str,
    date_to: str,
) -> List[str]:
    labels: List[str] = []
    seen: Set[str] = set()
    for hist in histories:
        to_status = (hist.to_status or "").strip()
        if to_status not in _ABANDONED_STATUSES:
            continue
        if _has_period_filter({"date_from": date_from, "date_to": date_to}):
            if not _event_in_period(_date_only(hist.changed_at), date_from, date_to):
                continue
        label = _ABANDONED_STAGE_LABELS.get(to_status, to_status)
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _format_interview_abandoned_hint(name: str, stage_labels: List[str]) -> str:
    if not stage_labels:
        return name
    return name + " · " + "、".join(stage_labels)


def _append_unique_interview_abandoned_hint(
    names: List[str],
    name: str,
    stage_labels: List[str],
) -> None:
    hint = _format_interview_abandoned_hint(name, stage_labels)
    if hint and hint not in names:
        names.append(hint)


def _metrics_for_apps(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
    candidate_names: Optional[Dict[int, str]] = None,
) -> Dict[str, Any]:
    date_from, date_to = _period_bounds(filters)
    snapshot_as_of = _snapshot_as_of(filters)
    metrics = _empty_job_metrics()
    names_by_id = candidate_names or {}

    for app in apps:
        histories = hist_map.get(app.id, [])
        status_snapshot = _status_at(app, histories, snapshot_as_of)
        if _recommended_in_period(app, date_from, date_to):
            metrics["pushed_resume_count"] += 1
            if status_snapshot == "recommended":
                metrics["pending_delivery_review_count"] += 1
        if _app_counts_as_stage_passed(
            app,
            histories,
            "internal_screen",
            "pending_client_screen",
            date_from,
            date_to,
            snapshot_as_of,
        ):
            metrics["internal_screen_passed"] += 1
        if _app_had_transition_to_in_period(
            histories, "client_screen_duplicate", date_from, date_to
        ):
            metrics["duplicate_count"] += 1
        if status_snapshot == "pending_client_screen":
            metrics["pending_client_screen"] += 1
        if status_snapshot in _SCHEDULING_INTERVIEW_SNAPSHOT_STATUSES:
            metrics["scheduling_interview_count"] += 1
        if _app_counts_as_stage_passed(
            app,
            histories,
            "client_screen",
            "scheduling_interview",
            date_from,
            date_to,
            snapshot_as_of,
        ):
            metrics["client_screen_passed"] += 1
        if _app_had_transition_in_period(histories, _ABANDONED_STATUSES, date_from, date_to):
            metrics["interview_abandoned"] += 1
            _append_unique_interview_abandoned_hint(
                metrics["interview_abandoned_names"],
                _candidate_display_name(app, names_by_id),
                _abandoned_stage_labels_in_period(histories, date_from, date_to),
            )
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
        if _app_counts_as_stage_passed(
            app,
            histories,
            "offer",
            "onboarding",
            date_from,
            date_to,
            snapshot_as_of,
        ):
            metrics["offer_accepted_count"] += 1
        if _app_had_transition_in_period(
            histories, _OFFER_DROPPED_STATUSES, date_from, date_to
        ):
            metrics["offer_dropped_count"] += 1
            _append_unique_name(
                metrics["offer_dropped_names"],
                _candidate_display_name(app, names_by_id),
            )
        if status_snapshot in _ONBOARDING_SNAPSHOT_STATUSES:
            metrics["onboarding_count"] += 1
        if _app_had_transition_in_period(
            histories, _ONBOARDING_LOST_STATUSES, date_from, date_to
        ):
            metrics["onboarding_lost_count"] += 1
            _append_unique_name(
                metrics["onboarding_lost_names"],
                _candidate_display_name(app, names_by_id),
            )
        if _app_counts_as_hired(app, histories, date_from, date_to, snapshot_as_of):
            metrics["hired_count"] += 1
        if status_snapshot == "hired" and not getattr(app, "converted_to_roster_entry_id", None):
            metrics["pending_roster_conversion_count"] += 1
    return metrics


_JOB_STAGE_RATE_SPECS = (
    ("duplicate_count", "duplicate_count_rate", "pushed_resume_count"),
    ("client_screen_passed", "client_screen_passed_rate", "internal_screen_passed"),
    ("interview_abandoned", "interview_abandoned_rate", "internal_screen_passed"),
    ("first_interview_passed_count", "first_interview_passed_rate", "first_interview_count"),
    ("second_interview_passed_count", "second_interview_passed_rate", "second_interview_count"),
    ("interview_passed", "interview_passed_rate", "interviewed"),
    ("offer_accepted_count", "offer_accepted_count_rate", "second_interview_passed_count"),
    ("offer_dropped_count", "offer_dropped_count_rate", "second_interview_passed_count"),
    ("onboarding_lost_count", "onboarding_lost_count_rate", "onboarding_count"),
)


def _internal_screen_pass_rate_parts(metrics: Dict[str, Any]) -> tuple[int, int, str]:
    """内筛通过率 = 内筛通过 / (推送简历数 - 待内筛)。"""
    numerator = int(metrics.get("internal_screen_passed") or 0)
    denominator = int(metrics.get("pushed_resume_count") or 0) - int(
        metrics.get("pending_delivery_review_count") or 0
    )
    return numerator, denominator, _rate(numerator, denominator, decimals=0)


def _scheduling_pass_rate_parts(metrics: Dict[str, Any]) -> tuple[int, int, str]:
    """约面成功率 = (待面试 + 一面数) / (客筛通过 - 约面中)。"""
    numerator = int(metrics.get("pending_interview") or 0) + int(
        metrics.get("first_interview_count") or 0
    )
    denominator = int(metrics.get("client_screen_passed") or 0) - int(
        metrics.get("scheduling_interview_count") or 0
    )
    return numerator, denominator, _rate(numerator, denominator, decimals=0)


def _patch_scheduling_pass_rate(
    stage_rows: List[Dict[str, Any]],
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
    *,
    stage_key_field: str = "stage",
) -> None:
    _, denominator, rate = _scheduling_pass_rate_parts(
        _metrics_for_apps(apps, hist_map, filters)
    )
    for row in stage_rows:
        if row.get(stage_key_field) != "scheduling":
            continue
        row["pass_rate"] = rate
        row["denominator"] = denominator
        if "pass_rate_value" in row:
            row["pass_rate_value"] = _parse_rate_value(rate)
        if "processed" in row:
            row["processed"] = denominator
        break


def _attach_job_stage_rates(metrics: Dict[str, int]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(metrics)
    for num_key, rate_key, denom_key in _JOB_STAGE_RATE_SPECS:
        out[rate_key] = _rate(
            int(metrics.get(num_key, 0)),
            int(metrics.get(denom_key, 0)),
            decimals=0,
        )
    _, internal_denom, out["internal_screen_passed_rate"] = _internal_screen_pass_rate_parts(
        out
    )
    out["internal_screen_passed_denom"] = internal_denom
    _, _, out["scheduling_passed_rate"] = _scheduling_pass_rate_parts(out)
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
    ("hired_summary", "入职"),
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
        if stage_key == "internal_screen":
            pending = _pending_delivery_review_count(apps, hist_map, filters)
        else:
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

    _patch_scheduling_pass_rate(rows, apps, hist_map, filters, stage_key_field="key")
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

    candidate_ids = {
        int(app.candidate_id)
        for app in scoped_apps
        if getattr(app, "candidate_id", None) is not None
    }
    candidate_names: Dict[int, str] = {}
    if candidate_ids:
        from sqlalchemy import text

        ids_sql = ",".join(str(i) for i in sorted(candidate_ids))
        for cid, name in db.execute(
            text(f"SELECT id, name FROM rms_candidates WHERE id IN ({ids_sql})")
        ):
            candidate_names[int(cid)] = (name or "").strip()

    rows: List[Dict[str, Any]] = []
    total = _empty_job_metrics()
    total_headcount = 0
    for job in sorted(jobs, key=lambda j: int(j.id)):
        metrics = _metrics_for_apps(
            apps_by_job.get(int(job.id), []),
            hist_map,
            filters,
            candidate_names,
        )
        cid = int(job.client_id) if job.client_id is not None else None
        headcount = int(job.headcount or 0) if (job.status or "").strip() == "open" else 0
        total_headcount += headcount
        row = {
            "job_id": int(job.id),
            "job_title": (job.title or "").strip() or f"岗位#{job.id}",
            "client_id": cid,
            "client_name": client_names.get(cid, "") if cid is not None else "",
            "headcount": headcount,
            "location": (job.location or "").strip(),
            **_attach_job_stage_rates(metrics),
        }
        rows.append(row)
        for key in _SUMMARY_METRIC_KEYS:
            total[key] += metrics[key]
        for key in _LOSS_METRIC_NAME_KEYS:
            for name in metrics[key]:
                _append_unique_name(total[key], name)

    return {
        "period_label": _period_label(filters),
        "rows": rows,
        "total": {**_attach_job_stage_rates(total), "headcount": total_headcount},
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
            "name LIKE :pat OR code = 'DELIVERY' OR dept_type IN ('delivery', 'business')"
        ),
        dept_params={"pat": "%交付部%"},
    )


PIPELINE_ACTIVE_BUCKET_SPECS: Tuple[Tuple[str, str], ...] = (
    ("active_recommendation", "活跃推荐数"),
    ("pending_delivery_review", "待内筛"),
    ("pending_client_screen", "待客筛"),
    ("pending_first_interview", "待一面"),
    ("pending_second_interview", "待二面"),
    ("pending_final_interview", "待终面"),
    ("pending_offer", "待offer"),
    ("onboarding", "在途"),
)

PIPELINE_LOSS_BUCKET_SPECS: Tuple[Tuple[str, str], ...] = (
    ("historical_resume", "历史简历数"),
    ("internal_screen_failed", "内筛fail"),
    ("client_screen_failed", "客筛fail"),
    ("duplicate", "重复"),
    ("first_interview_failed", "一面fail"),
    ("second_interview_failed", "二面fail"),
    ("final_interview_failed", "终面fail"),
    ("offer_dropped", "弃offer"),
    ("onboarding_lost", "在途流失"),
)


def _app_matches_pipeline_active_bucket(
    app: Any,
    histories: List[Any],
    snapshot_as_of: str,
    bucket_key: str,
) -> bool:
    status = _status_at(app, histories, snapshot_as_of)
    if bucket_key == "active_recommendation":
        return status in ACTIVE_PIPELINE_STATUSES
    if bucket_key == "pending_delivery_review":
        return status == "recommended"
    if bucket_key == "pending_client_screen":
        return status == "pending_client_screen"
    if bucket_key == "pending_first_interview":
        return status == "pending_first_interview"
    if bucket_key == "pending_second_interview":
        return status == "first_interview_passed"
    if bucket_key == "pending_final_interview":
        return status == "second_interview_passed"
    if bucket_key == "pending_offer":
        return status == "pending_offer"
    if bucket_key == "onboarding":
        return status == "onboarding"
    return False


def _app_matches_pipeline_loss_bucket(
    app: Any,
    histories: List[Any],
    date_from: str,
    date_to: str,
    bucket_key: str,
) -> bool:
    if bucket_key == "historical_resume":
        return _recommended_in_period(app, date_from, date_to)
    if bucket_key == "internal_screen_failed":
        return _app_had_transition_in_period(
            histories, {"internal_screen_failed"}, date_from, date_to
        )
    if bucket_key == "client_screen_failed":
        return _app_had_transition_in_period(
            histories, {"client_screen_failed"}, date_from, date_to
        )
    if bucket_key == "duplicate":
        return _app_had_transition_to_in_period(
            histories, "client_screen_duplicate", date_from, date_to
        )
    if bucket_key == "first_interview_failed":
        return _app_had_transition_in_period(
            histories, {"first_interview_failed"}, date_from, date_to
        )
    if bucket_key == "second_interview_failed":
        return _app_had_transition_in_period(
            histories, {"second_interview_failed"}, date_from, date_to
        )
    if bucket_key == "final_interview_failed":
        return _app_had_transition_in_period(
            histories, {"final_interview_failed"}, date_from, date_to
        )
    if bucket_key == "offer_dropped":
        return _app_had_transition_in_period(
            histories, _OFFER_DROPPED_STATUSES, date_from, date_to
        )
    if bucket_key == "onboarding_lost":
        return _app_had_transition_in_period(
            histories, _ONBOARDING_LOST_STATUSES, date_from, date_to
        )
    return False


def _is_client_secondary_field(field: str) -> bool:
    return (field or "").strip() in ("client", "client_id")


def _is_job_secondary_field(field: str) -> bool:
    return (field or "").strip() in ("job", "job_id")


def compute_pipeline_grouped_series(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
    mode: str,
    secondary_field: str,
    db: Session,
    Client: Type[Any],
    *,
    RmsJob: Optional[Type[Any]] = None,
    hide_empty: bool = False,
) -> tuple[List[str], List[str], Dict[str, Dict[str, float]]]:
    """Grouped pipeline buckets (active snapshot / loss historical) by secondary axis."""
    specs = (
        PIPELINE_ACTIVE_BUCKET_SPECS
        if mode == "active"
        else PIPELINE_LOSS_BUCKET_SPECS
    )
    snapshot_as_of = _snapshot_as_of(filters)
    date_from, date_to = _period_bounds(filters)

    groups: Dict[Any, List[Any]] = defaultdict(list)
    for app in apps:
        if _is_client_secondary_field(secondary_field):
            sk = getattr(app, "client_id", None)
        else:
            sk = getattr(app, secondary_field, None)
        sk = sk if sk is not None else "(空)"
        groups[sk].append(app)

    name_map: Dict[int, str] = {}
    if _is_client_secondary_field(secondary_field) and Client is not None:
        cids = []
        for key in groups:
            if key == "(空)":
                continue
            try:
                cids.append(int(key))
            except (TypeError, ValueError):
                pass
        if cids:
            for cid, cname in (
                db.query(Client.id, Client.name).filter(Client.id.in_(cids)).all()
            ):
                name_map[int(cid)] = (cname or "").strip() or f"客户#{cid}"

    job_name_map: Dict[int, str] = {}
    if _is_job_secondary_field(secondary_field) and RmsJob is not None:
        jids = []
        for key in groups:
            if key == "(空)":
                continue
            try:
                jids.append(int(key))
            except (TypeError, ValueError):
                pass
        if jids:
            for jid, title in (
                db.query(RmsJob.id, RmsJob.title).filter(RmsJob.id.in_(jids)).all()
            ):
                job_name_map[int(jid)] = (title or "").strip() or f"岗位#{jid}"

    def _secondary_label(raw_key: Any) -> str:
        if _is_client_secondary_field(secondary_field):
            if raw_key == "(空)":
                return "(空)"
            try:
                cid = int(raw_key)
            except (TypeError, ValueError):
                return str(raw_key)
            return name_map.get(cid, f"客户#{cid}")
        if _is_job_secondary_field(secondary_field):
            if raw_key == "(空)":
                return "(空)"
            try:
                jid = int(raw_key)
            except (TypeError, ValueError):
                return str(raw_key)
            return job_name_map.get(jid, f"岗位#{jid}")
        return str(raw_key) if raw_key != "(空)" else "(空)"

    secondary_raw_keys = sorted(groups.keys(), key=lambda k: _secondary_label(k))
    secondary_labels = [_secondary_label(k) for k in secondary_raw_keys]
    primary_labels = [label for _, label in specs]
    matrix: Dict[str, Dict[str, float]] = {}

    for bucket_key, bucket_label in specs:
        row: Dict[str, float] = {}
        for raw_sk, sec_label in zip(secondary_raw_keys, secondary_labels):
            count = 0
            for app in groups[raw_sk]:
                histories = hist_map.get(app.id, [])
                if mode == "active":
                    matched = _app_matches_pipeline_active_bucket(
                        app, histories, snapshot_as_of, bucket_key
                    )
                else:
                    matched = _app_matches_pipeline_loss_bucket(
                        app, histories, date_from, date_to, bucket_key
                    )
                if matched:
                    count += 1
            row[sec_label] = float(count)
        if hide_empty and not any(row.get(sl, 0) for sl in secondary_labels):
            continue
        matrix[bucket_label] = row

    if hide_empty:
        primary_labels = [pl for pl in primary_labels if pl in matrix]
    return primary_labels, secondary_labels, matrix


def _pipeline_dialysis_grouped(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
    db: Session,
    Client: Type[Any],
) -> Dict[str, Any]:
    """Pipeline dialysis grouped by client — active snapshot + loss historical buckets."""

    def _pack(mode: str) -> Dict[str, Any]:
        primary_labels, secondary_labels, matrix = compute_pipeline_grouped_series(
            apps,
            hist_map,
            filters,
            mode,
            "client",
            db,
            Client,
            hide_empty=False,
        )
        data_rows: List[Dict[str, Any]] = []
        for pl in primary_labels:
            row: Dict[str, Any] = {"label": pl}
            for sl in secondary_labels:
                row[sl] = matrix.get(pl, {}).get(sl, 0.0)
            data_rows.append(row)
        return {"keys": secondary_labels, "data": data_rows}

    return {"active": _pack("active"), "loss": _pack("loss")}


LINE1_SNAPSHOT_STATUS_ORDER: Tuple[str, ...] = tuple(_PIPELINE_LABELS.keys())

LINE1_HISTORICAL_STAGE_LABELS: Tuple[Tuple[str, str], ...] = (
    ("internal_screen", "内筛通过"),
    ("client_screen", "客筛通过"),
    ("scheduling", "约面成功"),
    ("first_interview", "一面通过"),
    ("second_interview", "二面通过"),
    ("final_interview", "终面通过"),
    ("offer", "接offer"),
)

LINE1_LABEL_LIFECYCLE_KEYS: Dict[str, str] = {
    label: key for key, label in LINE1_HISTORICAL_STAGE_LABELS
}
LINE1_LABEL_LIFECYCLE_KEYS["已入职"] = "hired_summary"

# Job-stage table rates only where columns align; 终面/接offer use lifecycle 五率.
LINE1_LABEL_JOB_STAGE_RATE_KEYS: Dict[str, str] = {
    "内筛通过": "internal_screen_passed_rate",
    "客筛通过": "client_screen_passed_rate",
    "约面成功": "scheduling_passed_rate",
    "一面通过": "first_interview_passed_rate",
    "二面通过": "second_interview_passed_rate",
}


def line1_pass_rates_for_labels(
    labels: List[str],
    job_stage_total: Optional[Dict[str, Any]] = None,
    lifecycle_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Optional[str]]:
    total = job_stage_total or {}
    by_key = {str(r.get("key") or ""): r for r in (lifecycle_rows or [])}
    out: List[Optional[str]] = []
    for label in labels:
        lab = str(label or "").strip()
        lc_key = LINE1_LABEL_LIFECYCLE_KEYS.get(lab)
        if lc_key:
            lc_row = by_key.get(lc_key)
            if lc_row:
                lc_rate = lc_row.get("pass_rate")
                if lc_rate is not None and str(lc_rate).strip() not in ("", "—"):
                    out.append(str(lc_rate))
                    continue
        rate_key = LINE1_LABEL_JOB_STAGE_RATE_KEYS.get(lab)
        if not rate_key:
            out.append(None)
            continue
        rate = total.get(rate_key)
        if rate is None or str(rate).strip() in ("", "—"):
            out.append(None)
        else:
            out.append(str(rate))
    return out


def dashboard_period_label(filters: Dict[str, Any]) -> str:
    """Human-readable dashboard period for line1 range pill; 全量 → 全部."""
    label = _period_label(filters)
    return "全部" if label == "全量" else label


def compute_line1_axis_series(
    apps: List[Any],
    hist_map: Dict[int, List[Any]],
    filters: Dict[str, Any],
    mode: str,
    *,
    hide_empty: bool = False,
) -> tuple[List[str], List[float]]:
    """Line1 x-axis buckets for snapshot / historical modes."""
    if mode == "snapshot":
        snapshot_as_of = _snapshot_as_of(filters)
        counts = {status: 0 for status in LINE1_SNAPSHOT_STATUS_ORDER}
        for app in apps:
            histories = hist_map.get(app.id, [])
            status = _status_at(app, histories, snapshot_as_of)
            if status in counts:
                counts[status] += 1
        labels = [_PIPELINE_LABELS[s] for s in LINE1_SNAPSHOT_STATUS_ORDER]
        values = [float(counts[s]) for s in LINE1_SNAPSHOT_STATUS_ORDER]
    elif mode == "historical":
        date_from, date_to = _period_bounds(filters)
        snapshot_as_of = _snapshot_as_of(filters)
        labels = [label for _, label in LINE1_HISTORICAL_STAGE_LABELS] + ["已入职"]
        value_map = {label: 0.0 for label in labels}
        for app in apps:
            histories = hist_map.get(app.id, [])
            for stage_key, label in LINE1_HISTORICAL_STAGE_LABELS:
                pass_status = _STAGE_PASS[stage_key]
                if _app_counts_as_stage_passed(
                    app,
                    histories,
                    stage_key,
                    pass_status,
                    date_from,
                    date_to,
                    snapshot_as_of,
                ):
                    value_map[label] += 1.0
            if _app_counts_as_hired(app, histories, date_from, date_to, snapshot_as_of):
                value_map["已入职"] += 1.0
        values = [value_map[label] for label in labels]
    else:
        return [], []

    if hide_empty:
        pairs = [(label, val) for label, val in zip(labels, values) if val]
        labels = [p[0] for p in pairs]
        values = [p[1] for p in pairs]
    return labels, values


def parse_dashboard_filter_params(
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
    filters: Dict[str, Any] = {
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
    return {k: v for k, v in filters.items() if v is not None and v != "" and v != []}


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
        "pipeline_dialysis": _pipeline_dialysis_grouped(
            scoped_apps, hist_map, filters, db, Client
        ),
    }

