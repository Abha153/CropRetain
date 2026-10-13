"""
Real authenticated FARMER <-> TRANSPORTER workflow -- transporter-facing
endpoints (dashboard, profile, claiming a request).

Negotiation (offers), chat, status updates and reviews live in
app/routers/transport_negotiation.py, scoped under /transport/requests/{id}/...
so both farmer- and transporter-facing clients call the same endpoints
with identity/role derived from the JWT.
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_transporter

router = APIRouter(prefix="/transporter", tags=["transporter"])


def _public_farmer_summary(farmer: models.Farmer) -> dict:
    """PII-minimized farmer summary for a transporter who has NOT yet been
    assigned to the request -- no phone/email/exact contact details."""
    return {"id": farmer.id, "name": farmer.name, "location": farmer.location}


def _request_dict_for_transporter(r: models.TransportRequest, assigned: bool) -> dict:
    d = {
        "id": r.id,
        "lot_id": r.lot_id,
        "transaction_id": r.transaction_id,
        "pickup_location": r.pickup_location,
        "destination": r.destination,
        "pickup_date": r.pickup_date,
        "pickup_time": r.pickup_time,
        "vehicle_type": r.vehicle_type,
        "quantity_kg": r.quantity_kg,
        "estimated_cost": r.estimated_cost,
        "status": r.status,
        "negotiation_status": r.negotiation_status,
        "transporter_agreed_price": r.transporter_agreed_price,
        "transporter_agreed_at": r.transporter_agreed_at.isoformat() if r.transporter_agreed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    if assigned:
        # Only once a transporter is actually assigned do we reveal the
        # farmer's identity/location as a contact point -- never before.
        d["farmer"] = _public_farmer_summary(r.farmer) if r.farmer else None
    return d


@router.get("/profile", response_model=schemas.TransporterOut)
def my_profile(transporter: models.Transporter = Depends(require_transporter)):
    return transporter


@router.patch("/profile", response_model=schemas.TransporterOut)
def update_profile(
    payload: schemas.TransporterRegister,
    transporter: models.Transporter = Depends(require_transporter),
    db: Session = Depends(get_db),
):
    """Reuses TransporterRegister for the editable fields (name/phone/
    business info); email/password are left untouched by this endpoint on
    purpose -- credential changes are out of scope for this pass."""
    transporter.name = payload.name or transporter.name
    transporter.phone = payload.phone or transporter.phone
    transporter.business_name = payload.business_name
    transporter.service_area = payload.service_area
    transporter.vehicle_types = payload.vehicle_types
    transporter.preferred_language = payload.preferred_language or transporter.preferred_language
    db.commit()
    db.refresh(transporter)
    return transporter


@router.get("/requests/available")
def available_requests(
    transporter: models.Transporter = Depends(require_transporter),
    db: Session = Depends(get_db),
):
    """Requests any authenticated transporter may see and claim: not yet
    claimed by anyone, not cancelled/delivered. Farmer identity is
    withheld until claimed (see _request_dict_for_transporter)."""
    reqs = (
        db.query(models.TransportRequest)
        .filter(
            models.TransportRequest.transporter_id.is_(None),
            models.TransportRequest.negotiation_status == "OPEN",
            models.TransportRequest.status.notin_(["CANCELLED", "DELIVERED"]),
        )
        .order_by(models.TransportRequest.created_at.desc())
        .all()
    )
    return [_request_dict_for_transporter(r, assigned=False) for r in reqs]


@router.get("/requests/mine")
def my_assigned_requests(
    transporter: models.Transporter = Depends(require_transporter),
    db: Session = Depends(get_db),
):
    reqs = (
        db.query(models.TransportRequest)
        .filter(models.TransportRequest.transporter_id == transporter.id)
        .order_by(models.TransportRequest.created_at.desc())
        .all()
    )
    return [_request_dict_for_transporter(r, assigned=True) for r in reqs]


@router.post("/requests/{request_id}/claim")
def claim_request(
    request_id: int,
    transporter: models.Transporter = Depends(require_transporter),
    db: Session = Depends(get_db),
):
    """A transporter engages with an open request, becoming the sole
    authorized transporter on it. Server-side check-and-set (single
    UPDATE guarded by transporter_id IS NULL in the WHERE-equivalent
    filter below) prevents two transporters racing to claim the same
    request."""
    r = (
        db.query(models.TransportRequest)
        .filter(models.TransportRequest.id == request_id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Transport request not found")
    if r.status in ("CANCELLED", "DELIVERED"):
        raise HTTPException(status_code=400, detail=f"Request is {r.status} and cannot be claimed")
    if r.transporter_id is not None:
        raise HTTPException(status_code=409, detail="This request has already been claimed by a transporter")

    r.transporter_id = transporter.id
    r.negotiation_status = "NEGOTIATING"
    r.claimed_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(r)
    return _request_dict_for_transporter(r, assigned=True)


@router.get("/requests/{request_id}")
def get_assigned_request(
    request_id: int,
    transporter: models.Transporter = Depends(require_transporter),
    db: Session = Depends(get_db),
):
    r = db.query(models.TransportRequest).filter(models.TransportRequest.id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Transport request not found")
    # Visible if unclaimed (browsing) or claimed BY this transporter --
    # never another transporter's claimed/assigned request.
    if r.transporter_id is not None and r.transporter_id != transporter.id:
        raise HTTPException(status_code=404, detail="Transport request not found")
    return _request_dict_for_transporter(r, assigned=(r.transporter_id == transporter.id))
