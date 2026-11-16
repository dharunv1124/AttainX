"""
Pytest configuration for isolated automated test runs.
Restricts SQLite usage strictly to isolated test suites.
The production/application database remains PostgreSQL.
"""

import os
import secrets
from pathlib import Path
import pytest

# Ensure automated tests run in an isolated testing environment using an isolated test SQLite DB
os.environ["ENVIRONMENT"] = "testing"
for password_name in (
    "OBE_SEED_ADMIN_PASSWORD",
    "OBE_SEED_FACULTY_PASSWORD",
    "OBE_SEED_ADVISOR_PASSWORD",
    "OBE_SEED_HOD_PASSWORD",
):
    os.environ[password_name] = secrets.token_urlsafe(32)
os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(32)
test_database_path = Path(
    os.environ.get(
        "OBE_TEST_DATABASE_PATH",
        str(Path(__file__).resolve().parents[1] / "obe_test.sqlite"),
    )
).resolve()
if test_database_path.exists():
    test_database_path.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{test_database_path.as_posix()}"
os.environ["CORS_ORIGINS"] = "http://testserver"

from app.config import settings
from app.db.base import Base
from app.db.session import engine, SessionLocal
from app.seeds.dev_seed import seed_database
from app.db.models import User


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Session-level fixture for isolated automated tests.
    Sets up SQLite tables and seed data strictly for tests without modifying
    or touching production PostgreSQL database.
    """
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not db.query(User).first():
            seed_database(db)
    yield
