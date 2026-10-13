from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import schemas
from app.mock_data.crops import CROP_BY_NAME
from app.routers.market import compare_markets, _history_rows
from app.services.price_predictor import predict_next_days
from app.services.recommendation_engine import build_recommendation

router = APIRouter(prefix="/advisor", tags=["advisor"])


@router.post("/recommend")
def recommend(payload: schemas.AdvisorRequest, db: Session = Depends(get_db)):
    if payload.crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")

    comparison = compare_markets(
        crop=payload.crop, quantity_kg=payload.quantity_kg, location=payload.location, db=db,
    )
    if comparison.get("insufficient_data") or not comparison.get("recommended_market"):
        raise HTTPException(
            status_code=404,
            detail="Insufficient data to make a reliable recommendation.",
        )
    best_market_name = comparison["recommended_market"]

    # Honesty: prefer genuine accumulated live history; only use the
    # clearly-labeled demo series as an explicit, tagged fallback so this
    # recommendation is never silently built on invented "historical" data
    # without saying so.
    rows = _history_rows(db, payload.crop, best_market_name, data_source="live")
    history_is_demo = False
    if not rows:
        rows = _history_rows(db, payload.crop, best_market_name, data_source="demo")
        history_is_demo = True
    history = [{"date": r.date, "modal_price": round(r.modal_price / 100.0, 2),
                "arrivals_tonnes": r.arrivals_tonnes} for r in rows]
    if not history:
        raise HTTPException(status_code=404, detail="No historical data available for this market")

    forecast = predict_next_days(history, days=7)

    # Live rows (data_source="live") always have arrivals_tonnes=None --
    # that resource does not publish arrival volume at all. A plain sum()
    # over rows that include None raises TypeError and 500s this endpoint
    # the moment a market has genuine accumulated live history. Average
    # only rows with a known figure; a 0 baseline is already treated as
    # "insufficient signal" downstream rather than a fabricated trend.
    def _avg_known_arrivals(rows):
        known = [h["arrivals_tonnes"] for h in rows if h["arrivals_tonnes"] is not None]
        return sum(known) / len(known) if known else 0.0

    arrivals_recent_avg = _avg_known_arrivals(history[-7:])
    arrivals_baseline_avg = _avg_known_arrivals(history)

    crop_info = CROP_BY_NAME[payload.crop]
    recommendation = build_recommendation(
        crop_info=crop_info, quantity_kg=payload.quantity_kg, quality_grade=payload.quality_grade,
        location=payload.location, market_options=comparison["options"], forecast=forecast,
        arrivals_recent_avg=arrivals_recent_avg, arrivals_baseline_avg=arrivals_baseline_avg,
    )

    return {
        "crop": payload.crop,
        "quantity_kg": payload.quantity_kg,
        "quality_grade": payload.quality_grade,
        "location": payload.location,
        "forecast": forecast,
        "forecast_is_demo": history_is_demo,
        "forecast_demo_disclaimer": (
            "This crop/market doesn't have enough real accumulated mandi "
            "history yet, so the short-term trend below uses the clearly "
            "labeled demo dataset instead -- not real government data."
        ) if history_is_demo else None,
        "recommendation": recommendation,
    }
