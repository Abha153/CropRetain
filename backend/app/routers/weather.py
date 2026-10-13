"""
Weather endpoints. Thin HTTP layer over app/services/weather_service.py --
all live-fetch/fallback/validation logic lives there, not here.

Two entry points:
  GET /weather/farmer   -- auth required, uses the signed-in farmer's own
                            saved location/coordinates (Farmer.location,
                            Farmer.latitude, Farmer.longitude).
  GET /weather           -- public, ad-hoc lookup by explicit lat/lon and/or
                            a location name. This is what the "Use My
                            Location" GPS flow calls with the browser's
                            fresh coordinates, which may differ from the
                            farmer's saved profile location -- see
                            frontend/src/utils/location.js.

Weather for a set of coordinates is not private data (the same public
market/location data other CropRetain endpoints like /market/nearest-market
already expose without auth), so /weather intentionally follows that same
existing precedent rather than inventing a new ownership rule for it.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth_utils import require_farmer
from app.services import weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/farmer")
def farmer_weather(current=Depends(require_farmer)):
    farmer = current
    lat = farmer.latitude if farmer.latitude else None
    lon = farmer.longitude if farmer.longitude else None
    return weather_service.get_weather(lat, lon, farmer.location)


@router.get("")
def weather_lookup(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    location: Optional[str] = Query(None),
):
    return weather_service.get_weather(latitude, longitude, location)
