"""
Transport & logistics cost modelling.

This is the SINGLE authoritative transport calculator used everywhere in
CropRetain (market comparison, buyer matching, the Advisor/Assistant, the
profit calculator, FarmPool, the admin impact dashboard) -- do not add a
second one. If a new feature needs a transport estimate, call the
functions in this module.

Every figure produced here is an ESTIMATE, never an official tariff or a
live transporter quote. It models realistic small-commercial-vehicle
economics for rural India (a per-km-times-arbitrary-rate model was
replaced because it produced implausibly low totals, e.g. ~₹950 for a
1-tonne, 106 km haul -- about ₹9/km-tonne, cheaper than diesel alone would
cost). The new model prices out: vehicle/load category, fuel (at a
configurable reference diesel price), a flat per-trip driver allocation,
per-km maintenance and vehicle overhead, tolls beyond a short free radius,
an empty return leg (the vehicle doesn't carry a return load), and a
minimum-trip floor so a short dedicated haul isn't priced as if it were
free. None of these constants are official rates -- they are labelled and
documented so they can be tuned per region/date without touching the
formula shape.
"""
import hashlib
import random

from app.mock_data.locations import distance_between

# ---- Configurable reference assumptions -----------------------------------
# These are demo/reference values, not official tariffs, and are meant to be
# overridden per region/date (e.g. via env var or admin setting) rather than
# hardcoded permanently. Geography-independent: nothing below is specific to
# any one state -- the same formula runs for Maharashtra, Chhattisgarh, or
# any other state CropRetain operates in.
DIESEL_PRICE_PER_LITRE = 101.90  # INR/L, reference pump price assumption

# (max_load_kg, label, fuel_efficiency_km_per_l, driver_cost_per_trip,
#  maintenance_cost_per_km, vehicle_overhead_per_km)
# Smaller vehicles are more fuel-efficient per km but far less efficient
# per tonne-km than a bigger truck -- exactly why bulk/FarmPool shipments
# get meaningfully cheaper per-kg transport than a small solo shipment.
VEHICLE_CATEGORIES = [
    (1000, "Mini Pickup (up to 1T)",     14.0, 400.0, 2.0, 1.5),
    (3000, "Light Commercial Vehicle (1-3T)", 9.5, 600.0, 3.0, 2.5),
    (9000, "Medium Truck (3-9T)",         5.5, 900.0, 4.5, 4.0),
]

TOLL_FREE_RADIUS_KM = 20.0   # short local hauls typically don't cross a toll plaza
TOLL_RATE_PER_KM = 1.5       # INR/km beyond the free radius, one-way
MINIMUM_TRIP_CHARGE = 600.0  # floor for any dedicated trip -- driver + vehicle
                              # booking has a real minimum cost even for a
                              # very short haul; avoids implausible near-zero totals

MANDI_CHARGE_RATE = 0.015    # ~1.5% market/commission fee on transaction value
HANDLING_COST_PER_KG = 0.15  # loading/unloading/labour -- charged separately
                              # from the vehicle trip cost above, see
                              # net_profit_breakdown()

SHARED_RATE_DISCOUNT = 0.80  # bulk/full-truckload running-cost discount (see
                              # shared_transport_plan) -- applies to fuel,
                              # maintenance and overhead, NOT to the driver's
                              # flat per-trip fee, which doesn't shrink just
                              # because the truck is fuller


def _select_vehicle(quantity_kg: float):
    """Pick the smallest vehicle category that can carry the shipment.
    Falls back to the largest category for loads bigger than any single
    listed vehicle (in reality: a bigger truck or multiple trips)."""
    for cap, label, kmpl, driver_cost, maint_per_km, overhead_per_km in VEHICLE_CATEGORIES:
        if quantity_kg <= cap:
            return cap, label, kmpl, driver_cost, maint_per_km, overhead_per_km
    return VEHICLE_CATEGORIES[-1]


