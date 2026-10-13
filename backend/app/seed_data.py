"""
Seeds the CropRetain database with realistic demo data so the whole app -- and
the hackathon demo flow described in the README -- works immediately without
any external APIs or manual data entry.

Run automatically on first startup (see app/main.py) if the farmers table is
empty. Can also be run directly: `python -m app.seed_data`.
"""
import datetime as dt

from app.database import Base, engine, SessionLocal
from app import models
from app.auth_utils import hash_password
from app.mock_data.demo_users import DEMO_FARMERS, DEMO_BUYERS, DEMO_PASSWORD
from app.mock_data.crops import CROPS
from app.mock_data.historical_prices import generate_all_history


def ensure_demo_buyer_verification_records(db=None, demo_emails=None) -> int:
    """Give every DEMO buyer that is marked verified a real, backing
    BuyerVerification record (plus its audit-log entry).

    Trust summaries treat BuyerVerification as the source of truth, so a
    demo buyer carrying only Buyer.verification_status == "verified" would
    otherwise show as NOT_VERIFIED. Rather than weakening that rule, the
    demo data is made consistent. Idempotent; only touches buyers whose
    email is in DEMO_BUYERS (or `demo_emails`) and who have no record yet.
    Runs on every startup, so databases seeded before this existed are
    repaired too. Returns the number of records created.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        if demo_emails is None:
            demo_emails = {b["email"] for b in DEMO_BUYERS
                           if b.get("verification_status") == "verified"}
        if not demo_emails:
            return 0
        buyers = db.query(models.Buyer).filter(
            models.Buyer.email.in_(list(demo_emails)),
            models.Buyer.verification_status == "verified",
        ).all()
        created = 0
        for buyer in buyers:
            has_record = db.query(models.BuyerVerification.id).filter(
                models.BuyerVerification.buyer_id == buyer.id
            ).first()
            if has_record:
                continue
            ts = dt.datetime.utcnow()
            db.add(models.BuyerVerification(
                buyer_id=buyer.id, business_name=buyer.company_name,
                document_urls=[f"demo://buyer_{buyer.id}_verification.pdf"],
                verification_status="VERIFIED", verification_method="PLATFORM_VERIFIED",
                verification_notes="Demo seed record -- not a real platform review. (Demo data)",
                submitted_at=ts, verified_at=ts, reviewed_at=ts, reviewed_by="demo-seed",
            ))
            db.add(models.BuyerVerificationAuditLog(
                buyer_id=buyer.id, old_status="PENDING", new_status="VERIFIED",
                reviewer_admin_id="demo-seed",
                note="Demo seed record backing a verified demo buyer. (Demo data)",
            ))
            created += 1
        if created:
            db.commit()
        return created
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.Farmer).count() > 0:
            print("CropRetain DB already seeded -- skipping.")
            return

        print("Seeding CropRetain demo data...")

        # ---- Farmers ----
        farmers = []
        for f in DEMO_FARMERS:
            farmer = models.Farmer(
                name=f["name"], email=f["email"],
                password_hash=hash_password(DEMO_PASSWORD),
                phone=f["phone"], location=f["location"],
                latitude=f["latitude"], longitude=f["longitude"],
                crops=f["crops"], preferred_language=f["preferred_language"],
                rating=f["rating"], fpo_group=f["fpo_group"],
            )
            db.add(farmer)
            farmers.append(farmer)
        db.commit()
        for f in farmers:
            db.refresh(f)

        # ---- Buyers ----
        buyers = []
        for b in DEMO_BUYERS:
            buyer = models.Buyer(
                company_name=b["company_name"], email=b["email"],
                password_hash=hash_password(DEMO_PASSWORD),
                phone=b["phone"], location=b["location"],
                latitude=b["latitude"], longitude=b["longitude"],
                buyer_type=b["buyer_type"], verification_status=b["verification_status"],
                reliability_score=b["reliability_score"],
                payment_history_score=b["payment_history_score"],
                crops_of_interest=b["crops_of_interest"],
            )
            db.add(buyer)
            buyers.append(buyer)
        db.commit()
        for b in buyers:
            db.refresh(b)

        # ---- Market price history (bulk insert for speed) ----
        rows = []
        for crop_name, market_name, history in generate_all_history():
            for h in history:
                rows.append({
                    "crop": crop_name, "market": market_name, "date": h["date"],
                    "min_price": h["min_price"], "max_price": h["max_price"],
                    "modal_price": h["modal_price"], "arrivals_tonnes": h["arrivals_tonnes"],
                    # Explicitly tagged "demo" -- this is the synthesized 60-day
                    # series from historical_prices.py, never a real government
                    # feed. Real snapshots captured from data.gov.in at request
                    # time are inserted separately with data_source="live" (see
                    # app/routers/market.py::_record_live_snapshot). Historical
                    # trend charts only ever read "live" rows -- see the honesty
                    # note on GET /market/prices.
                    "data_source": "demo",
                })
        db.bulk_insert_mappings(models.MarketPrice, rows)
        db.commit()
        print(f"  Inserted {len(rows)} historical market price rows.")

        # ---- Demo crop listings ----
        ramesh, sunita, manoj = farmers[0], farmers[1], farmers[2]
        today = dt.date.today()
        listings_seed = [
            dict(farmer_id=ramesh.id, crop="Tomato", quantity_kg=2000, quality_grade="A",
                 quality_score=88, expected_price_per_kg=28, location=ramesh.location,
                 available_date=(today + dt.timedelta(days=1)).isoformat(),
                 min_acceptable_price=22,
                 bidding_deadline=(today + dt.timedelta(days=4)).isoformat()),
            dict(farmer_id=ramesh.id, crop="Paddy (Rice)", quantity_kg=5000, quality_grade="B",
                 quality_score=76, expected_price_per_kg=21, location=ramesh.location,
                 available_date=(today + dt.timedelta(days=10)).isoformat(),
                 min_acceptable_price=18,
                 bidding_deadline=(today + dt.timedelta(days=14)).isoformat()),
            dict(farmer_id=sunita.id, crop="Onion", quantity_kg=3000, quality_grade="A",
                 quality_score=91, expected_price_per_kg=19, location=sunita.location,
                 available_date=today.isoformat(),
                 min_acceptable_price=15,
                 bidding_deadline=(today + dt.timedelta(days=5)).isoformat()),
            dict(farmer_id=manoj.id, crop="Maize", quantity_kg=4000, quality_grade="B",
                 quality_score=72, expected_price_per_kg=20, location=manoj.location,
                 available_date=(today + dt.timedelta(days=3)).isoformat(),
                 min_acceptable_price=17,
                 bidding_deadline=(today + dt.timedelta(days=7)).isoformat()),
            dict(farmer_id=manoj.id, crop="Chana (Gram)", quantity_kg=1500, quality_grade="A",
                 quality_score=85, expected_price_per_kg=54, location=manoj.location,
                 available_date=(today + dt.timedelta(days=6)).isoformat(),
                 min_acceptable_price=48,
                 bidding_deadline=(today + dt.timedelta(days=10)).isoformat()),
        ]
        listings = []
        for l in listings_seed:
            listing = models.CropListing(**l)
            db.add(listing)
            listings.append(listing)
        db.commit()
        for l in listings:
            db.refresh(l)

        # ---- Demo offers on the first two listings ----
        tomato_listing = listings[0]
        onion_listing = listings[2]
        offers_seed = [
            dict(buyer_id=buyers[0].id, listing_id=tomato_listing.id, offered_price_per_kg=26.5,
                 quantity_kg=2000, message="Can pick up within 2 days."),
            dict(buyer_id=buyers[1].id, listing_id=tomato_listing.id, offered_price_per_kg=27.0,
                 quantity_kg=1500, message="Interested in Grade A only, retail chain."),
            dict(buyer_id=buyers[2].id, listing_id=onion_listing.id, offered_price_per_kg=18.0,
                 quantity_kg=3000, message="Export order, need consistent quality."),
        ]
        for o in offers_seed:
            db.add(models.BuyerOffer(**o))
        db.commit()

        # ---- Notifications ----
        notif_seed = [
            dict(farmer_id=ramesh.id, type="high_demand", severity="success",
                 title="High demand nearby",
                 message="A buyer near Bilaspur is looking for 1,000 kg of Tomato this week."),
            dict(farmer_id=ramesh.id, type="opportunity", severity="success",
                 title="Better price in another market",
                 message="Your expected net profit may be higher in Raipur for Paddy (Rice) this week."),
            dict(farmer_id=sunita.id, type="price_drop", severity="warning",
                 title="Price drop alert",
                 message="Onion prices in Raigarh have dropped recently -- consider comparing nearby markets."),
            dict(farmer_id=manoj.id, type="harvest_reminder", severity="info",
                 title="Harvest reminder",
                 message="Based on your crop schedule, update your available Maize quantity."),
        ]
        for n in notif_seed:
            db.add(models.Notification(**n))
        db.commit()

        # ---- Group selling pool ----
        pool = models.GroupSellingPool(
            crop="Chana (Gram)", fpo_name="Durg Farmer Collective", status="open",
        )
        db.add(pool)
        db.commit()
        db.refresh(pool)
        db.add(models.GroupPoolMembership(pool_id=pool.id, farmer_id=manoj.id, quantity_kg=1500))
        db.commit()

        ramesh, sunita, manoj = farmers[0], farmers[1], farmers[2]
        freshfoods, greenbasket, agriexport = buyers[0], buyers[1], buyers[2]

        # ---- Buyer Verifications (Phase 2) ----
        verif_seed = [
            dict(buyer_id=freshfoods.id, business_name="FreshFoods Processing Pvt. Ltd.",
                 business_registration_number="CIN-U15100CG2018PTC123456",
                 gst_number="22AABCF1234A1Z5", license_number="FSSAI-10012345678901",
                 document_urls=["demo://freshfoods_gst.pdf", "demo://freshfoods_fssai.pdf"],
                 verification_status="VERIFIED", verification_method="PLATFORM_VERIFIED",
                 verification_notes="Documents verified by CropRetain platform team. (Demo data)",
                 verified_at=dt.datetime.utcnow() - dt.timedelta(days=30)),
            dict(buyer_id=greenbasket.id, business_name="GreenBasket Retail",
                 business_registration_number="CIN-U51100CG2019PTC654321",
                 gst_number="22AABCG5678B2Z8",
                 document_urls=["demo://greenbasket_gst.pdf"],
                 verification_status="VERIFIED", verification_method="PLATFORM_VERIFIED",
                 verification_notes="GST certificate verified. (Demo data)",
                 verified_at=dt.datetime.utcnow() - dt.timedelta(days=45)),
            dict(buyer_id=agriexport.id, business_name="AgriExport India",
                 business_registration_number="CIN-U01100CG2015PTC987654",
                 gst_number="22AABCA9012C3Z1", license_number="APEDA-EXP-2023-001",
                 document_urls=["demo://agriexport_gst.pdf", "demo://agriexport_apeda.pdf"],
                 verification_status="VERIFIED", verification_method="PLATFORM_VERIFIED",
                 verified_at=dt.datetime.utcnow() - dt.timedelta(days=60)),
        ]
        for v in verif_seed:
            db.add(models.BuyerVerification(**v))
        db.commit()

        # ---- Buyer Demands (Phase 1) ----
        demand_seed = [
            dict(buyer_id=freshfoods.id, crop="Tomato",
                 required_quantity_kg=5000, minimum_quantity_kg=2000, maximum_quantity_kg=6000,
                 target_price_per_kg=28.0, quality_grade="A",
                 moisture_limit=12.0, foreign_matter_limit=2.0, damaged_grains_limit=3.0,
                 delivery_location="Raipur", delivery_latitude=21.2514, delivery_longitude=81.6296,
                 delivery_deadline=(today + dt.timedelta(days=14)).isoformat(),
                 payment_terms="50% advance, balance on delivery",
                 additional_requirements="Uniform size, no surface damage. (Demo demand)",
                 status="ACTIVE", expires_at=(today + dt.timedelta(days=20)).isoformat()),
            dict(buyer_id=agriexport.id, crop="Soybean",
                 required_quantity_kg=3000, minimum_quantity_kg=2000, maximum_quantity_kg=5000,
                 target_price_per_kg=50.5, quality_grade="A",
                 moisture_limit=12.0, foreign_matter_limit=1.5, damaged_grains_limit=2.0,
                 delivery_location="Raipur", delivery_latitude=21.2514, delivery_longitude=81.6296,
                 delivery_deadline=(today + dt.timedelta(days=30)).isoformat(),
                 payment_terms="Full payment within 7 days of delivery",
                 additional_requirements="Export grade, clean and dry. (Demo demand)",
                 status="ACTIVE", expires_at=(today + dt.timedelta(days=30)).isoformat()),
            dict(buyer_id=greenbasket.id, crop="Onion",
                 required_quantity_kg=3000, minimum_quantity_kg=1500, maximum_quantity_kg=4000,
                 target_price_per_kg=19.0, quality_grade="A",
                 moisture_limit=14.0, foreign_matter_limit=2.0, damaged_grains_limit=4.0,
                 delivery_location="Bilaspur",
                 delivery_deadline=(today + dt.timedelta(days=10)).isoformat(),
                 payment_terms="Cash on delivery",
                 additional_requirements="(Demo demand)",
                 status="ACTIVE", expires_at=(today + dt.timedelta(days=15)).isoformat()),
            # ---- additional interconnected demo demands, tying the new
            # buyers to crops the new farmers actually grow, so matching
            # produces real results across the larger seeded pool ----
            dict(buyer_id=buyers[4].id, crop="Tomato",  # Kisan Limited (Riya Malhotra)
                 required_quantity_kg=8000, minimum_quantity_kg=5000, maximum_quantity_kg=10000,
                 target_price_per_kg=25.5, quality_grade="A",
                 moisture_limit=None, foreign_matter_limit=2.0, damaged_grains_limit=3.0,
                 delivery_location="Raipur", delivery_latitude=21.2514, delivery_longitude=81.6296,
                 delivery_deadline=(today + dt.timedelta(days=12)).isoformat(),
                 payment_terms="Net 7 days after delivery",
                 additional_requirements="Bulk tomato procurement for processing. (Demo demand)",
                 status="ACTIVE", expires_at=(today + dt.timedelta(days=18)).isoformat()),
            dict(buyer_id=buyers[6].id, crop="Soybean",  # FarmLink Agro
                 required_quantity_kg=4000, minimum_quantity_kg=2000, maximum_quantity_kg=6000,
                 target_price_per_kg=49.0, quality_grade="A",
                 moisture_limit=12.0, foreign_matter_limit=1.5, damaged_grains_limit=2.0,
                 delivery_location="Rajnandgaon", delivery_latitude=21.0972, delivery_longitude=81.0388,
                 delivery_deadline=(today + dt.timedelta(days=20)).isoformat(),
                 payment_terms="50% advance, balance on delivery",
                 additional_requirements="(Demo demand)",
                 status="ACTIVE", expires_at=(today + dt.timedelta(days=25)).isoformat()),
            dict(buyer_id=buyers[7].id, crop="Paddy (Rice)",  # GreenRoute Foods
                 required_quantity_kg=5000, minimum_quantity_kg=3000, maximum_quantity_kg=7000,
                 target_price_per_kg=20.5, quality_grade="B",
                 moisture_limit=14.0, foreign_matter_limit=3.0, damaged_grains_limit=4.0,
                 delivery_location="Mahasamund", delivery_latitude=21.1093, delivery_longitude=82.0980,
                 delivery_deadline=(today + dt.timedelta(days=16)).isoformat(),
                 payment_terms="Cash on delivery",
                 additional_requirements="(Demo demand)",
                 status="ACTIVE", expires_at=(today + dt.timedelta(days=22)).isoformat()),
        ]
        demands = []
        for d in demand_seed:
            dem = models.BuyerDemand(**d)
            db.add(dem)
            demands.append(dem)
        db.commit()
        for d in demands:
            db.refresh(d)

        # ---- Lots (Phase 4) ----
        lot_seed = [
            dict(lot_number="CW-DEMO-00001", farmer_id=ramesh.id, crop="Soybean",
                 quantity_kg=4000, grade="A", quality_score=92.0,
                 quality_report={"quality_grade": "A", "visual_quality_score": 92,
                                  "moisture_pct": 10.5, "foreign_matter_pct": 0.8, "damaged_pct": 1.2,
                                  "detected_notes": ["Uniform color", "Dry and clean", "Minimal foreign matter"],
                                  "analysis_method": "AI Estimated Quality — image-based analysis only, not lab-certified.",
                                  "demo_mode": True},
                 harvest_date=(today - dt.timedelta(days=5)).isoformat(),
                 available_date=today.isoformat(),
                 location=ramesh.location, latitude=ramesh.latitude, longitude=ramesh.longitude,
                 expected_price=49.0, minimum_price=45.0, status="AVAILABLE",
                 note="Demo lot — Bilaspur Soybean harvest, AI Grade A"),
            dict(lot_number="CW-DEMO-00002", farmer_id=sunita.id, crop="Onion",
                 quantity_kg=2500, grade="A", quality_score=88.0,
                 quality_report={"quality_grade": "A", "visual_quality_score": 88,
                                  "moisture_pct": 13.0, "foreign_matter_pct": 1.5, "damaged_pct": 2.5,
                                  "detected_notes": ["Good size uniformity", "Firm texture"],
                                  "analysis_method": "AI Estimated Quality — image-based analysis only, not lab-certified.",
                                  "demo_mode": True},
                 harvest_date=(today - dt.timedelta(days=3)).isoformat(),
                 available_date=today.isoformat(),
                 location=sunita.location, latitude=sunita.latitude, longitude=sunita.longitude,
                 expected_price=19.0, minimum_price=15.0, status="AVAILABLE",
                 note="Demo lot — Raigarh Onion"),
            dict(lot_number="CW-DEMO-00003", farmer_id=manoj.id, crop="Maize",
                 quantity_kg=3500, grade="B", quality_score=78.0,
                 quality_report={"quality_grade": "B", "visual_quality_score": 78,
                                  "moisture_pct": 14.5, "foreign_matter_pct": 2.2, "damaged_pct": 3.1,
                                  "detected_notes": ["Acceptable moisture", "Some grain size variation"],
                                  "analysis_method": "AI Estimated Quality — image-based analysis only, not lab-certified.",
                                  "demo_mode": True},
                 harvest_date=(today - dt.timedelta(days=7)).isoformat(),
                 available_date=(today + dt.timedelta(days=1)).isoformat(),
                 location=manoj.location, latitude=manoj.latitude, longitude=manoj.longitude,
                 expected_price=20.0, minimum_price=17.0, status="AVAILABLE",
                 note="Demo lot — Durg Maize"),
            # ---- additional interconnected demo lots from the new farmers,
            # sized/priced/located to genuinely match the new buyer demands
            # above (Preeti's Tomato -> Kisan Limited; Dilip's Soybean ->
            # FarmLink Agro; Kavita's Paddy -> GreenRoute Foods) ----
            dict(lot_number="CW-DEMO-00004", farmer_id=farmers[3].id, crop="Tomato",  # Preeti
                 quantity_kg=6000, grade="A", quality_score=90.0,
                 quality_report={"quality_grade": "A", "visual_quality_score": 90,
                                  "moisture_pct": 11.0, "foreign_matter_pct": 1.0, "damaged_pct": 1.5,
                                  "detected_notes": ["Uniform ripeness", "Firm skin"],
                                  "analysis_method": "AI Estimated Quality — image-based analysis only, not lab-certified.",
                                  "demo_mode": True},
                 harvest_date=(today - dt.timedelta(days=2)).isoformat(),
                 available_date=today.isoformat(),
                 location=farmers[3].location, latitude=farmers[3].latitude, longitude=farmers[3].longitude,
                 expected_price=25.0, minimum_price=21.0, status="AVAILABLE",
                 note="Demo lot — Bilaspur Tomato"),
            dict(lot_number="CW-DEMO-00005", farmer_id=farmers[4].id, crop="Soybean",  # Dilip
                 quantity_kg=3800, grade="A", quality_score=89.0,
                 quality_report={"quality_grade": "A", "visual_quality_score": 89,
                                  "moisture_pct": 10.8, "foreign_matter_pct": 1.1, "damaged_pct": 1.4,
                                  "detected_notes": ["Dry and clean", "Consistent grain size"],
                                  "analysis_method": "AI Estimated Quality — image-based analysis only, not lab-certified.",
                                  "demo_mode": True},
                 harvest_date=(today - dt.timedelta(days=4)).isoformat(),
                 available_date=today.isoformat(),
                 location=farmers[4].location, latitude=farmers[4].latitude, longitude=farmers[4].longitude,
                 expected_price=48.0, minimum_price=44.0, status="AVAILABLE",
                 note="Demo lot — Rajnandgaon Soybean"),
            dict(lot_number="CW-DEMO-00006", farmer_id=farmers[5].id, crop="Paddy (Rice)",  # Kavita
                 quantity_kg=5200, grade="B", quality_score=80.0,
                 quality_report={"quality_grade": "B", "visual_quality_score": 80,
                                  "moisture_pct": 13.8, "foreign_matter_pct": 2.0, "damaged_pct": 2.8,
                                  "detected_notes": ["Acceptable moisture", "Minor grain variation"],
                                  "analysis_method": "AI Estimated Quality — image-based analysis only, not lab-certified.",
                                  "demo_mode": True},
                 harvest_date=(today - dt.timedelta(days=6)).isoformat(),
                 available_date=today.isoformat(),
                 location=farmers[5].location, latitude=farmers[5].latitude, longitude=farmers[5].longitude,
                 expected_price=20.0, minimum_price=17.5, status="AVAILABLE",
                 note="Demo lot — Mahasamund Paddy"),
        ]
        lots = []
        for l in lot_seed:
            lot = models.Lot(**l)
            db.add(lot)
            lots.append(lot)
        db.commit()
        for l in lots:
            db.refresh(l)

        # ---- Storage Facilities (Phase 6 — all DEMO) ----
        storage_seed = [
            dict(name="Bilaspur Agri Warehouse (Demo)", facility_type="WAREHOUSE",
                 location="Bilaspur", latitude=22.0797, longitude=82.1409,
                 capacity_kg=500000, available_capacity_kg=180000, price_per_kg_per_day=0.12,
                 crop_types=["Soybean", "Maize", "Wheat", "Paddy (Rice)", "Chana (Gram)"],
                 temperature_controlled=False,
                 warehouse_features=["Loading dock", "Weighing bridge", "24hr security"],
                 quality_services=["Visual grading", "Moisture testing"],
                 contact="+91 77777 11111",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Raipur Cold Storage Pvt. Ltd. (Demo)", facility_type="COLD_STORAGE",
                 location="Raipur", latitude=21.2514, longitude=81.6296,
                 capacity_kg=200000, available_capacity_kg=75000, price_per_kg_per_day=0.28,
                 crop_types=["Tomato", "Onion", "Potato"],
                 temperature_controlled=True,
                 warehouse_features=["Humidity control", "Temperature monitoring"],
                 quality_services=["Visual grading", "Moisture testing", "Weight certification"],
                 contact="+91 77777 22222",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Durg FPO Collective Storage (Demo)", facility_type="FPO_STORAGE",
                 location="Durg", latitude=21.1904, longitude=81.2849,
                 capacity_kg=120000, available_capacity_kg=60000, price_per_kg_per_day=0.08,
                 crop_types=["Maize", "Chana (Gram)", "Groundnut", "Soybean"],
                 temperature_controlled=False,
                 warehouse_features=["Member priority access", "Pest control"],
                 quality_services=["Visual grading"],
                 contact="+91 77777 33333",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            # ---- additional demo storage facilities, spread across the same
            # towns DEMO_FARMERS/DEMO_BUYERS already use so distance/price
            # comparisons are meaningful, not just extra unconnected rows ----
            dict(name="Raigarh Grain Godown (Demo)", facility_type="WAREHOUSE",
                 location="Raigarh", latitude=21.8974, longitude=83.3950,
                 capacity_kg=250000, available_capacity_kg=95000, price_per_kg_per_day=0.10,
                 crop_types=["Wheat", "Onion", "Maize"],
                 temperature_controlled=False,
                 warehouse_features=["Weighing bridge", "Rail siding nearby"],
                 quality_services=["Visual grading", "Moisture testing"],
                 contact="+91 77777 44444",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Korba Farmers' Warehouse (Demo)", facility_type="WAREHOUSE",
                 location="Korba", latitude=22.3595, longitude=82.7501,
                 capacity_kg=180000, available_capacity_kg=70000, price_per_kg_per_day=0.11,
                 crop_types=["Wheat", "Paddy (Rice)", "Groundnut"],
                 temperature_controlled=False,
                 warehouse_features=["Loading dock", "24hr security"],
                 quality_services=["Visual grading"],
                 contact="+91 77777 55555",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Rajnandgaon Producer Company Store (Demo)", facility_type="FPO_STORAGE",
                 location="Rajnandgaon", latitude=21.0972, longitude=81.0388,
                 capacity_kg=90000, available_capacity_kg=40000, price_per_kg_per_day=0.07,
                 crop_types=["Soybean", "Chana (Gram)", "Wheat"],
                 temperature_controlled=False,
                 warehouse_features=["Member priority access"],
                 quality_services=["Visual grading", "Moisture testing"],
                 contact="+91 77777 66666",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Mahasamund District Warehouse (Demo)", facility_type="WAREHOUSE",
                 location="Mahasamund", latitude=21.1093, longitude=82.0980,
                 capacity_kg=160000, available_capacity_kg=55000, price_per_kg_per_day=0.09,
                 crop_types=["Paddy (Rice)", "Maize"],
                 temperature_controlled=False,
                 warehouse_features=["Weighing bridge", "Pest control"],
                 quality_services=["Visual grading"],
                 contact="+91 77777 77777",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Ambikapur Cold Store (Demo)", facility_type="COLD_STORAGE",
                 location="Ambikapur", latitude=23.1200, longitude=83.1950,
                 capacity_kg=110000, available_capacity_kg=42000, price_per_kg_per_day=0.26,
                 crop_types=["Maize", "Chana (Gram)"],
                 temperature_controlled=True,
                 warehouse_features=["Humidity control", "Temperature monitoring"],
                 quality_services=["Visual grading", "Weight certification"],
                 contact="+91 77777 88888",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Jagdalpur Bastar FPO Storage (Demo)", facility_type="FPO_STORAGE",
                 location="Jagdalpur", latitude=19.0748, longitude=82.0198,
                 capacity_kg=80000, available_capacity_kg=35000, price_per_kg_per_day=0.08,
                 crop_types=["Paddy (Rice)", "Groundnut", "Soybean"],
                 temperature_controlled=False,
                 warehouse_features=["Member priority access", "Pest control"],
                 quality_services=["Visual grading"],
                 contact="+91 77777 99999",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
            dict(name="Bilha Village Grain Store (Demo)", facility_type="WAREHOUSE",
                 location="Bilha", latitude=22.1500, longitude=82.0500,
                 capacity_kg=60000, available_capacity_kg=28000, price_per_kg_per_day=0.10,
                 crop_types=["Tomato", "Onion", "Wheat"],
                 temperature_controlled=False,
                 warehouse_features=["Loading dock"],
                 quality_services=["Visual grading"],
                 contact="+91 77777 10101",
                 verification_status="DEMO", status="ACTIVE", is_demo=True),
        ]
        for s in storage_seed:
            db.add(models.StorageFacility(**s))
        db.commit()

        # ---- Demo Transactions with full lifecycle events (Phase 10, 12) ----
        # Transaction 1: Completed (farmer Ramesh sold Tomato to FreshFoods)
        txn1 = models.Transaction(
            listing_id=listings[0].id, farmer_id=ramesh.id, buyer_id=freshfoods.id,
            final_price_per_kg=27.0, quantity_kg=2000,
            total_amount=54000.0, market_used="Bilaspur",
            status="COMPLETED",
        )
        db.add(txn1)
        db.flush()
        txn1_events = [
            ("OFFER_CREATED", "Offer of ₹27/kg submitted by FreshFoods", "buyer", freshfoods.id,
             today - dt.timedelta(days=10)),
            ("OFFER_ACCEPTED", "Offer accepted by Ramesh Kumar", "farmer", ramesh.id,
             today - dt.timedelta(days=10, hours=2)),
            ("ORDER_CONFIRMED", "Order confirmed by both parties", "system", None,
             today - dt.timedelta(days=9)),
            ("LOGISTICS_CONFIRMED", "Transport arranged via shared vehicle", "farmer", ramesh.id,
             today - dt.timedelta(days=8)),
            ("PICKED_UP", "Produce picked up from Bilaspur", "system", None,
             today - dt.timedelta(days=7)),
            ("IN_TRANSIT", "In transit to Raipur", "system", None,
             today - dt.timedelta(days=7, hours=3)),
            ("DELIVERED", "Delivered to FreshFoods, Raipur", "buyer", freshfoods.id,
             today - dt.timedelta(days=5)),
            ("PAYMENT_INITIATED", "Payment of ₹54,000 initiated via NEFT", "buyer", freshfoods.id,
             today - dt.timedelta(days=5, hours=4)),
            ("PAYMENT_RECEIVED", "Payment confirmed received by farmer", "farmer", ramesh.id,
             today - dt.timedelta(days=4)),
            ("COMPLETED", "Transaction completed successfully", "system", None,
             today - dt.timedelta(days=4, hours=1)),
        ]
        for etype, desc, by, by_id, ts in txn1_events:
            db.add(models.TransactionEvent(
                transaction_id=txn1.id, event_type=etype, description=desc,
                performed_by=by, performed_by_id=by_id,
                created_at=dt.datetime.combine(ts, dt.time(10, 0)) if isinstance(ts, dt.date) else ts,
            ))

        # Transaction 2: In-progress (Sunita → GreenBasket, waiting payment)
        txn2 = models.Transaction(
            listing_id=listings[2].id, farmer_id=sunita.id, buyer_id=greenbasket.id,
            final_price_per_kg=18.5, quantity_kg=3000,
            total_amount=55500.0, market_used="Raigarh",
            status="DELIVERED",
        )
        db.add(txn2)
        db.flush()
        txn2_events = [
            ("OFFER_CREATED", "Offer of ₹18.5/kg submitted by GreenBasket", "buyer", greenbasket.id,
             today - dt.timedelta(days=4)),
            ("OFFER_ACCEPTED", "Offer accepted by Sunita Verma", "farmer", sunita.id,
             today - dt.timedelta(days=4, hours=1)),
            ("ORDER_CONFIRMED", "Order confirmed", "system", None, today - dt.timedelta(days=3)),
            ("LOGISTICS_CONFIRMED", "Transport confirmed", "farmer", sunita.id,
             today - dt.timedelta(days=3, hours=6)),
            ("PICKED_UP", "Produce picked up from Raigarh", "system", None,
             today - dt.timedelta(days=2)),
            ("DELIVERED", "Delivered to GreenBasket", "buyer", greenbasket.id,
             today - dt.timedelta(days=1)),
        ]
        for etype, desc, by, by_id, ts in txn2_events:
            db.add(models.TransactionEvent(
                transaction_id=txn2.id, event_type=etype, description=desc,
                performed_by=by, performed_by_id=by_id,
                created_at=dt.datetime.combine(ts, dt.time(9, 0)) if isinstance(ts, dt.date) else ts,
            ))
        db.commit()
        db.refresh(txn1); db.refresh(txn2)

        # Payment for txn1 (completed/paid)
        db.add(models.Payment(
            transaction_id=txn1.id, buyer_id=freshfoods.id, farmer_id=ramesh.id,
            amount=54000.0, currency="INR", payment_status="PAID",
            payment_method="NEFT", payment_reference="CW-PAY-DEMO-00001",
            payment_due_date=(today - dt.timedelta(days=5)).isoformat(),
            initiated_at=dt.datetime.combine(today - dt.timedelta(days=5), dt.time(14, 0)),
            received_at=dt.datetime.combine(today - dt.timedelta(days=4), dt.time(10, 0)),
            notes="Demo simulated payment — not a real financial transaction.",
            is_demo=True,
        ))
        # Payment for txn2 (pending)
        db.add(models.Payment(
            transaction_id=txn2.id, buyer_id=greenbasket.id, farmer_id=sunita.id,
            amount=55500.0, currency="INR", payment_status="DUE",
            payment_due_date=(today + dt.timedelta(days=2)).isoformat(),
            notes="Demo simulated payment — payment due within 2 days of delivery.",
            is_demo=True,
        ))

        # Demo Grievance (Phase 13)
        db.add(models.Grievance(
            transaction_id=txn2.id,
            raised_by="farmer", raised_by_id=sunita.id,
            against_user="buyer", against_user_id=greenbasket.id,
            category="PAYMENT",
            description="Payment is overdue by 1 day. No response from buyer. (Demo grievance)",
            status="OPEN", priority="HIGH",
        ))
        db.commit()

        print("  Inserted demo verifications, demands, lots, storage, transactions, payments, grievances.")
        print("CropRetain demo data seeded successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
