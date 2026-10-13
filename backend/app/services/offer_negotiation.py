"""
Shared logic for multi-round crop-offer negotiation (buyer <-> farmer).

Design (see IMPLEMENTATION_NOTES.md):
  * BuyerOffer.status stays the THREAD-level commercial state
    ("pending" == negotiation open; accepted / rejected / withdrawn terminal).
  * BuyerOfferRound holds one immutable row per round. Strict turn-taking:
    only the RECEIVER of the latest PENDING round may respond.
  * ALL acceptance -- the legacy PATCH /offers/{id}/accept and the new
    round-accept endpoint -- goes through finalize_acceptance(), so the
    Transaction/inventory/event logic exists exactly once.
  * Identity (sender / receiver / farmer) is derived from the authenticated
    user plus listing/lot ownership; nothing identity-related is read from a
    request body.
"""
import datetime as dt
from typing import Optional, Tuple, Union

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models

MAX_ROUNDS_PER_OFFER = 20

R_PENDING, R_COUNTERED, R_ACCEPTED, R_REJECTED, R_WITHDRAWN = (
    "PENDING", "COUNTERED", "ACCEPTED", "REJECTED", "WITHDRAWN")
_LEGACY_TO_ROUND = {"pending": R_PENDING, "accepted": R_ACCEPTED,
                    "rejected": R_REJECTED, "withdrawn": R_WITHDRAWN}

Target = Union[models.CropListing, models.Lot]


def _now() -> dt.datetime:
    return dt.datetime.utcnow()


# ─── target (listing / lot) helpers ──────────────────────────────────────────

def load_target(db: Session, offer: models.BuyerOffer, lock: bool = False) -> Tuple[Optional[str], Optional[Target]]:
    """Returns ("listing"|"lot", row) or (None, None) if the target is gone.
    `lock=True` issues SELECT ... FOR UPDATE (a no-op on SQLite)."""
    if offer.listing_id:
        q = db.query(models.CropListing).filter(models.CropListing.id == offer.listing_id)
        kind = "listing"
    else:
        q = db.query(models.Lot).filter(models.Lot.id == offer.lot_id)
        kind = "lot"
    if lock:
        q = q.with_for_update()
    row = q.first()
    return (kind, row) if row else (None, None)


def target_open(kind: str, target: Target) -> bool:
    if kind == "listing":
        return target.status == "active"
    return target.status in ("AVAILABLE", "UNDER_OFFER")


def target_floor(kind: str, target: Target) -> Optional[float]:
    return target.min_acceptable_price if kind == "listing" else target.minimum_price


def target_summary(kind: str, target: Target, include_floor: bool) -> dict:
    d = {"kind": kind, "id": target.id, "crop": target.crop, "location": target.location,
         "quantity_kg": target.quantity_kg, "status": target.status,
         "expected_price_per_kg": target.expected_price_per_kg if kind == "listing" else target.expected_price}
    if kind == "lot":
        d["lot_number"] = target.lot_number
    if include_floor:
        d["min_price_per_kg"] = target_floor(kind, target)
    return d


# ─── rounds ──────────────────────────────────────────────────────────────────

def latest_round(db: Session, offer_id: int) -> Optional[models.BuyerOfferRound]:
    return (db.query(models.BuyerOfferRound)
            .filter(models.BuyerOfferRound.offer_id == offer_id)
            .order_by(models.BuyerOfferRound.sequence.desc()).first())


def ensure_rounds(db: Session, offer: models.BuyerOffer, farmer_id: int) -> models.BuyerOfferRound:
    """Lazy / idempotent backfill: an offer that predates negotiation (or was
    inserted directly) has no round rows. Create round 1 from it (buyer ->
    farmer) so every code path can assume at least one round exists. Never
    alters an offer that already has rounds."""
    existing = latest_round(db, offer.id)
    if existing:
        return existing
    r = models.BuyerOfferRound(
        offer_id=offer.id, sequence=1,
        sender_role="buyer", sender_id=offer.buyer_id,
        receiver_role="farmer", receiver_id=farmer_id,
        price_per_kg=offer.offered_price_per_kg, quantity_kg=offer.quantity_kg,
        message=offer.message or None, language=offer.language or "en",
        status=_LEGACY_TO_ROUND.get(offer.status, R_PENDING),
        created_at=offer.created_at or _now(),
        responded_at=None if offer.status == "pending" else (offer.created_at or _now()),
    )
    db.add(r)
    db.flush()
    return r


def create_first_round(db: Session, offer: models.BuyerOffer, farmer_id: int) -> models.BuyerOfferRound:
    """Called by POST /offers right after the BuyerOffer row is flushed."""
    return ensure_rounds(db, offer, farmer_id)


def backfill_offer_rounds(db: Session) -> int:
    """Startup backfill: one round-1 row for every pre-existing offer that has
    none. Idempotent. Offers whose listing/lot no longer exists are skipped
    (nothing can act on them anyway). Returns the number created."""
    ids_with_rounds = {r[0] for r in db.query(models.BuyerOfferRound.offer_id).distinct().all()}
    created = 0
    for offer in db.query(models.BuyerOffer).all():
        if offer.id in ids_with_rounds:
            continue
        kind, target = load_target(db, offer)
        if not target:
            continue
        ensure_rounds(db, offer, target.farmer_id)
        created += 1
    db.commit()
    return created


