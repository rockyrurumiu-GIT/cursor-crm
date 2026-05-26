"""Delivery Pipeline business logic — migrated from main.py (Phase 5B)."""

import csv
import io
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Type

from fastapi import HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from schemas.delivery_pipeline import PIPELINE_EXPORT_HEADERS, PIPELINE_HEADER_MAP
from services.date_utils import parse_loose_date
from services.period_utils import (
    extract_period_month,
    normalize_period_label,
    period_sort_key,
    period_week_bounds,
    week_label_from_date,
)


# ---------------------------------------------------------------------------
# Serialization / normalization
# ---------------------------------------------------------------------------

def pipeline_entry_to_dict(e: Any) -> Dict[str, str]:
    return {
        "id": e.id,
        "client_id": e.client_id,
        "resume_time": e.resume_time or "",
        "date": e.date or "",
        "position": e.position or "",
        "full_name": e.full_name or "",
        "domain": e.domain or "",
        "years_experience": e.years_experience or "",
        "region": e.region or "",
        "phone": e.phone or "",
        "education": e.education or "",
        "recruiter": e.recruiter or "",
        "resume_screening": e.resume_screening or "",
        "interviewed": e.interviewed or "",
        "interview_time": e.interview_time or "",
        "interviewer": e.interviewer or "",
        "result": e.result or "",
        "got_offer": e.got_offer or "",
        "onboarding_time": e.onboarding_time or "",
        "onboarded": e.onboarded or "",
        "status_note": e.status_note or "",
        "serial_no": e.serial_no or "",
    }


def normalize_pipeline_payload(d: Dict[str, Any]) -> Dict[str, str]:
    keys = [
        "resume_time", "date", "position", "full_name", "domain",
        "years_experience", "region", "phone", "education", "recruiter",
        "resume_screening", "interviewed", "interview_time", "interviewer",
        "result", "got_offer", "onboarding_time", "onboarded", "status_note",
        "serial_no",
    ]
    out: Dict[str, str] = {}
    for k in keys:
        v = d.get(k, "")
        if v is None:
            v = ""
        out[k] = str(v).strip()
    return out


def validate_pipeline_payload(
    data: Dict[str, str],
    *,
    context: str = "保存",
    row_hint: str = "",
) -> None:
    allowed_interviewed = {"", "是", "放弃", "约面"}
    allowed_result = {"", "通过", "不通过", "待定", "放弃面试", "待面ing"}
    name = str(data.get("full_name") or "").strip()
    interviewed = str(data.get("interviewed") or "").strip()
    interview_time = str(data.get("interview_time") or "").strip()
    result = str(data.get("result") or "").strip()
    got_offer = str(data.get("got_offer") or "").strip()
    onboarding_time = str(data.get("onboarding_time") or "").strip()
    onboarded = str(data.get("onboarded") or "").strip()

    label_parts = [context]
    if row_hint:
        label_parts.append(row_hint)
    if name:
        label_parts.append(name)
    prefix = "｜".join(label_parts)

    if interviewed not in allowed_interviewed:
        raise HTTPException(status_code=400, detail=f'{prefix}：是否面试仅支持填写“是 / 放弃 / 约面”')
    if result not in allowed_result:
        raise HTTPException(status_code=400, detail=f'{prefix}：面试结果仅支持填写“通过 / 不通过 / 待定”')
    if got_offer and got_offer not in ("是", "否"):
        raise HTTPException(status_code=400, detail=f'{prefix}：是否接offer仅支持填写“是”或“否”')
    if interviewed == "是" and not interview_time:
        raise HTTPException(status_code=400, detail=f'{prefix}：是否面试为“是”时，必须填写面试时间')
    if got_offer and result != "通过":
        raise HTTPException(status_code=400, detail=f'{prefix}：已填写是否接offer时，面试结果必须为“通过”')

    has_onboarding_signal = bool(onboarding_time) or ("已入职" in onboarded) or ("待入职" in onboarded)
    if has_onboarding_signal and not got_offer:
        raise HTTPException(status_code=400, detail=f'{prefix}：已填写入职时间或将是否入职改为“X月已入职/待入职”时，必须填写是否接offer')
    if has_onboarding_signal and result != "通过":
        raise HTTPException(status_code=400, detail=f'{prefix}：已填写入职时间或已标记待入职/已入职时，面试结果必须为“通过”')
    if has_onboarding_signal and got_offer == "否":
        raise HTTPException(status_code=400, detail=f'{prefix}：已填写入职时间或已标记待入职/已入职时，是否接offer不能为“否”')


