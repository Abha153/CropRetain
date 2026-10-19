"""
Reproducible training for CropWise's ML price forecast. Run it in YOUR OWN
Python environment (it downloads the Kaggle dataset itself via kagglehub).

    cd backend
    python -m scripts.train_price_forecast                     # download + train
    python -m scripts.train_price_forecast --dataset-dir D:\\data\\commodity --since 2023-01-01

It trains HistGradientBoosting and CatBoost on identical features/splits, picks the winner on
VALIDATION error only, and writes models/price_forecast/
{bundle.joblib, metadata.json, analysis.json, recent_history.csv}.
Feature/target logic is NOT defined here -- it comes from
app/services/price_forecast/features.py, the same module inference uses.

Design (differs from the KrishiSight notebook on purpose; see README section):
  * leak-free: no target encoding / global aggregates / z-score of the target
  * chronological train / validation / test split with an H-day purge gap
  * log-ratio target -> scale-free across crops; compared with naive baselines
  * HistGradientBoosting (scikit-learn): handles NaN natively, no extra deps
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # allow `python scripts/...`

from app.services.price_forecast import features as F          # noqa: E402
from app.mock_data.crops import CROPS                           # noqa: E402
from app.mock_data.locations import MARKETS                     # noqa: E402

DATASET_HANDLE = "khandelwalmanas/daily-commodity-prices-india"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "models" / "price_forecast"
RECENT_DAYS = 60
MAX_TRAIN_ABS_LOG_RATIO = math.log(3.0)   # drop absurd TRAIN targets only (never filter val/test)

# CropWise crop -> candidate dataset commodity names. NOT verified against the
# dataset (it was not available when this was written): matching is by
# normalised string and the script prints exactly what matched / did not.
CROP_ALIASES = {
    "Tomato": ["Tomato"],
    "Paddy (Rice)": ["Paddy(Dhan)(Common)", "Paddy(Common)", "Paddy"],
    "Wheat": ["Wheat"],
    "Potato": ["Potato"],
    "Onion": ["Onion"],
    "Soybean": ["Soyabean", "Soybean"],
    "Maize": ["Maize"],
    "Chana (Gram)": ["Bengal Gram(Gram)(Whole)", "Bengal Gram", "Gram"],
    "Groundnut": ["Groundnut"],
    "Sugarcane": ["Sugarcane"],
}
# CropWise market -> extra dataset market names (renamed districts). Unverified.
MARKET_ALIASES = {
    "Ahilyanagar": ["Ahmednagar"],
    "Chhatrapati Sambhajinagar": ["Aurangabad"],
}
# Logical column -> candidate raw names (lower-cased, spaces/_x0020_ -> "_").
# First four mirror the notebook's COL_RENAMES / Arrival_Date / Modal_Price.
COLUMN_CANDIDATES = {
    "commodity": ["commodity_name", "commodity"],
    "market": ["market_name", "market"],
    "state": ["state_name", "state"],
    "date": ["arrival_date", "date", "price_date", "reported_date"],
    "modal": ["modal_price", "modal"],
}


def norm(x) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _canon_cols(cols):
    return {c: str(c).replace("_x0020_", "_").strip().lower().replace(" ", "_") for c in cols}


def detect_columns(cols) -> dict:
    canon = _canon_cols(cols)
    inv = {}
    for c, k in canon.items():
        inv.setdefault(k, c)
    found = {}
    for logical, cands in COLUMN_CANDIDATES.items():
        for cand in cands:
            if cand in inv:
                found[logical] = inv[cand]
                break
    return found


# ───────────────────────── data loading ─────────────────────────
def find_files(root: Path):
    pq = sorted(root.rglob("*.parquet"))
    return pq if pq else sorted(root.rglob("*.csv"))


def iter_chunks(path: Path, chunk_rows: int):
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=chunk_rows):
            yield batch.to_pandas()
    else:
        yield from pd.read_csv(path, chunksize=chunk_rows, low_memory=False, on_bad_lines="skip")


def load_filtered(files, wanted_norm: set, chunk_rows=1_000_000, max_rows=None) -> tuple:
    """Stream files, keep only rows of CropWise-mapped commodities."""
    kept, seen, total, used = [], Counter(), 0, []
    for path in files:
        cols = None
        for chunk in iter_chunks(path, chunk_rows):
            if cols is None:
                cols = detect_columns(chunk.columns)
                missing = {"commodity", "market", "date", "modal"} - set(cols)
                if missing:
                    print(f"  skip {path.name}: missing {sorted(missing)}; columns = {list(chunk.columns)}")
                    break
                used.append(path.name)
            sub = chunk[[cols[k] for k in cols]].rename(columns={v: k for k, v in cols.items()})
            seen.update(sub["commodity"].astype(str).value_counts().to_dict())
            sub = sub[sub["commodity"].astype(str).map(norm).isin(wanted_norm)]
            if "state" not in sub:
                sub["state"] = "Unknown"
            kept.append(sub)
            total += len(chunk)
            if max_rows and total >= max_rows:
                break
        print(f"  read {path.name} (cumulative rows scanned: {total:,})")
        if max_rows and total >= max_rows:
            print("  WARNING: --max-rows truncates by file order, NOT by date. Smoke test only.")
            break
    if not kept:
        raise SystemExit(f"No usable data files. Files seen: {[p.name for p in files]}")
    return pd.concat(kept, ignore_index=True), seen, used


def clean(raw: pd.DataFrame, since=None) -> tuple:
    """-> (df[state,market,crop,date,modal_price], commodity_map)."""
    alias_to_crop = {norm(a): crop for crop, al in CROP_ALIASES.items() for a in al}
    df = raw.copy()
    df["crop"] = df["commodity"].astype(str).map(norm).map(alias_to_crop)
    cmap = {}
    for crop, grp in df.groupby("crop"):
        cmap[crop] = {str(k): int(v) for k, v in grp["commodity"].value_counts().items()}
    df["date"] = F.parse_dates(df["date"])
    df["modal_price"] = pd.to_numeric(df["modal"], errors="coerce")
    df["market"] = df["market"].astype(str).str.strip()
    df["state"] = df["state"].fillna("Unknown").astype(str).str.strip()
    n0 = len(df)
    df = df.dropna(subset=["crop", "date", "modal_price"])
    df = df[(df["modal_price"] > 0) & np.isfinite(df["modal_price"])]
    df = df[df["date"] <= pd.Timestamp(dt.date.today())]
    if since:
        df = df[df["date"] >= pd.Timestamp(since)]
    print(f"  cleaned rows: {len(df):,} of {n0:,} candidate rows")
    df = (df.groupby(["state", "market", "crop", "date"], as_index=False)["modal_price"].median())
    return df, cmap


# ───────────────────────── features / split ─────────────────────────
def build_table(df: pd.DataFrame, crop_idx: dict) -> pd.DataFrame:
    parts, n = [], 0
    groups = df.groupby(["state", "market", "crop"], sort=False)
    total = groups.ngroups
    for (state, market, crop), g in groups:
        s = F.daily_series(g["date"], g["modal_price"])
        if len(s) < F.MIN_OBS_28 + 1:
            continue
        f = F.add_targets(F.compute_features(s, crop_idx[crop]), s)
        f = f[f["eligible"] & f["y"].notna()].copy()
        if f.empty:
            continue
        f["state"], f["market"], f["crop"] = state, market, crop
        f.index.name = "as_of"
        parts.append(f.reset_index())
        n += 1
        if n % 2000 == 0:
            print(f"  featurised {n:,}/{total:,} series")
    if not parts:
        raise SystemExit("No series had enough history to build training rows.")
    return pd.concat(parts, ignore_index=True)


def chronological_split(tab: pd.DataFrame, train_frac=0.70, val_frac=0.15):
    """Split on as-of date with an H-day purge so no label window crosses a boundary."""
    dates = np.sort(tab["as_of"].unique())
    t1 = dates[int(len(dates) * train_frac) - 1]
    t2 = dates[int(len(dates) * (train_frac + val_frac)) - 1]
    H = pd.Timedelta(days=F.HORIZON_DAYS)
    train = tab[tab["target_date"] <= t1]
    val = tab[(tab["as_of"] > t1) & (tab["target_date"] <= t2)]
    test = tab[tab["as_of"] > t2]
    return train, val, test, pd.Timestamp(t1), pd.Timestamp(t2)


# ───────────────────────── model / metrics ─────────────────────────
def _hgb(max_iter, loss="absolute_error", quantile=None, seed=42):
    from sklearn.ensemble import HistGradientBoostingRegressor
    kw = dict(loss=loss, max_iter=max_iter, learning_rate=0.08, max_leaf_nodes=31,
              min_samples_leaf=100, l2_regularization=1.0, early_stopping=False,
              categorical_features=F.CATEGORICAL_COLS, random_state=seed)
    if quantile is not None:
        kw["quantile"] = quantile
    return HistGradientBoostingRegressor(**kw)


def _xy(t: pd.DataFrame):
    X = t[F.FEATURE_COLS].astype(float)
    X["commodity_idx"] = X["commodity_idx"].astype(int)
    return X, t["y"].to_numpy()


def _price(t: pd.DataFrame, ratio) -> np.ndarray:
    return t["price"].to_numpy() * np.exp(np.clip(ratio, -F.MAX_ABS_LOG_RATIO, F.MAX_ABS_LOG_RATIO))


def mae(a, b): return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))
def rmse(a, b): return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))
def mape(a, b):
    a = np.asarray(a, dtype=float)
    return float(np.mean(np.abs(a - np.asarray(b)) / np.abs(a)))   # actual prices are > 0


def evaluate(t: pd.DataFrame, pred_price, lo, hi) -> dict:
    actual = t["future_price"].to_numpy()
    persistence = t["price"].to_numpy()
    ma7 = persistence * np.exp(-t["dev_ma7"].to_numpy())
    out = {
        "rows": int(len(t)),
        "model": {"mae": mae(actual, pred_price), "rmse": rmse(actual, pred_price), "mape": mape(actual, pred_price)},
        "baseline_persistence": {"mae": mae(actual, persistence), "rmse": rmse(actual, persistence),
                                 "mape": mape(actual, persistence)},
        "baseline_ma7": {"mae": mae(actual, ma7), "rmse": rmse(actual, ma7), "mape": mape(actual, ma7)},
        "interval_coverage_80": float(np.mean((actual >= lo) & (actual <= hi))),
        "unit": F.PRICE_UNIT,
    }
    out["model_beats_persistence"] = out["model"]["mae"] < out["baseline_persistence"]["mae"]
    return out


# ───────────────────────── model families ─────────────────────────
FAMILY_LABELS = {
    "hgb": "HistGradientBoosting on log price-ratio (scikit-learn)",
    "catboost": "CatBoost on log price-ratio",
}
# A challenger replaces the incumbent (the first family) only if it cuts VALIDATION
# MAE by at least this much; otherwise the lighter/simpler model ships.
SELECTION_MARGIN = 0.01
# A crop is only offered if it has at least this many rows in BOTH the validation and the
# test split -- otherwise its accuracy is unmeasured and we refuse to forecast it.
MIN_HELDOUT_ROWS = 300
INTERVAL_TARGET = 0.80      # nominal coverage of the q10-q90 band
FEATURE_LABELS = {
    "commodity_idx": "Crop",
    "log_price": "Current price level",
    "ret_7": "Price change over last 7 days",
    "ret_14": "Price change over last 14 days",
    "dev_ma7": "Distance from 7-day average",
    "dev_ma28": "Distance from 28-day average",
    "cv_28": "Price volatility (28 days)",
    "n_obs_7": "Days with a price (last 7)",
    "n_obs_28": "Days with a price (last 28)",
    "target_month": "Month being forecast",
    "target_doy": "Day of year being forecast",
}


def available_families(requested) -> list:
    out = []
    for fam in requested:
        if fam == "hgb":
            out.append(fam)
        elif fam == "catboost":
            try:
                import catboost  # noqa: F401
                out.append(fam)
            except ImportError:
                print("  catboost is not installed -> skipping that challenger (pip install catboost)")
        else:
            raise SystemExit(f"Unknown model family {fam!r}; choose from {sorted(FAMILY_LABELS)}")
    if not out:
        raise SystemExit("No usable model family.")
    return out


def _fit_hgb(Xtr, ytr, val, Xva, max_iter, min_leaf):
    probe = _hgb(max_iter).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr)
    best_n, best_mae = max_iter, float("inf")
    for i, pred in enumerate(probe.staged_predict(Xva), start=1):
        if i % 10 == 0 or i == max_iter:
            m = mae(val["future_price"], _price(val, pred))
            if m < best_mae:
                best_n, best_mae = i, m
    print(f"  [hgb] best rounds = {best_n} (validation MAE {best_mae:.2f})")
    models = {
        "point": _hgb(best_n).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr),
        "q10": _hgb(best_n, "quantile", 0.10).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr),
        "q90": _hgb(best_n, "quantile", 0.90).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr),
    }
    return models, best_n


def _fit_catboost(Xtr, ytr, Xva, yva, max_iter):
    from catboost import CatBoostRegressor
    common = dict(learning_rate=0.08, depth=6, l2_leaf_reg=3.0, random_seed=42, verbose=0,
                  thread_count=-1, cat_features=list(F.CATEGORICAL_COLS), allow_writing_files=False)
    point = CatBoostRegressor(loss_function="MAE", iterations=max_iter * 3, **common)
    point.fit(Xtr, ytr, eval_set=(Xva, yva), use_best_model=True, early_stopping_rounds=50)
    best_n = int(point.get_best_iteration()) + 1
    print(f"  [catboost] best rounds = {best_n} (early stopping on validation MAE, log-ratio space)")
    models = {"point": point}
    for name, alpha in (("q10", 0.10), ("q90", 0.90)):
        models[name] = CatBoostRegressor(loss_function=f"Quantile:alpha={alpha}", iterations=best_n,
                                         **common).fit(Xtr, ytr)
    return models, best_n


def _run(models, t, X, pad=0.0):
    """Point forecast and band in INR/quintal. `pad` (log-ratio units, may be negative) widens the
    q10/q90 band after calibration on the validation split."""
    p = models["point"].predict(X)
    lo = np.minimum(models["q10"].predict(X) - pad, p)
    hi = np.maximum(models["q90"].predict(X) + pad, p)
    return _price(t, p), _price(t, lo), _price(t, hi)


def calibrate_interval_pad(models, val, Xva, target=INTERVAL_TARGET) -> float:
    """Conformalised quantile regression (Romano et al. 2019): the band's raw q10/q90 under-cover
    out of sample, so widen/narrow both ends by the finite-sample `target` quantile of how far the
    VALIDATION outcomes fell outside (positive) or inside (negative) the raw band. Uses validation
    only -- never the test split."""
    p = models["point"].predict(Xva)
    lo = np.minimum(models["q10"].predict(Xva), p)
    hi = np.maximum(models["q90"].predict(Xva), p)
    y = val["y"].to_numpy()
    score = np.maximum(lo - y, y - hi)
    n = len(score)
    k = min(int(np.ceil((n + 1) * target)), n)
    return float(np.sort(score)[k - 1])


def _perm_importance(point, t, X, max_rows=20000, repeats=2, seed=0) -> dict:
    """Permutation importance on held-out rows: how much the point forecast's MAE
    (INR/quintal) worsens when one input column is shuffled."""
    rng = np.random.default_rng(seed)
    if len(t) > max_rows:
        sel = rng.choice(len(t), max_rows, replace=False)
        t, X = t.iloc[sel], X.iloc[sel]
    base = mae(t["future_price"], _price(t, point.predict(X)))
    inc = {}
    for c in F.FEATURE_COLS:
        vals = []
        for _ in range(repeats):
            Xp = X.copy()
            Xp[c] = rng.permutation(Xp[c].to_numpy())
            vals.append(mae(t["future_price"], _price(t, point.predict(Xp))) - base)
        inc[c] = float(np.mean(vals))
    pos = {k: max(v, 0.0) for k, v in inc.items()}
    tot = sum(pos.values()) or 1.0
    ranked = sorted(inc, key=lambda k: inc[k], reverse=True)
    return {"baseline_mae": base, "evaluated_rows": int(len(t)), "ranking": [
        {"feature": k, "label": FEATURE_LABELS.get(k, k), "mae_increase": inc[k], "share": pos[k] / tot}
        for k in ranked]}


def _group_metrics(t: pd.DataFrame, pp, lo, hi) -> dict:
    a, p0 = t["future_price"].to_numpy(), t["price"].to_numpy()
    ma7 = p0 * np.exp(-t["dev_ma7"].to_numpy())
    chg_a, chg_p = a / p0 - 1.0, pp / p0 - 1.0
    big = np.abs(chg_a) >= 0.02          # directional accuracy only where the market really moved
    dir_acc = float(np.mean(np.sign(chg_p[big]) == np.sign(chg_a[big]))) if big.sum() >= 20 else None
    m_mae, b_mae = mae(a, pp), mae(a, p0)
    return {
        "rows": int(len(t)), "model_mae": m_mae, "persistence_mae": b_mae, "ma7_mae": mae(a, ma7),
        "model_mape": mape(a, pp), "persistence_mape": mape(a, p0),
        "skill_vs_persistence": (1.0 - m_mae / b_mae) if b_mae > 0 else None,
        "interval_coverage_80": float(np.mean((a >= lo) & (a <= hi))),
        "directional_accuracy": dir_acc, "directional_rows": int(big.sum()),
        "low_sample": bool(len(t) < 200),
    }


def build_analysis(test: pd.DataFrame, pp, lo, hi, importance: dict, meta: dict) -> dict:
    """Everything the frontend 'model analysis' panel shows, computed on the held-out test split."""
    t = test.reset_index(drop=True).copy()
    t["pp"], t["lo"], t["hi"] = pp, lo, hi
    a, p0 = t["future_price"].to_numpy(), t["price"].to_numpy()

    per_crop = {c: _group_metrics(g, g["pp"].to_numpy(), g["lo"].to_numpy(), g["hi"].to_numpy())
                for c, g in t.groupby("crop")}
    per_state = {}
    for s, g in t.groupby("state"):
        if len(g) >= 30:
            per_state[s] = _group_metrics(g, g["pp"].to_numpy(), g["lo"].to_numpy(), g["hi"].to_numpy())

    t["week"] = t["target_date"].dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")
    weekly = {}
    for c, g in [("All crops", t)] + list(t.groupby("crop")):
        rows = []
        for w, x in g.groupby("week"):
            if len(x) < 10:
                continue
            xa, xp0, xpp = x["future_price"].to_numpy(), x["price"].to_numpy(), x["pp"].to_numpy()
            rows.append({"week": w, "rows": int(len(x)),
                         "actual_change_pct": float(np.mean(xa / xp0 - 1) * 100),
                         "predicted_change_pct": float(np.mean(xpp / xp0 - 1) * 100),
                         "model_mae": mae(xa, xpp), "persistence_mae": mae(xa, xp0)})
        weekly[c] = rows

    err_m, err_b = np.abs(t["pp"].to_numpy() - a) / a, np.abs(p0 - a) / a
    edges = [(0.05, "within 5%"), (0.10, "within 10%"), (0.20, "within 20%")]
    buckets = [{"label": lab, "model": float(np.mean(err_m <= e)), "persistence": float(np.mean(err_b <= e))}
               for e, lab in edges]
    buckets.append({"label": "off by more than 20%", "model": float(np.mean(err_m > 0.20)),
                    "persistence": float(np.mean(err_b > 0.20))})

    rng = np.random.default_rng(0)
    pick = rng.choice(len(t), size=min(400, len(t)), replace=False)
    scatter = [{"actual": round(float(a[i] / p0[i] - 1) * 100, 2),
                "predicted": round(float(t["pp"].iat[i] / p0[i] - 1) * 100, 2), "crop": t["crop"].iat[i]}
               for i in pick]

    return {
        "schema_version": 1,
        "unit": F.PRICE_UNIT, "horizon_days": F.HORIZON_DAYS,
        "model": {"family": meta["model_family"], "label": FAMILY_LABELS[meta["model_family"]],
                  "trained_utc": meta["created_utc"], "best_iter": meta["best_iter"]},
        "selection": meta["selection"],
        "data": {"dataset": meta["dataset"], "date_range": meta["data_date_range"], "split": meta["split"],
                 "crops": sorted(meta["commodity_idx"]), "excluded_crops": meta.get("excluded_crops") or {},
                 "interval": meta.get("interval"), "prep": meta.get("data_prep")},
        "overall": {"validation": meta["metrics"]["validation"], "test": meta["metrics"]["test"]},
        "candidates": meta["metrics"]["candidates"],
        "per_crop_test": per_crop, "per_state_test": per_state,
        "weekly_test": weekly, "error_buckets_test": buckets, "scatter_test": scatter,
        "feature_importance": importance,
        "plain_language": {
            "what_it_predicts": f"The modal mandi price {F.HORIZON_DAYS} days after the latest observed price.",
            "how_tested": "Trained on earlier dates only; every number here is measured on later dates the model never saw, "
                          f"with a {F.HORIZON_DAYS}-day gap between the splits.",
            "baseline": "The 'price stays the same' baseline is the benchmark any forecast must beat.",
        },
    }


def _clean_json(o):
    """NaN/inf -> None and numpy scalars -> python, so the file is strict JSON."""
    if isinstance(o, dict):
        return {str(k): _clean_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean_json(v) for v in o]
    if isinstance(o, (np.floating, float)):
        v = float(o)
        return round(v, 6) if math.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def train_from_frame(df: pd.DataFrame, out_dir: Path, *, cmap=None, dataset_handle=DATASET_HANDLE,
                     dataset_files=None, max_iter=300, min_train_rows=1000, min_leaf=100,
                     families=("hgb",), prep_report=None, min_heldout_rows=MIN_HELDOUT_ROWS) -> dict:
    """df columns: state, market, crop (CropWise crop name), date, modal_price. Returns metadata.

    families: model families to train on the SAME features/splits. The first is the incumbent;
    a later one replaces it only if it lowers VALIDATION MAE by >= SELECTION_MARGIN. Test-split
    numbers of every family are reported for transparency but never used to choose."""
    families = available_families(families)
    crops_present = sorted(df["crop"].unique())
    crop_idx = {c: i for i, c in enumerate(crops_present)}
    print(f"[2/5] features for {df.groupby(['state','market','crop']).ngroups:,} series ...")
    tab = build_table(df, crop_idx)
    train, val, test, t1, t2 = chronological_split(tab)
    counts = {c: {"train_rows": int((train["crop"] == c).sum()), "val_rows": int((val["crop"] == c).sum()),
                  "test_rows": int((test["crop"] == c).sum())} for c in crops_present}
    supported = [c for c in crops_present
                 if counts[c]["val_rows"] >= min_heldout_rows and counts[c]["test_rows"] >= min_heldout_rows]
    excluded = {c: {**counts[c], "reason": f"fewer than {min_heldout_rows} rows in the validation and/or test split, "
                                          "so accuracy cannot be measured"}
                for c in crops_present if c not in supported}
    if excluded:
        print(f"  EXCLUDED crops (accuracy cannot be measured): {json.dumps(excluded)}")
        if not supported:
            raise SystemExit("No crop has enough validation and test rows; use more/longer history.")
        crops_present = supported
        crop_idx = {c: i for i, c in enumerate(crops_present)}
        tab = tab[tab["crop"].isin(supported)].copy()
        tab["commodity_idx"] = tab["crop"].map(crop_idx)
        train, val, test, t1, t2 = chronological_split(tab)
    print(f"  split | train<= {t1.date()} ({len(train):,}) | val<= {t2.date()} ({len(val):,}) | test> {t2.date()} ({len(test):,})")
    if len(train) < min_train_rows or len(val) == 0 or len(test) == 0:
        raise SystemExit("Not enough rows for a chronological train/val/test split. Use more data / earlier --since.")
    train = train[train["y"].abs() <= MAX_TRAIN_ABS_LOG_RATIO]

    Xtr, ytr = _xy(train); Xva, yva = _xy(val); Xte, _ = _xy(test)
    print(f"[3/5] fitting {', '.join(families)} (point + q10 + q90 each) on TRAIN only ...")
    results = {}
    for fam in families:
        t0 = time.time()
        if fam == "hgb":
            models, best_n = _fit_hgb(Xtr, ytr, val, Xva, max_iter, min_leaf)
        else:
            models, best_n = _fit_catboost(Xtr, ytr, Xva, yva, max_iter)
        pad = calibrate_interval_pad(models, val, Xva)
        v_pred, te_pred = _run(models, val, Xva, pad), _run(models, test, Xte, pad)
        results[fam] = {"models": models, "best_iter": best_n, "te_pred": te_pred, "pad": pad,
                        "validation": evaluate(val, *v_pred), "test": evaluate(test, *te_pred)}
        print(f"  {fam}: validation MAE {results[fam]['validation']['model']['mae']:.2f} | "
              f"test MAE {results[fam]['test']['model']['mae']:.2f} ({time.time()-t0:.0f}s)")

    winner = families[0]
    for challenger in families[1:]:
        inc = results[winner]["validation"]["model"]["mae"]
        if results[challenger]["validation"]["model"]["mae"] < inc * (1.0 - SELECTION_MARGIN):
            winner = challenger
    chosen = results[winner]
    print(f"[4/5] selected '{winner}' on validation MAE (margin {SELECTION_MARGIN:.0%})")
    models, best_n = chosen["models"], chosen["best_iter"]
    metrics = {"validation": chosen["validation"], "test": chosen["test"],
               "candidates": {f: {"validation": r["validation"], "test": r["test"], "best_iter": r["best_iter"],
                                    "interval_log_pad": r["pad"]}
                              for f, r in results.items()}}
    pp, plo, phi = chosen["te_pred"]
    per_crop = {}
    for crop in crops_present:
        m = (test["crop"] == crop).to_numpy()
        if m.sum():
            a = test["future_price"].to_numpy()[m]
            per_crop[crop] = {"rows": int(m.sum()), "model_mae": mae(a, pp[m]),
                              "persistence_mae": mae(a, test["price"].to_numpy()[m])}
    metrics["per_crop_test"] = per_crop
    importance = _perm_importance(models["point"], val, Xva)

    # snapshot of the dataset tail for CropWise markets (demo replay only)
    wanted = {}
    for m in MARKETS:
        names = {norm(m["name"])} | {norm(a) for a in MARKET_ALIASES.get(m["name"], [])}
        wanted[(norm(m["state"]), m["name"])] = names
    snap_rows, market_map = [], {}
    for (state, market, crop), g in df.groupby(["state", "market", "crop"]):
        for (st_n, cw_name), names in wanted.items():
            if norm(market) in names and (norm(state) == st_n or state == "Unknown"):
                g = g.sort_values("date")
                tail = g[g["date"] >= g["date"].max() - pd.Timedelta(days=RECENT_DAYS - 1)]
                snap_rows += [{"crop": crop, "market": cw_name, "date": d.date().isoformat(), "modal_price": float(p)}
                              for d, p in zip(tail["date"], tail["modal_price"])]
                market_map.setdefault(cw_name, set()).add(f"{state}/{market}")
    out_dir.mkdir(parents=True, exist_ok=True)
    import joblib, sklearn
    joblib.dump(models, out_dir / "bundle.joblib", compress=3)
    pd.DataFrame(snap_rows, columns=["crop", "market", "date", "modal_price"]).to_csv(out_dir / "recent_history.csv", index=False)
    versions = {"python": sys.version.split()[0], "sklearn": sklearn.__version__,
                "pandas": pd.__version__, "numpy": np.__version__}
    if "catboost" in results:
        import catboost
        versions["catboost"] = catboost.__version__
    data_prep = None
    if prep_report:
        data_prep = {k: prep_report.get(k) for k in (
            "input_file", "rows_in", "rows_out", "rows_out_share_of_input", "series", "markets", "states",
            "steps", "date_recovery_simulation", "identifier_recovery_simulation", "notes")}
    meta = {
        "schema_version": F.SCHEMA_VERSION, "horizon_days": F.HORIZON_DAYS,
        "target_field": F.TARGET_FIELD, "unit": F.PRICE_UNIT,
        "target": "log(price[as_of+H] / price[as_of])",
        "model_family": winner, "model_label": FAMILY_LABELS[winner],
        "selection": {"rule": f"lowest validation MAE; a challenger must beat the incumbent by >= {SELECTION_MARGIN:.0%}",
                      "chosen": winner, "incumbent": families[0], "margin": SELECTION_MARGIN,
                      "validation_mae": {f: r["validation"]["model"]["mae"] for f, r in results.items()},
                      "test_split_used_for_selection": False},
        "feature_cols": F.FEATURE_COLS, "categorical_cols": F.CATEGORICAL_COLS,
        "commodity_idx": crop_idx, "commodity_map": cmap or {},
        "known_markets": sorted(market_map), "market_map": {k: sorted(v) for k, v in market_map.items()},
        "dataset": dataset_handle, "dataset_files": dataset_files or [],
        "data_date_range": [str(df["date"].min().date()), str(df["date"].max().date())],
        "split": {"train_through_target_date": str(t1.date()), "val_through_target_date": str(t2.date()),
                  "rows": {"train": int(len(train)), "val": int(len(val)), "test": int(len(test))},
                  "purge_days": F.HORIZON_DAYS},
        "best_iter": best_n, "min_samples_leaf": min_leaf,
        "interval": {"nominal": INTERVAL_TARGET, "log_pad": chosen["pad"],
                     "method": "q10/q90 quantile models, widened by a split-conformal pad fitted on the "
                               "validation split only (test coverage is out-of-sample)"},
        "excluded_crops": excluded,
        "metrics": metrics,
        "data_prep": data_prep,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "versions": versions,
    }
    meta = _clean_json(meta)
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2, allow_nan=False), encoding="utf-8")
    analysis = _clean_json(build_analysis(test, pp, plo, phi, importance, meta))
    (out_dir / "analysis.json").write_text(json.dumps(analysis, allow_nan=False, separators=(",", ":")),
                                           encoding="utf-8")
    return meta


def print_report(meta: dict):
    print("\n=== RESULTS (computed on the held-out chronological splits; units: INR/quintal) ===")
    for split in ("validation", "test"):
        m = meta["metrics"][split]
        print(f"{split:>10} rows={m['rows']:,}   [model = {meta['model_family']}]")
        for k in ("model", "baseline_persistence", "baseline_ma7"):
            print(f"{'':>12}{k:<22} MAE={m[k]['mae']:.2f}  RMSE={m[k]['rmse']:.2f}  MAPE={m[k]['mape']:.1%}")
        print(f"{'':>12}80% interval coverage = {m['interval_coverage_80']:.1%}; beats persistence: {m['model_beats_persistence']}")
    cands = meta["metrics"].get("candidates", {})
    if len(cands) > 1:
        print("\n--- candidates (same features, same splits; chosen on VALIDATION MAE only) ---")
        for fam, r in cands.items():
            print(f"{fam:>10}  validation MAE={r['validation']['model']['mae']:.2f}   test MAE={r['test']['model']['mae']:.2f}"
                  f"   {'<- selected' if fam == meta['model_family'] else ''}")
    print(f"artifacts -> see out dir; known CropWise markets in data: {meta['known_markets']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset-dir", help="already-downloaded dataset folder (skips kagglehub)")
    ap.add_argument("--dataset-handle", default=DATASET_HANDLE)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--since", help="only use rows on/after YYYY-MM-DD (recommended: dataset is huge)")
    ap.add_argument("--max-rows", type=int, help="smoke test only: stop after N scanned rows (NOT chronological)")
    ap.add_argument("--max-iter", type=int, default=300)
    ap.add_argument("--models", default="hgb,catboost",
                    help="comma-separated model families to compare (first = incumbent). Default: hgb,catboost")
    ap.add_argument("--prep-report", help="prep_report.json written by scripts.prepare_price_data (embedded in metadata)")
    args = ap.parse_args(argv)

    t0 = time.time()
    if args.dataset_dir:
        root = Path(args.dataset_dir)
    else:
        import kagglehub
        print(f"[1/5] kagglehub.dataset_download({args.dataset_handle!r}) ...")
        root = Path(kagglehub.dataset_download(args.dataset_handle))
    files = find_files(root)
    print(f"[1/5] {len(files)} data file(s) under {root}: {[f.name for f in files][:10]}")
    wanted = {norm(a) for al in CROP_ALIASES.values() for a in al}
    raw, seen, used = load_filtered(files, wanted, max_rows=args.max_rows)
    df, cmap = clean(raw, args.since)
    missing = [c for c in CROP_ALIASES if c not in cmap]
    for c in missing:
        import difflib
        guess = difflib.get_close_matches(CROP_ALIASES[c][0], list(seen), n=5, cutoff=0.5)
        print(f"  NO MATCH for CropWise crop '{c}'. Closest dataset names: {guess}. Edit CROP_ALIASES to include one.")
    if not cmap:
        raise SystemExit("No CropWise crop matched any dataset commodity; fix CROP_ALIASES.")
    print("  crop -> dataset names:", json.dumps(cmap, indent=1)[:1500])
    prep = None
    if args.prep_report:
        prep = json.loads(Path(args.prep_report).read_text(encoding="utf-8"))
    elif (root / "prep_report.json").is_file():
        prep = json.loads((root / "prep_report.json").read_text(encoding="utf-8"))
    meta = train_from_frame(df, Path(args.out_dir), cmap=cmap, dataset_handle=args.dataset_handle,
                            dataset_files=used, max_iter=args.max_iter,
                            families=tuple(x.strip() for x in args.models.split(",") if x.strip()),
                            prep_report=prep)
    print_report(meta)
    print(f"[5/5] saved to {args.out_dir} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
