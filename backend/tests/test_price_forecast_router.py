"""
Router-level tests for /forecast/ml/* using an isolated in-memory SQLite DB
and the artifacts trained on synthetic data (no network, no Kaggle).
Skipped automatically if the API deps or ML deps are not installed.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("sklearn")

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routers import market as market_router
from app.routers import price_forecast_ml as r
from tests.test_price_forecast import _synthetic_frame, T  # reuse the synthetic generator/trainer


@pytest.fixture(scope="module")
def art_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("router_artifacts")
    T.train_from_frame(_synthetic_frame(), out, max_iter=30, min_train_rows=200, min_leaf=20, min_heldout_rows=1)
    return out


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _seed_live(db, crop="Tomato", market="Bilaspur", days=40):
    today = dt.date.today()
    for i in range(days, -1, -1):
        p = 2200.0 + 10 * (days - i)
        db.add(models.MarketPrice(crop=crop, market=market, date=(today - dt.timedelta(days=i)).isoformat(),
                                  min_price=p - 50, max_price=p + 50, modal_price=p, data_source="live"))
    db.commit()


def test_forecast_from_live_history(db, art_dir, monkeypatch):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    _seed_live(db)
    out = r.ml_forecast("Tomato", "Bilaspur", False, db)
    assert out["available"] is True and out["history_source"] == "live_db" and out["is_historical_replay"] is False
    fc = out["forecast"]
    assert fc["horizon_days"] == 7 and fc["unit"].startswith("INR per quintal")
    assert fc["predicted_price_low"] <= fc["predicted_price"] <= fc["predicted_price_high"]


def test_no_live_history_is_unavailable_not_invented(db, art_dir, monkeypatch):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    out = r.ml_forecast("Tomato", "Raipur", False, db)
    assert out["available"] is False and out["reason"] == "insufficient_history"


def test_unknown_crop_404_and_missing_artifacts(db, tmp_path, monkeypatch):
    with pytest.raises(HTTPException) as e:
        r.ml_forecast("Dragonfruit", "Bilaspur", False, db)
    assert e.value.status_code == 404
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(tmp_path / "none"))
    out = r.ml_forecast("Tomato", "Bilaspur", False, db)
    assert out["available"] is False and out["reason"] == "artifacts_missing"
    assert r.ml_status()["available"] is False


def test_compare_reuses_existing_logic_and_adds_forecast(db, art_dir, monkeypatch):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    _seed_live(db, market="Bilaspur")
    fake = {"crop": "Tomato", "quantity_kg": 1000.0, "location": "Bilaspur", "recommended_market": "Raipur",
            "insufficient_data": False, "options": [
                {"market": "Bilaspur", "distance_km": 5.0, "modal_price_per_kg": 22.0, "net_profit": 1.0},
                {"market": "Raipur", "distance_km": 110.0, "modal_price_per_kg": 23.0, "net_profit": 2.0}]}
    monkeypatch.setattr(market_router, "_compare_markets_core", lambda *a, **k: fake)
    out = r.ml_compare("Tomato", 1000.0, "Bilaspur", 6, False, db)
    assert out["recommended_market"] == "Raipur"                      # existing logic untouched
    by = {o["market"]: o for o in out["options"]}
    assert by["Bilaspur"]["ml_forecast"]["available"] and "forecast_net_profit" in by["Bilaspur"]
    assert by["Raipur"]["ml_forecast"]["available"] is False and "forecast_net_profit" not in by["Raipur"]
    assert out["forecast_coverage"] == "1 of 2 markets"
    assert out["forecast_recommended_market"] == "Bilaspur"


def test_analysis_endpoint(art_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    out = r.ml_analysis()
    assert out["available"] is True and out["horizon_days"] == 7
    assert out["overall"]["test"]["model"]["mae"] > 0 and "baseline_persistence" in out["overall"]["test"]
    st = r.ml_status()
    assert st["available"] is True and st["model_family"] and st["interval"]["nominal"] == 0.8

    import shutil
    partial = tmp_path / "partial"
    shutil.copytree(art_dir, partial)
    (partial / "analysis.json").unlink()
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(partial))
    assert r.ml_analysis() == {"available": False, "reason": "analysis_missing",
                               "message": "analysis.json not found; retrain with scripts/train_price_forecast.py"}
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(tmp_path / "none"))
    assert r.ml_analysis()["reason"] == "artifacts_missing"


def test_past_prices_endpoint_uses_live_rows_only(db):
    from app.routers import past_prices as pr
    db.add(models.MarketPrice(crop="Onion", market="Pune", date="2026-10-17", min_price=1000, max_price=2000,
                              modal_price=1500, data_source="demo"))
    db.add(models.MarketPrice(crop="Onion", market="Pune", date="2026-10-18", min_price=1000, max_price=2000,
                              modal_price=1700, data_source="live"))
    db.commit()
    out = pr.get_past_prices(crop="Onion", market="Pune", days=None, db=db)
    dates = [p["date"] for p in out["points"]]
    assert "2026-10-17" not in dates and dates[-1] == "2026-10-18"
    assert out["summary"]["latest"]["source"] == "live"
    assert pr.get_past_prices(crop="Onion", market="Nowhere", days=None, db=db)["available"] is False


def test_state_forecast_endpoint(tmp_path, monkeypatch):
    import numpy as np
    import pandas as pd
    from app.services import past_prices
    from scripts import train_state_forecast as S
    rng = np.random.default_rng(1)
    days = pd.date_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=2), periods=500)
    rows = []
    for crop, base in (("Onion", 2000.0), ("Potato", 1200.0)):
        p = base * np.exp(np.cumsum(rng.normal(0, 0.02, len(days))))
        rows += [{"state": "Maharashtra", "crop": crop, "date": d.date().isoformat(), "modal": float(v),
                  "arrival_tonnes": 10.0, "source": "x"} for d, v in zip(days, p)]
    csv = tmp_path / "state.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    out = tmp_path / "art"
    T.train_from_frame(S.state_frame(csv), out, max_iter=30, min_train_rows=200, min_leaf=20, min_heldout_rows=1)
    monkeypatch.setenv("PRICE_FORECAST_STATE_ARTIFACT_DIR", str(out))
    monkeypatch.setattr(past_prices, "_state_series", lambda: {
        (r["crop"], r["state"]): {} for r in rows} | {
        k: {x["date"]: {"date": x["date"], "modal": x["modal"]} for x in rows if (x["crop"], x["state"]) == k}
        for k in {(r["crop"], r["state"]) for r in rows}})
    res = r.ml_state_forecast(crop="Onion", state="Maharashtra")
    assert res["available"] is True and res["data_age_days"] == 2
    f = res["forecast"]
    assert f["predicted_price_low"] <= f["predicted_price"] <= f["predicted_price_high"]
    assert "historical_replay" not in " ".join(f["warnings"])
    assert res["model"]["this_crop_test"]["rows"] > 0
    assert r.ml_state_forecast(crop="Wheat", state="Maharashtra")["reason"] == "no_state_history"
    # data that is too old is refused, not forecast
    monkeypatch.setattr(r, "STATE_MAX_AGE_DAYS", 1)
    assert r.ml_state_forecast(crop="Onion", state="Maharashtra")["reason"] == "stale_history"


def test_no_live_history_falls_back_to_labelled_replay(db, art_dir, monkeypatch):
    """Insufficient live history + a covered snapshot -> real prediction, clearly flagged as replay."""
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    out = r.ml_forecast("Tomato", "Bilaspur", False, db)   # no live rows seeded; include_snapshot not needed
    assert out["available"] is True
    assert out["history_source"] == "training_snapshot" and out["is_historical_replay"] is True
    assert out["data_status"] == "historical_replay" and "NOT a current market forecast" in out["data_status_note"]
    assert any("historical_replay" in w for w in out["forecast"]["warnings"])
    assert out["forecast"]["history_age_days"] > 3


def test_stale_live_history_falls_back_to_labelled_replay(db, art_dir, monkeypatch):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    today = dt.date.today()
    for i in range(60, 40, -1):  # live rows exist but newest is ~40 days old
        db.add(models.MarketPrice(crop="Tomato", market="Bilaspur", date=(today - dt.timedelta(days=i)).isoformat(),
                                  min_price=2150, max_price=2250, modal_price=2200, data_source="live"))
    db.commit()
    out = r.ml_forecast("Tomato", "Bilaspur", False, db)
    assert out["available"] is True and out["is_historical_replay"] is True


def test_fresh_live_history_is_never_labelled_replay(db, art_dir, monkeypatch):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    _seed_live(db)
    out = r.ml_forecast("Tomato", "Bilaspur", False, db)
    assert out["data_status"] == "live" and out["data_status_note"] is None


def test_no_snapshot_for_market_stays_unavailable(db, art_dir, monkeypatch):
    monkeypatch.setenv("PRICE_FORECAST_ARTIFACT_DIR", str(art_dir))
    out = r.ml_forecast("Tomato", "Nowhereville", False, db)
    assert out["available"] is False and out["reason"] == "insufficient_history"
