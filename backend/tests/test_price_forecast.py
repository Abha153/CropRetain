"""
Tests for the ML price forecast: features (no future leakage), chronological
split, training artifacts, artifact loading, prediction, and invalid /
insufficient / stale / unsupported input.

Everything runs on SYNTHETIC data generated here -- no Kaggle download, no
network, no real DB. Metric VALUES are never asserted (synthetic data says
nothing about real accuracy); only structure, finiteness and invariants.
Requires: numpy, pandas, scikit-learn, joblib (requirements-ml.txt).
"""
import datetime as dt
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("joblib")

from app.services.price_forecast import features as F
from app.services.price_forecast import inference as inf
from scripts import train_price_forecast as T

TODAY = dt.date(2026, 6, 30)


def _synthetic_frame(days=420, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    specs = [("Chhattisgarh", "Bilaspur"), ("Maharashtra", "Nashik"), ("Maharashtra", "OtherMandi")]
    for crop, base in (("Tomato", 2200.0), ("Onion", 1800.0), ("Wheat", 2300.0)):
        for state, market in specs:
            p = base * rng.uniform(0.9, 1.1)
            for i in range(days, 0, -1):
                p = max(p * (1 + rng.normal(0, 0.03)) + 0.4 * (base - p) * 0.05, 50)
                if rng.random() < 0.15:           # ~15% of days missing, like real mandi data
                    continue
                rows.append((state, market, crop, pd.Timestamp(TODAY) - pd.Timedelta(days=i), float(p)))
    return pd.DataFrame(rows, columns=["state", "market", "crop", "date", "modal_price"])


@pytest.fixture(scope="module")
def frame():
    return _synthetic_frame()


@pytest.fixture(scope="module")
def artifact_dir(frame, tmp_path_factory):
    out = tmp_path_factory.mktemp("artifacts")
    T.train_from_frame(frame, out, max_iter=30, min_train_rows=200, min_leaf=20)
    return out


def _history(frame, crop="Tomato", market="Bilaspur", last_n=45):
    g = frame[(frame.crop == crop) & (frame.market == market)].sort_values("date").tail(last_n)
    return [{"date": d.date().isoformat(), "modal_price": p} for d, p in zip(g["date"], g["modal_price"])]


# ---------------- features: no future leakage ----------------
def test_features_ignore_future_prices():
    rng = np.random.default_rng(1)
    dates = pd.date_range("2025-01-01", periods=120, freq="D")
    s = F.daily_series(dates, 1000 + rng.normal(0, 20, 120).cumsum())
    cut = s.index[80]
    s_changed = s.copy()
    s_changed[s_changed.index > cut] *= 3.0           # wildly different future
    a = F.compute_features(s, 0).loc[:cut]
    b = F.compute_features(s_changed, 0).loc[:cut]
    pd.testing.assert_frame_equal(a, b)               # identical up to and incl. the as-of date


def test_target_is_exactly_horizon_days_ahead():
    dates = pd.date_range("2025-01-01", periods=60, freq="D")
    prices = np.linspace(1000, 1600, 60)
    s = F.daily_series(dates, prices)
    t = F.add_targets(F.compute_features(s, 0), s).dropna(subset=["y"])
    row = t.iloc[3]
    assert row["target_date"] == row.name + pd.Timedelta(days=F.HORIZON_DAYS)
    assert np.isclose(row["y"], np.log(s[row["target_date"]] / s[row.name]))
    assert len(t) == 60 - F.HORIZON_DAYS              # last H rows have no realised target


def test_limited_history_gives_same_features_as_full_history(frame):
    g = frame[(frame.crop == "Tomato") & (frame.market == "Bilaspur")]
    full = F.daily_series(g["date"], g["modal_price"])
    tail = full[full.index >= full.index[-1] - pd.Timedelta(days=60)]
    a = F.compute_features(full, 1).iloc[-1][F.FEATURE_COLS]
    b = F.compute_features(tail, 1).iloc[-1][F.FEATURE_COLS]
    pd.testing.assert_series_equal(a.astype(float), b.astype(float))


def test_bad_rows_are_dropped_not_guessed():
    s = F.daily_series(["2026-01-01", "not-a-date", "2026-01-03", "2026-01-04"], [100, 100, -5, float("nan")])
    assert list(s.index) == [pd.Timestamp("2026-01-01")]


# ---------------- split ----------------
def test_split_is_chronological_with_purge(frame):
    crop_idx = {c: i for i, c in enumerate(sorted(frame.crop.unique()))}
    tab = T.build_table(frame, crop_idx)
    train, val, test, t1, t2 = T.chronological_split(tab)
    assert len(train) and len(val) and len(test)
    assert train["target_date"].max() <= t1 < val["as_of"].min()
    assert val["target_date"].max() <= t2 < test["as_of"].min()
    assert train["as_of"].max() < val["as_of"].min() < test["as_of"].min()


# ---------------- training artifacts ----------------
def test_training_saves_all_artifacts_and_real_metrics(artifact_dir):
    for name in ("bundle.joblib", "metadata.json", "recent_history.csv"):
        assert (artifact_dir / name).is_file()
    meta = json.loads((artifact_dir / "metadata.json").read_text())
    assert meta["feature_cols"] == F.FEATURE_COLS
    assert meta["horizon_days"] == F.HORIZON_DAYS and meta["unit"] == F.PRICE_UNIT
    assert set(meta["commodity_idx"]) == {"Tomato", "Onion", "Wheat"}
    assert {"Bilaspur", "Nashik"} <= set(meta["known_markets"])
    test = meta["metrics"]["test"]
    for k in ("model", "baseline_persistence", "baseline_ma7"):
        assert np.isfinite(test[k]["mae"]) and np.isfinite(test[k]["rmse"])
    assert 0.0 <= test["interval_coverage_80"] <= 1.0
    # nothing target-derived may be a model input
    assert not {"Min_Price", "Max_Price", "y", "future_price"} & set(meta["feature_cols"])


def test_artifacts_load_and_validate(artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    assert set(arts.models) == {"point", "q10", "q90"}
    assert inf.load_artifacts(artifact_dir) is arts   # cached; not reloaded per request


def test_missing_artifacts_reported_not_trained(tmp_path):
    with pytest.raises(inf.ForecastError) as e:
        inf.load_artifacts(tmp_path / "nope")
    assert e.value.code == "artifacts_missing"


def test_mismatched_artifacts_rejected(artifact_dir, tmp_path):
    bad = tmp_path / "bad"
    shutil.copytree(artifact_dir, bad)
    meta = json.loads((bad / "metadata.json").read_text())
    meta["feature_cols"] = meta["feature_cols"][:-1]
    (bad / "metadata.json").write_text(json.dumps(meta))
    with pytest.raises(inf.ForecastError) as e:
        inf.load_artifacts(bad)
    assert e.value.code == "artifacts_invalid"


# ---------------- prediction ----------------
def test_prediction_shape_and_definition(frame, artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    hist = _history(frame)
    as_of = dt.date.fromisoformat(hist[-1]["date"])
    out = inf.predict(hist, "Tomato", "Bilaspur", today=as_of, artifacts=arts)
    assert out["target_field"] == "modal_price" and out["unit"] == F.PRICE_UNIT
    assert out["horizon_days"] == 7
    assert out["target_date"] == (as_of + dt.timedelta(days=7)).isoformat()
    assert out["as_of_date"] == as_of.isoformat()
    assert 0 < out["predicted_price_low"] <= out["predicted_price"] <= out["predicted_price_high"]
    assert abs(out["predicted_price_per_kg"] - out["predicted_price"] / 100) < 0.01
    assert out["baseline_persistence_price"] == out["last_observed_price"]
    # bounded by the safety guard
    assert 0.5 * out["last_observed_price"] <= out["predicted_price"] <= 2.0 * out["last_observed_price"] + 0.01
    again = inf.predict(hist, "Tomato", "Bilaspur", today=as_of, artifacts=arts)
    assert again == out                                # deterministic


def test_prediction_matches_direct_model_call_on_training_features(frame, artifact_dir):
    """Inference must produce exactly what the saved model gives on the shared feature code."""
    arts = inf.load_artifacts(artifact_dir)
    g = frame[(frame.crop == "Onion") & (frame.market == "Nashik")]
    s = F.daily_series(g["date"], g["modal_price"])
    row = F.compute_features(s, arts.meta["commodity_idx"]["Onion"]).iloc[-1]
    X = pd.DataFrame([row[F.FEATURE_COLS].to_dict()]).astype(float)
    X["commodity_idx"] = X["commodity_idx"].astype(int)
    expected = float(row["price"] * np.exp(np.clip(arts.models["point"].predict(X)[0], -F.MAX_ABS_LOG_RATIO, F.MAX_ABS_LOG_RATIO)))
    hist = _history(frame, "Onion", "Nashik", last_n=400)
    out = inf.predict(hist, "Onion", "Nashik", today=s.index[-1].date(), artifacts=arts)
    assert abs(out["predicted_price"] - round(expected, 2)) < 0.011


# ---------------- invalid / insufficient / stale / unsupported ----------------
def _code(fn):
    with pytest.raises(inf.ForecastError) as e:
        fn()
    return e.value.code


def test_insufficient_history(frame, artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    assert _code(lambda: inf.predict([], "Tomato", "Bilaspur", artifacts=arts)) == "insufficient_history"
    short = _history(frame, last_n=3)
    today = dt.date.fromisoformat(short[-1]["date"])
    assert _code(lambda: inf.predict(short, "Tomato", "Bilaspur", today=today, artifacts=arts)) == "insufficient_history"


def test_stale_history_refused_unless_explicit_replay(frame, artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    hist = _history(frame)
    old = dt.date.fromisoformat(hist[-1]["date"]) + dt.timedelta(days=30)
    assert _code(lambda: inf.predict(hist, "Tomato", "Bilaspur", today=old, artifacts=arts)) == "stale_history"
    out = inf.predict(hist, "Tomato", "Bilaspur", today=old, artifacts=arts, allow_stale=True)
    assert any("historical_replay" in w for w in out["warnings"])


def test_invalid_history_rejected(frame, artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    junk = [{"date": "garbage", "modal_price": 100}, {"date": "2026-06-01", "modal_price": -1},
            {"date": "2026-06-02", "modal_price": None}, {"date": "2026-06-03", "modal_price": "abc"}]
    assert _code(lambda: inf.predict(junk, "Tomato", "Bilaspur", today=TODAY, artifacts=arts)) == "invalid_history"
    future = [{"date": (TODAY + dt.timedelta(days=5)).isoformat(), "modal_price": 100.0}] * 1
    assert _code(lambda: inf.predict(future, "Tomato", "Bilaspur", today=TODAY, artifacts=arts)) == "invalid_history"


def test_unsupported_crop_and_unseen_market(frame, artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    hist = _history(frame)
    today = dt.date.fromisoformat(hist[-1]["date"])
    assert _code(lambda: inf.predict(hist, "Dragonfruit", "Bilaspur", today=today, artifacts=arts)) == "unsupported_crop"
    out = inf.predict(hist, "Tomato", "Raipur", today=today, artifacts=arts)   # market not in training data
    assert any("market_not_in_training_data" in w for w in out["warnings"])


def test_dd_mm_yyyy_dates_from_live_rows_are_accepted(frame, artifact_dir):
    arts = inf.load_artifacts(artifact_dir)
    hist = _history(frame)
    for h in hist:
        h["date"] = dt.date.fromisoformat(h["date"]).strftime("%d/%m/%Y")
    today = dt.datetime.strptime(hist[-1]["date"], "%d/%m/%Y").date()
    assert "predicted_price" in inf.predict(hist, "Tomato", "Bilaspur", today=today, artifacts=arts)
