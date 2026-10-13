from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.mock_data.locations import MARKETS, nearest_markets
from app.services.transport_optimizer import shared_transport_plan

router = APIRouter(prefix="/logistics", tags=["logistics"])

VEHICLES = [
    {"vehicle": "Mahindra Bolero Pickup", "capacity_kg": 1500, "cost_per_km": 14, "type": "mini-truck"},
    {"vehicle": "Tata Ace (Chhota Hathi)", "capacity_kg": 750, "cost_per_km": 9, "type": "mini-truck"},
    {"vehicle": "Eicher 14ft Truck", "capacity_kg": 5000, "cost_per_km": 22, "type": "truck"},
    {"vehicle": "Tata 407 Truck", "capacity_kg": 2500, "cost_per_km": 17, "type": "truck"},
]


@router.get("/vehicles")
def get_vehicles():
    return VEHICLES


@router.post("/farmpool")
def farmpool(payload: schemas.FarmPoolRequest, db: Session = Depends(get_db)):
    if payload.destination_market:
        destination = payload.destination_market
    else:
        candidates = [m for m in nearest_markets(payload.location) if m["name"] != payload.location]
        destination = candidates[0]["name"] if candidates else MARKETS[0]["name"]

    # If this pool request is linked to a real TransportRequest that has
    # already reached a transporter agreement, allocate shared cost from
    # that real, server-side price -- never from a client-supplied number,
    # and never overwriting the transport_optimizer estimate (see
    # shared_transport_plan()'s docstring/`cost_basis` field). Before an
    # agreement exists (no link, request not found, or still negotiating)
    # this silently falls back to the existing estimate-based behavior.
    agreed_transport_price = None
    if payload.transport_request_id is not None:
        tr = (
            db.query(models.TransportRequest)
            .filter(models.TransportRequest.id == payload.transport_request_id)
            .first()
        )
        if tr is not None and tr.transporter_agreed_price is not None:
            agreed_transport_price = tr.transporter_agreed_price

    plan = shared_transport_plan(
        crop=payload.crop, location=payload.location,
        quantity_kg=payload.quantity_kg, destination_market=destination,
        agreed_transport_price=agreed_transport_price,
    )
    plan["transport_request_id"] = payload.transport_request_id
    return plan
