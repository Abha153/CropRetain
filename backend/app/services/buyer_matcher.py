"""
Smart Buyer Matching engine — Phase 5 upgrade.

Produces a transparent, explainable match score (0-100) for each candidate
buyer. Factors:
  - Price attractiveness (vs market modal)
  - Buyer reliability score
  - Payment history score
  - Distance / transport feasibility
  - Quantity compatibility with buyer type + active demands
  - Crop interest + active demand match
  - Buyer verification status (bonus)
  - Active demand deadline fit

Every score comes with a per-factor breakdown and human-readable reasons.
No black-box output.

Backward compatible: score_buyers_for_listing() signature unchanged.
New: score_buyers_for_lot() for Lot objects.
     score_buyers_extended() accepts optional active_demands list.
"""
import datetime as dt

from app.mock_data.locations import distance_between
from app.services.transport_optimizer import estimate_transport_cost, estimate_handling_cost

BUYER_TYPE_PRICE_MULTIPLIER = {
    "processor": 0.95,
    "retailer": 1.06,
    "wholesaler": 0.90,
    "exporter": 1.14,
    "fpo": 1.00,
}

QUALITY_MULTIPLIER = {"A": 1.08, "B": 1.00, "C": 0.90}

IDEAL_QUANTITY_RANGE_KG = {
    "retailer": (50, 1200),
    "wholesaler": (500, 6000),
    "processor": (800, 12000),
    "exporter": (1500, 25000),
    "fpo": (0, 10 ** 7),
}

GRADE_ORDER = {"A": 3, "B": 2, "C": 1}


def _score_one_buyer(
    buyer,
    crop: str,
    quality_grade: str,
    quantity_kg: float,
    location: str,
    available_date_str: str,
    market_modal_price_per_kg: float,
    active_demands: list,         # BuyerDemand rows for this buyer (may be empty)
) -> dict:
    """
    Core scoring function used by both listing-based and lot-based matchers.
    Returns a full result dict including explainable breakdown.
    """
    distance = distance_between(location, buyer.location)
    type_mult = BUYER_TYPE_PRICE_MULTIPLIER.get(buyer.buyer_type, 1.0)
    quality_mult = QUALITY_MULTIPLIER.get(quality_grade, 1.0)
    estimated_price_per_kg = round(market_modal_price_per_kg * type_mult * quality_mult, 2)

    transport_cost = estimate_transport_cost(distance, quantity_kg)
    handling_cost = estimate_handling_cost(quantity_kg)
    gross = estimated_price_per_kg * quantity_kg
    net_profit = round(gross - transport_cost - handling_cost, 2)

    # --- Individual factor scores ---
    # 1. Price attractiveness
    price_score = min(100.0, (estimated_price_per_kg / max(market_modal_price_per_kg * 1.16, 0.01)) * 100)

    # 2. Reliability
    reliability_score = buyer.reliability_score

    # 3. Payment reliability
    payment_score = buyer.payment_history_score

    # 4. Distance
    distance_score = max(8.0, 100.0 - distance * 0.35)

    # 5. Quantity fit (buyer type range)
    lo, hi = IDEAL_QUANTITY_RANGE_KG.get(buyer.buyer_type, (0, 10 ** 7))
    qty_fit_score = 100.0 if lo <= quantity_kg <= hi else 55.0

    # 6. Crop interest
    crop_interest = getattr(buyer, "crops_of_interest", None) or []
    crop_match = crop in crop_interest
    crop_score = 100.0 if crop_match else 42.0

    # 7. Verification bonus (Phase 5 addition)
    is_verified = buyer.verification_status == "verified"
    verification_score = 100.0 if is_verified else 50.0

    # 8. Active demand match (Phase 5 addition)
    # Check if this buyer has an active demand that this lot/listing can fill
    demand_match_score = 0.0
    matched_demand = None
    for demand in active_demands:
        if demand.crop.lower() != crop.lower():
            continue
        # Quantity compatibility
        qty_min = demand.minimum_quantity_kg or (demand.required_quantity_kg * 0.5)
        qty_max = demand.maximum_quantity_kg or (demand.required_quantity_kg * 1.5)
        if not (qty_min <= quantity_kg <= qty_max):
            continue
        # Grade compatibility
        if demand.quality_grade:
            lot_grade_val = GRADE_ORDER.get(quality_grade, 0)
            req_grade_val = GRADE_ORDER.get(demand.quality_grade, 0)
            if lot_grade_val < req_grade_val:
                continue
        # Price: farmer price vs buyer target
        if demand.target_price_per_kg:
            # estimated_price >= target is good for farmer; near target is very good
            price_ratio = estimated_price_per_kg / demand.target_price_per_kg
            dem_price_score = min(100.0, price_ratio * 90.0)
        else:
            dem_price_score = 80.0
        # Deadline: available_date must be before delivery_deadline
        if demand.delivery_deadline and available_date_str:
            try:
                avail = dt.date.fromisoformat(available_date_str)
                deadline = dt.date.fromisoformat(demand.delivery_deadline)
                if avail > deadline:
                    continue  # Won't make the deadline
                days_buffer = (deadline - avail).days
                deadline_score = min(100.0, days_buffer * 5 + 60)
            except ValueError:
                deadline_score = 70.0
        else:
            deadline_score = 70.0

        score_for_this_demand = (dem_price_score * 0.5 + deadline_score * 0.3 + 100.0 * 0.2)
        if score_for_this_demand > demand_match_score:
            demand_match_score = score_for_this_demand
            matched_demand = demand

    # Demand match: 0 = no active demand, 100 = perfect demand match
    # Give partial credit just for being a verified active buyer
    if demand_match_score == 0:
        demand_match_score = 30.0  # baseline: buyer might buy even without a posted demand

    # --- Composite (weights sum to 1.0) ---
    # Added verification (0.05) and demand_match (0.10); reduced price slightly
    composite = (
        0.25 * price_score +
        0.18 * reliability_score +
        0.14 * payment_score +
        0.13 * distance_score +
        0.09 * qty_fit_score +
        0.08 * crop_score +
        0.08 * demand_match_score +
        0.05 * verification_score
    )

    # --- Human-readable reasons ---
    reasons = []
    if matched_demand:
        reasons.append(f"Active demand for {quantity_kg:,.0f} kg {crop} at ₹{matched_demand.target_price_per_kg * 100 if matched_demand.target_price_per_kg else 'N/A'}/q")
    if crop_match:
        reasons.append(f"Actively buying {crop}")
    if is_verified:
        reasons.append("Verified buyer (documents checked)")
    if distance <= 40:
        reasons.append(f"Nearby — {distance} km away")
    if buyer.reliability_score >= 85:
        reasons.append("Strong reliability track record")
    if buyer.payment_history_score >= 85:
        reasons.append("Reliable, on-time payment history")
    if qty_fit_score >= 100:
        reasons.append("Quantity fits their typical order size")
    if net_profit > 0:
        reasons.append(f"Est. net revenue ₹{net_profit:,.0f} after transport & handling")
    if not reasons:
        reasons.append("General market match based on crop and location")

    return {
        "buyer_id": buyer.id,
        "company_name": buyer.company_name,
        "buyer_type": buyer.buyer_type,
        "location": buyer.location,
        "verification_status": buyer.verification_status,
        "reliability_score": buyer.reliability_score,
        "payment_history_score": buyer.payment_history_score,
        "distance_km": distance,
        "estimated_price_per_kg": estimated_price_per_kg,
        "estimated_transport_cost": transport_cost,
        "estimated_net_profit": net_profit,
        "matched_demand_id": matched_demand.id if matched_demand else None,
        "match_score": round(min(composite, 99.5), 1),
        # Per-factor breakdown (Phase 5 — explainable score)
        "score_breakdown": {
            "price_attractiveness": round(price_score, 1),
            "buyer_reliability": round(reliability_score, 1),
            "payment_reliability": round(payment_score, 1),
            "location_proximity": round(distance_score, 1),
            "quantity_compatibility": round(qty_fit_score, 1),
            "crop_interest": round(crop_score, 1),
            "active_demand_match": round(demand_match_score, 1),
            "verification": round(verification_score, 1),
        },
        "reasons": reasons[:5],
    }


