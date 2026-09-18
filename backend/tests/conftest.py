"""Pytest Configuration and Fixtures for Fraud Detection Test Suite."""
import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Use an isolated SQLite database file for testing
TEST_DB_PATH = BACKEND_DIR / "test_suite.db"
if TEST_DB_PATH.exists():
    try:
        TEST_DB_PATH.unlink()
    except Exception:
        pass

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.fraud import create_user, get_user_by_email
from app.db.session import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import *
from app.services.rules_engine import seed_default_rules


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Initializes the database schema and seeds rules once per test session."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    seed_default_rules(db)
    
    # Create standard test roles
    if not get_user_by_email(db, "admin@testsuite.io"):
        create_user(db, "admin@testsuite.io", "Passw0rd123!", "Admin Tester", "admin")
    if not get_user_by_email(db, "analyst@testsuite.io"):
        create_user(db, "analyst@testsuite.io", "Passw0rd123!", "Analyst Tester", "analyst")
    if not get_user_by_email(db, "manager@testsuite.io"):
        create_user(db, "manager@testsuite.io", "Passw0rd123!", "Manager Tester", "business_manager")

    db.close()
    yield
    # Teardown
    try:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
    except Exception:
        pass


@pytest.fixture(scope="function")
def db():
    """Yields a database session for unit/component testing."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client():
    """Yields a FastAPI TestClient instance."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token(client):
    """Returns a valid JWT token for the admin user."""
    r = client.post("/api/auth/login", json={"email": "admin@testsuite.io", "password": "Passw0rd123!"})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def analyst_token(client):
    """Returns a valid JWT token for the analyst user."""
    r = client.post("/api/auth/login", json={"email": "analyst@testsuite.io", "password": "Passw0rd123!"})
    assert r.status_code == 200, f"Analyst login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    """Authorization headers for admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def analyst_headers(analyst_token):
    """Authorization headers for analyst."""
    return {"Authorization": f"Bearer {analyst_token}"}


@pytest.fixture(scope="session")
def merchant_api_key(client, admin_headers):
    """Creates an API client for external merchant ingestion."""
    r = client.post("/api/auth/api-clients", json={"name": "TestSuite Merchant"}, headers=admin_headers)
    assert r.status_code == 201, f"Failed to create API client: {r.text}"
    return r.json()["api_key"]


@pytest.fixture(scope="session")
def merchant_headers(merchant_api_key):
    """Headers for API key ingestion."""
    return {"X-API-Key": merchant_api_key}
