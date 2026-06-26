"""RMS applications business logic (Phase 2)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Type

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth.service import AuthContext
from schemas.rms import (
    ALLOWED_TRANSITIONS,
    APPLICATION_PROGRESS_STATUSES,
    APPLICATION_TERMINAL,
    is_pipeline_eligible_application,
    normalize_application_status,
    normalize_rms_date,
    utc_date_str,
    format_interview_schedule_display,
    validate_delivery_review_failed_note,
    validate_hired_at,
    validate_status_correction_note,
    validate_correction_backward,
    resolve_transition_history_note,
)
from services import rms_scope as rms_ds
from services.rms_resumes import MAX_RESUME_BYTES

PARSE_DRAFT_ALLOWED_SUFFIXES = frozenset({".pdf", ".txt", ".rtf"})
PARSE_DRAFT_WORD_SUFFIXES = frozenset({".doc", ".docx"})
PARSE_DRAFT_TEXT_MAX = 2000
_WORD_UNSUPPORTED_MSG = "Word 文档暂不支持自动解析，请手动填写或上传 PDF/TXT"

_CANDIDATE_REPORT_REQUIRED = (
    ("recommendation_note", "推荐评语"),
    ("current_salary", "当前薪资"),
    ("expected_salary", "期望薪资"),
    ("name", "姓名"),
    ("age", "年龄"),
    ("work_years", "年限"),
    ("phone", "手机号"),
    ("email_wechat", "邮箱/微信"),
    ("available_date", "到岗时间"),
    ("education_level", "学历"),
    ("source", "来源"),
    ("school", "学校"),
    ("major", "专业"),
    ("gender", "性别"),
    ("marital_status", "婚姻状况"),
)

_EXISTING_CANDIDATE_REPORT_REQUIRED = (
    ("city", "城市"),
    ("current_salary", "当前薪资"),
    ("expected_salary", "期望薪资"),
    ("name", "姓名"),
    ("age", "年龄"),
    ("work_years", "年限"),
    ("phone", "手机号"),
    ("email_wechat", "邮箱/微信"),
    ("available_date", "到岗时间"),
    ("education_level", "学历"),
    ("source", "来源"),
    ("school", "学校"),
    ("major", "专业"),
    ("gender", "性别"),
    ("marital_status", "婚姻状况"),
)

_RE_PHONE = re.compile(r"1[3-9]\d{9}")
_RE_PHONE_LABEL = re.compile(
    r"(?:手机|电话|联系电话|mobile|tel)\s*[:：]?\s*([0-9][0-9\s\-()]{10,24})",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RE_NAME = re.compile(
    r"姓名\s*[:：]\s*([^\n\r:：|｜,，;；\d]{2,20}?)"
    r"(?=(?:\s*(?:电话|手机|mobile|tel|email|邮箱|微信|性别|年龄|工作年限|年限)\s*[:：])"
    r"|[\s,，;；|｜]|$)",
    re.IGNORECASE,
)
_RE_NAME_FIELD_STOP = (
    r"(?=(?:\s*(?:电话|手机|mobile|tel|email|邮箱|微信|性别|年龄|工作年限|年限)\s*[:：])"
    r"|[\s,，;；|｜]|$)"
)
_RE_NAME_LABEL_INLINE = re.compile(
    r"姓\s*名\s*[:：]\s*"
    r"([^\n\r:：|｜,，;；\d]{1,24}?)"
    + _RE_NAME_FIELD_STOP,
    re.IGNORECASE | re.DOTALL,
)
_RE_NAME_LABEL_NEXT_LINE = re.compile(
    r"姓\s*名\s*[:：]?\s*\n\s*"
    r"([^\n\r:：|｜,，;；\d]{2,24}?)"
    + _RE_NAME_FIELD_STOP,
    re.IGNORECASE,
)
_RE_NAME_HEADER_STANDALONE = re.compile(r"^[\u4e00-\u9fa5·]{2,4}$")
_RE_RESUME_CONTEXT_NEAR_NAME = re.compile(
    r"(?:"
    r"电\s*话|手\s*机|mobile|tel|"
    r"学\s*历|毕业院校|院\s*校|专\s*业|"
    r"个人信息|个人资料|基本信息|"
    r"性\s*别|年\s*龄"
    r")\s*[:：]?|"
    r"1[3-9]\d{9}|"
    r"(?:男|女).*(?:\d{1,2}岁|1[3-9]\d{9})|"
    r"(?:\d{1,2}岁|1[3-9]\d{9}).*(?:男|女)",
    re.IGNORECASE,
)
_RE_AGE = re.compile(r"年龄\s*[:：]\s*(\d{1,2})")
_RE_AGE_PROFILE = re.compile(r"(?:男|女)\s*[|｜]\s*(\d{1,2})\s*岁")
_RE_AGE_PROFILE_BARE = re.compile(r"(?:男|女)\s*[|｜]\s*(\d{1,2})(?:\s*[|｜]|$)")
_RE_AGE_PIPE = re.compile(r"[|｜]\s*(\d{1,2})\s*岁\s*[|｜]")
_RE_AGE_GENDER_NEAR = re.compile(r"(?:男|女)[^|\n]{0,20}(\d{1,2})\s*岁")
_RE_AGE_LOOSE = re.compile(r"(?<![0-9])(\d{1,2})\s*岁(?!\s*(?:工作|以上)?经验)")
_RE_GENDER_PROFILE = re.compile(r"(?:^|[|｜]\s*)(男|女)(?:\s*[|｜])")
_RE_NAME_STANDALONE = re.compile(r"^[\u4e00-\u9fa5·]{2,6}$")
_RE_NAME_CHARS = re.compile(r"^[\u4e00-\u9fa5·]+$")
_NON_PERSON_NAME_EXACT = frozenset({
    "电话",
    "手机",
    "联系方式",
    "个人简历",
    "个人资料",
    "个人履历",
    "简历",
    "简历资料",
    "基本信息",
    "基本资料",
    "个人信息",
    "个人介绍",
    "求职意向",
    "教育经历",
    "工作经历",
    "项目经历",
    "自我评价",
    "技能",
    "证书",
    "测试",
    "效果",
    "相机",
})
_PLACE_NAME_EXACT = frozenset({
    "西安",
    "北京",
    "上海",
    "深圳",
    "广州",
    "杭州",
    "南京",
    "苏州",
    "成都",
    "重庆",
    "武汉",
    "长沙",
    "郑州",
    "天津",
    "青岛",
    "合肥",
    "厦门",
    "宁波",
    "无锡",
    "常州",
    "东莞",
    "佛山",
})
_RE_NAME_BRACKETS = re.compile(r"[\[\]【】（）()《》〈〉]")
_RE_NAME_GENDER_AGE_LINE = re.compile(
    r"^([\u4e00-\u9fa5·]{2,4})\s*(?:男|女)\s*[|｜]?\s*\d{1,2}\s*(?:岁)?"
)
_RE_ADMIN_PLACE_SUFFIX = re.compile(r"^[\u4e00-\u9fa5]{1,3}[省市区县]$")
_FILENAME_ROLE_MARKERS = (
    "开发",
    "测试",
    "产品",
    "经理",
    "工程师",
    "运维",
    "算法",
    "安卓",
    "Android",
    "iOS",
    "Java",
    "Python",
    "C++",
    "前端",
    "后端",
    "设计",
)
_FILENAME_NON_PERSON_EXACT = frozenset({
    "本科",
    "大专",
    "硕士",
    "博士",
    "研究生",
    "统本",
    "全日制",
    "非全日制",
})
_PROVINCE_NAME_EXACT = frozenset({
    "云南",
    "贵州",
    "四川",
    "陕西",
    "河南",
    "河北",
    "山东",
    "山西",
    "广东",
    "广西",
    "湖南",
    "湖北",
    "江苏",
    "浙江",
    "福建",
    "江西",
    "安徽",
    "甘肃",
    "青海",
    "海南",
    "辽宁",
    "吉林",
    "黑龙江",
    "内蒙古",
    "新疆",
    "西藏",
    "宁夏",
})
_DEMOGRAPHIC_NAME_EXACT = frozenset({
    "汉族",
    "回族",
    "满族",
    "蒙古族",
    "藏族",
    "维吾尔族",
    "壮族",
    "苗族",
    "土家族",
    "彝族",
    "朝鲜族",
})
_SECTION_HEADING_NAME_EXACT = frozenset({
    "个人优势",
    "专业技能",
    "工作经历",
    "项目经历",
    "教育经历",
    "教育背景",
    "求职信息",
    "联系方式",
    "荣誉奖励",
    "技能证书",
})


@dataclass(frozen=True)
class _NameCandidate:
    value: str
    source: str
    line_index: int
    score: int
    reason: str


_INSTITUTION_NAME_MARKERS = (
    "大学",
    "学院",
    "学校",
    "中学",
    "公司",
    "科技",
    "技术",
    "集团",
    "有限公司",
    "中心",
    "部门",
)
_RE_PROFILE_LINE = re.compile(
    r"(?:男|女).*(?:\d{1,2}岁|1[3-9]\d{9})|"
    r"(?:\d{1,2}岁|1[3-9]\d{9}).*(?:男|女)|"
    r"^(?:男|女)\s*[|｜]\s*\d{1,2}(?:\s*[|｜]|$)",
    re.MULTILINE,
)
_NAME_HEADER_SKIP = frozenset({
    "个人信息",
    "个人资料",
    "个人履历",
    "个人介绍",
    "基本资料",
    "基本信息",
    "联系方式",
    "个人简历",
    "简历",
    "简历资料",
    "电话",
    "手机",
    "求职意向",
    "自我评价",
    "工作经历",
    "工作经验",
    "教育经历",
    "教育背景",
    "项目经历",
    "技能",
    "证书",
    "测试",
    "效果",
    "相机",
})
_SPLIT_SECTION_HEADING_TARGETS = _SECTION_HEADING_NAME_EXACT | _NAME_HEADER_SKIP
_RE_WORK_YEARS_LABEL = re.compile(
    r"工作年限\s*[:：]\s*(\d+\s*(?:年(?:以上)?)?)"
)
_RE_WORK_YEARS_EXPERIENCE = re.compile(
    r"(?<![0-9])(\d+\s*年(?:以上)?)\s*(?:工作)?经验"
)
_DATE_TOKEN = r"(?:\d{4}[./]\d{1,2}|\d{4}年\d{1,2}月?)"
_END_TOKEN = rf"(?:至今|现在|present|current|{_DATE_TOKEN})"
WORK_PERIOD_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:[-—–~至]\s*)?(?P<end>{_END_TOKEN})",
    re.IGNORECASE,
)
_WORK_SECTION_START = re.compile(
    r"^(?:工作经历|工作经验|项目经历|实习经历|自我描述)\s*$"
)
_WORK_SECTION_STOP = re.compile(
    r"^(?:教育(?:背景|经历)|工作经历|工作经验|项目经历|实习经历|自我描述|"
    r"专业技能|自我评价|毕业论文|毕业设计)\s*$"
)
_RE_CURRENT_SALARY = re.compile(r"(?:当前薪资|目前薪资|现薪资)\s*[:：]\s*([^\n\r]{1,40})")
_RE_EXPECTED_SALARY = re.compile(r"(?:期望薪资|期望工资|期望薪酬)\s*[:：]\s*([^\n\r]{1,40})")
_RE_EDUCATION = re.compile(r"(博士研究生|博士|硕士研究生|硕士|本科|大专|专科|高中|中专|MBA|EMBA)")
_RE_SCHOOL = re.compile(r"(?:毕业院校|学校|院校)\s*[:：]\s*([^\n\r]{2,40})")
_RE_MAJOR = re.compile(r"专业\s*[:：]\s*([^\n\r]{2,40})")
_RE_GENDER = re.compile(r"性别\s*[:：]\s*(男|女)")

SCHOOL_ENTITY_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z](?:[\u4e00-\u9fa5A-Za-z0-9·\s]{0,38}[\u4e00-\u9fa5A-Za-z0-9·])?(?:大学|学院|学校))"
)
_EDU_BLOCK_START = re.compile(r"^教育\s*(?:背景|经历)\s*[:：]?\s*$")
_EDU_BLOCK_STOP = re.compile(
    r"^(?:工作经历|项目经历|专业技能|自我评价|毕业论文|毕业设计)"
)
_DATE_RANGE_RE = re.compile(
    r"\d{4}[./年]\d{1,2}\s*[-—–~至]+\s*\d{4}[./年]\d{1,2}"
)
_YEAR_ONLY_RANGE_RE = re.compile(r"\d{4}\s*[-—–~至]+\s*\d{4}")
_DEGREE_INLINE = re.compile(
    r"[|｜]\s*(博士研究生|博士|硕士研究生|硕士|本科|大专|专科|学士)"
)
_SKILL_LINE = re.compile(r"^(?:\d+[.、)]\s*)?(?:熟悉|精通|掌握|负责|参与|具有|具备)")
_DEGREE_IN_PARENS = re.compile(r"[（(]([^）)]+)[）)]")
_DEGREE_ONLY_LINE = re.compile(
    r"^(?:博士研究生|博士|硕士研究生|硕士|本科|大专|专科|学士)\s*$"
)
_FIELD_LABEL_SPLIT = re.compile(
    r"(?:电话|手机|mobile|tel|email|邮箱|微信|性别|年龄|工作年限|年限)\s*[:：]?",
    re.IGNORECASE,
)
_FIELD_BOUNDARY = "\uE000"

_RE_CJK = re.compile(r"[\u4e00-\u9fff]")
_RE_TRACKING_LINE = re.compile(r"^[A-Za-z0-9\-]{20,}$")
_RE_WATERMARK_LINE = re.compile(r"^(?:试用水印|水印)\s*$")


def _collapse_chinese_spaces(text: str) -> str:
    src = text or ""
    protected = re.sub(
        r"(?<=[\u4e00-\u9fa5])\s*(?=(?:电话|手机|邮箱|微信|性别|年龄|email|mobile|tel)\s*[:：])",
        _FIELD_BOUNDARY,
        src,
        flags=re.IGNORECASE,
    )
    collapsed = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", protected)
    return collapsed.replace(_FIELD_BOUNDARY, " ")


def _normalize_resume_line(line: str) -> str:
    return _collapse_chinese_spaces(re.sub(r"[ \t]+", " ", (line or "").strip()))


def _normalize_resume_digits(text: str) -> str:
    return (text or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def _normalize_resume_text(text: str) -> str:
    normalized = _normalize_resume_digits(text)
    return "\n".join(_normalize_resume_line(line) for line in normalized.splitlines())


def _normalize_school_name(name: str) -> str:
    val = _collapse_chinese_spaces(re.sub(r"\s+", "", (name or "").strip()))
    return re.sub(r"^[\d.\-/年月至—–~ ]+", "", val)


def _search_school_entity(text: str) -> Optional[re.Match[str]]:
    if not text:
        return None
    normalized = _collapse_chinese_spaces(text.strip())
    match = SCHOOL_ENTITY_RE.search(normalized)
    if match:
        return match
    compact = re.sub(r"\s+", "", text)
    return SCHOOL_ENTITY_RE.search(compact)


def application_to_dict(row: Any) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "id": row.id,
        "job_id": row.job_id,
        "candidate_id": row.candidate_id,
        "client_id": row.client_id,
        "resume_id": row.resume_id,
        "status": row.status or "",
        "recommended_by": row.recommended_by,
        "recommended_at": normalize_rms_date(row.recommended_at),
        "current_stage": row.current_stage or "",
        "last_activity_at": normalize_rms_date(row.last_activity_at),
        "created_at": normalize_rms_date(row.created_at),
        "updated_at": normalize_rms_date(row.updated_at),
        "receive_status": getattr(row, "receive_status", None) or "pending",
        "delivery_review_status": getattr(row, "delivery_review_status", None) or "pending",
        "hired_at": normalize_rms_date(getattr(row, "hired_at", None)),
        "converted_to_roster_entry_id": getattr(row, "converted_to_roster_entry_id", None),
        "converted_to_roster_at": normalize_rms_date(getattr(row, "converted_to_roster_at", None)),
        "converted_to_roster_by": getattr(row, "converted_to_roster_by", None),
        "can_submit_offer_approval": False,
        "planned_onboard_date": "",
        "first_interview_schedule": "",
        "second_interview_schedule": "",
    }
    return d


def interview_schedule_by_application_ids(
    db: Session,
    application_ids: List[int],
    *,
    RmsApplicationStatusHistory: Type[Any],
) -> Dict[int, Dict[str, str]]:
    """Latest 一面/二面时间备注（来自进入待一面/一面通过时的状态历史）。"""
    ids = sorted({int(i) for i in application_ids if i is not None})
    if not ids:
        return {}

    rows = (
        db.query(RmsApplicationStatusHistory)
        .filter(
            RmsApplicationStatusHistory.application_id.in_(ids),
            RmsApplicationStatusHistory.to_status.in_(
                ("pending_first_interview", "first_interview_passed")
            ),
        )
        .order_by(RmsApplicationStatusHistory.id.desc())
        .all()
    )
    out: Dict[int, Dict[str, str]] = {}
    for row in rows:
        app_id = int(row.application_id)
        bucket = out.setdefault(app_id, {})
        to_status = (row.to_status or "").strip()
        note = str(getattr(row, "note", None) or "")
        if to_status == "pending_first_interview" and "first_interview_schedule" not in bucket:
            val = format_interview_schedule_display(note, kind="first")
            if val:
                bucket["first_interview_schedule"] = val
        elif to_status == "first_interview_passed" and "second_interview_schedule" not in bucket:
            val = format_interview_schedule_display(note, kind="second")
            if val:
                bucket["second_interview_schedule"] = val
    return out


def _clients_by_id(db: Session, Client: Type[Any], client_ids: set[int]) -> Dict[int, Any]:
    if not client_ids:
        return {}
    rows = db.query(Client).filter(Client.id.in_(client_ids)).all()
    return {int(c.id): c for c in rows}


def _application_to_dict_with_capabilities(
    db: Session,
    ctx: AuthContext,
    row: Any,
    *,
    Client: Type[Any],
    offer_approval_info: Optional[Dict[int, Dict[str, str]]] = None,
    offer_onboard_dates: Optional[Dict[int, str]] = None,
    interview_schedules: Optional[Dict[int, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    items = _applications_to_dicts_with_capabilities(
        db,
        ctx,
        [row],
        Client=Client,
        offer_approval_info=offer_approval_info,
        offer_onboard_dates=offer_onboard_dates,
        interview_schedules=interview_schedules,
    )
    return items[0]


def _applications_to_dicts_with_capabilities(
    db: Session,
    ctx: AuthContext,
    rows: List[Any],
    *,
    Client: Type[Any],
    offer_approval_info: Optional[Dict[int, Dict[str, str]]] = None,
    offer_onboard_dates: Optional[Dict[int, str]] = None,
    interview_schedules: Optional[Dict[int, Dict[str, str]]] = None,
) -> List[Dict[str, Any]]:
    client_ids = {int(r.client_id) for r in rows if getattr(r, "client_id", None) is not None}
    clients_by_id = _clients_by_id(db, Client, client_ids)
    offer_approval_info = offer_approval_info or {}
    offer_onboard_dates = offer_onboard_dates or {}
    interview_schedules = interview_schedules or {}
    result: List[Dict[str, Any]] = []
    for row in rows:
        d = application_to_dict(row)
        client = clients_by_id.get(int(row.client_id)) if getattr(row, "client_id", None) is not None else None
        d["can_submit_offer_approval"] = rms_ds.can_submit_offer_approval(
            db,
            ctx,
            client,
            app_status=row.status or "",
        )
        d["offer_current_approval_node_label"] = ""
        d["offer_pending_approver_label"] = ""
        extra = offer_approval_info.get(int(row.id))
        if extra:
            d["offer_current_approval_node_label"] = extra.get("offer_current_approval_node_label") or ""
            d["offer_pending_approver_label"] = extra.get("offer_pending_approver_label") or ""
        onboard = offer_onboard_dates.get(int(row.id))
        if onboard:
            d["planned_onboard_date"] = normalize_rms_date(onboard) or onboard
        sched = interview_schedules.get(int(row.id)) or {}
        if sched.get("first_interview_schedule"):
            d["first_interview_schedule"] = sched["first_interview_schedule"]
        if sched.get("second_interview_schedule"):
            d["second_interview_schedule"] = sched["second_interview_schedule"]
        result.append(d)
    return result


def status_history_to_dict(row: Any) -> Dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "from_status": row.from_status or "",
        "to_status": row.to_status or "",
        "reason": row.reason or "",
        "note": row.note or "",
        "changed_by": row.changed_by,
        "changed_at": normalize_rms_date(row.changed_at),
    }


def list_applications(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    job_id: Optional[int] = None,
    candidate_id: Optional[int] = None,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    RmsOfferRecord: Optional[Type[Any]] = None,
    RmsOfferApprovalStep: Optional[Type[Any]] = None,
    RmsApplicationStatusHistory: Optional[Type[Any]] = None,
) -> List[Dict[str, Any]]:
    q = rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
    if job_id is not None:
        q = q.filter(RmsApplication.job_id == job_id)
    if candidate_id is not None:
        q = q.filter(RmsApplication.candidate_id == candidate_id)
    if client_id is not None:
        q = q.filter(RmsApplication.client_id == client_id)
    if status:
        q = q.filter(RmsApplication.status == status)
    rows = q.order_by(RmsApplication.id.desc()).all()
    offer_approval_info: Dict[int, Dict[str, str]] = {}
    offer_onboard_dates: Dict[int, str] = {}
    if RmsOfferRecord is not None and RmsOfferApprovalStep is not None:
        from services import rms_offer_approval as offer_svc

        pending_app_ids = [
            int(r.id)
            for r in rows
            if (getattr(r, "status", None) or "").strip() == "offer_approval_pending"
        ]
        if pending_app_ids:
            offer_approval_info = offer_svc.pending_approval_info_by_application_ids(
                db,
                pending_app_ids,
                RmsOfferRecord=RmsOfferRecord,
                RmsOfferApprovalStep=RmsOfferApprovalStep,
            )
        onboard_app_ids = [
            int(r.id)
            for r in rows
            if (getattr(r, "status", None) or "").strip() in ("offer_approval_pending", "onboarding")
        ]
        if onboard_app_ids:
            offer_onboard_dates = offer_svc.offer_planned_onboard_by_application_ids(
                db,
                onboard_app_ids,
                RmsOfferRecord=RmsOfferRecord,
            )
    interview_schedules: Dict[int, Dict[str, str]] = {}
    if RmsApplicationStatusHistory is not None:
        interview_app_ids = [
            int(r.id)
            for r in rows
            if (getattr(r, "status", None) or "").strip()
            in ("pending_first_interview", "first_interview_passed")
        ]
        if interview_app_ids:
            interview_schedules = interview_schedule_by_application_ids(
                db,
                interview_app_ids,
                RmsApplicationStatusHistory=RmsApplicationStatusHistory,
            )
    return _applications_to_dicts_with_capabilities(
        db,
        ctx,
        rows,
        Client=Client,
        offer_approval_info=offer_approval_info,
        offer_onboard_dates=offer_onboard_dates,
        interview_schedules=interview_schedules,
    )


def get_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    Client: Type[Any],
    *,
    RmsOfferRecord: Optional[Type[Any]] = None,
    RmsOfferApprovalStep: Optional[Type[Any]] = None,
    RmsApplicationStatusHistory: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = (
        rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="read")
        .filter(RmsApplication.id == application_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    offer_approval_info: Dict[int, Dict[str, str]] = {}
    offer_onboard_dates: Dict[int, str] = {}
    interview_schedules: Dict[int, Dict[str, str]] = {}
    if RmsOfferRecord is not None and RmsOfferApprovalStep is not None:
        from services import rms_offer_approval as offer_svc

        status = (row.status or "").strip()
        if status == "offer_approval_pending":
            offer_approval_info = offer_svc.pending_approval_info_by_application_ids(
                db,
                [int(row.id)],
                RmsOfferRecord=RmsOfferRecord,
                RmsOfferApprovalStep=RmsOfferApprovalStep,
            )
        if status in ("offer_approval_pending", "onboarding"):
            offer_onboard_dates = offer_svc.offer_planned_onboard_by_application_ids(
                db,
                [int(row.id)],
                RmsOfferRecord=RmsOfferRecord,
            )
    status = (row.status or "").strip()
    if (
        RmsApplicationStatusHistory is not None
        and status in ("pending_first_interview", "first_interview_passed")
    ):
        interview_schedules = interview_schedule_by_application_ids(
            db,
            [int(row.id)],
            RmsApplicationStatusHistory=RmsApplicationStatusHistory,
        )
    return _application_to_dict_with_capabilities(
        db,
        ctx,
        row,
        Client=Client,
        offer_approval_info=offer_approval_info,
        offer_onboard_dates=offer_onboard_dates,
        interview_schedules=interview_schedules,
    )


def _get_writable_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    Client: Type[Any],
):
    row = (
        rms_ds.scoped_applications_query(db, ctx, RmsApplication, Client, action="write")
        .filter(RmsApplication.id == application_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="推荐记录不存在")
    return row


def _strip_salary_field(value: Any) -> str:
    return str(value or "").replace(",", "").strip()


def validate_candidate_report_payload(report: Dict[str, Any]) -> None:
    """Validate required fields for candidate-report submission (city validated separately)."""
    if not report.get("job_id"):
        raise HTTPException(status_code=400, detail="请选择应聘岗位")
    for key, label in _CANDIDATE_REPORT_REQUIRED:
        if key in ("current_salary", "expected_salary"):
            val = _strip_salary_field(report.get(key))
        else:
            val = str(report.get(key) or "").strip()
        if not val:
            raise HTTPException(status_code=400, detail=f"请填写{label}")


def _existing_candidate_report_value(candidate: Any, data: Dict[str, Any], key: str) -> Any:
    if key == "city":
        if "city" in data:
            return data.get("city")
        if "location" in data:
            return data.get("location")
    if key in data:
        return data.get(key)
    return getattr(candidate, key, "")


def _validate_existing_candidate_report_profile(candidate: Any, data: Dict[str, Any]) -> None:
    for key, label in _EXISTING_CANDIDATE_REPORT_REQUIRED:
        raw = _existing_candidate_report_value(candidate, data, key)
        if key in ("current_salary", "expected_salary"):
            val = _strip_salary_field(raw)
        else:
            val = str(raw or "").strip()
        if not val:
            raise HTTPException(status_code=400, detail=f"请填写{label}")


def _sync_candidate_target_from_job(
    candidate: Any,
    job: Any,
    *,
    now: str,
) -> None:
    """Align candidate master target fields with the latest recommendation job."""
    candidate.target_job_id = int(job.id)
    candidate.target_client_id = int(job.client_id)
    candidate.updated_at = now


def create_application(
    db: Session,
    ctx: AuthContext,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    job_id = int(data["job_id"])
    candidate_id = int(data["candidate_id"])
    job = rms_ds.assert_job_recommendable(db, ctx, job_id, RmsJob, Client)
    rms_ds.assert_candidate_usable_for_application(
        db, ctx, candidate_id, RmsCandidate, RmsApplication, Client
    )
    candidate = db.query(RmsCandidate).filter(RmsCandidate.id == candidate_id).first()
    if not candidate:
        raise HTTPException(status_code=404, detail="候选人不存在")
    _validate_existing_candidate_report_profile(candidate, data)
    now = utc_date_str()
    row = RmsApplication(
        job_id=job_id,
        candidate_id=candidate_id,
        client_id=int(job.client_id),
        resume_id=data.get("resume_id"),
        status="recommended",
        receive_status="pending",
        delivery_review_status="pending",
        hired_at="",
        recommended_by=ctx.user_id,
        recommended_at=now,
        current_stage="recommended",
        last_activity_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _sync_candidate_target_from_job(candidate, job, now=now)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该岗位已存在该候选人的推荐记录")
    db.refresh(row)
    return application_to_dict(row)


def update_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    data: Dict[str, Any],
    RmsJob: Type[Any],
    RmsCandidate: Type[Any],
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    job_for_sync = None

    if data.get("job_id") is not None:
        job_id = int(data["job_id"])
        job_for_sync = rms_ds.assert_job_writable(db, ctx, job_id, RmsJob, Client)
        row.job_id = job_id
        row.client_id = int(job_for_sync.client_id)

    if data.get("candidate_id") is not None:
        candidate_id = int(data["candidate_id"])
        rms_ds.assert_candidate_usable_for_application(
            db, ctx, candidate_id, RmsCandidate, RmsApplication, Client
        )
        row.candidate_id = candidate_id

    if "resume_id" in data:
        row.resume_id = data.get("resume_id")

    row.updated_at = utc_date_str()
    if data.get("job_id") is not None or data.get("candidate_id") is not None:
        if job_for_sync is None:
            job_for_sync = db.query(RmsJob).filter(RmsJob.id == int(row.job_id)).first()
        candidate = (
            db.query(RmsCandidate)
            .filter(RmsCandidate.id == int(row.candidate_id))
            .first()
        )
        if job_for_sync and candidate:
            _sync_candidate_target_from_job(candidate, job_for_sync, now=row.updated_at)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="该岗位已存在该候选人的推荐记录")
    db.refresh(row)
    return application_to_dict(row)


def transition_application_status(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    data: Dict[str, Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
    *,
    RmsCandidate: Optional[Type[Any]] = None,
    RosterEntry: Optional[Type[Any]] = None,
    RmsOfferRecord: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    raw_from = (row.status or "").strip() or "recommended"
    if raw_from == "recommended":
        raise HTTPException(
            status_code=400,
            detail="推荐记录须先通过交付内审后方可变更招聘进展",
        )
    from_status = normalize_application_status(raw_from)
    to_status = str(data.get("to_status") or "").strip()
    mode = str(data.get("mode") or "transition").strip() or "transition"
    if not to_status:
        raise HTTPException(status_code=400, detail="to_status 不能为空")
    if to_status == from_status:
        raise HTTPException(status_code=400, detail="目标状态与当前状态相同")
    if to_status not in APPLICATION_PROGRESS_STATUSES:
        raise HTTPException(status_code=400, detail=f"非法招聘进展状态 {to_status}")

    if mode == "transition":
        if from_status in APPLICATION_TERMINAL:
            raise HTTPException(status_code=400, detail=f"终态 {from_status} 不可再流转")
        allowed = ALLOWED_TRANSITIONS.get(from_status)
        if allowed is None:
            raise HTTPException(status_code=400, detail=f"未知状态 {raw_from}，不可流转")
        if to_status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"不允许从 {from_status} 变更为 {to_status}",
            )
        hist_reason = str(data.get("reason") or "").strip()
        hist_note = resolve_transition_history_note(from_status, to_status, data)
    elif mode == "correction":
        if not is_pipeline_eligible_application(row):
            raise HTTPException(
                status_code=400,
                detail="状态修正仅适用于已接收且内审通过的推荐记录",
            )
        if from_status == "offer_approval_pending":
            raise HTTPException(
                status_code=400,
                detail="Offer审批中不可通过状态修正变更，须通过审批 API 或等待驳回",
            )
        validate_correction_backward(from_status, to_status)
        hist_note = validate_status_correction_note(str(data.get("note") or ""))
        hist_reason = "status_correction"
    else:
        raise HTTPException(status_code=400, detail=f"未知 mode {mode}")

    now = utc_date_str()
    if from_status == "hired" and to_status != "hired":
        row.hired_at = ""
    if to_status == "hired":
        row.hired_at = validate_hired_at(str(data.get("hired_at") or ""))
    row.status = to_status
    row.current_stage = to_status
    row.last_activity_at = now
    row.updated_at = now
    hist = RmsApplicationStatusHistory(
        application_id=row.id,
        from_status=raw_from if raw_from != from_status else from_status,
        to_status=to_status,
        reason=hist_reason,
        note=hist_note,
        changed_by=ctx.user_id,
        changed_at=now,
    )
    db.add(hist)
    if (
        mode == "correction"
        and from_status == "onboarding"
        and to_status == "pending_offer"
        and RmsOfferRecord is not None
    ):
        from services.rms_offer_records import supersede_approved_offers

        supersede_approved_offers(
            db,
            int(row.id),
            reason="status_correction_reoffer",
            RmsOfferRecord=RmsOfferRecord,
        )
    db.commit()
    db.refresh(row)
    sched = interview_schedule_by_application_ids(
        db, [int(row.id)], RmsApplicationStatusHistory=RmsApplicationStatusHistory
    )
    result = _application_to_dict_with_capabilities(
        db,
        ctx,
        row,
        Client=Client,
        interview_schedules=sched,
    )
    if to_status == "hired" and RmsCandidate is not None and RosterEntry is not None:
        from services import rms_roster_check as roster_chk

        roster_check = roster_chk.check_hired_roster_match(
            db, ctx, row, RmsCandidate, RosterEntry, Client
        )
        result["roster_check"] = roster_check
    return result


def list_status_history(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    get_application(db, ctx, application_id, RmsApplication, Client)
    rows = (
        db.query(RmsApplicationStatusHistory)
        .filter(RmsApplicationStatusHistory.application_id == application_id)
        .order_by(RmsApplicationStatusHistory.id.desc())
        .all()
    )
    return [status_history_to_dict(r) for r in rows]


def _delete_application_children(
    db: Session,
    application_id: int,
    *,
    RmsApplicationStatusHistory: Type[Any],
    RmsInterview: Optional[Type[Any]] = None,
    RmsOffer: Optional[Type[Any]] = None,
    RmsOfferRecord: Optional[Type[Any]] = None,
    RmsMatchResult: Optional[Type[Any]] = None,
) -> None:
    db.query(RmsApplicationStatusHistory).filter(
        RmsApplicationStatusHistory.application_id == application_id
    ).delete(synchronize_session=False)
    if RmsInterview is not None:
        db.query(RmsInterview).filter(
            RmsInterview.application_id == application_id
        ).delete(synchronize_session=False)
    if RmsOffer is not None:
        db.query(RmsOffer).filter(
            RmsOffer.application_id == application_id
        ).delete(synchronize_session=False)
    if RmsOfferRecord is not None:
        db.query(RmsOfferRecord).filter(
            RmsOfferRecord.application_id == application_id
        ).delete(synchronize_session=False)
    if RmsMatchResult is not None:
        db.query(RmsMatchResult).filter(
            RmsMatchResult.application_id == application_id
        ).delete(synchronize_session=False)


def delete_application(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
    *,
    RmsInterview: Optional[Type[Any]] = None,
    RmsOffer: Optional[Type[Any]] = None,
    RmsOfferRecord: Optional[Type[Any]] = None,
    RmsMatchResult: Optional[Type[Any]] = None,
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    app_id = int(row.id)
    candidate_id = int(row.candidate_id)
    _delete_application_children(
        db,
        app_id,
        RmsApplicationStatusHistory=RmsApplicationStatusHistory,
        RmsInterview=RmsInterview,
        RmsOffer=RmsOffer,
        RmsOfferRecord=RmsOfferRecord,
        RmsMatchResult=RmsMatchResult,
    )
    db.delete(row)
    db.commit()
    return {"ok": True, "id": app_id, "candidate_id": candidate_id}


def list_delivery_review_applications(
    db: Session,
    ctx: AuthContext,
    RmsApplication: Type[Any],
    Client: Type[Any],
) -> List[Dict[str, Any]]:
    q = rms_ds.scoped_applications_query(
        db,
        ctx,
        RmsApplication,
        Client,
        action="read",
        include_recommended_by_for_read=False,
    )
    q = q.filter(RmsApplication.status == "recommended")
    q = q.filter(
        or_(
            RmsApplication.delivery_review_status == "pending",
            RmsApplication.delivery_review_status == "",
            RmsApplication.delivery_review_status.is_(None),
        )
    )
    rows = q.order_by(RmsApplication.id.desc()).all()
    return [application_to_dict(r) for r in rows]


def submit_delivery_review(
    db: Session,
    ctx: AuthContext,
    application_id: int,
    data: Dict[str, Any],
    RmsApplication: Type[Any],
    RmsApplicationStatusHistory: Type[Any],
    Client: Type[Any],
) -> Dict[str, Any]:
    row = _get_writable_application(db, ctx, application_id, RmsApplication, Client)
    result = str(data.get("result") or "").strip()
    now = utc_date_str()
    if result == "passed":
        row.delivery_review_status = "passed"
        row.receive_status = "accepted"
        prev_status = (row.status or "").strip() or "recommended"
        if prev_status in ("", "recommended"):
            row.status = "pending_client_screen"
            row.current_stage = "pending_client_screen"
            row.last_activity_at = now
            hist = RmsApplicationStatusHistory(
                application_id=row.id,
                from_status="recommended",
                to_status="pending_client_screen",
                reason="delivery_review_passed",
                note=str(data.get("note") or "").strip(),
                changed_by=ctx.user_id,
                changed_at=now,
            )
            db.add(hist)
    elif result == "failed":
        fail_note = validate_delivery_review_failed_note(str(data.get("note") or ""))
        row.delivery_review_status = "failed"
        prev_status = (row.status or "").strip() or "recommended"
        row.status = "internal_screen_failed"
        row.current_stage = "internal_screen_failed"
        row.last_activity_at = now
        hist = RmsApplicationStatusHistory(
            application_id=row.id,
            from_status=prev_status,
            to_status="internal_screen_failed",
            reason="delivery_review_failed",
            note=fail_note,
            changed_by=ctx.user_id,
            changed_at=now,
        )
        db.add(hist)
    else:
        raise HTTPException(status_code=400, detail=f"非法内审结果 {result}")
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return application_to_dict(row)


def _pdf_blocks_to_text(page: Any) -> str:
    try:
        blocks = page.get_text("blocks", sort=True) or []
    except Exception:
        return ""
    parts: List[str] = []
    for block in blocks:
        if len(block) < 5:
            continue
        text = (block[4] or "").strip()
        if not text:
            continue
        if len(block) > 6 and block[6] == 1:
            continue
        parts.append(text)
    return "\n".join(parts).strip()


def _pdf_words_to_text(page: Any) -> str:
    try:
        words = page.get_text("words", sort=True) or []
    except Exception:
        return ""
    if not words:
        return ""
    lines_by_block: Dict[int, Dict[int, List[str]]] = {}
    for word_entry in words:
        if len(word_entry) < 8:
            continue
        word = str(word_entry[4]).strip()
        if not word:
            continue
        block_no = int(word_entry[5])
        line_no = int(word_entry[6])
        lines_by_block.setdefault(block_no, {}).setdefault(line_no, []).append(word)
    parts: List[str] = []
    for block_no in sorted(lines_by_block.keys()):
        block_lines = lines_by_block[block_no]
        for line_no in sorted(block_lines.keys()):
            parts.append(" ".join(block_lines[line_no]))
    return "\n".join(parts).strip()


def _extract_pdf_page_text(page: Any) -> str:
    text = _pdf_blocks_to_text(page)
    if text:
        return text
    text = _pdf_words_to_text(page)
    if text:
        return text
    try:
        return (page.get_text("text", sort=True) or "").strip()
    except Exception:
        return ""


def _extract_pdf_text(content: bytes) -> str:
    text = ""
    try:
        import fitz
    except ImportError:
        fitz = None  # type: ignore[assignment]
    if fitz is not None:
        try:
            doc = fitz.open(stream=content, filetype="pdf")
            try:
                parts: List[str] = []
                for i in range(len(doc)):
                    try:
                        parts.append(_extract_pdf_page_text(doc.load_page(i)))
                    except Exception:
                        parts.append("")
                text = "\n".join(parts).strip()
            finally:
                try:
                    doc.close()
                except Exception:
                    pass
        except Exception:
            text = ""
    if text:
        return text
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _count_cjk_chars(text: str) -> int:
    return len(_RE_CJK.findall(text or ""))


def _is_noise_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped:
        return False
    if _RE_WATERMARK_LINE.match(stripped):
        return True
    if _RE_TRACKING_LINE.match(stripped):
        return True
    if len(stripped) >= 20 and re.fullmatch(r"[A-Za-z0-9\-]+", stripped):
        return True
    if _count_cjk_chars(stripped) == 0 and len(stripped) > 40:
        alnum = sum(1 for ch in stripped if ch.isalnum())
        if alnum / len(stripped) > 0.85:
            return True
    return False


def _clean_resume_text_for_parse(raw_text: str) -> str:
    lines = (raw_text or "").splitlines()
    result: List[str] = []
    prev_nonempty = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if result and result[-1] != "":
                result.append("")
            continue
        if _is_noise_line(stripped):
            continue
        if stripped == prev_nonempty:
            continue
        result.append(stripped)
        prev_nonempty = stripped
    while result and result[-1] == "":
        result.pop()
    return "\n".join(result).strip()


def _build_extract_warning(
    raw_text: str,
    cleaned_text: str,
    draft_fields: Dict[str, str],
    *,
    is_pdf: bool = False,
) -> str:
    warnings: List[str] = []
    raw = raw_text or ""
    cleaned = cleaned_text or ""
    if raw and len(cleaned) < len(raw) * 0.5:
        warnings.append("检测到较多噪声文本已过滤")
    if raw and _count_cjk_chars(cleaned) < 50:
        warnings.append("识别到的中文内容较少")
    if raw and not any(
        (draft_fields.get(k) or "").strip()
        for k in ("phone", "name", "email_wechat")
    ):
        warnings.append("未能识别姓名、手机或邮箱")
    if is_pdf and not raw.strip():
        warnings.append("未能从 PDF 提取文本，可能是扫描件图片")
    deduped: List[str] = []
    for item in warnings:
        if item not in deduped:
            deduped.append(item)
    return "；".join(deduped)


def _empty_parse_draft_response(message: str = "") -> Dict[str, Any]:
    return {
        "draft_fields": {},
        "parsed_text": "",
        "parsed_text_raw": "",
        "parsed_text_length": 0,
        "parsed_text_raw_length": 0,
        "extract_warning": "",
        "message": message,
    }


def _extract_resume_text(file_name: str, content: bytes) -> Tuple[str, Optional[str]]:
    ext = os.path.splitext(file_name or "")[1].lower()
    if ext in PARSE_DRAFT_WORD_SUFFIXES:
        return "", _WORD_UNSUPPORTED_MSG
    if ext not in PARSE_DRAFT_ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail="该文件类型不支持自动解析")
    if ext == ".pdf":
        return _extract_pdf_text(content), None
    return content.decode("utf-8", errors="replace").strip(), None


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    return (m.group(1) if m.lastindex else m.group(0)).strip()


def _han_char_count(name: str) -> int:
    return sum(1 for ch in name if "\u4e00" <= ch <= "\u9fa5")


def reject_candidate_name_reason(name: str, *, strict_length: bool = False) -> str:
    """Return empty string if name is plausible; otherwise a reject reason code."""
    val = (name or "").strip()
    if not val:
        return "empty"
    if val in _NON_PERSON_NAME_EXACT:
        return "blocklist"
    if val in _PLACE_NAME_EXACT:
        return "place_name"
    if val in _DEMOGRAPHIC_NAME_EXACT:
        return "demographic"
    if val in _SECTION_HEADING_NAME_EXACT:
        return "section_heading"
    for marker in _INSTITUTION_NAME_MARKERS:
        if marker in val:
            return "institution_suffix"
    if _RE_NAME_BRACKETS.search(val):
        return "invalid_format"
    if not _RE_NAME_CHARS.fullmatch(val):
        return "format"
    if strict_length:
        han = _han_char_count(val)
        if "·" in val:
            if han < 2 or han > 8:
                return "length"
        elif han < 2 or han > 4:
            return "length"
    return ""


def _clean_extracted_name(raw: str) -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    label_parts = _FIELD_LABEL_SPLIT.split(val, maxsplit=1)
    if label_parts[0].strip():
        val = label_parts[0]
    val = re.sub(r"1[3-9][0-9 \-()]{9,20}.*$", "", val)
    val = val.strip(" \t:：,，;；|·")
    return val.strip()


def _normalize_name_candidate(raw: str) -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    if re.match(r"^名\s*[:：]", val):
        return ""
    val = re.sub(r"^(?:姓\s*名|姓名)\s*[:：]?", "", val)
    val = re.sub(r"\s+", "", val)
    val = val.strip(" \t:：,，;；|｜")
    if not val or reject_candidate_name_reason(val, strict_length=False):
        return ""
    return val


def _normalize_extracted_person_name(raw: str) -> str:
    return _normalize_name_candidate(raw)


def _resume_context_window(lines: List[str], line_index: int, *, radius: int = 6) -> str:
    start = max(0, line_index - radius)
    end = min(len(lines), line_index + radius + 1)
    return "\n".join(lines[start:end])


def _has_resume_context_near(lines: List[str], line_index: int) -> bool:
    if line_index < 0:
        return False
    window = _resume_context_window(lines, line_index)
    if _RE_RESUME_CONTEXT_NEAR_NAME.search(window):
        return True
    if _RE_PHONE.search(window) or _RE_EMAIL.search(window):
        return True
    return False


def _compact_text_for_name_match(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _name_appears_in_resume_text(name: str, text: str) -> bool:
    compact_name = re.sub(r"\s+", "", name or "")
    compact_text = _compact_text_for_name_match(text)
    return bool(compact_name and compact_name in compact_text)


def _is_admin_place_short_field(value: str) -> bool:
    val = (value or "").strip()
    if not val:
        return False
    if val in _PLACE_NAME_EXACT or val in _PROVINCE_NAME_EXACT:
        return True
    if _RE_NAME_HEADER_STANDALONE.fullmatch(val) and _RE_ADMIN_PLACE_SUFFIX.fullmatch(val):
        return True
    return False


def _is_filename_person_candidate(value: str) -> bool:
    val = (value or "").strip()
    if not val:
        return False
    if not _RE_NAME_HEADER_STANDALONE.fullmatch(val):
        return False
    if re.search(r"[A-Za-z0-9]", val):
        return False
    if val in _FILENAME_NON_PERSON_EXACT:
        return False
    if _is_admin_place_short_field(val):
        return False
    if reject_candidate_name_reason(val, strict_length=False):
        return False
    lower = val.lower()
    if any(marker.lower() in lower for marker in _FILENAME_ROLE_MARKERS):
        return False
    return True


def _next_nonempty_line_index(lines: List[str], start: int) -> int:
    for j in range(start, len(lines)):
        if lines[j]:
            return j
    return -1


def _is_split_section_heading_candidate(lines: List[str], line_index: int) -> bool:
    line = lines[line_index]
    if not line or not _RE_NAME_HEADER_STANDALONE.fullmatch(line):
        return False
    next_idx = _next_nonempty_line_index(lines, line_index + 1)
    if next_idx < 0:
        return False
    next_line = lines[next_idx]
    if not next_line or not _RE_NAME_CHARS.fullmatch(next_line):
        return False
    if not (1 <= _han_char_count(next_line) <= 4):
        return False
    return (line + next_line) in _SPLIT_SECTION_HEADING_TARGETS


def _score_name_candidate(
    value: str,
    *,
    source: str,
    line_index: int,
    lines: List[str],
    resume_text: str = "",
    filename_values: set[str] | frozenset[str] | None = None,
) -> tuple[int, str]:
    filename_values = filename_values or frozenset()
    if not value:
        return 0, "empty"
    if reject_candidate_name_reason(value, strict_length=False):
        return 0, "rejected"
    if re.search(r"[A-Za-z0-9]", value):
        return 0, "format"

    base_scores = {
        "labeled": 90,
        "labeled_split": 90,
        "legacy_labeled": 90,
        "profile_line": 90,
        "header_line": 70,
        "filename": 65,
    }
    score = base_scores.get(source, 0)
    reason = source

    han = _han_char_count(value)
    if 2 <= han <= 4:
        score += 10

    if 0 <= line_index <= 3:
        score += 8

    if _has_resume_context_near(lines, line_index):
        score += 6

    if line_index > 20:
        score -= 20

    if source != "filename" and not _has_resume_context_near(lines, line_index):
        score -= 10

    if source == "filename" and _name_appears_in_resume_text(value, resume_text):
        score += 25

    if source != "filename" and value in filename_values:
        score += 15

    return max(score, 0), reason


def _append_name_candidate(
    candidates: List[_NameCandidate],
    raw: str,
    *,
    source: str,
    line_index: int,
    lines: List[str],
    resume_text: str = "",
    filename_values: set[str] | frozenset[str] | None = None,
) -> None:
    value = _normalize_name_candidate(raw)
    if not value:
        return
    score, reason = _score_name_candidate(
        value,
        source=source,
        line_index=line_index,
        lines=lines,
        resume_text=resume_text,
        filename_values=filename_values,
    )
    if score > 0:
        candidates.append(
            _NameCandidate(
                value=value,
                source=source,
                line_index=line_index,
                score=score,
                reason=reason,
            )
        )


_NAME_SOURCE_PRIORITY = {
    "labeled": 0,
    "profile_line": 0,
    "labeled_split": 1,
    "legacy_labeled": 2,
    "header_line": 3,
    "filename": 4,
}


def _select_best_name_candidate(candidates: List[_NameCandidate]) -> str:
    if not candidates:
        return ""
    ranked = sorted(
        candidates,
        key=lambda c: (
            -c.score,
            _NAME_SOURCE_PRIORITY.get(c.source, 99),
            c.line_index if c.line_index >= 0 else 999,
        ),
    )
    best = ranked[0]
    if best.score < 75:
        return ""
    return best.value


def _collect_name_candidates(text: str, *, file_name: str = "") -> List[_NameCandidate]:
    src = text or ""
    lines = [_normalize_resume_line(line) for line in src.splitlines()]
    candidates: List[_NameCandidate] = []
    filename_values: set[str] = set()
    if file_name:
        filename_values = set(_extract_name_candidates_from_filename(file_name))
    ctx = dict(resume_text=src, filename_values=filename_values)

    for pattern, source in (
        (_RE_NAME_LABEL_INLINE, "labeled"),
        (_RE_NAME_LABEL_NEXT_LINE, "labeled_split"),
    ):
        for match in pattern.finditer(src):
            line_index = src[: match.start()].count("\n")
            _append_name_candidate(
                candidates,
                match.group(1),
                source=source,
                line_index=line_index,
                lines=lines,
                **ctx,
            )

    for i, line in enumerate(lines):
        profile_match = _RE_NAME_GENDER_AGE_LINE.match(line)
        if profile_match:
            _append_name_candidate(
                candidates,
                profile_match.group(1),
                source="profile_line",
                line_index=i,
                lines=lines,
                **ctx,
            )

    nonempty = [line for line in lines if line]
    if nonempty:
        context_window = "\n".join(nonempty[:10])
        if (
            _RE_RESUME_CONTEXT_NEAR_NAME.search(context_window)
            or _RE_PROFILE_LINE.search(context_window)
            or _RE_AGE_LOOSE.search(context_window)
        ):
            nonempty_count = 0
            for i, line in enumerate(lines):
                if not line:
                    continue
                if nonempty_count >= 3:
                    break
                nonempty_count += 1
                if line in _NAME_HEADER_SKIP:
                    continue
                if _is_split_section_heading_candidate(lines, i):
                    continue
                if _is_admin_place_short_field(line):
                    continue
                if _RE_NAME_HEADER_STANDALONE.fullmatch(line):
                    _append_name_candidate(
                        candidates,
                        line,
                        source="header_line",
                        line_index=i,
                        lines=lines,
                        **ctx,
                    )

    for name in filename_values:
        _append_name_candidate(
            candidates,
            name,
            source="filename",
            line_index=-1,
            lines=lines,
            **ctx,
        )

    for match in _RE_NAME.finditer(src):
        line_index = src[: match.start()].count("\n")
        cleaned = _clean_extracted_name(match.group(1))
        _append_name_candidate(
            candidates,
            cleaned,
            source="legacy_labeled",
            line_index=line_index,
            lines=lines,
            **ctx,
        )

    return candidates


def _extract_name_from_labeled_fields(text: str) -> str:
    src = text or ""
    for pattern in (_RE_NAME_LABEL_INLINE, _RE_NAME_LABEL_NEXT_LINE):
        for match in pattern.finditer(src):
            name = _normalize_extracted_person_name(match.group(1))
            if name and not reject_candidate_name_reason(name, strict_length=False):
                return name
    return ""


def _extract_name(text: str, *, file_name: str = "") -> str:
    candidates = _collect_name_candidates(text or "", file_name=file_name)
    return _select_best_name_candidate(candidates)


def _extract_name_from_header(text: str) -> str:
    lines = [_normalize_resume_line(line) for line in (text or "").splitlines()]
    nonempty = [line for line in lines if line]
    if not nonempty:
        return ""
    context_window = "\n".join(nonempty[:10])
    if not (
        _RE_RESUME_CONTEXT_NEAR_NAME.search(context_window)
        or _RE_PROFILE_LINE.search(context_window)
        or _RE_AGE_LOOSE.search(context_window)
    ):
        return ""
    for line in nonempty[:3]:
        if line in _NAME_HEADER_SKIP:
            continue
        if not _RE_NAME_HEADER_STANDALONE.fullmatch(line):
            continue
        if reject_candidate_name_reason(line, strict_length=False):
            continue
        return line
    return ""


def _extract_name_candidates_from_filename(file_name: str) -> List[str]:
    stem = os.path.splitext(os.path.basename(file_name or ""))[0]
    parts = [part.strip() for part in re.split(r"[-—_]", stem) if part.strip()]
    candidates: List[str] = []
    seen: set[str] = set()

    for part in reversed(parts):
        if not _is_filename_person_candidate(part):
            continue
        if part in seen:
            continue
        seen.add(part)
        candidates.append(part)

    return candidates


def _extract_name_from_filename(file_name: str) -> str:
    candidates = _extract_name_candidates_from_filename(file_name)
    return candidates[0] if candidates else ""


def _is_plausible_age(raw: str) -> bool:
    try:
        age = int(str(raw or "").strip())
    except ValueError:
        return False
    return 16 <= age <= 70


def _extract_age(text: str) -> str:
    src = text or ""
    for pattern in (
        _RE_AGE,
        _RE_AGE_PROFILE,
        _RE_AGE_PROFILE_BARE,
        _RE_AGE_PIPE,
        _RE_AGE_GENDER_NEAR,
    ):
        age = _first_match(pattern, src)
        if age and _is_plausible_age(age):
            return age
    header = "\n".join((src or "").splitlines()[:12])
    for match in _RE_AGE_LOOSE.finditer(header):
        age = match.group(1)
        if _is_plausible_age(age):
            return age
    return ""


def _extract_gender(text: str) -> str:
    src = text or ""
    gender = _first_match(_RE_GENDER, src)
    if gender:
        return gender
    header_lines = (src or "").splitlines()[:12]
    header = "\n".join(header_lines)
    gender = _first_match(_RE_GENDER_PROFILE, header)
    if gender:
        return gender
    for line in header_lines:
        stripped = _normalize_resume_line(line)
        match = re.match(r"^(男|女)\s*[|｜]", stripped)
        if match:
            return match.group(1)
    return ""


def _normalize_work_years(raw: str) -> str:
    val = re.sub(r"\s+", "", raw or "")
    val = re.sub(r"(?:工作)?经验$", "", val)
    if not val:
        return ""
    if val.endswith("年以上"):
        return val
    if val.endswith("年"):
        return val
    if val.isdigit():
        return f"{val}年"
    return val


def _extract_explicit_work_years(src: str) -> str:
    for pattern in (_RE_WORK_YEARS_LABEL, _RE_WORK_YEARS_EXPERIENCE):
        m = pattern.search(src)
        if m:
            return _normalize_work_years(m.group(1))
    return ""


def _parse_year_month(token: str) -> Optional[Tuple[int, int]]:
    t = (token or "").strip()
    if not t:
        return None
    m = re.match(r"^(\d{4})[./](\d{1,2})$", t, re.IGNORECASE)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return year, month
        return None
    m = re.match(r"^(\d{4})年(\d{1,2})月?$", t)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return year, month
    return None


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _parse_work_periods(
    text: str,
    today: Optional[date] = None,
) -> List[Tuple[int, int]]:
    ref = today or date.today()
    periods: List[Tuple[int, int]] = []
    open_end_tokens = {"至今", "现在", "present", "current"}
    for m in WORK_PERIOD_RE.finditer(text or ""):
        start_parsed = _parse_year_month(m.group("start"))
        if not start_parsed:
            continue
        end_raw = (m.group("end") or "").strip()
        if end_raw.lower() in open_end_tokens or end_raw in open_end_tokens:
            end_parsed = (ref.year, ref.month)
        else:
            end_parsed = _parse_year_month(end_raw)
        if not end_parsed:
            continue
        start_idx = _month_index(*start_parsed)
        end_idx = _month_index(*end_parsed)
        if start_idx > end_idx:
            continue
        periods.append((start_idx, end_idx))
    return periods


def _merge_period_months(periods: List[Tuple[int, int]]) -> int:
    if not periods:
        return 0
    merged: List[Tuple[int, int]] = [sorted(periods)[0]]
    for start, end in sorted(periods)[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + 1:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return sum(end - start + 1 for start, end in merged)


def _format_work_years(total_months: int) -> str:
    if total_months <= 0:
        return ""
    if total_months < 12:
        return f"{total_months}个月"
    years, months = divmod(total_months, 12)
    if months == 0:
        return f"{years}年"
    return f"{years}年{months}个月"


def _text_without_education_block(text: str) -> str:
    lines = (text or "").splitlines()
    result: List[str] = []
    in_edu = False
    for line in lines:
        stripped = line.strip()
        if not in_edu:
            if _EDU_BLOCK_START.match(stripped):
                in_edu = True
                continue
            result.append(line)
            continue
        if _EDU_BLOCK_STOP.match(stripped):
            in_edu = False
            result.append(line)
    return "\n".join(result).strip()


def _extract_work_experience_text(text: str) -> str:
    lines = (text or "").splitlines()
    blocks: List[str] = []
    current: List[str] = []
    in_work = False

    for line in lines:
        stripped = line.strip()
        if _WORK_SECTION_START.match(stripped):
            if in_work and current:
                blocks.append("\n".join(current))
            current = []
            in_work = True
            continue
        if in_work:
            if stripped and _WORK_SECTION_STOP.match(stripped):
                if current:
                    blocks.append("\n".join(current))
                current = []
                in_work = False
                continue
            current.append(stripped)

    if in_work and current:
        blocks.append("\n".join(current))

    if blocks:
        return "\n".join(blocks)

    return _text_without_education_block(text)


def _parse_work_years_from_periods(
    text: str,
    today: Optional[date] = None,
) -> str:
    work_text = _extract_work_experience_text(text)
    if not work_text:
        return ""
    periods = _parse_work_periods(work_text, today=today)
    total = _merge_period_months(periods)
    return _format_work_years(total)


def _extract_education_block(text: str) -> str:
    lines = (text or "").splitlines()
    in_block = False
    block_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        if not in_block:
            if _EDU_BLOCK_START.match(stripped):
                in_block = True
            continue
        if _EDU_BLOCK_STOP.match(stripped):
            break
        block_lines.append(stripped)
    return "\n".join(block_lines).strip()


def _normalize_phone_candidate(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if _RE_PHONE.fullmatch(digits):
        return digits
    for match in re.finditer(r"1[3-9]\d{9}", digits):
        return match.group(0)
    return ""


def _extract_phone(text: str) -> str:
    src = text or ""
    candidates: List[str] = []
    for match in _RE_PHONE_LABEL.finditer(src):
        candidates.append(match.group(1))
    candidates.extend(re.findall(r"1[3-9][0-9 \-()]{9,20}", src))
    seen: set[str] = set()
    for raw in candidates:
        digits = _normalize_phone_candidate(raw)
        if not digits or digits in seen:
            continue
        seen.add(digits)
        return digits
    return ""


def _education_level_from_line(line: str) -> str:
    stripped = (line or "").strip()
    if not stripped:
        return ""
    for part in _DEGREE_IN_PARENS.findall(stripped):
        normalized = _normalize_education_level(part)
        if normalized:
            return normalized
    pipe_m = _DEGREE_INLINE.search(stripped)
    if pipe_m:
        normalized = _normalize_education_level(pipe_m.group(1))
        if normalized:
            return normalized
    return ""


def _is_education_continuation(prev: str, nxt: str) -> bool:
    if not nxt.strip() or _search_school_entity(nxt):
        return False
    if _DEGREE_ONLY_LINE.match(nxt.strip()):
        return False
    if _SKILL_LINE.match(nxt.strip()):
        return False
    if re.match(r"^(?:毕业论文|毕业设计|项目经历|工作经历|工作经验|实习经历)", nxt.strip()):
        return False
    if len(nxt.strip()) > 60:
        return False
    if _education_level_from_line(prev):
        return False
    if _DEGREE_INLINE.search(nxt):
        return True
    prev_stripped = prev.rstrip()
    nxt_stripped = nxt.lstrip()
    if not prev_stripped or not nxt_stripped:
        return False
    if re.match(r"^\d{4}", nxt_stripped):
        return False
    last = prev_stripped[-1]
    first = nxt_stripped[0]
    if "\u4e00" <= last <= "\u9fff" and "\u4e00" <= first <= "\u9fff":
        return True
    return False


def _merge_education_lines(lines: List[str]) -> List[str]:
    merged: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if idx + 1 < len(lines) and _is_education_continuation(line, lines[idx + 1]):
            nxt = lines[idx + 1].strip()
            prev_stripped = line.rstrip()
            nxt_stripped = nxt.lstrip()
            if (
                prev_stripped
                and nxt_stripped
                and "\u4e00" <= prev_stripped[-1] <= "\u9fff"
                and "\u4e00" <= nxt_stripped[0] <= "\u9fff"
            ):
                line = prev_stripped + nxt_stripped
            else:
                line = prev_stripped + " " + nxt_stripped
            idx += 1
        merged.append(line)
        idx += 1
    return merged


def _collect_education_lines(text: str) -> List[str]:
    block = _extract_education_block(text)
    source_lines = (
        [line.strip() for line in block.splitlines() if line.strip()]
        if block
        else [line.strip() for line in (text or "").splitlines() if line.strip()]
    )
    lines: List[str] = []
    idx = 0
    while idx < len(source_lines):
        stripped = source_lines[idx]
        if not block:
            if _WORK_SECTION_START.match(stripped) or _EDU_BLOCK_STOP.match(stripped):
                idx += 1
                continue
            if re.match(r"^(?:毕业论文|毕业设计)", stripped):
                idx += 1
                continue
            if not _search_school_entity(stripped):
                idx += 1
                continue
            if _SKILL_LINE.match(stripped):
                idx += 1
                continue
        lines.append(stripped)
        idx += 1
        while idx < len(source_lines) and _is_education_continuation(lines[-1], source_lines[idx]):
            lines.append(source_lines[idx].strip())
            idx += 1
    return lines


def _collect_education_content(text: str) -> str:
    lines = _merge_education_lines(_collect_education_lines(text))
    return "\n".join(lines).strip()


def _normalize_education_level(degree_text: str) -> str:
    t = (degree_text or "").strip()
    if not t:
        return ""
    if "博士" in t:
        return "其他"
    if "硕士" in t:
        return "硕士"
    if "学士" in t or "本科" in t:
        return "统本"
    if "大专" in t or "专科" in t:
        return "专科"
    return ""


def _clean_major(raw: str, school: str = "") -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    val = _DEGREE_IN_PARENS.sub("", val)
    val = _DATE_RANGE_RE.sub("", val)
    val = _YEAR_ONLY_RANGE_RE.sub("", val)
    val = _DEGREE_INLINE.sub("", val)
    if school:
        val = val.replace(school, "")
    val = re.sub(r"专业\s*$", "", val.strip())
    val = re.sub(
        r"(?:博士研究生|博士|硕士研究生|硕士|本科|大专|专科|学士)\s*$",
        "",
        val,
    )
    val = val.strip(" \t:：,，;；|")
    val = val.strip()
    if not val:
        return ""
    if "毕业论文" in val or "毕业设计" in val:
        return ""
    if school and school in val:
        return ""
    if _DATE_RANGE_RE.search(val):
        return ""
    if _search_school_entity(val):
        return ""
    return _collapse_chinese_spaces(val.strip())


def _parse_education_from_text(edu_block: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    pending_school = ""
    if not edu_block:
        return result
    for line in edu_block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^(?:毕业论文|毕业设计)", stripped):
            continue
        school_m = _search_school_entity(stripped)
        if school_m:
            school = _normalize_school_name(school_m.group(1))
            after = stripped[school_m.end():]
            level = _education_level_from_line(stripped)
            major = _clean_major(after, school=school)
            result["school"] = school
            pending_school = school if not major else ""
            if major:
                result["major"] = major
            if level:
                result["education_level"] = level
            continue
        if pending_school and not result.get("major"):
            if _DEGREE_ONLY_LINE.match(stripped):
                level = _normalize_education_level(stripped)
                if level:
                    result["education_level"] = level
                continue
            major = _clean_major(stripped, school=pending_school)
            if major:
                result["major"] = major
                pending_school = ""
            level = _education_level_from_line(stripped)
            if level:
                result["education_level"] = level
    return result


def _extract_draft_fields_from_text(text: str, *, file_name: str = "") -> Dict[str, str]:
    src = _normalize_resume_text(text).strip()
    fields: Dict[str, str] = {}
    if not src:
        return fields

    phone = _extract_phone(src)
    if phone:
        fields["phone"] = phone

    email_m = _RE_EMAIL.search(src)
    if email_m:
        fields["email_wechat"] = email_m.group(0)

    name = _extract_name(src, file_name=file_name)
    if name:
        fields["name"] = name

    age = _extract_age(src)
    if age:
        fields["age"] = age

    work_years = _extract_explicit_work_years(src)
    if work_years:
        fields["work_years"] = work_years
    else:
        parsed = _parse_work_years_from_periods(src)
        if parsed:
            fields["work_years"] = parsed

    current_salary = _first_match(_RE_CURRENT_SALARY, src)
    if current_salary:
        fields["current_salary"] = current_salary

    expected_salary = _first_match(_RE_EXPECTED_SALARY, src)
    if expected_salary:
        fields["expected_salary"] = expected_salary

    edu_content = _collect_education_content(src)
    edu = _parse_education_from_text(edu_content) if edu_content else {}
    if edu.get("school"):
        fields["school"] = edu["school"]
    else:
        school = _first_match(_RE_SCHOOL, src)
        if school:
            fields["school"] = _normalize_school_name(school)
        else:
            for line in src.splitlines():
                school_m = _search_school_entity(line)
                if school_m:
                    fields["school"] = _normalize_school_name(school_m.group(1))
                    break

    if edu.get("major"):
        fields["major"] = edu["major"]
    else:
        major = _first_match(_RE_MAJOR, src)
        if major:
            fields["major"] = major

    if edu.get("education_level"):
        fields["education_level"] = edu["education_level"]
    else:
        edu_m = _RE_EDUCATION.search(src)
        if edu_m:
            normalized = _normalize_education_level(edu_m.group(1))
            if normalized:
                fields["education_level"] = normalized

    gender = _extract_gender(src)
    if gender:
        fields["gender"] = gender

    return fields


def _parse_resume_content(file_name: str, content: bytes) -> Dict[str, Any]:
    ext = os.path.splitext(file_name or "")[1].lower()
    raw_text, word_msg = _extract_resume_text(file_name, content)
    if word_msg:
        return {
            "draft_fields": {},
            "cleaned_text": "",
            "raw_text": "",
            "extract_warning": "",
            "message": word_msg,
        }

    cleaned_text = _clean_resume_text_for_parse(raw_text)
    draft_fields = _extract_draft_fields_from_text(cleaned_text, file_name=file_name)
    extract_warning = _build_extract_warning(
        raw_text,
        cleaned_text,
        draft_fields,
        is_pdf=ext == ".pdf",
    )
    return {
        "draft_fields": draft_fields,
        "cleaned_text": cleaned_text,
        "raw_text": raw_text,
        "extract_warning": extract_warning,
        "message": "",
    }


def parse_resume_file_for_storage(file_name: str, content: bytes) -> Tuple[str, str]:
    """Return (parsed_text, parsed_json_str) for rms_resumes persistence."""
    try:
        parsed = _parse_resume_content(file_name, content)
        cleaned_text = parsed.get("cleaned_text") or ""
        draft_fields = parsed.get("draft_fields") or {}
        parsed_json = json.dumps(draft_fields, ensure_ascii=False)
        return cleaned_text, parsed_json
    except HTTPException:
        raise
    except Exception:
        return "", "{}"


def parse_resume_draft(file_name: str, content: bytes) -> Dict[str, Any]:
    if len(content) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=400, detail="简历文件不能超过 10MB")

    parsed = _parse_resume_content(file_name, content)
    if parsed.get("message"):
        return _empty_parse_draft_response(parsed["message"])

    cleaned_text = parsed["cleaned_text"]
    raw_text = parsed["raw_text"]
    return {
        "draft_fields": parsed["draft_fields"],
        "parsed_text": cleaned_text[:PARSE_DRAFT_TEXT_MAX] if cleaned_text else "",
        "parsed_text_raw": raw_text[:PARSE_DRAFT_TEXT_MAX] if raw_text else "",
        "parsed_text_length": len(cleaned_text),
        "parsed_text_raw_length": len(raw_text),
        "extract_warning": parsed["extract_warning"],
        "message": "",
    }
