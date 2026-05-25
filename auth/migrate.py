from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_all(engine: Engine) -> None:
    """Apply pending SQL migrations; idempotent via schema_migrations ledger."""
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "migration_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        for path in migration_files:
            mid = path.name
            row = conn.execute(
                text("SELECT 1 FROM schema_migrations WHERE migration_id = :id"),
                {"id": mid},
            ).fetchone()
            if row:
                logger.info("migration skipped: %s", mid)
                continue
            sql = path.read_text(encoding="utf-8")
            logger.info("migration applying: %s", mid)
            for stmt in _split_sql_statements(sql):
                if stmt.strip():
                    conn.execute(text(stmt))
            conn.execute(
                text(
                    "INSERT INTO schema_migrations (migration_id, applied_at) VALUES (:id, :at)"
                ),
                {"id": mid, "at": _utc_now()},
            )
            logger.info("migration applied: %s", mid)


def _split_sql_statements(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            parts.append("\n".join(buf))
            buf = []
    if buf:
        parts.append("\n".join(buf))
    return parts
