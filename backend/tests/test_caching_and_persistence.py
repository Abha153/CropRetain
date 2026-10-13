"""
- Item 1: agmarknet_service.fetch_price() must not repeatedly hit CEDA's
  price endpoint for the same (crop, market, state, district) within its
  TTL, and a failure must never be cached as if it were a successful
  price.
- Item 8: _record_live_snapshot must persist `source` and
  `source_timestamp` on MarketPrice rows, and must never mark a demo/
  fallback row as data_source="live".
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import agmarknet_service
from app.routers import market as market_router


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Item 1: agmarknet_service price-level caching
# ---------------------------------------------------------------------------

def _stub_resolve_ids(monkeypatch, commodity_id=1, state_id=1, district_id=1):
    monkeypatch.setattr(agmarknet_service, "_resolve_ids", lambda *a, **k: (commodity_id, state_id, district_id))


def test_repeated_fetch_price_calls_do_not_repeat_network_requests(monkeypatch):
    """Two calls for the same crop/market/state/district within the TTL
    window must only hit CEDA's price+quantity endpoints once."""
    agmarknet_service._cache.clear()
    agmarknet_service._failure_cache.clear()
    _stub_resolve_ids(monkeypatch)

    calls = {"get_markets": 0, "get_prices": 0, "get_quantities": 0}
    monkeypatch.setattr(agmarknet_service, "get_markets", lambda *a, **k: (calls.__setitem__("get_markets", calls["get_markets"] + 1), [{"market_id": 7, "market_name": "Bilaspur"}])[1])
    monkeypatch.setattr(agmarknet_service, "get_prices", lambda *a, **k: (calls.__setitem__("get_prices", calls["get_prices"] + 1), [{"market_id": 7, "date": "2026-08-26", "modal_price": 3500, "min_price": 3300, "max_price": 3700}])[1])
    monkeypatch.setattr(agmarknet_service, "get_quantities", lambda *a, **k: (calls.__setitem__("get_quantities", calls["get_quantities"] + 1), [{"market_id": 7, "quantity": 12.5}])[1])

    r1 = agmarknet_service.fetch_price("Tomato", "Bilaspur", "Chhattisgarh", "Bilaspur")
    r2 = agmarknet_service.fetch_price("Tomato", "Bilaspur", "Chhattisgarh", "Bilaspur")

    assert r1["status"] == "ok" and r2["status"] == "ok"
    assert r1["data"]["modal_price"] == r2["data"]["modal_price"] == 3500
    # Only the FIRST call should have actually hit the network functions.
    assert calls["get_markets"] == 1
    assert calls["get_prices"] == 1
    assert calls["get_quantities"] == 1


def test_failed_price_fetch_is_not_cached_as_success(monkeypatch):
    """A CEDA failure must never be served back as a successful "ok"
    result on a subsequent call -- it's cached as a failure (so repeated
    calls fail fast), never as fake success data."""
    agmarknet_service._cache.clear()
    agmarknet_service._failure_cache.clear()
    _stub_resolve_ids(monkeypatch)

    def _boom(*a, **k):
        raise agmarknet_service.AgmarknetError("simulated CEDA failure")

    monkeypatch.setattr(agmarknet_service, "get_markets", _boom)

    with pytest.raises(agmarknet_service.AgmarknetError):
        agmarknet_service.fetch_price("Tomato", "Bilaspur", "Chhattisgarh", "Bilaspur")
    # Second call within the failure-cache window must ALSO raise -- never
    # silently return a fabricated "ok" price.
    with pytest.raises(agmarknet_service.AgmarknetError):
        agmarknet_service.fetch_price("Tomato", "Bilaspur", "Chhattisgarh", "Bilaspur")