def score_buyers_for_listing(listing, buyers, market_modal_price_per_kg: float,
                               active_demands_by_buyer: dict = None):
    """
    Score all buyers against a CropListing.
    active_demands_by_buyer: optional {buyer_id: [BuyerDemand, ...]} lookup.
    Backward compatible — existing callers pass no active_demands_by_buyer.
    """
    results = []
    available_date = getattr(listing, 'available_date', None) or ''
    for buyer in buyers:
        demands = (active_demands_by_buyer or {}).get(buyer.id, [])
        result = _score_one_buyer(
            buyer=buyer,
            crop=listing.crop,
            quality_grade=listing.quality_grade,
            quantity_kg=listing.quantity_kg,
            location=listing.location,
            available_date_str=available_date,
            market_modal_price_per_kg=market_modal_price_per_kg,
            active_demands=demands,
        )
        results.append(result)

    results.sort(key=lambda r: r["match_score"], reverse=True)
    for idx, r in enumerate(results, start=1):
        r["rank"] = idx
    return results


def score_buyers_for_lot(lot, buyers, market_modal_price_per_kg: float,
                          active_demands_by_buyer: dict = None):
    """
    Score all buyers against a Lot object (Phase 5 addition).
    Lot uses .grade instead of .quality_grade; .expected_price instead of
    .expected_price_per_kg.
    """
    results = []
    available_date = getattr(lot, 'available_date', None) or ''
    for buyer in buyers:
        demands = (active_demands_by_buyer or {}).get(buyer.id, [])
        result = _score_one_buyer(
            buyer=buyer,
            crop=lot.crop,
            quality_grade=lot.grade,
            quantity_kg=lot.quantity_kg,
            location=lot.location,
            available_date_str=available_date,
            market_modal_price_per_kg=market_modal_price_per_kg,
            active_demands=demands,
        )
        results.append(result)

    results.sort(key=lambda r: r["match_score"], reverse=True)
    for idx, r in enumerate(results, start=1):
        r["rank"] = idx
    return results
