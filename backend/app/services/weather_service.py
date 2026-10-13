"""
Weather service -- LIVE (Open-Meteo) with a deterministic SEEDED DEMO
fallback, never a randomly-generated one.

CONTRACT (see app/routers/weather.py for the HTTP surface):

    get_weather(latitude, longitude, location_name) -> dict with:
        status: "LIVE" | "DEMO" | "UNAVAILABLE"
        source: "Open-Meteo" | "CropRetain Demo Dataset" | None
        location: {name, latitude, longitude}
        current: {...} | None
        forecast: [ {date, weather_code, condition, temp_min, temp_max,
                     humidity, rainfall_probability, rainfall_mm,
                     wind_speed_kmh}, ... up to 7 entries ] | []

FLOW
    try live (Open-Meteo)
        -> validate response shape
        -> return LIVE
    except (network error, timeout, HTTP error, malformed response)
        -> look up deterministic seeded fallback for location_name
        -> if found: return DEMO
        -> if not found: return UNAVAILABLE

HONESTY (read before trusting this blindly): this sandboxed development
environment cannot reach api.open-meteo.com at all -- confirmed both via
direct network attempts (blocked, not on this environment's allowlist)
and via api.open-meteo.com's own robots.txt (disallows automated
fetching, so even the assistant's web-fetch tool was refused). The LIVE
code path below is written strictly to Open-Meteo's public, versioned,
well-documented Forecast API contract (https://open-meteo.com/en/docs --
no API key required for the free/non-commercial tier) and is covered by
mocked-response tests that exercise real Open-Meteo-shaped JSON, but it
has NOT been exercised against a real live HTTP round trip from this
environment. Please verify once deployed somewhere with outbound
internet access, and report back if Open-Meteo's schema has changed.

DATA INTEGRITY: the DEMO dataset below is a small, fixed, hand-authored
table -- no random.random(), no per-request generation, no per-day
drift. The same location always returns the same 7-day demo forecast
until this file is edited. Every seeded location below corresponds to an
actual DEMO_FARMERS location in app/mock_data/demo_users.py (Bilaspur,
Raigarh, Durg, Rajnandgaon, Mahasamund, Korba, Ambikapur, Jagdalpur,
Bilha, Raipur) -- no farmer's location was invented or changed to make
weather "available".
"""
import datetime as dt
import time
from typing import Optional

import httpx

from app.config import settings, logger

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_DAYS = 7
LIVE_CACHE_TTL_SECONDS = 20 * 60  # 15-30 min window per spec; picked 20.
REQUEST_TIMEOUT_SECONDS = 6.0

# ---------------------------------------------------------------------------
# WMO weather code -> human condition. One centralized mapping (per spec
# "do not duplicate this mapping across components") -- the frontend
# receives the resolved `condition` string plus the raw `weather_code`, and
# maps `weather_code` to an icon itself (see frontend/src/utils/weatherCodes.js)
# rather than this backend module knowing anything about icon names.
# ---------------------------------------------------------------------------
_WMO_CONDITIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


def condition_for_code(code) -> str:
    try:
        return _WMO_CONDITIONS.get(int(code), "Unknown")
    except (TypeError, ValueError):
        return "Unknown"


class WeatherAPIError(Exception):
    """Raised for any live-fetch failure: network, timeout, HTTP status,
    or a response that doesn't match the expected shape. Caught by
    get_weather() to trigger the DEMO fallback -- never surfaced raw."""


# ---------------------------------------------------------------------------
# LIVE fetch
# ---------------------------------------------------------------------------

_live_cache: dict = {}  # (rounded_lat, rounded_lon) -> (expires_at, result)

# Failures are NOT written into _live_cache above (that only ever holds a
# successful result). Without a short negative cache, an unreachable/slow
# Open-Meteo means every dashboard load re-pays the full
# REQUEST_TIMEOUT_SECONDS timeout instead of failing fast to the demo
# fallback after the first attempt.
_FAILURE_CACHE_TTL_SECONDS = 60.0
_failure_cache: dict = {}


def _cache_key(lat: float, lon: float):
    # Round to ~1.1km precision so nearby requests share a cache entry
    # without materially changing which forecast grid cell is used.
    return (round(lat, 2), round(lon, 2))


