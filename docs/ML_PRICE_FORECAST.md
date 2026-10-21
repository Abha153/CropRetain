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
`bundle.joblib` (point, q10, q90 models) · `metadata.json` (feature list, commodity vocabulary, crop/market mapping actually matched, split dates, metrics, band calibration, excluded crops, library versions) · `analysis.json` (everything the frontend analysis panel shows, precomputed on the held-out test split; served by `GET /forecast/ml/analysis`) · `recent_history.csv` (last 60 days per CropWise market from the training data; used only for `include_snapshot=true` demo replay).
No encoders/scalers are needed by design (log-ratio target; only the commodity id vocabulary is stored). Commit the artifacts if the deployed server should serve forecasts.

## Safety behaviour
`available:false` + `reason` (HTTP 200, like the existing `/forecast`) for: `artifacts_missing`, `artifacts_invalid`, `unsupported_crop`, `invalid_history`, `insufficient_history` (< 6 observed days in last 28), `stale_history` (latest price > 3 days old), `ml_dependencies_missing`. Unknown crop → 404. A market absent from the training data returns a warning (the model only uses that market's own recent prices). Forecast is clipped to ×0.5…×2 of the last price. History comes only from genuine `data_source="live"` rows, or — explicitly via `include_snapshot=true` — the training-data tail, flagged `is_historical_replay: true`.

## Model choice, and what the numbers say (trained on the supplied 2023-06 → 2025-06 CSV)
`train_price_forecast.py` trains **HistGradientBoosting** and **CatBoost** on identical features and splits and keeps the winner by **validation** MAE only (a challenger must beat the incumbent by 1%). The test split is reported, never used to choose.

| INR/quintal | validation | test (unseen) |
|---|---|---|
| Model (HistGradientBoosting) | 274 | 192 |
| "Price stays the same" | 287 | 182 |
| 7-day average | 302 | 193 |
| CatBoost (not chosen) | 280 | 195 |

Read honestly: the model beat "price stays the same" on validation (about 5% lower error) but **lost to it on test (about 5% higher typical error)**, while doing better on large misses (RMSE 343 vs 363). The weekly view in the analysis panel shows why: through Feb–Apr 2025 it kept forecasting rises while prices fell. "Day of year" carries about half of its weight, and with about two years of history each season has been seen once, so a seasonal habit from one year misleads in the next. The analysis panel states this plainly, and every forecast carries the `model_did_not_beat_persistence_baseline_on_test_split` warning while it holds. More history (a longer export) is the real fix; retrain with it and the verdict updates itself.

* **Interval**: the raw q10/q90 band covered only 73.5% of unseen prices. It is now widened by a split-conformal pad fitted on validation only, giving **79.5%** coverage on the unseen test split (target 80%).
* **Crops covered: Onion and Potato.** Tomato and Wheat have too few rows in the validation/test periods for their accuracy to be measured, so the trainer excludes them (`excluded_crops` in `metadata.json`) and the API answers `unsupported_crop` with the reason, rather than forecasting a crop it cannot vouch for. Rice is in the CSV but is milled rice, not the app's "Paddy (Rice)", so it is not mapped.

## Training on a messy Agmarknet-style CSV
```powershell
cd backend
pip install -r requirements-train.txt          # adds CatBoost; serving needs only requirements-ml.txt
python -m scripts.prepare_price_data --input C:\path\messy.csv --out-dir data\clean_prices
python -m scripts.train_price_forecast --dataset-dir data\clean_prices --since 2023-01-01
```
`prepare_price_data` never invents a price. A blank date is filled only when the rows just before and after share one date; a blank state / market / commodity only when the data maps its key to exactly one value; rows with no modal price, max < min, or a price outside 0.15×–8× of the commodity median (unit errors) are dropped. The accuracy of each recovery rule is measured by hiding known values and re-deriving them, and is written to `prep_report.json` and shown in the analysis panel (about 99.99% for dates, 100% for states and commodities). `--models hgb` skips CatBoost.

## Frontend analysis panel
`GET /forecast/ml/analysis` feeds the "Model analysis" section of the Price Forecast page: verdict vs "price stays the same", typical vs large misses, share of forecasts within 5/10/20%, week-by-week predicted vs real change, predicted-vs-real scatter, input importance (permutation, on validation data), per-crop and per-state tables, and the data/model-selection details. Every chart has a table view.

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

## Past prices section

`GET /market/past-prices?crop=&market=&days=` feeds the "Past prices" block on the Price Forecast page
(`frontend/src/components/PastPrices.jsx`): a plain-language summary, four stat tiles, a line chart and a table view.

- Data: bundled recorded history in `backend/app/data/past_prices.csv` plus any `market_prices` rows with
  `data_source="live"`. Demo rows are never used. Nothing is interpolated; a stretch of 30+ days with no record is
  returned in `gaps` and drawn as a shaded "No records" band.
- The trend sentence uses only the newest unbroken run of records, so a gap (e.g. Jun 2025 -> Oct 2026) is never
  read as a price move. With fewer than 4 records in that run it says there is not enough to call a trend.
- Rebuild the file from a cleaned history plus a one-day export:
  `python -m scripts.build_past_prices --history clean_prices.csv --snapshot <agmarknet.csv> --snapshot-label snapshot_2026-10-18`.
  The export spells the state "Chattisgarh"; both spellings are accepted. Chhattisgarh rows usually name small APMCs
  (e.g. "Kharora APMC"); when the district is an app market they are averaged into it and the real mandi names are kept
  in the row's `note`, which the page shows ("district mandis: ...").
- Fresh data: the page only shows newer prices once the live sync stores them (`POST /market/sync`).

### State averages and the all-India comparison

- `app/data/state_prices.csv`: statewide daily average modal price (weighted by arrivals) for Chhattisgarh and
  Maharashtra, from an Agmarknet "All Type of Report (All Grades)" export. The Past prices block shows this by default
  because it is current and near-daily; a toggle switches to a single market's own history (`scope=market`).
  A state average is one price for the whole state, not any one mandi's price.
- `app/data/national_prices.csv`: all-India wholesale price on 16 Oct 2026 and on the same date 1 week, 1 month and
  1-3 years earlier (the "Wholesale-Mandi-Prices-of-*" files). Shown as a comparison strip, not a chart.
- Build both with `--state-report <csv>` and `--national <csv> ...` on `scripts/build_past_prices.py`.

### State-level forecast model

A second model, `backend/models/price_forecast_state/`, is trained on `app/data/state_prices.csv` by
`python -m scripts.train_state_forecast` (same features, chronological split, validation-only model selection and
conformal band calibration as the per-market model; it calls the same `train_from_frame`). It forecasts the statewide
average price 7 days ahead for Onion, Potato and Tomato in Chhattisgarh and Maharashtra
(`GET /forecast/ml/state?crop=&state=`), and is shown on the Past prices block in the "state average" view.

Held-out test (last ~15% of dates, May-Oct 2026, 966 rows; INR/quintal): HistGradientBoosting MAE 266 vs 284 for "price
stays the same" (-6%; Onion -9%, Potato -9%, Tomato -3%) and 269 for a 7-day average, so it is roughly level with the
7-day average. The 80% band covered 75% on test (80% on validation, where it was calibrated). CatBoost was also
trained (test MAE 263) but did not beat HistGradientBoosting on validation by the 1% margin, so it was not chosen.

Limits: the series is statewide, not any one mandi; it is only as fresh as the last export of `state_prices.csv` (the
endpoint refuses data older than 14 days); and the test period contains an unusually large Onion price rise, which is
hard for any model.

## Verifying that ML is actually working (any environment)

Run these against your backend (replace `$API` with e.g. `http://localhost:8000` or your deployed URL):

```bash
curl -s $API/forecast/ml/status
```
* `"available": true` and a `crops` list -> the ML libraries and model files are loaded. Expect `["Onion","Potato"]`.
* `"reason": "ml_dependencies_missing"` -> the server was installed without numpy/pandas/scikit-learn/joblib. These are now in `backend/requirements.txt`; redeploy with a fresh install.
* `"reason": "artifacts_missing"` -> `backend/models/price_forecast/` was not deployed with the app.

```bash
curl -s "$API/forecast/ml?crop=Potato&market=Bilaspur"
curl -s "$API/forecast/ml?crop=Soybean&market=Raipur"
```
* Potato/Bilaspur returns a forecast. If there is no recent live price history it is a **historical replay** (`is_historical_replay: true`, `history_source: "training_snapshot"`) of data that ends in June 2025, flagged with a staleness warning. It is a demonstration of the model, **not a prediction for next week**.
* Soybean returns `unsupported_crop`: the trained model covers only Onion and Potato (Tomato and Wheat were excluded because they lacked enough held-out rows to measure accuracy; the other crops were never trained).
* A *live* forecast needs fresh rows in `market_prices` with `data_source="live"` for that crop and market.

The farmer dashboard shows the same facts: a forecast card with a model line ("Model: ... trained on data up to ...") that names what the server is really running, and a reason-specific message whenever no forecast is available.

`/forecast/ml/compare` never turns a historical replay into `forecast_net_profit` or into the forecast ranking; those use live-history forecasts only.

## Deployment notes
* Install from `backend/requirements.txt` (includes the serving dependencies). scikit-learn is pinned to the version the shipped model was trained with (1.9.1) because pickled models are not guaranteed to load across versions.
* Memory: the API with ML loaded used about 250 MB RSS in local measurement. Check this against your host's memory limit before deploying.
* Known limits: 11 trained markets (only Bilaspur, Durg and Rajnandgaon are Chhattisgarh markets); on the test split the model did not beat the "price stays the same" baseline, which the API reports as a warning.
