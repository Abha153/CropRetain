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
    T.train_from_frame(_synthetic_frame(), out, max_iter=30, min_train_rows=200, min_leaf=20)
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
