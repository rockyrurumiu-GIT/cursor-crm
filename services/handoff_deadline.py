"""Handoff review deadline (business days) and pre-expiry reminders."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional, Set, Tuple, Type

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_HOLIDAY_FILE = BASE_DIR / "data" / "china_public_holidays.json"

HANDOFF_REVIEW_DEADLINE_BUSINESS_DAYS = 2
HANDOFF_DEADLINE_REMINDER_HOURS = 12
REMINDER_JOB_INTERVAL_SEC = 300


@lru_cache(maxsize=1)
def _load_calendar(path: str) -> Tuple[frozenset[date], frozenset[date]]:
    p = Path(path)
    holidays: Set[date] = set()
    workdays: Set[date] = set()
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            for item in raw.get("holidays") or []:
                holidays.add(date.fromisoformat(str(item)[:10]))
            for item in raw.get("workdays") or []:
                workdays.add(date.fromisoformat(str(item)[:10]))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("handoff holiday calendar load failed: %s", exc)
    return frozenset(holidays), frozenset(workdays)


def calendar_path() -> str:
    return os.environ.get("CRM_HOLIDAY_CALENDAR", str(DEFAULT_HOLIDAY_FILE))


def is_business_day(
    day: date,
    holidays: Optional[Set[date]] = None,
    workdays: Optional[Set[date]] = None,
) -> bool:
    hset, wset = _load_calendar(calendar_path())
    holidays = hset if holidays is None else holidays
    workdays = wset if workdays is None else workdays
    if day in workdays:
        return True
    if day in holidays:
        return False
    return day.weekday() < 5


def add_business_days(
    start: datetime,
    days: int,
    *,
    holidays: Optional[Set[date]] = None,
    workdays: Optional[Set[date]] = None,
) -> datetime:
    if days <= 0:
        return start
    cur = start
    added = 0
    while added < days:
        cur = cur + timedelta(days=1)
        if is_business_day(cur.date(), holidays, workdays):
            added += 1
    return cur


def compute_review_deadline(submitted_at: datetime, business_days: int = HANDOFF_REVIEW_DEADLINE_BUSINESS_DAYS) -> datetime:
    return add_business_days(submitted_at, business_days)


def format_deadline_local(dt: datetime) -> str:
    return dt.strftime("%Y/%m/%d %H:%M")


def ensure_handoff_review_deadline(handoff: Any, submitted_at: Optional[datetime] = None) -> None:
    base = submitted_at or getattr(handoff, "submitted_at", None) or datetime.now()
    handoff.review_deadline_at = compute_review_deadline(base)
    handoff.deadline_reminder_sent_at = None


def backfill_missing_deadlines(db: Session, HandoffRequest: Type[Any]) -> int:
    rows = (
        db.query(HandoffRequest)
        .filter(
            HandoffRequest.status == "pending_review",
            HandoffRequest.submitted_at.isnot(None),
            HandoffRequest.review_deadline_at.is_(None),
        )
        .all()
    )
    for h in rows:
        ensure_handoff_review_deadline(h, h.submitted_at)
    if rows:
        db.commit()
    return len(rows)


def process_handoff_deadline_reminders(
    db: Session,
    *,
    HandoffRequest: Type[Any],
    Client: Type[Any],
    CrmNotification: Type[Any],
    notify: Callable[[Session, str, str, str, int, int], None],
) -> int:
    now = datetime.now()
    remind_after = now
    remind_before = now + timedelta(hours=HANDOFF_DEADLINE_REMINDER_HOURS)
    rows = (
        db.query(HandoffRequest)
        .filter(
            HandoffRequest.status == "pending_review",
            HandoffRequest.review_deadline_at.isnot(None),
            HandoffRequest.deadline_reminder_sent_at.is_(None),
            HandoffRequest.review_deadline_at > remind_after,
            HandoffRequest.review_deadline_at <= remind_before,
        )
        .all()
    )
    sent = 0
    for h in rows:
        target = (getattr(h, "delivery_owner", None) or "").strip()
        if not target:
            continue
        client = db.query(Client).filter(Client.id == h.client_id).first()
        client_name = client.name if client else ""
        deadline_text = format_deadline_local(h.review_deadline_at)
        notify(
            db,
            target,
            "handoff_deadline_reminder",
            f"【即将超时】{client_name}：{h.title}，请于 {deadline_text} 前完成审批",
            int(h.id),
            int(h.client_id),
        )
        h.deadline_reminder_sent_at = now
        sent += 1
    if sent:
        db.commit()
    return sent


def maintain_deadlines_on_session(
    db: Session,
    *,
    HandoffRequest: Type[Any],
    Client: Type[Any],
    CrmNotification: Type[Any],
    notify: Callable[[Session, str, str, str, int, int], None],
) -> None:
    backfill_missing_deadlines(db, HandoffRequest)
    process_handoff_deadline_reminders(
        db,
        HandoffRequest=HandoffRequest,
        Client=Client,
        CrmNotification=CrmNotification,
        notify=notify,
    )


def run_deadline_maintenance(
    session_factory: Callable[[], Session],
    *,
    HandoffRequest: Type[Any],
    Client: Type[Any],
    CrmNotification: Type[Any],
    notify: Callable[[Session, str, str, str, int, int], None],
) -> None:
    db = session_factory()
    try:
        maintain_deadlines_on_session(
            db,
            HandoffRequest=HandoffRequest,
            Client=Client,
            CrmNotification=CrmNotification,
            notify=notify,
        )
    except Exception:
        logger.exception("handoff deadline maintenance failed")
        db.rollback()
    finally:
        db.close()


def start_deadline_reminder_thread(
    session_factory: Callable[[], Session],
    *,
    HandoffRequest: Type[Any],
    Client: Type[Any],
    CrmNotification: Type[Any],
    notify: Callable[[Session, str, str, str, int, int], None],
) -> None:
    def _loop() -> None:
        while True:
            run_deadline_maintenance(
                session_factory,
                HandoffRequest=HandoffRequest,
                Client=Client,
                CrmNotification=CrmNotification,
                notify=notify,
            )
            time.sleep(REMINDER_JOB_INTERVAL_SEC)

    threading.Thread(target=_loop, name="handoff-deadline-reminder", daemon=True).start()
