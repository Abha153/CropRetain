"""GET /market/past-prices -- recorded price history for one crop/market (see services/past_prices.py)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers import market as market_router
from app.services import past_prices

router = APIRouter(prefix="/market", tags=["past-prices"])


@router.get("/past-prices")
def get_past_prices(crop: str, market: str,
                    days: Optional[int] = Query(None, ge=7, le=3000, description="Window ending at the latest recorded price; omit for all"),
                    scope: str = Query("auto", pattern="^(auto|state|market)$"),
                    db: Session = Depends(get_db)):
    live = market_router._history_rows(db, crop, market, data_source="live")
    return past_prices.build_series(crop, market, live_rows=live, window=days, scope=scope)


@router.get("/past-prices/series")
def list_series():
    """Crop/market pairs with bundled recorded history."""
    return {"series": past_prices.available_series()}
