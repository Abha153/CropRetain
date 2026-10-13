"""
Tests for login activity tracking (login_events table + last_login column).

Covers:
  - a successful /auth/login records a success event and updates last_login
  - a failed /auth/login against a real account records a failed event tied
    to that account's id/role (never the password)
  - a failed /auth/login against an unknown email records role="unknown",
    user_id=None -- never guesses or fabricates an identity
  - login_events rows never contain password/hash/token fields (structural
    guarantee: the model itself has no such column)
  - "unique users" counts distinct (role, user_id), so a farmer and a buyer
    that happen to share the same numeric id are correctly counted as two
    different people, not one
  - the new admin analytics endpoints are unreachable without an admin token

Uses an isolated in-memory SQLite database, mirroring the existing pattern
in test_market_router.py -- no shared state with the real cropwise.db.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.auth_utils import hash_password
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed one farmer and one buyer that deliberately share id=1 across
    # their two tables, to prove unique-user counting can't collide them.
    db = TestingSessionLocal()
    farmer = models.Farmer(
        name="Test Farmer", email="farmer@test.com",
        password_hash=hash_password("CorrectHorse1"),
        location="Bilaspur",
    )
    buyer = models.Buyer(
        company_name="Test Buyer Co", email="buyer@test.com",
        password_hash=hash_password("CorrectHorse2"),
        location="Raipur",
    )
    db.add(farmer)
    db.add(buyer)
    db.commit()
    db.close()

    yield TestClient(app), TestingSessionLocal
    app.dependency_overrides.clear()


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_successful_login_records_event_and_last_login(client):
    tc, SessionLocal = client
    resp = _login(tc, "farmer@test.com", "CorrectHorse1")
    assert resp.status_code == 200  # existing behavior unchanged

    db = SessionLocal()
    events = db.query(models.LoginEvent).all()
    assert len(events) == 1
    assert events[0].success is True
    assert events[0].role == "farmer"
    farmer = db.query(models.Farmer).filter_by(email="farmer@test.com").first()
    assert farmer.last_login is not None
    db.close()


def test_failed_login_against_real_account_identifies_user_not_password(client):
    tc, SessionLocal = client
    resp = _login(tc, "farmer@test.com", "WrongPassword")
    assert resp.status_code == 401  # existing behavior unchanged

    db = SessionLocal()
    events = db.query(models.LoginEvent).all()
    assert len(events) == 1
    assert events[0].success is False
    assert events[0].role == "farmer"
    farmer = db.query(models.Farmer).filter_by(email="farmer@test.com").first()
    assert events[0].user_id == farmer.id
    # last_login must NOT be touched by a failed attempt
    assert farmer.last_login is None
    # structural guarantee: LoginEvent has no column that could hold a
    # password, hash, token, or api key
    columns = {c.name for c in models.LoginEvent.__table__.columns}
    assert columns == {"id", "user_id", "role", "login_time", "success"}
    db.close()


def test_failed_login_unknown_email_does_not_guess_identity(client):
    tc, SessionLocal = client
    resp = _login(tc, "nobody@nowhere.com", "whatever")
    assert resp.status_code == 401

    db = SessionLocal()
    events = db.query(models.LoginEvent).all()
    assert len(events) == 1
    assert events[0].user_id is None
    assert events[0].role == "unknown"
    db.close()


def test_unique_users_distinguish_farmer_and_buyer_sharing_same_id(client):
    tc, SessionLocal = client
    _login(tc, "farmer@test.com", "CorrectHorse1")
    _login(tc, "buyer@test.com", "CorrectHorse2")
    _login(tc, "farmer@test.com", "CorrectHorse1")  # same farmer logs in again

    db = SessionLocal()
    # 3 successful events...
    assert db.query(models.LoginEvent).filter_by(success=True).count() == 3
    # ...but only 2 unique (role, user_id) people, computed the same way
    # app/routers/admin.py::user_activity does it.
    unique = (
        db.query(models.LoginEvent.role, models.LoginEvent.user_id)
        .filter(models.LoginEvent.success.is_(True))
        .distinct()
        .count()
    )
    assert unique == 2
    db.close()


def test_admin_endpoints_require_admin_role(client):
    tc, _ = client
    farmer_token = _login(tc, "farmer@test.com", "CorrectHorse1").json()["access_token"]
    for path in ("/admin/user-activity", "/admin/recent-activity", "/admin/users"):
        resp = tc.get(path, headers={"Authorization": f"Bearer {farmer_token}"})
        assert resp.status_code == 403
        resp_noauth = tc.get(path)
        assert resp_noauth.status_code == 401
