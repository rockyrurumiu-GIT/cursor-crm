"""RMS request/response schemas and status transition constants."""
from __future__ import annotations

import re
from typing import Any, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict

RECEIVE_STATUSES = frozenset({"pending", "accepted", "rejected"})
DELIVERY_REVIEW_STATUSES = frozenset({"pending", "passed", "failed"})

# Display labels — keep in sync with static/js/pages/rms-application-labels.js
APPLICATION_PROGRESS_LABELS: dict[str, str] = {
    "pending_internal_screen": "待内筛",
    "internal_screen_failed": "内筛fail",
    "pending_client_screen": "待客筛",
    "client_screen_failed": "客筛fail",
    "client_screen_duplicate": "重复",
    "scheduling_interview": "约面中",
    "interview_scheduling_failed": "约面fail",
    "pending_first_interview": "待一面",
    "first_interview_passed": "一面通过",
    "first_interview_failed": "一面fail",
    "second_interview_passed": "二面通过",
    "second_interview_failed": "二面fail",
    "second_interview_abandoned": "二面弃面",
    "final_interview_failed": "终面fail",
    "final_interview_abandoned": "终面弃面",
    "pending_offer": "待offer",
    "offer_dropped": "弃offer",
    "onboarding": "在途",
    "onboarding_lost": "在途流失",
    "hired": "已入职",
}

LEGACY_APPLICATION_STATUS_LABELS: dict[str, str] = {
    "recommended": "待内筛",
    "screening": "待客筛",
    "interview": "待一面",
    "offer": "待offer",
    "rejected": "已拒收",
    "withdrawn": "已撤回",
}

RECEIVE_STATUS_LABELS: dict[str, str] = {
    "pending": "未接收",
    "accepted": "已接收",
    "rejected": "已拒收",
}

DELIVERY_REVIEW_STATUS_LABELS: dict[str, str] = {
    "pending": "待内审",
    "passed": "内审通过",
    "failed": "内审失败",
}

JOB_PRIORITY_LABELS: dict[str, str] = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

JOB_STATUS_LABELS: dict[str, str] = {
    "open": "open",
    "closed": "closed",
    "freeze": "freeze",
}

RMS_ENUM_GROUP_FIELDS = frozenset({
    ("rms_applications", "current_stage"),
    ("rms_applications", "status"),
    ("rms_applications", "receive_status"),
    ("rms_applications", "delivery_review_status"),
    ("rms_jobs", "status"),
    ("rms_jobs", "priority"),
})

RMS_FK_GROUP_FIELDS = frozenset({
    ("rms_jobs", "client_id"),
    ("rms_jobs", "owner_user_id"),
    ("rms_applications", "client_id"),
    ("rms_applications", "job_id"),
    ("rms_applications", "candidate_id"),
    ("rms_applications", "recommended_by"),
})


def application_progress_label(status: str) -> str:
    s = (status or "").strip()
    if not s:
        return "(空)"
    return APPLICATION_PROGRESS_LABELS.get(s) or LEGACY_APPLICATION_STATUS_LABELS.get(s) or s


def resolve_rms_group_label(source_key: str, field_key: str, raw: Any) -> str:
    """Map RMS enum/code field values to display labels for dashboard group_by."""
    s = "" if raw is None else str(raw).strip()
    if not s or s == "(空)":
        return "(空)"
    if source_key == "rms_applications":
        if field_key in ("current_stage", "status"):
            return application_progress_label(s)
        if field_key == "receive_status":
            return RECEIVE_STATUS_LABELS.get(s, s)
        if field_key == "delivery_review_status":
            return DELIVERY_REVIEW_STATUS_LABELS.get(s, s)
    if source_key == "rms_jobs":
        if field_key == "priority":
            return JOB_PRIORITY_LABELS.get(s, s)
        if field_key == "status":
            return JOB_STATUS_LABELS.get(s, s)
    return s

LEGACY_STATUS_NORMALIZE: dict[str, str] = {
    "screening": "pending_client_screen",
    "interview": "pending_first_interview",
    "offer": "pending_offer",
}

APPLICATION_PROGRESS_TERMINAL = frozenset({
    "internal_screen_failed",
    "client_screen_failed",
    "client_screen_duplicate",
    "interview_scheduling_failed",
    "first_interview_failed",
    "second_interview_failed",
    "second_interview_abandoned",
    "final_interview_failed",
    "final_interview_abandoned",
    "offer_dropped",
    "onboarding_lost",
    "hired",
    "rejected",
    "withdrawn",
})

