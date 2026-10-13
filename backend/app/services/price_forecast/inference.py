"""
Inference for the saved price-forecast model. Loads artifacts written by
scripts/train_price_forecast.py; NEVER trains. Raises ForecastError (with a
machine-readable `code`) instead of guessing whenever it cannot forecast
safely.

Artifact directory (override with env PRICE_FORECAST_ARTIFACT_DIR):
    <backend>/models/price_forecast/
        bundle.joblib       {"point": model, "q10": model, "q90": model}
        metadata.json       feature list, vocabularies, metrics, split dates, versions
        recent_history.csv  columns crop,market,date,modal_price (demo replay only)
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from app.services.price_forecast import features as F

DEFAULT_ARTIFACT_DIR = Path(__file__).resolve().parents[3] / "models" / "price_forecast"


class ForecastError(Exception):
    """code: artifacts_missing | artifacts_invalid | unsupported_crop |
    invalid_history | insufficient_history | stale_history"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Artifacts:
    models: dict
    meta: dict
    directory: Path
    _snapshot: Optional[pd.DataFrame] = field(default=None, repr=False)


_CACHE: dict = {}


def artifact_dir() -> Path:
    return Path(os.environ.get("PRICE_FORECAST_ARTIFACT_DIR") or DEFAULT_ARTIFACT_DIR)


def load_artifacts(directory: Optional[Path] = None) -> Artifacts:
    """Load + validate artifacts (cached per directory/mtime). Not called at
    app startup; first forecast request pays a one-off load."""
    d = Path(directory) if directory else artifact_dir()
    meta_path, bundle_path = d / "metadata.json", d / "bundle.joblib"
    if not meta_path.is_file() or not bundle_path.is_file():
        raise ForecastError(
            "artifacts_missing",
            "Price-forecast model artifacts not found. Run scripts/train_price_forecast.py "
            "(see README section 'ML price forecast').",
        )
    key = (str(d.resolve()), meta_path.stat().st_mtime_ns, bundle_path.stat().st_mtime_ns)
    if key in _CACHE:
        return _CACHE[key]
    try:
        import joblib
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        models = joblib.load(bundle_path)
    except Exception as e:  # corrupt/incompatible file -- report, don't crash the API
        raise ForecastError("artifacts_invalid", f"Could not load model artifacts: {e}")
    if (meta.get("schema_version") != F.SCHEMA_VERSION
            or meta.get("feature_cols") != F.FEATURE_COLS
            or meta.get("horizon_days") != F.HORIZON_DAYS
            or not {"point", "q10", "q90"} <= set(models)):
        raise ForecastError(
            "artifacts_invalid",
            "Artifacts do not match the current feature definition; retrain with "
            "scripts/train_price_forecast.py.",
        )
    _CACHE.clear()
    arts = Artifacts(models=models, meta=meta, directory=d)
    _CACHE[key] = arts
    return arts


def load_snapshot_history(arts: Artifacts, crop: str, market: str) -> list:
    """Tail of the TRAINING dataset for a CropRetain crop/market (demo replay only)."""
    p = arts.directory / "recent_history.csv"
    if not p.is_file():
        return []
    if arts._snapshot is None:
        arts._snapshot = pd.read_csv(p)
    df = arts._snapshot
    sub = df[(df["crop"] == crop) & (df["market"] == market)]
    return [{"date": r.date, "modal_price": float(r.modal_price)} for r in sub.itertuples()]


def predict(history: list, crop: str, market: Optional[str] = None, *,
            today: Optional[dt.date] = None, allow_stale: bool = False,
            artifacts: Optional[Artifacts] = None) -> dict:
    """
    history: [{"date": "YYYY-MM-DD" | "DD/MM/YYYY", "modal_price": INR/quintal}, ...]
    Returns the forecast dict, or raises ForecastError.
    allow_stale=True is only for explicit historical replay (response must say so).
    """
    arts = artifacts or load_artifacts()
    meta = arts.meta
    cidx = meta["commodity_idx"].get(crop)
    if cidx is None:
        raise ForecastError("unsupported_crop", f"No trained model coverage for crop '{crop}'.")

    if not history:
        raise ForecastError("insufficient_history", "No price history available.")
    s = F.daily_series([h.get("date") for h in history], [h.get("modal_price") for h in history])
    if s.empty:
        raise ForecastError("invalid_history", "No valid (dated, positive) price rows in history.")
    dropped = len(history) - int(len(s))  # approximate: includes same-day duplicates merged by median

    today = today or dt.date.today()
    as_of = s.index[-1].date()
    if as_of > today:
        raise ForecastError("invalid_history", f"Latest price is dated in the future ({as_of}).")
    age_days = (today - as_of).days
    if age_days > F.MAX_STALE_DAYS and not allow_stale:
        raise ForecastError(
            "stale_history",
            f"Latest price is {age_days} days old (limit {F.MAX_STALE_DAYS}); not forecasting from stale data.",
        )

    feats = F.compute_features(s, cidx)
    last = feats.iloc[-1]
    if not bool(last["eligible"]):
        raise ForecastError(
            "insufficient_history",
            f"Need >= {F.MIN_OBS_28} observed days in the last 28 days; found {int(last['n_obs_28'])}.",
        )

    X = pd.DataFrame([last[F.FEATURE_COLS].to_dict()]).astype(float)
    X["commodity_idx"] = X["commodity_idx"].astype(int)
    clip = lambda v: float(np.clip(v, -F.MAX_ABS_LOG_RATIO, F.MAX_ABS_LOG_RATIO))
    r_pt = clip(arts.models["point"].predict(X)[0])
    r_lo = clip(arts.models["q10"].predict(X)[0])
    r_hi = clip(arts.models["q90"].predict(X)[0])
    r_lo, r_hi = min(r_lo, r_pt), max(r_hi, r_pt)   # quantile crossing guard
    price = float(last["price"])
    pred, lo, hi = (price * math.exp(r) for r in (r_pt, r_lo, r_hi))
    if not all(math.isfinite(v) and v > 0 for v in (pred, lo, hi)):
        raise ForecastError("invalid_history", "Model produced a non-finite forecast; refusing to return it.")

    warnings = []
    if market and market not in meta.get("known_markets", []):
        warnings.append("market_not_in_training_data: forecast uses only this market's own recent prices.")
    if not meta.get("metrics", {}).get("test", {}).get("model_beats_persistence", False):
        warnings.append("model_did_not_beat_persistence_baseline_on_test_split")
    if age_days > F.MAX_STALE_DAYS:
        warnings.append(f"historical_replay: latest price is {age_days} days old")

    target_date = as_of + dt.timedelta(days=F.HORIZON_DAYS)
    r2 = lambda v: round(v, 2)
    return {
        "crop": crop, "market": market,
        "target_field": F.TARGET_FIELD, "unit": F.PRICE_UNIT,
        "horizon_days": F.HORIZON_DAYS,
        "as_of_date": as_of.isoformat(), "target_date": target_date.isoformat(),
        "last_observed_price": r2(price),
        "predicted_price": r2(pred), "predicted_price_low": r2(lo), "predicted_price_high": r2(hi),
        "interval": "approx. 80% (q10-q90 quantile models)",
        "predicted_price_per_kg": r2(pred / 100.0),
        "baseline_persistence_price": r2(price),
        "observations_used": int(len(s)), "obs_last_28_days": int(last["n_obs_28"]),
        "history_age_days": age_days,
        "dropped_or_merged_rows": max(dropped, 0),
        "warnings": warnings,
    }
