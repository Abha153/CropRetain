from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_buyer, require_farmer
from app.services import offer_negotiation as neg
from app.routers.notifications import send_farmer_notification, send_buyer_notification

router = APIRouter(prefix="/offers", tags=["offers"])


@router.post("", response_model=schemas.OfferOut)
def create_offer(payload: schemas.OfferCreate, buyer: models.Buyer = Depends(require_buyer),
                  db: Session = Depends(get_db)):
    if bool(payload.listing_id) == bool(payload.lot_id):
        raise HTTPException(status_code=400, detail="Provide exactly one of listing_id or lot_id")

    if payload.offered_price_per_kg <= 0:
        raise HTTPException(status_code=400, detail="Offer price must be greater than zero")
    if payload.quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="Offer quantity must be greater than zero")

    demand = None
    if payload.buyer_demand_id:
        demand = db.query(models.BuyerDemand).filter(
            models.BuyerDemand.id == payload.buyer_demand_id
        ).first()
        if not demand or demand.buyer_id != buyer.id:
            raise HTTPException(status_code=403, detail="You can only reference your own buyer demand")

    if payload.listing_id:
        listing = db.query(models.CropListing).filter(models.CropListing.id == payload.listing_id).first()
        if not listing:
            raise HTTPException(status_code=404, detail="Listing not found")
        if listing.status != "active":
            raise HTTPException(status_code=400, detail="This listing is no longer active")
        if payload.quantity_kg > listing.quantity_kg:
            raise HTTPException(
                status_code=400,
                detail=f"Offer quantity ({payload.quantity_kg} kg) exceeds the listed quantity ({listing.quantity_kg} kg)",
            )
        if listing.min_acceptable_price is not None and payload.offered_price_per_kg < listing.min_acceptable_price:
            raise HTTPException(
                status_code=400,
                detail=f"Offer is below the farmer's minimum acceptable price of \u20b9{listing.min_acceptable_price}/kg",
            )
        offer = models.BuyerOffer(
            buyer_id=buyer.id, listing_id=payload.listing_id,
            buyer_demand_id=payload.buyer_demand_id,
            offered_price_per_kg=payload.offered_price_per_kg,
            quantity_kg=payload.quantity_kg, message=payload.message or "",
            language=payload.language,
        )
    else:
        lot = db.query(models.Lot).filter(models.Lot.id == payload.lot_id).first()
        if not lot:
            raise HTTPException(status_code=404, detail="Lot not found")
        if lot.status not in ("AVAILABLE", "UNDER_OFFER"):
            raise HTTPException(status_code=400, detail=f"This lot is {lot.status} and cannot receive new offers")
        if payload.quantity_kg > lot.quantity_kg:
            raise HTTPException(
                status_code=400,
                detail=f"Offer quantity ({payload.quantity_kg} kg) exceeds the lot quantity ({lot.quantity_kg} kg)",
            )
        if lot.minimum_price is not None and payload.offered_price_per_kg < lot.minimum_price:
            raise HTTPException(
                status_code=400,
                detail=f"Offer is below the farmer's minimum acceptable price of \u20b9{lot.minimum_price}/kg",
            )
        offer = models.BuyerOffer(
            buyer_id=buyer.id, lot_id=payload.lot_id,
            buyer_demand_id=payload.buyer_demand_id,
            offered_price_per_kg=payload.offered_price_per_kg,
            quantity_kg=payload.quantity_kg, message=payload.message or "",
            language=payload.language,
        )
        lot.status = "UNDER_OFFER"

    db.add(offer)
    db.flush()
    # Round 1 of the negotiation thread: buyer -> farmer (owner of the target).
    owner_id = (listing.farmer_id if payload.listing_id else lot.farmer_id)
    neg.create_first_round(db, offer, owner_id)
    db.commit()
    db.refresh(offer)
    neg.annotate_offers(db, [offer])
    return offer


