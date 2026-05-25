"""Pytest fixtures for phase-01 smoke tests (isolated SQLite DB)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEST_DB_FILE = ROOT / "tests" / "_pytest_crm.db"


@pytest.fixture(scope="session", autouse=True)
def _test_env():
    if TEST_DB_FILE.is_file():
        TEST_DB_FILE.unlink()
    os.environ["CRM_ALLOW_DEFAULT_ADMIN"] = "1"
    os.environ["CRM_ADMIN_CREDENTIALS_STORE"] = str(ROOT / "tests" / "_pytest_no_admin_creds.json")
    os.environ["CRM_DB_URL"] = f"sqlite:///{TEST_DB_FILE}"
    os.environ.pop("CRM_ADMIN_PASSWORD", None)
    yield
    if TEST_DB_FILE.is_file():
        TEST_DB_FILE.unlink()


@pytest.fixture(scope="session")
def app(_test_env):
    # Import after env is set so engine binds to test DB.
    import main as crm_main

    return crm_main.app


@pytest.fixture
def client(app):
    from starlette.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_auth():
    return ("admin", "admin123")

