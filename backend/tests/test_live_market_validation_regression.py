"""
Regression tests for the live market-data validation fix.

Context: this checkpoint's fetch_live_price_status() already had correct
client-side record validation (the `validated = [...]` list comprehension
matching market/state/commodity case-insensitively) -- that part was NOT
regressed. The actual bug was narrower: the filter key sent to
data.gov.in was `filters[state]` instead of `filters[state.keyword]`,
which is the field key confirmed correct against a real, live, successful
response's own `field_exposed` metadata (captured earlier in this
project's history -- see the comment in live_market_data.py). A wrong
filter key doesn't stop the API from returning HTTP 200 with real rows
for OTHER markets/states, which is exactly the shape of bug these tests
pin down: the server-side filter can't be trusted, so the client-side
validation is the actual safety net, and it must keep working correctly
regardless of what filter keys are sent.
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import live_market_data as lmd
from app.config import settings


def _mock_response(status_code=200, records=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"records": records or []}
    return resp


class TestLiveMarketValidationRegression(unittest.TestCase):
    def setUp(self):
        lmd._cache.clear()
        self._orig_key = settings.data_gov_in_api_key
        self._orig_source = settings.market_data_source
        settings.data_gov_in_api_key = "test-key"
        settings.market_data_source = "live"

    def tearDown(self):
        settings.data_gov_in_api_key = self._orig_key
        settings.market_data_source = self._orig_source

    def test_filter_key_uses_state_keyword(self):
        """Confirms the actual fix: filters[state.keyword], not
        filters[state]. This is the one concrete thing that regressed."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(records=[])
            lmd.fetch_live_price_status("Onion", "Nashik", "Maharashtra")
            params = mock_get.call_args.kwargs["params"]
            self.assertIn("filters[state.keyword]", params)
            self.assertNotIn("filters[state]", params)

    def test_scenario_1_requested_market_A_api_returns_market_B_first_reject(self):
        """The exact regression class: requested market A, API's first/only
        record is for a completely different market B -- must be rejected,
        never displayed as if it were A's price."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(records=[{
                "modal_price": "1800", "state": "Chattisgarh", "market": "Raipur",
                "commodity": "Paddy(Common)", "arrival_date": "01/09/2026",
            }])
            outcome = lmd.fetch_live_price_status("Paddy", "Kharsiya", "Chhattisgarh")
            self.assertEqual(outcome["status"], "no_records")
            self.assertIsNone(outcome["result"])

    def test_scenario_2_requested_market_A_api_returns_A_accept(self):
        """Sanity check the fix doesn't over-reject: a genuine match for
        the requested market must still be accepted."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(records=[{
                "modal_price": "2100", "state": "Chattisgarh", "market": "Kharsiya",
                "commodity": "Paddy(Common)", "arrival_date": "01/09/2026",
            }])
            outcome = lmd.fetch_live_price_status("Paddy", "Kharsiya", "Chhattisgarh")
            self.assertEqual(outcome["status"], "ok")
            self.assertEqual(outcome["result"]["modal_price"], 2100.0)
            self.assertEqual(outcome["result"]["market"], "Kharsiya")

    def test_scenario_3_state_commodity_mismatch_reject(self):
        """Market name happens to match, but state AND commodity don't --
        must still be rejected, not partially accepted."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(records=[{
                "modal_price": "5000", "state": "Punjab", "market": "Kharsiya",
                "commodity": "Wheat", "arrival_date": "01/09/2026",
            }])
            outcome = lmd.fetch_live_price_status("Paddy", "Kharsiya", "Chhattisgarh")
            self.assertEqual(outcome["status"], "no_records")

    def test_scenario_4_no_exact_validated_record_returns_unavailable(self):
        """API returns HTTP 200 with an empty records list -- the plain
        'genuinely nothing here' case, must map to no_records (the
        existing app-wide 'unavailable' contract), never a fabricated
        fallback."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(records=[])
            outcome = lmd.fetch_live_price_status("Onion", "TotallyMadeUpMarket", "Maharashtra")
            self.assertEqual(outcome["status"], "no_records")
            self.assertIsNone(outcome["result"])

    def test_http_error_maps_to_error_not_no_records(self):
        """A real API failure (5xx) must be distinguishable from a genuine
        'no data' response -- only 'error' should trigger any demo
        fallback upstream, never 'no_records'."""
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(status_code=503)
            outcome = lmd.fetch_live_price_status("Onion", "Nashik", "Maharashtra")
            self.assertEqual(outcome["status"], "error")

    def test_mandi_directory_discovery_also_uses_state_keyword(self):
        """The sibling discovery loop (mandi_directory.py) shares the same
        resource and must use the same corrected filter key."""
        from app.services import mandi_directory as md
        md._discovery_cache = {}
        with patch("httpx.Client.get") as mock_get:
            mock_get.return_value = _mock_response(records=[])
            md.discover_state_markets("Maharashtra")
            params = mock_get.call_args.kwargs["params"]
            self.assertIn("filters[state.keyword]", params)


if __name__ == "__main__":
    unittest.main(verbosity=2)
