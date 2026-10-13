import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.mock_data.crops import CROP_BY_NAME
from app.routers.market import _history_rows
from app.services.price_predictor import predict_next_days, backtest_accuracy

router = APIRouter(prefix="/forecast", tags=["forecast"])

MIN_REAL_POINTS_FOR_FORECAST = 4
UNAVAILABLE_MESSAGE = "Historical mandi data is currently unavailable."


@router.get("")
def get_forecast(crop: str, market: str, history_days: int = 30, predict_days: int = 7,
                  include_demo: bool = False, db: Session = Depends(get_db)):
    """
    HONESTY: by default the forecast is built ONLY from genuine
    accumulated live price snapshots (data_source="live"). A brand-new
    deployment (or one running purely on the seeded demo dataset) won't
    have enough real history yet -- in that case this returns
    `available: false` with an explanation instead of a chart built on
    invented data.

    Pass `include_demo=true` to explicitly run the same transparent
    trend/volatility model over the clearly-labeled synthetic demo series
    instead (useful for a hackathon walkthrough of the methodology itself)
    -- the response is tagged `is_demo: true` throughout so it can never
    be mistaken for a forecast based on real data.
    """
    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")

    rows = _history_rows(db, crop, market, data_source="live")
    is_demo = False
    if len(rows) < MIN_REAL_POINTS_FOR_FORECAST:
        if not include_demo:
            return {
                "crop": crop, "market": market, "available": False,
                "is_demo": False, "message": UNAVAILABLE_MESSAGE,
            }
        rows = _history_rows(db, crop, market, data_source="demo")
        is_demo = True
        if not rows:
            return {
                "crop": crop, "market": market, "available": False,
                "is_demo": True, "message": UNAVAILABLE_MESSAGE,
            }

    full_history = [{"date": r.date, "modal_price": round(r.modal_price / 100.0, 2),
                      "min_price": round(r.min_price / 100.0, 2), "max_price": round(r.max_price / 100.0, 2),
                      "arrivals_tonnes": r.arrivals_tonnes} for r in rows]

    forecast = predict_next_days(full_history, days=predict_days)
    accuracy = backtest_accuracy(full_history)  # None if not enough history -- never fabricated

    today = dt.date.today()
    forecast_dates = [(today + dt.timedelta(days=i)).isoformat() for i in range(1, predict_days + 1)]
    forecast_series = [
        {"date": d, "predicted_price": p}
        for d, p in zip(forecast_dates, forecast["daily_predictions"])
    ]

    return {
        "crop": crop,
        "market": market,
        "available": True,
        "is_demo": is_demo,
        "message": None,
        "demo_disclaimer": (
            "Simulated for demonstration only, over the synthetic demo price "
            "series -- not a forecast based on real mandi data. Requested "
            "explicitly via include_demo=true."
        ) if is_demo else None,
        "history": full_history[-history_days:],
        "forecast_series": forecast_series,
        "current_price": full_history[-1]["modal_price"],
        "predicted_price_low": forecast["predicted_price_low"],
        "predicted_price_high": forecast["predicted_price_high"],
        "predicted_price_mid": forecast["predicted_price_mid"],
        "confidence_pct": forecast["confidence_pct"],
        "trend_direction": forecast["trend_direction"],
        "volatility_pct": forecast.get("volatility_pct"),
        # Technical honesty block -- see README "Forecasting methodology".
        # Never call this "AI prediction" in the UI; it's a transparent
        # trend + volatility model, and accuracy metrics below are
        # genuinely backtested on this crop/market's own history, not
        # invented figures.
        "methodology": {
            "method": "Linear trend regression over the recent price window, with a volatility-based uncertainty band.",
            "model_type": "statistical (least-squares regression + historical volatility)",
            "is_machine_learning": False,
            "forecast_horizon_days": predict_days,
            "historical_data_period_days": len(full_history),
            "historical_records_used": len(full_history),
            "data_source": (
                "Demo/seeded mandi-style dataset (see Market Intelligence data-source note) -- not a live feed."
                if is_demo else
                "Genuine live snapshots captured from data.gov.in (Agmarknet) over time."
            ),
        },
        "backtested_accuracy": accuracy,  # None if history is too short to backtest -- shown honestly in UI
    }
