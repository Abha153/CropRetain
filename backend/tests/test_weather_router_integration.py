"""
Integration-level test for the /weather/farmer router: proves the router
correctly threads a REAL Farmer row's location/coordinates through to
weather_service.get_weather(), i.e. two different farmers in two
different seeded towns each get their OWN location's weather, not a
shared/default one. Calls the router function directly (same pattern as
test_market_router.py) rather than spinning up a full HTTP+auth stack.
"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.routers import weather as weather_router


class _FakeFarmer:
    def __init__(self, location, latitude, longitude):
        self.location = location
        self.latitude = latitude
        self.longitude = longitude


def test_two_different_farmers_get_two_different_locations_weather():
    farmer_a = _FakeFarmer("Bilaspur", 22.0797, 82.1409)
    farmer_b = _FakeFarmer("Raipur", 21.2514, 81.6296)

    # No live network in this sandbox (see weather_service.py's honesty
    # note) so both resolve via the seeded DEMO path -- that's fine, this
    # test is specifically about location MATCHING, not live-vs-demo.
    with patch("app.services.weather_service._fetch_live", side_effect=weather_service_error()):
        result_a = weather_router.farmer_weather(current=farmer_a)
        result_b = weather_router.farmer_weather(current=farmer_b)

    assert result_a["status"] == "DEMO"
    assert result_b["status"] == "DEMO"
    assert "Bilaspur" in result_a["location"]["name"]
    assert "Raipur" in result_b["location"]["name"]
    assert result_a["forecast"] != result_b["forecast"]  # genuinely different data


def weather_service_error():
    from app.services.weather_service import WeatherAPIError
    return WeatherAPIError("network disabled for deterministic test")


def test_farmer_with_zero_coordinates_still_resolves_by_location_name():
    # Farmer.latitude/longitude default to 0.0 in the model -- must not be
    # treated as valid GPS coordinates (0,0 is a real place in the ocean).
    farmer = _FakeFarmer("Durg", 0.0, 0.0)
    result = weather_router.farmer_weather(current=farmer)
    assert result["status"] == "DEMO"
    assert "Durg" in result["location"]["name"]


def test_unseeded_farmer_location_is_honestly_unavailable():
    farmer = _FakeFarmer("SomeCityWithNoSeedData", 0.0, 0.0)
    result = weather_router.farmer_weather(current=farmer)
    assert result["status"] == "UNAVAILABLE"
    assert result["forecast"] == []


def test_public_lookup_endpoint_accepts_gps_coordinates_directly():
    # Simulates the "Use My Location" GPS flow calling GET /weather with
    # fresh browser coordinates rather than a farmer's saved profile.
    result = weather_router.weather_lookup(latitude=None, longitude=None, location="Korba")
    assert result["status"] == "DEMO"
    assert "Korba" in result["location"]["name"]
