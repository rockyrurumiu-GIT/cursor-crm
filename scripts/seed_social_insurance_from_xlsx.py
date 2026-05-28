#!/usr/bin/env python3
"""Seed social_insurance_locations from 毛利测算表2026.xlsx (idempotent if table empty)."""
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import SocialInsuranceLocation, DB_URL, BASE_DIR
from services.gm_insurance import ensure_social_insurance_schema, seed_social_insurance_locations


def main():
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    ensure_social_insurance_schema(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        n = seed_social_insurance_locations(db, SocialInsuranceLocation, base_dir=BASE_DIR)
        print(f"Seeded {n} rows")
    finally:
        db.close()


if __name__ == "__main__":
    main()
