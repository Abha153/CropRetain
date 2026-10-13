from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, get_current_user

router = APIRouter(prefix="/listings", tags=["listings"])


@router.post("", response_model=schemas.ListingOut)
def create_listing(payload: schemas.ListingCreate, farmer: models.Farmer = Depends(require_farmer),
                    db: Session = Depends(get_db)):
    listing = models.CropListing(
        farmer_id=farmer.id,
        crop=payload.crop,
        quantity_kg=payload.quantity_kg,
        quality_grade=payload.quality_grade,
        quality_score=payload.quality_score,
        expected_price_per_kg=payload.expected_price_per_kg,
        location=payload.location or farmer.location,
        available_date=payload.available_date,
        min_acceptable_price=payload.min_acceptable_price,
        bidding_deadline=payload.bidding_deadline,
        image_note=payload.image_note,
        note=payload.note,
        language=payload.language,
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


@router.get("", response_model=List[schemas.ListingOut])
def list_listings(crop: Optional[str] = None, location: Optional[str] = None,
                   min_quantity_kg: Optional[float] = None, quality_grade: Optional[str] = None,
                   status: str = "active", db: Session = Depends(get_db)):
    q = db.query(models.CropListing).filter(models.CropListing.status == status)
    if crop:
        q = q.filter(models.CropListing.crop == crop)
    if location:
        q = q.filter(models.CropListing.location == location)
    if quality_grade:
        q = q.filter(models.CropListing.quality_grade == quality_grade)
    if min_quantity_kg:
        q = q.filter(models.CropListing.quantity_kg >= min_quantity_kg)
    return q.order_by(models.CropListing.created_at.desc()).all()


@router.get("/mine", response_model=List[schemas.ListingOut])
def my_listings(farmer: models.Farmer = Depends(require_farmer), db: Session = Depends(get_db)):
    return (
        db.query(models.CropListing)
        .filter(models.CropListing.farmer_id == farmer.id)
        .order_by(models.CropListing.created_at.desc())
        .all()
    )


@router.get("/{listing_id}", response_model=schemas.ListingOut)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(models.CropListing).filter(models.CropListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.patch("/{listing_id}/status", response_model=schemas.ListingOut)
def update_listing_status(listing_id: int, new_status: str,
                           farmer: models.Farmer = Depends(require_farmer),
                           db: Session = Depends(get_db)):
    listing = db.query(models.CropListing).filter(models.CropListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="You can only edit your own listings")
    if new_status not in ("active", "sold", "expired"):
        raise HTTPException(status_code=400, detail="Invalid status")
    listing.status = new_status
    db.commit()
    db.refresh(listing)
    return listing


@router.delete("/{listing_id}")
def delete_listing(listing_id: int, farmer: models.Farmer = Depends(require_farmer),
                    db: Session = Depends(get_db)):
    listing = db.query(models.CropListing).filter(models.CropListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="You can only delete your own listings")
    db.delete(listing)
    db.commit()
    return {"deleted": True}
