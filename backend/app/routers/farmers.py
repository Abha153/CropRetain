from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer

router = APIRouter(prefix="/farmers", tags=["farmers"])


@router.get("/me", response_model=schemas.FarmerOut)
def get_me(farmer: models.Farmer = Depends(require_farmer)):
    return farmer


@router.put("/me", response_model=schemas.FarmerOut)
def update_me(payload: schemas.FarmerUpdate, farmer: models.Farmer = Depends(require_farmer),
              db: Session = Depends(get_db)):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farmer, field, value)
    db.commit()
    db.refresh(farmer)
    return farmer


@router.get("/{farmer_id}", response_model=schemas.FarmerPublicOut)
def get_farmer(farmer_id: int, db: Session = Depends(get_db)):
    """Public marketplace view -- deliberately excludes email/phone (see FarmerPublicOut)."""
    farmer = db.query(models.Farmer).filter(models.Farmer.id == farmer_id).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found")
    return farmer