def estimate_transport_cost_breakdown(distance_km: float, quantity_kg: float,
                                       diesel_price_per_litre: float = DIESEL_PRICE_PER_LITRE) -> dict:
    """Full explainable breakdown of a transport estimate. Use this
    wherever the UI/Assistant needs to explain the number, not just show
    it -- e.g. answering "why is transport so cheap"."""
    one_way_km = max(distance_km, 0.1)
    cap, vehicle_label, kmpl, driver_cost, maint_per_km, overhead_per_km = _select_vehicle(quantity_kg)

    # Empty return: the vehicle carries goods one-way only, but still burns
    # fuel and accrues per-km running costs on the way back.
    round_trip_km = one_way_km * 2.0

    fuel_litres = round_trip_km / kmpl
    fuel_cost = fuel_litres * diesel_price_per_litre
    maintenance_cost = round_trip_km * maint_per_km
    overhead_cost = round_trip_km * overhead_per_km
    toll_cost = max(one_way_km - TOLL_FREE_RADIUS_KM, 0) * TOLL_RATE_PER_KM

    subtotal = fuel_cost + driver_cost + maintenance_cost + overhead_cost + toll_cost
    total = max(subtotal, MINIMUM_TRIP_CHARGE)
    minimum_applied = total > subtotal

    return {
        "total_cost": round(total, 2),
        "vehicle_category": vehicle_label,
        "one_way_distance_km": round(one_way_km, 1),
        "round_trip_distance_km": round(round_trip_km, 1),
        "fuel_efficiency_km_per_l": kmpl,
        "diesel_price_per_litre": diesel_price_per_litre,
        "fuel_cost": round(fuel_cost, 2),
        "driver_cost": round(driver_cost, 2),
        "maintenance_cost": round(maintenance_cost, 2),
        "vehicle_overhead_cost": round(overhead_cost, 2),
        "toll_cost": round(toll_cost, 2),
        "minimum_trip_charge_applied": minimum_applied,
        "label": "ESTIMATED",  # never a live transporter quote or official tariff
        "explanation": (
            f"{vehicle_label}, round-trip {round(round_trip_km, 1)} km "
            f"(one-way {round(one_way_km, 1)} km + empty return) at "
            f"{kmpl} km/L on \u20b9{diesel_price_per_litre}/L diesel, plus a "
            f"\u20b9{driver_cost:.0f} driver allocation, "
            f"\u20b9{maint_per_km}/km maintenance, \u20b9{overhead_per_km}/km vehicle "
            f"overhead" + (f", and \u20b9{TOLL_RATE_PER_KM}/km tolls beyond "
            f"{TOLL_FREE_RADIUS_KM:.0f} km" if toll_cost > 0 else "") +
            (". A minimum trip charge was applied since the calculated cost "
             "was below the realistic floor for booking a dedicated vehicle."
             if minimum_applied else ".") +
            " This is a CropRetain ESTIMATE, not a live transporter quote or "
            "official tariff."
        ),
    }


def estimate_transport_cost(distance_km: float, quantity_kg: float) -> float:
    """Backward-compatible entry point -- returns just the total, as every
    existing caller expects a plain float. Use
    estimate_transport_cost_breakdown() instead when you need to explain
    the figure to the user."""
    return estimate_transport_cost_breakdown(distance_km, quantity_kg)["total_cost"]


def estimate_mandi_charges(quantity_kg: float, price_per_kg: float) -> float:
    value = quantity_kg * price_per_kg
    return round(value * MANDI_CHARGE_RATE, 2)


def estimate_handling_cost(quantity_kg: float) -> float:
    return round(quantity_kg * HANDLING_COST_PER_KG, 2)


def net_profit_breakdown(quantity_kg: float, price_per_kg: float, distance_km: float) -> dict:
    gross = round(quantity_kg * price_per_kg, 2)
    transport = estimate_transport_cost(distance_km, quantity_kg)
    mandi = estimate_mandi_charges(quantity_kg, price_per_kg)
    handling = estimate_handling_cost(quantity_kg)
    net = round(gross - transport - mandi - handling, 2)
    return {
        "gross_revenue": gross,
        "transport_cost": transport,
        "mandi_charges": mandi,
        "handling_cost": handling,
        # Field name kept as "net_profit" for API/internal-consumer
        # stability (recommendation_engine.py, profit.py, assistant.py and
        # market.py's compare-and-sort logic all read this key) -- the
        # user-facing wording fix ("Estimated Net Return" instead of "Net
        # Profit") was already applied at the display layer (BestOption.jsx,
        # templates.py), which is the correct place for a wording change
        # that isn't also an accounting change.
        "net_profit": net,
    }


def _seed_int(*parts) -> int:
    digest = hashlib.sha256("::".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:8], 16)


def find_nearby_pool_partners(crop: str, location: str, quantity_kg: float):
    """
    Simulate other nearby farmers with the same crop available for shared
    transport (FarmPool). Deterministic per crop+location so the demo is
    stable across refreshes.

    HONESTY NOTE: these are fabricated illustrative profiles, not real
    platform users -- see `pool_partners_are_simulated`/
    `pool_partners_disclaimer` on shared_transport_plan()'s return value
    below. Every caller (currently FarmPool.jsx) must surface that
    disclaimer wherever `pool_partners` is rendered.
    """
    rng = random.Random(_seed_int("farmpool", crop, location))
    count = rng.randint(2, 4)
    partners = []
    names = ["Anita Patel", "Deepak Yadav", "Kavita Sahu", "Vikram Netam", "Farida Khan", "Prakash Rao"]
    rng.shuffle(names)
    for i in range(count):
        partners.append({
            "farmer_name": names[i % len(names)],
            "distance_from_you_km": round(rng.uniform(2, 14), 1),
            "quantity_kg": round(rng.uniform(300, 1200), 0),
        })
    return partners


