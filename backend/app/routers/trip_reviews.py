"""
FarmPool / shared-logistics trust layer.

Complements the existing `ratings` router (farmer<->buyer, attached to a
Transaction) by covering a different relationship: how the TRIP itself
went. Reviews attach to a TransportRequest and cover the transporter, the
shared journey, and the FPO/aggregator when one is involved.

Every eligibility rule is enforced server-side. The client never supplies
reviewer identity, participation status, or the `verified` flag.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth_utils import require_farmer

router = APIRouter(prefix="/trip-reviews", tags=["trip-reviews"])

VALID_TYPES = {"TRANSPORTER", "JOURNEY", "FPO"}

# A trip can only be reviewed once it has actually finished. DELIVERED is
# the terminal success state in TransportRequest's documented lifecycle
# (REQUESTED / MATCHED / CONFIRMED / PICKED_UP / IN_TRANSIT / DELIVERED /
# CANCELLED) -- anything earlier means the journey is still in progress.
COMPLETED_STATUSES = {"DELIVERED"}


def _validate_score(value, field_name):
    """Ratings are 1-5. Reject anything else rather than silently clamping,
    so a malformed client can't quietly skew aggregates."""
    if value is None:
        return None
    if not (1.0 <= float(value) <= 5.0):
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be between 1 and 5",
        )
    return float(value)


@router.post("")
def submit_trip_review(
    payload: dict,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Submit a TRANSPORTER / JOURNEY / FPO review for a completed trip."""
    transport_request_id = payload.get("transport_request_id")
    review_type = (payload.get("review_type") or "").upper()

    if not transport_request_id:
        raise HTTPException(status_code=400, detail="transport_request_id is required")
    if review_type not in VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"review_type must be one of {sorted(VALID_TYPES)}",
        )

    trip = db.query(models.TransportRequest).filter(
        models.TransportRequest.id == transport_request_id
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    # --- Eligibility gate 1: the reviewer must have been on this trip. ---
    # Authorisation comes from the authenticated farmer, never from the body.
    if trip.farmer_id != farmer.id:
        raise HTTPException(
            status_code=403,
            detail="You can only review a trip you participated in",
        )

    # --- Eligibility gate 2: the trip must actually be finished. ---
    if trip.status not in COMPLETED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="This trip is not completed yet",
        )

    # --- Eligibility gate 3: an FPO review requires an actual FPO. ---
    pool_id = payload.get("pool_id")
    if review_type == "FPO":
        if not pool_id:
            raise HTTPException(
                status_code=400,
                detail="pool_id is required for an FPO review",
            )
        pool = db.query(models.GroupSellingPool).filter(
            models.GroupSellingPool.id == pool_id
        ).first()
        if not pool:
            raise HTTPException(status_code=404, detail="Pool not found")
        # The reviewer must be a member of the pool they're rating.
        member = db.query(models.GroupPoolMembership).filter(
            models.GroupPoolMembership.pool_id == pool_id,
            models.GroupPoolMembership.farmer_id == farmer.id,
        ).first()
        if not member:
            raise HTTPException(
                status_code=403,
                detail="You can only review an FPO pool you joined",
            )

    # --- Duplicate guard (also enforced by a DB unique constraint). ---
    existing = db.query(models.TripReview).filter(
        models.TripReview.transport_request_id == transport_request_id,
        models.TripReview.reviewer_farmer_id == farmer.id,
        models.TripReview.review_type == review_type,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You have already submitted this review for this trip",
        )

    rating = payload.get("rating")
    if rating is None:
        raise HTTPException(status_code=400, detail="rating is required")

    review = models.TripReview(
        transport_request_id=transport_request_id,
        pool_id=pool_id if review_type == "FPO" else payload.get("pool_id"),
        reviewer_farmer_id=farmer.id,
        review_type=review_type,
        rating=_validate_score(rating, "rating"),
        punctuality=_validate_score(payload.get("punctuality"), "punctuality"),
        communication=_validate_score(payload.get("communication"), "communication"),
        handling=_validate_score(payload.get("handling"), "handling"),
        coordination=_validate_score(payload.get("coordination"), "coordination"),
        comment=(payload.get("comment") or None),
        # Set server-side only, after every gate above has passed.
        verified=True,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return _review_dict(review)


@router.get("/for-trip/{transport_request_id}")
def reviews_for_trip(transport_request_id: int, db: Session = Depends(get_db)):
    """All reviews for one trip, plus per-type aggregates."""
    reviews = db.query(models.TripReview).filter(
        models.TripReview.transport_request_id == transport_request_id
    ).all()
    return {
        "transport_request_id": transport_request_id,
        "reviews": [_review_dict(r) for r in reviews],
        "summary": _aggregate(reviews),
    }


@router.get("/my/{transport_request_id}")
def my_reviews_for_trip(
    transport_request_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Which review types this farmer has already submitted for this trip --
    lets the UI disable already-used options instead of failing on submit."""
    reviews = db.query(models.TripReview).filter(
        models.TripReview.transport_request_id == transport_request_id,
        models.TripReview.reviewer_farmer_id == farmer.id,
    ).all()
    return {
        "submitted_types": [r.review_type for r in reviews],
        "reviews": [_review_dict(r) for r in reviews],
    }


def _avg(values):
    real = [v for v in values if v is not None]
    return round(sum(real) / len(real), 2) if real else None


def _aggregate(reviews):
    """Aggregates computed from stored rows only -- never hardcoded."""
    out = {}
    for rtype in sorted(VALID_TYPES):
        subset = [r for r in reviews if r.review_type == rtype]
        if not subset:
            out[rtype] = {"count": 0, "overall": None}
            continue
        out[rtype] = {
            "count": len(subset),
            "verified_count": len([r for r in subset if r.verified]),
            "overall": _avg([r.rating for r in subset]),
            "punctuality": _avg([r.punctuality for r in subset]),
            "communication": _avg([r.communication for r in subset]),
            "handling": _avg([r.handling for r in subset]),
            "coordination": _avg([r.coordination for r in subset]),
        }
    return out


def _review_dict(r: models.TripReview) -> dict:
    return {
        "id": r.id,
        "transport_request_id": r.transport_request_id,
        "pool_id": r.pool_id,
        "review_type": r.review_type,
        "rating": r.rating,
        "punctuality": r.punctuality,
        "communication": r.communication,
        "handling": r.handling,
        "coordination": r.coordination,
        "comment": r.comment,
        "verified": r.verified,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