def _fetch_live(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timezone": "auto",
        "forecast_days": FORECAST_DAYS,
    }
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(OPEN_METEO_URL, params=params)
    except httpx.HTTPError as e:
        raise WeatherAPIError(f"network error: {e}") from e

    if resp.status_code != 200:
        raise WeatherAPIError(f"HTTP {resp.status_code}")

    try:
        data = resp.json()
    except ValueError as e:
        raise WeatherAPIError(f"invalid JSON: {e}") from e

    # Validate shape before trusting anything -- same "never blindly trust
    # a 200" discipline as the data.gov.in integration.
    current = data.get("current")
    daily = data.get("daily")
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise WeatherAPIError("missing current/daily blocks")

    required_daily_keys = (
        "time", "weather_code", "temperature_2m_max", "temperature_2m_min",
        "precipitation_probability_max", "precipitation_sum", "wind_speed_10m_max",
    )
    for key in required_daily_keys:
        if key not in daily or not isinstance(daily[key], list):
            raise WeatherAPIError(f"daily block missing/invalid field: {key}")
    lengths = {len(daily[k]) for k in required_daily_keys}
    if len(lengths) != 1 or lengths == {0}:
        raise WeatherAPIError("daily arrays have inconsistent/zero length")

    try:
        forecast = []
        for i in range(len(daily["time"])):
            forecast.append({
                "date": daily["time"][i],
                "weather_code": int(daily["weather_code"][i]),
                "condition": condition_for_code(daily["weather_code"][i]),
                "temp_min": round(float(daily["temperature_2m_min"][i]), 1),
                "temp_max": round(float(daily["temperature_2m_max"][i]), 1),
                "rainfall_probability": round(float(daily["precipitation_probability_max"][i]), 0),
                "rainfall_mm": round(float(daily["precipitation_sum"][i]), 1),
                "wind_speed_kmh": round(float(daily["wind_speed_10m_max"][i]), 1),
                "humidity": None,  # Open-Meteo's daily block has no humidity field
            })
        current_out = {
            "temperature": round(float(current["temperature_2m"]), 1),
            "humidity": round(float(current["relative_humidity_2m"]), 0) if current.get("relative_humidity_2m") is not None else None,
            "precipitation_mm": round(float(current.get("precipitation", 0)), 1),
            "weather_code": int(current["weather_code"]),
            "condition": condition_for_code(current["weather_code"]),
            "wind_speed_kmh": round(float(current["wind_speed_10m"]), 1),
        }
    except (KeyError, TypeError, ValueError) as e:
        raise WeatherAPIError(f"malformed values: {e}") from e

    return {"current": current_out, "forecast": forecast}


# ---------------------------------------------------------------------------
# DEMO fallback -- deterministic, hand-authored, never random
# ---------------------------------------------------------------------------

def _demo_day(offset, temp_max, temp_min, humidity, rain_prob, rain_mm, wind, code):
    base = dt.date(2026, 9, 2)  # fixed anchor -- see module docstring: this
    # is a deterministic table, not "today's real date" recomputed live.
    return {
        "date": (base + dt.timedelta(days=offset)).isoformat(),
        "weather_code": code,
        "condition": condition_for_code(code),
        "temp_min": temp_min, "temp_max": temp_max,
        "humidity": humidity,
        "rainfall_probability": rain_prob, "rainfall_mm": rain_mm,
        "wind_speed_kmh": wind,
    }


