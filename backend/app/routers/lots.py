"""
Lot management — Phase 4.

Lots are the primary sellable unit: a proper agricultural lot with a lot
number, quality report, and full lifecycle status.  They coexist with the
existing CropListing system — a farmer can create a Lot directly (with an
optional link to an existing listing) or have one auto-created when they
post a listing.
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, get_current_user

router = APIRouter(prefix="/lots", tags=["lots"])

VALID_STATUSES = {"DRAFT", "AVAILABLE", "UNDER_OFFER", "SOLD", "IN_TRANSIT", "DELIVERED", "CANCELLED"}


def _next_lot_number(db: Session) -> str:
    """Generate sequential lot number CW-<YEAR>-<5-digit sequence>."""
    year = dt.date.today().year
    count = db.query(models.Lot).count()
    return f"CW-{year}-{count + 1:05d}"


@router.post("", response_model=schemas.LotOut)
def create_lot(
    payload: schemas.LotCreate,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    if payload.quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0 kg")
    if payload.expected_price <= 0:
        raise HTTPException(status_code=400, detail="Expected price must be greater than ₹0/kg")
    if payload.minimum_price and payload.minimum_price > payload.expected_price:
        raise HTTPException(status_code=400, detail="Minimum price cannot exceed expected price")

    lot = models.Lot(
        lot_number=_next_lot_number(db),
        farmer_id=farmer.id,
        fpo_id=payload.fpo_id,
        listing_id=payload.listing_id,
        crop=payload.crop,
        quantity_kg=payload.quantity_kg,
        grade=payload.grade,
        quality_score=payload.quality_score,
        quality_report=payload.quality_report,
        harvest_date=payload.harvest_date,
        available_date=payload.available_date or dt.date.today().isoformat(),
        location=payload.location or farmer.location,
        latitude=payload.latitude or farmer.latitude,
        longitude=payload.longitude or farmer.longitude,
        expected_price=payload.expected_price,
        minimum_price=payload.minimum_price,
        note=payload.note,
        status="AVAILABLE",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@router.get("", response_model=List[schemas.LotOut])
def list_lots(
    crop: Optional[str] = None,
    location: Optional[str] = None,
    grade: Optional[str] = None,
    status: str = "AVAILABLE",
    min_quantity_kg: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """Public endpoint — farmers and buyers can browse available lots."""
    q = db.query(models.Lot)
    if status:
        q = q.filter(models.Lot.status == status)
    if crop:
        q = q.filter(models.Lot.crop == crop)
    if location:
        q = q.filter(models.Lot.location == location)
    if grade:
        q = q.filter(models.Lot.grade == grade)
    if min_quantity_kg:
        q = q.filter(models.Lot.quantity_kg >= min_quantity_kg)
    return q.order_by(models.Lot.created_at.desc()).all()


@router.get("/mine", response_model=List[schemas.LotOut])
def my_lots(
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Lot)
        .filter(models.Lot.farmer_id == farmer.id)
        .order_by(models.Lot.created_at.desc())
        .all()
    )


@router.get("/{lot_id}", response_model=schemas.LotOut)
def get_lot(lot_id: int, db: Session = Depends(get_db)):
    lot = db.query(models.Lot).filter(models.Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return lot


@router.patch("/{lot_id}", response_model=schemas.LotOut)
def update_lot(
    lot_id: int,
    payload: schemas.LotUpdate,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    lot = db.query(models.Lot).filter(models.Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if lot.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="You can only edit your own lots")
    if lot.status in ("SOLD", "DELIVERED", "CANCELLED"):
        raise HTTPException(status_code=400, detail=f"Cannot edit a lot in {lot.status} status")
    if payload.status and payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(lot, field, value)
    db.commit()
    db.refresh(lot)
    return lot


@router.delete("/{lot_id}")
def cancel_lot(
    lot_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    lot = db.query(models.Lot).filter(models.Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if lot.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own lots")
    if lot.status in ("SOLD", "IN_TRANSIT", "DELIVERED"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel a lot in {lot.status} status")
    lot.status = "CANCELLED"
    db.commit()
    return {"cancelled": True, "lot_id": lot_id}