APPLICATION_TERMINAL = APPLICATION_PROGRESS_TERMINAL

ACTIVE_PIPELINE_STATUSES = frozenset({
    "pending_internal_screen",
    "pending_client_screen",
    "scheduling_interview",
    "pending_first_interview",
    "first_interview_passed",
    "second_interview_passed",
    "pending_offer",
    "onboarding",
})

# Raw DB statuses counted as 活跃推荐 on job list (includes legacy aliases).
# Excludes terminal/inactive progress: hired, onboarding, and all fail/drop statuses.
JOB_ACTIVE_RECOMMENDATION_RAW_STATUSES = frozenset({
    "recommended",
    "pending_internal_screen",
    "screening",
    "pending_client_screen",
    "scheduling_interview",
    "interview",
    "pending_first_interview",
    "first_interview_passed",
    "second_interview_passed",
    "offer",
    "pending_offer",
})

APPLICATION_PROGRESS_STATUSES = frozenset({
    "pending_internal_screen",
    "internal_screen_failed",
    "pending_client_screen",
    "client_screen_failed",
    "client_screen_duplicate",
    "scheduling_interview",
    "interview_scheduling_failed",
    "pending_first_interview",
    "first_interview_passed",
    "first_interview_failed",
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
    "final_interview_failed",
    "final_interview_abandoned",
    "pending_offer",
    "offer_dropped",
    "onboarding",
    "onboarding_lost",
    "hired",
})

# Ordered pipeline — keep values in sync with static/js/pages/rms-application-labels.js
APPLICATION_PROGRESS_ORDER: Tuple[str, ...] = (
    "pending_internal_screen",
    "internal_screen_failed",
    "pending_client_screen",
    "client_screen_failed",
    "client_screen_duplicate",
    "scheduling_interview",
    "interview_scheduling_failed",
    "pending_first_interview",
    "first_interview_passed",
    "first_interview_failed",
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
    "final_interview_failed",
    "final_interview_abandoned",
    "pending_offer",
    "offer_dropped",
    "onboarding",
    "onboarding_lost",
    "hired",
)

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending_internal_screen": {"internal_screen_failed", "pending_client_screen"},
    "pending_client_screen": {
        "client_screen_failed",
        "client_screen_duplicate",
        "scheduling_interview",
    },
    "scheduling_interview": {"interview_scheduling_failed", "pending_first_interview"},
    "pending_first_interview": {"first_interview_failed", "first_interview_passed"},
    "first_interview_passed": {
        "second_interview_failed",
        "second_interview_passed",
        "second_interview_abandoned",
    },
    "second_interview_passed": {
        "final_interview_failed",
        "pending_offer",
        "final_interview_abandoned",
    },
    "pending_offer": {"offer_dropped", "onboarding"},
    "onboarding": {"onboarding_lost", "hired"},
}

_HIRED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RMS_DATE_RE = _HIRED_AT_RE

FORBIDDEN_APPLICATION_BODY_KEYS = frozenset({
    "status",
    "client_id",
    "current_stage",
    "last_activity_at",
})

JOB_PRIORITIES = frozenset({"high", "medium", "low"})
JOB_STATUSES = frozenset({"open", "closed", "freeze"})
JOB_SALARY_CAP_MIN = 1000
JOB_SALARY_CAP_MAX = 99999

JOB_WRITABLE_STR_FIELDS = (
    "title",
    "department",
    "location",
    "job_description",
    "requirements",
    "status",
    "priority",
    "salary_cap",
    "years_required",
    "education",
    "overtime_travel",
    "interviewer",
    "note",
)


def normalize_application_status(status: str) -> str:
    s = (status or "").strip()
    if not s:
        return "recommended"
    return LEGACY_STATUS_NORMALIZE.get(s, s)


