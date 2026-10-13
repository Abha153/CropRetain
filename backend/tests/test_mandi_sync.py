"""
Phase 3 (official mandi-data sync) + Phase 4 (timestamp/freshness) tests.

No network: `live_market_data.fetch_live_price_status` and market discovery
are monkeypatched to controlled provider outcomes.

The properties under test are the honesty-critical ones:
  - a live sync writes data_source="live" rows and never touches demo rows
  - observed_at comes from the PROVIDER; fetched_at comes from CropRetain;
    they are not the same value
  - a record with no provider observation date is skipped, not back-dated
  - a failed sync preserves the previous last_successful_sync
  - "no records" and "provider error" are reported as different statuses
"""
import sys
import os
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import mandi_sync, live_market_data, mandi_directory


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _provider_ok(modal=2450.0, arrival_date="15/09/2026", quantity=None):
    return {
        "status": "ok",
        "result": {
            "crop": "Tomato", "market": "Pune", "state": "Maharashtra",
            "arrival_date": arrival_date, "modal_price": modal,
            "min_price": modal - 150, "max_price": modal + 150,
            "quantity": quantity, "fetched_at": "2026-09-15T09:00:00Z",
        },
    }


def _configure(monkeypatch, outcome, markets=("Pune",)):
    monkeypatch.setattr(live_market_data, "is_configured", lambda: True)
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: outcome)
    monkeypatch.setattr(mandi_directory, "discover_state_markets", lambda *a, **k: list(markets))


def test_sync_persists_live_rows_with_distinct_observed_and_fetched_timestamps(db, monkeypatch):
    _configure(monkeypatch, _provider_ok())

    result = mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    assert result["status"] == "ok"
    assert result["records_synced"] == 1

    row = db.query(models.MarketPrice).filter_by(data_source="live").one()
    assert row.source == "data.gov.in"
    # observed_at is the provider's own reported date, stored verbatim.
    assert row.observed_at == "15/09/2026"
    # fetched_at is CropRetain's own server clock -- a real datetime, and
    # explicitly NOT the same value/format as the provider's observation date.
    assert isinstance(row.fetched_at, dt.datetime)
    assert str(row.observed_at) != str(row.fetched_at)


def test_sync_never_invents_an_observation_date(db, monkeypatch):
    """A provider record with no arrival_date cannot be honestly placed in
    time, so it is skipped -- never stamped with today's date."""
    _configure(monkeypatch, _provider_ok(arrival_date=None))

    result = mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    assert result["records_synced"] == 0
    assert db.query(models.MarketPrice).count() == 0


def test_sync_does_not_fabricate_arrival_volume(db, monkeypatch):
    """No arrival volume from the provider must stay NULL, not become 0.0 --
    a fabricated zero is indistinguishable from a real zero-arrival day."""
    _configure(monkeypatch, _provider_ok(quantity=None))

    mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    row = db.query(models.MarketPrice).filter_by(data_source="live").one()
    assert row.arrivals_tonnes is None


def test_sync_never_overwrites_a_demo_row(db, monkeypatch):
    """Live and demo rows for the same crop/market/date must coexist and stay
    separately identifiable -- the live sync must not rewrite demo history."""
    db.add(models.MarketPrice(
        crop="Tomato", market="Pune", date="15/09/2026",
        min_price=1.0, max_price=2.0, modal_price=1.5,
        arrivals_tonnes=5.0, data_source="demo",
    ))
    db.commit()

    _configure(monkeypatch, _provider_ok(modal=2450.0))
    mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    demo = db.query(models.MarketPrice).filter_by(data_source="demo").one()
    live = db.query(models.MarketPrice).filter_by(data_source="live").one()
    assert demo.modal_price == 1.5, "demo row must be untouched"
    assert demo.source is None
    assert live.modal_price == 2450.0
    assert live.source == "data.gov.in"


def test_resync_updates_in_place_instead_of_duplicating(db, monkeypatch):
    _configure(monkeypatch, _provider_ok(modal=2450.0))
    mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    _configure(monkeypatch, _provider_ok(modal=2600.0))
    mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    rows = db.query(models.MarketPrice).filter_by(data_source="live").all()
    assert len(rows) == 1, "same crop/market/observation-date must upsert"
    assert rows[0].modal_price == 2600.0


def test_failed_sync_preserves_previous_last_successful_sync(db, monkeypatch):
    """A stale-but-known state must stay distinguishable from a fresh one:
    a later failure must not erase the fact that we once had good data."""
    _configure(monkeypatch, _provider_ok())
    first = mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])
    good_sync = first["last_successful_sync"]
    assert good_sync is not None

    _configure(monkeypatch, {"status": "error", "result": None})
    second = mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    assert second["status"] == "error"
    assert second["records_synced"] == 0
    assert second["last_successful_sync"] == good_sync, "must not be cleared by a failure"

    fresh = mandi_sync.freshness(db)
    assert fresh["status"] == "stale"
    assert fresh["last_successful_sync"] == good_sync
    assert fresh["last_error"]


def test_no_records_is_distinct_from_provider_error(db, monkeypatch):
    """Provider responded fine but has nothing for this state -- a real
    answer, not a failure."""
    _configure(monkeypatch, {"status": "no_records", "result": None})

    result = mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    assert result["status"] == "no_records"
    assert result["records_synced"] == 0


def test_unconfigured_provider_reports_not_configured_and_attempts_nothing(db, monkeypatch):
    monkeypatch.setattr(live_market_data, "is_configured", lambda: False)
    called = {"n": 0}

    def _should_not_run(*a, **k):
        called["n"] += 1
        return _provider_ok()

    monkeypatch.setattr(live_market_data, "fetch_live_price_status", _should_not_run)

    result = mandi_sync.sync_state(db, state="Maharashtra", crops=["Tomato"])

    assert result["status"] == "not_configured"
    assert called["n"] == 0, "must not hit the provider with no key configured"


def test_freshness_reports_never_synced_before_any_sync(db):
    fresh = mandi_sync.freshness(db)
    assert fresh["status"] == "never_synced"
    assert fresh["last_successful_sync"] is None
