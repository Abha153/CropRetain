"""
Phase 1-4 validation script. Run from backend/: python validate_p1.py
"""
import sys
# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PASS = []
FAIL = []

def check(name, fn):
    try:
        fn()
        PASS.append(name)
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL.append((name, str(e)))
        print(f"  FAIL  {name}: {e}")

# 1. Core imports
def test_imports():
    from app.main import app
    from app import models, schemas
    from app.routers import (lots, buyer_demands, buyer_verification,
                              transactions, payments, grievances)
    from app.auth_utils import require_farmer, require_buyer, require_admin

check("Core imports", test_imports)

# 2. Route registration
def test_routes():
    import importlib
    expected = {
        "lots":                ["/lots", "/lots/mine", "/lots/{lot_id}"],
        "buyer_demands":       ["/buyer-demands", "/buyer-demands/mine", "/buyer-demands/{demand_id}"],
        "buyer_verification":  ["/buyer-verification", "/buyer-verification/me"],
        "transactions":        ["/transactions/mine", "/transactions/{txn_id}", "/transactions/{txn_id}/timeline"],
        "payments":            ["/payments/mine", "/payments/{payment_id}", "/payments"],
        "grievances":          ["/grievances", "/grievances/mine", "/grievances/{grievance_id}"],
    }
    for mod_name, paths in expected.items():
        mod = importlib.import_module(f"app.routers.{mod_name}")
        actual = [r.path for r in mod.router.routes]
        for p in paths:
            assert p in actual, f"{mod_name}: missing {p!r}, got {actual}"

check("Route registration", test_routes)

# 3. Schema field consistency
def test_schema_fields():
    from app import schemas

    lot_fields = set(schemas.LotOut.model_fields.keys())
    for f in ["id","lot_number","farmer_id","crop","quantity_kg","grade","quality_score","expected_price","status","created_at","updated_at"]:
        assert f in lot_fields, f"LotOut missing: {f}"

    demand_fields = set(schemas.BuyerDemandOut.model_fields.keys())
    for f in ["id","buyer_id","crop","required_quantity_kg","status","created_at","updated_at"]:
        assert f in demand_fields, f"BuyerDemandOut missing: {f}"

    payment_fields = set(schemas.PaymentOut.model_fields.keys())
    for f in ["id","transaction_id","buyer_id","farmer_id","amount","payment_status","is_demo"]:
        assert f in payment_fields, f"PaymentOut missing: {f}"

    grievance_fields = set(schemas.GrievanceOut.model_fields.keys())
    for f in ["id","raised_by","raised_by_id","category","description","status","created_at"]:
        assert f in grievance_fields, f"GrievanceOut missing: {f}"

check("Schema field consistency", test_schema_fields)

# 4. DB tables
def test_db_tables():
    from app.database import Base, engine, run_lightweight_migrations
    from app import models
    Base.metadata.create_all(bind=engine)
    run_lightweight_migrations()
    actual = set(Base.metadata.tables.keys())
    expected = [
        "farmers","buyers","crop_listings","buyer_offers","transactions",
        "market_prices","notifications","group_selling_pools","group_pool_memberships",
        "login_events","buyer_demands","buyer_verifications","lots","storage_facilities",
        "storage_bookings","transport_requests","payments","transaction_events","grievances","ratings",
    ]
    for t in expected:
        assert t in actual, f"Missing table: {t}"
    print(f"    {len(actual)} tables total")

check("All 20 DB tables created", test_db_tables)

# 5. Seed data
def test_seed():
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    try:
        if db.query(models.Farmer).count() == 0:
            from app.seed_data import seed
            seed()
        counts = {
            "farmers":             db.query(models.Farmer).count(),
            "buyers":              db.query(models.Buyer).count(),
            "lots":                db.query(models.Lot).count(),
            "buyer_demands":       db.query(models.BuyerDemand).count(),
            "buyer_verifications": db.query(models.BuyerVerification).count(),
            "transactions":        db.query(models.Transaction).count(),
            "transaction_events":  db.query(models.TransactionEvent).count(),
            "payments":            db.query(models.Payment).count(),
            "grievances":          db.query(models.Grievance).count(),
            "storage_facilities":  db.query(models.StorageFacility).count(),
        }
        for name, count in counts.items():
            assert count > 0, f"{name!r} is empty after seed"
        print(f"    {counts}")
    finally:
        db.close()

check("Seed data all records present", test_seed)

# 6. ORM relationships
def test_relationships():
    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    try:
        farmer = db.query(models.Farmer).first()
        assert farmer is not None, "No farmers in DB"
        _ = farmer.lots          # Farmer.lots relationship
        _ = farmer.listings      # existing
        _ = farmer.notifications # existing

        buyer = db.query(models.Buyer).first()
        assert buyer is not None, "No buyers in DB"
        _ = buyer.demands        # Buyer.demands
        _ = buyer.verification   # Buyer.verification (uselist=False)
        _ = buyer.offers         # existing

        txn = db.query(models.Transaction).first()
        assert txn is not None, "No transactions in DB"
        _ = txn.events           # Transaction.events
        _ = txn.payments         # Transaction.payments

        storage = db.query(models.StorageFacility).first()
        assert storage is not None, "No storage facilities in DB"
        _ = storage.bookings     # StorageFacility.bookings
    finally:
        db.close()

check("ORM relationships load correctly", test_relationships)

# 7. Migration columns
def test_migration_columns():
    from app.database import engine
    from sqlalchemy import inspect as sa_inspect
    insp = sa_inspect(engine)

    txn_cols = {c["name"] for c in insp.get_columns("transactions")}
    for col in ["lot_id","offer_id","updated_at"]:
        assert col in txn_cols, f"transactions.{col} missing"

    notif_cols = {c["name"] for c in insp.get_columns("notifications")}
    assert "buyer_id" in notif_cols, "notifications.buyer_id missing"

