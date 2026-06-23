"""Tests for handoff → RMS job sync."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from services.handoff_rms_sync import sync_handoff_positions_to_rms_jobs


class _FakeRmsJob:
    client_id = None
    title = None
    location = None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def test_sync_creates_and_updates_rms_jobs():
    db = MagicMock()
    existing = SimpleNamespace(
        client_id=1,
        title="Java开发",
        location="深圳",
        headcount=2,
        updated_at="",
    )
    q = MagicMock()
    q.filter.return_value = q
    q.first.side_effect = [existing, None]
    db.query.return_value = q

    handoff = SimpleNamespace(
        client_id=1,
        delivery_owner_user_id=9,
        requirement_json='{"positions":[{"role":"Java开发","headcount":3},{"role":"测试","headcount":1}],"context":{"location":"深圳"}}',
    )

    result = sync_handoff_positions_to_rms_jobs(
        db,
        handoff,
        RmsJob=_FakeRmsJob,
        operator_user_id=5,
    )

    assert result == {"created": 1, "updated": 1, "synced": 2}
    assert existing.headcount == 3
    assert db.add.called


def test_sync_uses_operator_when_no_delivery_owner():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.first.return_value = None
    db.query.return_value = q

    handoff = SimpleNamespace(
        client_id=2,
        delivery_owner_user_id=None,
        requirement_json='{"positions":[{"role":"PM","headcount":2}]}',
    )

    result = sync_handoff_positions_to_rms_jobs(
        db,
        handoff,
        RmsJob=_FakeRmsJob,
        operator_user_id=7,
    )

    assert result["created"] == 1
    added = db.add.call_args[0][0]
    assert added.owner_user_id == 7
