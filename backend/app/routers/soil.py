"""
Soil Advisor: explainable crop-suitability screening linked to the existing
market-comparison / net-return logic.

* Suitability comes from services/soil_advisor.py (cited rules only).
* Every money figure comes from routers.market._compare_markets_core, which
  itself uses services.transport_optimizer.net_profit_breakdown -- this
  router adds NO financial calculation of its own.
* Auth: unauthenticated, matching /market/compare and /advisor/recommend,
  which are the endpoints this builds on. It stores nothing.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.errors import AppError
from app.mock_data.locations import MARKET_BY_NAME
from app.routers.market import _compare_markets_core
from app.services.soil_advisor import (
    evaluate_all, sources_for, REGIONAL_LIMITATION,
    DATA_QUALITY_ESTIMATED, DATA_QUALITY_UNAVAILABLE, INPUT_PROVENANCE,
)
from app.services.soil_crop_rules import TEXTURE_CLASSES, SEASONS, IRRIGATION_LEVELS
from app.services.soil_health import rate_soil_health

router = APIRouter(prefix="/soil", tags=["soil"])

FINANCIAL_ASSUMPTIONS = [
    "Estimated net return = value of the quantity you entered at the best-scoring market, "
    "minus estimated transport, mandi charges and handling (existing CropRetain estimates).",
    "It does NOT include seed, fertiliser, labour, irrigation or other cultivation costs, "
    "and it is not a yield forecast or a profit guarantee.",
    "Prices are labelled LIVE or DEMO per market; transport costs are estimates, not quotes.",
]


@router.get("/options")
def soil_options():
    """Allowed input values, so the UI never hard-codes them."""
    return {
        "soil_texture": TEXTURE_CLASSES, "season": SEASONS, "irrigation": IRRIGATION_LEVELS,
        "locations": sorted(MARKET_BY_NAME.keys()),
    }


def _financial_for(crop: str, quantity_kg: float, location: str, db: Session) -> dict:
    try:
        cmp = _compare_markets_core(crop, quantity_kg, location, 6, db)
    except HTTPException:
        return {"data_quality": DATA_QUALITY_UNAVAILABLE, "available": False,
                "reason_code": "MARKET_COMPARISON_FAILED"}
    if cmp.get("insufficient_data") or not cmp.get("options"):
        return {"data_quality": DATA_QUALITY_UNAVAILABLE, "available": False,
                "reason_code": "NO_MARKET_DATA"}
    best = cmp["options"][0]  # _compare_markets_core sorts by net_profit, descending
    return {
        "data_quality": DATA_QUALITY_ESTIMATED,
        "available": True,
        "best_market": best["market"],
        "distance_km": best["distance_km"],
        "modal_price_per_kg": best["modal_price_per_kg"],
        "price_data_label": "LIVE" if best["data_source"] == "live" else "DEMO",
        "price_as_of": best["as_of_date"],
        "gross_revenue": best["gross_revenue"],
        "transport_cost": best["transport_cost"],
        "mandi_charges": best["mandi_charges"],
        "handling_cost": best["handling_cost"],
        "estimated_net_return": best["net_profit"],
        "gain_vs_nearest_market": cmp["profit_gain_vs_nearest_market"],
        "market_data_summary": cmp["data_source_summary"],
    }


@router.post("/health-check")
def health_check(payload: schemas.SoilHealthRequest):
    """Rate soil-test values (organic carbon, N, P, K, pH, EC) against the
    cited TNAU rating chart. Stores nothing, computes no money figures."""
    values = payload.model_dump()
    if all(v is None for v in values.values()):
        raise AppError(400, "SOIL_HEALTH_NO_INPUT",
                       "Provide at least one soil-test value: organic_carbon, nitrogen, "
                       "phosphorus, potassium, ph or ec.")
    result = rate_soil_health(**values)
    result["regional_limitation"] = REGIONAL_LIMITATION
    return result


@router.post("/advise")
def advise(payload: schemas.SoilAdvisorRequest, db: Session = Depends(get_db)):
    if payload.soil_texture is not None and payload.soil_texture not in TEXTURE_CLASSES:
        raise AppError(422, "SOIL_INVALID_TEXTURE",
                       f"soil_texture must be one of: {', '.join(TEXTURE_CLASSES)}")
    if payload.season is not None and payload.season not in SEASONS:
        raise AppError(422, "SOIL_INVALID_SEASON",
                       f"season must be one of: {', '.join(SEASONS)}")
    if payload.irrigation is not None and payload.irrigation not in IRRIGATION_LEVELS:
        raise AppError(422, "SOIL_INVALID_IRRIGATION",
                       f"irrigation must be one of: {', '.join(IRRIGATION_LEVELS)}")

    test_values = {
        "organic_carbon": payload.organic_carbon, "nitrogen": payload.nitrogen,
        "phosphorus": payload.phosphorus, "potassium": payload.potassium,
        "ph": payload.soil_ph, "ec": payload.ec,
    }
    has_test_value = any(v is not None for v in test_values.values())
    soil_inputs = (payload.soil_ph, payload.soil_texture, payload.season)
    if all(v is None for v in soil_inputs) and not has_test_value:
        raise AppError(400, "SOIL_NO_INPUT",
                       "Provide at least one of soil_ph, soil_texture, season or a soil-test "
                       "value (organic_carbon, nitrogen, phosphorus, potassium, ec).")

    want_money = payload.quantity_kg is not None or payload.location is not None
    if want_money:
        if payload.quantity_kg is None or payload.location is None:
            raise AppError(400, "SOIL_FINANCIAL_INPUT_INCOMPLETE",
                           "quantity_kg and location must be given together.")
        if payload.location not in MARKET_BY_NAME:
            raise AppError(400, "SOIL_UNKNOWN_LOCATION",
                           "location must be a market/location name known to CropRetain "
                           "(see GET /soil/options).")

    result = evaluate_all(
        soil_ph=payload.soil_ph, soil_texture=payload.soil_texture,
        season=payload.season, irrigation=payload.irrigation,
    )

    used_sources = set()
    recommendations = []
    for r in result["ranked"]:
        used_sources.update(r["source_ids"])
        r = dict(r)
        if want_money:
            r["financial"] = _financial_for(r["crop"], payload.quantity_kg, payload.location, db)
        else:
            r["financial"] = {"data_quality": DATA_QUALITY_UNAVAILABLE, "available": False,
                              "reason_code": "QUANTITY_OR_LOCATION_NOT_PROVIDED"}
        recommendations.append(r)

    soil_health = rate_soil_health(**test_values) if has_test_value else None
    sources = sources_for(used_sources)
    if soil_health and soil_health["sources"]:
        sources = sources + [s for s in soil_health["sources"]
                             if s["id"] not in {x["id"] for x in sources}]

    return {
        "data_quality": (DATA_QUALITY_ESTIMATED if (recommendations or soil_health)
                         else DATA_QUALITY_UNAVAILABLE),
        "inputs": {
            "soil_ph": payload.soil_ph, "soil_texture": payload.soil_texture,
            "season": payload.season, "irrigation": payload.irrigation,
            "quantity_kg": payload.quantity_kg, "location": payload.location,
            "organic_carbon": payload.organic_carbon, "nitrogen": payload.nitrogen,
            "phosphorus": payload.phosphorus, "potassium": payload.potassium,
            "ec": payload.ec,
            "provenance": INPUT_PROVENANCE,
        },
        "method": "RULE_CHECK_AGAINST_CITED_GUIDANCE",
        "recommendations": recommendations,
        "unavailable_crops": result["unavailable"],
        "soil_health": soil_health,
        "sources": sources,
        "regional_limitation": REGIONAL_LIMITATION,
        "financial_assumptions": FINANCIAL_ASSUMPTIONS if want_money else [],
        "not_covered": [
            "Photo- or sensor-based soil detection",
            "Crop-specific nutrient requirements and fertiliser doses",
            "District-specific rules",
        ],
    }
