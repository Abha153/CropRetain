"""
Buyer Demand — Phase 1 & 3.

Buyers post what they want to buy (crop, quantity, quality requirements,
price, location, deadline).  Farmers browse active demands, see a match
percentage calculated from their lots/listings, and can respond.

Phase 3 quality matching is included here: when a farmer has a lot with
an AI quality result we compare it against the demand's requirements and
return a per-criterion breakdown — always labelled "AI Estimated".
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_buyer, require_farmer, get_current_user
from app.mock_data.locations import distance_between

router = APIRouter(prefix="/buyer-demands", tags=["buyer-demands"])

VALID_STATUSES = {"ACTIVE", "PARTIALLY_FILLED", "FULFILLED", "EXPIRED", "CANCELLED"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quality_match(demand: models.BuyerDemand, lot: models.Lot) -> dict:
    """
    Compare a lot's AI quality data against a demand's requirements.
    Returns a score 0-100 and per-criterion pass/fail list.
    All grades here are from AI image analysis — never claimed as lab-certified.
    """
    checks = []
    score_parts = []

    # Grade check
    grade_order = {"A": 3, "B": 2, "C": 1}
    if demand.quality_grade:
        lot_grade_val = grade_order.get(lot.grade, 0)
        req_grade_val = grade_order.get(demand.quality_grade, 0)
        passed = lot_grade_val >= req_grade_val
        checks.append({"criterion": "AI Estimated Grade", "required": demand.quality_grade,
                        "actual": lot.grade, "passed": passed})
        score_parts.append(100.0 if passed else 0.0)
    else:
        checks.append({"criterion": "AI Estimated Grade", "required": "Any", "actual": lot.grade, "passed": True})
        score_parts.append(100.0)

    # Moisture — if report has it
    report = lot.quality_report or {}
    moisture = report.get("moisture_pct")
    if demand.moisture_limit is not None and moisture is not None:
        passed = moisture <= demand.moisture_limit
        checks.append({"criterion": "Moisture %", "required": f"≤{demand.moisture_limit}%",
                        "actual": f"{moisture}%", "passed": passed})
        score_parts.append(100.0 if passed else 20.0)
    else:
        checks.append({"criterion": "Moisture %", "required": f"≤{demand.moisture_limit or 'N/A'}%",
                        "actual": "Not measured", "passed": None})

    # Foreign matter
    fm = report.get("foreign_matter_pct")
    if demand.foreign_matter_limit is not None and fm is not None:
        passed = fm <= demand.foreign_matter_limit
        checks.append({"criterion": "Foreign Matter %", "required": f"≤{demand.foreign_matter_limit}%",
                        "actual": f"{fm}%", "passed": passed})
        score_parts.append(100.0 if passed else 20.0)

    # Damaged grains
    dmg = report.get("damaged_pct")
    if demand.damaged_grains_limit is not None and dmg is not None:
        passed = dmg <= demand.damaged_grains_limit
        checks.append({"criterion": "Damaged Grains %", "required": f"≤{demand.damaged_grains_limit}%",
                        "actual": f"{dmg}%", "passed": passed})
        score_parts.append(100.0 if passed else 20.0)

    # Quantity fit
    qty_min = demand.minimum_quantity_kg or (demand.required_quantity_kg * 0.7)
    qty_max = demand.maximum_quantity_kg or (demand.required_quantity_kg * 1.3)
    qty_passed = qty_min <= lot.quantity_kg <= qty_max
    checks.append({"criterion": "Quantity", "required": f"{qty_min:.0f}–{qty_max:.0f} kg",
                    "actual": f"{lot.quantity_kg:.0f} kg", "passed": qty_passed})
    score_parts.append(100.0 if qty_passed else 40.0)

    overall = round(sum(score_parts) / len(score_parts), 1) if score_parts else 0.0
    return {
        "quality_match_score": overall,
        "criteria": checks,
        "note": "AI Estimated Quality — image-based analysis only, not lab-certified.",
    }


def _demand_match_score(demand: models.BuyerDemand, buyer: models.Buyer,
                         crop: str, quantity_kg: float, location: str,
                         grade: Optional[str], price_per_kg: Optional[float]) -> dict:
    """
    Score how well a farmer's crop matches a buyer demand.
    Returns 0-100 with breakdown.
    """
    scores = {}

    # Crop match (binary)
    scores["crop"] = 100.0 if demand.crop.lower() == crop.lower() else 0.0

    # Price: farmer price vs buyer target
    if demand.target_price_per_kg and price_per_kg:
        ratio = price_per_kg / demand.target_price_per_kg
        # 100% if farmer asks ≤ target; decays if above
        scores["price"] = max(0.0, min(100.0, (2.0 - ratio) * 100.0))
    else:
        scores["price"] = 70.0  # neutral if no target

    # Quantity fit
    qty_min = demand.minimum_quantity_kg or (demand.required_quantity_kg * 0.5)
    qty_max = demand.maximum_quantity_kg or (demand.required_quantity_kg * 1.5)
    scores["quantity"] = 100.0 if qty_min <= quantity_kg <= qty_max else 50.0

    # Distance
    if demand.delivery_location and location:
        dist = distance_between(location, demand.delivery_location)
        scores["location"] = max(10.0, 100.0 - dist * 0.4)
    else:
        scores["location"] = 70.0

    # Grade match
    grade_order = {"A": 3, "B": 2, "C": 1}
    if demand.quality_grade and grade:
        lot_val = grade_order.get(grade, 0)
        req_val = grade_order.get(demand.quality_grade, 0)
        scores["grade"] = 100.0 if lot_val >= req_val else 40.0
    else:
        scores["grade"] = 80.0

    # Buyer reliability bonus
    scores["reliability"] = buyer.reliability_score

    weights = {"crop": 0.25, "price": 0.25, "quantity": 0.20,
               "location": 0.15, "grade": 0.10, "reliability": 0.05}
    composite = sum(scores[k] * weights[k] for k in scores)

    return {
        "overall": round(min(composite, 99.5), 1),
        "breakdown": {k: round(v, 1) for k, v in scores.items()},
    }


# ---------------------------------------------------------------------------
# Buyer — create / edit / cancel / view
# ---------------------------------------------------------------------------

@router.post("", response_model=schemas.BuyerDemandOut)
def create_demand(
    payload: schemas.BuyerDemandCreate,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    if payload.required_quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="Required quantity must be > 0 kg")
    if payload.minimum_quantity_kg and payload.minimum_quantity_kg > payload.required_quantity_kg:
        raise HTTPException(status_code=400, detail="Minimum quantity cannot exceed required quantity")

    demand = models.BuyerDemand(
        buyer_id=buyer.id,
        **payload.model_dump(),
    )
    db.add(demand)
    db.commit()
    db.refresh(demand)
    return demand


@router.get("/mine", response_model=List[schemas.BuyerDemandOut])
def my_demands(
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.BuyerDemand)
        .filter(models.BuyerDemand.buyer_id == buyer.id)
        .order_by(models.BuyerDemand.created_at.desc())
        .all()
    )


@router.patch("/{demand_id}", response_model=schemas.BuyerDemandOut)
def update_demand(
    demand_id: int,
    payload: schemas.BuyerDemandUpdate,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    demand = db.query(models.BuyerDemand).filter(models.BuyerDemand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demand not found")
    if demand.buyer_id != buyer.id:
        raise HTTPException(status_code=403, detail="You can only edit your own demands")
    if demand.status in ("FULFILLED", "CANCELLED"):
        raise HTTPException(status_code=400, detail=f"Cannot edit a demand in {demand.status} status")
    if payload.status and payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(demand, field, value)
    db.commit()
    db.refresh(demand)
    return demand


@router.patch("/{demand_id}/cancel")
def cancel_demand(
    demand_id: int,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    demand = db.query(models.BuyerDemand).filter(models.BuyerDemand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demand not found")
    if demand.buyer_id != buyer.id:
        raise HTTPException(status_code=403, detail="You can only cancel your own demands")
    if demand.status == "CANCELLED":
        raise HTTPException(status_code=400, detail="Already cancelled")
    demand.status = "CANCELLED"
    db.commit()
    return {"cancelled": True}


# ---------------------------------------------------------------------------
# Public browse — farmers see active demands, get match score
# ---------------------------------------------------------------------------

@router.get("", response_model=List[schemas.BuyerDemandOut])
def list_demands(
    crop: Optional[str] = None,
    location: Optional[str] = None,
    min_quantity_kg: Optional[float] = None,
    max_price: Optional[float] = None,
    quality_grade: Optional[str] = None,
    status: str = "ACTIVE",
    db: Session = Depends(get_db),
):
    """Public endpoint — anyone can browse active buyer demands."""
    q = db.query(models.BuyerDemand)
    if status:
        q = q.filter(models.BuyerDemand.status == status)
    if crop:
        q = q.filter(models.BuyerDemand.crop == crop)
    if location:
        q = q.filter(models.BuyerDemand.delivery_location == location)
    if min_quantity_kg:
        q = q.filter(models.BuyerDemand.required_quantity_kg >= min_quantity_kg)
    if max_price:
        q = q.filter(models.BuyerDemand.target_price_per_kg <= max_price)
    if quality_grade:
        q = q.filter(models.BuyerDemand.quality_grade == quality_grade)
    return q.order_by(models.BuyerDemand.created_at.desc()).all()


@router.get("/{demand_id}", response_model=schemas.BuyerDemandOut)
def get_demand(demand_id: int, db: Session = Depends(get_db)):
    demand = db.query(models.BuyerDemand).filter(models.BuyerDemand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demand not found")
    return demand


@router.get("/{demand_id}/matches")
def demand_matches(
    demand_id: int,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    For buyers: see which lots best match their demand.
    For farmers: see how their lots score against this demand.
    Returns top matching lots with per-criterion breakdown.
    """
    demand = db.query(models.BuyerDemand).filter(models.BuyerDemand.id == demand_id).first()
    if not demand:
        raise HTTPException(status_code=404, detail="Demand not found")

    buyer = db.query(models.Buyer).filter(models.Buyer.id == demand.buyer_id).first()

    # Find matching lots — same crop, available status
    lots = (
        db.query(models.Lot)
        .filter(models.Lot.crop == demand.crop, models.Lot.status == "AVAILABLE")
        .all()
    )
    # Also include active CropListings for backward compat
    listings = (
        db.query(models.CropListing)
        .filter(models.CropListing.crop == demand.crop, models.CropListing.status == "active")
        .all()
    )

    results = []
    for lot in lots:
        match = _demand_match_score(
            demand, buyer, lot.crop, lot.quantity_kg,
            lot.location, lot.grade, lot.expected_price,
        )
        quality = _quality_match(demand, lot)
        farmer = db.query(models.Farmer).filter(models.Farmer.id == lot.farmer_id).first()
        results.append({
            "source": "lot",
            "id": lot.id,
            "lot_number": lot.lot_number,
            "farmer_name": farmer.name if farmer else "Unknown",
            "farmer_location": lot.location,
            "crop": lot.crop,
            "quantity_kg": lot.quantity_kg,
            "grade": lot.grade,
            "quality_score": lot.quality_score,
            "expected_price_per_kg": lot.expected_price,
            "match_score": match["overall"],
            "match_breakdown": match["breakdown"],
            "quality_match": quality,
        })

    for listing in listings:
        # listings have no quality_report, use simpler quality match
        match = _demand_match_score(
            demand, buyer, listing.crop, listing.quantity_kg,
            listing.location, listing.quality_grade, listing.expected_price_per_kg,
        )
        farmer = db.query(models.Farmer).filter(models.Farmer.id == listing.farmer_id).first()
        results.append({
            "source": "listing",
            "id": listing.id,
            "lot_number": None,
            "farmer_name": farmer.name if farmer else "Unknown",
            "farmer_location": listing.location,
            "crop": listing.crop,
            "quantity_kg": listing.quantity_kg,
            "grade": listing.quality_grade,
            "quality_score": listing.quality_score,
            "expected_price_per_kg": listing.expected_price_per_kg,
            "match_score": match["overall"],
            "match_breakdown": match["breakdown"],
            "quality_match": None,
        })

    results.sort(key=lambda r: r["match_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    return {
        "demand_id": demand_id,
        "crop": demand.crop,
        "matches": results[:10],
    }
