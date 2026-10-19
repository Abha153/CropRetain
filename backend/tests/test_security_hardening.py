"""
Production-safety tests: admin credentials, demo seeding, and demo
"verification". Real JWT/auth stack on in-memory SQLite, like the other
router tests.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.config import settings
from app.database import Base, get_db
from app.seed_data import ensure_demo_buyer_verification_records
from app.services.trust_summary import build_trust_summary

DEFAULT_USER, DEFAULT_PASS = "admin", "cropwise-admin-demo-2026"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    from app.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _admin_login(client, user, password):
    return client.post("/auth/admin/login", data={"username": user, "password": password})


def test_default_admin_credentials_still_work_outside_production(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "admin_username", DEFAULT_USER)
    monkeypatch.setattr(settings, "admin_password", DEFAULT_PASS)
    assert _admin_login(client, DEFAULT_USER, DEFAULT_PASS).status_code == 200


def test_production_refuses_default_admin_credentials(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_username", DEFAULT_USER)
    monkeypatch.setattr(settings, "admin_password", DEFAULT_PASS)
    r = _admin_login(client, DEFAULT_USER, DEFAULT_PASS)
    assert r.status_code == 503 and r.json()["code"] == "ADMIN_NOT_CONFIGURED"


def test_production_accepts_configured_admin_credentials_and_rejects_wrong_ones(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "admin_username", "ops-admin")
    monkeypatch.setattr(settings, "admin_password", "a-real-long-secret-1")
    assert _admin_login(client, "ops-admin", "a-real-long-secret-1").status_code == 200
    assert _admin_login(client, "ops-admin", "wrong").status_code == 401
    assert _admin_login(client, DEFAULT_USER, DEFAULT_PASS).status_code == 401


def test_empty_admin_password_never_logs_in(client, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "admin_username", "ops-admin")
    monkeypatch.setattr(settings, "admin_password", "")
    assert _admin_login(client, "ops-admin", "").status_code == 401


def test_seeded_demo_verification_does_not_count_as_verified_in_trust_summary(db):
    demo = models.Buyer(company_name="Demo Buyer", email="d@cropwise.demo", password_hash="x",
                        location="Raipur", verification_status="verified")
    real = models.Buyer(company_name="Real Buyer", email="r@real.example", password_hash="x",
                        location="Raipur", verification_status="pending")
    db.add_all([demo, real])
    db.commit()
    assert ensure_demo_buyer_verification_records(db=db, demo_emails={demo.email}) == 1
    db.add(models.BuyerVerification(buyer_id=real.id, verification_status="VERIFIED",
                                    verification_method="PLATFORM_VERIFIED", reviewed_by="admin@real.example"))
    db.commit()

    d = build_trust_summary(db, "buyer", demo.id)
    r = build_trust_summary(db, "buyer", real.id)
    assert d["verification"]["state"] == "NOT_VERIFIED" and d["verification"]["tier"] == "DEMO_SEED"
    assert "VERIFIED" not in d["badges"] and "NOT_VERIFIED" in d["flags"]
    assert r["verification"]["state"] == "VERIFIED" and "VERIFIED" in r["badges"]