# Each location: 7 hand-authored, internally-consistent days (high rain
# probability days use a rain/drizzle/thunderstorm WMO code, never
# "Clear sky" -- see module docstring's "impossible combinations" rule).
# Coordinates match app/mock_data/demo_users.py exactly.
_SEEDED_WEATHER = {
    "bilaspur": {
        "display_name": "Bilaspur, Chhattisgarh", "latitude": 22.0797, "longitude": 82.1409,
        "days": [
            _demo_day(0, 33.0, 24.0, 68, 10, 0.0, 9.0, 1),
            _demo_day(1, 34.0, 25.0, 65, 5, 0.0, 8.0, 0),
            _demo_day(2, 32.0, 24.5, 74, 40, 3.0, 12.0, 61),
            _demo_day(3, 29.0, 23.0, 85, 78, 22.0, 18.0, 63),
            _demo_day(4, 28.5, 22.5, 88, 82, 30.0, 21.0, 80),
            _demo_day(5, 30.0, 23.5, 76, 45, 6.0, 14.0, 61),
            _demo_day(6, 32.5, 24.0, 66, 15, 0.5, 10.0, 2),
        ],
    },
    "raigarh": {
        "display_name": "Raigarh, Chhattisgarh", "latitude": 21.8974, "longitude": 83.3950,
        "days": [
            _demo_day(0, 32.5, 24.5, 70, 15, 0.0, 10.0, 2),
            _demo_day(1, 31.0, 24.0, 78, 55, 8.0, 15.0, 61),
            _demo_day(2, 29.5, 23.0, 84, 70, 18.0, 17.0, 63),
            _demo_day(3, 30.0, 23.5, 72, 35, 2.0, 13.0, 51),
            _demo_day(4, 33.0, 25.0, 60, 8, 0.0, 9.0, 0),
            _demo_day(5, 33.5, 25.5, 58, 5, 0.0, 8.0, 1),
            _demo_day(6, 31.5, 24.0, 68, 20, 1.0, 11.0, 2),
        ],
    },
    "durg": {
        "display_name": "Durg, Chhattisgarh", "latitude": 21.1904, "longitude": 81.2849,
        "days": [
            _demo_day(0, 34.5, 25.5, 55, 5, 0.0, 7.0, 0),
            _demo_day(1, 35.0, 26.0, 52, 5, 0.0, 7.0, 0),
            _demo_day(2, 34.0, 25.5, 60, 15, 0.0, 9.0, 1),
            _demo_day(3, 31.0, 24.0, 76, 60, 12.0, 16.0, 61),
            _demo_day(4, 29.5, 23.0, 83, 72, 20.0, 19.0, 63),
            _demo_day(5, 31.5, 24.0, 70, 30, 2.0, 12.0, 51),
            _demo_day(6, 33.5, 25.0, 58, 10, 0.0, 8.0, 1),
        ],
    },
    "rajnandgaon": {
        "display_name": "Rajnandgaon, Chhattisgarh", "latitude": 21.0972, "longitude": 81.0388,
        "days": [
            _demo_day(0, 33.5, 24.5, 62, 12, 0.0, 8.0, 1),
            _demo_day(1, 30.5, 23.5, 80, 65, 15.0, 17.0, 63),
            _demo_day(2, 28.5, 22.5, 87, 85, 28.0, 22.0, 82),
            _demo_day(3, 29.0, 23.0, 82, 68, 16.0, 18.0, 61),
            _demo_day(4, 31.5, 24.0, 68, 25, 1.0, 12.0, 2),
            _demo_day(5, 34.0, 25.5, 56, 8, 0.0, 8.0, 0),
            _demo_day(6, 34.5, 25.5, 54, 5, 0.0, 7.0, 0),
        ],
    },
    "mahasamund": {
        "display_name": "Mahasamund, Chhattisgarh", "latitude": 21.1093, "longitude": 82.0980,
        "days": [
            _demo_day(0, 32.0, 24.0, 70, 20, 0.5, 10.0, 2),
            _demo_day(1, 33.0, 24.5, 63, 10, 0.0, 9.0, 1),
            _demo_day(2, 30.0, 23.5, 79, 58, 10.0, 15.0, 61),
            _demo_day(3, 28.5, 22.5, 86, 80, 24.0, 20.0, 80),
            _demo_day(4, 29.5, 23.0, 81, 66, 14.0, 17.0, 61),
            _demo_day(5, 32.0, 24.0, 68, 22, 1.0, 11.0, 2),
            _demo_day(6, 33.5, 25.0, 60, 10, 0.0, 8.0, 0),
        ],
    },
    "korba": {
        "display_name": "Korba, Chhattisgarh", "latitude": 22.3595, "longitude": 82.7501,
        "days": [
            _demo_day(0, 31.5, 23.5, 72, 25, 1.0, 11.0, 2),
            _demo_day(1, 29.5, 22.5, 82, 62, 13.0, 16.0, 61),
            _demo_day(2, 27.5, 21.5, 89, 84, 26.0, 21.0, 82),
            _demo_day(3, 28.0, 22.0, 85, 75, 19.0, 19.0, 63),
            _demo_day(4, 30.5, 23.0, 74, 38, 4.0, 13.0, 51),
            _demo_day(5, 32.5, 24.0, 64, 15, 0.0, 10.0, 1),
            _demo_day(6, 33.0, 24.5, 60, 10, 0.0, 9.0, 0),
        ],
    },
    "ambikapur": {
        "display_name": "Ambikapur, Chhattisgarh (Surguja)", "latitude": 23.1200, "longitude": 83.1950,
        "days": [
            _demo_day(0, 28.5, 20.0, 68, 15, 0.0, 9.0, 1),
            _demo_day(1, 29.0, 20.5, 65, 10, 0.0, 8.0, 0),
            _demo_day(2, 27.0, 19.5, 78, 55, 9.0, 14.0, 61),
            _demo_day(3, 25.5, 18.5, 86, 80, 22.0, 19.0, 80),
            _demo_day(4, 26.0, 19.0, 82, 70, 17.0, 17.0, 63),
            _demo_day(5, 28.0, 20.0, 70, 28, 1.0, 11.0, 2),
            _demo_day(6, 29.5, 21.0, 62, 12, 0.0, 9.0, 1),
        ],
    },
    "jagdalpur": {
        "display_name": "Jagdalpur, Chhattisgarh (Bastar)", "latitude": 19.0748, "longitude": 82.0198,
        "days": [
            _demo_day(0, 30.5, 22.5, 76, 35, 3.0, 12.0, 2),
            _demo_day(1, 28.5, 21.5, 84, 62, 14.0, 16.0, 61),
            _demo_day(2, 27.0, 21.0, 90, 88, 32.0, 23.0, 82),
            _demo_day(3, 27.5, 21.5, 87, 76, 21.0, 20.0, 63),
            _demo_day(4, 29.0, 22.0, 79, 50, 7.0, 14.0, 61),
            _demo_day(5, 31.0, 23.0, 68, 20, 0.5, 10.0, 1),
            _demo_day(6, 31.5, 23.5, 64, 15, 0.0, 9.0, 1),
        ],
    },
    "bilha": {
        "display_name": "Bilha, Chhattisgarh (Bilaspur district)", "latitude": 22.1500, "longitude": 82.0500,
        "days": [
            _demo_day(0, 33.0, 24.0, 68, 10, 0.0, 9.0, 1),
            _demo_day(1, 34.0, 25.0, 65, 5, 0.0, 8.0, 0),
            _demo_day(2, 32.0, 24.5, 74, 40, 3.0, 12.0, 61),
            _demo_day(3, 29.0, 23.0, 85, 78, 22.0, 18.0, 63),
            _demo_day(4, 28.5, 22.5, 88, 82, 30.0, 21.0, 80),
            _demo_day(5, 30.0, 23.5, 76, 45, 6.0, 14.0, 61),
            _demo_day(6, 32.5, 24.0, 66, 15, 0.5, 10.0, 2),
        ],
    },
    "raipur": {
        "display_name": "Raipur, Chhattisgarh", "latitude": 21.2514, "longitude": 81.6296,
        "days": [
            _demo_day(0, 34.0, 25.0, 60, 8, 0.0, 8.0, 0),
            _demo_day(1, 34.5, 25.5, 58, 5, 0.0, 7.0, 0),
            _demo_day(2, 33.0, 24.5, 66, 20, 0.5, 11.0, 1),
            _demo_day(3, 30.0, 23.5, 80, 62, 13.0, 16.0, 61),
            _demo_day(4, 28.5, 22.5, 87, 83, 27.0, 21.0, 82),
            _demo_day(5, 30.5, 23.5, 75, 40, 4.0, 13.0, 51),
            _demo_day(6, 33.0, 24.5, 62, 12, 0.0, 9.0, 1),
        ],
    },
}