def normalize_pipeline_insight_demand_payload(d: Dict[str, Any]) -> Dict[str, str]:
    return {
        "period": str(d.get("period", "") or "").strip(),
        "position": str(d.get("position", "") or "").strip(),
        "region": str(d.get("region", "") or "").strip(),
        "demand_qty": str(d.get("demand_qty", "") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Resequence
# ---------------------------------------------------------------------------

def resequence_pipeline_serial_no(db: Session, client_id: int, PipelineEntry: Type) -> None:
    rows = (
        db.query(PipelineEntry)
        .filter(PipelineEntry.client_id == client_id)
        .order_by(PipelineEntry.id)
        .all()
    )
    for idx, row in enumerate(rows, start=1):
        row.serial_no = str(idx)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def write_pipeline_backup_csv(client: Any, rows: list, backup_dir: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in client.name if ch.isalnum() or ch in (" ", "-", "_")).strip() or f"client_{client.id}"
    name = f"pipeline_backup_{safe_name}__cid{client.id}__{ts}.csv"
    path = os.path.join(backup_dir, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(PIPELINE_EXPORT_HEADERS)
        for e in rows:
            d = pipeline_entry_to_dict(e)
            writer.writerow([d.get(PIPELINE_HEADER_MAP[h], "") for h in PIPELINE_EXPORT_HEADERS])
    return name


# ---------------------------------------------------------------------------
# Insight dashboard computation
# ---------------------------------------------------------------------------

def compute_pipeline_insight(
    db: Session,
    client_id: int,
    Client: Type,
    PipelineEntry: Type,
    InsightDemand: Type,
) -> dict:
    """Complete pipeline insight/dashboard computation (formerly inline in handler)."""
    c = db.query(Client).filter(Client.id == client_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")

    detail_metric_keys = [
        "待客户筛选", "待面试", "已面试", "面试通过",
        "本周offer人数", "offer在谈", "弃offer/谈薪失败",
        "在途人数/待入职", "月度在途流失(包含前序)", "本周入职人数",
    ]

    def empty_detail_map() -> Dict[str, List[str]]:
        return {k: [] for k in detail_metric_keys}

    def append_detail(detail_map: Dict[str, List[str]], metric_key: str, full_name: str, position: str) -> None:
        name = str(full_name or "").strip()
        pos = str(position or "").strip()
        if not name:
            return
        detail_map.setdefault(metric_key, []).append(f"{name}｜{pos or '-'}")

    def _detail_date_text(raw_value: str, parsed_date: Optional[Any]) -> str:
        if parsed_date:
            return parsed_date.strftime("%Y/%m/%d")
        return str(raw_value or "").strip() or "-"

    def _is_previous_month_interview(interview_parsed: Optional[Any], onboarding_parsed: Optional[Any]) -> bool:
        if not interview_parsed or not onboarding_parsed:
            return False
        previous_month = 12 if int(onboarding_parsed.month) == 1 else int(onboarding_parsed.month) - 1
        return int(interview_parsed.month) == previous_month

    def _detail_name_with_period_mark(full_name: str, interview_parsed: Optional[Any], onboarding_parsed: Optional[Any]) -> str:
        name = str(full_name or "").strip() or "-"
        if _is_previous_month_interview(interview_parsed, onboarding_parsed):
            return f"{name}(上月)"
        return name

    def detail_with_onboarding(full_name: str, position: str, interview_parsed, onboarding_raw: str, onboarding_parsed) -> str:
        name = _detail_name_with_period_mark(full_name, interview_parsed, onboarding_parsed)
        pos = str(position or "").strip() or "-"
        return f"{name}｜{pos}｜{_detail_date_text(onboarding_raw, onboarding_parsed)}"

    def detail_with_cross_month_mark(full_name: str, position: str, interview_parsed, onboarding_parsed) -> str:
        name = _detail_name_with_period_mark(full_name, interview_parsed, onboarding_parsed)
        pos = str(position or "").strip() or "-"
        return f"{name}｜{pos}"

    demand_rows = db.query(InsightDemand).filter(InsightDemand.client_id == client_id).all()
    demand_map = {
        (str(item.period or "").strip(), str(item.position or "").strip(), str(item.region or "").strip()):
        str(item.demand_qty or "").strip()
        for item in demand_rows
    }

    rows = db.query(PipelineEntry).filter(PipelineEntry.client_id == client_id).order_by(PipelineEntry.id).all()
    today = datetime.now().date()
    grouped: Dict[tuple, Dict[str, Any]] = {}
    inner_fail_counts: Dict[tuple, int] = {}
    weekly_onboard_counts: Dict[tuple, int] = {}
    weekly_in_transit_counts: Dict[tuple, int] = {}
    weekly_in_transit_loss_counts: Dict[tuple, int] = {}
    weekly_onboard_details: Dict[tuple, List[str]] = {}
    weekly_in_transit_details: Dict[tuple, List[str]] = {}
    weekly_in_transit_loss_details: Dict[tuple, List[str]] = {}
    anomalies: List[Dict[str, str]] = []

    def ensure_group(group_key: tuple) -> Dict[str, Any]:
        group_period, group_position, group_region = group_key
        if group_key not in grouped:
            grouped[group_key] = {
                "时间": group_period,
                "岗位": group_position,
                "需求数量": "",
                "地点": group_region,
                "推送简历量": 0,
                "内筛通过": 0,
                "重复": 0,
                "待客户筛选": 0,
                "客筛通过": 0,
                "放弃面试": 0,
                "待面试": 0,
                "已面试": 0,
                "面试通过": 0,
                "本周offer人数": 0,
                "offer在谈": 0,
                "弃offer/谈薪失败": 0,
                "在途人数/待入职": 0,
                "月度在途流失(包含前序)": 0,
                "本周入职人数": 0,
                "本月入职人数": 0,
                "_metric_details": empty_detail_map(),
            }
            inner_fail_counts[group_key] = 0
        return grouped[group_key]

    for e in rows:
        period = normalize_period_label(str(e.date or "").strip())
        position = str(e.position or "").strip()
        region = str(e.region or "").strip()
        if not period or not position:
            continue
        key = (period, position, region)
        item = ensure_group(key)
        item["推送简历量"] += 1
        detail_map = item["_metric_details"]
        resume_screening = str(e.resume_screening or "").strip()
        interviewed = str(e.interviewed or "").strip()
        interview_time = str(e.interview_time or "").strip()
        result = str(e.result or "").strip()
        got_offer = str(e.got_offer or "").strip()
        onboarded = str(e.onboarded or "").strip()
        interview_date = parse_loose_date(interview_time)
        interview_period = week_label_from_date(interview_date) if interview_date else ""
        onboarding_time = str(e.onboarding_time or "").strip()
        onboarding_date = parse_loose_date(onboarding_time)
        period_bounds = period_week_bounds(period)
        period_end = period_bounds[1] if period_bounds else None

        if resume_screening == "友商重复":
            item["重复"] += 1
        if resume_screening == "内筛不通过":
            inner_fail_counts[key] = int(inner_fail_counts.get(key, 0)) + 1
        if resume_screening == "待反馈":
            item["待客户筛选"] += 1
            append_detail(detail_map, "待客户筛选", e.full_name, position)
        if resume_screening == "通过":
            item["客筛通过"] += 1
        if interviewed == "放弃":
            item["放弃面试"] += 1
        if interviewed == "约面" and (
            not interview_time or (interview_date and period_end and interview_date > period_end)
        ):
            item["待面试"] += 1
            append_detail(detail_map, "待面试", e.full_name, position)
        if interviewed == "是" and interview_date:
            interviewed_item = ensure_group((interview_period or period, position, region))
            interviewed_item["已面试"] += 1
            append_detail(interviewed_item["_metric_details"], "已面试", e.full_name, position)
        if interviewed == "是" and not interview_time:
            anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "是否面试=是，但面试时间为空", "时间": period, "岗位": position, "地点": region})
        if result == "通过":
            result_item = ensure_group((interview_period or period, position, region))
            result_item["面试通过"] += 1
            append_detail(result_item["_metric_details"], "面试通过", e.full_name, position)
            if interviewed != "是":
                anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "面试结果=通过，但是否面试不为“是”", "时间": period, "岗位": position, "地点": region})
        if got_offer in ("是", "否") and result != "通过":
            anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "是否接offer已填写，但面试结果不为“通过”", "时间": period, "岗位": position, "地点": region})
        if got_offer == "是" and result == "通过":
            offer_item = ensure_group((interview_period or period, position, region))
            offer_item["本周offer人数"] += 1
            offer_item["_metric_details"].setdefault("本周offer人数", []).append(
                detail_with_cross_month_mark(e.full_name, position, interview_date, onboarding_date)
            )
        if result == "通过" and not got_offer:
            negotiating_item = ensure_group((interview_period or period, position, region))
            negotiating_item["offer在谈"] += 1
            append_detail(negotiating_item["_metric_details"], "offer在谈", e.full_name, position)
        if got_offer == "否" and result == "通过":
            offer_reject_item = ensure_group((interview_period or period, position, region))
            offer_reject_item["弃offer/谈薪失败"] += 1
            append_detail(offer_reject_item["_metric_details"], "弃offer/谈薪失败", e.full_name, position)
        if got_offer == "是" and onboarded == "放弃入职":
            if onboarding_date:
                loss_week = week_label_from_date(onboarding_date)
                loss_key = (loss_week, position, region)
                weekly_in_transit_loss_counts[loss_key] = int(weekly_in_transit_loss_counts.get(loss_key, 0)) + 1
                weekly_in_transit_loss_details.setdefault(loss_key, []).append(
                    detail_with_onboarding(e.full_name, position, interview_date, onboarding_time, onboarding_date)
                )
            else:
                anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "状态为放弃入职，但入职时间为空或无法解析", "时间": period, "岗位": position, "地点": region})
        if "待入职" in onboarded and onboarding_date and onboarding_date <= today:
            anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "状态为待入职，但入职时间未晚于今天", "时间": period, "岗位": position, "地点": region})
        elif "待入职" in onboarded and not onboarding_date:
            m_wait = re.search(r"(\d{1,2})\s*月\s*待入职", onboarded)
            if m_wait:
                anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "状态为待入职，但待入职月份早于当前月份", "时间": period, "岗位": position, "地点": region})
        is_waiting_text = bool(re.fullmatch(r"\s*\d{1,2}\s*月\s*待入职\s*", onboarded))
        if is_waiting_text and onboarding_date and onboarding_date > today:
            waiting_week = week_label_from_date(onboarding_date)
            waiting_key = (waiting_week, position, region)
            weekly_in_transit_counts[waiting_key] = int(weekly_in_transit_counts.get(waiting_key, 0)) + 1
            weekly_in_transit_details.setdefault(waiting_key, []).append(
                detail_with_onboarding(e.full_name, position, interview_date, onboarding_time, onboarding_date)
            )
        if "已入职" in onboarded and not onboarding_date:
            anomalies.append({"row_id": int(e.id), "姓名": str(e.full_name or "").strip() or "-", "问题": "状态为已入职，但入职时间为空或无法解析", "时间": period, "岗位": position, "地点": region})
        count_weekly_onboard = False
        if onboarding_date:
            if "已入职" in onboarded:
                count_weekly_onboard = True
            elif onboarded == "是" and onboarding_date <= today:
                count_weekly_onboard = True
        if count_weekly_onboard:
            onboard_week = week_label_from_date(onboarding_date)
            onboard_key = (onboard_week, position, region)
            weekly_onboard_counts[onboard_key] = int(weekly_onboard_counts.get(onboard_key, 0)) + 1
            weekly_onboard_details.setdefault(onboard_key, []).append(
                detail_with_onboarding(e.full_name, position, interview_date, onboarding_time, onboarding_date)
            )
        period_month = extract_period_month(period)
        if period_month is not None:
            if re.search(rf"{int(period_month)}\s*月\s*已入职", onboarded):
                item["本月入职人数"] += 1
            elif (
                onboarded == "是"
                and onboarding_date
                and onboarding_date <= today
                and int(onboarding_date.month) == int(period_month)
            ):
                item["本月入职人数"] += 1

    supplemental_keys: Dict[tuple, bool] = {}
    for k, cnt in weekly_onboard_counts.items():
        if cnt > 0:
            supplemental_keys[k] = True
    for k, cnt in weekly_in_transit_counts.items():
        if cnt > 0:
            supplemental_keys[k] = True
    for k, cnt in weekly_in_transit_loss_counts.items():
        if cnt > 0:
            supplemental_keys[k] = True

    for (onboard_week, onboard_pos, onboard_region) in supplemental_keys.keys():
        synthetic_key = (onboard_week, onboard_pos, onboard_region)
        if synthetic_key in grouped:
            continue
        ensure_group(synthetic_key)

    out = list(grouped.values())
    for item in out:
        key = (item["时间"], item["岗位"], item["地点"])
        inner_fail = int(inner_fail_counts.get(key, 0))
        item["内筛通过"] = max(0, int(item["推送简历量"]) - inner_fail)
        period_norm = normalize_period_label(str(item.get("时间", "") or "").strip())
        pos = str(item.get("岗位", "") or "").strip()
        region_val = str(item.get("地点", "") or "").strip()
        onboard_key = (period_norm, pos, region_val)
        item["本周入职人数"] = int(weekly_onboard_counts.get(onboard_key, 0))
        item["在途人数/待入职"] = int(weekly_in_transit_counts.get(onboard_key, 0))
        item["月度在途流失(包含前序)"] = int(weekly_in_transit_loss_counts.get(onboard_key, 0))
        item["_metric_details"]["本周入职人数"] = list(weekly_onboard_details.get(onboard_key, []))
        item["_metric_details"]["在途人数/待入职"] = list(weekly_in_transit_details.get(onboard_key, []))
        item["_metric_details"]["月度在途流失(包含前序)"] = list(weekly_in_transit_loss_details.get(onboard_key, []))
        item["需求数量"] = demand_map.get(key, "")
    out.sort(
        key=lambda x: (
            period_sort_key(str(x.get("时间", ""))),
            str(x.get("岗位", "")),
            str(x.get("地点", "")),
        ),
        reverse=True,
    )
    return {"rows": out, "anomalies": anomalies}
