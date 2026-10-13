from fastapi import APIRouter

from app import schemas

router = APIRouter(prefix="/profit", tags=["profit"])


def _simulate_one(s: schemas.ProfitScenario) -> dict:
    revenue = round(s.quantity_kg * s.selling_price_per_kg, 2)
    total_cost = round(
        s.transport_cost + s.labour_cost + s.packaging_cost + s.storage_cost + s.other_cost, 2
    )
    net_profit = round(revenue - total_cost, 2)
    per_kg_profit = round(net_profit / s.quantity_kg, 2) if s.quantity_kg else 0
    return {
        "label": s.label, "crop": s.crop, "quantity_kg": s.quantity_kg,
        "revenue": revenue, "total_cost": total_cost, "net_profit": net_profit,
        "net_profit_per_kg": per_kg_profit,
        "cost_breakdown": {
            "transport_cost": s.transport_cost, "labour_cost": s.labour_cost,
            "packaging_cost": s.packaging_cost, "storage_cost": s.storage_cost,
            "other_cost": s.other_cost,
        },
    }


@router.post("/simulate")
def simulate(payload: schemas.ProfitScenario):
    return _simulate_one(payload)


@router.post("/compare")
def compare(payload: schemas.ProfitCompareRequest):
    results = [_simulate_one(s) for s in payload.scenarios]
    if not results:
        return {"scenarios": [], "best_option": None}
    best = max(results, key=lambda r: r["net_profit"])
    for r in results:
        r["is_best"] = r["label"] == best["label"]
    return {"scenarios": results, "best_option": best["label"]}
