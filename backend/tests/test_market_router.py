"""
Unit tests for app/routers/market.py's _get_price(), covering the
fallback rules (updated per an explicit product decision: the dashboard
must never go blank or show a dead end -- live data is still always tried
and preferred first, but EVERY non-"ok" outcome now falls back to seeded
demo data when it exists):
  - "no_records" (live API confirmed no record for this exact selection)
    now falls back to demo data, clearly tagged, instead of showing nothing.
  - "error" / "not_configured" fall back to demo data when seeded (as before).
  - live mode (MARKET_DATA_SOURCE=live) no longer suppresses the demo
    fallback on "error"/"not_configured" -- it now behaves the same as
    demo mode for fallback purposes.
  - only when NOTHING is seeded for a crop/market pair at all does the
    genuine "unavailable" (data_source=None) outcome remain.
  - only a genuine mandi-level ("market") hit gets persisted into the
    historical MarketPrice series -- a district-level aggregate must not
    be silently blended into that same per-market history.

Uses an isolated in-memory SQLite database (not the real cropwise.db) and
monkeypatches mandi_directory.fetch_price_result directly, so no network
calls happen and no other test's data can leak in.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.routers import market as market_router
from app.services import mandi_directory
from app.config import settings


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_demo_row(db, crop="Tomato", market="Bilaspur"):
    db.add(models.MarketPrice(
        crop=crop, market=market, date="2026-08-20",
        min_price=3200.0, max_price=3600.0, modal_price=3400.0,
        arrivals_tonnes=50.0, data_source="demo",
    ))
    db.commit()


def test_ok_market_level_persists_history_and_labels_live(db, monkeypatch):
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "ok",
        "data": {
            "modal_price": 3500.0, "min_price": 3300.0, "max_price": 3700.0,
            "arrival_date": "26/08/2026", "matched_market_name": "Bilaspur",
            "variety": "Local", "grade": "FAQ", "fetched_at": "2026-08-26T00:00:00Z",
            "source_resource": "market",
        },
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "ok"
    assert result["data_source"] == "live"
    assert result["source_resource"] == "market"

    persisted = db.query(models.MarketPrice).filter_by(
        crop="Tomato", market="Bilaspur", data_source="live",
    ).all()
    assert len(persisted) == 1
    assert persisted[0].modal_price == 3500.0


def test_ok_district_variety_does_not_pollute_market_history(db, monkeypatch):
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "ok",
        "data": {
            "modal_price": 3400.0, "min_price": 3200.0, "max_price": 3600.0,
            "arrival_date": "26/08/2026", "matched_market_name": "Bilaspur (district)",
            "varieties": [{"variety": "Local", "modal_price": 3400.0}],
            "fetched_at": "2026-08-26T00:00:00Z",
            "source_resource": "district_variety",
            "district_reference_note": (
                "Calculated from available variety-level government records; "
                "this is not a specific mandi modal price."
            ),
        },
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "ok"
    assert result["source_resource"] == "district_variety"
    assert "not a specific mandi modal price" in result["district_reference_note"]

    # The critical assertion: a district-aggregate value must never be
    # silently written into the per-market historical price series.
    persisted = db.query(models.MarketPrice).filter_by(crop="Tomato", market="Bilaspur").all()
    assert len(persisted) == 0


def test_no_records_now_falls_back_to_demo_when_seeded(db, monkeypatch):
    _seed_demo_row(db)  # demo data IS available for this market
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "no_records", "data": None,
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "demo_fallback"
    assert result["data_source"] == "demo"  # dashboard must never go blank
    assert result["fallback_reason"] == "no_records"
    assert "no official government record" in result["message"].lower()


def test_error_falls_back_to_demo_when_seeded(db, monkeypatch):
    _seed_demo_row(db)
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "error", "data": None,
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "demo_fallback"
    assert result["data_source"] == "demo"
    assert result["fallback_reason"] == "error"


def test_not_configured_falls_back_to_demo_without_unavailable_framing(db, monkeypatch):
    _seed_demo_row(db)
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "not_configured", "data": None,
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "demo_fallback"
    assert result["data_source"] == "demo"
    assert "unavailable" not in result["message"].lower()


def test_live_mode_without_key_still_falls_back_to_demo(db, monkeypatch):
    # Product decision: live mode no longer suppresses the demo fallback --
    # the dashboard must always show something useful, clearly badged DEMO,
    # rather than a dead "configuration required" end state.
    _seed_demo_row(db)
    monkeypatch.setattr(settings, "market_data_source", "live")
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "not_configured", "data": None,
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "demo_fallback"
    assert result["data_source"] == "demo"
    assert result["fallback_reason"] == "not_configured"


def test_live_mode_api_failure_also_falls_back_to_demo(db, monkeypatch):
    _seed_demo_row(db)
    monkeypatch.setattr(settings, "market_data_source", "live")
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "error", "data": None,
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "demo_fallback"
    assert result["data_source"] == "demo"
    assert result["fallback_reason"] == "error"


def test_genuinely_nothing_seeded_still_reports_unavailable(db, monkeypatch):
    # The one case that must still surface honestly: no live record AND
    # nothing seeded for this crop/market pair at all (no _seed_demo_row
    # call here -- deliberately nothing in the DB for this pair).
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "error", "data": None,
    })

    result = market_router._get_price(db, "Tomato", "Bilaspur")

    assert result["status"] == "unavailable"
    assert result["data_source"] is None


def test_compare_markets_pads_to_at_least_three_options_via_demo_fallback(db, monkeypatch):
    # Simulate the exact reported bug: live mode confirms no_records for
    # every market. Demo data is only actually seeded (via _seed_demo_row)
    # for one crop/market pair, but generate_all_history() in the real app
    # seeds every crop x market combination -- this test just confirms the
    # padding loop itself keeps trying further markets until it hits 3 (or
    # genuinely runs out), rather than stopping at whatever top_n=6
    # produced.
    for market_name in ("Bilaspur", "Raipur", "Durg", "Raigarh"):
        _seed_demo_row(db, crop="Tomato", market=market_name)
    monkeypatch.setattr(mandi_directory, "fetch_price_result", lambda crop, market, **k: {
        "status": "no_records", "data": None,
    })

    result = market_router.compare_markets(crop="Tomato", quantity_kg=1000, location="Raigarh", top_n=1, db=db)

    assert result["insufficient_data"] is False
    assert len(result["options"]) >= 3
    assert result["data_source_summary"] == "demo"
    assert all(o["data_source"] == "demo" for o in result["options"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
