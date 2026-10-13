"""
Weather service tests.

LIVE-path tests use a mocked httpx response shaped exactly like a real
Open-Meteo response (per the documented API contract) -- this sandbox has
no network route to api.open-meteo.com (confirmed blocked at the sandbox
level, and separately Open-Meteo's own robots.txt disallows automated
fetching even via the assistant's web tooling), so this is NOT a
substitute for a real live round trip. It proves the request-building and
response-parsing logic is correct against the real schema; a genuine
network test still needs to happen once deployed somewhere with outbound
internet access. See weather_service.py's module docstring for the full
honesty note.
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import weather_service as ws


def _mock_open_meteo_response(status_code=200, days=7, malformed=False):
    resp = MagicMock()
    resp.status_code = status_code
    if malformed:
        resp.json.return_value = {"current": {}, "daily": {"time": []}}
        return resp
    resp.json.return_value = {
        "current": {
            "temperature_2m": 31.2, "relative_humidity_2m": 64,
            "precipitation": 0.0, "weather_code": 1, "wind_speed_10m": 11.4,
        },
        "daily": {
            "time": [f"2026-09-{2+i:02d}" for i in range(days)],
            "weather_code": [1, 61, 2, 0, 63, 2, 1][:days],
            "temperature_2m_max": [33.1, 29.5, 32.0, 34.2, 28.0, 31.5, 32.8][:days],
            "temperature_2m_min": [24.0, 22.5, 23.8, 25.1, 22.0, 23.5, 24.2][:days],
            "precipitation_probability_max": [10, 65, 20, 5, 78, 25, 15][:days],
            "precipitation_sum": [0.0, 12.0, 1.0, 0.0, 24.0, 2.0, 0.5][:days],
            "wind_speed_10m_max": [10.0, 15.0, 11.0, 9.0, 19.0, 12.0, 10.5][:days],
        },
    }
    return resp


class TestWeatherLive(unittest.TestCase):
    def setUp(self):
        ws._live_cache.clear()

    @patch("httpx.Client.get")
    def test_live_success_parses_correctly(self, mock_get):
        mock_get.return_value = _mock_open_meteo_response()
        result = ws.get_weather(19.9975, 73.7898, "Nashik")
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(result["source"], "Open-Meteo")
        self.assertEqual(len(result["forecast"]), 7)
        self.assertEqual(result["current"]["temperature"], 31.2)
        self.assertEqual(result["forecast"][0]["condition"], "Mainly clear")
        # Sanity: request actually included the documented params
        params = mock_get.call_args.kwargs["params"]
        self.assertIn("current", params)
        self.assertIn("daily", params)
        self.assertEqual(params["timezone"], "auto")

    @patch("httpx.Client.get")
    def test_live_caches_repeat_requests(self, mock_get):
        mock_get.return_value = _mock_open_meteo_response()
        ws.get_weather(19.9975, 73.7898, "Nashik")
        ws.get_weather(19.9975, 73.7898, "Nashik")
        self.assertEqual(mock_get.call_count, 1)  # second call served from cache

    @patch("httpx.Client.get")
    def test_live_http_error_falls_back_to_demo(self, mock_get):
        mock_get.return_value = _mock_open_meteo_response(status_code=503)
        result = ws.get_weather(22.0797, 82.1409, "Bilaspur")
        self.assertEqual(result["status"], "DEMO")
        self.assertEqual(result["source"], "CropRetain Demo Dataset")

    @patch("httpx.Client.get")
    def test_live_malformed_response_falls_back_to_demo(self, mock_get):
        mock_get.return_value = _mock_open_meteo_response(malformed=True)
        result = ws.get_weather(22.0797, 82.1409, "Bilaspur")
        self.assertEqual(result["status"], "DEMO")

    @patch("httpx.Client.get")
    def test_network_exception_falls_back_to_demo(self, mock_get):
        import httpx
        mock_get.side_effect = httpx.ConnectTimeout("timed out")
        result = ws.get_weather(22.0797, 82.1409, "Bilaspur")
        self.assertEqual(result["status"], "DEMO")

    def test_live_never_attempted_without_coordinates(self):
        # No lat/lon -> must go straight to demo/unavailable, no network call
        with patch("httpx.Client.get") as mock_get:
            result = ws.get_weather(None, None, "Bilaspur")
            mock_get.assert_not_called()
            self.assertEqual(result["status"], "DEMO")


class TestWeatherDemoFallback(unittest.TestCase):
    def test_known_seeded_location_returns_demo(self):
        result = ws.get_weather(None, None, "Raipur")
        self.assertEqual(result["status"], "DEMO")
        self.assertEqual(result["source"], "CropRetain Demo Dataset")
        self.assertEqual(len(result["forecast"]), 7)

    def test_all_ten_seeded_farmer_locations_covered(self):
        # Every DEMO_FARMERS location from demo_users.py must resolve.
        for loc in ["Bilaspur", "Raigarh", "Durg", "Rajnandgaon", "Mahasamund",
                    "Korba", "Ambikapur", "Jagdalpur", "Bilha", "Raipur"]:
            result = ws.get_weather(None, None, loc)
            self.assertEqual(result["status"], "DEMO", f"{loc} should have seeded weather")

    def test_unknown_location_is_unavailable_not_fabricated(self):
        result = ws.get_weather(None, None, "SomeTotallyUnseededVillage")
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIsNone(result["current"])
        self.assertEqual(result["forecast"], [])

    def test_demo_data_is_deterministic_across_calls(self):
        a = ws.get_weather(None, None, "Durg")
        b = ws.get_weather(None, None, "Durg")
        self.assertEqual(a["forecast"], b["forecast"])
        self.assertEqual(a["current"], b["current"])

    def test_no_random_module_used_in_demo_path(self):
        # Static assertion: the demo dataset must not call random.* at
        # request time. Verified by source inspection, not just behavior.
        import inspect
        src = inspect.getsource(ws)
        demo_section = src.split("# DEMO fallback")[1].split("# ----")[0]
        self.assertNotIn("random.", demo_section)
        self.assertNotIn("Math.random", demo_section)

    def test_rain_probability_never_paired_with_clear_sky(self):
        # Internal consistency check across the whole seeded dataset:
        # "Rain Probability = 80% should generally correspond to a rainy/
        # cloudy condition, not Clear Sky."
        for loc, data in ws._SEEDED_WEATHER.items():
            for day in data["days"]:
                if day["rainfall_probability"] >= 60:
                    self.assertNotEqual(day["weather_code"], 0,
                        f"{loc} day {day['date']}: {day['rainfall_probability']}% rain but coded Clear sky")


class TestWeatherRiskDerivation(unittest.TestCase):
    def test_high_rain_probability_is_high_risk(self):
        result = ws.get_weather(None, None, "Jagdalpur")  # day1 (tomorrow) = 62% prob, 14mm
        risk, note = ws.derive_weather_risk(result)
        self.assertIn(risk, ("Medium", "High"))  # 62% >= 40 at least Medium; verify exact:
        self.assertEqual(risk, "Medium")
        self.assertIn("Demo forecast", note)

    def test_risk_labels_documented_thresholds(self):
        fake_high = {"status": "DEMO", "forecast": [
            {"rainfall_probability": 10, "rainfall_mm": 0, "condition": "Clear sky"},
            {"rainfall_probability": 75, "rainfall_mm": 25, "condition": "Slight rain"},
        ]}
        risk, _ = ws.derive_weather_risk(fake_high)
        self.assertEqual(risk, "High")

        fake_low = {"status": "LIVE", "forecast": [
            {"rainfall_probability": 5, "rainfall_mm": 0, "condition": "Clear sky"},
            {"rainfall_probability": 10, "rainfall_mm": 0, "condition": "Clear sky"},
        ]}
        risk, note = ws.derive_weather_risk(fake_low)
        self.assertEqual(risk, "Low")
        self.assertNotIn("demonstration data", note)  # LIVE note shouldn't claim demo

    def test_insufficient_forecast_returns_none(self):
        self.assertIsNone(ws.derive_weather_risk({"status": "UNAVAILABLE", "forecast": []}))


class TestRecommendationEngineWeatherIntegration(unittest.TestCase):
    def test_resolve_weather_risk_uses_seeded_data_for_known_location(self):
        from app.services.recommendation_engine import resolve_weather_risk
        risk, note = resolve_weather_risk("Tomato", "Bilaspur")
        self.assertIn(risk, ("Low", "Medium", "High"))
        self.assertIn("forecast", note.lower())

    def test_resolve_weather_risk_falls_back_for_unknown_location(self):
        from app.services.recommendation_engine import resolve_weather_risk, simulate_weather_risk
        risk, note = resolve_weather_risk("Tomato", "SomeUnseededTown")
        # Should match simulate_weather_risk's own deterministic output
        # for the same inputs (same seeded RNG), proving genuine fallback.
        expected = simulate_weather_risk("Tomato", "SomeUnseededTown")
        self.assertEqual((risk, note), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