def utc_date_str() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize_rms_date(value: Any) -> str:
    """Normalize RMS date fields to YYYY-MM-DD for storage/API output."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    head = s[:10]
    if _RMS_DATE_RE.match(head):
        return head
    return s


def validate_hired_at(value: str) -> str:
    from fastapi import HTTPException

    v = (value or "").strip()
    if not v:
        raise HTTPException(status_code=400, detail="已入职状态必须填写入职时间 hired_at")
    if not _HIRED_AT_RE.match(v):
        raise HTTPException(status_code=400, detail="hired_at 格式须为 YYYY-MM-DD")
    return v


def is_pipeline_eligible_application(row: Any) -> bool:
    recv = (getattr(row, "receive_status", None) or "pending").strip()
    dr = (getattr(row, "delivery_review_status", None) or "pending").strip()
    return recv == "accepted" and dr == "passed"


def validate_status_correction_note(note: str) -> str:
    from fastapi import HTTPException

    v = (note or "").strip()
    if len(v) < 2:
        raise HTTPException(status_code=400, detail="状态修正备注至少 2 个字")
    return v


def validate_delivery_review_failed_note(note: str) -> str:
    from fastapi import HTTPException

    v = (note or "").strip()
    if len(v) < 2:
        raise HTTPException(status_code=400, detail="内审失败须填写理由")
    return v


def reject_forbidden_application_keys(body: dict) -> None:
    from fastapi import HTTPException

    if not isinstance(body, dict):
        return
    bad = sorted(FORBIDDEN_APPLICATION_BODY_KEYS & body.keys())
    if bad:
        raise HTTPException(status_code=400, detail=f"不允许的字段: {', '.join(bad)}")


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: int
    candidate_id: int
    resume_id: Optional[int] = None


class ApplicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: Optional[int] = None
    candidate_id: Optional[int] = None
    resume_id: Optional[int] = None


class ApplicationStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_status: str
    mode: Literal["transition", "correction"] = "transition"
    hired_at: str = ""
    reason: str = ""
    note: str = ""


class DeliveryReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: Literal["passed", "failed"]
    note: str = ""


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: int
    title: str = ""
    department: str = ""
    location: str = ""
    headcount: int = 1
    job_description: str = ""
    requirements: str = ""
    status: str = "open"
    priority: str = "medium"
    salary_cap: str = ""
    years_required: str = ""
    education: str = ""
    overtime_travel: str = ""
    interviewer: str = ""
    note: str = ""
    owner_user_id: int
    delivery_owner_user_id: Optional[int] = None
    sales_owner_user_id: Optional[int] = None


class JobUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: Optional[int] = None
    title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    headcount: Optional[int] = None
    job_description: Optional[str] = None
    requirements: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    salary_cap: Optional[str] = None
    years_required: Optional[str] = None
    education: Optional[str] = None
    overtime_travel: Optional[str] = None
    interviewer: Optional[str] = None
    note: Optional[str] = None
    owner_user_id: Optional[int] = None


CANDIDATE_EDUCATION_LEVELS = frozenset(
    {"重本", "统本", "专科", "硕士", "留学生", "民教网", "其他"}
)
CANDIDATE_GENDERS = frozenset({"男", "女"})
CANDIDATE_SOURCE_PRESETS = frozenset(
    {"内部RMS", "平台", "Boss", "linkedin", "猎聘", "内推", "挂靠", "外协"}
)
CANDIDATE_SOURCES = CANDIDATE_SOURCE_PRESETS | {"其他"}
CANDIDATE_MARITAL_STATUSES = frozenset({"未婚", "已婚"})

CANDIDATE_WRITABLE_STR_FIELDS = (
    "name",
    "phone",
    "email",
    "wechat",
    "email_wechat",
    "age",
    "work_years",
    "current_salary",
    "expected_salary",
    "available_date",
    "education_level",
    "school",
    "major",
    "gender",
    "marital_status",
    "current_company",
    "current_title",
    "city",
    "source",
    "tags",
)


class CandidateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    phone: str = ""
    email: str = ""
    wechat: str = ""
    email_wechat: str = ""
    age: str = ""
    work_years: str = ""
    target_job_id: Optional[int] = None
    target_client_id: Optional[int] = None
    current_salary: str = ""
    expected_salary: str = ""
    available_date: str = ""
    education_level: str = ""
    school: str = ""
    major: str = ""
    gender: str = ""
    marital_status: str = ""
    current_company: str = ""
    current_title: str = ""
    city: str = ""
    source: str = ""
    tags: str = "[]"


class CandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    wechat: Optional[str] = None
    email_wechat: Optional[str] = None
    age: Optional[str] = None
    work_years: Optional[str] = None
    target_job_id: Optional[int] = None
    target_client_id: Optional[int] = None
    current_salary: Optional[str] = None
    expected_salary: Optional[str] = None
    available_date: Optional[str] = None
    education_level: Optional[str] = None
    school: Optional[str] = None
    major: Optional[str] = None
    gender: Optional[str] = None
    marital_status: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    city: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
