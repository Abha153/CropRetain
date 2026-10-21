"""
Router-level checks for the Tomato / Bilaspur inconsistency (statewide history exists, no market-level
forecast). Uses an isolated in-memory SQLite DB and the real shipped data/artifacts.
Skipped automatically when the API deps or ML deps are not installed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("sklearn")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.routers import forecast as stat_router
from app.routers import price_forecast_ml as r


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def test_trend_forecast_unavailable_reports_reason_and_counts(db):
    out = stat_router.get_forecast("Tomato", "Bilaspur", include_demo=False, db=db)
    assert out["available"] is False and out["reason"] == "insufficient_live_history"
    assert out["live_points"] == 0 and out["min_live_points"] == stat_router.MIN_REAL_POINTS_FOR_FORECAST
    assert "Historical mandi data is currently unavailable" not in out["message"]


def test_demo_requested_but_no_demo_series_is_labelled_not_faked(db):
    out = stat_router.get_forecast("Tomato", "Bilaspur", include_demo=True, db=db)
    assert out["available"] is False and out["is_demo"] is True and out["reason"] == "no_demo_data"


def test_availability_separates_statewide_history_from_market_forecast(db):
    out = r.ml_availability("Tomato", "Bilaspur", db)
    assert out["recorded_history"]["state"]["available"] is True        # statewide history exists...
    assert out["live_history"]["sufficient"] is False                    # ...live market history does not...
    assert out["market_ml"]["status"] == "unsupported_crop"              # ...and the market model refuses Tomato
    # the statewide model is judged on its own data freshness, independently of the market model
    assert out["state_ml"]["status"] in ("available", "stale_history")


def test_backend_fault_is_reported_as_service_error_not_no_data(db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("model exploded")
    monkeypatch.setattr(r, "_forecast_one", boom)
    out = r.ml_availability("Tomato", "Bilaspur", db)
    assert out["market_ml"]["status"] == "service_error"


def test_unknown_crop_is_404(db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        r.ml_availability("Dragonfruit", "Bilaspur", db)
    assert e.value.status_code == 404
