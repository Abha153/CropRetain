"""
Mock crop catalogue. base_price_per_quintal reflects a realistic modal mandi
price (INR per 100kg quintal) used as the seed for historical price
generation. volatility drives how much daily prices wiggle. In production,
base prices would be replaced by a live Agmarknet/eNAM feed.
"""

CROPS = [
    {
        "name": "Tomato", "emoji": "🍅", "category": "vegetable",
        "base_price_per_quintal": 2200, "volatility": 0.09, "unit": "quintal",
        "perishability": "high", "shelf_life_days": 5,
    },
    {
        "name": "Paddy (Rice)", "emoji": "🌾", "category": "grain",
        "base_price_per_quintal": 2100, "volatility": 0.02, "unit": "quintal",
        "perishability": "low", "shelf_life_days": 365,
    },
    {
        "name": "Wheat", "emoji": "🌾", "category": "grain",
        "base_price_per_quintal": 2300, "volatility": 0.02, "unit": "quintal",
        "perishability": "low", "shelf_life_days": 365,
    },
    {
        "name": "Potato", "emoji": "🥔", "category": "vegetable",
        "base_price_per_quintal": 1400, "volatility": 0.07, "unit": "quintal",
        "perishability": "medium", "shelf_life_days": 60,
    },
    {
        "name": "Onion", "emoji": "🧅", "category": "vegetable",
        "base_price_per_quintal": 1800, "volatility": 0.11, "unit": "quintal",
        "perishability": "medium", "shelf_life_days": 90,
    },
    {
        "name": "Soybean", "emoji": "🌱", "category": "oilseed",
        "base_price_per_quintal": 4200, "volatility": 0.04, "unit": "quintal",
        "perishability": "low", "shelf_life_days": 270,
    },
    {
        "name": "Maize", "emoji": "🌽", "category": "grain",
        "base_price_per_quintal": 2000, "volatility": 0.03, "unit": "quintal",
        "perishability": "low", "shelf_life_days": 270,
    },
    {
        "name": "Chana (Gram)", "emoji": "🫘", "category": "pulse",
        "base_price_per_quintal": 5300, "volatility": 0.03, "unit": "quintal",
        "perishability": "low", "shelf_life_days": 300,
    },
    {
        "name": "Groundnut", "emoji": "🥜", "category": "oilseed",
        "base_price_per_quintal": 5800, "volatility": 0.04, "unit": "quintal",
        "perishability": "low", "shelf_life_days": 240,
    },
    {
        "name": "Sugarcane", "emoji": "🎋", "category": "cash crop",
        "base_price_per_quintal": 350, "volatility": 0.015, "unit": "quintal",
        "perishability": "medium", "shelf_life_days": 15,
    },
]

CROP_BY_NAME = {c["name"]: c for c in CROPS}


def crop_names():
    return [c["name"] for c in CROPS]
