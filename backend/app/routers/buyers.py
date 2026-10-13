from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_buyer

router = APIRouter(prefix="/buyers", tags=["buyers"])


@router.get("/me", response_model=schemas.BuyerOut)
def get_me(buyer: models.Buyer = Depends(require_buyer)):
    return buyer


@router.get("", response_model=List[schemas.BuyerPublicOut])
def list_buyers(crop: Optional[str] = None, buyer_type: Optional[str] = None,
                 db: Session = Depends(get_db)):
    """Public marketplace directory -- deliberately excludes email/phone."""
    q = db.query(models.Buyer)
    if buyer_type:
        q = q.filter(models.Buyer.buyer_type == buyer_type)
    buyers = q.all()
    if crop:
        buyers = [b for b in buyers if crop in (b.crops_of_interest or [])]
    return buyers


@router.get("/{buyer_id}", response_model=schemas.BuyerPublicOut)
def get_buyer(buyer_id: int, db: Session = Depends(get_db)):
    buyer = db.query(models.Buyer).filter(models.Buyer.id == buyer_id).first()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")
    return buyer
