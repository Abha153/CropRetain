"""
Regression test for the FarmPool agreed-price integration.

Bug being fixed: shared_transport_plan() / POST /logistics/farmpool always
allocated cost from the transport_optimizer ESTIMATE, even after a real
transporter negotiation had produced a server-side
TransportRequest.transporter_agreed_price. This meant a farmer could see
"your share: X" based on a number that had already been superseded by a
real agreed price -- an honesty bug, not just a cosmetic one.

Fix under test:
  - shared_transport_plan(..., agreed_transport_price=None) is backward
    compatible: with no agreed price, behavior/labels are unchanged
    ("ESTIMATED", same figures as before).
  - When an agreed_transport_price IS supplied, the existing proportional
    allocation rule (share = total * my_qty / pool_qty) is applied to that
    real price instead of the estimate, the estimate is preserved
    alongside it (never overwritten), and cost_basis/label flip to
    "AGREED".
  - POST /logistics/farmpool only uses an agreed price that actually
    exists server-side on the linked TransportRequest -- it can never be
    supplied by the client directly.

Run: pytest backend/tests/test_farmpool_agreed_price.py -v
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models
from app.database import Base, get_db
from app.services.transport_optimizer import shared_transport_plan, find_nearby_pool_partners


# ─── Pure-function tests: shared_transport_plan() ────────────────────────────

def test_no_agreed_price_keeps_estimate_behavior():
    """Backward compatibility: omitting agreed_transport_price must behave
    exactly like before the fix."""
    plan = shared_transport_plan("Tomato", "Bilaspur", 500, "Raipur")
    assert plan["cost_basis"] == "ESTIMATED"
    assert plan["label"] == "ESTIMATED"
    assert plan["transporter_agreed_price"] is None
    # The allocation basis with no agreed price is the estimate itself.
    partners_total = 500 + sum(
        p["quantity_kg"] for p in find_nearby_pool_partners("Tomato", "Bilaspur", 500)
    )
    expected_share = round(plan["estimated_shared_transport_cost"] * (500 / partners_total), 2)
    assert plan["your_shared_transport_cost"] == expected_share


def test_agreed_price_1500_overrides_estimate_1700_allocation():
    """The exact scenario from the spec: estimated ≈ ₹1700, agreed = ₹1500
    -- farmer shares must be computed from ₹1500, not the estimate, once
    an agreement exists."""
    ESTIMATED = 1700.0
    AGREED = 1500.0

    plan_before = shared_transport_plan("Tomato", "Bilaspur", 500, "Raipur")
    # Confirm we're exercising a realistic pool (>1 participant) so the
    # allocation fraction is actually meaningful, not just 100%.
    total_qty = plan_before["total_pool_quantity_kg"]
    assert total_qty > 500

    plan_after = shared_transport_plan(
        "Tomato", "Bilaspur", 500, "Raipur", agreed_transport_price=AGREED
    )

    my_fraction = 500 / total_qty
    expected_share_from_agreed = round(AGREED * my_fraction, 2)
    expected_share_from_estimated = round(ESTIMATED * my_fraction, 2)

    assert plan_after["cost_basis"] == "AGREED"
    assert plan_after["label"] == "AGREED"
    assert plan_after["transporter_agreed_price"] == AGREED
    assert plan_after["your_shared_transport_cost"] == expected_share_from_agreed
    # Must NOT equal what a ₹1700-estimate-based allocation would produce.
    assert plan_after["your_shared_transport_cost"] != expected_share_from_estimated
    # The estimate must survive untouched alongside the agreed-price figure.
    assert plan_after["estimated_shared_transport_cost"] == plan_before["estimated_shared_transport_cost"]
    assert plan_after["your_estimated_shared_share"] == plan_before["your_shared_transport_cost"]


def test_agreed_price_allocation_uses_existing_proportional_rule():
    """The allocation RULE itself (share proportional to quantity) must be
    identical before/after -- only the total it's applied to changes."""
    partners = find_nearby_pool_partners("Tomato", "Bilaspur", 500)
    total_qty = 500 + sum(p["quantity_kg"] for p in partners)

    plan = shared_transport_plan("Tomato", "Bilaspur", 500, "Raipur", agreed_transport_price=2000.0)
    assert plan["your_shared_transport_cost"] == round(2000.0 * (500 / total_qty), 2)


# ─── Endpoint-level test: POST /logistics/farmpool honors DB-stored agreement ─

@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    from app.main import app

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _make_farmer(db):
    f = models.Farmer(name="Farmer", email="farmpool-farmer@example.com", password_hash="x", location="Bilaspur")
    db.add(f)
    db.flush()
    return f


def _make_transport_request(db, farmer, estimated_cost=1700.0, agreed_price=None):
    r = models.TransportRequest(
        farmer_id=farmer.id,
        pickup_location="Bilaspur",
        destination="Raipur",
        estimated_cost=estimated_cost,
        transporter_agreed_price=agreed_price,
        negotiation_status="AGREED" if agreed_price is not None else "OPEN",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_farmpool_endpoint_uses_estimate_before_agreement(client, db):
    farmer = _make_farmer(db)
    tr = _make_transport_request(db, farmer, estimated_cost=1700.0, agreed_price=None)

    resp = client.post("/logistics/farmpool", json={
        "crop": "Tomato", "location": "Bilaspur", "quantity_kg": 500,
        "destination_market": "Raipur", "transport_request_id": tr.id,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["cost_basis"] == "ESTIMATED"
    assert body["transporter_agreed_price"] is None


def test_farmpool_endpoint_uses_real_agreed_price_after_agreement(client, db):
    farmer = _make_farmer(db)
    tr = _make_transport_request(db, farmer, estimated_cost=1700.0, agreed_price=1500.0)

    resp = client.post("/logistics/farmpool", json={
        "crop": "Tomato", "location": "Bilaspur", "quantity_kg": 500,
        "destination_market": "Raipur", "transport_request_id": tr.id,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["cost_basis"] == "AGREED"
    assert body["transporter_agreed_price"] == 1500.0

    total_qty = body["total_pool_quantity_kg"]
    expected_share = round(1500.0 * (500 / total_qty), 2)
    assert body["your_shared_transport_cost"] == expected_share

    # The TransportRequest's own estimated_cost (1700) must remain
    # untouched in the database -- the fix must never overwrite it.
    db.refresh(tr)
    assert tr.estimated_cost == 1700.0
    assert tr.transporter_agreed_price == 1500.0


def test_farmpool_endpoint_ignores_client_supplied_agreed_price():
    """The FarmPoolRequest schema has no client-writable agreed-price
    field at all -- only a transport_request_id the server resolves
    itself -- so a client cannot spoof an agreed price."""
    from app import schemas
    assert "agreed_price" not in schemas.FarmPoolRequest.model_fields
    assert "transporter_agreed_price" not in schemas.FarmPoolRequest.model_fields
    assert "transport_request_id" in schemas.FarmPoolRequest.model_fields
