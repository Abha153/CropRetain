"""
Reproducible training for CropWise's ML price forecast. Run it in YOUR OWN
Python environment (it downloads the Kaggle dataset itself via kagglehub).

    cd backend
    python -m scripts.train_price_forecast                     # download + train
    python -m scripts.train_price_forecast --dataset-dir D:\\data\\commodity --since 2023-01-01

It writes models/price_forecast/{bundle.joblib, metadata.json, recent_history.csv}.
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


def evaluate(t: pd.DataFrame, pred_price, lo, hi) -> dict:
    actual = t["future_price"].to_numpy()
    persistence = t["price"].to_numpy()
    ma7 = persistence * np.exp(-t["dev_ma7"].to_numpy())
    out = {
        "rows": int(len(t)),
        "model": {"mae": mae(actual, pred_price), "rmse": rmse(actual, pred_price)},
        "baseline_persistence": {"mae": mae(actual, persistence), "rmse": rmse(actual, persistence)},
        "baseline_ma7": {"mae": mae(actual, ma7), "rmse": rmse(actual, ma7)},
        "interval_coverage_80": float(np.mean((actual >= lo) & (actual <= hi))),
        "unit": F.PRICE_UNIT,
    }
    out["model_beats_persistence"] = out["model"]["mae"] < out["baseline_persistence"]["mae"]
    return out


def train_from_frame(df: pd.DataFrame, out_dir: Path, *, cmap=None, dataset_handle=DATASET_HANDLE,
                     dataset_files=None, max_iter=300, min_train_rows=1000, min_leaf=100) -> dict:
    """df columns: state, market, crop (CropWise crop name), date, modal_price. Returns metadata."""
    crops_present = sorted(df["crop"].unique())
    crop_idx = {c: i for i, c in enumerate(crops_present)}
    print(f"[2/5] features for {df.groupby(['state','market','crop']).ngroups:,} series ...")
    tab = build_table(df, crop_idx)
    train, val, test, t1, t2 = chronological_split(tab)
    print(f"  split | train<= {t1.date()} ({len(train):,}) | val<= {t2.date()} ({len(val):,}) | test> {t2.date()} ({len(test):,})")
    if len(train) < min_train_rows or len(val) == 0 or len(test) == 0:
        raise SystemExit("Not enough rows for a chronological train/val/test split. Use more data / earlier --since.")
    train = train[train["y"].abs() <= MAX_TRAIN_ABS_LOG_RATIO]

    Xtr, ytr = _xy(train); Xva, _ = _xy(val); Xte, _ = _xy(test)
    print(f"[3/5] selecting boosting rounds on validation (max {max_iter}) ...")
    probe = _hgb(max_iter).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr)
    best_n, best_mae = max_iter, float("inf")
    for i, pred in enumerate(probe.staged_predict(Xva), start=1):
        if i % 10 == 0 or i == max_iter:
            m = mae(val["future_price"], _price(val, pred))
            if m < best_mae:
                best_n, best_mae = i, m
    print(f"  best rounds = {best_n} (validation MAE {best_mae:.2f})")

    print("[4/5] fitting final point + q10 + q90 models on TRAIN only ...")
    models = {
        "point": _hgb(best_n).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr),
        "q10": _hgb(best_n, "quantile", 0.10).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr),
        "q90": _hgb(best_n, "quantile", 0.90).set_params(min_samples_leaf=min_leaf).fit(Xtr, ytr),
    }

    def run(t, X):
        p = models["point"].predict(X)
        lo = np.minimum(models["q10"].predict(X), p)
        hi = np.maximum(models["q90"].predict(X), p)
        return _price(t, p), _price(t, lo), _price(t, hi)

    metrics = {}
    for name, t, X in (("validation", val, Xva), ("test", test, Xte)):
        metrics[name] = evaluate(t, *run(t, X))
    pp, _, _ = run(test, Xte)
    per_crop = {}
    for crop in crops_present:
        m = (test["crop"] == crop).to_numpy()
        if m.sum():
            a = test["future_price"].to_numpy()[m]
            per_crop[crop] = {"rows": int(m.sum()), "model_mae": mae(a, pp[m]),
                              "persistence_mae": mae(a, test["price"].to_numpy()[m])}

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
    meta = {
        "schema_version": F.SCHEMA_VERSION, "horizon_days": F.HORIZON_DAYS,
        "target_field": F.TARGET_FIELD, "unit": F.PRICE_UNIT,
        "target": "log(price[as_of+H] / price[as_of])",
        "feature_cols": F.FEATURE_COLS, "categorical_cols": F.CATEGORICAL_COLS,
        "commodity_idx": crop_idx, "commodity_map": cmap or {},
        "known_markets": sorted(market_map), "market_map": {k: sorted(v) for k, v in market_map.items()},
        "dataset": dataset_handle, "dataset_files": dataset_files or [],
        "data_date_range": [str(df["date"].min().date()), str(df["date"].max().date())],
        "split": {"train_through_target_date": str(t1.date()), "val_through_target_date": str(t2.date()),
                  "rows": {"train": int(len(train)), "val": int(len(val)), "test": int(len(test))},
                  "purge_days": F.HORIZON_DAYS},
        "best_iter": best_n, "min_samples_leaf": min_leaf,
        "metrics": {**metrics, "per_crop_test": per_crop},
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "versions": {"python": sys.version.split()[0], "sklearn": sklearn.__version__,
                     "pandas": pd.__version__, "numpy": np.__version__},
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def print_report(meta: dict):
    print("\n=== RESULTS (computed on the held-out chronological splits; units: INR/quintal) ===")
    for split in ("validation", "test"):
        m = meta["metrics"][split]
        print(f"{split:>10} rows={m['rows']:,}")
        for k in ("model", "baseline_persistence", "baseline_ma7"):
            print(f"{'':>12}{k:<22} MAE={m[k]['mae']:.2f}  RMSE={m[k]['rmse']:.2f}")
        print(f"{'':>12}80% interval coverage = {m['interval_coverage_80']:.1%}; beats persistence: {m['model_beats_persistence']}")
    print(f"artifacts -> see out dir; known CropWise markets in data: {meta['known_markets']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset-dir", help="already-downloaded dataset folder (skips kagglehub)")
    ap.add_argument("--dataset-handle", default=DATASET_HANDLE)
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--since", help="only use rows on/after YYYY-MM-DD (recommended: dataset is huge)")
    ap.add_argument("--max-rows", type=int, help="smoke test only: stop after N scanned rows (NOT chronological)")
    ap.add_argument("--max-iter", type=int, default=300)
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
    meta = train_from_frame(df, Path(args.out_dir), cmap=cmap, dataset_handle=args.dataset_handle,
                            dataset_files=used, max_iter=args.max_iter)
    print_report(meta)
    print(f"[5/5] saved to {args.out_dir} in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
