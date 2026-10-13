import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models
from app.database import Base
from app.routers import offers as offers_router


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_accepting_partial_listing_offer_preserves_remaining_inventory(db):
    farmer = models.Farmer(name="Farmer", email="farmer@example.com", password_hash="x", location="Bilaspur")
    buyer = models.Buyer(company_name="Buyer", email="buyer@example.com", password_hash="x", location="Bilaspur")
    db.add_all([farmer, buyer])
    db.flush()
    listing = models.CropListing(
        farmer_id=farmer.id, crop="Tomato", quantity_kg=100,
        expected_price_per_kg=30, location="Bilaspur", available_date="2026-09-05",
    )
    db.add(listing)
    db.flush()
    offer = models.BuyerOffer(
        buyer_id=buyer.id, listing_id=listing.id, offered_price_per_kg=32,
        quantity_kg=40, status="pending",
    )
    db.add(offer)
    db.commit()

    result = offers_router.accept_offer(offer.id, farmer, db)

    db.refresh(listing)
    assert result["accepted"] is True
    assert listing.quantity_kg == 60
    assert listing.status == "active"
    transaction = db.query(models.Transaction).one()
    assert transaction.quantity_kg == 40


def test_accepting_partial_lot_offer_preserves_remaining_inventory(db):
    farmer = models.Farmer(name="Farmer", email="farmer@example.com", password_hash="x", location="Bilaspur")
    buyer = models.Buyer(company_name="Buyer", email="buyer@example.com", password_hash="x", location="Bilaspur")
    db.add_all([farmer, buyer])
    db.flush()
    lot = models.Lot(
        lot_number="LOT-TEST-001", farmer_id=farmer.id, crop="Tomato", quantity_kg=100,
        location="Bilaspur", expected_price=30, status="UNDER_OFFER",
    )
    db.add(lot)
    db.flush()
    offer = models.BuyerOffer(
        buyer_id=buyer.id, lot_id=lot.id, offered_price_per_kg=32,
        quantity_kg=40, status="pending",
    )
    db.add(offer)
    db.commit()

    result = offers_router.accept_offer(offer.id, farmer, db)

    db.refresh(lot)
    assert result["accepted"] is True
    assert lot.quantity_kg == 60
    assert lot.status == "AVAILABLE"
    transaction = db.query(models.Transaction).one()
    assert transaction.lot_id == lot.id
    assert transaction.quantity_kg == 40