def awaiting_role_for(offer: models.BuyerOffer, rnd: Optional[models.BuyerOfferRound]) -> Optional[str]:
    if offer.status != "pending":
        return None
    if rnd is None:                    # legacy offer, no rounds yet: buyer offered, farmer's move
        return "farmer"
    return rnd.receiver_role if rnd.status == R_PENDING else None


def annotate_offers(db: Session, offers: list) -> list:
    """Attach transient awaiting_role / round_count to ORM offers so the
    existing OfferOut response model can serialise them."""
    if not offers:
        return offers
    ids = [o.id for o in offers]
    rows = (db.query(models.BuyerOfferRound)
            .filter(models.BuyerOfferRound.offer_id.in_(ids))
            .order_by(models.BuyerOfferRound.offer_id, models.BuyerOfferRound.sequence).all())
    last, count = {}, {}
    for r in rows:
        last[r.offer_id] = r
        count[r.offer_id] = count.get(r.offer_id, 0) + 1
    for o in offers:
        o.awaiting_role = awaiting_role_for(o, last.get(o.id))
        o.round_count = count.get(o.id, 1)
    return offers


# ─── participation / turn checks ─────────────────────────────────────────────

def participant_role_check(offer: models.BuyerOffer, target: Target, user, role: str) -> None:
    """404 (not 403) for non-participants -- no existence leak, matching the
    transport-negotiation pattern."""
    if role == "buyer":
        ok = offer.buyer_id == user.id
    elif role == "farmer":
        ok = target.farmer_id == user.id
    else:
        ok = False
    if not ok:
        raise HTTPException(status_code=404, detail="Offer not found")


def other_party(offer: models.BuyerOffer, target: Target, role: str) -> Tuple[str, int]:
    return ("farmer", target.farmer_id) if role == "buyer" else ("buyer", offer.buyer_id)


def require_open_thread(offer: models.BuyerOffer) -> None:
    if offer.status != "pending":
        raise HTTPException(status_code=400,
                            detail=f"This offer is already {offer.status} and cannot be changed")


def require_actionable_round(rnd: models.BuyerOfferRound, role: str, *, as_receiver: bool = True) -> None:
    """The round must be the latest, still-PENDING one, and the caller must be
    its receiver (or its sender, for withdraw)."""
    if rnd.status != R_PENDING:
        raise HTTPException(status_code=409,
                            detail=f"Round {rnd.sequence} is already {rnd.status.lower()} (stale request)")
    mine = rnd.receiver_role if as_receiver else rnd.sender_role
    if mine != role:
        raise HTTPException(
            status_code=400,
            detail=("Waiting on the other party to respond to your last offer" if as_receiver
                    else "Only the sender of the outstanding offer can withdraw it"))


def validate_terms(kind: str, target: Target, role: str, price: float, qty: float) -> None:
    if price is None or price <= 0:
        raise HTTPException(status_code=400, detail="Offer price must be greater than zero")
    if qty is None or qty <= 0:
        raise HTTPException(status_code=400, detail="Offer quantity must be greater than zero")
    if not target_open(kind, target):
        raise HTTPException(status_code=400,
                            detail="This listing is no longer active" if kind == "listing"
                            else f"This lot is {target.status} and cannot receive new offers")
    if qty > target.quantity_kg:
        raise HTTPException(status_code=400,
                            detail=f"Offer quantity ({qty} kg) exceeds the available quantity ({target.quantity_kg} kg)")
    floor = target_floor(kind, target)
    if role == "buyer" and floor is not None and price < floor:
        raise HTTPException(status_code=400, detail="Offer is below the farmer's minimum acceptable price")


# ─── thread-closing (reject / withdraw) ──────────────────────────────────────

def _release_lot_if_idle(db: Session, offer: models.BuyerOffer, kind: str, target: Target) -> None:
    """Legacy behaviour: if no other pending offers remain on a lot that is
    UNDER_OFFER, free it back to AVAILABLE."""
    if kind != "lot":
        return
    remaining = (db.query(models.BuyerOffer)
                 .filter(models.BuyerOffer.lot_id == target.id, models.BuyerOffer.id != offer.id,
                         models.BuyerOffer.status == "pending").count())
    if remaining == 0 and target.status == "UNDER_OFFER":
        target.status = "AVAILABLE"


def close_thread(db: Session, offer: models.BuyerOffer, rnd: models.BuyerOfferRound,
                 kind: str, target: Target, round_status: str, thread_status: str) -> None:
    now = _now()
    rnd.status = round_status
    rnd.responded_at = now
    offer.status = thread_status
    offer.updated_at = now
    _release_lot_if_idle(db, offer, kind, target)


# ─── shared finalization (the ONE acceptance routine) ────────────────────────

