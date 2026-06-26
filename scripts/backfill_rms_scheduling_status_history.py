#!/usr/bin/env python3
"""Backfill missing scheduling / first- / second-interview status history rows.

Apps that reached later pipeline stages via status_correction may lack intermediate
history nodes. This script inserts audit rows so lifecycle metrics and history align.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from schemas.rms import APPLICATION_PROGRESS_ORDER, normalize_application_status

_BACKFILL_REASON = "history_backfill"
_SCHEDULING_PASSED = set(
    APPLICATION_PROGRESS_ORDER[APPLICATION_PROGRESS_ORDER.index("pending_first_interview") :]
)
_CLIENT_SCREEN_PASSED = set(
    APPLICATION_PROGRESS_ORDER[APPLICATION_PROGRESS_ORDER.index("scheduling_interview") :]
)
_FIRST_INTERVIEW_PASSED = set(
    APPLICATION_PROGRESS_ORDER[APPLICATION_PROGRESS_ORDER.index("first_interview_passed") :]
)
_PAST_FIRST_INTERVIEW_WITHOUT_PASS = _FIRST_INTERVIEW_PASSED - {
    "first_interview_passed",
    "first_interview_failed",
}
_SECOND_INTERVIEW_PASSED = set(
    APPLICATION_PROGRESS_ORDER[APPLICATION_PROGRESS_ORDER.index("second_interview_passed") :]
)
_PAST_SECOND_INTERVIEW_WITHOUT_PASS = _SECOND_INTERVIEW_PASSED - {
    "second_interview_passed",
    "second_interview_failed",
    "second_interview_abandoned",
}


def _db_path(db_url: str) -> Path:
    if db_url.startswith("sqlite:///"):
        raw = db_url[len("sqlite:///") :]
        path = Path(raw)
        if not path.is_absolute():
            path = ROOT / path
        return path
    raise SystemExit(f"Unsupported DB URL: {db_url}")


def _load_apps(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(
        """
        SELECT id, status, delivery_review_status
        FROM rms_applications
        WHERE delivery_review_status = 'passed'
        ORDER BY id
        """
    ).fetchall()


def _history(conn: sqlite3.Connection, app_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT id, from_status, to_status, reason, changed_at, changed_by
        FROM rms_application_status_history
        WHERE application_id = ?
        ORDER BY id ASC
        """,
        (app_id,),
    ).fetchall()


def _to_statuses(histories: list[sqlite3.Row]) -> set[str]:
    out: set[str] = set()
    for row in histories:
        st = normalize_application_status(str(row["to_status"] or ""))
        if st:
            out.add(st)
    return out


def _first_transition_to(histories: list[sqlite3.Row], targets: set[str]) -> sqlite3.Row | None:
    for row in histories:
        st = normalize_application_status(str(row["to_status"] or ""))
        if st in targets:
            return row
    return None


def _plan_backfill(app_id: int, histories: list[sqlite3.Row]) -> list[dict]:
    if not histories:
        return []
    reached = _to_statuses(histories)
    if not (reached & _SCHEDULING_PASSED):
        return []
    inserts: list[dict] = []
    has_si = "scheduling_interview" in reached
    has_pfi = "pending_first_interview" in reached

    if not has_si and (reached & _CLIENT_SCREEN_PASSED):
        anchor = _first_transition_to(histories, _SCHEDULING_PASSED) or histories[-1]
        from_st = "pending_client_screen"
        for row in histories:
            st = normalize_application_status(str(row["to_status"] or ""))
            if st == "pending_client_screen":
                from_st = "pending_client_screen"
                break
        inserts.append(
            {
                "application_id": app_id,
                "from_status": from_st,
                "to_status": "scheduling_interview",
                "reason": _BACKFILL_REASON,
                "note": "统计补录：约面中",
                "changed_at": anchor["changed_at"],
                "changed_by": anchor["changed_by"],
                "before_id": int(anchor["id"]),
            }
        )
        has_si = True

    if not has_pfi and (reached & _SCHEDULING_PASSED):
        anchor = _first_transition_to(
            histories,
            _SCHEDULING_PASSED - {"scheduling_interview", "interview_scheduling_failed"},
        ) or _first_transition_to(histories, _SCHEDULING_PASSED)
        if anchor is None:
            return inserts
        from_st = "scheduling_interview" if has_si else "pending_client_screen"
        inserts.append(
            {
                "application_id": app_id,
                "from_status": from_st,
                "to_status": "pending_first_interview",
                "reason": _BACKFILL_REASON,
                "note": "统计补录：待一面",
                "changed_at": anchor["changed_at"],
                "changed_by": anchor["changed_by"],
                "before_id": int(anchor["id"]),
            }
        )
    return inserts


