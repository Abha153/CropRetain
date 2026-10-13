"""
Phase 16 — Notifications (extended for buyers)
Reuses existing Notification model which already has buyer_id column.
"""
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth_utils import require_farmer, require_buyer

router = APIRouter(prefix="/notifications", tags=["notifications"])

ALERT_TEMPLATES = [
    dict(type="price_drop", severity="warning", title="Price drop alert",
         message="{crop} prices in {market} have dropped recently -- compare nearby markets before selling."),
    dict(type="high_demand", severity="success", title="High demand nearby",
         message="A buyer near your location is looking for bulk {crop}. Check the marketplace for new offers."),
    dict(type="opportunity", severity="success", title="Selling opportunity",
         message="Your estimated net profit for {crop} may be higher in a nearby market this week."),
    dict(type="harvest_reminder", severity="info", title="Harvest reminder",
         message="Based on your crop calendar, it may be time to update your available {crop} quantity."),
]

BUYER_ALERT_TEMPLATES = [
    dict(type="new_lot", severity="success", title="New lot available",
         message="A new {crop} lot has been listed that matches your demand requirements."),
    dict(type="offer_update", severity="info", title="Offer update",
         message="There has been an update to one of your active offers for {crop}."),
    dict(type="verification_update", severity="info", title="Verification update",
         message="Your buyer verification status has been updated. Check your profile."),
    dict(type="payment_due", severity="warning", title="Payment reminder",
         message="A payment for your recent {crop} order is coming due soon."),
]


# ─── farmer notifications ─────────────────────────────────────────────────────

@router.get("/mine")
def my_notifications(farmer: models.Farmer = Depends(require_farmer), db: Session = Depends(get_db)):
    return (
        db.query(models.Notification)
        .filter(models.Notification.farmer_id == farmer.id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, farmer: models.Farmer = Depends(require_farmer),
              db: Session = Depends(get_db)):
    n = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not n or n.farmer_id != farmer.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"marked_read": True}


@router.post("/generate")
def generate_alert(farmer: models.Farmer = Depends(require_farmer), db: Session = Depends(get_db)):
    """Demo helper: generates one fresh alert for the farmer's crops."""
    crop = random.choice(farmer.crops) if farmer.crops else "your crop"
    template = random.choice(ALERT_TEMPLATES)
    n = models.Notification(
        farmer_id=farmer.id, type=template["type"], severity=template["severity"],
        title=template["title"], message=template["message"].format(crop=crop, market=farmer.location),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


# ─── buyer notifications ──────────────────────────────────────────────────────

@router.get("/buyer/mine")
def my_buyer_notifications(buyer: models.Buyer = Depends(require_buyer), db: Session = Depends(get_db)):
    return (
        db.query(models.Notification)
        .filter(models.Notification.buyer_id == buyer.id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )


@router.patch("/buyer/{notification_id}/read")
def mark_buyer_notification_read(
    notification_id: int,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    n = db.query(models.Notification).filter(models.Notification.id == notification_id).first()
    if not n or n.buyer_id != buyer.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"marked_read": True}


@router.post("/buyer/generate")
def generate_buyer_alert(buyer: models.Buyer = Depends(require_buyer), db: Session = Depends(get_db)):
    """Demo helper: generates one fresh alert for the buyer."""
    crop = random.choice(buyer.crops) if buyer.crops else "your crop"
    template = random.choice(BUYER_ALERT_TEMPLATES)
    n = models.Notification(
        buyer_id=buyer.id, type=template["type"], severity=template["severity"],
        title=template["title"], message=template["message"].format(crop=crop),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


# ─── utility: send notification (called from other routers) ──────────────────

def send_farmer_notification(db: Session, farmer_id: int, type_: str, title: str, message: str,
                              severity: str = "info"):
    """Create a notification for a farmer. Silent on error."""
    try:
        n = models.Notification(farmer_id=farmer_id, type=type_, title=title,
                                message=message, severity=severity)
        db.add(n)
        db.commit()
    except Exception:
        db.rollback()


def send_buyer_notification(db: Session, buyer_id: int, type_: str, title: str, message: str,
                             severity: str = "info"):
    """Create a notification for a buyer. Silent on error."""
    try:
        n = models.Notification(buyer_id=buyer_id, type=type_, title=title,
                                message=message, severity=severity)
        db.add(n)
        db.commit()
    except Exception:
        db.rollback()
