from __future__ import annotations

from datetime import date, datetime

from services.handoff_deadline import add_business_days, compute_review_deadline, is_business_day


def test_is_business_day_weekend():
    holidays: set[date] = set()
    workdays: set[date] = set()
    assert is_business_day(date(2026, 6, 22), holidays, workdays) is True  # Mon
    assert is_business_day(date(2026, 6, 27), holidays, workdays) is False  # Sat


def test_is_business_day_holiday_and_makeup():
    holidays = {date(2026, 6, 22)}
    workdays = {date(2026, 6, 27)}
    assert is_business_day(date(2026, 6, 22), holidays, workdays) is False
    assert is_business_day(date(2026, 6, 27), holidays, workdays) is True


def test_add_two_business_days_from_monday():
    start = datetime(2026, 6, 22, 10, 18, 33)
    end = add_business_days(start, 2, holidays=set(), workdays=set())
    assert end == datetime(2026, 6, 24, 10, 18, 33)


def test_add_two_business_days_from_friday_skips_weekend():
    start = datetime(2026, 6, 26, 15, 0, 0)
    end = add_business_days(start, 2, holidays=set(), workdays=set())
    assert end == datetime(2026, 6, 30, 15, 0, 0)


def test_add_business_days_skips_holiday():
    start = datetime(2026, 6, 19, 9, 0, 0)  # Fri
    holidays = {date(2026, 6, 22), date(2026, 6, 23)}  # Mon/Tue off
    end = add_business_days(start, 2, holidays=holidays, workdays=set())
    assert end == datetime(2026, 6, 25, 9, 0, 0)  # Thu


def test_compute_review_deadline_default_two_days():
    start = datetime(2026, 6, 10, 10, 18, 33)  # Wed, avoids 2026 Dragon Boat holidays
    end = compute_review_deadline(start)
    assert end == datetime(2026, 6, 12, 10, 18, 33)


def test_deadline_reminder_within_twelve_hours():
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    import services.handoff_deadline as mod
    from services.handoff_deadline import process_handoff_deadline_reminders

    now = datetime(2026, 6, 11, 10, 0, 0)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    class _Col:
        def isnot(self, _x):
            return self

        def is_(self, _x):
            return self

        def __gt__(self, _x):
            return self

        def __le__(self, _x):
            return self

    class _Handoff:
        status = _Col()
        review_deadline_at = _Col()
        deadline_reminder_sent_at = _Col()

    class _Client:
        id = _Col()

    original = mod.datetime
    mod.datetime = _FixedDatetime

    handoff = SimpleNamespace(
        id=1,
        client_id=9,
        title="测试交接",
        delivery_owner="ops_head",
        review_deadline_at=datetime(2026, 6, 12, 10, 18, 33),
        deadline_reminder_sent_at=None,
        status="pending_review",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [handoff]
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(name="测试客户")
    sent = []

    def notify(db_, user, ntype, message, hid, cid):
        sent.append((user, ntype, message))

    try:
        count = process_handoff_deadline_reminders(
            db,
            HandoffRequest=_Handoff,
            Client=_Client,
            CrmNotification=object,
            notify=notify,
        )
    finally:
        mod.datetime = original

    assert count == 1
    assert sent[0][0] == "ops_head"
    assert sent[0][1] == "handoff_deadline_reminder"
    assert handoff.deadline_reminder_sent_at == now
