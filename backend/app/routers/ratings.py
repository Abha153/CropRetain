"""
Phase 14 — Ratings and Trust
After completed transactions, farmers rate buyers and buyers rate farmers.
Prevents duplicate ratings per transaction.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, require_buyer

router = APIRouter(prefix="/ratings", tags=["ratings"])


# ─── farmer rates buyer ───────────────────────────────────────────────────────

@router.post("/farmer-rates-buyer")
def farmer_rates_buyer(
    payload: schemas.RatingCreate,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Farmer rates a buyer after a completed transaction."""
    transaction_id = payload.transaction_id
    rating_value = payload.rating
    review = payload.review or ""

    txn = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not txn or txn.farmer_id != farmer.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.status not in ("COMPLETED", "DELIVERED", "PAYMENT_RECEIVED"):
        raise HTTPException(status_code=400, detail="Can only rate after transaction is delivered or completed")

    # Duplicate check
    existing = db.query(models.Rating).filter(
        models.Rating.transaction_id == transaction_id,
        models.Rating.rater_role == "farmer",
        models.Rating.rater_id == farmer.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already rated this transaction")

    rating = models.Rating(
        transaction_id=transaction_id,
        rater_role="farmer",
        rater_id=farmer.id,
        ratee_role="buyer",
        ratee_id=txn.buyer_id,
        rating=rating_value,
        review=review,
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return _rating_dict(rating)


# ─── buyer rates farmer ───────────────────────────────────────────────────────

@router.post("/buyer-rates-farmer")
def buyer_rates_farmer(
    payload: schemas.RatingCreate,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    """Buyer rates a farmer after a completed transaction."""
    transaction_id = payload.transaction_id
    rating_value = payload.rating
    review = payload.review or ""

    txn = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
    if not txn or txn.buyer_id != buyer.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.status not in ("COMPLETED", "DELIVERED", "PAYMENT_RECEIVED"):
        raise HTTPException(status_code=400, detail="Can only rate after transaction is delivered or completed")

    existing = db.query(models.Rating).filter(
        models.Rating.transaction_id == transaction_id,
        models.Rating.rater_role == "buyer",
        models.Rating.rater_id == buyer.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already rated this transaction")

    rating = models.Rating(
        transaction_id=transaction_id,
        rater_role="buyer",
        rater_id=buyer.id,
        ratee_role="farmer",
        ratee_id=txn.farmer_id,
        rating=rating_value,
        review=review,
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return _rating_dict(rating)


# ─── get ratings for a user ───────────────────────────────────────────────────

@router.get("/for-buyer/{buyer_id}")
def ratings_for_buyer(buyer_id: int, db: Session = Depends(get_db)):
    ratings = db.query(models.Rating).filter(
        models.Rating.ratee_role == "buyer",
        models.Rating.ratee_id == buyer_id,
    ).all()
    avg = round(sum(r.rating for r in ratings) / max(len(ratings), 1), 2) if ratings else None
    return {
        "buyer_id": buyer_id,
        "total_ratings": len(ratings),
        "average_rating": avg,
        "ratings": [_rating_dict(r) for r in ratings],
    }


@router.get("/for-farmer/{farmer_id}")
def ratings_for_farmer(farmer_id: int, db: Session = Depends(get_db)):
    ratings = db.query(models.Rating).filter(
        models.Rating.ratee_role == "farmer",
        models.Rating.ratee_id == farmer_id,
    ).all()
    avg = round(sum(r.rating for r in ratings) / max(len(ratings), 1), 2) if ratings else None
    return {
        "farmer_id": farmer_id,
        "total_ratings": len(ratings),
        "average_rating": avg,
        "ratings": [_rating_dict(r) for r in ratings],
    }


@router.get("/my-transaction/{transaction_id}")
def my_transaction_rating(
    transaction_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Check if farmer has already rated a specific transaction."""
    existing = db.query(models.Rating).filter(
        models.Rating.transaction_id == transaction_id,
        models.Rating.rater_role == "farmer",
        models.Rating.rater_id == farmer.id,
    ).first()
    return {"has_rated": existing is not None, "rating": _rating_dict(existing) if existing else None}


# ─── helper ──────────────────────────────────────────────────────────────────

def _rating_dict(r: models.Rating) -> dict:
    if r is None:
        return None
    return {
        "id": r.id,
        "transaction_id": r.transaction_id,
        "rater_role": r.rater_role,
        "rater_id": r.rater_id,
        "ratee_role": r.ratee_role,
        "ratee_id": r.ratee_id,
        "rating": r.rating,
        "review": r.review,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
