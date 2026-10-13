"""
Phase 9 — Transport / Logistics Coordination
Upgrades FarmPool calculator into a real coordination workflow.
"""
import datetime as dt
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import AppError
from app import models, schemas
from app.auth_utils import require_farmer
from app.routers.transactions import _add_event, _normalize_status

router = APIRouter(prefix="/transport", tags=["transport"])

# Status flow
VALID_TRANSITIONS = {
    "REQUESTED": ["MATCHED", "CANCELLED"],
    "MATCHED":   ["CONFIRMED", "CANCELLED"],
    "CONFIRMED": ["PICKED_UP", "CANCELLED"],
    "PICKED_UP": ["IN_TRANSIT"],
    "IN_TRANSIT": ["DELIVERED"],
    "DELIVERED": [],
    "CANCELLED": [],
}

# Built-in vehicle options (from existing logistics mock data)
VEHICLE_OPTIONS = [
    {"vehicle": "Mahindra Bolero Pickup", "capacity_kg": 1500, "cost_per_km": 14, "type": "mini-truck"},
    {"vehicle": "Tata Ace (Chhota Hathi)", "capacity_kg": 750, "cost_per_km": 9, "type": "mini-truck"},
    {"vehicle": "Eicher 14ft Truck", "capacity_kg": 5000, "cost_per_km": 22, "type": "truck"},
    {"vehicle": "Tata 407 Truck", "capacity_kg": 2500, "cost_per_km": 17, "type": "truck"},
]


# ─── create request ───────────────────────────────────────────────────────────

