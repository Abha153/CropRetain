"""
Real authenticated FARMER <-> TRANSPORTER workflow -- negotiation
(persistent offer history), chat, transporter-driven status transitions,
and two-sided reviews.

Deliberately a SEPARATE router/module from app/routers/transport.py (the
legacy farmer-recorded quote flow, kept fully intact for backward
compatibility) and from app/routers/trip_reviews.py (FarmPool shared-trip
reviews, unrelated relationship). Same URL prefix ("/transport"), disjoint
paths -- both routers can be mounted together with no collisions.

Every mutating endpoint derives sender/receiver/reviewer/role from the
authenticated JWT + the TransportRequest's farmer_id/transporter_id --
never from the request body.
"""
import datetime as dt
from typing import Tuple, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer_or_transporter, require_transporter
from app.routers.transport import _request_dict

router = APIRouter(prefix="/transport", tags=["transport-negotiation"])

Participant = Union[models.Farmer, models.Transporter]

# Transporter-driven physical-trip transitions layered on top of the
# existing status field (see app/routers/transport.py::VALID_TRANSITIONS,
# which this deliberately mirrors + extends with COMPLETED so both the
# legacy farmer-driven and new transporter-driven callers agree on the
# same status values on the same column).
TRANSPORTER_VALID_TRANSITIONS = {
    "CONFIRMED": ["PICKED_UP", "CANCELLED"],
    "MATCHED": ["PICKED_UP", "CANCELLED"],
    "PICKED_UP": ["IN_TRANSIT"],
    "IN_TRANSIT": ["DELIVERED"],
    "DELIVERED": ["COMPLETED"],
}


def _load_participant_request(
    request_id: int, user: Participant, role: str, db: Session
) -> models.TransportRequest:
    """Loads the TransportRequest and enforces that the caller is an
    actual participant -- the owning farmer, or the assigned transporter.
    404 (not 403) on mismatch, matching the ownership-check pattern used
    throughout the rest of this codebase (no existence-leak)."""
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Transport request not found")
    if role == "farmer":
        if r.farmer_id != user.id:
            raise HTTPException(status_code=404, detail="Transport request not found")
    else:  # transporter
        if r.transporter_id is None or r.transporter_id != user.id:
            raise HTTPException(status_code=404, detail="Transport request not found")
    return r


def _other_party(r: models.TransportRequest, role: str) -> Tuple[str, int]:
    if role == "farmer":
        if r.transporter_id is None:
            raise HTTPException(status_code=400, detail="No transporter has claimed this request yet")
        return "transporter", r.transporter_id
    return "farmer", r.farmer_id


# ─── negotiation (persistent multi-round offer history) ─────────────────────

