"""
Multi-round crop-deal negotiation (buyer <-> farmer) -- counter / accept /
reject / withdraw with persistent, immutable round history.

Mounted on the SAME "/offers" prefix as app/routers/offers.py (which keeps
the legacy create / list / PATCH accept / PATCH reject endpoints) with
disjoint paths. main.py includes offers.router FIRST so that the static
paths there (/offers/mine, /offers/listing/..) win over /offers/{offer_id}.

Every endpoint derives identity from the JWT + listing/lot ownership.
Non-participants get 404 (no existence leak). Stale or out-of-turn actions
get 409 / 400. The offer row is locked (SELECT ... FOR UPDATE on Postgres)
and UNIQUE(offer_id, sequence) backstops concurrent counters (-> 409).
"""
from typing import List, Tuple, Union

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer_or_buyer
from app.services import offer_negotiation as neg
from app.routers.notifications import send_farmer_notification, send_buyer_notification

router = APIRouter(prefix="/offers", tags=["offer-negotiation"])

Participant = Union[models.Farmer, models.Buyer]


def _notify(db: Session, role: str, user_id: int, type_: str, title: str, message: str, severity="info"):
    """Runs AFTER our commit (the helpers commit themselves, silently)."""
    fn = send_farmer_notification if role == "farmer" else send_buyer_notification
    fn(db, user_id, type_, title, message, severity)


def _load(db: Session, offer_id: int, user: Participant, role: str, lock: bool = False):
    q = db.query(models.BuyerOffer).filter(models.BuyerOffer.id == offer_id)
    offer = (q.with_for_update() if lock else q).first()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    kind, target = neg.load_target(db, offer)
    if not target:
        raise HTTPException(status_code=404, detail="Offer not found")
    neg.participant_role_check(offer, target, user, role)
    return offer, kind, target


def _load_round(db: Session, offer: models.BuyerOffer, round_id: int) -> models.BuyerOfferRound:
    rnd = (db.query(models.BuyerOfferRound)
           .filter(models.BuyerOfferRound.id == round_id, models.BuyerOfferRound.offer_id == offer.id).first())
    if not rnd:
        raise HTTPException(status_code=404, detail="Round not found")
    return rnd


def _require_latest(db: Session, offer: models.BuyerOffer, rnd: models.BuyerOfferRound) -> None:
    latest = neg.latest_round(db, offer.id)
    if latest is None or latest.id != rnd.id:
        raise HTTPException(status_code=409, detail="This round is no longer the current one (stale request)")


def _can_act(offer, rnd, role) -> dict:
    live = offer.status == "pending" and rnd is not None and rnd.status == neg.R_PENDING
    mine = live and rnd.receiver_role == role
    return {"accept": bool(mine), "reject": bool(mine),
            "counter": bool(mine and rnd.sequence < neg.MAX_ROUNDS_PER_OFFER),
            "withdraw": bool(live and rnd.sender_role == role)}


# ─── reads ───────────────────────────────────────────────────────────────────

@router.get("/awaiting-me", response_model=List[schemas.OfferOut])
def offers_awaiting_me(current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
                       db: Session = Depends(get_db)):
    """Open negotiation threads where it is the CALLER's turn to respond."""
    user, role = current
    if role == "buyer":
        offers = db.query(models.BuyerOffer).filter(
            models.BuyerOffer.buyer_id == user.id, models.BuyerOffer.status == "pending").all()
    else:
        l_ids = [i for (i,) in db.query(models.CropListing.id).filter(models.CropListing.farmer_id == user.id)]
        lot_ids = [i for (i,) in db.query(models.Lot.id).filter(models.Lot.farmer_id == user.id)]
        offers = []
        if l_ids:
            offers += db.query(models.BuyerOffer).filter(
                models.BuyerOffer.listing_id.in_(l_ids), models.BuyerOffer.status == "pending").all()
        if lot_ids:
            offers += db.query(models.BuyerOffer).filter(
                models.BuyerOffer.lot_id.in_(lot_ids), models.BuyerOffer.status == "pending").all()
    neg.annotate_offers(db, offers)
    return sorted([o for o in offers if o.awaiting_role == role], key=lambda o: o.created_at, reverse=True)


@router.get("/{offer_id}", response_model=schemas.OfferThreadOut)
def get_thread(offer_id: int, current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
               db: Session = Depends(get_db)):
    user, role = current
    offer, kind, target = _load(db, offer_id, user, role)
    rnd = neg.ensure_rounds(db, offer, target.farmer_id)   # lazy backfill for pre-negotiation offers
    db.commit()
    rounds = (db.query(models.BuyerOfferRound).filter(models.BuyerOfferRound.offer_id == offer.id)
              .order_by(models.BuyerOfferRound.sequence).all())
    neg.annotate_offers(db, [offer])
    buyer = db.query(models.Buyer).filter(models.Buyer.id == offer.buyer_id).first()
    farmer = db.query(models.Farmer).filter(models.Farmer.id == target.farmer_id).first()
    txn = db.query(models.Transaction).filter(models.Transaction.offer_id == offer.id).first()
    return {
        "offer": offer, "rounds": rounds, "awaiting_role": neg.awaiting_role_for(offer, rnd),
        "can_act": _can_act(offer, rnd, role), "buyer": buyer, "farmer": farmer,
        "target": neg.target_summary(kind, target, include_floor=(role == "farmer")),
        "transaction_id": txn.id if txn else None,
    }


@router.get("/{offer_id}/rounds", response_model=List[schemas.OfferRoundOut])
def list_rounds(offer_id: int, current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
                db: Session = Depends(get_db)):
    """Full, immutable, chronological history -- participants only."""
    user, role = current
    offer, kind, target = _load(db, offer_id, user, role)
    neg.ensure_rounds(db, offer, target.farmer_id)
    db.commit()
    return (db.query(models.BuyerOfferRound).filter(models.BuyerOfferRound.offer_id == offer.id)
            .order_by(models.BuyerOfferRound.sequence).all())