def shared_transport_plan(crop: str, location: str, quantity_kg: float, destination_market: str,
                           agreed_transport_price: float = None):
    """Compute the FarmPool shared-cost allocation.

    `agreed_transport_price` is OPTIONAL and, when provided, must be the
    real server-side `TransportRequest.transporter_agreed_price` (see
    app/models.py) -- i.e. an actual negotiated price a transporter has
    agreed to for the pooled trip, never a client-supplied number. When
    given, the pool's shared cost is allocated from that real price
    instead of the transport_optimizer estimate below. The estimate
    (`shared_total_cost`/`your_shared_transport_cost` basis) is still
    computed either way and never silently discarded -- callers that want
    to show "what we estimated" alongside "what was actually agreed" can
    use `estimated_shared_transport_cost` and `cost_basis`.

    Flow this implements (see backend/HANDOFF.md / MVP_AUDIT.md):
        estimated_cost -> transporter quote -> negotiation ->
        agreed_price -> FarmPool cost allocation (this function)
    """
    distance = distance_between(location, destination_market)
    partners = find_nearby_pool_partners(crop, location, quantity_kg)

    my_individual_cost = estimate_transport_cost(distance, quantity_kg)

    total_pool_quantity = quantity_kg + sum(p["quantity_kg"] for p in partners)

    # A pooled shipment fills whichever vehicle category actually fits the
    # combined quantity (not always the biggest truck) and gets a bulk
    # discount on the running-cost components -- but not on the driver's
    # flat per-trip fee, which is the same whether the truck is half-full
    # or completely full. Using the pool's real size (rather than always
    # assuming a full big truck) matters: a big truck's much higher flat
    # driver fee can make a small pool's "shared" cost look artificially
    # worse than going alone.
    cap, vehicle_label, kmpl, driver_cost, maint_per_km, overhead_per_km = _select_vehicle(total_pool_quantity)
    round_trip_km = distance * 2.0
    fuel_cost = (round_trip_km / kmpl) * DIESEL_PRICE_PER_LITRE * SHARED_RATE_DISCOUNT
    maintenance_cost = round_trip_km * maint_per_km * SHARED_RATE_DISCOUNT
    overhead_cost = round_trip_km * overhead_per_km * SHARED_RATE_DISCOUNT
    toll_cost = max(distance - TOLL_FREE_RADIUS_KM, 0) * TOLL_RATE_PER_KM
    estimated_shared_total_cost = max(fuel_cost + driver_cost + maintenance_cost + overhead_cost + toll_cost,
                                       MINIMUM_TRIP_CHARGE)

    # ALLOCATION RULE (pre-existing, reused as-is): each participant pays
    # in proportion to their share of the pooled quantity. Before a
    # transporter agreement exists this is applied to the ESTIMATE; once a
    # real agreed price exists, the identical rule is applied to that real
    # price instead -- the rule doesn't change, only which total it's
    # applied to.
    has_agreed_price = agreed_transport_price is not None
    allocation_basis_total = float(agreed_transport_price) if has_agreed_price else estimated_shared_total_cost

    my_share = (allocation_basis_total * (quantity_kg / total_pool_quantity)
                if total_pool_quantity else allocation_basis_total)
    my_share = round(my_share, 2)
    savings = round(my_individual_cost - my_share, 2)

    estimated_my_share = (estimated_shared_total_cost * (quantity_kg / total_pool_quantity)
                           if total_pool_quantity else estimated_shared_total_cost)
    estimated_my_share = round(estimated_my_share, 2)

    return {
        "destination_market": destination_market,
        "distance_km": distance,
        "your_quantity_kg": quantity_kg,
        "pool_partners": partners,
        # HONESTY FIELD (fixes the FarmPool-shows-fake-farmers-as-real
        # regression): pool_partners above are a deterministic simulation,
        # not real platform users. FarmPool.jsx must render
        # pool_partners_disclaimer wherever it lists pool_partners -- the
        # translation key used for the actual displayed text is
        # farmpool.simulatedPartnersDisclaimer (see i18n locale files),
        # this string is a backend-side fallback/log value only.
        "pool_partners_are_simulated": True,
        "pool_partners_disclaimer": "Demo data -- nearby farmer profiles shown here are simulated.",
        "total_pool_quantity_kg": round(total_pool_quantity, 1),
        "vehicle_category": vehicle_label,
        "your_individual_transport_cost": my_individual_cost,
        # Real transport-optimizer ESTIMATE for the pooled trip and this
        # farmer's estimated share of it -- always present, never
        # overwritten by an agreed price, so the UI can always show
        # "what we estimated" even after a real price is agreed.
        "estimated_shared_transport_cost": estimated_shared_total_cost,
        "your_estimated_shared_share": estimated_my_share,
        # The amount this farmer actually owes under the current basis
        # (agreed price if one exists, otherwise the estimate -- kept as
        # `your_shared_transport_cost` for backward compatibility with
        # existing frontend/tests).
        "your_shared_transport_cost": my_share,
        "estimated_savings": max(savings, 0),
        "savings_pct": round((savings / my_individual_cost) * 100, 1) if my_individual_cost else 0,
        # AGREED once a real transporter_agreed_price was supplied and used
        # as the allocation basis; ESTIMATED otherwise. Frontend/Assistant
        # must never present ESTIMATED figures as if they were AGREED.
        "cost_basis": "AGREED" if has_agreed_price else "ESTIMATED",
        "transporter_agreed_price": round(float(agreed_transport_price), 2) if has_agreed_price else None,
        "label": "AGREED" if has_agreed_price else "ESTIMATED",
    }