def finalize_acceptance(db: Session, offer: models.BuyerOffer, rnd: models.BuyerOfferRound,
                        accepted_by: str, actor_id: int) -> models.Transaction:
    """Accept `rnd` and create the authoritative deal.

    Used by BOTH the legacy farmer PATCH accept and the new round-accept
    endpoint. Re-locks and re-validates the target (so two competing accepts
    cannot oversell), decrements inventory, closes sibling threads on
    sell-out, snapshots the agreed terms onto the offer, creates the
    Transaction (farmer_id from OWNERSHIP, never from the caller's role) and
    rebuilds the negotiation timeline from the rounds. Caller commits.
    """
    kind, target = load_target(db, offer, lock=True)
    if not target:
        raise HTTPException(status_code=404, detail="Listing not found" if offer.listing_id else "Lot not found")
    if kind == "listing":
        if target.status != "active":
            raise HTTPException(status_code=400, detail="This listing is no longer active")
        if rnd.quantity_kg > target.quantity_kg:
            raise HTTPException(status_code=400, detail="Offer quantity exceeds the remaining listing quantity")
    else:
        if target.status not in ("AVAILABLE", "UNDER_OFFER"):
            raise HTTPException(status_code=400, detail=f"This lot is {target.status} and cannot be sold")
        if rnd.quantity_kg > target.quantity_kg:
            raise HTTPException(status_code=400, detail="Offer quantity exceeds the remaining lot quantity")

    now = _now()
    target.quantity_kg = round(target.quantity_kg - rnd.quantity_kg, 2)
    if kind == "listing":
        target.status = "sold" if target.quantity_kg <= 0 else "active"
        sold_out = target.status == "sold"
        sibling_filter = models.BuyerOffer.listing_id == target.id
        lot_id = None
    else:
        target.status = "SOLD" if target.quantity_kg <= 0 else "AVAILABLE"
        sold_out = target.status == "SOLD"
        sibling_filter = models.BuyerOffer.lot_id == target.id
        lot_id = target.id
        if offer.buyer_demand_id:   # close out the demand this offer was fulfilling (legacy behaviour)
            demand = db.query(models.BuyerDemand).filter(models.BuyerDemand.id == offer.buyer_demand_id).first()
            if demand and demand.status not in ("FULFILLED", "CANCELLED", "EXPIRED"):
                demand.status = "FULFILLED"

    if sold_out:   # reject other pending threads, and close their outstanding rounds consistently
        others = (db.query(models.BuyerOffer)
                  .filter(sibling_filter, models.BuyerOffer.id != offer.id, models.BuyerOffer.status == "pending").all())
        for o in others:
            o.status = "rejected"
            o.updated_at = now
            for orn in (db.query(models.BuyerOfferRound)
                        .filter(models.BuyerOfferRound.offer_id == o.id,
                                models.BuyerOfferRound.status == R_PENDING).all()):
                orn.status = R_REJECTED
                orn.responded_at = now

    rnd.status = R_ACCEPTED
    rnd.responded_at = now
    offer.status = "accepted"
    offer.offered_price_per_kg = rnd.price_per_kg   # mirror stays equal to the accepted round
    offer.quantity_kg = rnd.quantity_kg
    offer.accepted_round_id = rnd.id
    offer.agreed_price_per_kg = rnd.price_per_kg
    offer.agreed_quantity_kg = rnd.quantity_kg
    offer.agreed_at = now
    offer.updated_at = now

    txn = models.Transaction(
        listing_id=offer.listing_id, lot_id=lot_id, offer_id=offer.id,
        farmer_id=target.farmer_id, buyer_id=offer.buyer_id,
        final_price_per_kg=rnd.price_per_kg, quantity_kg=rnd.quantity_kg,
        total_amount=round(rnd.price_per_kg * rnd.quantity_kg, 2),
        market_used=target.location, status="OFFER_ACCEPTED",
    )
    db.add(txn)
    db.flush()

    rounds = (db.query(models.BuyerOfferRound).filter(models.BuyerOfferRound.offer_id == offer.id)
              .order_by(models.BuyerOfferRound.sequence).all())
    first = rounds[0] if rounds else rnd
    db.add(models.TransactionEvent(
        transaction_id=txn.id, event_type="OFFER_CREATED",
        description=f"Offer of ₹{first.price_per_kg}/kg created by buyer",
        performed_by="buyer", performed_by_id=offer.buyer_id, created_at=first.created_at or now))
    for r in rounds[1:]:
        if r.id == rnd.id and r.sequence == first.sequence:
            continue
        if r.sequence >= rnd.sequence:
            break
        db.add(models.TransactionEvent(
            transaction_id=txn.id, event_type="OFFER_COUNTERED",
            description=f"Round {r.sequence}: {r.sender_role} proposed ₹{r.price_per_kg}/kg for {r.quantity_kg} kg",
            performed_by=r.sender_role, performed_by_id=r.sender_id, created_at=r.created_at or now))
    db.add(models.TransactionEvent(
        transaction_id=txn.id, event_type="OFFER_ACCEPTED",
        description=f"Offer accepted by {accepted_by}. Transaction initiated.",
        performed_by=accepted_by, performed_by_id=actor_id))
    return txn
