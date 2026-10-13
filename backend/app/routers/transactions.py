"""
Transaction lifecycle router — Phase 10 & 12.

Lifecycle states:
    OFFER_CREATED → OFFER_ACCEPTED → ORDER_CONFIRMED →
    LOGISTICS_PENDING → LOGISTICS_CONFIRMED → PICKED_UP →
    IN_TRANSIT → DELIVERED → PAYMENT_PENDING →
    PAYMENT_INITIATED → PAYMENT_RECEIVED → COMPLETED

Old rows with status="completed" are treated as COMPLETED for display purposes.

Every status change creates a TransactionEvent row so the full timeline
is always available.
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, require_buyer, require_admin, get_current_user

router = APIRouter(prefix="/transactions", tags=["transactions"])

# Legal forward transitions (buyer or farmer can advance through these)
# Note: ORDER_CONFIRMED -> LOGISTICS_PENDING is intentionally NOT here.
# That transition now only happens as a side effect of the farmer actually
# creating a TransportRequest (see app/routers/transport.py), so it can't be
# faked via this endpoint without a real transport request behind it.
FARMER_ALLOWED_TRANSITIONS = {
    "LOGISTICS_CONFIRMED": ["PICKED_UP"],
    "PICKED_UP": ["IN_TRANSIT"],
    "PAYMENT_RECEIVED": ["COMPLETED"],
}

BUYER_ALLOWED_TRANSITIONS = {
    "OFFER_ACCEPTED": ["ORDER_CONFIRMED"],
    "IN_TRANSIT": ["DELIVERED"],
    "DELIVERED": ["PAYMENT_PENDING"],
    "PAYMENT_PENDING": ["PAYMENT_INITIATED"],
}

ADMIN_ALLOWED_TRANSITIONS = {
    # Admin can force any transition for dispute resolution -- including
    # ORDER_CONFIRMED -> LOGISTICS_PENDING, which farmers/buyers can only
    # reach organically by creating a real transport request.
    k: v for k, v in {
        **FARMER_ALLOWED_TRANSITIONS,
        **BUYER_ALLOWED_TRANSITIONS,
        "ORDER_CONFIRMED": ["LOGISTICS_PENDING"],
        "LOGISTICS_PENDING": ["LOGISTICS_CONFIRMED"],
        "PAYMENT_RECEIVED": ["COMPLETED"],
    }.items()
}


def _normalize_status(raw: str) -> str:
    """Map legacy 'completed' rows to the canonical COMPLETED status."""
    if raw and raw.lower() == "completed":
        return "COMPLETED"
    return raw


def _add_event(db: Session, txn_id: int, event_type: str, description: str,
               performed_by: str, performed_by_id: Optional[int] = None):
    db.add(models.TransactionEvent(
        transaction_id=txn_id,
        event_type=event_type,
        description=description,
        performed_by=performed_by,
        performed_by_id=performed_by_id,
    ))


def _txn_out(txn: models.Transaction) -> dict:
    """Serialize a transaction, normalizing legacy status."""
    return {
        "id": txn.id,
        "listing_id": txn.listing_id,
        "lot_id": txn.lot_id,
        "offer_id": txn.offer_id,
        "farmer_id": txn.farmer_id,
        "buyer_id": txn.buyer_id,
        "final_price_per_kg": txn.final_price_per_kg,
        "quantity_kg": txn.quantity_kg,
        "total_amount": txn.total_amount,
        "market_used": txn.market_used,
        "status": _normalize_status(txn.status),
        "created_at": txn.created_at.isoformat() if txn.created_at else None,
        "updated_at": txn.updated_at.isoformat() if txn.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Shared: both farmer and buyer can view their own transactions
# ---------------------------------------------------------------------------

@router.get("/mine")
def my_transactions(current=Depends(get_current_user), db: Session = Depends(get_db)):
    role = current["role"]
    user = current["user"]
    if role == "farmer":
        txns = db.query(models.Transaction).filter(
            models.Transaction.farmer_id == user.id
        ).order_by(models.Transaction.created_at.desc()).all()
    elif role == "buyer":
        txns = db.query(models.Transaction).filter(
            models.Transaction.buyer_id == user.id
        ).order_by(models.Transaction.created_at.desc()).all()
    else:
        txns = []
    return [_txn_out(t) for t in txns]


@router.get("/{txn_id}")
def get_transaction(txn_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    txn = db.query(models.Transaction).filter(models.Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    role = current["role"]
    user = current["user"]
    if role == "farmer" and txn.farmer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if role == "buyer" and txn.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    # admin can see all
    return _txn_out(txn)


# ---------------------------------------------------------------------------
# Timeline endpoint (Phase 12)
# ---------------------------------------------------------------------------

@router.get("/{txn_id}/timeline")
def transaction_timeline(txn_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    txn = db.query(models.Transaction).filter(models.Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    role = current["role"]
    user = current["user"]
    if role == "farmer" and txn.farmer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if role == "buyer" and txn.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    events = (
        db.query(models.TransactionEvent)
        .filter(models.TransactionEvent.transaction_id == txn_id)
        .order_by(models.TransactionEvent.created_at.asc())
        .all()
    )
    return {
        "transaction_id": txn_id,
        "current_status": _normalize_status(txn.status),
        "timeline": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "description": e.description,
                "performed_by": e.performed_by,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


# ---------------------------------------------------------------------------
# Status progression
# ---------------------------------------------------------------------------

@router.patch("/{txn_id}/status")
def update_transaction_status(
    txn_id: int,
    payload: schemas.TransactionStatusUpdate,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Advance transaction through the lifecycle.
    Farmers and buyers can move through their respective allowed transitions.
    Admin can perform any valid transition.
    """
    txn = db.query(models.Transaction).filter(models.Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    role = current["role"]
    user = current["user"]
    new_status = payload.status.upper()
    current_status = _normalize_status(txn.status)

    # Authorization: caller must be a party to this transaction
    if role == "farmer":
        if txn.farmer_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        allowed = FARMER_ALLOWED_TRANSITIONS.get(current_status, [])
    elif role == "buyer":
        if txn.buyer_id != user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        allowed = BUYER_ALLOWED_TRANSITIONS.get(current_status, [])
    elif role == "admin":
        allowed = ADMIN_ALLOWED_TRANSITIONS.get(current_status, [])
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    if new_status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current_status} to {new_status}. "
                   f"Allowed: {allowed or 'none from this state'}",
        )

    txn.status = new_status
    txn.updated_at = dt.datetime.utcnow()

    # Determine who performed this and record event
    by_id = user.id if role != "admin" else None
    status_descriptions = {
        "ORDER_CONFIRMED": "Order confirmed by buyer",
        "LOGISTICS_PENDING": "Logistics requested by farmer",
        "LOGISTICS_CONFIRMED": "Transport confirmed",
        "PICKED_UP": "Produce picked up from farm",
        "IN_TRANSIT": "In transit to delivery location",
        "DELIVERED": "Delivery confirmed by buyer",
        "PAYMENT_PENDING": "Awaiting payment",
        "PAYMENT_INITIATED": "Payment initiated by buyer (Demo simulated)",
        "PAYMENT_RECEIVED": "Payment received by farmer (Demo simulated)",
        "COMPLETED": "Transaction completed",
    }
    _add_event(
        db, txn_id, new_status,
        status_descriptions.get(new_status, f"Status changed to {new_status}"),
        role, by_id,
    )
    db.commit()
    return {"updated": True, "new_status": new_status, "transaction_id": txn_id}


# ---------------------------------------------------------------------------
# Admin: list all transactions
# ---------------------------------------------------------------------------

@router.get("")
def list_all_transactions(
    status: Optional[str] = None,
    farmer_id: Optional[int] = None,
    buyer_id: Optional[int] = None,
    limit: int = 50,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(models.Transaction)
    if status:
        q = q.filter(models.Transaction.status == status)
    if farmer_id:
        q = q.filter(models.Transaction.farmer_id == farmer_id)
    if buyer_id:
        q = q.filter(models.Transaction.buyer_id == buyer_id)
    txns = q.order_by(models.Transaction.created_at.desc()).limit(limit).all()
    return [_txn_out(t) for t in txns]
