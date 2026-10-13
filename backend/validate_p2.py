"""
validate_p2.py — Phase 6-18 backend validation
Uses the real seeded database (cropwise.db) by default.
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
# Use the real DB so seed data is available
os.environ.setdefault("DATABASE_URL", "sqlite:///./cropwise.db")
# Use the same placeholder key that config.py uses (before the random-rotation logic)
os.environ["SECRET_KEY"] = "cropwise-hackathon-demo-secret-key-change-me"
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

PASS = []
FAIL = []

def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))

# ─── Auth helpers ────────────────────────────────────────────────────────────
def register_and_login(role, email, **kwargs):
    payload = {"role": role, "email": email, "password": "pass123", **kwargs}
    client.post("/auth/register", json=payload)  # may already exist
    r = client.post("/auth/login", data={"username": email, "password": "pass123"})
    if r.status_code == 200:
        return r.json()["access_token"]
    return None

farmer_token = register_and_login("farmer", "p2farmer@test.com",
    name="P2Farmer", location="Bilaspur", crops=["Tomato", "Soybean"])
buyer_token = register_and_login("buyer", "p2buyer@test.com",
    company_name="P2Buyer Co", location="Raipur", crops=["Tomato"])

check("Farmer token obtained", farmer_token is not None)
check("Buyer token obtained", buyer_token is not None)

fh = {"Authorization": f"Bearer {farmer_token}"} if farmer_token else {}
bh = {"Authorization": f"Bearer {buyer_token}"} if buyer_token else {}

# ─── Phase 6: Storage ────────────────────────────────────────────────────────
print("\n--- Phase 6: Storage ---")
r = client.get("/storage/facilities")
check("GET /storage/facilities returns 200", r.status_code == 200)
check("Returns list", isinstance(r.json(), list))
facilities = r.json()
check("Storage facilities seeded (>0)", len(facilities) > 0, f"got {len(facilities)}")

if facilities:
    fid = facilities[0]["id"]
    r2 = client.get(f"/storage/facilities/{fid}")
    check("GET /storage/facilities/{id}", r2.status_code == 200)
    f_data = r2.json()
    check("is_demo field present", "is_demo" in f_data)
    check("demo_disclaimer present for demo facility", f_data.get("is_demo") and f_data.get("demo_disclaimer") is not None)

    # estimate cost
    r3 = client.get(f"/storage/estimate?facility_id={fid}&quantity_kg=1000&days=7")
    check("GET /storage/estimate", r3.status_code == 200)
    check("estimated_cost in response", "estimated_cost" in r3.json())

    if farmer_token:
        # create booking
        r4 = client.post("/storage/bookings", headers=fh, json={
            "storage_facility_id": fid,
            "quantity_kg": 500,
            "start_date": "2026-09-01",
            "end_date": "2026-09-15",
        })
        check("POST /storage/bookings (farmer)", r4.status_code == 200, str(r4.json()))

        # my bookings
        r5 = client.get("/storage/bookings/mine", headers=fh)
        check("GET /storage/bookings/mine", r5.status_code == 200)

        if r4.status_code == 200:
            bid = r4.json()["id"]
            r6 = client.patch(f"/storage/bookings/{bid}/cancel", headers=fh)
            check("PATCH /storage/bookings/{id}/cancel", r6.status_code == 200)

    # crop filter
    r_cf = client.get("/storage/facilities?crop=Soybean")
    check("GET /storage/facilities?crop= filter", r_cf.status_code == 200)

# ─── Phase 9: Transport ─────────────────────────────────────────────────────
print("\n--- Phase 9: Transport ---")
r = client.get("/transport/vehicle-options")
check("GET /transport/vehicle-options", r.status_code == 200)
check("Returns list of vehicles", isinstance(r.json(), list) and len(r.json()) > 0)

if farmer_token:
    r_t = client.post("/transport/requests", headers=fh, json={
        "pickup_location": "Bilaspur",
        "destination": "Raipur",
        "pickup_date": "2026-09-10",
        "quantity_kg": 1000,
        "shared_transport": False,
    })
    check("POST /transport/requests", r_t.status_code == 200, str(r_t.json()))

    if r_t.status_code == 200:
        tid = r_t.json()["id"]
        r_mine = client.get("/transport/requests/mine", headers=fh)
        check("GET /transport/requests/mine", r_mine.status_code == 200)
        check("Request in mine", any(t["id"] == tid for t in r_mine.json()))

        # advance REQUESTED → MATCHED
        r_adv = client.patch(f"/transport/requests/{tid}/status", headers=fh, json={"status": "MATCHED"})
        check("Advance REQUESTED→MATCHED", r_adv.status_code == 200, str(r_adv.json()))

        # invalid transition from MATCHED → DELIVERED should fail
        r_bad = client.patch(f"/transport/requests/{tid}/status", headers=fh, json={"status": "DELIVERED"})
        check("Invalid transition rejected", r_bad.status_code == 400, str(r_bad.json()))

        # cancel
        r_cancel = client.patch(f"/transport/requests/{tid}/cancel", headers=fh)
        check("Cancel transport request", r_cancel.status_code == 200)

# ─── Phase 8: Market arrivals ────────────────────────────────────────────────
print("\n--- Phase 8: Arrivals ---")
r_arr = client.get("/market/arrivals?crop=Tomato&market=Bilaspur")
check("GET /market/arrivals returns 200", r_arr.status_code == 200)
arr = r_arr.json()
check("is_demo field always present", "is_demo" in arr, str(arr.keys()))
check("summary or not-available response", "summary" in arr or not arr.get("available"))

if arr.get("available"):
    s = arr["summary"]
    check("summary.demand_signal present", "demand_signal" in s)
    check("summary.modal_price present", "modal_price" in s)

# non-existent crop
r_bad = client.get("/market/arrivals?crop=InvalidCrop999&market=Bilaspur")
check("Unknown crop returns 404", r_bad.status_code == 404)

# ─── Phase 7: Selling window ──────────────────────────────────────────────────
print("\n--- Phase 7: Selling Window ---")
r_sw = client.get("/market/selling-window?crop=Tomato&market=Bilaspur&quantity_kg=1000")
check("GET /market/selling-window returns 200", r_sw.status_code == 200, str(r_sw.text[:300]))
if r_sw.status_code == 200:
    sw = r_sw.json()
    check("recommendation field", "recommendation" in sw, str(sw.keys()))
    check("options list with 2+ items", "options" in sw and len(sw["options"]) >= 2)
    check("forecast_disclaimer present", "forecast_disclaimer" in sw)
    check("SELL_NOW option always included", any(o["label"] == "SELL_NOW" for o in sw.get("options", [])))
    check("is_demo labelled", "is_demo" in sw)

# ─── Phase 14: Ratings ───────────────────────────────────────────────────────
print("\n--- Phase 14: Ratings ---")
r_rb = client.get("/ratings/for-buyer/999")
check("GET /ratings/for-buyer/{id}", r_rb.status_code == 200)
check("ratings list + total_ratings", "total_ratings" in r_rb.json() and "ratings" in r_rb.json())

r_rf = client.get("/ratings/for-farmer/999")
check("GET /ratings/for-farmer/{id}", r_rf.status_code == 200)

# Auth required for rating
if farmer_token:
    r_rate = client.post("/ratings/farmer-rates-buyer", headers=fh,
                         json={"transaction_id": 9999, "rating": 4.5, "review": "test"})
    check("Rating non-existent txn returns 404", r_rate.status_code == 404, str(r_rate.json()))

    r_rate_bad = client.post("/ratings/farmer-rates-buyer", headers=fh,
                              json={"transaction_id": 9999, "rating": 10.0})
    check("Rating value >5 rejected", r_rate_bad.status_code == 422, str(r_rate_bad.json()))

# ─── Phase 16: Buyer notifications ───────────────────────────────────────────
print("\n--- Phase 16: Buyer Notifications ---")
if buyer_token:
    r_bn = client.get("/notifications/buyer/mine", headers=bh)
    check("GET /notifications/buyer/mine", r_bn.status_code == 200, str(r_bn.json()))

    r_bg = client.post("/notifications/buyer/generate", headers=bh)
    check("POST /notifications/buyer/generate", r_bg.status_code == 200, str(r_bg.json()))
    check("Generated notification has title", "title" in r_bg.json())

# Farmer token can't access buyer notifications
if farmer_token:
    r_no = client.get("/notifications/buyer/mine", headers=fh)
    check("Farmer can't access buyer notifications", r_no.status_code in (401, 403, 404, 422), str(r_no.json()))

# ─── Summary ────────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  PASS {len(PASS)}/{len(PASS)+len(FAIL)}  FAIL {len(FAIL)}")
if FAIL:
    print(f"\n  Failures:")
    for f in FAIL:
        print(f"    • {f}")
print(f"{'='*55}")

sys.exit(0 if not FAIL else 1)
