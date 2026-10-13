"""
Priority 8/9 — receipt generation and SHA-256 integrity tests.

The properties that actually matter here:
  - a receipt snapshots REAL transaction data, and records None (not a
    plausible default) for anything the DB genuinely doesn't have
  - the canonical form is order-independent, so verification can't fail
    spuriously on dict ordering
  - an untampered receipt verifies
  - a TAMPERED receipt fails verification (the whole point of the hash)
  - regeneration is idempotent -- a reissued receipt would otherwise get a
    new generated_at and therefore a different hash
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import receipt_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def txn(db):
    farmer = models.Farmer(name="Sunita Verma", email="s@test.com", password_hash="x", location="Raigarh")
    buyer = models.Buyer(company_name="FreshFoods Pvt Ltd", email="b@test.com", password_hash="x", location="Raipur")
    db.add_all([farmer, buyer])
    db.commit()
    t = models.Transaction(
        farmer_id=farmer.id, buyer_id=buyer.id,
        final_price_per_kg=28.5, quantity_kg=2500, total_amount=71250.0,
        market_used="Mahasamund", status="COMPLETED",
    )
    db.add(t)
    db.commit()
    db.add(models.TransactionEvent(
        transaction_id=t.id, event_type="OFFER_ACCEPTED", performed_by="buyer",
    ))
    db.commit()
    return t


def test_receipt_snapshots_real_transaction_data(db, txn):
    r = receipt_service.generate_receipt(db, txn)

    p = r.payload
    assert p["transaction_id"] == txn.id
    assert p["supplier"]["name"] == "Sunita Verma"
    assert p["buyer"]["name"] == "FreshFoods Pvt Ltd"
    assert p["quantity_kg"] == 2500
    assert p["sale_amount"] == 71250.0
    assert r.receipt_id.startswith("CW-RCPT-")
    assert r.hash_algorithm == "SHA-256"
    assert len(r.hash_value) == 64  # hex sha256


def test_missing_transport_cost_is_none_not_fabricated(db, txn):
    """No transport request linked -> transport_cost must be None, and
    total must not silently invent one."""
    r = receipt_service.generate_receipt(db, txn)
    assert r.payload["transport_cost"] is None
    assert r.payload["total_amount"] == 71250.0


def test_untampered_receipt_verifies(db, txn):
    r = receipt_service.generate_receipt(db, txn)
    result = receipt_service.verify_receipt(r)

    assert result["integrity_verified"] is True
    assert result["result"] == "INTEGRITY_VERIFIED"
    assert result["stored_hash"] == result["recomputed_hash"]


def test_tampered_receipt_fails_verification(db, txn):
    """The entire point of the hash: altering the stored content after
    issue must be detectable."""
    r = receipt_service.generate_receipt(db, txn)

    tampered = dict(r.payload)
    tampered["sale_amount"] = 999999.0   # someone edits the amount
    r.payload = tampered

    result = receipt_service.verify_receipt(r)
    assert result["integrity_verified"] is False
    assert result["result"] == "INTEGRITY_MISMATCH"
    assert result["stored_hash"] != result["recomputed_hash"]


def test_canonical_form_is_key_order_independent(db):
    """Verification must not fail just because a dict was built in a
    different order -- otherwise the mechanism is useless in practice."""
    a = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}}
    b = {"a": 1, "nested": {"x": 1, "y": 2}, "b": 2}
    assert receipt_service.compute_hash(a) == receipt_service.compute_hash(b)


def test_hash_covers_receipt_id_and_generated_at(db, txn):
    """Issue metadata is inside the hashed payload, so altering it is
    also detected -- not just the money fields."""
    r = receipt_service.generate_receipt(db, txn)
    tampered = dict(r.payload)
    tampered["receipt_id"] = "CW-RCPT-999999"
    r.payload = tampered
    assert receipt_service.verify_receipt(r)["integrity_verified"] is False


def test_regeneration_is_idempotent(db, txn):
    """A receipt is an issued document; asking again returns the same one
    rather than minting a new hash for the same transaction."""
    first = receipt_service.generate_receipt(db, txn)
    second = receipt_service.generate_receipt(db, txn)

    assert first.receipt_id == second.receipt_id
    assert first.hash_value == second.hash_value
    assert db.query(models.Receipt).filter_by(transaction_id=txn.id).count() == 1


def test_receipt_generation_records_a_transaction_event(db, txn):
    receipt_service.generate_receipt(db, txn)
    events = db.query(models.TransactionEvent).filter_by(
        transaction_id=txn.id, event_type="RECEIPT_GENERATED",
    ).all()
    assert len(events) == 1


def test_rendered_document_contains_hash_and_integrity_caveat(db, txn):
    r = receipt_service.generate_receipt(db, txn)
    text = receipt_service.render_receipt_text(r)

    assert "CropRetain Transaction Receipt" in text
    assert r.hash_value in text
    assert r.receipt_id in text
    # The caveat must travel with the document -- SHA-256 proves content
    # integrity, not that the trade really happened.
    assert "does not, on its own, prove" in text
