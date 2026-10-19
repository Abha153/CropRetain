"""
Tests for the opt-in DEMO accounts (app/demo_accounts.py) and the rules that
keep demo data out of production (app/demo_policy.py).

Pins down: no demo seeding in production, no default/weak password, idempotent
seeding, existing accounts never overwritten, the demo buyer is UNVERIFIED with
no verification record, simulated records are labelled DEMO, and the API tells
the UI which accounts are demo accounts.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo_accounts, models
from app.auth_utils import hash_password, verify_password
from app.database import Base, get_db
from app.demo_policy import (
    auto_seed_allowed, demo_accounts_allowed, demo_password_problem, is_demo_email,
)

PASSWORD = "a-long-test-password-1"


# ---------------------------------------------------------------- policy ----

@pytest.mark.parametrize("env,allowed", [
    ("development", True), ("", True), (None, True), ("staging", True),
    ("production", False), ("PRODUCTION", False), (" prod ", False),
])
def test_auto_seed_and_demo_accounts_are_blocked_only_in_production(env, allowed):
    assert auto_seed_allowed(env) is allowed
    assert demo_accounts_allowed(env) is allowed


@pytest.mark.parametrize("pw", [None, "", "short", "elevenchars"])
def test_missing_or_short_password_is_rejected_without_echoing_it(pw):
    problem = demo_password_problem(pw)
    assert problem and (not pw or pw not in problem)


def test_long_enough_password_is_accepted():
    assert demo_password_problem(PASSWORD) is None


@pytest.mark.parametrize("email,expected", [
    ("abha.tiwari@cropretain.demo", True), ("ramesh@cropwise.demo", True),
    ("ABHA@CROPRETAIN.DEMO", True), ("real.farmer@gmail.com", False),
    ("demo@example.com", False), ("", False), (None, False),
])
def test_is_demo_email(email, expected):
    assert is_demo_email(email) is expected


def test_main_refuses_in_production_and_without_password(monkeypatch, capsys):
    from app.config import settings
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "demo_account_password", PASSWORD)
    assert demo_accounts.main() == 2
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "demo_account_password", "")
    assert demo_accounts.main() == 2
    out = capsys.readouterr()
    assert PASSWORD not in out.out + out.err


# --------------------------------------------------------------- seeding ----

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_seed_creates_both_accounts_and_labelled_sample_records(db):
    result = demo_accounts.seed_demo_accounts(db, PASSWORD)
    assert "farmer Abha Tiwari" in result["created"] and "buyer Preeti Tiwari" in result["created"]

    abha = db.query(models.Farmer).filter_by(email=demo_accounts.ABHA_EMAIL).one()
    preeti = db.query(models.Buyer).filter_by(email=demo_accounts.PREETI_EMAIL).one()
    assert abha.name == "Abha Tiwari" and abha.location == "Bilaspur"
    assert "Preeti Tiwari" in preeti.company_name and preeti.location == "Bilaspur"

    # Passwords are hashed, never stored as given.
    assert abha.password_hash != PASSWORD and verify_password(PASSWORD, abha.password_hash)
    assert verify_password(PASSWORD, preeti.password_hash)

    # The demo buyer is unverified and has no verification record.
    assert preeti.verification_status == "pending"
    assert db.query(models.BuyerVerification).filter_by(buyer_id=preeti.id).first() is None

    listing = db.query(models.CropListing).filter_by(farmer_id=abha.id).one()
    demand = db.query(models.BuyerDemand).filter_by(buyer_id=preeti.id).one()
    offer = db.query(models.BuyerOffer).filter_by(buyer_id=preeti.id).one()
    assert "DEMO" in listing.note and "DEMO" in demand.additional_requirements and "DEMO" in offer.message
    assert offer.listing_id == listing.id


def test_seed_is_idempotent(db):
    demo_accounts.seed_demo_accounts(db, PASSWORD)
    counts = lambda: (db.query(models.Farmer).count(), db.query(models.Buyer).count(),
                      db.query(models.CropListing).count(), db.query(models.BuyerDemand).count(),
                      db.query(models.BuyerOffer).count())
    before = counts()
    again = demo_accounts.seed_demo_accounts(db, PASSWORD)
    assert counts() == before == (1, 1, 1, 1, 1)
    assert again["created"] == [] and len(again["existing"]) == 2


def test_existing_account_is_never_overwritten(db):
    original = hash_password("the-real-owners-own-password")
    db.add(models.Farmer(name="Someone Else", email=demo_accounts.ABHA_EMAIL,
                         password_hash=original, location="Raipur"))
    db.commit()
    demo_accounts.seed_demo_accounts(db, PASSWORD)
    abha = db.query(models.Farmer).filter_by(email=demo_accounts.ABHA_EMAIL).one()
    assert abha.password_hash == original and abha.name == "Someone Else"
    assert not verify_password(PASSWORD, abha.password_hash)


def test_seed_does_not_touch_other_users(db):
    db.add(models.Farmer(name="Real Farmer", email="real@example.com",
                         password_hash=hash_password("x" * 12), location="Durg"))
    db.commit()
    demo_accounts.seed_demo_accounts(db, PASSWORD)
    assert db.query(models.Farmer).filter_by(email="real@example.com").count() == 1


# ------------------------------------------------------------- API flags ----

@pytest.fixture()
def client(db):
    from app.main import app

    def _override():
        yield db

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_login_reports_demo_flag_and_roles_stay_separate(client, db):
    demo_accounts.seed_demo_accounts(db, PASSWORD)
    db.add(models.Farmer(name="Real Farmer", email="real@example.com",
                         password_hash=hash_password("another-long-pass"), location="Durg"))
    db.commit()

    farmer = _login(client, demo_accounts.ABHA_EMAIL, PASSWORD).json()
    buyer = _login(client, demo_accounts.PREETI_EMAIL, PASSWORD).json()
    real = _login(client, "real@example.com", "another-long-pass").json()

    assert farmer["role"] == "farmer" and farmer["user"]["is_demo"] is True
    assert buyer["role"] == "buyer" and buyer["user"]["is_demo"] is True
    assert buyer["user"]["verification_status"] == "pending"
    assert real["user"]["is_demo"] is False
    assert _login(client, demo_accounts.ABHA_EMAIL, "wrong-password-here").status_code == 401


# ------------------------------------------- verification badge honesty ----

def test_badge_marks_seeded_demo_verification_but_not_real_review_or_unverified(client, db):
    from app.seed_data import ensure_demo_buyer_verification_records

    seeded = models.Buyer(company_name="Seeded Demo", email="seeded@cropwise.demo",
                          password_hash="x", location="Raipur", verification_status="verified")
    real = models.Buyer(company_name="Real Co", email="real@co.example",
                        password_hash="x", location="Raipur", verification_status="pending")
    db.add_all([seeded, real])
    db.commit()
    assert ensure_demo_buyer_verification_records(db=db, demo_emails={seeded.email}) == 1
    db.add(models.BuyerVerification(buyer_id=real.id, verification_status="VERIFIED",
                                    reviewed_by="admin@real.example"))
    db.commit()
    demo_accounts.seed_demo_accounts(db, PASSWORD)
    preeti = db.query(models.Buyer).filter_by(email=demo_accounts.PREETI_EMAIL).one()

    s = client.get(f"/buyer-verification/{seeded.id}/badge").json()
    r = client.get(f"/buyer-verification/{real.id}/badge").json()
    p = client.get(f"/buyer-verification/{preeti.id}/badge").json()
    assert s["demo_seed"] is True
    assert r["demo_seed"] is False and r["status"] == "PLATFORM_VERIFIED"
    assert p["demo_seed"] is False and p["status"] == "INSUFFICIENT_VERIFICATION_EVIDENCE"
