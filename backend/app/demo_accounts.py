"""
Opt-in demo accounts for the farmer-to-buyer journey.

    DEMO_ACCOUNT_PASSWORD='<choose 12+ characters>' python -m app.demo_accounts

Creates (only if missing) two clearly labelled DEMO accounts:
  * Abha Tiwari   - farmer, Bilaspur, Chhattisgarh  (abha.tiwari@cropretain.demo)
  * Preeti Tiwari - buyer,  Bilaspur, Chhattisgarh  (preeti.tiwari@cropretain.demo),
                    UNVERIFIED: no verification record is created.
plus one simulated listing for Abha, one simulated demand and one simulated
offer from Preeti. Every simulated record says DEMO in its text.

Safety rules, enforced in code:
  * Never runs when APP_ENV=production.
  * The password comes only from the environment; there is no default and it
    is never printed or stored in the repo. It is hashed with the app's
    normal password hashing.
  * Idempotent: re-running adds nothing. An existing account (same e-mail) is
    left untouched - its password is never overwritten.
  * Not called from application startup.
"""
import datetime as dt
import sys

from app import models
from app.demo_policy import demo_accounts_allowed, demo_password_problem

ABHA_EMAIL = "abha.tiwari@cropretain.demo"
PREETI_EMAIL = "preeti.tiwari@cropretain.demo"

LISTING_NOTE = "DEMO listing: simulated for testing, not a real offer to sell."
DEMAND_NOTE = "DEMO requirement: simulated for testing, not a real purchase need."
OFFER_MESSAGE = "[DEMO] Simulated offer for testing; not a real commercial offer."


def seed_demo_accounts(db, password: str) -> dict:
    """Create the demo accounts and sample records that are missing.
    Returns {"created": [...], "existing": [...]} (labels, never secrets)."""
    from app.auth_utils import hash_password  # imported lazily: needs the app stack

    created, existing = [], []
    today = dt.date.today()

    farmer = db.query(models.Farmer).filter(models.Farmer.email == ABHA_EMAIL).first()
    if farmer:
        existing.append("farmer Abha Tiwari")
    else:
        farmer = models.Farmer(
            name="Abha Tiwari", email=ABHA_EMAIL, password_hash=hash_password(password),
            phone="", location="Bilaspur", latitude=22.0797, longitude=82.1409,
            crops=["Soybean", "Paddy (Rice)"], preferred_language="hi",
        )
        db.add(farmer)
        db.flush()
        created.append("farmer Abha Tiwari")

    buyer = db.query(models.Buyer).filter(models.Buyer.email == PREETI_EMAIL).first()
    if buyer:
        existing.append("buyer Preeti Tiwari")
    else:
        # Same starting state as a real self-registered buyer: pending, neutral
        # scores, and NO BuyerVerification record.
        buyer = models.Buyer(
            company_name="Preeti Tiwari (DEMO buyer)", email=PREETI_EMAIL,
            password_hash=hash_password(password), phone="",
            location="Bilaspur", latitude=22.0797, longitude=82.1409,
            buyer_type="retailer", verification_status="pending",
            reliability_score=60.0, payment_history_score=60.0,
            crops_of_interest=["Soybean"], preferred_language="en",
        )
        db.add(buyer)
        db.flush()
        created.append("buyer Preeti Tiwari")

    listing = db.query(models.CropListing).filter(
        models.CropListing.farmer_id == farmer.id,
        models.CropListing.note == LISTING_NOTE).first()
    if listing is None:
        listing = models.CropListing(
            farmer_id=farmer.id, crop="Soybean", quantity_kg=1200, quality_grade="B",
            quality_score=75, expected_price_per_kg=42, location="Bilaspur",
            available_date=(today + dt.timedelta(days=7)).isoformat(),
            min_acceptable_price=38,
            bidding_deadline=(today + dt.timedelta(days=10)).isoformat(),
            note=LISTING_NOTE,
        )
        db.add(listing)
        db.flush()
        created.append("sample listing")

    if not db.query(models.BuyerDemand).filter(
            models.BuyerDemand.buyer_id == buyer.id,
            models.BuyerDemand.additional_requirements == DEMAND_NOTE).first():
        db.add(models.BuyerDemand(
            buyer_id=buyer.id, crop="Soybean", required_quantity_kg=1000,
            target_price_per_kg=40, quality_grade="B", delivery_location="Bilaspur",
            additional_requirements=DEMAND_NOTE, status="ACTIVE",
            expires_at=(today + dt.timedelta(days=14)).isoformat(),
        ))
        created.append("sample demand")

    if not db.query(models.BuyerOffer).filter(
            models.BuyerOffer.buyer_id == buyer.id,
            models.BuyerOffer.listing_id == listing.id,
            models.BuyerOffer.message == OFFER_MESSAGE).first():
        db.add(models.BuyerOffer(
            buyer_id=buyer.id, listing_id=listing.id, offered_price_per_kg=39.0,
            quantity_kg=1000, message=OFFER_MESSAGE,
        ))
        created.append("sample offer")

    db.commit()
    return {"created": created, "existing": existing}


def main() -> int:
    from app.config import settings
    if not demo_accounts_allowed(settings.app_env):
        print("Refusing to create demo accounts: APP_ENV is production.", file=sys.stderr)
        return 2
    problem = demo_password_problem(settings.demo_account_password)
    if problem:
        print(f"Cannot create demo accounts: {problem}", file=sys.stderr)
        return 2

    from app.database import Base, engine, SessionLocal
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed_demo_accounts(db, settings.demo_account_password)
        try:  # round 1 for the sample offer; also done lazily/at startup
            from app.services.offer_negotiation import backfill_offer_rounds
            backfill_offer_rounds(db)
        except Exception as exc:  # pragma: no cover - best effort
            print(f"Note: offer-round backfill skipped ({type(exc).__name__}).", file=sys.stderr)
    finally:
        db.close()
    print("Created:", ", ".join(result["created"]) or "nothing new")
    print("Already present:", ", ".join(result["existing"]) or "none")
    print(f"Log in with {ABHA_EMAIL} (farmer) or {PREETI_EMAIL} (buyer) and the password you set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
