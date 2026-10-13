"""Phase 5 validation: buyer matching upgrade."""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PASS = []; FAIL = []

def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL.append((name, str(e)))
        print(f"  FAIL  {name}: {e}")

# 1. New function imports
def test_imports():
    from app.services.buyer_matcher import (
        score_buyers_for_listing, score_buyers_for_lot, _score_one_buyer
    )
    from app.routers.matching import match_buyers, match_buyers_for_lot, _build_demands_lookup

check("Phase 5 imports", test_imports)

# 2. score_buyers_for_listing backward compat (no demands passed)
def test_listing_backward_compat():
    from app.services.buyer_matcher import score_buyers_for_listing

    class FakeBuyer:
        id = 1; company_name = "Test Co"; buyer_type = "wholesaler"
        location = "Bilaspur"; verification_status = "verified"
        reliability_score = 88.0; payment_history_score = 90.0
        crops_of_interest = ["Tomato"]

    class FakeListing:
        crop = "Tomato"; quality_grade = "A"; quantity_kg = 2000
        location = "Bilaspur"; available_date = "2026-09-01"

    # Old call signature (no active_demands_by_buyer) must still work
    results = score_buyers_for_listing(FakeListing(), [FakeBuyer()], 28.0)
    assert len(results) == 1
    assert "match_score" in results[0]
    assert "score_breakdown" in results[0], "score_breakdown missing from result"
    assert "rank" in results[0]
    bd = results[0]["score_breakdown"]
    for key in ["price_attractiveness","buyer_reliability","payment_reliability",
                "location_proximity","quantity_compatibility","crop_interest",
                "active_demand_match","verification"]:
        assert key in bd, f"score_breakdown missing: {key}"

check("Listing matching backward compat + breakdown", test_listing_backward_compat)

# 3. score_buyers_for_lot
def test_lot_matching():
    from app.services.buyer_matcher import score_buyers_for_lot

    class FakeBuyer:
        id = 1; company_name = "AgriExport India"; buyer_type = "exporter"
        location = "Durg"; verification_status = "verified"
        reliability_score = 81.0; payment_history_score = 84.0
        crops_of_interest = ["Soybean"]

    class FakeLot:
        crop = "Soybean"; grade = "A"; quantity_kg = 4000
        location = "Bilaspur"; available_date = "2026-09-10"

    results = score_buyers_for_lot(FakeLot(), [FakeBuyer()], 50.5)
    assert len(results) == 1
    r = results[0]
    assert "match_score" in r
    assert r["match_score"] > 0
    assert "score_breakdown" in r
    assert r["rank"] == 1

check("Lot-based buyer matching", test_lot_matching)

# 4. Demand match raises score
def test_demand_boosts_score():
    from app.services.buyer_matcher import score_buyers_for_lot

    class FakeBuyer:
        id = 99; company_name = "Buyer With Demand"; buyer_type = "wholesaler"
        location = "Bilaspur"; verification_status = "verified"
        reliability_score = 85.0; payment_history_score = 88.0
        crops_of_interest = ["Soybean"]

    class FakeBuyerNoDemand:
        id = 100; company_name = "Buyer No Demand"; buyer_type = "wholesaler"
        location = "Bilaspur"; verification_status = "verified"
        reliability_score = 85.0; payment_history_score = 88.0
        crops_of_interest = ["Soybean"]

    class FakeDemand:
        id = 1; crop = "Soybean"; status = "ACTIVE"
        required_quantity_kg = 4000.0; minimum_quantity_kg = 2000.0; maximum_quantity_kg = 6000.0
        target_price_per_kg = 50.0; quality_grade = "A"
        delivery_deadline = "2026-12-31"; delivery_location = "Bilaspur"

    class FakeLot:
        crop = "Soybean"; grade = "A"; quantity_kg = 4000
        location = "Bilaspur"; available_date = "2026-09-10"

    # Buyer with demand vs buyer without
    results_with = score_buyers_for_lot(FakeLot(), [FakeBuyer()], 50.5,
                                         {99: [FakeDemand()]})
    results_without = score_buyers_for_lot(FakeLot(), [FakeBuyerNoDemand()], 50.5, {})

    score_with = results_with[0]["match_score"]
    score_without = results_without[0]["match_score"]
    assert score_with > score_without, (
        f"Demand match should boost score: {score_with} vs {score_without}"
    )
    assert results_with[0]["matched_demand_id"] == 1
    assert results_without[0]["matched_demand_id"] is None

check("Active demand boosts match score", test_demand_boosts_score)

# 5. Verification status affects score
def test_verified_bonus():
    from app.services.buyer_matcher import score_buyers_for_lot

    class VerifiedBuyer:
        id = 1; company_name = "Verified Co"; buyer_type = "wholesaler"
        location = "Bilaspur"; verification_status = "verified"
        reliability_score = 80.0; payment_history_score = 80.0
        crops_of_interest = ["Tomato"]

    class UnverifiedBuyer:
        id = 2; company_name = "Unverified Co"; buyer_type = "wholesaler"
        location = "Bilaspur"; verification_status = "pending"
        reliability_score = 80.0; payment_history_score = 80.0
        crops_of_interest = ["Tomato"]

    class FakeLot:
        crop = "Tomato"; grade = "A"; quantity_kg = 1000
        location = "Bilaspur"; available_date = "2026-09-10"

    r_verified = score_buyers_for_lot(FakeLot(), [VerifiedBuyer()], 25.0)[0]
    r_unverified = score_buyers_for_lot(FakeLot(), [UnverifiedBuyer()], 25.0)[0]
    assert r_verified["match_score"] > r_unverified["match_score"], (
        f"Verified should score higher: {r_verified['match_score']} vs {r_unverified['match_score']}"
    )
    assert r_verified["score_breakdown"]["verification"] == 100.0
    assert r_unverified["score_breakdown"]["verification"] == 50.0

check("Verification status affects score", test_verified_bonus)

# 6. /matching/lot route registered
def test_lot_route():
    import importlib
    matching = importlib.import_module("app.routers.matching")
    routes = [r.path for r in matching.router.routes]
    assert "/matching/lot/{lot_id}" in routes, f"Missing route, got: {routes}"
    assert "/matching/listing/{listing_id}" in routes

check("/matching/lot route registered", test_lot_route)

# 7. api/client.js has matchBuyersForLot
def test_client():
    import os
    client = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'api', 'client.js')
    content = open(client, encoding='utf-8').read()
    assert "matchBuyersForLot" in content, "matchBuyersForLot missing from api/client.js"

check("Frontend client has matchBuyersForLot", test_client)

print()
print("=" * 40)
print(f"Phase 5: {len(PASS)}/{len(PASS)+len(FAIL)} passed")
if FAIL:
    for n, e in FAIL: print(f"  FAIL: {n}: {e[:150]}")
    sys.exit(1)
else:
    print("All Phase 5 checks passed.")
    sys.exit(0)