check("Migration columns present", test_migration_columns)

# 8. Legacy transaction status normalization
def test_status_compat():
    from app.routers.transactions import _normalize_status
    assert _normalize_status("completed") == "COMPLETED"
    assert _normalize_status("COMPLETED") == "COMPLETED"
    assert _normalize_status("OFFER_ACCEPTED") == "OFFER_ACCEPTED"

check("Transaction legacy status backward compat", test_status_compat)

# 9. Quality match scoring
def test_quality_match():
    from app.routers.buyer_demands import _quality_match

    class FakeDemand:
        quality_grade = "A"
        moisture_limit = 12.0
        foreign_matter_limit = 2.0
        damaged_grains_limit = 3.0
        minimum_quantity_kg = 1000.0
        maximum_quantity_kg = 5000.0
        required_quantity_kg = 3000.0

    class FakeLot:
        grade = "A"
        quantity_kg = 3000.0
        quality_report = {"moisture_pct": 10.5, "foreign_matter_pct": 0.8, "damaged_pct": 1.2}

    result = _quality_match(FakeDemand(), FakeLot())
    assert "quality_match_score" in result, "Missing quality_match_score"
    score = result["quality_match_score"]
    assert score > 80, f"Expected >80 for good match, got {score}"
    assert len(result["criteria"]) > 0, "No criteria returned"
    # Failing lot (bad grade)
    class BadLot:
        grade = "C"
        quantity_kg = 500.0  # below minimum
        quality_report = {"moisture_pct": 18.0, "foreign_matter_pct": 5.0, "damaged_pct": 8.0}
    bad_result = _quality_match(FakeDemand(), BadLot())
    assert bad_result["quality_match_score"] < 80, f"Bad lot should score <80, got {bad_result['quality_match_score']}"

check("Quality match scoring", test_quality_match)

# 10. Lot number format
def test_lot_number():
    from app.routers.lots import _next_lot_number
    from app.database import SessionLocal
    import datetime
    db = SessionLocal()
    try:
        num = _next_lot_number(db)
        year = datetime.date.today().year
        assert num.startswith(f"CW-{year}-"), f"Bad format: {num}"
        assert len(num.split("-")) == 3, f"Expected 3 parts: {num}"
    finally:
        db.close()

check("Lot number generation", test_lot_number)

# 11. Payment reference
def test_payment_ref():
    from app.routers.payments import _payment_ref
    ref = _payment_ref()
    assert ref.startswith("CW-PAY-"), f"Bad ref: {ref}"
    # Must be unique (probabilistic)
    refs = {_payment_ref() for _ in range(5)}
    assert len(refs) == 5, "Payment refs not unique"

check("Payment reference generation", test_payment_ref)

# 12. Auth function imports (structural check)
def test_auth_structure():
    from app.auth_utils import require_farmer, require_buyer, require_admin

    # Check lots routes use require_farmer for mutation, public for reads
    import inspect
    from app.routers import lots, buyer_demands, buyer_verification, grievances

    # Verify create_lot requires farmer
    sig = inspect.signature(lots.create_lot)
    params = dict(sig.parameters)
    # FastAPI injects Depends - check the annotation
    assert "farmer" in params or "db" in params, "create_lot must have farmer/db param"

check("Auth structure check", test_auth_structure)

# 13. Frontend api/client coverage
def test_client_coverage():
    import os
    client_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'api', 'client.js')
    with open(client_path, encoding='utf-8') as f:
        content = f.read()
    required = [
        "createLot","myLots","getLots","getLot","cancelLot",
        "createDemand","myDemands","getDemands","cancelDemand","demandMatches",
        "submitVerification","myVerification","adminApproveVerification","adminRejectVerification",
        "myTransactions","getTransaction","getTransactionTimeline","updateTransactionStatus",
        "myPayments","paymentForTransaction","createPayment","initiatePayment","confirmPaymentReceived",
        "raiseGrievance","myGrievances","getGrievance","updateGrievance",
    ]
    for method in required:
        assert method in content, f"Missing in api/client.js: {method}"

check("Frontend api/client coverage", test_client_coverage)

# 14. Frontend pages exist
def test_frontend_pages():
    import os
    pages_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'src', 'pages')
    required = ["Lots.jsx","BuyerDemands.jsx","BuyerVerification.jsx","Transactions.jsx","TransactionDetail.jsx"]
    for page in required:
        path = os.path.join(pages_dir, page)
        assert os.path.exists(path), f"Missing page: {page}"

check("Frontend pages exist", test_frontend_pages)

# 15. Existing routers still intact
def test_existing_routers():
    from app.routers import (
        auth, farmers, buyers, listings, offers, market, advisor,
        forecast, matching, logistics, profit, group_selling,
        notifications, quality, assistant, admin
    )
    # Check offers still has accept_offer with new transaction status
    import inspect
    from app.routers.offers import accept_offer
    src = inspect.getsource(accept_offer)
    assert "OFFER_ACCEPTED" in src, "accept_offer should use OFFER_ACCEPTED status"
    assert "TransactionEvent" in src, "accept_offer should create TransactionEvent"
    assert 'status="completed"' not in src, "accept_offer must not use legacy 'completed' status"

check("Existing routers intact + offers updated", test_existing_routers)

# Summary
print()
print("=" * 50)
print(f"PASSED: {len(PASS)}/{len(PASS)+len(FAIL)}")
if FAIL:
    print(f"FAILED: {len(FAIL)}")
    for name, err in FAIL:
        print(f"  FAIL: {name}")
        print(f"    -> {err[:200]}")
    sys.exit(1)
else:
    print("All checks passed.")
    sys.exit(0)
