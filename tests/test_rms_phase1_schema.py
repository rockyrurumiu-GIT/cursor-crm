"""RMS Phase 1: migration ledger, table schema, ORM registration."""
from __future__ import annotations

import importlib

import pytest
from sqlalchemy import text

from auth.migrate import run_all as run_schema_migrations

RMS_TABLES = (
    "rms_jobs",
    "rms_candidates",
    "rms_resumes",
    "rms_applications",
    "rms_application_status_history",
    "rms_interviews",
    "rms_offers",
    "rms_match_results",
)

EXPECTED_ORM_TABLENAMES = {
    "RmsJob": "rms_jobs",
    "RmsCandidate": "rms_candidates",
    "RmsResume": "rms_resumes",
    "RmsApplication": "rms_applications",
    "RmsApplicationStatusHistory": "rms_application_status_history",
    "RmsInterview": "rms_interviews",
    "RmsOffer": "rms_offers",
    "RmsMatchResult": "rms_match_results",
}


def _column_names(conn, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {str(r[1]) for r in rows}


def _reload_main():
    import main as crm_main

    importlib.reload(crm_main)
    return crm_main


@pytest.fixture
def crm_main(_test_env):
    return _reload_main()


def test_migration_005_applied(crm_main):
    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT migration_id FROM schema_migrations "
                "WHERE migration_id = '005_rms_tables.sql'"
            )
        ).fetchone()
    assert row is not None


def test_rms_tables_exist(crm_main):
    with crm_main.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name LIKE 'rms_%' ORDER BY name"
            )
        ).fetchall()
    names = {str(r[0]) for r in rows}
    assert names == set(RMS_TABLES)


def test_rms_jobs_has_client_id_and_owner_user_id(crm_main):
    with crm_main.engine.connect() as conn:
        cols = _column_names(conn, "rms_jobs")
    assert "client_id" in cols
    assert "owner_user_id" in cols


def test_rms_candidates_has_created_by_user_id(crm_main):
    with crm_main.engine.connect() as conn:
        cols = _column_names(conn, "rms_candidates")
    assert "created_by_user_id" in cols


def test_rms_applications_has_client_id(crm_main):
    with crm_main.engine.connect() as conn:
        cols = _column_names(conn, "rms_applications")
    assert "client_id" in cols


def test_migration_009_applied_and_columns(crm_main):
    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT migration_id FROM schema_migrations "
                "WHERE migration_id = '009_rms_applications_pipeline.sql'"
            )
        ).fetchone()
        assert row is not None
        cols = _column_names(conn, "rms_applications")
    for col in ("receive_status", "delivery_review_status", "hired_at"):
        assert col in cols


def test_migration_009_idempotent_second_run(crm_main):
    run_schema_migrations(crm_main.engine)
    run_schema_migrations(crm_main.engine)
    with crm_main.engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM schema_migrations "
                "WHERE migration_id = '009_rms_applications_pipeline.sql'"
            )
        ).scalar()
    assert int(count or 0) == 1


def test_rms_application_orm_pipeline_fields(crm_main):
    RmsApplication = crm_main.RMS_MODELS["RmsApplication"]
    assert hasattr(RmsApplication, "receive_status")
    assert hasattr(RmsApplication, "delivery_review_status")
    assert hasattr(RmsApplication, "hired_at")


def test_rms_date_helpers():
    from schemas.rms import normalize_rms_date, utc_date_str

    today = utc_date_str()
    assert len(today) == 10
    assert today[4] == "-" and today[7] == "-"
    assert normalize_rms_date("2026-06-07T14:30:00Z") == "2026-06-07"
    assert normalize_rms_date("2026-06-07 14:30:00") == "2026-06-07"
    assert normalize_rms_date("2026-06-07") == "2026-06-07"
    assert normalize_rms_date("") == ""


def test_rms_applications_unique_job_candidate(crm_main):
    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'rms_applications'")
        ).fetchone()
    assert row is not None
    ddl = str(row[0]).upper()
    assert "UNIQUE" in ddl
    assert "JOB_ID" in ddl
    assert "CANDIDATE_ID" in ddl


def test_rms_match_results_has_application_id(crm_main):
    with crm_main.engine.connect() as conn:
        cols = _column_names(conn, "rms_match_results")
    assert "application_id" in cols
    assert "job_id" in cols
    assert "candidate_id" in cols


def test_rms_match_results_no_client_id(crm_main):
    with crm_main.engine.connect() as conn:
        cols = _column_names(conn, "rms_match_results")
    assert "client_id" not in cols


def test_migration_005_idempotent_second_run(crm_main):
    run_schema_migrations(crm_main.engine)
    run_schema_migrations(crm_main.engine)
    with crm_main.engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = '005_rms_tables.sql'")
        ).scalar()
    assert int(count or 0) == 1


def test_migration_007_applied_and_idempotent(crm_main):
    run_schema_migrations(crm_main.engine)
    with crm_main.engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT migration_id FROM schema_migrations "
                "WHERE migration_id = '007_rms_jobs_extended.sql'"
            )
        ).fetchone()
        assert row is not None
        cols = _column_names(conn, "rms_jobs")
    for col in (
        "priority",
        "salary_cap",
        "years_required",
        "education",
        "overtime_travel",
        "interviewer",
        "note",
    ):
        assert col in cols
    run_schema_migrations(crm_main.engine)
    with crm_main.engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE migration_id = '007_rms_jobs_extended.sql'")
        ).scalar()
    assert int(count or 0) == 1


def test_orm_models_registered(crm_main):
    models = crm_main.RMS_MODELS
    assert set(models.keys()) == set(EXPECTED_ORM_TABLENAMES.keys())
    for class_name, tablename in EXPECTED_ORM_TABLENAMES.items():
        assert models[class_name].__tablename__ == tablename


def test_register_rms_models_idempotent(crm_main):
    from models.rms import register_rms_models

    first = register_rms_models(crm_main.Base)
    second = register_rms_models(crm_main.Base)
    assert first.keys() == second.keys()
    assert first["RmsJob"] is second["RmsJob"]


def test_register_rms_models_separate_base_isolated():
    from sqlalchemy.orm import declarative_base

    from models.rms import register_rms_models

    BaseA = declarative_base()
    models_a = register_rms_models(BaseA)

    BaseB = declarative_base()
    models_b = register_rms_models(BaseB)

    assert "rms_jobs" in BaseA.metadata.tables
    assert "rms_jobs" in BaseB.metadata.tables
    assert models_a["RmsJob"] is not models_b["RmsJob"]