def _normalize_location_key(location_name: Optional[str]) -> Optional[str]:
    if not location_name:
        return None
    return location_name.strip().lower().split(",")[0].strip()


def _get_seeded(location_name: Optional[str]) -> Optional[dict]:
    key = _normalize_location_key(location_name)
    if not key:
        return None
    return _SEEDED_WEATHER.get(key)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_weather(latitude: Optional[float], longitude: Optional[float], location_name: Optional[str]) -> dict:
    """
    Resolves weather for a location, preferring LIVE (Open-Meteo) and
    falling back to a deterministic DEMO forecast, per module docstring.
    Never raises -- always returns a well-formed status/source/location/
    current/forecast dict, even on total failure (status=UNAVAILABLE).
    """
    loc_out = {"name": location_name, "latitude": latitude, "longitude": longitude}

    if latitude and longitude:
        cache_k = _cache_key(latitude, longitude)
        cached = _live_cache.get(cache_k)
        if cached and cached[0] > time.time():
            result = cached[1]
            return {"status": "LIVE", "source": "Open-Meteo", "location": loc_out, **result}
        failure_expires = _failure_cache.get(cache_k)
        if failure_expires and failure_expires > time.time():
            logger.debug("weather_service: skipping live fetch, recent failure cached for %s", cache_k)
        else:
            try:
                result = _fetch_live(latitude, longitude)
                _live_cache[cache_k] = (time.time() + LIVE_CACHE_TTL_SECONDS, result)
                return {"status": "LIVE", "source": "Open-Meteo", "location": loc_out, **result}
            except WeatherAPIError as e:
                logger.info("weather_service: live fetch failed for (%s, %s): %s -- trying demo fallback",
                            latitude, longitude, e)
                _failure_cache[cache_k] = time.time() + _FAILURE_CACHE_TTL_SECONDS

    seeded = _get_seeded(location_name)
    if seeded:
        loc_out = {"name": seeded["display_name"], "latitude": seeded["latitude"], "longitude": seeded["longitude"]}
        days = seeded["days"]
        current = {
            "temperature": days[0]["temp_max"],
            "humidity": days[0]["humidity"],
            "precipitation_mm": days[0]["rainfall_mm"],
            "weather_code": days[0]["weather_code"],
            "condition": days[0]["condition"],
            "wind_speed_kmh": days[0]["wind_speed_kmh"],
        }
        return {"status": "DEMO", "source": "CropRetain Demo Dataset", "location": loc_out,
                "current": current, "forecast": days}

    return {"status": "UNAVAILABLE", "source": None, "location": loc_out, "current": None, "forecast": []}


