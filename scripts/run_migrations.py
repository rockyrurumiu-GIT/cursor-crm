#!/usr/bin/env python3
"""Apply pending SQL migrations to the CRM database."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import create_engine

from auth.migrate import run_all

DB_URL = os.environ.get("CRM_DB_URL", "sqlite:///./crm_v8.db")


def main() -> int:
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    run_all(engine)
    print("Migrations complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