@router.get("/listing/{listing_id}", response_model=List[schemas.OfferOut])
def offers_for_listing(listing_id: int, farmer: models.Farmer = Depends(require_farmer),
                        db: Session = Depends(get_db)):
    listing = db.query(models.CropListing).filter(models.CropListing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    if listing.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="You can only view offers on your own listings")
    offers = (
        db.query(models.BuyerOffer)
        .filter(models.BuyerOffer.listing_id == listing_id)
        .order_by(models.BuyerOffer.offered_price_per_kg.desc())
        .all()
    )
    return neg.annotate_offers(db, offers)


@router.get("/lot/{lot_id}", response_model=List[schemas.OfferOut])
def offers_for_lot(lot_id: int, farmer: models.Farmer = Depends(require_farmer),
                    db: Session = Depends(get_db)):
    lot = db.query(models.Lot).filter(models.Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    if lot.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="You can only view offers on your own lots")
    offers = (
        db.query(models.BuyerOffer)
        .filter(models.BuyerOffer.lot_id == lot_id)
        .order_by(models.BuyerOffer.offered_price_per_kg.desc())
        .all()
    )
    return neg.annotate_offers(db, offers)


@router.get("/mine", response_model=List[schemas.OfferOut])
def my_offers(buyer: models.Buyer = Depends(require_buyer), db: Session = Depends(get_db)):
    return neg.annotate_offers(db, (
        db.query(models.BuyerOffer)
        .filter(models.BuyerOffer.buyer_id == buyer.id)
        .order_by(models.BuyerOffer.created_at.desc())
        .all()
    ))


def _farmer_owned_target(offer, farmer, db, verb):
    """Legacy ownership check (403 + legacy messages) for the farmer PATCH endpoints."""
    kind, target = neg.load_target(db, offer)
    noun = "listings" if offer.listing_id else "lots"
    if not target or target.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail=f"You can only {verb} offers on your own {noun}")
    return kind, target


@router.patch("/{offer_id}/accept")
def accept_offer(offer_id: int, farmer: models.Farmer = Depends(require_farmer),
                 db: Session = Depends(get_db)):
    """Legacy farmer accept (path/behaviour preserved). Turn-aware: if the
    buyer currently holds the move (farmer countered), the farmer cannot
    accept their own counter. All acceptance goes through the shared
    finalize_acceptance() routine."""
    offer = (db.query(models.BuyerOffer).filter(models.BuyerOffer.id == offer_id)
             .with_for_update().first())
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "pending":
        raise HTTPException(status_code=400, detail=f"This offer is already {offer.status} and cannot be changed")
    _farmer_owned_target(offer, farmer, db, "accept")
    rnd = neg.ensure_rounds(db, offer, farmer.id)
    neg.require_actionable_round(rnd, "farmer")
    txn = neg.finalize_acceptance(db, offer, rnd, "farmer", farmer.id)
    db.commit()
    send_buyer_notification(db, offer.buyer_id, "offer_accepted", "Offer accepted",
                            f"Your offer of ₹{offer.agreed_price_per_kg}/kg was accepted.", "success")
    return {"accepted": True, "transaction_id": txn.id}


@router.patch("/{offer_id}/reject")
def reject_offer(offer_id: int, farmer: models.Farmer = Depends(require_farmer),
                 db: Session = Depends(get_db)):
    """Legacy farmer reject (path/behaviour preserved), now turn-aware."""
    offer = (db.query(models.BuyerOffer).filter(models.BuyerOffer.id == offer_id)
             .with_for_update().first())
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "pending":
        raise HTTPException(status_code=400, detail=f"This offer is already {offer.status} and cannot be changed")
    kind, target = _farmer_owned_target(offer, farmer, db, "reject")
    rnd = neg.ensure_rounds(db, offer, farmer.id)
    neg.require_actionable_round(rnd, "farmer")
    neg.close_thread(db, offer, rnd, kind, target, neg.R_REJECTED, "rejected")
    db.commit()
    send_buyer_notification(db, offer.buyer_id, "offer_rejected", "Offer declined",
                            "The farmer declined your offer.", "warning")
    return {"rejected": True}
