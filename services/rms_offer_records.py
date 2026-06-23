"""RMS offer record helpers (shared by offer approval and application status)."""
from __future__ import annotations

from typing import Any, Type

from sqlalchemy.orm import Session

from schemas.rms import utc_date_str


def supersede_approved_offers(
    db: Session,
    application_id: int,
    *,
    reason: str,
    RmsOfferRecord: Type[Any],
) -> int:
    """Mark approved offer records as superseded. Does not commit."""
    rows = (
        db.query(RmsOfferRecord)
        .filter(
            RmsOfferRecord.application_id == int(application_id),
            RmsOfferRecord.status == "approved",
        )
        .all()
    )
    if not rows:
        return 0
    now = utc_date_str()
    note = (reason or "").strip()
    for row in rows:
        row.status = "superseded"
        row.reason = note
        row.current_approval_node = ""
        row.updated_at = now
    return len(rows)
