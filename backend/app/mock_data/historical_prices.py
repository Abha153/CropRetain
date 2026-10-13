"""
Deterministic historical mandi price generator.

Real Agmarknet/eNAM price feeds are not reachable from a hackathon sandbox,
so we synthesize a realistic 60-day daily price history per (crop, market)
pair using a seeded random walk. Because the seed is derived from the crop
and market names, the same crop/market pair always produces the same
history for a given run of seed_data.py, which keeps the demo stable and
reproducible.
"""
import datetime as dt
import hashlib
import random

from app.mock_data.crops import CROPS
from app.mock_data.locations import MARKETS

HISTORY_DAYS = 60

# Markets closer to state capital / bigger consumption hubs trend a little
# higher (more demand, more buyers). Remote markets trend a little lower.
MARKET_MULTIPLIER = {
    "Raipur": 1.06,
    "Durg": 1.03,
    "Bilaspur": 1.00,
    "Bilha": 0.97,
    "Korba": 0.99,
    "Raigarh": 0.98,
    "Rajnandgaon": 1.01,
    "Mahasamund": 0.99,
    "Ambikapur": 0.94,
    "Jagdalpur": 0.92,
}


def _seed_for(crop: str, market: str) -> int:
    digest = hashlib.sha256(f"{crop}::{market}".encode()).hexdigest()
    return int(digest[:8], 16)


def generate_history(crop: dict, market_name: str, days: int = HISTORY_DAYS):
    rng = random.Random(_seed_for(crop["name"], market_name))
    multiplier = MARKET_MULTIPLIER.get(market_name, 1.0)
    price = crop["base_price_per_quintal"] * multiplier * rng.uniform(0.96, 1.04)
    vol = crop["volatility"]

    today = dt.date.today()
    history = []
    for i in range(days, 0, -1):
        day = today - dt.timedelta(days=i)
        # gentle weekly demand cycle (weekend markets a touch busier) plus
        # a slow seasonal drift plus daily noise
        weekday_factor = 1.0 + (0.015 if day.weekday() in (5, 6) else 0.0)
        seasonal_drift = 1.0 + 0.0006 * math_sin_like(i)
        noise = 1.0 + rng.uniform(-vol, vol)
        price = max(price * weekday_factor * seasonal_drift * noise, price * 0.85)
        modal = round(price, 2)
        spread = modal * rng.uniform(0.03, 0.08)
        min_p = round(max(modal - spread, 1), 2)
        max_p = round(modal + spread, 2)
        arrivals = round(rng.uniform(20, 400) * (1.3 if crop["category"] == "vegetable" else 1.0), 1)
        history.append({
            "date": day.isoformat(),
            "min_price": min_p,
            "max_price": max_p,
            "modal_price": modal,
            "arrivals_tonnes": arrivals,
        })
    return history


def math_sin_like(i: int) -> float:
    """Tiny deterministic pseudo-cyclical wave without importing numpy."""
    import math
    return math.sin(i / 6.0)


def generate_all_history():
    """Yield (crop_name, market_name, history_list) for every crop/market pair."""
    for crop in CROPS:
        for market in MARKETS:
            yield crop["name"], market["name"], generate_history(crop, market["name"])