def test_cached_price_expires_after_ttl(monkeypatch):
    """Stale cached data must not be served forever -- once the TTL
    elapses, a fresh network call happens again."""
    agmarknet_service._cache.clear()
    agmarknet_service._failure_cache.clear()
    _stub_resolve_ids(monkeypatch)

    calls = {"n": 0}

    def _get_prices(*a, **k):
        calls["n"] += 1
        return [{"market_id": 7, "date": "2026-08-26", "modal_price": 3500, "min_price": 3300, "max_price": 3700}]

    monkeypatch.setattr(agmarknet_service, "get_markets", lambda *a, **k: [{"market_id": 7, "market_name": "Bilaspur"}])
    monkeypatch.setattr(agmarknet_service, "get_prices", _get_prices)
    monkeypatch.setattr(agmarknet_service, "get_quantities", lambda *a, **k: [])

    agmarknet_service.fetch_price("Tomato", "Bilaspur", "Chhattisgarh", "Bilaspur")
    assert calls["n"] == 1

    # Force the cached entry to look expired without waiting 10 minutes.
    import datetime as dt
    key = "price:Tomato|Bilaspur|Chhattisgarh|Bilaspur"
    expires_at, value = agmarknet_service._cache[key]
    agmarknet_service._cache[key] = (dt.datetime.utcnow() - dt.timedelta(seconds=1), value)

    agmarknet_service.fetch_price("Tomato", "Bilaspur", "Chhattisgarh", "Bilaspur")
    assert calls["n"] == 2, "expired cache entry should trigger a fresh fetch"


# ---------------------------------------------------------------------------
# Item 8: historical persistence -- source / source_timestamp / data_source
# ---------------------------------------------------------------------------

def test_live_snapshot_persists_source_and_source_timestamp(db):
    live = {
        "modal_price": 3500.0, "min_price": 3300.0, "max_price": 3700.0,
        "date": "26/08/2026", "sources": ["data.gov.in", "agmarknet"],
        "fetched_at": "2026-08-26T00:05:00Z", "source_resource": "market",
    }
    market_router._record_live_snapshot(db, "Tomato", "Bilaspur", live)

    row = db.query(models.MarketPrice).filter_by(crop="Tomato", market="Bilaspur").first()
    assert row is not None
    assert row.data_source == "live"
    assert row.source == "data.gov.in+agmarknet"
    assert row.source_timestamp == "2026-08-26T00:05:00Z"


def test_single_source_live_snapshot_records_that_one_source(db):
    live = {
        "modal_price": 3500.0, "min_price": 3300.0, "max_price": 3700.0,
        "date": "26/08/2026", "sources": ["agmarknet"],
        "fetched_at": "2026-08-26T00:05:00Z", "source_resource": "market",
    }
    market_router._record_live_snapshot(db, "Tomato", "Bilaspur", live)

    row = db.query(models.MarketPrice).filter_by(crop="Tomato", market="Bilaspur").first()
    assert row.source == "agmarknet"
    assert row.data_source == "live"


def test_demo_seed_rows_never_get_a_source_label(db):
    """Seeded/demo rows must stay unambiguously data_source="demo" with
    no `source` value -- they must never be mistaken for a live fetch."""
    db.add(models.MarketPrice(
        crop="Tomato", market="Bilaspur", date="2026-08-20",
        min_price=3000.0, max_price=3200.0, modal_price=3100.0,
        arrivals_tonnes=10.0, data_source="demo",
    ))
    db.commit()
    row = db.query(models.MarketPrice).filter_by(crop="Tomato", market="Bilaspur").first()
    assert row.data_source == "demo"
    assert row.source is None
    assert row.source_timestamp is None


def test_live_snapshot_upsert_updates_source_on_repeat_fetch(db):
    """Re-fetching the same day's data (e.g. cache expiring and being
    re-hit, possibly from a DIFFERENT combination of sources this time)
    must update `source`/`source_timestamp` on the existing row, not
    leave stale attribution behind."""
    first = {
        "modal_price": 3500.0, "min_price": 3300.0, "max_price": 3700.0,
        "date": "26/08/2026", "sources": ["data.gov.in"],
        "fetched_at": "2026-08-26T00:05:00Z", "source_resource": "market",
    }
    market_router._record_live_snapshot(db, "Tomato", "Bilaspur", first)

    second = {
        "modal_price": 3510.0, "min_price": 3310.0, "max_price": 3710.0,
        "date": "26/08/2026", "sources": ["data.gov.in", "agmarknet"],
        "fetched_at": "2026-08-26T00:15:00Z", "source_resource": "market",
    }
    market_router._record_live_snapshot(db, "Tomato", "Bilaspur", second)

    rows = db.query(models.MarketPrice).filter_by(crop="Tomato", market="Bilaspur").all()
    assert len(rows) == 1, "must upsert, not duplicate, the same (crop, market, date) row"
    assert rows[0].source == "data.gov.in+agmarknet"
    assert rows[0].modal_price == 3510.0
