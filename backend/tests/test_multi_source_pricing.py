"""
Tests for multi-source price combination in
app/services/mandi_directory.py::fetch_price_result -- data.gov.in and
Agmarknet (via CEDA) are queried CONCURRENTLY and their results combined,
never treated as "first hit wins" alternatives. See that function's
docstring for the full status/field contract.

No network is touched: live_market_data.fetch_live_price_status,
district_market_data.fetch_district_variety_price_status, and
agmarknet_service.fetch_price/is_configured are all monkeypatched to
controlled outcomes.

Run with: pytest backend/tests/test_multi_source_pricing.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.services import mandi_directory, live_market_data, district_market_data, agmarknet_service


DATA_GOV_IN_OK = {
    "status": "ok",
    "result": {
        "source": "live", "provider": "data.gov.in (Agmarknet)",
        "crop": "Tomato", "market": "Bilaspur", "state": "Chhattisgarh",
        "arrival_date": "26/08/2026", "modal_price": 3500.0,
        "min_price": 3300.0, "max_price": 3700.0,
        "variety": "Local", "grade": "FAQ", "fetched_at": "2026-08-26T00:00:00Z",
    },
}
DISTRICT_NO_RECORDS = {"status": "no_records", "result": None}


def _agmarknet_ok(modal_price, date="2026-08-26"):
    return {
        "status": "ok",
        "data": {
            "source": "CEDA_AGMARKNET", "provider": "CEDA AGMARKNET",
            "crop": "Tomato", "market": "Bilaspur", "state": "Chhattisgarh",
            "arrival_date": date, "modal_price": modal_price,
            "min_price": modal_price - 100, "max_price": modal_price + 100,
            "quantity": 12.5, "market_id": 1, "source_resource": "market",
            "fetched_at": "2026-08-26T00:05:00Z",
        },
    }


def _configure_agmarknet(monkeypatch, fetch_return=None, fetch_raises=None):
    monkeypatch.setattr(agmarknet_service, "is_configured", lambda: True)
    if fetch_raises is not None:
        def _raise(*a, **k):
            raise fetch_raises
        monkeypatch.setattr(agmarknet_service, "fetch_price", _raise)
    else:
        monkeypatch.setattr(agmarknet_service, "fetch_price", lambda *a, **k: fetch_return)


def _unconfigure_agmarknet(monkeypatch):
    monkeypatch.setattr(agmarknet_service, "is_configured", lambda: False)


def _data_gov_in_ok(monkeypatch, outcome=DATA_GOV_IN_OK, district_outcome=DISTRICT_NO_RECORDS):
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: outcome)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: district_outcome)


def _data_gov_in_not_configured(monkeypatch):
    not_configured = {"status": "not_configured", "result": None}
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: not_configured)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: not_configured)


# ---------------------------------------------------------------------------
# Both sources configured and returning usable data
# ---------------------------------------------------------------------------

def test_both_sources_agreeing_are_combined_not_first_hit_wins(monkeypatch):
    """When both providers are configured and both have data, the result
    must reflect BOTH -- not just whichever happened to be tried first."""
    _data_gov_in_ok(monkeypatch)
    _configure_agmarknet(monkeypatch, fetch_return=_agmarknet_ok(3510.0))  # within 2% of 3500 -> agrees

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    data = outcome["data"]
    assert set(data["sources"]) == {"data.gov.in", "agmarknet"}
    assert data["source_conflict"] is False
    assert "data.gov.in" in data["source_values"]
    assert "agmarknet" in data["source_values"]
    assert data["source_values"]["data.gov.in"]["modal_price"] == 3500.0
    assert data["source_values"]["agmarknet"]["modal_price"] == 3510.0


def test_conflicting_prices_are_preserved_not_discarded(monkeypatch):
    """A genuine disagreement (>2%) between sources must be flagged, and
    BOTH values must still be retrievable -- never silently pick one and
    hide the other."""
    _data_gov_in_ok(monkeypatch)  # 3500.0
    _configure_agmarknet(monkeypatch, fetch_return=_agmarknet_ok(4200.0))  # 20% higher -> genuine conflict

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    data = outcome["data"]
    assert data["source_conflict"] is True
    assert data["source_values"]["data.gov.in"]["modal_price"] == 3500.0
    assert data["source_values"]["agmarknet"]["modal_price"] == 4200.0
    # Neither value was silently dropped or averaged away.
    assert {r["modal_price"] for r in data["observations"]} == {3500.0, 4200.0}


def test_different_observation_dates_are_both_preserved(monkeypatch):
    """Two sources reporting genuinely different dates are different
    observations, not a same-day conflict -- both must survive."""
    _data_gov_in_ok(monkeypatch)  # 26/08/2026
    _configure_agmarknet(monkeypatch, fetch_return=_agmarknet_ok(3600.0, date="2026-08-27"))  # later date

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    data = outcome["data"]
    assert len(data["observations"]) == 2
    # "Latest" (top-level) values should reflect the most recent date -- CEDA's 27th, not data.gov.in's 26th.
    assert data["modal_price"] == 3600.0
    assert "agmarknet" in data["sources"]


# ---------------------------------------------------------------------------
# One source unavailable -- the other's data must still be used
# ---------------------------------------------------------------------------

def test_agmarknet_unconfigured_does_not_block_data_gov_in_result(monkeypatch):
    _data_gov_in_ok(monkeypatch)
    _unconfigure_agmarknet(monkeypatch)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    assert outcome["data"]["sources"] == ["data.gov.in"]
    assert outcome["data"]["source_conflict"] is False


def test_data_gov_in_unavailable_does_not_block_agmarknet_result(monkeypatch):
    """The reverse: data.gov.in has nothing (not configured), but
    Agmarknet does -- the request must not fail just because one source
    is down (per the 'do not fail the whole request' requirement)."""
    _data_gov_in_not_configured(monkeypatch)
    _configure_agmarknet(monkeypatch, fetch_return=_agmarknet_ok(3500.0))

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    assert outcome["data"]["sources"] == ["agmarknet"]


def test_agmarknet_request_failure_does_not_block_data_gov_in_result(monkeypatch):
    """A genuine provider error (not just unconfigured) on one source
    must still let the other source's usable data through."""
    _data_gov_in_ok(monkeypatch)
    _configure_agmarknet(monkeypatch, fetch_raises=agmarknet_service.AgmarknetError("simulated failure"))

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    assert outcome["status"] == "ok"
    assert outcome["data"]["sources"] == ["data.gov.in"]


