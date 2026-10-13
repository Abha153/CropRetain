from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer

router = APIRouter(prefix="/group-selling", tags=["group-selling"])


@router.get("")
def list_pools(crop: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.GroupSellingPool).filter(models.GroupSellingPool.status == "open")
    if crop:
        q = q.filter(models.GroupSellingPool.crop == crop)
    pools = q.all()
    results = []
    for p in pools:
        member_count = len(p.member_farmer_ids)
        total_qty = p.total_quantity_kg
        estimated_price_improvement_pct = min(4 + member_count * 2.5 + (total_qty / 5000), 18)
        results.append({
            "id": p.id, "crop": p.crop, "fpo_name": p.fpo_name,
            "member_count": member_count, "total_quantity_kg": total_qty,
            "estimated_price_improvement_pct": round(estimated_price_improvement_pct, 1),
            "potential_bulk_buyers": 4 + member_count * 2,
        })
    return results


@router.post("/join")
def join_pool(payload: schemas.GroupSellingJoin, farmer: models.Farmer = Depends(require_farmer),
              db: Session = Depends(get_db)):
    pool = (
        db.query(models.GroupSellingPool)
        .filter(models.GroupSellingPool.crop == payload.crop, models.GroupSellingPool.status == "open")
        .first()
    )
    if not pool:
        pool = models.GroupSellingPool(
            crop=payload.crop, fpo_name=payload.fpo_name or f"{farmer.location} Growers Collective",
            status="open",
        )
        db.add(pool)
        db.commit()
        db.refresh(pool)

    # Upsert this farmer's membership -- re-joining updates quantity instead
    # of duplicating/adding on top of it (fixes prior double-count bug).
    membership = (
        db.query(models.GroupPoolMembership)
        .filter(models.GroupPoolMembership.pool_id == pool.id,
                models.GroupPoolMembership.farmer_id == farmer.id)
        .first()
    )
    if membership:
        membership.quantity_kg = payload.quantity_kg
    else:
        membership = models.GroupPoolMembership(
            pool_id=pool.id, farmer_id=farmer.id, quantity_kg=payload.quantity_kg,
        )
        db.add(membership)
    db.commit()
    db.refresh(pool)

    return {
        "id": pool.id, "crop": pool.crop, "fpo_name": pool.fpo_name,
        "member_count": len(pool.member_farmer_ids),
        "total_quantity_kg": pool.total_quantity_kg,
    }
