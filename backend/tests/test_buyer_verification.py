"""
Tests for the buyer verification workflow (app/routers/buyer_verification.py).

CropRetain is not integrated with eNAM or any government license-verification
API -- PLATFORM_VERIFIED means "CropRetain's own admin reviewed the evidence",
nothing more. These tests check the mapping from the existing 5-state
internal model to the 4 canonical display tiers, the submit -> approve/
reject workflow, and that the audit log actually gets written.

Run: pytest backend/tests/test_buyer_verification.py -v
"""
import os
import sys

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models, schemas
from app.database import Base
from app.auth_utils import require_admin
from app.routers import buyer_verification as bv_router


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_buyer(db, email="buyer@example.com"):
    b = models.Buyer(company_name="Test Traders", email=email, password_hash="x", location="Bilaspur")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


ADMIN = {"user": {"username": "admin@cropwise.demo"}, "role": "admin"}


# ─── display mapping: the ONE place the 4 tiers are defined ────────────────

def test_display_mapping_covers_every_internal_state():
    expected = {
        "PENDING": "INSUFFICIENT_VERIFICATION_EVIDENCE",
        "UNDER_REVIEW": "SELF_DECLARED",
        "VERIFIED": "PLATFORM_VERIFIED",
        "REJECTED": "VERIFICATION_REJECTED",
        "SUSPENDED": "VERIFICATION_REJECTED",
    }
    for internal, expected_display in expected.items():
        assert bv_router.DISPLAY_STATUS[internal] == expected_display

    # every display label is CropRetain's own wording, never a government claim
    for label in bv_router.DISPLAY_LABEL.values():
        for banned in ("Government", "eNAM", "Licensed", "Certified"):
            assert banned not in label


def test_no_row_displays_as_insufficient_evidence():
    info = bv_router.display_info(None)
    assert info["status"] == "INSUFFICIENT_VERIFICATION_EVIDENCE"
    assert info["label"] == "Insufficient Verification Evidence"


# ─── new buyer defaults ──────────────────────────────────────────────────────

def test_new_buyer_has_no_verification_row_and_badge_is_insufficient(db):
    buyer = _make_buyer(db)
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer.id).first()
    assert v is None   # nothing submitted yet -- this IS the default state

    badge = bv_router.get_buyer_verification_badge(buyer.id, db)
    assert badge["status"] == "INSUFFICIENT_VERIFICATION_EVIDENCE"
    assert badge["status"] != "PLATFORM_VERIFIED"   # a new buyer can never appear verified


# ─── submit -> SELF_DECLARED ─────────────────────────────────────────────────

def test_submit_moves_to_self_declared_with_server_timestamp(db):
    buyer = _make_buyer(db)
    payload = schemas.BuyerVerificationCreate(business_name="Test Traders Pvt Ltd")

    result = bv_router.submit_verification(payload, buyer, db)

    assert result["display_status"] == "SELF_DECLARED"
    assert result["verification_status"] == "UNDER_REVIEW"   # real internal state
    assert result["submitted_at"] is not None
    assert result["reviewed_at"] is None                      # not reviewed by anyone yet


# ─── admin approve -> PLATFORM_VERIFIED, with audit log ─────────────────────

def test_admin_approve_sets_platform_verified_and_writes_audit_log(db):
    buyer = _make_buyer(db)
    bv_router.submit_verification(schemas.BuyerVerificationCreate(business_name="Test Traders"), buyer, db)

    result = bv_router.approve_verification(buyer.id, "Docs check out", ADMIN["user"], db)
    assert result["approved"] is True

    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer.id).first()
    assert v.verification_status == "VERIFIED"
    assert v.reviewed_at is not None
    assert v.reviewed_by == "admin@cropwise.demo"

    db.refresh(buyer)
    assert buyer.verification_status == "verified"   # mirrored for the match engine

    badge = bv_router.get_buyer_verification_badge(buyer.id, db)
    assert badge["status"] == "PLATFORM_VERIFIED"

    log = db.query(models.BuyerVerificationAuditLog).filter(
        models.BuyerVerificationAuditLog.buyer_id == buyer.id
    ).order_by(models.BuyerVerificationAuditLog.id.desc()).first()
    assert log is not None
    assert log.old_status == "UNDER_REVIEW"
    assert log.new_status == "VERIFIED"
    assert log.reviewer_admin_id == "admin@cropwise.demo"
    assert log.note == "Docs check out"


def test_admin_reject_sets_verification_rejected_and_writes_audit_log(db):
    buyer = _make_buyer(db)
    bv_router.submit_verification(schemas.BuyerVerificationCreate(business_name="Test Traders"), buyer, db)

    bv_router.reject_verification(buyer.id, "GST number could not be matched", ADMIN["user"], db)

    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer.id).first()
    assert v.verification_status == "REJECTED"
    assert v.reviewed_by == "admin@cropwise.demo"

    badge = bv_router.get_buyer_verification_badge(buyer.id, db)
    assert badge["status"] == "VERIFICATION_REJECTED"

    log = db.query(models.BuyerVerificationAuditLog).filter(
        models.BuyerVerificationAuditLog.buyer_id == buyer.id
    ).order_by(models.BuyerVerificationAuditLog.id.desc()).first()
    assert log.new_status == "REJECTED"
    assert log.note == "GST number could not be matched"


# ─── a buyer can never set their own status to PLATFORM_VERIFIED ───────────

def test_buyer_submission_never_sets_verified_directly(db):
    buyer = _make_buyer(db)
    # No field in BuyerVerificationCreate can set verification_status at all --
    # confirm the schema genuinely has no such field, so there is no way for
    # a buyer's own submission payload to force VERIFIED.
    assert "verification_status" not in schemas.BuyerVerificationCreate.model_fields

    result = bv_router.submit_verification(schemas.BuyerVerificationCreate(business_name="X"), buyer, db)
    assert result["verification_status"] != "VERIFIED"
    assert result["display_status"] != "PLATFORM_VERIFIED"


def test_only_admin_role_passes_require_admin():
    with pytest.raises(HTTPException) as exc:
        require_admin({"role": "buyer", "user": {"id": 1}})
    assert exc.value.status_code == 403

    # admin role passes through
    assert require_admin({"role": "admin", "user": {"username": "a"}}) == {"username": "a"}


# ─── resubmission after rejection re-opens as SELF_DECLARED, not silently verified ─

def test_resubmission_after_rejection_returns_to_self_declared(db):
    buyer = _make_buyer(db)
    bv_router.submit_verification(schemas.BuyerVerificationCreate(business_name="Test Traders"), buyer, db)
    bv_router.reject_verification(buyer.id, "Missing GST", ADMIN["user"], db)

    result = bv_router.submit_verification(
        schemas.BuyerVerificationCreate(business_name="Test Traders", gst_number="27AAAAA0000A1Z5"), buyer, db
    )
    assert result["display_status"] == "SELF_DECLARED"
    assert result["verification_status"] == "UNDER_REVIEW"
