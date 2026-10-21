"""
Forecast availability report for one crop + market.

The Price Forecast page shows three things that answer DIFFERENT questions and
must never be conflated:

  1. recorded price history   -- statewide daily average and/or this market's own
                                 records (services/past_prices.py). Says nothing about
                                 whether a prediction is possible.
  2. live history             -- genuine market_prices(data_source="live") rows for this
                                 exact crop/market; the statistical trend forecast needs
                                 a minimum number of them.
  3. ML forecast              -- market-level model (few crops) and a separate statewide
                                 model; each can be unavailable for its own reason.

This module only classifies. It runs no model and invents nothing: the ML results are
passed in (as the router computed them) and history comes from past_prices.
No FastAPI / SQLAlchemy imports, so it is cheap to test.
"""
import datetime as dt
from typing import Optional

from app.services import past_prices

# Reason codes the UI maps to plain-language copy.
ML_REASONS = (
    "available", "unsupported_crop", "insufficient_history", "stale_history",
    "invalid_history", "artifacts_missing", "artifacts_invalid",
    "ml_dependencies_missing", "no_state_history", "no_state", "service_error",
)


def history_scope(crop: str, market: str, live_rows, scope: str, today: Optional[dt.date] = None) -> dict:
    """Recorded-history summary for exactly one scope ("state" or "market").

    build_series silently falls back to the other scope when the requested one is empty; that
    fallback is NOT reported here as if it were the requested scope.
    """
    r = past_prices.build_series(crop, market, live_rows=live_rows, scope=scope, today=today)
    if not r.get("available") or r.get("scope") != scope:
        return {"available": False}
    s = r["summary"]
    return {
        "available": True,
        "scope": scope,
        "label": f"{r['state']} average" if scope == "state" else market,
        "n_points": s["n_points"],
        "first_date": s["first_date"],
        "latest_date": s["latest"]["date"],
        "latest_price_per_kg": round(s["latest"]["modal"] / 100.0, 2),
        "age_days": s["latest"]["age_days"],
    }


def classify_ml(result: Optional[dict]) -> dict:
    """Reduce a router result ({available, reason, message, ...}) to a status the UI can show."""
    if not isinstance(result, dict):
        return {"status": "service_error", "message": "The forecast service did not return a result."}
    if result.get("available"):
        fc = result.get("forecast") or {}
        return {
            "status": "available",
            "is_historical_replay": bool(result.get("is_historical_replay")),
            "as_of_date": fc.get("as_of_date"),
            "history_age_days": fc.get("history_age_days"),
        }
    return {"status": result.get("reason") or "unavailable", "message": result.get("message")}


def build_availability(crop: str, market: str, *, live_rows, market_ml: Optional[dict], state_ml: Optional[dict],
                       min_live_points: int, today: Optional[dt.date] = None) -> dict:
    state = past_prices.state_of(market)
    live_rows = list(live_rows)
    return {
        "crop": crop, "market": market, "state": state,
        "recorded_history": {
            "state": history_scope(crop, market, live_rows, "state", today),
            "market": history_scope(crop, market, live_rows, "market", today),
        },
        "live_history": {"points": len(live_rows), "required_for_trend_forecast": min_live_points,
                         "sufficient": len(live_rows) >= min_live_points},
        "market_ml": classify_ml(market_ml),
        "state_ml": classify_ml(state_ml) if state else {"status": "no_state",
                                                           "message": "This market is not mapped to a state."},
    }
