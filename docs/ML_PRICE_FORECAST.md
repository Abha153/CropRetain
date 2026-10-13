# ML price forecast (KrishiSight-derived) — integration notes

Adds `/forecast/ml`, `/forecast/ml/status`, `/forecast/ml/compare`. The existing `/forecast`
(statistical trend model) and `/market/*` are unchanged. The model is trained **offline** by
`backend/scripts/train_price_forecast.py`; the API only loads saved artifacts and never trains.

## Forecast definition
| | |
|---|---|
| Target field | `Modal_Price` / `modal_price` |
| Unit | INR per quintal (100 kg); responses also give INR/kg (= ÷100, same as `/market/compare`) |
| Horizon | 7 calendar days |
| As-of date | date of the latest observation in the series |
| Target date | as-of date + 7 days (returned explicitly as `target_date`) |
| Model output | `log(price[target] / price[as-of])`, converted back to INR/quintal |
| Interval | approx. 80% band from q10/q90 quantile models (coverage is measured on the test split and stored in metadata) |

## What was changed relative to the KrishiSight notebook, and why
Verified from the notebook source (cells 10–18):
1. `Commodity_Price_ZScore` is computed from the row's own `Modal_Price` → **direct target leakage**; it is a model input. Any reported R² (the saved output says 0.9162) is not trustworthy.
2. `State/District/Market/Commodity/Variety_TE`, `Market/Commodity/State_Price_Mean/Std`, `Comm_Month_Mean` are computed on the **whole dataset including the test period** (comment says "leave-one-out" but plain `groupby.mean` is used, on all rows).
3. Missing lag values are filled with the **global median** of the full frame; outlier removal (±3σ) uses full-data statistics.
4. Data are sampled by *first N rows per file* (`SAMPLE_ROWS_PER_FILE`), not chronologically; the 80/20 time split uses a quantile of dates but no validation set, and Optuna (if enabled) tunes **on the test set**.
5. `Price_Lag_7` = 7th previous *record*, not 7 days ago; the target is same-day price, not a future price, so the notebook is not a forecaster as written.
6. `StackingEnsemble`/encoders/`te_maps` were never saved; only three `.pkl` models on Google Drive (not supplied, not verified).

New pipeline: features use only observations ≤ as-of date (`app/services/price_forecast/features.py`, shared by training and inference), no target encoding or global aggregates, chronological train/val/test with a 7-day purge gap, naive baselines (persistence, 7-day mean), `HistGradientBoostingRegressor` (NaN-native, no LightGBM/XGBoost/SHAP/Gradio/Optuna dependency).

## Artifacts (`backend/models/price_forecast/`, override with `PRICE_FORECAST_ARTIFACT_DIR`)
`bundle.joblib` (point, q10, q90 models) · `metadata.json` (feature list, commodity vocabulary, crop/market mapping actually matched, split dates, metrics, library versions) · `recent_history.csv` (last 60 days per CropWise market from the training data; used only for `include_snapshot=true` demo replay).
No encoders/scalers are needed by design (log-ratio target; only the commodity id vocabulary is stored). Commit the artifacts if the deployed server should serve forecasts.

## Safety behaviour
`available:false` + `reason` (HTTP 200, like the existing `/forecast`) for: `artifacts_missing`, `artifacts_invalid`, `unsupported_crop`, `invalid_history`, `insufficient_history` (< 6 observed days in last 28), `stale_history` (latest price > 3 days old), `ml_dependencies_missing`. Unknown crop → 404. A market absent from the training data returns a warning (the model only uses that market's own recent prices). Forecast is clipped to ×0.5…×2 of the last price. History comes only from genuine `data_source="live"` rows, or — explicitly via `include_snapshot=true` — the training-data tail, flagged `is_historical_replay: true`.

## Commands (Windows PowerShell)
```powershell
git apply --check cropwise-ml-forecast.patch; git apply cropwise-ml-forecast.patch
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt; pip install -r requirements-ml.txt
python -m pytest tests/test_price_forecast.py tests/test_price_forecast_router.py -q
python -m scripts.train_price_forecast --since 2023-01-01          # downloads via kagglehub, trains, prints MAE/RMSE
uvicorn app.main:app --reload
Invoke-RestMethod "http://127.0.0.1:8000/forecast/ml/status"
Invoke-RestMethod "http://127.0.0.1:8000/forecast/ml?crop=Tomato&market=Nashik&include_snapshot=true"
```
If the training script reports `NO MATCH for CropWise crop ...`, edit `CROP_ALIASES` (and `MARKET_ALIASES`) at the top of the script using the suggested dataset names.