@router.post("/requests")
def create_transport_request(
    payload: schemas.TransportRequestCreate,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Farmer creates a transport request for a lot/transaction."""
    lot_id = payload.lot_id
    if lot_id:
        lot = db.query(models.Lot).filter(models.Lot.id == lot_id, models.Lot.farmer_id == farmer.id).first()
        if not lot:
            raise AppError(status_code=404, code="LOT_NOT_FOUND_OR_NOT_YOURS", detail="Lot not found or not yours")

    # Validate + link the transaction this transport request fulfils, so
    # transport progress can drive the transaction lifecycle instead of the
    # two staying disconnected.
    transaction_id = payload.transaction_id
    txn = None
    if transaction_id:
        txn = db.query(models.Transaction).filter(models.Transaction.id == transaction_id).first()
        if not txn or txn.farmer_id != farmer.id:
            raise AppError(status_code=404, code="TRANSACTION_NOT_FOUND_OR_NOT_YOURS", detail="Transaction not found or not yours")

    req = models.TransportRequest(
        lot_id=lot_id,
        transaction_id=transaction_id,
        farmer_id=farmer.id,
        buyer_id=payload.buyer_id or (txn.buyer_id if txn else None),
        pickup_location=payload.pickup_location,
        destination=payload.destination,
        pickup_date=payload.pickup_date,
        pickup_time=payload.pickup_time,
        vehicle_type=payload.vehicle_type,
        quantity_kg=payload.quantity_kg,
        shared_transport=payload.shared_transport,
        estimated_cost=payload.estimated_cost,
        status="REQUESTED",
    )
    db.add(req)

    # If the transaction is confirmed and waiting on logistics, move it into
    # LOGISTICS_PENDING now that a transport request actually exists for it.
    if txn and _normalize_status(txn.status) == "ORDER_CONFIRMED":
        txn.status = "LOGISTICS_PENDING"
        txn.updated_at = dt.datetime.utcnow()
        _add_event(db, txn.id, "LOGISTICS_PENDING",
                   "Transport requested by farmer", "farmer", farmer.id)

    db.commit()
    db.refresh(req)

    # Auto-match: if shared transport, scan for compatible requests
    if req.shared_transport:
        _try_match_shared(req, db)

    return _request_dict(req)


def _try_match_shared(req: models.TransportRequest, db: Session):
    """Simple shared-transport matching: find another REQUESTED request going same route."""
    others = (
        db.query(models.TransportRequest)
        .filter(
            models.TransportRequest.id != req.id,
            models.TransportRequest.destination == req.destination,
            models.TransportRequest.status == "REQUESTED",
            models.TransportRequest.shared_transport == True,
        )
        .all()
    )
    if others:
        req.status = "MATCHED"
        db.commit()


# ─── list / get ──────────────────────────────────────────────────────────────

@router.get("/requests/mine")
def my_requests(farmer: models.Farmer = Depends(require_farmer), db: Session = Depends(get_db)):
    reqs = (
        db.query(models.TransportRequest)
        .filter(models.TransportRequest.farmer_id == farmer.id)
        .order_by(models.TransportRequest.created_at.desc())
        .all()
    )
    return [_request_dict(r) for r in reqs]


@router.get("/requests/{request_id}")
def get_request(
    request_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r or r.farmer_id != farmer.id:
        raise AppError(status_code=404, code="TRANSPORT_REQUEST_NOT_FOUND", detail="Transport request not found")
    return _request_dict(r)


# ─── status update ────────────────────────────────────────────────────────────

@router.patch("/requests/{request_id}/status")
def update_status(
    request_id: int,
    payload: schemas.TransportStatusUpdate,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r or r.farmer_id != farmer.id:
        raise AppError(status_code=404, code="TRANSPORT_REQUEST_NOT_FOUND", detail="Transport request not found")

    new_status = (payload.status or "").upper()
    if new_status not in VALID_TRANSITIONS.get(r.status, []):
        raise AppError(
            status_code=400,
            code="INVALID_STATUS_TRANSITION",
            detail=f"Cannot transition from {r.status} to {new_status}. "
                   f"Valid transitions: {VALID_TRANSITIONS.get(r.status, [])}",
        )
    r.status = new_status
    if new_status == "PICKED_UP":
        r.picked_up_at = dt.datetime.utcnow()
    if new_status == "DELIVERED":
        r.delivered_at = dt.datetime.utcnow()
    if payload.driver_name:
        r.driver_name = payload.driver_name
    if payload.driver_contact:
        r.driver_contact = payload.driver_contact
    if payload.vehicle_type:
        r.vehicle_type = payload.vehicle_type

    # If lot exists update its status too
    if r.lot_id and new_status in ("PICKED_UP", "IN_TRANSIT", "DELIVERED"):
        lot = db.query(models.Lot).filter(models.Lot.id == r.lot_id).first()
        if lot:
            if new_status == "PICKED_UP":
                lot.status = "IN_TRANSIT"
            elif new_status == "DELIVERED":
                lot.status = "DELIVERED"

    # Keep the linked transaction's lifecycle status in sync with real
    # transport events, so transport doesn't stay an isolated module.
    # Guarded by the transaction's current status so an out-of-order or
    # duplicate transport update can't skip/rewind transaction states.
    txn = None
    if r.transaction_id:
        txn = db.query(models.Transaction).filter(models.Transaction.id == r.transaction_id).first()
    if txn:
        current = _normalize_status(txn.status)
        transport_to_txn = {
            "CONFIRMED": ("LOGISTICS_PENDING", "LOGISTICS_CONFIRMED", "Transport confirmed"),
            "PICKED_UP": ("LOGISTICS_CONFIRMED", "PICKED_UP", "Produce picked up from farm"),
            "IN_TRANSIT": ("PICKED_UP", "IN_TRANSIT", "In transit to delivery location"),
            "DELIVERED": ("IN_TRANSIT", "DELIVERED", "Delivery confirmed via transport tracking"),
        }
        mapping = transport_to_txn.get(new_status)
        if mapping:
            required_from, txn_new_status, description = mapping
            if current == required_from:
                txn.status = txn_new_status
                txn.updated_at = dt.datetime.utcnow()
                _add_event(db, txn.id, txn_new_status, description, "farmer", r.farmer_id)

    db.commit()
    db.refresh(r)
    return _request_dict(r)


# ─── transporter quote / negotiation / agreed price ───────────────────────────
#
# See the note on TransportRequest.quote_status in models.py: there is no
# transporter login in this codebase, so the quote is recorded by the
# farmer who owns the request (the same person who already enters
# driver_name/driver_contact). Only that farmer can submit/counter/accept/
# reject it -- reusing the exact ownership check every other endpoint in
# this router already uses, not a new authorization system.

QUOTE_VALID_FROM = {
    "submit_quote":   ("AWAITING_QUOTE", "QUOTED", "COUNTERED"),
    "counter_offer":  ("QUOTED",),
    "accept":         ("QUOTED",),
    "reject":         ("QUOTED",),
}


def _load_owned_request(request_id: int, farmer: models.Farmer, db: Session) -> models.TransportRequest:
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r or r.farmer_id != farmer.id:
        raise AppError(status_code=404, code="TRANSPORT_REQUEST_NOT_FOUND", detail="Transport request not found")
    if r.status in ("DELIVERED", "CANCELLED"):
        raise AppError(status_code=400, code="TRIP_ALREADY_PAST_QUOTING", detail=f"Trip is already {r.status}; quote can no longer change")
    return r


@router.post("/requests/{request_id}/quote")
def submit_quote(
    request_id: int,
    payload: schemas.TransportQuoteSubmit,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Record the price the transporter actually quoted (not CropRetain's estimate)."""
    r = _load_owned_request(request_id, farmer, db)
    if r.quote_status not in QUOTE_VALID_FROM["submit_quote"]:
        raise AppError(status_code=400, code="INVALID_QUOTE_STATUS_FOR_SUBMIT", detail=f"Cannot submit a quote while quote_status is {r.quote_status}")
    r.quoted_price = payload.quoted_price
    r.quoted_at = dt.datetime.utcnow()
    r.quote_status = "QUOTED"
    db.commit()
    db.refresh(r)
    return _request_dict(r)


@router.post("/requests/{request_id}/quote/counter-offer")
def counter_offer(
    request_id: int,
    payload: schemas.TransportCounterOffer,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """One lightweight counter round: farmer proposes a different price.
    A revised quote (via submit_quote) moves it back to QUOTED so the
    farmer can accept/reject/counter again. Not real-time chat -- just a
    single stored proposal at a time."""
    r = _load_owned_request(request_id, farmer, db)
    if r.quote_status not in QUOTE_VALID_FROM["counter_offer"]:
        raise AppError(status_code=400, code="INVALID_QUOTE_STATUS_FOR_COUNTER", detail=f"Cannot counter-offer while quote_status is {r.quote_status}")
    r.counter_price = payload.counter_price
    r.counter_by = "farmer"
    r.counter_at = dt.datetime.utcnow()
    r.quote_status = "COUNTERED"
    db.commit()
    db.refresh(r)
    return _request_dict(r)


@router.post("/requests/{request_id}/quote/accept")
def accept_quote(
    request_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Farmer accepts the current quoted_price. The agreed price is computed
    and stored server-side from r.quoted_price -- never trusted from the
    request body, so the frontend cannot submit a different number."""
    r = _load_owned_request(request_id, farmer, db)
    if r.quote_status not in QUOTE_VALID_FROM["accept"]:
        raise AppError(status_code=400, code="INVALID_QUOTE_STATUS_FOR_ACCEPT", detail=f"Cannot accept while quote_status is {r.quote_status}")
    r.agreed_price = r.quoted_price
    r.agreed_at = dt.datetime.utcnow()
    r.quote_status = "ACCEPTED"
    db.commit()
    db.refresh(r)
    return _request_dict(r)


@router.post("/requests/{request_id}/quote/reject")
def reject_quote(
    request_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    r = _load_owned_request(request_id, farmer, db)
    if r.quote_status not in QUOTE_VALID_FROM["reject"]:
        raise AppError(status_code=400, code="INVALID_QUOTE_STATUS_FOR_REJECT", detail=f"Cannot reject while quote_status is {r.quote_status}")
    r.quote_status = "REJECTED"
    db.commit()
    db.refresh(r)
    return _request_dict(r)


# ─── cancel ──────────────────────────────────────────────────────────────────

@router.patch("/requests/{request_id}/cancel")
def cancel_request(
    request_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r or r.farmer_id != farmer.id:
        raise AppError(status_code=404, code="TRANSPORT_REQUEST_NOT_FOUND", detail="Transport request not found")
    if r.status in ("DELIVERED", "CANCELLED"):
        raise AppError(status_code=400, code="TRANSPORT_REQUEST_NOT_CANCELLABLE", detail=f"Cannot cancel a request in status {r.status}")
    r.status = "CANCELLED"
    db.commit()
    return {"cancelled": True}


# ─── vehicle options ─────────────────────────────────────────────────────────

@router.get("/vehicle-options")
def vehicle_options(quantity_kg: Optional[float] = Query(None)):
    """Return suitable vehicle options, optionally filtered by capacity."""
    if quantity_kg:
        return [v for v in VEHICLE_OPTIONS if v["capacity_kg"] >= quantity_kg]
    return VEHICLE_OPTIONS


# ─── helper ──────────────────────────────────────────────────────────────────

def _request_dict(r: models.TransportRequest) -> dict:
    return {
        "id": r.id,
        "lot_id": r.lot_id,
        "transaction_id": r.transaction_id,
        "farmer_id": r.farmer_id,
        "buyer_id": r.buyer_id,
        "pickup_location": r.pickup_location,
        "destination": r.destination,
        "pickup_date": r.pickup_date,
        "pickup_time": r.pickup_time,
        "vehicle_type": r.vehicle_type,
        "driver_name": r.driver_name,
        "driver_contact": r.driver_contact,
        "vehicle_capacity": r.vehicle_capacity,
        "quantity_kg": r.quantity_kg,
        "estimated_cost": r.estimated_cost,
        "shared_transport": r.shared_transport,
        "status": r.status,
        "status_label": _status_label(r.status),
        "picked_up_at": r.picked_up_at.isoformat() if r.picked_up_at else None,
        "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
        # Quote / negotiation / agreed price -- see models.py for why this
        # is recorded by the farmer rather than a separate transporter login.
        "quote_status": r.quote_status,
        "quoted_price": r.quoted_price,
        "quoted_at": r.quoted_at.isoformat() if r.quoted_at else None,
        "counter_price": r.counter_price,
        "counter_by": r.counter_by,
        "counter_at": r.counter_at.isoformat() if r.counter_at else None,
        "agreed_price": r.agreed_price,
        "agreed_at": r.agreed_at.isoformat() if r.agreed_at else None,
        # Real authenticated Transporter <-> Farmer workflow (separate
        # state machine from the legacy quote_status fields above -- see
        # models.py). transporter is only a lightweight public summary,
        # never the transporter's password hash or email.
        "transporter_id": r.transporter_id,
        "transporter": _transporter_summary(r.transporter) if r.transporter else None,
        "negotiation_status": r.negotiation_status,
        "claimed_at": r.claimed_at.isoformat() if r.claimed_at else None,
        "transporter_agreed_price": r.transporter_agreed_price,
        "transporter_agreed_at": r.transporter_agreed_at.isoformat() if r.transporter_agreed_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _transporter_summary(t: "models.Transporter") -> dict:
    return {
        "id": t.id, "name": t.name, "phone": t.phone,
        "business_name": t.business_name, "vehicle_types": t.vehicle_types,
        "rating": t.rating, "rating_count": t.rating_count,
    }


def _status_label(status: str) -> str:
    # NOTE: kept only for API backward-compatibility (e.g. external
    # integrations/tests that may read it). The frontend does NOT render
    # this value -- it derives the localized status label itself from the
    # `status` code via t(`transport.statusLabel.${status}`), so this
    # English-only string never reaches the UI regardless of the user's
    # selected language.
    return {
        "REQUESTED": "Transport Requested",
        "MATCHED": "Vehicle Matched",
        "CONFIRMED": "Pickup Confirmed",
        "PICKED_UP": "Goods Picked Up",
        "IN_TRANSIT": "In Transit",
        "DELIVERED": "Delivered",
        "CANCELLED": "Cancelled",
    }.get(status, status)
