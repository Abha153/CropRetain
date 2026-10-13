"""
Unit tests for the honesty-critical data-source logic in
app/services/mandi_directory.py and app/routers/market.py's _get_price().

These tests do NOT touch the network -- every live_market_data /
district_market_data call is monkeypatched to a controlled outcome, and
the optional Agmarknet provider is disabled, so they verify the
STATUS-ROUTING LOGIC (ok / no_records / error / not_configured -> correct
label / correct fallback-or-not) rather than any external API behavior.

Run with: pytest backend/tests/test_mandi_directory.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.services import (
    mandi_directory, live_market_data, district_market_data, agmarknet_service,
)


MARKET_OK = {
    "status": "ok",
    "result": {
        "source": "live", "provider": "data.gov.in (Agmarknet)",
        "crop": "Tomato", "market": "Bilaspur", "state": "Chhattisgarh",
        "arrival_date": "26/08/2026", "modal_price": 3500.0,
        "min_price": 3300.0, "max_price": 3700.0,
        "variety": "Local", "grade": "FAQ", "fetched_at": "2026-08-26T00:00:00Z",
    },
}
DISTRICT_OK = {
    "status": "ok",
    "result": {
        "source": "live", "provider": "data.gov.in (Variety-wise Daily Market Prices)",
        "crop": "Tomato", "district": "Bilaspur", "state": "Chhattisgarh",
        "arrival_date": "26/08/2026", "modal_price": 3400.0,
        "min_price": 3200.0, "max_price": 3600.0,
        "varieties": [{"variety": "Local", "grade": "FAQ",
                        "min_price": 3200.0, "max_price": 3600.0, "modal_price": 3400.0,
                        "market": "Bilaspur", "commodity_code": "78"}],
        "fetched_at": "2026-08-26T00:00:00Z",
    },
}
NO_RECORDS = {"status": "no_records", "result": None}
ERROR = {"status": "error", "result": None}
NOT_CONFIGURED = {"status": "not_configured", "result": None}


@pytest.fixture(autouse=True)
def _no_real_discovery(monkeypatch):
    """Every test in this file is offline -- never let discovery attempt
    a real HTTP call, and never let stale in-process caches leak between
    tests."""
    monkeypatch.setattr(mandi_directory, "discover_state_markets", lambda state="Chhattisgarh": [])
    monkeypatch.setattr(agmarknet_service, "is_configured", lambda: False)
    mandi_directory._discovery_cache.clear()
    live_market_data._cache.clear()
    district_market_data._cache.clear()
    yield


def test_market_resource_hit_is_labeled_government_mandi_price(monkeypatch):
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: MARKET_OK)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: DISTRICT_OK)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    assert outcome["data"]["source_resource"] == "market"
    # Market-level hit should win even though the district resource also
    # has data -- it must NOT be relabeled as a district reference.
    assert "district_reference_note" not in outcome["data"] or outcome["data"].get("district_reference_note") is None


def test_district_only_hit_is_labeled_district_reference_not_mandi_price(monkeypatch):
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: NO_RECORDS)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: DISTRICT_OK)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    assert outcome["data"]["source_resource"] == "district_variety"
    # The critical honesty requirement: this must never be presented as a
    # specific mandi's modal price.
    note = outcome["data"]["district_reference_note"]
    assert "not a specific mandi modal price" in note


def test_clean_zero_records_is_not_records_not_demo(monkeypatch):
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: NO_RECORDS)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: NO_RECORDS)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "no_records"
    assert outcome["data"] is None


def test_actual_api_failure_is_error_not_no_records(monkeypatch):
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: ERROR)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: NO_RECORDS)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    # A genuine failure on one resource, clean "nothing here" on the
    # other -- overall must surface as "error" (the only status allowed
    # to trigger a demo fallback), never silently as "no_records".
    assert outcome["status"] == "error"
    assert outcome["data"] is None


def test_not_configured_when_neither_resource_is_set_up(monkeypatch):
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: NOT_CONFIGURED)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: NOT_CONFIGURED)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "not_configured"
    assert outcome["data"] is None


def test_fuzzy_match_rejected_below_confidence_threshold(monkeypatch):
    """A merely plausible-looking name must NOT be promoted to a candidate
    -- wrong live mandi data is worse than no live data."""
    monkeypatch.setattr(
        mandi_directory, "discover_state_markets",
        lambda state="Chhattisgarh": ["Totally Different Town"],
    )
    candidates = mandi_directory.resolve_candidate_market_names("Bilaspur")
    assert candidates == ["Bilaspur"]  # no fuzzy candidate added


def test_fuzzy_match_accepted_above_confidence_threshold(monkeypatch):
    monkeypatch.setattr(
        mandi_directory, "discover_state_markets",
        lambda state="Chhattisgarh": ["Bilaspur "],  # trivial whitespace difference -> very high similarity
    )
    candidates = mandi_directory.resolve_candidate_market_names("Bilaspur")
    assert "Bilaspur " in candidates


def test_manual_alias_hints_always_included():
    candidates = mandi_directory.resolve_candidate_market_names("Bilha")
    assert "Bilaspur" in candidates
    assert "Bilha" in candidates


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