# ---------------------------------------------------------------------------
# Neither source has data -- status priority (error > no_records > not_configured)
# ---------------------------------------------------------------------------

def test_no_records_from_a_configured_source_is_not_downgraded_to_not_configured(monkeypatch):
    """Regression: data.gov.in genuinely confirms no record exists, but
    Agmarknet simply isn't configured -- the overall answer must stay the
    honest 'no_records', not get diluted into 'not_configured' just
    because the OTHER source wasn't set up."""
    no_records = {"status": "no_records", "result": None}
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: no_records)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: no_records)
    _unconfigure_agmarknet(monkeypatch)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")
    assert outcome["status"] == "no_records"


def test_neither_source_configured_is_not_configured(monkeypatch):
    _data_gov_in_not_configured(monkeypatch)
    _unconfigure_agmarknet(monkeypatch)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")
    assert outcome["status"] == "not_configured"


def test_error_outranks_no_records_and_not_configured(monkeypatch):
    error_outcome = {"status": "error", "result": None}
    monkeypatch.setattr(live_market_data, "fetch_live_price_status", lambda *a, **k: error_outcome)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", lambda *a, **k: error_outcome)
    _unconfigure_agmarknet(monkeypatch)

    outcome = mandi_directory.fetch_price_result("Tomato", "Bilaspur")
    assert outcome["status"] == "error"


# ---------------------------------------------------------------------------
# Both sources queried in parallel, not sequentially
# ---------------------------------------------------------------------------

def test_both_sources_are_queried_concurrently(monkeypatch):
    """Both providers should be invoked for every request where both are
    configured -- proving this isn't a 'try data.gov.in, only fall back to
    Agmarknet if it fails' chain."""
    calls = {"data_gov_in": 0, "agmarknet": 0}

    def _live(*a, **k):
        calls["data_gov_in"] += 1
        return DATA_GOV_IN_OK

    def _district(*a, **k):
        return DISTRICT_NO_RECORDS

    def _agmarknet(*a, **k):
        calls["agmarknet"] += 1
        return _agmarknet_ok(3510.0)

    monkeypatch.setattr(live_market_data, "fetch_live_price_status", _live)
    monkeypatch.setattr(district_market_data, "fetch_district_variety_price_status", _district)
    _configure_agmarknet(monkeypatch, fetch_return=_agmarknet_ok(3510.0))
    monkeypatch.setattr(agmarknet_service, "fetch_price", _agmarknet)

    mandi_directory.fetch_price_result("Tomato", "Bilaspur")

    # data.gov.in is tried per-candidate (resolve_candidate_market_names
    # may yield 1+ names), so >=1 is the correct assertion; Agmarknet is
    # tried exactly once since it's a single request, not name-resolution.
    assert calls["data_gov_in"] >= 1
    assert calls["agmarknet"] == 1
