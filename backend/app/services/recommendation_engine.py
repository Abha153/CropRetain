"""
AgriAdvisor recommendation engine.

Combines market comparison, price forecast, arrivals (supply) trend, and a
simulated weather signal into a single, explainable selling recommendation.
Every number shown to the farmer traces back to a visible factor -- the
engine never emits a recommendation without the reasons behind it.
"""
import hashlib
import random
import datetime as dt


def _seeded_random(*parts) -> random.Random:
    digest = hashlib.sha256("::".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(digest[:8], 16))


def simulate_weather_risk(crop: str, location: str):
    today = dt.date.today().isoformat()
    rng = _seeded_random("weather", crop, location, today)
    r = rng.random()
    if r < 0.6:
        return "Low", "Clear skies expected in the region; little to no transport disruption."
    if r < 0.86:
        return "Medium", "Isolated showers possible; minor road delays may occur."
    return "High", "Heavy rain forecast in the region; transport delays and spoilage risk are elevated."


def resolve_weather_risk(crop: str, location: str):
    """
    Preferred weather-risk source for build_recommendation(). Tries real
    weather data (CropRetain Demo Dataset seeded forecast, or LIVE
    Open-Meteo if lat/lon were available -- this function is only called
    with a location NAME, so in practice it resolves the seeded fallback
    when the location matches a known seeded town, per
    app/services/weather_service.py). If no weather data exists for this
    location, falls back to the original simulate_weather_risk() rather
    than breaking recommendation generation entirely -- see that
    function's docstring history: it is intentionally NOT deleted.
    """
    from app.services import weather_service  # local import: avoids a
    # hard dependency from every recommendation_engine caller/test on the
    # weather module when it isn't needed.
    result = weather_service.get_weather(None, None, location)
    if result["status"] in ("LIVE", "DEMO"):
        derived = weather_service.derive_weather_risk(result)
        if derived:
            return derived
    return simulate_weather_risk(crop, location)


def supply_demand_levels(arrivals_recent_avg: float, arrivals_baseline_avg: float):
    if arrivals_baseline_avg <= 0:
        return "Medium", "Medium"
    ratio = arrivals_recent_avg / arrivals_baseline_avg
    if ratio < 0.85:
        supply, demand = "Low", "High"
    elif ratio > 1.15:
        supply, demand = "High", "Low"
    else:
        supply, demand = "Medium", "Medium"
    return supply, demand


def transport_cost_label(transport_cost: float, gross_revenue: float) -> str:
    if gross_revenue <= 0:
        return "Moderate"
    ratio = transport_cost / gross_revenue
    if ratio < 0.03:
        return "Low"
    if ratio < 0.08:
        return "Moderate"
    return "High"


def primary_risk_text(weather_risk, trend, supply_level):
    if weather_risk == "High":
        return "Heavy rain forecast may disrupt transport and increase spoilage risk."
    if supply_level == "High":
        return "High arrivals in nearby markets may soften prices over the next few days."
    if trend == "decreasing":
        return "Prices have been trending downward recently."
    return "Moderate price volatility is possible -- avoid committing 100% of stock at once."


def build_recommendation(crop_info: dict, quantity_kg: float, quality_grade: str, location: str,
                          market_options: list, forecast: dict,
                          arrivals_recent_avg: float, arrivals_baseline_avg: float):
    best_market = max(market_options, key=lambda m: m["net_profit"])
    supply_level, demand_level = supply_demand_levels(arrivals_recent_avg, arrivals_baseline_avg)
    weather_risk, weather_note = resolve_weather_risk(crop_info["name"], location)
    trend = forecast["trend_direction"]
    confidence = forecast["confidence_pct"]
    perishable = crop_info["perishability"] == "high"

    if perishable:
        sell_now_pct, wait_days = 100, 0
        wait_rationale = (
            f"{crop_info['name']} is highly perishable (shelf life ~{crop_info['shelf_life_days']} days). "
            "Selling promptly avoids spoilage losses even if prices might firm up slightly later."
        )
    elif trend == "increasing" and demand_level in ("Medium", "High") and weather_risk != "High":
        sell_now_pct, wait_days = 55, 3
        wait_rationale = (
            "Prices are trending upward with healthy demand, so holding part of your stock for a "
            "few more days could capture a better price -- if you have safe storage available."
        )
    elif trend == "decreasing" or weather_risk == "High":
        sell_now_pct, wait_days = 90, 0
        wait_rationale = "Prices are softening or weather could disrupt transport -- selling soon protects your revenue."
    else:
        sell_now_pct, wait_days = 75, 1
        wait_rationale = "The market looks stable. Selling most of your stock now is the lower-risk choice."

    hold_pct = 100 - sell_now_pct
    recommendation_text = f"Sell {sell_now_pct}% of your {quantity_kg:.0f} kg {crop_info['name']} now in {best_market['market']}"
    if hold_pct > 0:
        recommendation_text += f", and hold the remaining {hold_pct}% for about {wait_days} day(s) if you can store it safely."
    else:
        recommendation_text += "."

    factors = [
        {"label": "Demand", "value": demand_level, "icon": "📈"},
        {"label": "Supply / Arrivals", "value": supply_level, "icon": "📦"},
        {"label": "Weather Risk", "value": weather_risk, "icon": "🌧️" if weather_risk != "Low" else "☀️", "note": weather_note},
        {"label": "Transport Cost", "value": transport_cost_label(best_market["transport_cost"], best_market["gross_revenue"]), "icon": "🚚"},
        {"label": "Price Trend", "value": trend.capitalize(), "icon": "📊"},
    ]

    return {
        "recommended_market": best_market["market"],
        "recommendation_text": recommendation_text,
        "sell_now_pct": sell_now_pct,
        "hold_pct": hold_pct,
        "wait_days": wait_days,
        "wait_rationale": wait_rationale,
        "confidence_pct": confidence,
        "confidence_label": "High" if confidence >= 70 else "Medium" if confidence >= 50 else "Low",
        "expected_price_range": {
            "low": forecast["predicted_price_low"],
            "high": forecast["predicted_price_high"],
        },
        "factors": factors,
        "primary_risk": primary_risk_text(weather_risk, trend, supply_level),
        "market_options_considered": market_options,
    }