@router.post("/requests/{request_id}/offers", response_model=schemas.TransportOfferOut)
def create_offer(
    request_id: int,
    payload: schemas.TransportOfferCreate,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    """Submit a quote (transporter) or counter-offer (farmer). The very
    first offer on a request must come from the transporter (matching the
    real-world workflow: transporter quotes, farmer negotiates). After
    that, turn alternates strictly: only the RECEIVER of the current
    outstanding offer may respond, by submitting a new offer (a straight
    accept uses the /accept endpoint instead, not this one)."""
    user, role = current
    r = _load_participant_request(request_id, user, role, db)

    if r.status in ("DELIVERED", "CANCELLED", "COMPLETED"):
        raise HTTPException(status_code=400, detail=f"Trip is already {r.status}; negotiation is closed")
    if r.negotiation_status == "AGREED":
        raise HTTPException(status_code=400, detail="This request already has an agreed price; negotiation is closed")
    if r.negotiation_status == "DECLINED":
        raise HTTPException(status_code=400, detail="This negotiation was declined and is closed")
    if r.negotiation_status == "OPEN":
        raise HTTPException(status_code=400, detail="No transporter has claimed this request yet")

    receiver_role, receiver_id = _other_party(r, role)

    latest = (
        db.query(models.TransportOffer)
        .filter(models.TransportOffer.transport_request_id == r.id)
        .order_by(models.TransportOffer.sequence.desc())
        .first()
    )

    if latest is None:
        # First offer: must come from the transporter.
        if role != "transporter":
            raise HTTPException(status_code=400, detail="The transporter must submit the first quote")
        next_sequence = 1
    else:
        if latest.status == "PENDING":
            # It's the OTHER party's turn to respond to the outstanding
            # offer -- prevents either side from submitting twice in a
            # row (out-of-turn) or piling up offers without the other
            # party ever having a chance to respond.
            if latest.sender_role == role:
                raise HTTPException(status_code=400, detail="Waiting on the other party to respond to your last offer")
            # This new offer implicitly supersedes (counters) the
            # outstanding one -- the sender is choosing to counter rather
            # than accept it via the dedicated accept endpoint.
            latest.status = "SUPERSEDED"
            latest.responded_at = dt.datetime.utcnow()
        elif latest.status != "PENDING" and r.negotiation_status not in ("NEGOTIATING",):
            raise HTTPException(status_code=400, detail="This negotiation is no longer open")
        next_sequence = latest.sequence + 1

    offer = models.TransportOffer(
        transport_request_id=r.id,
        sequence=next_sequence,
        sender_role=role,
        sender_id=user.id,
        receiver_role=receiver_role,
        receiver_id=receiver_id,
        amount=payload.amount,
        message=payload.message,
        status="PENDING",
    )
    db.add(offer)
    r.negotiation_status = "NEGOTIATING"
    r.updated_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(offer)
    return offer


@router.get("/requests/{request_id}/offers", response_model=list[schemas.TransportOfferOut])
def list_offers(
    request_id: int,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    """Full, immutable, chronological offer history -- participants only."""
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    return (
        db.query(models.TransportOffer)
        .filter(models.TransportOffer.transport_request_id == r.id)
        .order_by(models.TransportOffer.sequence.asc())
        .all()
    )


@router.post("/requests/{request_id}/offers/{offer_id}/accept", response_model=schemas.TransportOfferOut)
def accept_offer(
    request_id: int,
    offer_id: int,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    """Only the RECEIVER of a still-PENDING offer may accept it. The
    final agreed amount is taken server-side from the stored offer row,
    never from the client."""
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    offer = (
        db.query(models.TransportOffer)
        .filter(models.TransportOffer.id == offer_id, models.TransportOffer.transport_request_id == r.id)
        .first()
    )
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.receiver_role != role or offer.receiver_id != user.id:
        raise HTTPException(status_code=403, detail="Only the recipient of this offer can accept it")
    if offer.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"This offer is {offer.status.lower()}, not an outstanding offer -- it cannot be accepted (stale or already responded to)")

    offer.status = "ACCEPTED"
    offer.responded_at = dt.datetime.utcnow()
    r.negotiation_status = "AGREED"
    r.transporter_agreed_price = offer.amount
    r.transporter_agreed_at = dt.datetime.utcnow()
    r.updated_at = dt.datetime.utcnow()
    # Reuse CONFIRMED as booking, matching the existing status lifecycle
    # (see app/routers/transport.py) rather than inventing a competing
    # "BOOKED" status -- only advance if the physical trip hasn't already
    # moved past that point some other way.
    if r.status in ("REQUESTED", "MATCHED"):
        r.status = "CONFIRMED"
    db.commit()
    db.refresh(offer)
    return offer


@router.post("/requests/{request_id}/offers/{offer_id}/reject", response_model=schemas.TransportOfferOut)
def reject_offer(
    request_id: int,
    offer_id: int,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    """Only the RECEIVER of a still-PENDING offer may reject it outright
    (closing the negotiation entirely -- for a counter-proposal instead,
    submit a new offer via POST /offers, which supersedes automatically)."""
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    offer = (
        db.query(models.TransportOffer)
        .filter(models.TransportOffer.id == offer_id, models.TransportOffer.transport_request_id == r.id)
        .first()
    )
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.receiver_role != role or offer.receiver_id != user.id:
        raise HTTPException(status_code=403, detail="Only the recipient of this offer can reject it")
    if offer.status != "PENDING":
        raise HTTPException(status_code=400, detail=f"This offer is {offer.status.lower()}; it cannot be rejected (stale or already responded to)")

    offer.status = "REJECTED"
    offer.responded_at = dt.datetime.utcnow()
    r.negotiation_status = "DECLINED"
    r.updated_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(offer)
    return offer


# ─── chat (transport-request-scoped) ─────────────────────────────────────────

@router.post("/requests/{request_id}/messages", response_model=schemas.TransportMessageOut)
def send_message(
    request_id: int,
    payload: schemas.TransportMessageCreate,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    receiver_role, receiver_id = _other_party(r, role)

    msg = models.TransportMessage(
        transport_request_id=r.id,
        sender_role=role,
        sender_id=user.id,
        recipient_role=receiver_role,
        recipient_id=receiver_id,
        message=payload.message,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@router.get("/requests/{request_id}/messages", response_model=list[schemas.TransportMessageOut])
def list_messages(
    request_id: int,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    return (
        db.query(models.TransportMessage)
        .filter(models.TransportMessage.transport_request_id == r.id)
        .order_by(models.TransportMessage.id.asc())
        .all()
    )


# ─── transporter-driven status transitions ───────────────────────────────────

@router.post("/requests/{request_id}/transporter-status")
def transporter_update_status(
    request_id: int,
    payload: schemas.TransporterStatusUpdate,
    transporter: models.Transporter = Depends(require_transporter),
    db: Session = Depends(get_db),
):
    """Only the assigned transporter may mark pickup/in-transit/delivered/
    completed -- the farmer-facing PATCH /transport/requests/{id}/status
    in transport.py is untouched and still works for the legacy flow."""
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r or r.transporter_id != transporter.id:
        raise HTTPException(status_code=404, detail="Transport request not found")

    new_status = (payload.status or "").upper()
    if new_status not in TRANSPORTER_VALID_TRANSITIONS.get(r.status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {r.status} to {new_status}. "
                   f"Valid transitions: {TRANSPORTER_VALID_TRANSITIONS.get(r.status, [])}",
        )
    r.status = new_status
    now = dt.datetime.utcnow()
    if new_status == "PICKED_UP":
        r.picked_up_at = now
    elif new_status == "DELIVERED":
        r.delivered_at = now
    elif new_status == "COMPLETED":
        r.completed_at = now
    r.updated_at = now

    if r.lot_id and new_status in ("PICKED_UP", "IN_TRANSIT", "DELIVERED"):
        lot = db.query(models.Lot).filter(models.Lot.id == r.lot_id).first()
        if lot:
            lot.status = "IN_TRANSIT" if new_status != "DELIVERED" else "DELIVERED"

    db.commit()
    db.refresh(r)
    d = _request_dict(r)
    d["transporter_id"] = r.transporter_id
    d["negotiation_status"] = r.negotiation_status
    d["transporter_agreed_price"] = r.transporter_agreed_price
    d["completed_at"] = r.completed_at.isoformat() if r.completed_at else None
    return d


# ─── two-sided reviews ────────────────────────────────────────────────────────

@router.post("/requests/{request_id}/review", response_model=schemas.TransportReviewOut)
def submit_review(
    request_id: int,
    payload: schemas.TransportReviewCreate,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    if r.status not in ("DELIVERED", "COMPLETED"):
        raise HTTPException(status_code=400, detail="Reviews are only allowed after delivery is complete")

    reviewee_role, reviewee_id = _other_party(r, role)

    existing = (
        db.query(models.TransportReview)
        .filter(
            models.TransportReview.transport_request_id == r.id,
            models.TransportReview.reviewer_role == role,
            models.TransportReview.reviewer_id == user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="You have already reviewed this trip")

    review = models.TransportReview(
        transport_request_id=r.id,
        reviewer_role=role,
        reviewer_id=user.id,
        reviewee_role=reviewee_role,
        reviewee_id=reviewee_id,
        rating=payload.rating,
        punctuality=payload.punctuality,
        communication=payload.communication,
        handling=payload.handling,
        reliability=payload.reliability,
        comment=payload.comment,
    )
    db.add(review)
    db.flush()

    # Roll the new rating into the reviewee's aggregate score. Transporter
    # aggregate lives on Transporter.rating/rating_count; farmers don't
    # currently carry a rating_count column, so their `rating` (already
    # present on Farmer) is updated as a simple running average using the
    # count of transport reviews they've received.
    if reviewee_role == "transporter":
        t = db.query(models.Transporter).filter(models.Transporter.id == reviewee_id).first()
        if t:
            total = t.rating * t.rating_count + payload.rating
            t.rating_count += 1
            t.rating = round(total / t.rating_count, 2)
    else:
        f = db.query(models.Farmer).filter(models.Farmer.id == reviewee_id).first()
        if f:
            count = (
                db.query(models.TransportReview)
                .filter(
                    models.TransportReview.reviewee_role == "farmer",
                    models.TransportReview.reviewee_id == reviewee_id,
                )
                .count()
            )
            prior_total = f.rating * max(count - 1, 0)
            f.rating = round((prior_total + payload.rating) / count, 2)

    db.commit()
    db.refresh(review)
    return review


@router.get("/requests/{request_id}/reviews", response_model=list[schemas.TransportReviewOut])
def list_reviews(
    request_id: int,
    current: Tuple[Participant, str] = Depends(require_farmer_or_transporter),
    db: Session = Depends(get_db),
):
    user, role = current
    r = _load_participant_request(request_id, user, role, db)
    return (
        db.query(models.TransportReview)
        .filter(models.TransportReview.transport_request_id == r.id)
        .order_by(models.TransportReview.created_at.asc())
        .all()
    )