# ─── counter ─────────────────────────────────────────────────────────────────

@router.post("/{offer_id}/counter", response_model=schemas.OfferRoundOut)
def counter_offer(offer_id: int, payload: schemas.OfferCounter,
                  current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
                  db: Session = Depends(get_db)):
    """Counter the outstanding round. Only its RECEIVER may do this; the new
    round supersedes (COUNTERED) the previous one and flips the turn."""
    user, role = current
    offer, kind, target = _load(db, offer_id, user, role, lock=True)
    neg.require_open_thread(offer)
    rnd = neg.ensure_rounds(db, offer, target.farmer_id)
    if payload.based_on_round_id is not None and payload.based_on_round_id != rnd.id:
        raise HTTPException(status_code=409, detail="The offer changed since you loaded it (stale request)")
    neg.require_actionable_round(rnd, role)
    if rnd.sequence >= neg.MAX_ROUNDS_PER_OFFER:
        raise HTTPException(status_code=400,
                            detail=f"Negotiation round limit ({neg.MAX_ROUNDS_PER_OFFER}) reached; accept, reject or withdraw")
    qty = payload.quantity_kg if payload.quantity_kg is not None else rnd.quantity_kg
    neg.validate_terms(kind, target, role, payload.price_per_kg, qty)

    recv_role, recv_id = neg.other_party(offer, target, role)
    now = neg._now()
    rnd.status = neg.R_COUNTERED
    rnd.responded_at = now
    new = models.BuyerOfferRound(
        offer_id=offer.id, sequence=rnd.sequence + 1,
        sender_role=role, sender_id=user.id, receiver_role=recv_role, receiver_id=recv_id,
        price_per_kg=payload.price_per_kg, quantity_kg=qty,
        message=payload.message, language=payload.language, status=neg.R_PENDING)
    db.add(new)
    offer.offered_price_per_kg = payload.price_per_kg   # mirror of the latest round
    offer.quantity_kg = qty
    offer.updated_at = now
    try:
        db.commit()
    except IntegrityError:   # a concurrent counter took this sequence number
        db.rollback()
        raise HTTPException(status_code=409, detail="Another response was recorded first; reload and try again")
    db.refresh(new)
    _notify(db, recv_role, recv_id, "offer_countered", "New counter-offer",
            f"Counter-offer: ₹{new.price_per_kg}/kg for {new.quantity_kg} kg.", "info")
    return new


# ─── accept / reject / withdraw ──────────────────────────────────────────────

@router.post("/{offer_id}/rounds/{round_id}/accept")
def accept_round(offer_id: int, round_id: int,
                 current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
                 db: Session = Depends(get_db)):
    """Accept the outstanding round (receiver only). The agreed price and
    quantity come from the STORED round, never the client. Uses the same
    finalize_acceptance() as the legacy endpoint."""
    user, role = current
    offer, kind, target = _load(db, offer_id, user, role, lock=True)
    neg.require_open_thread(offer)
    rnd = _load_round(db, offer, round_id)
    _require_latest(db, offer, rnd)
    neg.require_actionable_round(rnd, role)
    txn = neg.finalize_acceptance(db, offer, rnd, role, user.id)
    db.commit()
    other_role, other_id = neg.other_party(offer, target, role)
    _notify(db, other_role, other_id, "offer_accepted", "Offer accepted",
            f"Deal agreed at ₹{rnd.price_per_kg}/kg for {rnd.quantity_kg} kg.", "success")
    return {"accepted": True, "transaction_id": txn.id, "offer_id": offer.id, "round_id": rnd.id,
            "final_price_per_kg": txn.final_price_per_kg, "quantity_kg": txn.quantity_kg}


@router.post("/{offer_id}/rounds/{round_id}/reject")
def reject_round(offer_id: int, round_id: int,
                 current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
                 db: Session = Depends(get_db)):
    """Receiver rejects outright: closes THIS buyer's thread only."""
    user, role = current
    offer, kind, target = _load(db, offer_id, user, role, lock=True)
    neg.require_open_thread(offer)
    rnd = _load_round(db, offer, round_id)
    _require_latest(db, offer, rnd)
    neg.require_actionable_round(rnd, role)
    neg.close_thread(db, offer, rnd, kind, target, neg.R_REJECTED, "rejected")
    db.commit()
    other_role, other_id = neg.other_party(offer, target, role)
    _notify(db, other_role, other_id, "offer_rejected", "Offer declined",
            f"Round {rnd.sequence} was declined.", "warning")
    return {"rejected": True, "offer_id": offer.id, "round_id": rnd.id}


@router.post("/{offer_id}/withdraw")
def withdraw_offer(offer_id: int, current: Tuple[Participant, str] = Depends(require_farmer_or_buyer),
                   db: Session = Depends(get_db)):
    """The SENDER of the outstanding round withdraws it, ending the thread."""
    user, role = current
    offer, kind, target = _load(db, offer_id, user, role, lock=True)
    neg.require_open_thread(offer)
    rnd = neg.ensure_rounds(db, offer, target.farmer_id)
    neg.require_actionable_round(rnd, role, as_receiver=False)
    neg.close_thread(db, offer, rnd, kind, target, neg.R_WITHDRAWN, "withdrawn")
    db.commit()
    other_role, other_id = neg.other_party(offer, target, role)
    _notify(db, other_role, other_id, "offer_withdrawn", "Offer withdrawn",
            f"Round {rnd.sequence} was withdrawn.", "info")
    return {"withdrawn": True, "offer_id": offer.id, "round_id": rnd.id}
