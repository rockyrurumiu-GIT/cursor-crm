#!/usr/bin/env python3
"""Backfill owner_user_id / delivery_owner_user_id from legacy string owner fields."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _resolve_db_path(db_url: str) -> Path:
    if db_url.startswith("sqlite:///"):
        raw = db_url[len("sqlite:///") :]
        p = Path(raw)
        if not p.is_absolute():
            p = ROOT / raw
        return p
    raise SystemExit(f"Unsupported CRM_DB_URL: {db_url}")


def _match_user_id(conn: sqlite3.Connection, label: str) -> int | None:
    s = (label or "").strip()
    if not s:
        return None
    row = conn.execute(
        "SELECT id FROM sys_user WHERE LOWER(username) = LOWER(?) OR display_name = ? LIMIT 1",
        (s, s),
    ).fetchone()
    return int(row[0]) if row else None


def run(db_path: Path, *, apply: bool) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    unmatched_clients: list[tuple] = []
    unmatched_handoffs: list[tuple] = []
    updated_clients = 0
    updated_handoffs = 0

    for row in conn.execute(
        "SELECT id, name, owner, owner_user_id FROM clients ORDER BY id"
    ):
        if row["owner_user_id"]:
            continue
        owner_label = row["owner"] or ""
        uid = _match_user_id(conn, owner_label)
        if uid:
            if apply:
                conn.execute(
                    "UPDATE clients SET owner_user_id = ? WHERE id = ?",
                    (uid, row["id"]),
                )
            updated_clients += 1
        elif owner_label.strip():
            unmatched_clients.append((row["id"], row["name"], owner_label))

    for row in conn.execute(
        "SELECT id, client_id, delivery_owner, delivery_owner_user_id FROM handoff_requests ORDER BY id"
    ):
        if row["delivery_owner_user_id"]:
            continue
        label = row["delivery_owner"] or ""
        uid = _match_user_id(conn, label)
        if uid:
            if apply:
                conn.execute(
                    "UPDATE handoff_requests SET delivery_owner_user_id = ? WHERE id = ?",
                    (uid, row["id"]),
                )
            updated_handoffs += 1
        elif label.strip():
            unmatched_handoffs.append((row["id"], row["client_id"], label))

    print(f"clients matched: {updated_clients}")
    print(f"handoffs matched: {updated_handoffs}")
    if unmatched_clients:
        print("unmatched clients (id, name, owner):")
        for item in unmatched_clients[:50]:
            print(" ", item)
        if len(unmatched_clients) > 50:
            print(f"  ... and {len(unmatched_clients) - 50} more")
    if unmatched_handoffs:
        print("unmatched handoffs (id, client_id, delivery_owner):")
        for item in unmatched_handoffs[:50]:
            print(" ", item)

    if apply:
        conn.commit()
        print("applied.")
    else:
        print("dry-run only; pass --apply to write changes.")
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate string owners to owner_user_id columns")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLite URL (default: CRM_DB_URL or sqlite:///./crm_v8.db)",
    )
    args = parser.parse_args()
    import os

    db_url = args.db_url or os.environ.get("CRM_DB_URL", "sqlite:///./crm_v8.db")
    db_path = _resolve_db_path(db_url)
    if not db_path.is_file():
        raise SystemExit(f"Database not found: {db_path}")
    if args.apply:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = db_path.with_suffix(db_path.suffix + f".owner_migrate_{ts}.bak")
        shutil.copy2(db_path, backup)
        print(f"backup: {backup}")
    return run(db_path, apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
