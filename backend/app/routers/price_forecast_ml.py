"""
ML price forecast endpoints -- separate from the existing /forecast route
(statistical trend model) and from /market/*. Nothing here trains a model;
it loads artifacts produced by scripts/train_price_forecast.py.

  GET /forecast/ml/status    artifact + metric summary
  GET /forecast/ml/analysis  full held-out-test analysis (baselines, per-crop/state error, drivers)
  GET /forecast/ml           7-day-ahead forecast for one crop/market
  GET /forecast/ml/state     7-day-ahead STATEWIDE average forecast (separate model, models/price_forecast_state)
  GET /forecast/ml/compare   existing /market/compare result + forecast per market

HONESTY: history comes ONLY from genuine live snapshots in market_prices
(data_source="live"), exactly like the existing /forecast. Too little or stale
history -> available:false with a reason, never a guess. `include_snapshot=true`
explicitly replays the tail of the TRAINING dataset (flagged is_historical_replay).
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.mock_data.crops import CROP_BY_NAME
from app.routers import market as market_router
from app.services.transport_optimizer import net_profit_breakdown

router = APIRouter(prefix="/forecast/ml", tags=["forecast-ml"])


def _service():
    """Lazy import so the API still boots if the optional ML deps are absent."""
    try:
        from app.services.price_forecast import inference
        return inference
    except ImportError:
        return None


def _unavailable(crop, market, code, message):
    return {"crop": crop, "market": market, "available": False, "reason": code, "message": message}


def _live_history(db, crop, market):
    rows = market_router._history_rows(db, crop, market, data_source="live")
    # market_prices.modal_price is INR/quintal (market.py divides by 100 for INR/kg)
    return [{"date": r.date, "modal_price": r.modal_price} for r in rows]


def _forecast_one(inf, db, crop, market, include_snapshot=False):
    try:
        arts = inf.load_artifacts()
        history, source, replay = _live_history(db, crop, market), "live_db", False
        try:
            fc = inf.predict(history, crop, market, artifacts=arts)
        except inf.ForecastError as e:
            if e.code in ("insufficient_history", "stale_history"):
                snap = inf.load_snapshot_history(arts, crop, market)
                if not snap:
                    raise
                source, replay = "training_snapshot", True
                fc = inf.predict(snap, crop, market, artifacts=arts, allow_stale=True)
            else:
                raise
    except inf.ForecastError as e:
        return _unavailable(crop, market, e.code, e.message)
    t = arts.meta["metrics"]["test"]
    return {
        "crop": crop, "market": market, "available": True,
        "history_source": source, "is_historical_replay": replay,
        "forecast": fc,
        "model": {
            "type": f"{arts.meta.get('model_label') or 'gradient boosting'}; is_machine_learning=true",
            "family": arts.meta.get("model_family"),
            "beats_persistence_on_test": bool(t.get("model_beats_persistence")),
            "dataset": arts.meta["dataset"], "trained_utc": arts.meta["created_utc"],
            "test_mae_inr_per_quintal": round(t["model"]["mae"], 2),
            "test_rmse_inr_per_quintal": round(t["model"]["rmse"], 2),
            "persistence_baseline_test_mae": round(t["baseline_persistence"]["mae"], 2),
            "evaluated_on": "chronological held-out test split, all markets (not this market alone)",
        },
    }


STATE_MAX_AGE_DAYS = 14   # state data comes from periodic report exports, so allow a little more age than live sync


def _state_dir():
    import os
    from pathlib import Path
    return Path(os.environ.get("PRICE_FORECAST_STATE_ARTIFACT_DIR") or
                Path(__file__).resolve().parents[2] / "models" / "price_forecast_state")


@router.get("/state")
def ml_state_forecast(crop: str, state: str):
    """Statewide average-price forecast. History is the bundled statewide daily series (past_prices
    service); it is only as fresh as the last export, and the response says exactly how old it is."""
    from app.services import past_prices
    inf = _service()
    if inf is None:
        return _unavailable(crop, state, "ml_dependencies_missing", "pip install -r requirements-ml.txt")
    series = past_prices._state_series().get((crop, state))
    if not series:
        return _unavailable(crop, state, "no_state_history", f"No statewide price history for {crop} in {state}.")
    try:
        arts = inf.load_artifacts(_state_dir())
        history = [{"date": d, "modal_price": r["modal"]} for d, r in sorted(series.items())]
        fc = inf.predict(history, crop, f"{state} (state average)", artifacts=arts, allow_stale=True)
    except inf.ForecastError as e:
        return _unavailable(crop, state, e.code, e.message)
    age = fc["history_age_days"]
    if age > STATE_MAX_AGE_DAYS:
        return _unavailable(crop, state, "stale_history",
                            f"Statewide data ends {fc['as_of_date']} ({age} days ago); not forecasting from data that old. "
                            "Refresh app/data/state_prices.csv.")
    fc["warnings"] = [w for w in fc["warnings"] if not w.startswith(("historical_replay", "market_not_in_training_data"))]
    t = arts.meta["metrics"]["test"]
    pc = arts.meta["metrics"].get("per_crop_test", {}).get(crop)
    return {
        "crop": crop, "state": state, "available": True, "forecast": fc, "data_age_days": age,
        "model": {
            "family": arts.meta.get("model_family"), "trained_utc": arts.meta["created_utc"],
            "dataset": arts.meta["dataset"], "data_date_range": arts.meta["data_date_range"],
            "test_mae_inr_per_quintal": round(t["model"]["mae"], 2),
            "persistence_baseline_test_mae": round(t["baseline_persistence"]["mae"], 2),
            "ma7_baseline_test_mae": round(t["baseline_ma7"]["mae"], 2),
            "beats_persistence_on_test": bool(t.get("model_beats_persistence")),
            "interval_coverage_test": t.get("interval_coverage_80"),
            "this_crop_test": ({"rows": pc["rows"], "model_mae": round(pc["model_mae"], 2),
                                "persistence_mae": round(pc["persistence_mae"], 2)} if pc else None),
            "evaluated_on": "chronological held-out test split (last ~15% of dates), statewide series",
        },
    }


@router.get("/status")
def ml_status():
    inf = _service()
    if inf is None:
        return {"available": False, "reason": "ml_dependencies_missing",
                "message": "pip install -r requirements-ml.txt"}
    try:
        m = inf.load_artifacts().meta
    except inf.ForecastError as e:
        return {"available": False, "reason": e.code, "message": e.message}
    return {"available": True, "horizon_days": m["horizon_days"], "unit": m["unit"],
            "model_family": m.get("model_family"), "model_label": m.get("model_label"),
            "crops": sorted(m["commodity_idx"]), "excluded_crops": m.get("excluded_crops", {}),
            "known_markets": m["known_markets"],
            "dataset": m["dataset"], "data_date_range": m["data_date_range"],
            "split": m["split"], "metrics": m["metrics"], "interval": m.get("interval"),
            "selection": m.get("selection"), "created_utc": m["created_utc"]}


@router.get("/analysis")
def ml_analysis():
    """Everything the frontend 'model analysis' panel needs, precomputed at training time on the
    held-out TEST split (dates the model never saw). Nothing is recomputed per request."""
    inf = _service()
    if inf is None:
        return {"available": False, "reason": "ml_dependencies_missing",
                "message": "pip install -r requirements-ml.txt"}
    try:
        arts = inf.load_artifacts()
    except inf.ForecastError as e:
        return {"available": False, "reason": e.code, "message": e.message}
    path = arts.directory / "analysis.json"
    if not path.is_file():
        return {"available": False, "reason": "analysis_missing",
                "message": "analysis.json not found; retrain with scripts/train_price_forecast.py"}
    try:
        return {"available": True, **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError) as e:
        return {"available": False, "reason": "analysis_invalid", "message": f"Could not read analysis.json: {e}"}


@router.get("")
def ml_forecast(crop: str, market: str, include_snapshot: bool = False, db: Session = Depends(get_db)):
    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")
    inf = _service()
    if inf is None:
        return _unavailable(crop, market, "ml_dependencies_missing", "pip install -r requirements-ml.txt")
    return _forecast_one(inf, db, crop, market, include_snapshot)


@router.get("/compare")
def ml_compare(crop: str = Query(...), quantity_kg: float = Query(...), location: str = Query(...),
               top_n: int = Query(6, ge=1, le=30), include_snapshot: bool = False,
               db: Session = Depends(get_db)):
    """Reuses the existing market-comparison logic unchanged, then adds a forecast
    (and forecast-based net return via the same net_profit_breakdown) per market."""
    result = market_router._compare_markets_core(crop, quantity_kg, location, top_n, db)
    inf = _service()
    options = []
    for o in result.get("options", []):
        fc = (_forecast_one(inf, db, crop, o["market"], include_snapshot) if inf else
              _unavailable(crop, o["market"], "ml_dependencies_missing", "pip install -r requirements-ml.txt"))
        entry = {**o, "ml_forecast": fc}
        if fc["available"]:
            per_kg = fc["forecast"]["predicted_price_per_kg"]
            entry["forecast_net_profit"] = net_profit_breakdown(quantity_kg, per_kg, o["distance_km"])["net_profit"]
        options.append(entry)
    ranked = sorted((o for o in options if "forecast_net_profit" in o),
                    key=lambda o: o["forecast_net_profit"], reverse=True)
    return {
        **result, "options": options,
        "forecast_horizon_days": 7,
        "forecast_ranking": [{"market": o["market"], "forecast_net_profit": o["forecast_net_profit"]} for o in ranked],
        "forecast_recommended_market": ranked[0]["market"] if ranked else None,
        "forecast_coverage": f"{len(ranked)} of {len(options)} markets",
        "note": "Existing fields (recommended_market, net_profit, ...) are unchanged and based on today's price; "
                "forecast_* fields are separate and only cover markets with enough live history.",
    }
