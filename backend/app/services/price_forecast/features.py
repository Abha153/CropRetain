"""
Single source of truth for the forecast definition and feature generation.
Used unchanged by training and by inference -- do not duplicate this logic.

FORECAST DEFINITION
  target field   : Modal_Price (modal_price), INR per quintal (100 kg)
  horizon        : HORIZON_DAYS calendar days after the as-of date
  as-of date     : date of the latest observation in the series
  target date    : as-of date + HORIZON_DAYS
  model output   : log(price[target date] / price[as-of date]); converted
                   back to INR/quintal by the caller.

NO-LEAKAGE RULES (every feature at as-of date t uses observations dated <= t)
  * all rolling windows end at t (inclusive); lags are last-known price at t-k
  * no target encoding, no global/market/commodity aggregates, no z-scores
    computed from the full dataset -- the model sees only the series' own
    past plus a commodity id and the target month/day-of-year
  * the target is only attached in add_targets() (training only)

This module deliberately imports nothing from `app.*`, so the training script
can use it without a DATABASE_URL.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

SCHEMA_VERSION = 1
HORIZON_DAYS = 7
TARGET_FIELD = "modal_price"
PRICE_UNIT = "INR per quintal (100 kg)"

MIN_OBS_28 = 6            # need >= this many distinct observed days in the trailing 28 days
MAX_STALE_DAYS = 3        # live inference refuses history whose latest point is older than this
MAX_ABS_LOG_RATIO = math.log(2.0)   # prediction guard: never forecast beyond x0.5 / x2.0

FEATURE_COLS = [
    "commodity_idx",   # categorical id from the TRAINING vocabulary (metadata.json)
    "log_price",       # log of the latest observed modal price (as-of date)
    "ret_7",           # log(price_t / last-known price at t-7d)
    "ret_14",          # log(price_t / last-known price at t-14d)
    "dev_ma7",         # log(price_t / mean of observed prices in [t-6, t])
    "dev_ma28",        # log(price_t / mean of observed prices in [t-27, t])
    "cv_28",           # std/mean of observed prices in [t-27, t]
    "n_obs_7",         # observed days in [t-6, t]
    "n_obs_28",        # observed days in [t-27, t]
    "target_month",    # calendar month of the target date
    "target_doy",      # day of year of the target date
]
CATEGORICAL_COLS = ["commodity_idx"]

_DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%y", "%d-%m-%y"]


def parse_dates(values) -> pd.Series:
    """Tolerant date parser (same multi-format approach as the KrishiSight
    notebook, plus ISO dates). Unparseable values become NaT, never guessed."""
    s = pd.Series(values)
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce").dt.tz_localize(None).dt.normalize()
    raw = s.astype(str).str.strip().str.slice(0, 10)
    parsed = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    for fmt in _DATE_FORMATS:
        todo = parsed.isna()
        if not todo.any():
            break
        parsed[todo] = pd.to_datetime(raw[todo], format=fmt, errors="coerce")
    return parsed.dt.normalize()


def daily_series(dates, prices) -> pd.Series:
    """One price per calendar day (median if several rows share a day);
    non-finite and non-positive prices and unparseable dates are dropped."""
    d = parse_dates(dates)
    p = pd.to_numeric(pd.Series(prices), errors="coerce")
    s = pd.Series(p.to_numpy(dtype=float), index=pd.DatetimeIndex(d.to_numpy()))
    s = s[s.index.notna() & np.isfinite(s.to_numpy()) & (s.to_numpy() > 0)]
    if s.empty:
        return s
    return s.groupby(level=0).median().sort_index()


def compute_features(s: pd.Series, commodity_idx: int) -> pd.DataFrame:
    """Features for every observed date of one (market, commodity) series.
    `s` is the output of daily_series(). Row t uses only observations <= t."""
    cols = FEATURE_COLS + ["price", "eligible"]
    if s.empty:
        return pd.DataFrame(columns=cols)
    full = s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))
    ff = full.ffill()                                   # last-known price as of each day
    ma7 = full.rolling(7, min_periods=1).mean()
    ma28 = full.rolling(28, min_periods=1).mean()
    sd28 = full.rolling(28, min_periods=2).std()
    n7 = full.rolling(7, min_periods=1).count()
    n28 = full.rolling(28, min_periods=1).count()
    lag7, lag14 = ff.shift(7), ff.shift(14)

    idx = s.index
    f = pd.DataFrame(index=idx)
    f["commodity_idx"] = int(commodity_idx)
    f["log_price"] = np.log(s)
    f["ret_7"] = np.log(s / lag7.reindex(idx))
    f["ret_14"] = np.log(s / lag14.reindex(idx))
    f["dev_ma7"] = np.log(s / ma7.reindex(idx))
    f["dev_ma28"] = np.log(s / ma28.reindex(idx))
    f["cv_28"] = (sd28 / ma28).reindex(idx)
    f["n_obs_7"] = n7.reindex(idx)
    f["n_obs_28"] = n28.reindex(idx)
    target_date = idx + pd.Timedelta(days=HORIZON_DAYS)
    f["target_month"] = target_date.month
    f["target_doy"] = target_date.dayofyear
    f["price"] = s
    f["eligible"] = f["n_obs_28"] >= MIN_OBS_28
    return f[cols]


def add_targets(f: pd.DataFrame, s: pd.Series) -> pd.DataFrame:
    """TRAINING ONLY: attach the realised price exactly HORIZON_DAYS later.
    Rows with no observation on that exact day get y = NaN and are dropped."""
    out = f.copy()
    out["target_date"] = out.index + pd.Timedelta(days=HORIZON_DAYS)
    out["future_price"] = s.reindex(out["target_date"]).to_numpy()
    out["y"] = np.log(out["future_price"] / out["price"])
    return out
