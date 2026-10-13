"""
Mock market/location data.

CropRetain is a pan-India platform. This list is not restricted to any one
state -- it currently ships two demo regions with real-world coordinates so
distance and transport-cost math behaves realistically:

  - Chhattisgarh: the original PS-26132 demo region
  - Maharashtra: the SIH/PS-26132 primary demo showcase region (see
    Settings.default_demo_state in app/config.py, which controls which
    state a request falls back to when none is specified -- Maharashtra by
    default, but that is a configurable demo default, not a hardcoded
    restriction; every function that reads it accepts an explicit state
    override).

In production this would be replaced by a live mandi/APMC directory API
covering all states.
"""
import math

MARKETS = [
    # ---- Chhattisgarh (original demo region) ----
    {"name": "Bilaspur",     "latitude": 22.0797, "longitude": 82.1409, "state": "Chhattisgarh"},
    {"name": "Raipur",       "latitude": 21.2514, "longitude": 81.6296, "state": "Chhattisgarh"},
    {"name": "Durg",         "latitude": 21.1904, "longitude": 81.2849, "state": "Chhattisgarh"},
    {"name": "Raigarh",      "latitude": 21.8974, "longitude": 83.3950, "state": "Chhattisgarh"},
    {"name": "Korba",        "latitude": 22.3595, "longitude": 82.7501, "state": "Chhattisgarh"},
    {"name": "Bilha",        "latitude": 22.1500, "longitude": 82.0500, "state": "Chhattisgarh"},
    {"name": "Ambikapur",    "latitude": 23.1200, "longitude": 83.1950, "state": "Chhattisgarh"},
    {"name": "Rajnandgaon",  "latitude": 21.0972, "longitude": 81.0388, "state": "Chhattisgarh"},
    {"name": "Mahasamund",   "latitude": 21.1093, "longitude": 82.0980, "state": "Chhattisgarh"},
    {"name": "Jagdalpur",    "latitude": 19.0748, "longitude": 82.0198, "state": "Chhattisgarh"},
    # ---- Maharashtra (primary SIH/PS-26132 demo showcase region) ----
    {"name": "Nashik",       "latitude": 19.9975, "longitude": 73.7898, "state": "Maharashtra"},
    {"name": "Sangli",       "latitude": 16.8524, "longitude": 74.5815, "state": "Maharashtra"},
    {"name": "Solapur",      "latitude": 17.6599, "longitude": 75.9064, "state": "Maharashtra"},
    {"name": "Pune",         "latitude": 18.5204, "longitude": 73.8567, "state": "Maharashtra"},
    {"name": "Kolhapur",     "latitude": 16.7050, "longitude": 74.2433, "state": "Maharashtra"},
    {"name": "Ahilyanagar",  "latitude": 19.0952, "longitude": 74.7496, "state": "Maharashtra"},
    {"name": "Chhatrapati Sambhajinagar", "latitude": 19.8762, "longitude": 75.3433, "state": "Maharashtra"},
    {"name": "Nagpur",       "latitude": 21.1458, "longitude": 79.0882, "state": "Maharashtra"},
    {"name": "Amravati",     "latitude": 20.9374, "longitude": 77.7796, "state": "Maharashtra"},
    {"name": "Akola",        "latitude": 20.7002, "longitude": 77.0082, "state": "Maharashtra"},
]

MARKET_BY_NAME = {m["name"]: m for m in MARKETS}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two points, in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def distance_between(market_a: str, market_b: str) -> float:
    a = MARKET_BY_NAME.get(market_a)
    b = MARKET_BY_NAME.get(market_b)
    if not a or not b:
        return 50.0  # fallback default
    if a["name"] == b["name"]:
        return 4.0  # local/intra-town movement
    return round(haversine_km(a["latitude"], a["longitude"], b["latitude"], b["longitude"]), 1)


def nearest_markets(location: str, limit: int = None):
    """Return all markets sorted by distance from `location` (nearest first)."""
    ranked = sorted(MARKETS, key=lambda m: distance_between(location, m["name"]))
    if limit:
        ranked = ranked[:limit]
    return ranked


def nearest_market_to_coordinates(latitude: float, longitude: float):
    """Resolve a raw (lat, lon) -- e.g. from browser/device GPS -- to the
    nearest known market in MARKETS, pan-India (not restricted to any one
    state). Used so granting location permission genuinely overrides the
    configurable demo default (Settings.default_demo_state) rather than the
    app silently staying pinned to the demo region regardless of where the
    user actually is.

    Returns the matching MARKETS entry, or None if MARKETS is empty.
    """
    if not MARKETS:
        return None
    return min(MARKETS, key=lambda m: haversine_km(latitude, longitude, m["latitude"], m["longitude"]))
