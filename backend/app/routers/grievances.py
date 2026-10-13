"""
Grievance / Dispute system — Phase 13.

Any party to a transaction can raise a grievance.
Admin resolves.
Every status change is recorded in the transaction timeline.
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, require_buyer, require_admin, get_current_user
from app.routers.transactions import _add_event

router = APIRouter(prefix="/grievances", tags=["grievances"])

VALID_CATEGORIES = {
    "PAYMENT", "QUALITY", "QUANTITY", "PRICE",
    "DELIVERY", "LOGISTICS", "BUYER", "FARMER", "OTHER"
}
VALID_STATUSES = {
    "OPEN", "UNDER_REVIEW", "WAITING_FOR_EVIDENCE", "RESOLVED", "REJECTED", "CLOSED"
}
VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH"}


@router.post("", response_model=schemas.GrievanceOut)
def raise_grievance(
    payload: schemas.GrievanceCreate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = current["role"]
    if role not in ("farmer", "buyer"):
        raise HTTPException(status_code=403, detail="Only farmers or buyers can raise grievances")

    user = current["user"]

    if payload.category.upper() not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")

    # Validate transaction ownership if provided
    if payload.transaction_id:
        txn = db.query(models.Transaction).filter(
            models.Transaction.id == payload.transaction_id
        ).first()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")
        if role == "farmer" and txn.farmer_id != user.id:
            raise HTTPException(status_code=403, detail="You can only raise grievances on your own transactions")
        if role == "buyer" and txn.buyer_id != user.id:
            raise HTTPException(status_code=403, detail="You can only raise grievances on your own transactions")

    grievance = models.Grievance(
        transaction_id=payload.transaction_id,
        raised_by=role,
        raised_by_id=user.id,
        against_user=payload.against_user,
        against_user_id=payload.against_user_id,
        category=payload.category.upper(),
        description=payload.description,
        evidence_urls=payload.evidence_urls,
        status="OPEN",
        priority=payload.priority.upper() if payload.priority else "MEDIUM",
    )
    db.add(grievance)
    db.flush()

    # Record in transaction timeline if linked
    if payload.transaction_id:
        _add_event(
            db, payload.transaction_id,
            "GRIEVANCE_RAISED",
            f"Grievance raised by {role}: {payload.category} — {payload.description[:80]}",
            role, user.id,
        )

    db.commit()
    db.refresh(grievance)
    return grievance


@router.get("/mine", response_model=List[schemas.GrievanceOut])
def my_grievances(current=Depends(get_current_user), db: Session = Depends(get_db)):
    role = current["role"]
    user = current["user"]
    if role not in ("farmer", "buyer"):
        return []
    return (
        db.query(models.Grievance)
        .filter(models.Grievance.raised_by == role,
                models.Grievance.raised_by_id == user.id)
        .order_by(models.Grievance.created_at.desc())
        .all()
    )


@router.get("/{grievance_id}", response_model=schemas.GrievanceOut)
def get_grievance(
    grievance_id: int,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    grievance = db.query(models.Grievance).filter(models.Grievance.id == grievance_id).first()
    if not grievance:
        raise HTTPException(status_code=404, detail="Grievance not found")
    role = current["role"]
    user = current["user"]
    if role == "admin":
        return grievance
    # Must be the raiser or the party the grievance is against
    if role not in ("farmer", "buyer"):
        raise HTTPException(status_code=403, detail="Access denied")
    if not (
        (grievance.raised_by == role and grievance.raised_by_id == user.id) or
        (grievance.against_user == role and grievance.against_user_id == user.id)
    ):
        raise HTTPException(status_code=403, detail="Access denied")
    return grievance


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.GrievanceOut])
def list_grievances(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(models.Grievance)
    if status:
        q = q.filter(models.Grievance.status == status.upper())
    if category:
        q = q.filter(models.Grievance.category == category.upper())
    if priority:
        q = q.filter(models.Grievance.priority == priority.upper())
    return q.order_by(models.Grievance.created_at.desc()).limit(limit).all()


@router.patch("/{grievance_id}", response_model=schemas.GrievanceOut)
def update_grievance(
    grievance_id: int,
    payload: schemas.GrievanceUpdate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Admin can update any field.
    Farmers/buyers can only add evidence (status changes by admin).
    """
    grievance = db.query(models.Grievance).filter(models.Grievance.id == grievance_id).first()
    if not grievance:
        raise HTTPException(status_code=404, detail="Grievance not found")

    role = current["role"]
    user = current["user"]

    if role == "admin":
        # Admin can change status, resolution, priority, assigned_to
        if payload.status and payload.status.upper() not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status")
        if payload.status:
            old_status = grievance.status
            grievance.status = payload.status.upper()
            if payload.status.upper() in ("RESOLVED", "CLOSED"):
                grievance.resolved_at = dt.datetime.utcnow()
                if grievance.transaction_id:
                    _add_event(
                        db, grievance.transaction_id,
                        "GRIEVANCE_RESOLVED",
                        f"Grievance {grievance_id} resolved: {payload.resolution or 'resolved by admin'}",
                        "admin", None,
                    )
        if payload.resolution:
            grievance.resolution = payload.resolution
        if payload.priority:
            grievance.priority = payload.priority.upper()
        if payload.assigned_to:
            grievance.assigned_to = payload.assigned_to
    else:
        # Non-admin: only raiser can add evidence URL (PUT body would extend evidence_urls)
        if not (grievance.raised_by == role and grievance.raised_by_id == user.id):
            raise HTTPException(status_code=403, detail="Access denied")
        if grievance.status in ("RESOLVED", "CLOSED", "REJECTED"):
            raise HTTPException(status_code=400, detail=f"Cannot update a {grievance.status} grievance")
        # Only allow bumping to WAITING_FOR_EVIDENCE when re-submitting
        if payload.status and payload.status.upper() == "WAITING_FOR_EVIDENCE":
            grievance.status = "WAITING_FOR_EVIDENCE"

    grievance.updated_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(grievance)
    return grievance
