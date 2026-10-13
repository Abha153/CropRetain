"""
Regression tests for the compare_markets()/_admin/impact performance fixes:

  - compare_markets() fetches each candidate market's network outcome
    concurrently, not one-at-a-time -- a slow/unreachable provider must
    cost roughly one call's worth of latency, not (markets x latency).
  - _compare_markets_core()'s optional `outcome_cache` lets a caller that
    makes many compare_markets-equivalent calls in one request (currently
    only admin.py's impact dashboard) reuse an already-fetched (crop,
    market) network result instead of re-fetching it.
  - a failed/slow provider must never be cached or reported as a
    successful ("live") result -- only genuine successes are reused.
  - /admin/impact must not repeat the same (crop, market) network lookup
    once per listing when several sampled listings share a crop/location.

Uses an isolated in-memory SQLite database and monkeypatches
mandi_directory.fetch_price_result directly, so no real network calls
happen in this suite.
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base, get_db
from app.routers import market as market_router
from app.services import mandi_directory
from app.auth_utils import require_admin
from app.main import app


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_demo_row(db, crop, market):
    db.add(models.MarketPrice(
        crop=crop, market=market, date="2026-08-20",
        min_price=1000.0, max_price=1200.0, modal_price=1100.0,
        arrivals_tonnes=10.0, data_source="demo",
    ))
    db.commit()


def test_compare_markets_fetches_candidate_markets_concurrently(db, monkeypatch):
    """6 markets each taking 0.2s over the network should take close to
    0.2s total, not 1.2s -- proves the fetch is concurrent, not a
    sequential for-loop."""
    from app.mock_data.locations import MARKETS
    for m in MARKETS[:6]:
        _seed_demo_row(db, "Wheat", m["name"])

    def slow(crop, market, **k):
        time.sleep(0.2)
        return {"status": "error", "data": None}

    monkeypatch.setattr(mandi_directory, "fetch_price_result", slow)

    start = time.monotonic()
    result = market_router._compare_markets_core(
        crop="Wheat", quantity_kg=500, location=MARKETS[0]["name"], top_n=6, db=db,
    )
    elapsed = time.monotonic() - start

    assert len(result["options"]) > 0
    # Sequential would be ~1.2s (6 x 0.2s); concurrent should be well under half that.
    assert elapsed < 0.6, f"expected concurrent fetch, took {elapsed:.2f}s for 6x0.2s calls"


def test_outcome_cache_deduplicates_identical_crop_market_lookups(db, monkeypatch):
    """Two compare_markets-equivalent calls sharing the same crop and
    candidate markets, given the same outcome_cache dict, must only hit
    the network once per distinct (crop, market) pair -- not once per
    call. This is exactly the admin /impact dashboard's access pattern
    across its sampled listings."""
    from app.mock_data.locations import MARKETS
    for m in MARKETS[:6]:
        _seed_demo_row(db, "Wheat", m["name"])

    call_count = {"n": 0}

    def counting_fetch(crop, market, **k):
        call_count["n"] += 1
        return {"status": "error", "data": None}

    monkeypatch.setattr(mandi_directory, "fetch_price_result", counting_fetch)

    shared_cache = {}
    for _ in range(5):  # simulate 5 listings all requesting the same crop/location
        market_router._compare_markets_core(
            crop="Wheat", quantity_kg=500, location=MARKETS[0]["name"], top_n=6,
            db=db, outcome_cache=shared_cache,
        )

    # 6 distinct markets were looked up once each, regardless of 5 repeated calls.
    assert call_count["n"] == 6, f"expected 6 distinct network calls, got {call_count['n']}"


def test_outcome_cache_is_not_shared_across_compare_markets_calls_by_default(db, monkeypatch):
    """A caller that does NOT pass outcome_cache (i.e. every normal
    Best Selling Option / AI Advisor request) must NOT silently reuse
    another request's cached network result -- outcome_cache is opt-in
    per-call, not a hidden global."""
    from app.mock_data.locations import MARKETS
    for m in MARKETS[:6]:
        _seed_demo_row(db, "Wheat", m["name"])

    call_count = {"n": 0}

    def counting_fetch(crop, market, **k):
        call_count["n"] += 1
        return {"status": "error", "data": None}

    monkeypatch.setattr(mandi_directory, "fetch_price_result", counting_fetch)

    market_router._compare_markets_core(
        crop="Wheat", quantity_kg=500, location=MARKETS[0]["name"], top_n=6, db=db,
    )
    market_router._compare_markets_core(
        crop="Wheat", quantity_kg=500, location=MARKETS[0]["name"], top_n=6, db=db,
    )

    # No shared cache passed -> each call re-fetches its own 6 markets: 12 total.
    assert call_count["n"] == 12


def test_cached_outcome_preserves_failure_status_never_becomes_fake_success(db, monkeypatch):
    """A cached network outcome must round-trip its real status -- a
    provider failure reused from outcome_cache must still resolve to the
    demo fallback (data_source="demo"), never get relabeled as "live"."""
    from app.mock_data.locations import MARKETS
    market_name = MARKETS[0]["name"]
    _seed_demo_row(db, "Wheat", market_name)

    def always_error(crop, market, **k):
        return {"status": "error", "data": None}

    monkeypatch.setattr(mandi_directory, "fetch_price_result", always_error)

    shared_cache = {}
    outcome = market_router._fetch_price_outcome("Wheat", market_name)
    shared_cache[("Wheat", market_name)] = outcome

    # Resolve twice from the same cached (failed) outcome.
    for _ in range(2):
        resolved = market_router._resolve_price(db, "Wheat", market_name, shared_cache[("Wheat", market_name)])
        assert resolved["data_source"] == "demo"
        assert resolved["status"] == "demo_fallback"


def test_admin_impact_dashboard_reuses_cache_across_shared_listings():
    """End-to-end: seed several listings that all share crop/location, hit
    /admin/impact, and confirm the number of distinct network lookups
    stays bounded to the distinct (crop, market) pairs actually needed --
    not one full set of lookups per listing."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}

    db = TestingSessionLocal()
    from app.mock_data.locations import MARKETS
    for m in MARKETS[:6]:
        _seed_demo_row(db, "Wheat", m["name"])
    farmer = models.Farmer(
        name="F", email="f@test.com", password_hash="x", location=MARKETS[0]["name"],
    )
    db.add(farmer)
    db.commit()
    # 10 listings, all same crop + location -> should share the same 6-market lookup set.
    import datetime as _dt
    for i in range(10):
        db.add(models.CropListing(
            farmer_id=farmer.id, crop="Wheat", quantity_kg=100, location=MARKETS[0]["name"],
            expected_price_per_kg=10.0, status="ACTIVE", available_date=_dt.date.today(),
        ))
    db.commit()
    db.close()

    call_count = {"n": 0}

    def counting_fetch(crop, market, **k):
        call_count["n"] += 1
        return {"status": "error", "data": None}

    import app.services.mandi_directory as mandi_directory_mod
    original = mandi_directory_mod.fetch_price_result
    mandi_directory_mod.fetch_price_result = counting_fetch
    try:
        client = TestClient(app)
        resp = client.get("/admin/impact")
        assert resp.status_code == 200
    finally:
        mandi_directory_mod.fetch_price_result = original
        app.dependency_overrides.clear()

    # 10 listings sharing one crop/location against 6 nearby markets should
    # cost ~6 network calls total, not 10 x 6 = 60.
    assert call_count["n"] <= 6 + 6, f"expected lookups bounded by distinct markets, got {call_count['n']}"