# ---------------------------------------------------------------------------
# Weather-risk derivation for the recommendation engine (replaces
# simulate_weather_risk's OUTPUT when real/seeded weather is available --
# see app/services/recommendation_engine.py. simulate_weather_risk itself
# is left intact as the final fallback when no weather data exists at all).
#
# DOCUMENTED RULE (deterministic, not an ML model):
#   tomorrow's rainfall_probability >= 70  OR rainfall_mm >= 20  -> High
#   tomorrow's rainfall_probability >= 40  OR rainfall_mm >= 8   -> Medium
#   otherwise                                                     -> Low
# ---------------------------------------------------------------------------

def derive_weather_risk(weather_result: dict):
    forecast = weather_result.get("forecast") or []
    if len(forecast) < 2:
        return None  # not enough data to assess "tomorrow" -- caller falls back
    tomorrow = forecast[1]
    prob = tomorrow.get("rainfall_probability") or 0
    mm = tomorrow.get("rainfall_mm") or 0
    if prob >= 70 or mm >= 20:
        risk = "High"
    elif prob >= 40 or mm >= 8:
        risk = "Medium"
    else:
        risk = "Low"
    source_word = "Live" if weather_result.get("status") == "LIVE" else "Demo"
    note = (
        f"{source_word} forecast: {tomorrow['condition']} tomorrow, "
        f"{int(prob)}% rain chance. "
        + ("This is demonstration data, not a live forecast." if source_word == "Demo" else "")
    ).strip()
    return risk, note