def _plan_first_interview_backfill(
    app_id: int,
    histories: list[sqlite3.Row],
    extra_to_statuses: list[str],
) -> list[dict]:
    if not histories:
        return []
    reached = _to_statuses(histories)
    for st in extra_to_statuses:
        reached.add(normalize_application_status(st))
    if "first_interview_passed" in reached:
        return []
    if not (reached & _PAST_FIRST_INTERVIEW_WITHOUT_PASS):
        return []
    anchor = _first_transition_to(histories, _PAST_FIRST_INTERVIEW_WITHOUT_PASS)
    if anchor is None:
        return []
    if "pending_first_interview" in reached:
        from_st = "pending_first_interview"
    elif "scheduling_interview" in reached:
        from_st = "scheduling_interview"
    else:
        from_st = "pending_client_screen"
    return [
        {
            "application_id": app_id,
            "from_status": from_st,
            "to_status": "first_interview_passed",
            "reason": _BACKFILL_REASON,
            "note": "统计补录：一面通过",
            "changed_at": anchor["changed_at"],
            "changed_by": anchor["changed_by"],
            "before_id": int(anchor["id"]),
        }
    ]


def _plan_second_interview_backfill(
    app_id: int,
    histories: list[sqlite3.Row],
    extra_to_statuses: list[str],
) -> list[dict]:
    if not histories:
        return []
    reached = _to_statuses(histories)
    for st in extra_to_statuses:
        reached.add(normalize_application_status(st))
    if "second_interview_passed" in reached:
        return []
    if not (reached & _PAST_SECOND_INTERVIEW_WITHOUT_PASS):
        return []
    anchor = _first_transition_to(histories, _PAST_SECOND_INTERVIEW_WITHOUT_PASS)
    if anchor is None:
        return []
    if "first_interview_passed" in reached:
        from_st = "first_interview_passed"
    elif "pending_first_interview" in reached:
        from_st = "pending_first_interview"
    elif "scheduling_interview" in reached:
        from_st = "scheduling_interview"
    else:
        from_st = "pending_client_screen"
    return [
        {
            "application_id": app_id,
            "from_status": from_st,
            "to_status": "second_interview_passed",
            "reason": _BACKFILL_REASON,
            "note": "统计补录：二面通过",
            "changed_at": anchor["changed_at"],
            "changed_by": anchor["changed_by"],
            "before_id": int(anchor["id"]),
        }
    ]


def backfill(conn: sqlite3.Connection, *, dry_run: bool) -> dict:
    planned: list[dict] = []
    for app in _load_apps(conn):
        app_id = int(app["id"])
        hist = _history(conn, app_id)
        scheduling = _plan_backfill(app_id, hist)
        planned.extend(scheduling)
        first_inserts = _plan_first_interview_backfill(
            app_id,
            hist,
            [row["to_status"] for row in scheduling],
        )
        planned.extend(first_inserts)
        extra = [row["to_status"] for row in scheduling] + [row["to_status"] for row in first_inserts]
        planned.extend(_plan_second_interview_backfill(app_id, hist, extra))

    if dry_run:
        return {"dry_run": True, "insert_count": len(planned), "rows": planned}

    inserted = 0
    for row in sorted(planned, key=lambda r: (r["application_id"], r["before_id"])):
        conn.execute(
            """
            INSERT INTO rms_application_status_history
            (application_id, from_status, to_status, reason, note, changed_by, changed_at)
            VALUES (:application_id, :from_status, :to_status, :reason, :note, :changed_by, :changed_at)
            """,
            row,
        )
        inserted += 1
    if inserted:
        conn.commit()
    return {"dry_run": False, "insert_count": inserted}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill RMS scheduling / first- / second-interview status history"
    )
    parser.add_argument(
        "--db-url",
        default=os.environ.get("CRM_DB_URL", "sqlite:///./crm_v8.db"),
        help="SQLite URL (default: CRM_DB_URL or sqlite:///./crm_v8.db)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply inserts (default: dry-run only)",
    )
    args = parser.parse_args()
    path = _db_path(args.db_url)
    if not path.exists():
        raise SystemExit(f"Database not found: {path}")

    conn = sqlite3.connect(path)
    try:
        result = backfill(conn, dry_run=not args.commit)
    finally:
        conn.close()

    mode = "COMMITTED" if args.commit else "DRY-RUN"
    print(f"[{mode}] would insert {result['insert_count']} history row(s)")
    for row in result.get("rows") or []:
        print(
            f"  app#{row['application_id']}: "
            f"{row['from_status']} -> {row['to_status']} @ {row['changed_at']} ({row['note']})"
        )


if __name__ == "__main__":
    main()
