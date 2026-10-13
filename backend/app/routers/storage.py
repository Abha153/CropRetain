"""
Phase 6 — Storage Marketplace
Farmers can browse, compare, and book storage facilities.
All demo facilities are clearly labelled is_demo=True.
"""
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, require_admin

router = APIRouter(prefix="/storage", tags=["storage"])


# ─── helpers ────────────────────────────────────────────────────────────────

def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Approximate great-circle distance in km."""
    import math
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── facilities ─────────────────────────────────────────────────────────────

@router.get("/facilities")
def list_facilities(
    crop: Optional[str] = Query(None),
    facility_type: Optional[str] = Query(None),
    min_capacity: Optional[float] = Query(None),
    db: Session = Depends(get_db),
):
    """Browse available storage facilities.  All demo facilities are clearly labelled."""
    q = db.query(models.StorageFacility).filter(models.StorageFacility.status == "ACTIVE")
    if facility_type:
        q = q.filter(models.StorageFacility.facility_type == facility_type)
    if min_capacity:
        q = q.filter(models.StorageFacility.available_capacity_kg >= min_capacity)
    facilities = q.all()

    result = []
    for f in facilities:
        # If crop filter is applied and crop_types is set, check compatibility
        if crop and f.crop_types:
            if crop not in f.crop_types and "All" not in f.crop_types:
                continue
        result.append(_facility_dict(f))
    return result


@router.get("/facilities/{facility_id}")
def get_facility(facility_id: int, db: Session = Depends(get_db)):
    f = db.query(models.StorageFacility).filter(models.StorageFacility.id == facility_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Storage facility not found")
    return _facility_dict(f)


def _facility_dict(f: models.StorageFacility) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "facility_type": f.facility_type,
        "location": f.location,
        "latitude": f.latitude,
        "longitude": f.longitude,
        "capacity_kg": f.capacity_kg,
        "available_capacity_kg": f.available_capacity_kg,
        "utilisation_pct": round((1 - f.available_capacity_kg / max(f.capacity_kg, 1)) * 100, 1),
        "price_per_kg_per_day": f.price_per_kg_per_day,
        "crop_types": f.crop_types or [],
        "temperature_controlled": f.temperature_controlled,
        "warehouse_features": f.warehouse_features or [],
        "quality_services": f.quality_services or [],
        "contact": f.contact,
        "verification_status": f.verification_status,
        "status": f.status,
        "is_demo": f.is_demo,
        "demo_disclaimer": (
            "⚠️ Demo / Sample Facility — availability and pricing are illustrative only, "
            "not real-time government or verified warehouse data."
        ) if f.is_demo else None,
    }


# ─── cost estimator (no auth required) ─────────────────────────────────────

@router.get("/estimate")
def estimate_cost(
    facility_id: int,
    quantity_kg: float = Query(..., gt=0),
    days: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    f = db.query(models.StorageFacility).filter(models.StorageFacility.id == facility_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Facility not found")
    cost = round(quantity_kg * f.price_per_kg_per_day * days, 2)
    return {
        "facility_id": facility_id,
        "facility_name": f.name,
        "quantity_kg": quantity_kg,
        "days": days,
        "price_per_kg_per_day": f.price_per_kg_per_day,
        "estimated_cost": cost,
        "is_demo": f.is_demo,
    }


# ─── bookings ────────────────────────────────────────────────────────────────

@router.post("/bookings")
def create_booking(
    payload: schemas.StorageBookingCreate,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Farmer requests a storage booking."""
    facility_id = payload.storage_facility_id
    quantity_kg = payload.quantity_kg  # already validated > 0 by the schema (Field(gt=0))
    start_date = payload.start_date
    end_date = payload.end_date
    lot_id = payload.lot_id

    if lot_id:
        lot = db.query(models.Lot).filter(models.Lot.id == lot_id).first()
        if not lot or lot.farmer_id != farmer.id:
            raise HTTPException(status_code=403, detail="You can only book storage against your own lot")

    facility = db.query(models.StorageFacility).filter(models.StorageFacility.id == facility_id).first()
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    if facility.available_capacity_kg < quantity_kg:
        raise HTTPException(status_code=400, detail="Not enough available capacity at this facility")

    # Estimate cost
    estimated_cost = None
    if end_date:
        try:
            s = dt.date.fromisoformat(start_date)
            e = dt.date.fromisoformat(end_date)
            days = max((e - s).days, 1)
            estimated_cost = round(quantity_kg * facility.price_per_kg_per_day * days, 2)
        except ValueError:
            pass

    booking = models.StorageBooking(
        farmer_id=farmer.id,
        storage_facility_id=facility_id,
        lot_id=lot_id,
        quantity_kg=quantity_kg,
        start_date=start_date,
        end_date=end_date,
        estimated_cost=estimated_cost,
        status="REQUESTED",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _booking_dict(booking)


@router.get("/bookings/mine")
def my_bookings(farmer: models.Farmer = Depends(require_farmer), db: Session = Depends(get_db)):
    bookings = (
        db.query(models.StorageBooking)
        .filter(models.StorageBooking.farmer_id == farmer.id)
        .order_by(models.StorageBooking.created_at.desc())
        .all()
    )
    return [_booking_dict(b) for b in bookings]


@router.get("/bookings/{booking_id}")
def get_booking(
    booking_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    b = db.query(models.StorageBooking).filter(models.StorageBooking.id == booking_id).first()
    if not b or b.farmer_id != farmer.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _booking_dict(b)


@router.patch("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    b = db.query(models.StorageBooking).filter(models.StorageBooking.id == booking_id).first()
    if not b or b.farmer_id != farmer.id:
        raise HTTPException(status_code=404, detail="Booking not found")
    if b.status not in ("REQUESTED", "CONFIRMED"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel booking in status {b.status}")
    # If capacity was already reserved (booking was CONFIRMED), give it
    # back to the facility -- otherwise every confirmed-then-cancelled
    # booking permanently shrinks available_capacity_kg with no way to
    # recover it.
    if b.status == "CONFIRMED":
        facility = db.query(models.StorageFacility).filter(
            models.StorageFacility.id == b.storage_facility_id
        ).first()
        if facility:
            facility.available_capacity_kg = min(
                facility.capacity_kg, facility.available_capacity_kg + b.quantity_kg
            )
    b.status = "CANCELLED"
    db.commit()
    return {"cancelled": True}


# ─── admin: confirm bookings ─────────────────────────────────────────────────

@router.patch("/bookings/{booking_id}/confirm")
def confirm_booking(booking_id: int, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Admin/facility operator confirms a booking.

    Previously had NO auth dependency at all -- any unauthenticated caller
    could confirm arbitrary bookings and drain a facility's available
    capacity. Now requires admin, consistent with every other
    state-changing admin action in this codebase (buyer verification,
    grievance resolution, transaction override)."""
    b = db.query(models.StorageBooking).filter(models.StorageBooking.id == booking_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")
    if b.status != "REQUESTED":
        raise HTTPException(status_code=400, detail=f"Booking is already {b.status}")
    b.status = "CONFIRMED"
    # reduce available capacity
    facility = db.query(models.StorageFacility).filter(models.StorageFacility.id == b.storage_facility_id).first()
    if facility:
        facility.available_capacity_kg = max(0, facility.available_capacity_kg - b.quantity_kg)
    db.commit()
    return {"confirmed": True}


def _booking_dict(b: models.StorageBooking) -> dict:
    facility = b.facility
    return {
        "id": b.id,
        "farmer_id": b.farmer_id,
        "storage_facility_id": b.storage_facility_id,
        "facility_name": facility.name if facility else None,
        "facility_type": facility.facility_type if facility else None,
        "facility_location": facility.location if facility else None,
        "is_demo_facility": facility.is_demo if facility else True,
        "lot_id": b.lot_id,
        "quantity_kg": b.quantity_kg,
        "start_date": b.start_date,
        "end_date": b.end_date,
        "estimated_cost": b.estimated_cost,
        "status": b.status,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }
