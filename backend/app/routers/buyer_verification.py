"""
Buyer Verification — Phase 2.

Three trust tiers clearly displayed:
  PLATFORM_VERIFIED  — admin reviewed documents
  DOCUMENT_VERIFIED  — documents submitted, not yet reviewed
  SELF_DECLARED      — buyer filled in their own details
  PENDING            — nothing submitted yet

We never claim government verification.
"""
import datetime as dt
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_buyer, require_admin, get_current_user

router = APIRouter(prefix="/buyer-verification", tags=["buyer-verification"])

VALID_STATUSES = {"PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED", "SUSPENDED"}

# ---------------------------------------------------------------------------
# Display mapping -- CropRetain's own 5-state internal model (above) mapped to
# the 4 canonical, precisely-worded tiers used everywhere a human reads a
# buyer's trust status: marketplace cards, AgriAdvisor, and this buyer's own
# verification page. This is the ONE place that mapping is defined so every
# surface says the same thing. We never claim government/eNAM verification --
# "PLATFORM_VERIFIED" means CropRetain's own admin reviewed the evidence.
DISPLAY_STATUS = {
    "PENDING":       "INSUFFICIENT_VERIFICATION_EVIDENCE",
    "UNDER_REVIEW":  "SELF_DECLARED",
    "VERIFIED":      "PLATFORM_VERIFIED",
    "REJECTED":      "VERIFICATION_REJECTED",
    # No dedicated "suspended" tier in the 4-state model; a suspended buyer
    # must not keep showing as verified, so it displays as rejected while
    # the real SUSPENDED value is preserved internally for admin/audit use.
    "SUSPENDED":     "VERIFICATION_REJECTED",
}
DISPLAY_LABEL = {
    "INSUFFICIENT_VERIFICATION_EVIDENCE": "Insufficient Verification Evidence",
    "SELF_DECLARED": "Self-Declared",
    "PLATFORM_VERIFIED": "Platform Verified",
    "VERIFICATION_REJECTED": "Verification Rejected",
}
DISPLAY_DESCRIPTION = {
    "INSUFFICIENT_VERIFICATION_EVIDENCE": "Not enough verification evidence has been submitted yet.",
    "SELF_DECLARED": "Information was submitted by the buyer but has not yet been independently verified by CropRetain.",
    "PLATFORM_VERIFIED": "Buyer information and submitted evidence were reviewed by CropRetain.",
    "VERIFICATION_REJECTED": "The submitted evidence was reviewed and was not accepted.",
}


def display_info(verification: "models.BuyerVerification | None") -> dict:
    """Never 404s, never invents evidence: no row -> INSUFFICIENT_VERIFICATION_EVIDENCE."""
    internal = verification.verification_status if verification else "PENDING"
    status = DISPLAY_STATUS.get(internal, "INSUFFICIENT_VERIFICATION_EVIDENCE")
    return {
        "status": status,
        "label": DISPLAY_LABEL[status],
        "description": DISPLAY_DESCRIPTION[status],
    }


def _record_audit(db: Session, buyer_id: int, old_status: str, new_status: str, admin_email: str, note: str = ""):
    db.add(models.BuyerVerificationAuditLog(
        buyer_id=buyer_id, old_status=old_status, new_status=new_status,
        reviewer_admin_id=admin_email, note=note,
    ))


def _out(v: models.BuyerVerification) -> dict:
    out = schemas.BuyerVerificationOut.model_validate(v).model_dump()
    info = display_info(v)
    out["display_status"] = info["status"]
    out["display_label"] = info["label"]
    out["display_description"] = info["description"]
    return out


def _public_out(v: models.BuyerVerification) -> dict:
    """Public-safe view: display tier only (see BuyerVerificationPublicOut).
    verified_at is shown only while the buyer is actually Platform Verified --
    reject/suspend do not clear it, so it must not leak for other tiers."""
    info = display_info(v)
    return {
        "buyer_id": v.buyer_id,
        "display_status": info["status"],
        "display_label": info["label"],
        "display_description": info["description"],
        "verified_at": v.verified_at if info["status"] == "PLATFORM_VERIFIED" else None,
    }


# ---------------------------------------------------------------------------
# Buyer — submit / view own verification
# ---------------------------------------------------------------------------

@router.post("", response_model=schemas.BuyerVerificationOut)
def submit_verification(
    payload: schemas.BuyerVerificationCreate,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.BuyerVerification)
        .filter(models.BuyerVerification.buyer_id == buyer.id)
        .first()
    )
    if existing:
        # Update existing submission
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(existing, field, value)
        existing.submitted_at = dt.datetime.utcnow()
        # Re-opening a rejected/pending submission bumps it to UNDER_REVIEW
        if existing.verification_status in ("PENDING", "REJECTED"):
            existing.verification_status = "UNDER_REVIEW"
            existing.verification_method = (
                "DOCUMENT_VERIFIED" if payload.document_urls else "SELF_DECLARED"
            )
        db.commit()
        db.refresh(existing)
        return _out(existing)

    method = "DOCUMENT_VERIFIED" if payload.document_urls else "SELF_DECLARED"
    verification = models.BuyerVerification(
        buyer_id=buyer.id,
        business_name=payload.business_name,
        business_registration_number=payload.business_registration_number,
        gst_number=payload.gst_number,
        license_number=payload.license_number,
        document_urls=payload.document_urls,
        verification_status="UNDER_REVIEW",
        verification_method=method,
        submitted_at=dt.datetime.utcnow(),
    )
    db.add(verification)
    db.commit()
    db.refresh(verification)
    return _out(verification)


@router.get("/me", response_model=schemas.BuyerVerificationOut)
def my_verification(
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer.id).first()
    if not v:
        raise HTTPException(status_code=404, detail="No verification submission found. Submit one first.")
    return _out(v)


@router.get("/{buyer_id}", response_model=schemas.BuyerVerificationPublicOut)
def get_buyer_verification(
    buyer_id: int,
    db: Session = Depends(get_db),
):
    """Public endpoint -- anyone can see a buyer's verification DISPLAY tier.
    Documents, GST/licence/registration numbers, admin notes, reviewer
    identity and the raw internal status are never returned here (they remain
    available to the buyer via /me and to admins via the list endpoint)."""
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="No verification record for this buyer")
    return _public_out(v)


@router.get("/{buyer_id}/badge")
def get_buyer_verification_badge(buyer_id: int, db: Session = Depends(get_db)):
    """Public, never 404s -- for marketplace/buyer-card display. A buyer who
    has never submitted anything correctly shows Insufficient Verification
    Evidence rather than erroring or silently showing nothing."""
    buyer = db.query(models.Buyer).filter(models.Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer_id).first()
    # `demo_seed` is a bare boolean so the UI can label seeded demonstration
    # records as demo instead of presenting them as a real platform review.
    return {"buyer_id": buyer_id, **display_info(v),
            "demo_seed": bool(v and v.reviewed_by == "demo-seed")}


# ---------------------------------------------------------------------------
# Admin — review and decide
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.BuyerVerificationOut])
def list_verifications(
    status: str = "UNDER_REVIEW",
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin only: list pending/under-review verifications."""
    q = db.query(models.BuyerVerification)
    if status:
        q = q.filter(models.BuyerVerification.verification_status == status)
    return q.order_by(models.BuyerVerification.created_at.asc()).all()


@router.patch("/{buyer_id}/approve")
def approve_verification(
    buyer_id: int,
    notes: str = "",
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="No verification record for this buyer")

    old_status = v.verification_status
    v.verification_status = "VERIFIED"
    v.verification_method = "PLATFORM_VERIFIED"
    v.verification_notes = notes
    v.verified_at = dt.datetime.utcnow()
    v.reviewed_at = v.verified_at
    v.reviewed_by = admin.get("username") if isinstance(admin, dict) else str(admin)
    v.rejected_reason = None

    # Mirror onto the Buyer row so the match engine sees it without a join
    buyer = db.query(models.Buyer).filter(models.Buyer.id == buyer_id).first()
    if buyer:
        buyer.verification_status = "verified"

    _record_audit(db, buyer_id, old_status, "VERIFIED", v.reviewed_by, notes)
    db.commit()
    return {"approved": True, "buyer_id": buyer_id}


@router.patch("/{buyer_id}/reject")
def reject_verification(
    buyer_id: int,
    reason: str = "Documents could not be verified",
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="No verification record for this buyer")

    old_status = v.verification_status
    v.verification_status = "REJECTED"
    v.rejected_reason = reason
    v.reviewed_at = dt.datetime.utcnow()
    reviewer = admin.get("username") if isinstance(admin, dict) else str(admin)
    v.reviewed_by = reviewer

    buyer = db.query(models.Buyer).filter(models.Buyer.id == buyer_id).first()
    if buyer:
        buyer.verification_status = "pending"

    _record_audit(db, buyer_id, old_status, "REJECTED", reviewer, reason)
    db.commit()
    return {"rejected": True, "buyer_id": buyer_id, "reason": reason}


@router.patch("/{buyer_id}/suspend")
def suspend_buyer(
    buyer_id: int,
    reason: str = "Suspended by admin",
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    v = db.query(models.BuyerVerification).filter(models.BuyerVerification.buyer_id == buyer_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="No verification record for this buyer")
    old_status = v.verification_status
    v.verification_status = "SUSPENDED"
    v.verification_notes = reason
    v.reviewed_at = dt.datetime.utcnow()
    reviewer = admin.get("username") if isinstance(admin, dict) else str(admin)
    v.reviewed_by = reviewer

    # Mirror onto the Buyer row, same as approve/reject -- without this, a
    # previously-verified buyer stays "verified" on the Buyer row (which is
    # the field the match engine and buyer-facing badges actually read),
    # so a suspended buyer would keep getting the verification bonus in
    # matching and keep showing a verified badge to farmers.
    buyer = db.query(models.Buyer).filter(models.Buyer.id == buyer_id).first()
    if buyer:
        buyer.verification_status = "pending"

    _record_audit(db, buyer_id, old_status, "SUSPENDED", reviewer, reason)
    db.commit()
    return {"suspended": True, "buyer_id": buyer_id}
